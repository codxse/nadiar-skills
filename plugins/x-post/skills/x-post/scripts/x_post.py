#!/usr/bin/env python3
"""Post and read on X (Twitter) via API v2, OAuth 1.0a user context.

Stdlib only. OAuth 1.0a is HMAC-SHA1 (hmac/hashlib/base64), so no crypto
library is needed — unlike gtm/gsc/ga4's RS256 service-account JWT, which
does need google-auth. Every call goes over urllib.request.
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.twitter.com/2/"
TWEET_FIELDS = "created_at,public_metrics,lang"
USER_FIELDS = "public_metrics,description,created_at"

ERROR_HINTS = {
    401: "invalid or expired credentials — regenerate the Access Token in "
         "console.x.com (App > Keys & Tokens) and re-export it",
    403: "check two things in this order: (1) console.x.com > the app > "
         "'Project Access' — it must point at a project with an active paid "
         "plan (Free is deprecated; a Pay Per Use project with credit "
         "works), moving it there is required even if the app already "
         "shows 'a' project attached, since the old Free/Basic one still "
         "counts as attached and still 403s; (2) the app's 'User "
         "authentication settings' > App permissions must be 'Read and "
         "write', AND the Access Token must have been (re)generated *after* "
         "that was set — a token generated while permissions were Read-only "
         "stays read-only forever, regenerating it is the only fix",
    429: "rate limited — X API v2 free-tier-equivalent limits are tight "
         "(POST /2/tweets: 100 req/15min per user on Pay Per Use); wait and "
         "retry, don't loop",
}


class Failure(Exception):
    pass


# --- auth -------------------------------------------------------------

def credentials():
    names = ("X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise Failure(
            f"missing env var(s): {', '.join(missing)}\n"
            "  All four come from console.x.com > the app > Keys & Tokens.\n"
            "  On zsh, export them in ~/.zshenv, not ~/.zshrc — zsh only\n"
            "  reads .zshrc for interactive shells, invisible to an agent's\n"
            "  non-interactive shell."
        )
    return tuple(os.environ[n] for n in names)


def oauth1_header(method, url, params, api_key, api_secret, access_token, access_secret):
    """Sign a request per OAuth 1.0a. `params` are query-string params only —
    a JSON POST body is never part of the OAuth 1.0a signature base string."""
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }

    def pct(s):
        return urllib.parse.quote(str(s), safe="")

    all_params = {**oauth_params, **params}
    param_string = "&".join(f"{pct(k)}={pct(v)}" for k, v in sorted(all_params.items()))
    base_string = "&".join([method.upper(), pct(url), pct(param_string)])
    signing_key = f"{pct(api_secret)}&{pct(access_secret)}"

    signature = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(signature).decode()

    return "OAuth " + ", ".join(f'{pct(k)}="{pct(v)}"' for k, v in sorted(oauth_params.items()))


def request(method, path, query=None, body=None):
    query = query or {}
    api_key, api_secret, access_token, access_secret = credentials()
    url = API_BASE + path

    auth_header = oauth1_header(method, url, query, api_key, api_secret, access_token, access_secret)
    full_url = f"{url}?{urllib.parse.urlencode(query)}" if query else url

    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": auth_header}
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:800]
        hint = ERROR_HINTS.get(error.code, "")
        raise Failure(f"HTTP {error.code} {error.reason}" + (f" — {hint}" if hint else "") + f"\n{detail}") from None


def print_json(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False))


# --- audit log for every mutating call ---------------------------------

def log_path():
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / ".git").exists():
            return candidate / ".x-audit.jsonl"
    return Path.cwd() / ".x-audit.jsonl"


def record(entry):
    full_entry = {**entry, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = log_path()
    try:
        with path.open("a") as handle:
            handle.write(json.dumps(full_entry, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"warning: could not write audit log {path}: {error}", file=sys.stderr)


# --- commands ------------------------------------------------------------

def read_text(args):
    # --text/--text-file is a required mutually exclusive group, so argparse
    # itself guarantees exactly one is set — no need to check for neither.
    return Path(args.text_file).read_text() if args.text_file else args.text


def cmd_tweets_post(args):
    text = read_text(args)
    result = request("POST", "tweets", body={"text": text})
    record({"action": "post", "id": result.get("data", {}).get("id"), "text": text})
    print_json(result)


def cmd_tweets_get(args):
    print_json(request("GET", f"tweets/{args.id}", query={
        "tweet.fields": TWEET_FIELDS + ",author_id",
    }))


def cmd_tweets_delete(args):
    result = request("DELETE", f"tweets/{args.id}")
    record({"action": "delete", "id": args.id})
    print_json(result)


def cmd_users_me(args):
    print_json(request("GET", "users/me", query={"user.fields": USER_FIELDS}))


def cmd_users_get(args):
    print_json(request("GET", f"users/by/username/{args.username}", query={"user.fields": USER_FIELDS}))


def cmd_users_tweets(args):
    user = request("GET", f"users/by/username/{args.username}")
    user_id = user["data"]["id"]
    query = {
        "max_results": str(min(max(args.count, 5), 100)),
        "tweet.fields": TWEET_FIELDS,
        "exclude": "retweets" if args.include_replies else "retweets,replies",
    }
    print_json(request("GET", f"users/{user_id}/tweets", query=query))


DISPATCH = {
    ("tweets", "post"): cmd_tweets_post,
    ("tweets", "get"): cmd_tweets_get,
    ("tweets", "delete"): cmd_tweets_delete,
    ("users", "me"): cmd_users_me,
    ("users", "get"): cmd_users_get,
    ("users", "tweets"): cmd_users_tweets,
}


def build_parser():
    parser = argparse.ArgumentParser(prog="x_post.py", description="Post and read on X via API v2.")
    resource = parser.add_subparsers(dest="resource", required=True)

    tweets = resource.add_parser("tweets").add_subparsers(dest="verb", required=True)

    post = tweets.add_parser("post")
    group = post.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--text-file")

    get = tweets.add_parser("get")
    get.add_argument("--id", required=True)

    delete = tweets.add_parser("delete")
    delete.add_argument("--id", required=True)

    users = resource.add_parser("users").add_subparsers(dest="verb", required=True)
    users.add_parser("me")

    get_user = users.add_parser("get")
    get_user.add_argument("--username", required=True)

    user_tweets = users.add_parser("tweets")
    user_tweets.add_argument("--username", required=True)
    user_tweets.add_argument("--count", type=int, default=20)
    user_tweets.add_argument("--include-replies", action="store_true")

    return parser


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
