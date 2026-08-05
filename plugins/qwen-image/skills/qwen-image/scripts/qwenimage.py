#!/usr/bin/env python3
"""Generate and edit images with Alibaba Cloud Model Studio's Qwen-Image models.

Stdlib only. The API hands back short-lived URLs; this downloads them straight
to disk, so no image bytes ever pass through a calling agent's context.
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

PATH = "/api/v1/services/aigc/multimodal-generation/generation"

# The five sizes qwen-image and qwen-image-plus accept; nothing else passes.
FIXED_SIZES = ["1664*928", "1472*1104", "1328*1328", "1104*1472", "928*1664"]

# Limits confirmed by probing the live API, not just the published docs.
# size rule: ("area", min, max) caps width*height and lets any shape through;
#            ("dim", min, max) caps each side; ("fixed", list); ("none",) means
#            the model ignores size entirely.
MODELS = {
    "qwen-image-3.0-pro": {
        "t2i": True, "i2i": True, "max_n": 6,
        "size": ("area", 262144, 6553600),
    },
    "qwen-image-2.0-pro": {
        "t2i": True, "i2i": False, "max_n": 6,
        "size": ("area", 262144, 4194304),
    },
    "qwen-image-2.0": {
        "t2i": True, "i2i": False, "max_n": 6,
        "size": ("area", 262144, 4194304),
    },
    "qwen-image-max": {
        "t2i": True, "i2i": False, "max_n": 1,
        "size": ("dim", 512, 2048),
    },
    "qwen-image-plus": {
        "t2i": True, "i2i": False, "max_n": 1,
        "size": ("fixed", FIXED_SIZES),
    },
    "qwen-image": {
        "t2i": True, "i2i": False, "max_n": 1,
        "size": ("fixed", FIXED_SIZES),
    },
    "qwen-image-edit-max": {
        "t2i": False, "i2i": True, "max_n": 6,
        "size": ("dim", 512, 2048),
    },
    "qwen-image-edit-plus": {
        "t2i": False, "i2i": True, "max_n": 6,
        "size": ("dim", 512, 2048),
    },
    # Ignores both n and size: always returns exactly one image at its own
    # chosen resolution. Passing n > 1 bills n renders and returns one.
    "qwen-image-edit": {
        "t2i": False, "i2i": True, "max_n": 1,
        "size": ("none",),
    },
}

DEFAULT_GENERATE_MODEL = "qwen-image-3.0-pro"
DEFAULT_EDIT_MODEL = "qwen-image-3.0-pro"

MAX_INPUT_IMAGES = 3
MAX_INPUT_BYTES = 10 * 1024 * 1024
INPUT_MIMES = {
    "image/jpeg", "image/png", "image/bmp",
    "image/tiff", "image/webp", "image/gif",
}
OUTPUT_SUFFIXES = {".png"}


class Failure(Exception):
    pass


def credentials():
    key = os.environ.get("QWEN_API_KEY")
    host = os.environ.get("QWEN_API_HOST")
    missing = [
        name for name, value in (("QWEN_API_KEY", key), ("QWEN_API_HOST", host))
        if not value
    ]
    if missing:
        raise Failure(
            f"{' and '.join(missing)} not set.\n"
            "  Both come from the Model Studio console (Singapore / ap-southeast-1):\n"
            "  the key from API-KEY, the host from your workspace's dedicated\n"
            "  endpoint, e.g. ws-xxxxxxxx.ap-southeast-1.maas.aliyuncs.com\n"
            "  Put the exports in ~/.zshenv, not ~/.zshrc — zsh skips .zshrc for the\n"
            "  non-interactive shells that coding agents run commands in."
        )
    return key, host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")


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
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise Failure(
            f"{path} is {path.stat().st_size / 1e6:.1f} MB; the limit is 10 MB per image"
        )
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in INPUT_MIMES:
        raise Failure(
            f"unsupported input image type for {path.name}: {mime or 'unknown'}\n"
            f"  supported: {', '.join(sorted(INPUT_MIMES))}"
        )
    data = base64.b64encode(path.read_bytes()).decode()
    return {"image": f"data:{mime};base64,{data}"}


def resolve_size(model, size):
    """Validate --size against the model before spending a request on it."""
    rule = MODELS[model]["size"]
    if rule[0] == "none":
        if size:
            raise Failure(f"{model} ignores --size; drop the flag")
        return None
    if not size:
        return None

    normalised = size.lower().replace("x", "*").replace("×", "*")
    parts = normalised.split("*")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise Failure(f"--size must look like 1664*928 (got '{size}')")
    width, height = (int(part) for part in parts)
    normalised = f"{width}*{height}"

    if rule[0] == "fixed":
        if normalised not in rule[1]:
            raise Failure(
                f"{model} only accepts these sizes: {', '.join(rule[1])}\n"
                f"  got {normalised}"
            )
    elif rule[0] == "area":
        _, low, high = rule
        if not low <= width * height <= high:
            raise Failure(
                f"{model} needs width*height between {low} and {high} pixels "
                f"(about {int(low ** 0.5)}² to {int(high ** 0.5)}²); "
                f"{normalised} is {width * height}"
            )
    elif rule[0] == "dim":
        _, low, high = rule
        if not (low <= width <= high and low <= height <= high):
            raise Failure(
                f"{model} needs each side between {low} and {high} pixels; got {normalised}"
            )
    return normalised


def resolve_model(command, model):
    if model not in MODELS:
        raise Failure(
            f"unknown model '{model}'\n  available: {', '.join(MODELS)}"
        )
    capability = "i2i" if command == "edit" else "t2i"
    if not MODELS[model][capability]:
        usable = [name for name, spec in MODELS.items() if spec[capability]]
        raise Failure(
            f"{model} does not support {command}\n  usable here: {', '.join(usable)}"
        )
    return model


def resolve_count(model, count):
    limit = MODELS[model]["max_n"]
    if count < 1:
        raise Failure("--n must be at least 1")
    if count > limit:
        extra = (
            "\n  It bills every requested render but only ever returns one image."
            if model == "qwen-image-edit" else ""
        )
        raise Failure(f"{model} supports --n up to {limit}, got {count}.{extra}")
    return count


def output_paths(out, count):
    base = Path(out)
    if base.suffix.lower() not in OUTPUT_SUFFIXES:
        raise Failure(
            f"--out must end in .png (got '{base.suffix or 'no extension'}').\n"
            f"  The API only returns PNG. To end up with a JPEG, render to .png and\n"
            f"  convert: magick {base.stem}.png {base.stem}.jpg"
        )
    if count == 1:
        targets = [base]
    else:
        targets = [
            base.with_name(f"{base.stem}-{index}{base.suffix}")
            for index in range(1, count + 1)
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


def build_request(prompt, images, model, size, count, args):
    content = images + [{"text": prompt}]
    parameters = {"prompt_extend": not args.no_prompt_extend}
    if count > 1:
        parameters["n"] = count
    if size:
        parameters["size"] = size
    if args.negative_prompt:
        parameters["negative_prompt"] = args.negative_prompt
    if args.seed is not None:
        parameters["seed"] = args.seed
    if args.watermark:
        parameters["watermark"] = True
    return {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }


def call_api(body, key, host, timeout, retries):
    """POST once, retrying only throttling — every other failure is final.

    Model Studio workspaces are rate limited tightly enough that a burst of
    renders will hit Throttling.RateQuota; that costs nothing and is worth
    waiting out.
    """
    url = f"https://{host}{PATH}"
    delay = 5
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            code, message, detail = read_error(error)
            if code and code.startswith("Throttling") and attempt < retries:
                print(
                    f"  rate limited, retrying in {delay}s "
                    f"({attempt + 1}/{retries})",
                    file=sys.stderr,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise Failure(describe_http_error(error.code, code, message, detail)) from None
        except urllib.error.URLError as error:
            raise Failure(f"could not reach {host}: {error.reason}") from None
    raise Failure("still rate limited after every retry; try again in a few minutes")


def read_error(error):
    detail = error.read().decode(errors="replace")
    try:
        parsed = json.loads(detail)
        return parsed.get("code"), parsed.get("message"), detail
    except json.JSONDecodeError:
        return None, None, detail


def describe_http_error(status, code, message, detail):
    hints = {
        "InvalidApiKey": (
            "QWEN_API_KEY is not valid for this endpoint. Beijing and Singapore "
            "issue separate keys and they are not interchangeable."
        ),
        "Model.AccessDenied": (
            "this key's workspace has no access to that model; some are "
            "limited preview and need an application in Model Gallery"
        ),
        "AllocationQuota.Exceeded": "the free quota or account balance is exhausted",
        "DataInspectionFailed": "the prompt or an input image was rejected by content moderation",
    }
    hint = hints.get(code, "")
    if code:
        head = f"HTTP {status} {code}: {message}"
    else:
        head = f"HTTP {status}\n{detail[:800]}"
    return head + (f"\n  {hint}" if hint else "")


def harvest(payload):
    """Pull image URLs and any text the model returned alongside them."""
    output = payload.get("output") or {}
    urls, texts = [], []
    for choice in output.get("choices") or []:
        for part in ((choice.get("message") or {}).get("content") or []):
            if isinstance(part, dict):
                if isinstance(part.get("image"), str):
                    urls.append(part["image"])
                elif isinstance(part.get("text"), str):
                    texts.append(part["text"])
    return urls, texts


def download(url, target, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            target.write_bytes(response.read())
    except urllib.error.URLError as error:
        raise Failure(
            f"generated the image but could not download it: {error}\n"
            f"  result URLs expire 24 hours after generation"
        ) from None


def log_path(explicit, out):
    if explicit:
        return Path(explicit)
    directory = Path(out).resolve().parent
    for candidate in [directory, *directory.parents]:
        if (candidate / ".git").exists():
            return candidate / ".qwenimage.jsonl"
    return Path.cwd() / ".qwenimage.jsonl"


def record(path, entry):
    try:
        with path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"warning: could not write log {path}: {error}", file=sys.stderr)


def run(args):
    key, host = credentials()
    model = resolve_model(args.command, args.model)
    size = resolve_size(model, args.size)
    count = resolve_count(model, args.n)

    prompt = read_prompt(args)
    images = [encode_image(path) for path in (args.input or [])]

    if args.command == "edit":
        if not images:
            raise Failure("edit needs at least one --input image")
        if len(images) > MAX_INPUT_IMAGES:
            raise Failure(
                f"{len(images)} input images given, the API accepts at most "
                f"{MAX_INPUT_IMAGES}"
            )

    targets = output_paths(args.out, count)
    body = build_request(prompt, images, model, size, count, args)

    started = time.monotonic()
    payload = call_api(body, key, host, args.timeout, args.retries)
    elapsed = time.monotonic() - started
    urls, texts = harvest(payload)

    if not urls:
        raise Failure(
            "no image in the response.\n"
            f"  {' '.join(texts)[:500] or json.dumps(payload)[:500]}"
        )
    if len(urls) < count:
        print(
            f"warning: asked for {count} images, the API returned {len(urls)}",
            file=sys.stderr,
        )
        targets = targets[:len(urls)]

    usage = payload.get("usage") or {}
    log = log_path(args.log, args.out)

    for target, url in zip(targets, urls):
        download(url, target, args.timeout)
        record(log, {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "out": str(target),
            "command": args.command,
            "model": model,
            "size": size,
            "requested_n": count,
            "seed": args.seed,
            "negative_prompt": args.negative_prompt,
            "prompt_extend": not args.no_prompt_extend,
            "watermark": args.watermark,
            "inputs": args.input or [],
            "prompt": prompt,
            "usage": usage,
            "request_id": payload.get("request_id"),
            "seconds": round(elapsed, 1),
        })
        kilobytes = target.stat().st_size / 1024
        print(f"{target}  {kilobytes:.0f} KB  {elapsed:.1f}s")

    for text in texts:
        print(f"  model note: {text.strip()[:300]}")

    print(f"{len(targets)} image(s){describe_usage(usage)} from {model}  logged to {log}")


def describe_usage(usage):
    """Summarise usage across both response shapes the API has been seen to use.

    The published schema documents width/height/image_count, but live responses
    return output_width/output_height/output_image_count plus a billing tier.
    """
    width = usage.get("output_width") or usage.get("width")
    height = usage.get("output_height") or usage.get("height")
    billed = usage.get("output_image_count") or usage.get("image_count")
    tier = usage.get("output_image_type")

    parts = []
    if width and height:
        parts.append(f" at {width}x{height}")
    if billed:
        parts.append(f", {billed} billed")
    if tier:
        parts.append(f" as {tier}")
    return "".join(parts)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="qwenimage.py",
        description="Generate and edit images with Qwen-Image on Model Studio.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    commands = [
        ("generate", "text-to-image", DEFAULT_GENERATE_MODEL),
        ("edit", "edit or fuse 1-3 input images with a text instruction", DEFAULT_EDIT_MODEL),
    ]
    for name, help_text, default_model in commands:
        sub = subparsers.add_parser(name, help=help_text)
        prompt_group = sub.add_mutually_exclusive_group(required=True)
        prompt_group.add_argument("--prompt-file", help="path to the prompt, or - for stdin")
        prompt_group.add_argument("--prompt", help="inline prompt; prefer --prompt-file")
        sub.add_argument("--out", required=True, help=".png path, never overwritten")
        sub.add_argument("--input", action="append", metavar="PATH",
                         help="input image; repeat for up to 3 (edit only)")
        sub.add_argument("--model", default=default_model, choices=list(MODELS),
                         metavar="MODEL", help=f"default: {default_model}")
        sub.add_argument("--size", metavar="W*H",
                         help="omit to let the model pick from the prompt")
        sub.add_argument("--n", type=int, default=1, metavar="COUNT",
                         help="render COUNT variants as <out>-1, <out>-2, ...")
        sub.add_argument("--negative-prompt", metavar="TEXT",
                         help="what to keep out of the image (max 500 chars)")
        sub.add_argument("--seed", type=int, metavar="N", help="0-2147483647, for reproducibility")
        sub.add_argument("--no-prompt-extend", action="store_true",
                         help="skip the server-side prompt rewriter")
        sub.add_argument("--watermark", action="store_true",
                         help="stamp a visible 'Qwen-Image' watermark")
        sub.add_argument("--log", help="JSONL log path (default: <repo root>/.qwenimage.jsonl)")
        sub.add_argument("--timeout", type=int, default=300, metavar="SECONDS")
        sub.add_argument("--retries", type=int, default=4, metavar="COUNT",
                         help="retries on rate limiting, with backoff")

    args = parser.parse_args(argv)
    if args.negative_prompt and len(args.negative_prompt) > 500:
        parser.error("--negative-prompt is capped at 500 characters")
    if args.seed is not None and not 0 <= args.seed <= 2147483647:
        parser.error("--seed must be between 0 and 2147483647")
    if args.command == "generate" and args.input:
        parser.error("generate takes no --input; use the edit command")
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
