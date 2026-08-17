#!/usr/bin/env python3
"""Read Google Search Console data and manage sitemaps via the Search Console API v1.

Auth reuses GTM_SERVICE_ACCOUNT_KEY (same service account as the gtm skill).
google-auth signs the JWT-bearer assertion (RS256 needs real crypto, stdlib
has none); everything else — the token exchange and every Search Console API
call — goes over stdlib urllib.
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

ROOT = "https://searchconsole.googleapis.com/"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]


class Failure(Exception):
    pass


# --- auth -----------------------------------------------------------------

def access_token():
    key_path = os.environ.get("GTM_SERVICE_ACCOUNT_KEY")
    if not key_path:
        raise Failure(
            "GTM_SERVICE_ACCOUNT_KEY is not set.\n"
            "  This skill reuses the same service account key as the gtm skill.\n"
            "  Point it at the service account JSON key from Google Cloud Console\n"
            "  (IAM & Admin > Service Accounts), and make sure that same service\n"
            "  account is added as a user with Full permission inside Search\n"
            "  Console itself (Settings > Users and permissions) — a GCP-level\n"
            "  role alone grants nothing in Search Console.\n"
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
    url = ROOT + path
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
        raise Failure(f"could not reach the Search Console API: {error.reason}") from None


def describe_http_error(error):
    detail = error.read().decode(errors="replace")[:800]
    hints = {
        400: "check --dimensions/--filter/date values — the API rejects a malformed query shape with this code",
        401: "access token invalid or expired",
        403: "the service account lacks Search Console permission on this site — check Settings > Users and permissions in the Search Console UI, not GCP IAM",
        404: "the site URL is wrong, or the service account has no access to it — sc-domain:example.com and https://example.com/ are different properties, not interchangeable",
    }
    hint = hints.get(error.code, "")
    return f"HTTP {error.code} {error.reason}" + (f" — {hint}" if hint else "") + f"\n{detail}"


def print_json(payload):
    print(json.dumps(payload, indent=2))


# --- audit log for every mutating call (sitemap submit/delete) ------------

def log_path():
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / ".git").exists():
            return candidate / ".gsc-audit.jsonl"
    return Path.cwd() / ".gsc-audit.jsonl"


def record(entry):
    entry["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = log_path()
    try:
        with path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"warning: could not write audit log {path}: {error}", file=sys.stderr)


def site_path(site):
    return f"webmasters/v3/sites/{urllib.parse.quote(site, safe='')}"


# --- commands -----------------------------------------------------------

def cmd_sites_list(args):
    print_json(call("GET", "webmasters/v3/sites"))


def cmd_sites_get(args):
    print_json(call("GET", site_path(args.site)))


def cmd_sitemaps_list(args):
    query = {"sitemapIndex": args.sitemap_index} if args.sitemap_index else None
    print_json(call("GET", f"{site_path(args.site)}/sitemaps", query=query))


def cmd_sitemaps_get(args):
    feedpath = urllib.parse.quote(args.sitemap, safe="")
    print_json(call("GET", f"{site_path(args.site)}/sitemaps/{feedpath}"))


def cmd_sitemaps_submit(args):
    feedpath = urllib.parse.quote(args.sitemap, safe="")
    call("PUT", f"{site_path(args.site)}/sitemaps/{feedpath}")
    record({"resource": "sitemaps", "verb": "submit", "site": args.site, "sitemap": args.sitemap})
    print(f"submitted {args.sitemap}")


def cmd_sitemaps_delete(args):
    feedpath = urllib.parse.quote(args.sitemap, safe="")
    call("DELETE", f"{site_path(args.site)}/sitemaps/{feedpath}")
    record({"resource": "sitemaps", "verb": "delete", "site": args.site, "sitemap": args.sitemap})
    print(f"deleted {args.sitemap}")


def cmd_analytics_query(args):
    body = {
        "startDate": args.start,
        "endDate": args.end,
        "rowLimit": args.row_limit,
        "startRow": args.start_row,
    }
    if args.dimensions:
        body["dimensions"] = [d.strip().upper() for d in args.dimensions.split(",")]
    if args.search_type:
        body["type"] = args.search_type.upper()
    if args.data_state:
        body["dataState"] = args.data_state.upper()
    if args.filter:
        filters = []
        for raw in args.filter:
            parts = raw.split(":", 2)
            if len(parts) != 3:
                raise Failure(f"--filter must be DIMENSION:OPERATOR:EXPRESSION, got: {raw}")
            dimension, operator, expression = parts
            filters.append({"dimension": dimension.upper(), "operator": operator.upper(), "expression": expression})
        body["dimensionFilterGroups"] = [{"groupType": "AND", "filters": filters}]
    print_json(call("POST", f"{site_path(args.site)}/searchAnalytics/query", body=body))


def cmd_inspect_url(args):
    body = {"inspectionUrl": args.url, "siteUrl": args.site}
    if args.language_code:
        body["languageCode"] = args.language_code
    print_json(call("POST", "v1/urlInspection/index:inspect", body=body))


# --- CLI wiring ---------------------------------------------------------

# --site stays fixed across most calls in one session, so it falls back to
# GSC_SITE_URL instead of being retyped (or hardcoded) into every command.
# --sitemap/--url are per-call and always explicit — no env var makes sense
# for those.

def add_site(sub):
    default = os.environ.get("GSC_SITE_URL")
    help_text = f"Search Console site URL, e.g. sc-domain:example.com or https://example.com/ (default: $GSC_SITE_URL, currently {'set' if default else 'unset'})"
    sub.add_argument("--site", required=default is None, default=default, help=help_text)


def build_parser():
    parser = argparse.ArgumentParser(prog="gsc.py", description="Read Google Search Console data and manage sitemaps via the Search Console API v1.")
    resource = parser.add_subparsers(dest="resource", required=True)

    sites = resource.add_parser("sites").add_subparsers(dest="verb", required=True)
    sites.add_parser("list")
    add_site(sites.add_parser("get"))

    sitemaps = resource.add_parser("sitemaps").add_subparsers(dest="verb", required=True)
    list_parser = sitemaps.add_parser("list")
    add_site(list_parser)
    list_parser.add_argument("--sitemap-index", help="filter to sitemaps inside this sitemap index")
    get_parser = sitemaps.add_parser("get")
    add_site(get_parser)
    get_parser.add_argument("--sitemap", required=True, help="full sitemap URL, e.g. https://example.com/sitemap.xml")
    submit_parser = sitemaps.add_parser("submit")
    add_site(submit_parser)
    submit_parser.add_argument("--sitemap", required=True)
    delete_parser = sitemaps.add_parser("delete")
    add_site(delete_parser)
    delete_parser.add_argument("--sitemap", required=True)

    analytics = resource.add_parser("analytics").add_subparsers(dest="verb", required=True)
    query_parser = analytics.add_parser("query")
    add_site(query_parser)
    query_parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    query_parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    query_parser.add_argument("--dimensions", help="comma-separated: query,page,date,country,device,searchAppearance,hour")
    query_parser.add_argument("--search-type", help="web|image|video|news|discover|googleNews (default: web)")
    query_parser.add_argument("--row-limit", type=int, default=1000)
    query_parser.add_argument("--start-row", type=int, default=0)
    query_parser.add_argument("--data-state", help="final|all (default: final; 'all' includes fresh/unfinalized data)")
    query_parser.add_argument(
        "--filter", action="append",
        help="DIMENSION:OPERATOR:EXPRESSION, repeatable, ANDed together. "
             "dimension: query|page|country|device|searchAppearance. "
             "operator: equals|notEquals|contains|notContains|includingRegex|excludingRegex",
    )

    inspect = resource.add_parser("inspect").add_subparsers(dest="verb", required=True)
    inspect_url = inspect.add_parser("url")
    add_site(inspect_url)
    inspect_url.add_argument("--url", required=True, help="full URL to inspect, must be under --site")
    inspect_url.add_argument("--language-code", help="IETF BCP-47 code, default en-US")

    return parser


DISPATCH = {
    ("sites", "list"): cmd_sites_list,
    ("sites", "get"): cmd_sites_get,
    ("sitemaps", "list"): cmd_sitemaps_list,
    ("sitemaps", "get"): cmd_sitemaps_get,
    ("sitemaps", "submit"): cmd_sitemaps_submit,
    ("sitemaps", "delete"): cmd_sitemaps_delete,
    ("analytics", "query"): cmd_analytics_query,
    ("inspect", "url"): cmd_inspect_url,
}


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
