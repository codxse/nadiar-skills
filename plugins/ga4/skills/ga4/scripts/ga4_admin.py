#!/usr/bin/env python3
"""Manage GA4 property configuration via the Analytics Admin API v1beta:
custom dimensions, custom metrics, key events, and data streams.

This is a separate concern from the ga4 skill's primary path — reporting
reads go through the bundled analytics-mcp MCP server (read-only by design,
requests only the analytics.readonly scope). This script exists because
analytics-mcp has no write tools at all; it calls the Admin API's write
methods directly.

Auth reuses GA_SERVICE_ACCOUNT_KEY (same service account as the rest of the
ga4 skill). google-auth signs the JWT-bearer assertion (RS256 needs real
crypto, stdlib has none); everything else goes over stdlib urllib.
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

ROOT = "https://analyticsadmin.googleapis.com/"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/analytics.edit"]

MEASUREMENT_UNITS = ["STANDARD", "CURRENCY", "FEET", "METERS", "KILOMETERS", "MILES", "MILLISECONDS", "SECONDS", "MINUTES", "HOURS"]
COUNTING_METHODS = ["ONCE_PER_EVENT", "ONCE_PER_SESSION"]


class Failure(Exception):
    pass


# --- auth -----------------------------------------------------------------

def access_token():
    key_path = os.environ.get("GA_SERVICE_ACCOUNT_KEY")
    if not key_path:
        raise Failure(
            "GA_SERVICE_ACCOUNT_KEY is not set.\n"
            "  Same service account key as the rest of the ga4 skill. Make sure\n"
            "  that service account is added inside the GA4 property itself\n"
            "  (Admin > Property Access Management) with Editor or above — Viewer\n"
            "  can't write, and a GCP IAM role alone grants nothing in GA4.\n"
            "  On zsh, export it in ~/.zshenv, not ~/.zshrc — zsh only reads\n"
            "  .zshrc for interactive shells, invisible to an agent's commands."
        )
    path = Path(key_path).expanduser()
    if not path.is_file():
        raise Failure(f"GA_SERVICE_ACCOUNT_KEY points at a missing file: {path}")
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
        raise Failure(f"could not reach the Analytics Admin API: {error.reason}") from None


def describe_http_error(error):
    detail = error.read().decode(errors="replace")[:800]
    hints = {
        400: "check the field names/enum values in the request — a bad --update-mask candidate also lands here",
        401: "access token invalid or expired",
        403: "the service account lacks edit access on this property — check Admin > Property Access Management (needs Editor or above), not GCP IAM",
        404: "the property or resource name is wrong, or the service account has no access to it",
        429: "the property has hit a quota (e.g. custom dimension/metric slots) — list existing ones before creating another",
    }
    hint = hints.get(error.code, "")
    return f"HTTP {error.code} {error.reason}" + (f" — {hint}" if hint else "") + f"\n{detail}"


def print_json(payload):
    print(json.dumps(payload, indent=2))


# --- audit log for every mutating call (create/patch/archive/delete) ------

def log_path():
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / ".git").exists():
            return candidate / ".ga4-audit.jsonl"
    return Path.cwd() / ".ga4-audit.jsonl"


def record(entry):
    entry["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = log_path()
    try:
        with path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError as error:
        print(f"warning: could not write audit log {path}: {error}", file=sys.stderr)


def property_path(property_id):
    text = str(property_id)
    return text if text.startswith("properties/") else f"properties/{text}"


def mask_and_body(fields):
    """fields: dict of {api_field_name: value_or_None}. Returns (updateMask, body)
    containing only the entries the caller actually set."""
    present = {k: v for k, v in fields.items() if v is not None}
    return ",".join(present.keys()), present


# --- dimensions (customDimensions) -----------------------------------------

def cmd_dimensions_list(args):
    print_json(call("GET", f"v1beta/{property_path(args.property)}/customDimensions"))


def cmd_dimensions_get(args):
    print_json(call("GET", f"v1beta/{args.name}"))


def cmd_dimensions_create(args):
    body = {"displayName": args.display_name, "parameterName": args.parameter_name, "scope": args.scope}
    if args.description:
        body["description"] = args.description
    if args.disallow_ads_personalization:
        body["disallowAdsPersonalization"] = True
    result = call("POST", f"v1beta/{property_path(args.property)}/customDimensions", body=body)
    record({"resource": "customDimensions", "verb": "create", "property": args.property, "body": body})
    print_json(result)


def cmd_dimensions_patch(args):
    if args.disallow_ads_personalization and args.allow_ads_personalization:
        raise Failure("pass at most one of --disallow-ads-personalization / --allow-ads-personalization")
    mask, body = mask_and_body({
        "displayName": args.display_name,
        "description": args.description,
        "disallowAdsPersonalization": True if args.disallow_ads_personalization else (False if args.allow_ads_personalization else None),
    })
    if not mask:
        raise Failure("nothing to patch — pass at least one of --display-name/--description/--disallow-ads-personalization/--allow-ads-personalization")
    result = call("PATCH", f"v1beta/{args.name}", query={"updateMask": mask}, body=body)
    record({"resource": "customDimensions", "verb": "patch", "name": args.name, "body": body})
    print_json(result)


def cmd_dimensions_archive(args):
    call("POST", f"v1beta/{args.name}:archive", body={})
    record({"resource": "customDimensions", "verb": "archive", "name": args.name})
    print(f"archived {args.name}")


# --- metrics (customMetrics) ------------------------------------------------

def cmd_metrics_list(args):
    print_json(call("GET", f"v1beta/{property_path(args.property)}/customMetrics"))


def cmd_metrics_get(args):
    print_json(call("GET", f"v1beta/{args.name}"))


def cmd_metrics_create(args):
    body = {
        "displayName": args.display_name,
        "parameterName": args.parameter_name,
        "scope": "EVENT",
        "measurementUnit": args.measurement_unit,
    }
    if args.description:
        body["description"] = args.description
    if args.restricted_metric_type:
        body["restrictedMetricType"] = args.restricted_metric_type
    result = call("POST", f"v1beta/{property_path(args.property)}/customMetrics", body=body)
    record({"resource": "customMetrics", "verb": "create", "property": args.property, "body": body})
    print_json(result)


def cmd_metrics_patch(args):
    mask, body = mask_and_body({
        "displayName": args.display_name,
        "description": args.description,
        "measurementUnit": args.measurement_unit,
    })
    if not mask:
        raise Failure("nothing to patch — pass at least one of --display-name/--description/--measurement-unit")
    result = call("PATCH", f"v1beta/{args.name}", query={"updateMask": mask}, body=body)
    record({"resource": "customMetrics", "verb": "patch", "name": args.name, "body": body})
    print_json(result)


def cmd_metrics_archive(args):
    call("POST", f"v1beta/{args.name}:archive", body={})
    record({"resource": "customMetrics", "verb": "archive", "name": args.name})
    print(f"archived {args.name}")


# --- events (keyEvents) -----------------------------------------------------
# Note: the Admin API's older conversionEvents resource is deprecated in
# Google's own docs in favor of keyEvents — this skill only ever uses
# keyEvents, deliberately.

def cmd_events_list(args):
    print_json(call("GET", f"v1beta/{property_path(args.property)}/keyEvents"))


def cmd_events_get(args):
    print_json(call("GET", f"v1beta/{args.name}"))


def default_value_from(args):
    if bool(args.currency_code) != (args.numeric_value is not None):
        raise Failure("--currency-code and --numeric-value must be given together, or not at all")
    if args.currency_code:
        return {"currencyCode": args.currency_code, "numericValue": args.numeric_value}
    return None


def cmd_events_create(args):
    body = {"eventName": args.event_name, "countingMethod": args.counting_method}
    default_value = default_value_from(args)
    if default_value:
        body["defaultValue"] = default_value
    result = call("POST", f"v1beta/{property_path(args.property)}/keyEvents", body=body)
    record({"resource": "keyEvents", "verb": "create", "property": args.property, "body": body})
    print_json(result)


def cmd_events_patch(args):
    default_value = default_value_from(args)
    mask, body = mask_and_body({
        "countingMethod": args.counting_method,
        "defaultValue": default_value,
    })
    if not mask:
        raise Failure("nothing to patch — pass --counting-method and/or both --currency-code and --numeric-value")
    result = call("PATCH", f"v1beta/{args.name}", query={"updateMask": mask}, body=body)
    record({"resource": "keyEvents", "verb": "patch", "name": args.name, "body": body})
    print_json(result)


def cmd_events_delete(args):
    call("DELETE", f"v1beta/{args.name}")
    record({"resource": "keyEvents", "verb": "delete", "name": args.name})
    print(f"deleted {args.name}")


# --- streams (dataStreams) --------------------------------------------------

def cmd_streams_list(args):
    print_json(call("GET", f"v1beta/{property_path(args.property)}/dataStreams"))


def cmd_streams_get(args):
    print_json(call("GET", f"v1beta/{args.name}"))


def cmd_streams_create(args):
    body = {"type": args.type}
    if args.display_name:
        body["displayName"] = args.display_name
    if args.type == "WEB_DATA_STREAM":
        web = {}
        if args.default_uri:
            web["defaultUri"] = args.default_uri
        if web:
            body["webStreamData"] = web
    elif args.type == "ANDROID_APP_DATA_STREAM":
        if not args.package_name:
            raise Failure("--package-name is required for --type ANDROID_APP_DATA_STREAM")
        body["androidAppStreamData"] = {"packageName": args.package_name}
    elif args.type == "IOS_APP_DATA_STREAM":
        if not args.bundle_id:
            raise Failure("--bundle-id is required for --type IOS_APP_DATA_STREAM")
        body["iosAppStreamData"] = {"bundleId": args.bundle_id}
    result = call("POST", f"v1beta/{property_path(args.property)}/dataStreams", body=body)
    record({"resource": "dataStreams", "verb": "create", "property": args.property, "body": body})
    print_json(result)


def cmd_streams_patch(args):
    mask, body = mask_and_body({"displayName": args.display_name})
    if args.default_uri:
        mask = (mask + "," if mask else "") + "webStreamData.defaultUri"
        body["webStreamData"] = {"defaultUri": args.default_uri}
    if not mask:
        raise Failure("nothing to patch — pass --display-name and/or --default-uri")
    result = call("PATCH", f"v1beta/{args.name}", query={"updateMask": mask}, body=body)
    record({"resource": "dataStreams", "verb": "patch", "name": args.name, "body": body})
    print_json(result)


def cmd_streams_delete(args):
    call("DELETE", f"v1beta/{args.name}")
    record({"resource": "dataStreams", "verb": "delete", "name": args.name})
    print(f"deleted {args.name}")


# --- CLI wiring --------------------------------------------------------

# --property is named on every call. A property identifies one site, so it
# belongs to the task, not to the machine — a default carried in the
# environment would let a create/patch/archive land on whatever property
# happened to be exported, from any project, with nothing in the command
# naming the target. Only the service account key is read from the
# environment, because that is a property of this machine. --name is
# per-resource and equally explicit — copy it straight from a `list`
# response rather than reconstructing it.

def add_property(sub):
    sub.add_argument("--property", required=True, help="GA4 property ID or 'properties/N'")


def add_name(sub, resource_hint):
    sub.add_argument("--name", required=True, help=f"full resource name, e.g. properties/P/{resource_hint}/ID — copy from a `list` response")


def build_parser():
    parser = argparse.ArgumentParser(prog="ga4_admin.py", description="Manage GA4 property configuration (custom dimensions/metrics, key events, data streams) via the Analytics Admin API v1beta.")
    resource = parser.add_subparsers(dest="resource", required=True)

    dims = resource.add_parser("dimensions").add_subparsers(dest="verb", required=True)
    add_property(dims.add_parser("list"))
    add_name(dims.add_parser("get"), "customDimensions")
    create = dims.add_parser("create")
    add_property(create)
    create.add_argument("--display-name", required=True)
    create.add_argument("--parameter-name", required=True, help="immutable tagging parameter name")
    create.add_argument("--scope", required=True, choices=["EVENT", "USER", "ITEM"])
    create.add_argument("--description")
    create.add_argument("--disallow-ads-personalization", action="store_true")
    patch = dims.add_parser("patch")
    add_name(patch, "customDimensions")
    patch.add_argument("--display-name")
    patch.add_argument("--description")
    patch.add_argument("--disallow-ads-personalization", action="store_true")
    patch.add_argument("--allow-ads-personalization", action="store_true")
    add_name(dims.add_parser("archive"), "customDimensions")

    mets = resource.add_parser("metrics").add_subparsers(dest="verb", required=True)
    add_property(mets.add_parser("list"))
    add_name(mets.add_parser("get"), "customMetrics")
    create = mets.add_parser("create")
    add_property(create)
    create.add_argument("--display-name", required=True)
    create.add_argument("--parameter-name", required=True, help="immutable tagging parameter name")
    create.add_argument("--measurement-unit", required=True, choices=MEASUREMENT_UNITS)
    create.add_argument("--description")
    create.add_argument("--restricted-metric-type", action="append", choices=["COST_DATA", "REVENUE_DATA"])
    patch = mets.add_parser("patch")
    add_name(patch, "customMetrics")
    patch.add_argument("--display-name")
    patch.add_argument("--description")
    patch.add_argument("--measurement-unit", choices=MEASUREMENT_UNITS)
    add_name(mets.add_parser("archive"), "customMetrics")

    events = resource.add_parser("events").add_subparsers(dest="verb", required=True)
    add_property(events.add_parser("list"))
    add_name(events.add_parser("get"), "keyEvents")
    create = events.add_parser("create")
    add_property(create)
    create.add_argument("--event-name", required=True, help="e.g. purchase, sign_up — the raw GA4 event name, not a display label")
    create.add_argument("--counting-method", default="ONCE_PER_EVENT", choices=COUNTING_METHODS)
    create.add_argument("--currency-code", help="ISO 4217, e.g. USD — pairs with --numeric-value")
    create.add_argument("--numeric-value", type=float)
    patch = events.add_parser("patch")
    add_name(patch, "keyEvents")
    patch.add_argument("--counting-method", choices=COUNTING_METHODS)
    patch.add_argument("--currency-code")
    patch.add_argument("--numeric-value", type=float)
    add_name(events.add_parser("delete"), "keyEvents")

    streams = resource.add_parser("streams").add_subparsers(dest="verb", required=True)
    add_property(streams.add_parser("list"))
    add_name(streams.add_parser("get"), "dataStreams")
    create = streams.add_parser("create")
    add_property(create)
    create.add_argument("--type", required=True, choices=["WEB_DATA_STREAM", "ANDROID_APP_DATA_STREAM", "IOS_APP_DATA_STREAM"])
    create.add_argument("--display-name")
    create.add_argument("--default-uri", help="web streams only")
    create.add_argument("--package-name", help="Android streams only")
    create.add_argument("--bundle-id", help="iOS streams only")
    patch = streams.add_parser("patch")
    add_name(patch, "dataStreams")
    patch.add_argument("--display-name")
    patch.add_argument("--default-uri")
    add_name(streams.add_parser("delete"), "dataStreams")

    return parser


DISPATCH = {
    ("dimensions", "list"): cmd_dimensions_list,
    ("dimensions", "get"): cmd_dimensions_get,
    ("dimensions", "create"): cmd_dimensions_create,
    ("dimensions", "patch"): cmd_dimensions_patch,
    ("dimensions", "archive"): cmd_dimensions_archive,
    ("metrics", "list"): cmd_metrics_list,
    ("metrics", "get"): cmd_metrics_get,
    ("metrics", "create"): cmd_metrics_create,
    ("metrics", "patch"): cmd_metrics_patch,
    ("metrics", "archive"): cmd_metrics_archive,
    ("events", "list"): cmd_events_list,
    ("events", "get"): cmd_events_get,
    ("events", "create"): cmd_events_create,
    ("events", "patch"): cmd_events_patch,
    ("events", "delete"): cmd_events_delete,
    ("streams", "list"): cmd_streams_list,
    ("streams", "get"): cmd_streams_get,
    ("streams", "create"): cmd_streams_create,
    ("streams", "patch"): cmd_streams_patch,
    ("streams", "delete"): cmd_streams_delete,
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
