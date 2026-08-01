#!/usr/bin/env python3
"""Generate, edit, and compose images with Google's Gemini image models.

Stdlib only. Image bytes are read from and written to disk directly and never
printed, so nothing base64-shaped reaches a calling agent's context.
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

MODELS = {
    "lite": "gemini-3.1-flash-lite-image",
    "flash": "gemini-3.1-flash-image",
    "pro": "gemini-3-pro-image",
}

MODEL_SIZES = {
    "lite": ["512", "1K"],
    "flash": ["512", "1K", "2K", "4K"],
    "pro": ["512", "1K", "2K", "4K"],
}

# USD per 1M tokens, by output modality.
RATES = {
    "lite": {"input": 0.25, "text": 1.50, "image": 30.0},
    "flash": {"input": 0.50, "text": 3.00, "image": 60.0},
    "pro": {"input": 2.00, "text": 12.00, "image": 120.0},
}

# Published per-image prices, used only when the response omits usage.
LISTED_COST = {
    "lite": {"512": 0.034, "1K": 0.034},
    "flash": {"512": 0.045, "1K": 0.067, "2K": 0.101, "4K": 0.151},
    "pro": {"512": 0.134, "1K": 0.134, "2K": 0.134, "4K": 0.240},
}

ASPECT_RATIOS = [
    "1:1", "3:2", "2:3", "3:4", "4:3",
    "4:5", "5:4", "9:16", "16:9", "21:9",
]

OUTPUT_MIME = "image/jpeg"
OUTPUT_SUFFIXES = {".jpg", ".jpeg"}
INPUT_MIMES = {"image/png", "image/jpeg", "image/webp"}
MAX_REFERENCE_IMAGES = 14


class Failure(Exception):
    pass


def api_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise Failure(
            "GEMINI_API_KEY is not set.\n"
            "  Get a key at https://aistudio.google.com/apikey, enable billing on\n"
            "  its project (image models have no free tier), then export it.\n"
            "  Put the export in ~/.zshenv, not ~/.zshrc — zsh skips .zshrc for the\n"
            "  non-interactive shells that coding agents run commands in."
        )
    return key


def read_prompt(args):
    if args.prompt:
        return args.prompt
    if args.prompt_file == "-":
        return sys.stdin.read().strip()
    path = Path(args.prompt_file)
    if not path.is_file():
        raise Failure(f"prompt file not found: {path}")
    text = path.read_text().strip()
    if not text:
        raise Failure(f"prompt file is empty: {path}")
    return text


def encode_image(path):
    path = Path(path)
    if not path.is_file():
        raise Failure(f"input image not found: {path}")
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in INPUT_MIMES:
        raise Failure(f"unsupported input image type for {path.name}: {mime}")
    return {
        "type": "image",
        "mime_type": mime,
        "data": base64.b64encode(path.read_bytes()).decode(),
    }


def resolve_size(model, size):
    allowed = MODEL_SIZES[model]
    if size not in allowed:
        raise Failure(
            f"model '{model}' does not support size {size}; "
            f"supported: {', '.join(allowed)}"
        )
    return size


def output_paths(out, count):
    base = Path(out)
    if base.suffix.lower() not in OUTPUT_SUFFIXES:
        raise Failure(
            f"--out must end in .jpg or .jpeg (got '{base.suffix or 'no extension'}').\n"
            f"  The API only returns JPEG. To end up with a PNG, render to .jpg and\n"
            f"  convert: magick {base.stem}.jpg {base.stem}.png"
        )
    if count == 1:
        targets = [base]
    else:
        targets = [
            base.with_name(f"{base.stem}-{i}{base.suffix}")
            for i in range(1, count + 1)
        ]
    for target in targets:
        if target.exists():
            raise Failure(
                f"{target} already exists (this tool never overwrites).\n"
                f"  Pick another name, e.g. --out {suggest_free_name(target)}"
            )
    parent = targets[0].parent
    if not parent.is_dir():
        raise Failure(f"output directory does not exist: {parent}")
    return targets


def suggest_free_name(path):
    stem, suffix, parent = path.stem, path.suffix, path.parent
    for version in range(2, 100):
        candidate = parent / f"{stem}-v{version}{suffix}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}-{int(time.time())}{suffix}"


def build_request(prompt, images, model, size, aspect_ratio, thinking, grounding):
    if len(images) > MAX_REFERENCE_IMAGES:
        raise Failure(
            f"{len(images)} reference images given, maximum is {MAX_REFERENCE_IMAGES}"
        )
    body = {
        "model": MODELS[model],
        "input": [{"type": "text", "text": prompt}] + images,
        "response_format": {
            "type": "image",
            "mime_type": OUTPUT_MIME,
            "aspect_ratio": aspect_ratio,
            "image_size": size,
        },
    }
    if thinking != "minimal":
        body["generation_config"] = {"thinking_level": thinking}
    if grounding:
        if model == "lite":
            raise Failure("--grounding is not supported by the lite model")
        body["tools"] = [
            {"type": "google_search", "search_types": ["web_search", "image_search"]}
        ]
    return body


def call_api(body, timeout):
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "x-goog-api-key": api_key(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise Failure(describe_http_error(error)) from None
    except urllib.error.URLError as error:
        raise Failure(f"could not reach the Gemini API: {error.reason}") from None


def describe_http_error(error):
    detail = error.read().decode(errors="replace")[:800]
    hints = {
        400: "check aspect ratio and image size against the model",
        401: "GEMINI_API_KEY is invalid",
        403: "the key lacks access; confirm the API is enabled for its project",
        404: "this model does not offer that image size",
        429: "quota exhausted or billing not enabled (image models have no free tier)",
    }
    hint = hints.get(error.code, "")
    return f"HTTP {error.code} {error.reason}" + (f" — {hint}" if hint else "") + f"\n{detail}"


def harvest(payload):
    """Pull image parts and text out of the response without assuming its shape."""
    images, texts = [], []

    def walk(node):
        if isinstance(node, dict):
            mime = node.get("mime_type") or node.get("mimeType")
            data = node.get("data")
            if isinstance(mime, str) and mime.startswith("image/") and isinstance(data, str):
                images.append((mime, data))
                return
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                texts.append(node["text"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return images, texts


def measure_cost(payload, model, size):
    """Bill from reported usage; fall back to the published per-image price."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return LISTED_COST[model][size], {}

    modalities = usage.get("output_tokens_by_modality") or []
    image_tokens = sum(
        entry.get("tokens", 0) for entry in modalities
        if entry.get("modality") == "image"
    )
    input_tokens = usage.get("total_input_tokens", 0)
    output_tokens = usage.get("total_output_tokens", 0)
    text_tokens = max(output_tokens - image_tokens, 0)

    rates = RATES[model]
    cost = (
        input_tokens * rates["input"]
        + text_tokens * rates["text"]
        + image_tokens * rates["image"]
    ) / 1_000_000

    counts = {
        "input_tokens": input_tokens,
        "image_tokens": image_tokens,
        "text_tokens": text_tokens,
    }
    return cost, counts


def log_path(explicit, out):
    if explicit:
        return Path(explicit)
    directory = Path(out).resolve().parent
    for candidate in [directory, *directory.parents]:
        if (candidate / ".git").exists():
            return candidate / ".nanobanana.jsonl"
    return Path.cwd() / ".nanobanana.jsonl"


def record(path, entry):
    try:
        with path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"warning: could not write log {path}: {error}", file=sys.stderr)


def run(args):
    model = args.model
    size = resolve_size(model, args.size)
    if args.aspect_ratio not in ASPECT_RATIOS:
        raise Failure(
            f"unsupported aspect ratio {args.aspect_ratio}; "
            f"supported: {', '.join(ASPECT_RATIOS)}"
        )

    prompt = read_prompt(args)
    images = [encode_image(path) for path in (args.input or [])]

    if args.command == "edit" and not images:
        raise Failure("edit needs at least one --input image")
    if args.command == "compose" and len(images) < 2:
        raise Failure("compose needs at least two --input images")

    targets = output_paths(args.out, args.n)
    body = build_request(
        prompt, images, model, size, args.aspect_ratio, args.thinking, args.grounding,
    )

    log = log_path(args.log, args.out)
    total = 0.0

    for target in targets:
        started = time.monotonic()
        payload = call_api(body, args.timeout)
        elapsed = time.monotonic() - started
        found, texts = harvest(payload)

        if not found:
            status = payload.get("status", "unknown")
            note = " ".join(texts)[:500]
            raise Failure(
                f"no image in the response (status: {status}).\n"
                f"{note or 'The model may have refused the prompt.'}"
            )

        image_mime, data = found[0]
        target.write_bytes(base64.b64decode(data))
        cost, counts = measure_cost(payload, model, size)
        total += cost

        record(log, {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "out": str(target),
            "command": args.command,
            "model": MODELS[model],
            "size": size,
            "aspect_ratio": args.aspect_ratio,
            "mime_type": image_mime,
            "thinking_level": args.thinking,
            "grounding": args.grounding,
            "inputs": args.input or [],
            "prompt": prompt,
            "cost_usd": round(cost, 5),
            "seconds": round(elapsed, 1),
            **counts,
        })

        size_kb = target.stat().st_size / 1024
        print(f"{target}  {image_mime}  {size_kb:.0f} KB  {elapsed:.1f}s  ${cost:.4f}")
        for text in texts:
            print(f"  model note: {text.strip()[:300]}")

    print(f"total ${total:.4f}  ({MODELS[model]} {size} {args.aspect_ratio})  logged to {log}")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="nanobanana.py",
        description="Generate, edit, and compose images with Gemini image models.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("generate", "text-to-image"),
        ("edit", "modify one image with a text instruction"),
        ("compose", "combine two or more reference images"),
    ]:
        sub = subparsers.add_parser(name, help=help_text)
        prompt_group = sub.add_mutually_exclusive_group(required=True)
        prompt_group.add_argument("--prompt-file", help="path to the prompt, or - for stdin")
        prompt_group.add_argument("--prompt", help="inline prompt; prefer --prompt-file")
        sub.add_argument("--out", required=True, help=".jpg path, never overwritten")
        sub.add_argument("--input", action="append", metavar="PATH",
                         help="reference image; repeat for more (max 14)")
        sub.add_argument("--model", choices=MODELS, default="flash")
        sub.add_argument("--size", default="2K", choices=["512", "1K", "2K", "4K"])
        sub.add_argument("--ar", "--aspect-ratio", dest="aspect_ratio", default="1:1",
                         metavar="RATIO", help=f"one of: {', '.join(ASPECT_RATIOS)}")
        sub.add_argument("--thinking", choices=["minimal", "high"], default="minimal")
        sub.add_argument("--grounding", action="store_true",
                         help="ground the render in Google Search results")
        sub.add_argument("--n", type=int, default=1, metavar="COUNT",
                         help="render COUNT variants as <out>-1, <out>-2, ...")
        sub.add_argument("--log", help="JSONL log path (default: <repo root>/.nanobanana.jsonl)")
        sub.add_argument("--timeout", type=int, default=300, metavar="SECONDS")

    args = parser.parse_args(argv)
    if args.n < 1:
        parser.error("--n must be at least 1")
    return args


def main():
    try:
        run(parse_args(sys.argv[1:]))
    except Failure as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
