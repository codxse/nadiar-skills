#!/usr/bin/env python3
"""Guardrailed passthrough to Meta's ads-cli (`meta`, PyPI: meta-ads).

Adds the four things the bare CLI does not give an agent:

1. One namespaced credential (META_ADS_ACCESS_TOKEN) instead of the CLI's
   generic ACCESS_TOKEN, and a child environment scrubbed of the generic
   names so an ambient value or a stray .env can never decide which account
   a write lands on.
2. An explicit --ad-account-id on every account-scoped command.
3. `check`, which verifies the token against the live API — unlike
   `meta auth status`, which reports "Authenticated" for any non-empty string.
4. An append-only audit line for every mutating invocation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

AUDIT_FILENAME = ".meta-ads-audit.jsonl"
TOKEN_ENV = "META_ADS_ACCESS_TOKEN"
SCRUBBED_ENV = ("ACCESS_TOKEN", "AD_ACCOUNT_ID", "BUSINESS_ID")
MUTATING_VERBS = frozenset(
    {"create", "update", "delete", "connect", "disconnect", "assign-user"}
)
ACCOUNT_EXEMPT_GROUPS = frozenset({"adaccount", "page"})
LEAF_ACCOUNT_COMMANDS = (("dataset", "connect"), ("dataset", "disconnect"))
HELP_FLAGS = frozenset({"-h", "--help", "--version"})
OUTPUT_TAIL_CHARS = 2000


def fail(message: str, code: int = 2) -> None:
    print(f"meta_ads.py: {message}", file=sys.stderr)
    raise SystemExit(code)


def resolve_cli() -> list[str]:
    override = os.environ.get("META_ADS_CLI")
    if override:
        return override.split()
    on_path = shutil.which("meta")
    if on_path:
        return [on_path]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", "meta-ads", "meta"]
    fail(
        "no ads-cli found. Install uv (so `uvx --from meta-ads meta` works), "
        "or `pip install meta-ads`, or set META_ADS_CLI to the command."
    )
    raise AssertionError("unreachable")


def read_token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        fail(
            f"{TOKEN_ENV} is not set. Export the Meta system user access token "
            f"under that name (see reference/setup.md). The CLI's own generic "
            f"ACCESS_TOKEN is deliberately not read."
        )
    return token


def child_env(token: str, ad_account_id: str | None, business_id: str | None) -> dict[str, str]:
    """Every scrubbed name is set explicitly, empty when unused.

    An absent variable lets a .env anywhere up the tree supply the value; an
    empty one does not (the CLI reads a real environment variable in
    preference to .env, and treats empty as unset).
    """
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
    env["ACCESS_TOKEN"] = token
    env["AD_ACCOUNT_ID"] = ad_account_id or ""
    env["BUSINESS_ID"] = business_id or ""
    return env


def positionals(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


def is_mutating(args: list[str]) -> bool:
    return bool(MUTATING_VERBS & set(positionals(args)))


def pop_flag(args: list[str], flag: str) -> tuple[str | None, list[str]]:
    """Take a flag out of argv and return its value.

    The CLI's own --ad-account-id/--business-id are options of the `ads`
    *group*, legal only immediately after `ads`, and `dataset connect` reuses
    the name --ad-account-id for a different meaning at leaf level. So this
    wrapper owns the distinct names --account/--business, strips them here, and
    hands the values to the child through the environment the CLI documents for
    them — position-independent, and the CLI's own flags pass through untouched.
    """
    value: str | None = None
    remaining: list[str] = []
    skip = False
    for i, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg == flag and i + 1 < len(args):
            value = args[i + 1]
            skip = True
            continue
        if arg.startswith(f"{flag}="):
            value = arg.split("=", 1)[1]
            continue
        remaining.append(arg)
    return value, remaining


def needs_ad_account(args: list[str]) -> bool:
    words = positionals(args)
    if not words or words[0] != "ads":
        return False
    if HELP_FLAGS & set(args):
        return False
    if len(words) < 2:
        return False
    return words[1] not in ACCOUNT_EXEMPT_GROUPS


def stray_dotenv() -> Path | None:
    for directory in [Path.cwd(), *Path.cwd().parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
            if any(
                line.strip().startswith(name + "=")
                for line in text.splitlines()
                for name in SCRUBBED_ENV
            ):
                return candidate
    return None


def audit_path() -> Path:
    for directory in [Path.cwd(), *Path.cwd().parents]:
        if (directory / ".git").exists():
            return directory / AUDIT_FILENAME
    return Path.cwd() / AUDIT_FILENAME


def redact(args: list[str], token: str) -> list[str]:
    return ["***" if token and token in arg else arg for arg in args]


def write_audit(record: dict) -> None:
    path = audit_path()
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"meta_ads.py: could not write {path}: {error}", file=sys.stderr)


def run_check(cli: list[str], token: str, ad_account_id: str | None) -> int:
    command = cli + ["-o", "json", "ads", "adaccount", "list"]
    result = subprocess.run(
        command,
        env=child_env(token, ad_account_id, None),
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    if result.returncode != 0 or "Error:" in combined or "Not authenticated" in combined:
        print(combined.strip(), file=sys.stderr)
        print(
            f"meta_ads.py: {TOKEN_ENV} did not authenticate against the live API.",
            file=sys.stderr,
        )
        return result.returncode or 1
    print(combined.strip())
    if ad_account_id and ad_account_id not in combined:
        print(
            f"meta_ads.py: token is valid but {ad_account_id} is not among the "
            f"accounts it can reach — assign that ad account to the system user.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    if not args:
        fail("nothing to run. Try `meta_ads.py --account act_123 ads campaign list`.")

    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    cli = resolve_cli()

    ad_account_id, args = pop_flag(args, "--account")
    business_id, args = pop_flag(args, "--business")

    words = positionals(args)
    if words and words[0] == "check":
        return run_check(cli, read_token(), ad_account_id)

    if HELP_FLAGS & set(args):
        return subprocess.run(cli + args, env=os.environ.copy()).returncode

    token = read_token()

    misplaced = "--ad-account-id" in args and tuple(words[1:3]) not in LEAF_ACCOUNT_COMMANDS
    if misplaced:
        fail(
            "use this wrapper's --account act_... instead of --ad-account-id. "
            "The CLI accepts --ad-account-id only right after `ads`, and only "
            "`dataset connect`/`dataset disconnect` take it as a leaf option."
        )
    if "--business-id" in args:
        fail("use this wrapper's --business <id> instead of --business-id.")

    if needs_ad_account(args) and not ad_account_id:
        fail(
            "--account act_... is required on every account-scoped command. "
            "Pass it explicitly; it is never read from the environment."
        )

    leaked = stray_dotenv()
    if leaked:
        print(
            f"meta_ads.py: ignoring credentials in {leaked} — the child process "
            f"sees only {TOKEN_ENV} and the --ad-account-id you passed.",
            file=sys.stderr,
        )

    command = cli + args
    mutating = is_mutating(args)

    if dry_run:
        print(json.dumps(
            {
                "command": redact(command, token),
                "ad_account_id": ad_account_id,
                "business_id": business_id,
                "write": mutating,
                "audit_log": str(audit_path()) if mutating else None,
            },
            indent=2,
        ))
        return 0

    result = subprocess.run(command, env=child_env(token, ad_account_id, business_id))

    if mutating:
        write_audit(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "argv": redact(args, token),
                "ad_account_id": ad_account_id,
                "business_id": business_id,
                "exit_code": result.returncode,
                "cwd": str(Path.cwd()),
            }
        )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
