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
GOOGLE_PROJECT_ID for the real server process.
"""
import json
import os
import subprocess
import sys


def call(tool, args):
    env = dict(os.environ)
    missing = [v for v in ("GA_SERVICE_ACCOUNT_KEY", "GA_PROJECT_ID") if v not in env]
    if missing:
        print(f"error: {' and '.join(missing)} not set — see SKILL.md Setup", file=sys.stderr)
        sys.exit(1)
    env["GOOGLE_APPLICATION_CREDENTIALS"] = env["GA_SERVICE_ACCOUNT_KEY"]
    env["GOOGLE_PROJECT_ID"] = env["GA_PROJECT_ID"]
    proc = subprocess.Popen(
        ["pipx", "run", "analytics-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
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
    proc.wait(timeout=30)
    return resp


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <tool_name> '<json_args>'", file=sys.stderr)
        sys.exit(1)

    tool_name, tool_args = sys.argv[1], json.loads(sys.argv[2])
    response = call(tool_name, tool_args)

    if response is None:
        print("error: no response", file=sys.stderr)
        sys.exit(1)
    if "error" in response:
        print(json.dumps(response["error"], indent=2), file=sys.stderr)
        sys.exit(1)
    for item in response["result"].get("content", []):
        print(item.get("text", json.dumps(item)))
