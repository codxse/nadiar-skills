#!/usr/bin/env python3
"""Read and write Google Tag Manager configuration via the Tag Manager API v2.

Auth is a service account JSON key (GTM_SERVICE_ACCOUNT_KEY). google-auth
signs the JWT-bearer assertion (RS256 needs real crypto, stdlib has none);
everything else — the token exchange and every Tag Manager API call — goes
over stdlib urllib, so no image/JSON payload ever needs a second dependency.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
]
ENTITY_KINDS = ("tags", "triggers", "variables")


class Failure(Exception):
    pass


# --- auth -----------------------------------------------------------------

def access_token():
    key_path = os.environ.get("GTM_SERVICE_ACCOUNT_KEY")
    if not key_path:
        raise Failure(
            "GTM_SERVICE_ACCOUNT_KEY is not set.\n"
            "  Point it at the service account JSON key from Google Cloud\n"
            "  Console (IAM & Admin > Service Accounts), and make sure that\n"
            "  same service account is added as a user with Publish permission\n"
            "  inside the GTM container itself (tagmanager.google.com > Admin >\n"
            "  User Management) — a GCP-level role alone grants nothing in GTM.\n"
            "  On zsh, export it in ~/.zshenv, not ~/.zshrc — zsh only reads\n"
            "  .zshrc for interactive shells, invisible to an agent's commands."
        )
    path = Path(key_path).expanduser()
    if not path.is_file():
        raise Failure(f"GTM_SERVICE_ACCOUNT_KEY points at a missing file: {path}")
    try:
        from google.auth import crypt, jwt
    except ImportError:
        raise Failure("google-auth is not installed. Install it once with:\n  pip install google-auth") from None

    info = json.loads(path.read_text())
    signer = crypt.RSASigner.from_service_account_info(info)
    now = int(time.time())
    assertion = jwt.encode(signer, {
        "iss": info["client_email"],
        "scope": " ".join(SCOPES),
        "aud": TOKEN_ENDPOINT,
        "iat": now,
        "exp": now + 3600,
    }).decode()

    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    request = urllib.request.Request(TOKEN_ENDPOINT, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["access_token"]
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise Failure(f"token exchange failed: HTTP {error.code}\n{detail}") from None


# --- REST call --------------------------------------------------------------

def call(method, path, *, query=None, body=None):
    url = API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raise Failure(describe_http_error(error)) from None
    except urllib.error.URLError as error:
        raise Failure(f"could not reach the Tag Manager API: {error.reason}") from None


def describe_http_error(error):
    detail = error.read().decode(errors="replace")[:800]
    hints = {
        401: "access token invalid or expired",
        403: "the service account lacks GTM permission on this container/account — check User Management in the GTM UI",
        404: "account/container/workspace/entity ID is wrong, or the service account has no access to it — 403 and 404 look the same for a resource you have zero access to, GTM doesn't leak existence",
        409: "fingerprint mismatch — the entity changed since you last read it; get it again before updating",
    }
    hint = hints.get(error.code, "")
    return f"HTTP {error.code} {error.reason}" + (f" — {hint}" if hint else "") + f"\n{detail}"


def read_body(path):
    file = Path(path)
    if not file.is_file():
        raise Failure(f"body file not found: {file}")
    try:
        return json.loads(file.read_text())
    except json.JSONDecodeError as error:
        raise Failure(f"{file} is not valid JSON: {error}") from None


def print_json(payload):
    print(json.dumps(payload, indent=2))


# --- audit log for every mutating call ---------------------------------

def log_path():
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / ".git").exists():
            return candidate / ".gtm-audit.jsonl"
    return Path.cwd() / ".gtm-audit.jsonl"


def record(entry):
    entry["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = log_path()
    try:
        with path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"warning: could not write audit log {path}: {error}", file=sys.stderr)


# --- path builders ----------------------------------------------------------

def account_path(a):
    return f"accounts/{a}"


def container_path(a, c):
    return f"{account_path(a)}/containers/{c}"


def workspace_path(a, c, w):
    return f"{container_path(a, c)}/workspaces/{w}"


def entity_path(a, c, w, kind, entity_id):
    return f"{workspace_path(a, c, w)}/{kind}/{entity_id}"


def version_path(a, c, v):
    return f"{container_path(a, c)}/versions/{v}"


# --- commands -----------------------------------------------------------

def cmd_accounts_list(args):
    print_json(call("GET", "accounts"))


def cmd_containers_list(args):
    print_json(call("GET", f"{account_path(args.account)}/containers"))


def cmd_containers_get(args):
    print_json(call("GET", container_path(args.account, args.container)))


def cmd_workspaces_list(args):
    print_json(call("GET", f"{container_path(args.account, args.container)}/workspaces"))


def cmd_workspaces_get(args):
    print_json(call("GET", workspace_path(args.account, args.container, args.workspace)))


def cmd_workspaces_status(args):
    print_json(call("GET", f"{workspace_path(args.account, args.container, args.workspace)}/status"))


def entity_handlers(kind):
    singular = kind[:-1]

    def list_(args):
        print_json(call("GET", f"{workspace_path(args.account, args.container, args.workspace)}/{kind}"))

    def get(args):
        entity_id = getattr(args, singular)
        print_json(call("GET", entity_path(args.account, args.container, args.workspace, kind, entity_id)))

    def create(args):
        body = read_body(args.body_file)
        result = call("POST", f"{workspace_path(args.account, args.container, args.workspace)}/{kind}", body=body)
        record({
            "resource": kind, "verb": "create",
            "account": args.account, "container": args.container, "workspace": args.workspace,
            "id": result.get(f"{singular}Id"), "name": body.get("name"), "type": body.get("type"),
        })
        print_json(result)

    def update(args):
        entity_id = getattr(args, singular)
        body = read_body(args.body_file)
        query = {"fingerprint": args.fingerprint} if args.fingerprint else None
        result = call("PUT", entity_path(args.account, args.container, args.workspace, kind, entity_id), query=query, body=body)
        record({
            "resource": kind, "verb": "update",
            "account": args.account, "container": args.container, "workspace": args.workspace,
            "id": entity_id, "name": body.get("name"), "type": body.get("type"),
        })
        print_json(result)

    def delete(args):
        entity_id = getattr(args, singular)
        call("DELETE", entity_path(args.account, args.container, args.workspace, kind, entity_id))
        record({
            "resource": kind, "verb": "delete",
            "account": args.account, "container": args.container, "workspace": args.workspace,
            "id": entity_id,
        })
        print(f"deleted {singular} {entity_id}")

    return {"list": list_, "get": get, "create": create, "update": update, "delete": delete}


def cmd_version_create(args):
    body = {"name": args.name}
    if args.notes:
        body["notes"] = args.notes
    result = call("POST", f"{workspace_path(args.account, args.container, args.workspace)}:create_version", body=body)
    version = (result.get("containerVersion") or {}).get("containerVersionId")
    record({
        "resource": "version", "verb": "create",
        "account": args.account, "container": args.container, "workspace": args.workspace,
        "id": version, "name": args.name, "notes": args.notes,
    })
    print_json(result)


def cmd_version_get(args):
    print_json(call("GET", version_path(args.account, args.container, args.version)))


def cmd_version_publish(args):
    query = {"fingerprint": args.fingerprint} if args.fingerprint else None
    result = call("POST", f"{version_path(args.account, args.container, args.version)}:publish", query=query)
    record({
        "resource": "version", "verb": "publish",
        "account": args.account, "container": args.container,
        "id": args.version,
    })
    print_json(result)


# --- CLI wiring ---------------------------------------------------------

# Every ID is named on the command line, every time. An account/container/
# workspace identifies one site, so it belongs to the task, not to the
# machine — a default carried in the environment would let `version publish`
# ship to whatever container happened to be exported, from any project, with
# nothing in the command naming the target. Only the service account key is
# read from the environment, because that is a property of this machine.


def add_ids(sub, *names):
    for name in names:
        sub.add_argument(f"--{name}", required=True, help=f"GTM {name} ID")


def build_parser():
    parser = argparse.ArgumentParser(prog="gtm.py", description="Read and write Google Tag Manager via API v2.")
    resource = parser.add_subparsers(dest="resource", required=True)

    accounts = resource.add_parser("accounts").add_subparsers(dest="verb", required=True)
    accounts.add_parser("list")

    containers = resource.add_parser("containers").add_subparsers(dest="verb", required=True)
    add_ids(containers.add_parser("list"), "account")
    add_ids(containers.add_parser("get"), "account", "container")

    workspaces = resource.add_parser("workspaces").add_subparsers(dest="verb", required=True)
    add_ids(workspaces.add_parser("list"), "account", "container")
    add_ids(workspaces.add_parser("get"), "account", "container", "workspace")
    add_ids(workspaces.add_parser("status"), "account", "container", "workspace")

    for kind in ENTITY_KINDS:
        singular = kind[:-1]
        verbs = resource.add_parser(kind).add_subparsers(dest="verb", required=True)
        add_ids(verbs.add_parser("list"), "account", "container", "workspace")
        add_ids(verbs.add_parser("get"), "account", "container", "workspace", singular)
        create = verbs.add_parser("create")
        add_ids(create, "account", "container", "workspace")
        create.add_argument("--body-file", required=True, help=f"JSON body for the {singular} (see reference/api.md)")
        update = verbs.add_parser("update")
        add_ids(update, "account", "container", "workspace", singular)
        update.add_argument("--body-file", required=True, help=f"JSON body for the {singular} (see reference/api.md)")
        update.add_argument("--fingerprint", help="optimistic-concurrency check; omit to skip it")
        add_ids(verbs.add_parser("delete"), "account", "container", "workspace", singular)

    version = resource.add_parser("version").add_subparsers(dest="verb", required=True)
    create_version = version.add_parser("create")
    add_ids(create_version, "account", "container", "workspace")
    create_version.add_argument("--name", required=True)
    create_version.add_argument("--notes")
    add_ids(version.add_parser("get"), "account", "container", "version")
    publish = version.add_parser("publish")
    add_ids(publish, "account", "container", "version")
    publish.add_argument("--fingerprint", help="optimistic-concurrency check; omit to skip it")

    return parser


DISPATCH = {
    ("accounts", "list"): cmd_accounts_list,
    ("containers", "list"): cmd_containers_list,
    ("containers", "get"): cmd_containers_get,
    ("workspaces", "list"): cmd_workspaces_list,
    ("workspaces", "get"): cmd_workspaces_get,
    ("workspaces", "status"): cmd_workspaces_status,
    ("version", "create"): cmd_version_create,
    ("version", "get"): cmd_version_get,
    ("version", "publish"): cmd_version_publish,
}
for _kind in ENTITY_KINDS:
    for _verb, _fn in entity_handlers(_kind).items():
        DISPATCH[(_kind, _verb)] = _fn


def main():
    args = build_parser().parse_args(sys.argv[1:])
    try:
        DISPATCH[(args.resource, args.verb)](args)
    except Failure as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
