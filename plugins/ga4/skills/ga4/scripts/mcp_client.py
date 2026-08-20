#!/usr/bin/env python3
"""Fallback for driving analytics-mcp directly over stdio JSON-RPC.

Use this only when the plugin's MCP tools aren't in the current session's
tool list — MCP servers load once at session start, so a plugin installed
mid-session (or a subagent spawned from a session that predates the
install) won't see them until a fresh session starts. If the registered
tools work, use those instead; this is a workaround, not the primary path.

Usage:
  mcp_client.py <tool_name> '<json_args>'
  mcp_client.py get_account_summaries '{}'
  mcp_client.py run_report '{"property_id": 549905304, "date_ranges": [{"start_date": "30daysAgo", "end_date": "today"}], "dimensions": ["date"], "metrics": ["activeUsers"]}'

Reads GA_SERVICE_ACCOUNT_KEY / GA_PROJECT_ID from the environment, the same
vars the plugin's .mcp.json remaps into GOOGLE_APPLICATION_CREDENTIALS /
GOOGLE_PROJECT_ID for the real server process. The key path is expanded here
before being handed over: analytics-mcp runs as its own process and never
expands a leading ~, unlike gtm.py/gsc.py/ga4_admin.py which call
Path.expanduser() themselves. The registered MCP server in .mcp.json gets no
such help — its GA_SERVICE_ACCOUNT_KEY must already be an absolute path.

Exits non-zero on any failure, including a tool that failed while the
JSON-RPC call itself succeeded — see is_tool_failure below for why that is
not one check but two.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def call(tool, args):
    env = dict(os.environ)
    # An exported-but-empty var is as unusable as an absent one, and fails far
    # deeper in with an error that names neither.
    missing = [v for v in ("GA_SERVICE_ACCOUNT_KEY", "GA_PROJECT_ID") if not env.get(v)]
    if missing:
        print(f"error: {' and '.join(missing)} not set — see SKILL.md Setup", file=sys.stderr)
        sys.exit(1)
    key_path = Path(env["GA_SERVICE_ACCOUNT_KEY"]).expanduser()
    if not key_path.is_file():
        print(f"error: GA_SERVICE_ACCOUNT_KEY points at a missing file: {key_path}", file=sys.stderr)
        sys.exit(1)
    env["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)
    env["GOOGLE_PROJECT_ID"] = env["GA_PROJECT_ID"]
    proc = subprocess.Popen(
        ["pipx", "run", "analytics-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def read(want_id):
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") == want_id:
                return msg
        return None

    # stdin must stay open until the response is read: analytics-mcp exits on
    # stdin EOF before a tools/call reply completes its network round trip,
    # which reads as a silent hang rather than an error if closed too early.
    send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ga4-skill-fallback", "version": "1"},
            },
        }
    )
    read(1)
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
    )
    resp = read(2)

    proc.stdin.close()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return resp, proc.stderr.read()


def is_tool_failure(text):
    """Whether a successful JSON-RPC reply is really carrying a failed tool.

    analytics-mcp reports its own failures two different ways. A schema
    violation is caught by the MCP framework and comes back with
    isError: true. Anything raised inside the tool — a missing credentials
    file, an unknown tool name — is swallowed and returned as ordinary text
    content with **isError: false**, the body being {"error": "..."}. Checking
    isError alone therefore misses every auth failure, which is the one most
    likely to happen on a fresh machine.

    Matching is kept deliberately narrow — a dict of exactly one "error" key
    holding a string — so a real report that happens to contain an "error"
    field is never mistaken for a failure.
    """
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(parsed, dict)
        and list(parsed) == ["error"]
        and isinstance(parsed["error"], str)
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <tool_name> '<json_args>'", file=sys.stderr)
        sys.exit(1)

    tool_name, tool_args = sys.argv[1], json.loads(sys.argv[2])
    response, server_stderr = call(tool_name, tool_args)

    if response is None:
        print("error: no response from analytics-mcp", file=sys.stderr)
        if server_stderr.strip():
            print(server_stderr.strip(), file=sys.stderr)
        sys.exit(1)
    if "error" in response:
        print(json.dumps(response["error"], indent=2), file=sys.stderr)
        sys.exit(1)

    result = response["result"]
    texts = [item.get("text", json.dumps(item)) for item in result.get("content", [])]
    failed = result.get("isError") or any(is_tool_failure(text) for text in texts)
    stream = sys.stderr if failed else sys.stdout
    for text in texts:
        print(text, file=stream)
    sys.exit(1 if failed else 0)
