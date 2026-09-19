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
import mimetypes
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.twitter.com/2/"
MEDIA_UPLOAD_URL = "https://api.x.com/2/media/upload"
TWEET_FIELDS = "created_at,public_metrics,lang"
USER_FIELDS = "public_metrics,description,created_at"

TWEET_LIMIT = 280
URL_WEIGHT = 23
URL_PATTERN = re.compile(r"https?://\S+")

# X counts every URL as 23 characters regardless of its real length. It also
# counts CJK and emoji as 2, which this deliberately does not model — the
# check exists to catch a thread that would fail halfway through, and a
# Latin-script tweet is the case that matters here.
def weighted_length(text):
    return len(URL_PATTERN.sub("x" * URL_WEIGHT, text))

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


# --- media ---------------------------------------------------------------

def multipart_body(fields, file_field, filename, content_type, blob):
    """Assemble a multipart/form-data body. Returns (content_type, bytes).

    Like a JSON body, a multipart body is not part of the OAuth 1.0a
    signature base string, so the existing header signing applies unchanged.
    """
    boundary = uuid.uuid4().hex
    marker = f"--{boundary}".encode()
    parts = []

    for name, value in fields.items():
        parts += [
            marker,
            f'Content-Disposition: form-data; name="{name}"'.encode(),
            b"",
            str(value).encode(),
        ]

    parts += [
        marker,
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode(),
        f"Content-Type: {content_type}".encode(),
        b"",
        blob,
        f"--{boundary}--".encode(),
        b"",
    ]

    return f"multipart/form-data; boundary={boundary}", b"\r\n".join(parts)


def upload_media(path):
    """Upload one image and return its media id, via POST /2/media/upload."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise Failure(f"media file not found: {source}")

    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise Failure(f"{source.name} is {content_type}; only images are supported here")

    api_key, api_secret, access_token, access_secret = credentials()
    auth_header = oauth1_header("POST", MEDIA_UPLOAD_URL, {}, api_key, api_secret, access_token, access_secret)

    body_type, body = multipart_body(
        {"media_category": "tweet_image", "media_type": content_type},
        "media",
        source.name,
        content_type,
        source.read_bytes(),
    )

    req = urllib.request.Request(
        MEDIA_UPLOAD_URL,
        data=body,
        headers={"Authorization": auth_header, "Content-Type": body_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:800]
        hint = ERROR_HINTS.get(error.code, "")
        raise Failure(f"HTTP {error.code} {error.reason} uploading {source.name}"
                      + (f" — {hint}" if hint else "") + f"\n{detail}") from None

    media_id = result.get("data", {}).get("id") or result.get("id")
    if not media_id:
        raise Failure(f"upload succeeded but no media id in response:\n{json.dumps(result)}")
    return media_id


def post_tweet(text, media_paths=None, reply_to=None):
    body = {"text": text}
    if media_paths:
        body["media"] = {"media_ids": [upload_media(path) for path in media_paths]}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": reply_to}
    return request("POST", "tweets", body=body)


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


def check_length(text, label):
    length = weighted_length(text)
    if length > TWEET_LIMIT:
        raise Failure(f"{label} is {length} characters, over the {TWEET_LIMIT} limit "
                      "(every URL counts as 23) — trim it before posting")
    return length


def cmd_tweets_post(args):
    text = read_text(args)
    check_length(text, "tweet")
    result = post_tweet(text, args.media, args.reply_to)
    record({"action": "post", "id": result.get("data", {}).get("id"), "text": text,
            "media": args.media or [], "reply_to": args.reply_to})
    print_json(result)


def cmd_media_upload(args):
    print_json({"media_id": upload_media(args.file)})


# --- threads -------------------------------------------------------------

def load_thread(path):
    """Read a thread file: a JSON list of {"text": ..., "media": [paths]}."""
    try:
        entries = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise Failure(f"could not read thread file {path}: {error}") from None

    if not isinstance(entries, list) or not entries:
        raise Failure("thread file must be a non-empty JSON list of objects")

    tweets = []
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("text"), str):
            raise Failure(f'tweet {index}: each entry must be an object with a "text" string')
        media = entry.get("media", [])
        if not isinstance(media, list) or any(not isinstance(m, str) for m in media):
            raise Failure(f'tweet {index}: "media" must be a list of file paths')
        if len(media) > 4:
            raise Failure(f"tweet {index}: X accepts at most 4 images per tweet")
        tweets.append({"text": entry["text"], "media": media})
    return tweets


def validate_thread(tweets):
    """Check every tweet and every media file before posting anything — a
    thread that fails on tweet 3 leaves two orphans on the timeline."""
    for index, tweet in enumerate(tweets, 1):
        length = check_length(tweet["text"], f"tweet {index}")
        for path in tweet["media"]:
            if not Path(path).expanduser().is_file():
                raise Failure(f"tweet {index}: media file not found: {path}")
        yield index, length


def cmd_tweets_thread(args):
    if args.min_delay > args.max_delay:
        raise Failure("--min-delay cannot be greater than --max-delay")

    tweets = load_thread(args.file)
    plan = list(validate_thread(tweets))

    if args.dry_run:
        for index, length in plan:
            media = tweets[index - 1]["media"]
            suffix = f", {len(media)} image(s)" if media else ""
            print(f"[{index}/{len(tweets)}] {length} chars{suffix}")
        print(f"delay between tweets: random {args.min_delay}-{args.max_delay}s")
        return

    posted = []
    reply_to = args.reply_to
    try:
        for index, tweet in enumerate(tweets, 1):
            if index > 1:
                pause = random.uniform(args.min_delay, args.max_delay)
                print(f"waiting {pause:.0f}s before tweet {index}/{len(tweets)}", file=sys.stderr)
                time.sleep(pause)

            result = post_tweet(tweet["text"], tweet["media"], reply_to)
            reply_to = result.get("data", {}).get("id")
            posted.append(reply_to)
            record({"action": "post", "id": reply_to, "text": tweet["text"],
                    "media": tweet["media"], "reply_to": None if index == 1 else posted[-2],
                    "thread": f"{index}/{len(tweets)}"})
            print(f"posted {index}/{len(tweets)}: {reply_to}", file=sys.stderr)
    except Failure as error:
        if posted:
            remaining = json.dumps(tweets[len(posted):], ensure_ascii=False, indent=2)
            raise Failure(
                f"{error}\n\n"
                f"posted so far: {', '.join(posted)}\n"
                f"to resume, put the remaining tweets in a file and run:\n"
                f"  x_post.py tweets thread --file REST.json --reply-to {posted[-1]}\n"
                f"remaining:\n{remaining}"
            ) from None
        raise

    print_json({"thread": posted})


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
    ("tweets", "thread"): cmd_tweets_thread,
    ("tweets", "get"): cmd_tweets_get,
    ("tweets", "delete"): cmd_tweets_delete,
    ("media", "upload"): cmd_media_upload,
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
    post.add_argument("--media", nargs="+", metavar="FILE",
                      help="up to 4 image files to attach, in display order")
    post.add_argument("--reply-to", metavar="ID",
                      help="post as a reply to this tweet id")

    thread = tweets.add_parser("thread")
    thread.add_argument("--file", required=True,
                        help='JSON list of {"text": ..., "media": [paths]}')
    thread.add_argument("--min-delay", type=float, default=60,
                        help="minimum seconds between tweets (default 60)")
    thread.add_argument("--max-delay", type=float, default=300,
                        help="maximum seconds between tweets (default 300)")
    thread.add_argument("--reply-to", metavar="ID",
                        help="hang the thread off an existing tweet, e.g. to resume")
    thread.add_argument("--dry-run", action="store_true",
                        help="validate lengths and media paths, post nothing")

    get = tweets.add_parser("get")
    get.add_argument("--id", required=True)

    delete = tweets.add_parser("delete")
    delete.add_argument("--id", required=True)

    media = resource.add_parser("media").add_subparsers(dest="verb", required=True)
    media_upload = media.add_parser("upload")
    media_upload.add_argument("--file", required=True)

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
