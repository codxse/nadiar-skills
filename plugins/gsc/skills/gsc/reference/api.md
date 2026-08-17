# Search Console API v1 reference

Ground truth pulled from Google's live discovery document
(`https://www.googleapis.com/discovery/v1/apis/searchconsole/v1/rest`) and
verified against a real property (`sc-domain:goldypaper.com`), not from the
HTML docs — the discovery doc is what the API actually enforces, and even it
turned out to be stale in one place (see Mobile-Friendly Test below).

## Auth

Service-account JWT-bearer flow, no user consent screen — identical shape to
the `gtm` skill, reusing the same `GTM_SERVICE_ACCOUNT_KEY`:

1. Build a JWT: `iss` = service account email, `scope` =
   `https://www.googleapis.com/auth/webmasters`, `aud` =
   `https://oauth2.googleapis.com/token`, `iat`/`exp` (1 hour). Sign RS256
   with the private key from the JSON key file.
2. POST it to the token endpoint as
   `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=<jwt>`.
3. Use the returned `access_token` as `Authorization: Bearer <token>` on
   every Search Console API call.

Only one scope exists for this API (no separate read-only scope that still
allows sitemap writes) — `webmasters.readonly` exists but can't submit or
delete sitemaps, so this skill's "read + sitemap management" scope needs the
full `webmasters` scope regardless.

## Base URL and path shape

Two different path prefixes live under the same root,
`https://searchconsole.googleapis.com/`:

```
webmasters/v3/sites
webmasters/v3/sites/{siteUrl}
webmasters/v3/sites/{siteUrl}/sitemaps
webmasters/v3/sites/{siteUrl}/sitemaps/{feedpath}
webmasters/v3/sites/{siteUrl}/searchAnalytics/query
v1/urlInspection/index:inspect
```

`{siteUrl}` must be percent-encoded in the path — it's either
`sc-domain:example.com` (domain property, the colon needs escaping) or
`https://example.com/` (URL-prefix property). The two are different
properties with different permissions and different data; they are not
interchangeable, and a call against the wrong one 404s as if the site
doesn't exist at all.

`urlInspection.index.inspect` takes `siteUrl` in the **request body**, not
the path — the only method here that works that way.

## Method table (the subset this skill wraps)

| Command | HTTP | Path |
|---|---|---|
| `sites list` | GET | `webmasters/v3/sites` |
| `sites get` | GET | `webmasters/v3/sites/{site}` |
| `sitemaps list` | GET | `.../sites/{site}/sitemaps` (+`?sitemapIndex=`) |
| `sitemaps get` | GET | `.../sites/{site}/sitemaps/{feedpath}` |
| `sitemaps submit` | PUT | `.../sites/{site}/sitemaps/{feedpath}` (empty body) |
| `sitemaps delete` | DELETE | `.../sites/{site}/sitemaps/{feedpath}` |
| `analytics query` | POST | `.../sites/{site}/searchAnalytics/query` |
| `inspect url` | POST | `v1/urlInspection/index:inspect` |

This skill deliberately does not wrap `sites.add`/`sites.delete` (registering
or removing which properties the account tracks) — out of scope by design,
not by omission. If that's ever needed, it's a deliberate scope change to
this skill, not a missing flag.

## `analytics query` request body

```json
{
  "startDate": "2026-07-01",
  "endDate": "2026-07-31",
  "dimensions": ["QUERY", "PAGE"],
  "type": "WEB",
  "dataState": "FINAL",
  "rowLimit": 1000,
  "startRow": 0,
  "dimensionFilterGroups": [
    {"groupType": "AND", "filters": [
      {"dimension": "PAGE", "operator": "CONTAINS", "expression": "/blog/"}
    ]}
  ]
}
```

- `dimensions` enum: `DATE`, `QUERY`, `PAGE`, `COUNTRY`, `DEVICE`,
  `SEARCH_APPEARANCE`, `HOUR`.
- The search-type field is `type` — `searchType` also exists but Google's own
  reference docs mark it **deprecated, use `type` instead**. This skill only
  ever sends `type`.
- `type` enum: `WEB` (default when omitted), `IMAGE`, `VIDEO`, `NEWS`,
  `DISCOVER`, `GOOGLE_NEWS`.
- Filter `operator` enum: `EQUALS`, `NOT_EQUALS`, `CONTAINS`, `NOT_CONTAINS`,
  `INCLUDING_REGEX`, `EXCLUDING_REGEX`.
- `dataState`: `FINAL` (default) excludes the last ~2 days, which Google
  hasn't finished processing yet; `ALL` includes fresh/unfinalized data that
  can still shift on a later query.
- Dates are `YYYY-MM-DD` in Pacific Time (UTC-8), not the caller's local
  timezone.
- Response `rows` (when present) is an array of `{keys: [...], clicks,
  impressions, ctr, position}` — `keys` lines up positionally with the
  `dimensions` array in the request. **No `rows` key at all, not an empty
  array, means zero data for that range/filter** — this is what a newly
  verified or low-traffic property returns.

## `inspect url` response shape

```json
{
  "inspectionResult": {
    "inspectionResultLink": "https://search.google.com/search-console/inspect?...",
    "indexStatusResult": {
      "verdict": "PASS|PARTIAL|FAIL|NEUTRAL",
      "coverageState": "e.g. \"URL is unknown to Google\", \"Submitted and indexed\"",
      "robotsTxtState": "ALLOWED|DISALLOWED|ROBOTS_TXT_STATE_UNSPECIFIED",
      "indexingState": "INDEXING_ALLOWED|BLOCKED_BY_META_TAG|BLOCKED_BY_HTTP_HEADER|BLOCKED_BY_ROBOTS_TXT|INDEXING_STATE_UNSPECIFIED",
      "pageFetchState": "SUCCESSFUL|SOFT_404|BLOCKED_ROBOTS_TXT|NOT_FOUND|ACCESS_DENIED|SERVER_ERROR|PAGE_FETCH_STATE_UNSPECIFIED",
      "lastCrawlTime": "RFC3339 timestamp, omitted if never crawled",
      "googleCanonical": "the URL Google chose as canonical",
      "userCanonical": "the URL the page itself declares canonical",
      "sitemap": ["sitemap URLs that reference this page, if any"],
      "referringUrls": ["pages Google found linking to this URL"],
      "crawledAs": "DESKTOP|MOBILE"
    },
    "mobileUsabilityResult": {"verdict": "..."}
  }
}
```

For a URL Google has never crawled, most fields come back
`*_UNSPECIFIED`/absent rather than an error — `coverageState: "URL is
unknown to Google"` with everything else empty is the normal shape for that
case, confirmed live against `https://goldypaper.com/`.

## `sitemaps submit` / `delete`

Both take an empty body — the sitemap URL is entirely in the path
(`{feedpath}`, itself a full URL like `https://example.com/sitemap.xml`,
percent-encoded). `submit` is idempotent: resubmitting a sitemap Google
already knows about just refreshes its "last submitted" timestamp, no error.

## Mobile-Friendly Test — do not use

The discovery document still lists `urlTestingTools.mobileFriendlyTest.run`
(`v1/urlTestingTools/mobileFriendlyTest:run`) with a `url`/
`requestScreenshot` request body. **The live endpoint returns `400
INVALID_ARGUMENT` on every request**, including a known-good URL
(`https://www.google.com/`) — confirmed live, not a request-shape bug on
this skill's side. Google retired the standalone Mobile-Friendly Test tool;
the discovery schema wasn't updated to match. This skill does not wrap it.
Mobile usability signal, where available, now comes back inside
`inspect url`'s `mobileUsabilityResult` instead (itself often
`VERDICT_UNSPECIFIED` — Google folded most of this into Core Web Vitals
reporting, which has no API).

## Errors

| HTTP | Meaning here |
|---|---|
| 400 | malformed query body — usually a bad `--dimensions`/`--filter` value or an unparseable date |
| 401 | access token invalid/expired — a fresh `access_token()` call gets a new one automatically |
| 403 | service account has no permission on this site — check Search Console's own Users and permissions, not GCP IAM |
| 404 | wrong site URL, or the service account can't see this resource at all — `sc-domain:` and `https://` forms of the same domain are different properties |
