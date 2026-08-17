---
name: gsc
description: Read Google Search Console data — search performance (clicks, impressions, CTR, position by query/page/date/country/device), per-URL indexing status — and manage sitemaps (list, submit, delete), via the Search Console API v1. Use when the user asks about search traffic, rankings, top queries or pages, why a URL isn't indexed, or wants to resubmit a sitemap after publishing content. Also use when the user mentions Google Search Console, GSC, or Search Console specifically. Do NOT use for Google Tag Manager (see the gtm skill) or Google Analytics (GA4) reporting — both are separate APIs and separate concerns.
---

# GSC — Google Search Console via the API

A single stdlib-Python script over the Search Console API v1. The one
non-stdlib piece is `google-auth`, used only to RS256-sign the service
account's JWT — every actual API call still goes over plain `urllib`.

Read-only for search performance and indexing status; the only write
operations are sitemap submit/delete — this skill is deliberately scoped
narrower than `gtm`. It does not register or remove properties from the
account (`sites.add`/`sites.delete`) — that's out of scope by design.

## Setup — check before the first call

- **`GTM_SERVICE_ACCOUNT_KEY` exported** — this skill reuses the exact same
  service account key as the `gtm` skill, pointing at the service account
  JSON key from Google Cloud Console (IAM & Admin → Service Accounts). On
  zsh, put the export in `~/.zshenv`, **not `~/.zshrc`** — zsh only reads
  `.zshrc` for interactive shells, invisible to the non-interactive shell an
  agent runs commands in.
- **That same service account must be added as a user inside Search Console
  itself** (search.google.com/search-console → the property → Settings →
  Users and permissions → Add user), with permission level **Full** — Full
  is required for sitemap submit/delete (Restricted can't write). A GCP IAM
  role does nothing here — Search Console access is granted entirely inside
  the Search Console UI, not Cloud Console. Same pattern as GTM.
- **`pip install google-auth`** once — already done if `gtm` is set up.
- **Search Console API enabled** on the service account's GCP project (APIs
  & Services → Library → "Search Console API").
- **Optionally, `GSC_SITE_URL` exported** for whichever property is worked
  on most — every command falls back to it instead of requiring `--site` on
  every call. Without it, `--site` is required explicitly.

## Finding the site URL

`--site` falls back to `GSC_SITE_URL` when that env var is set — pass the
flag only to override, or to work against a different property for one
call. Never hardcode it when the env var covers it.

A property is either a **domain property** (`sc-domain:example.com`, covers
http/https and all subdomains) or a **URL-prefix property**
(`https://example.com/`, that scheme+host only) — these are different
properties with different data, not two names for the same thing. Find the
exact string in the Search Console UI's property picker dropdown, or run
`gsc.py sites list` (no `--site` needed) to see every property the service
account can access.

## Workflow

**1. Discover before assuming.** `sites list` to confirm which properties
are accessible. `sitemaps list` to see what's already submitted before
submitting again.

**2. Search performance is `analytics query`**, not a report you browse —
give it a date range and dimensions. `--dimensions query,page` groups by
both; a plain `analytics query --start ... --end ...` with no dimensions
returns one aggregate row for the whole date range. **No `rows` key in the
response means zero data for that range** (not an error) — a new or
low-traffic property genuinely has nothing to show yet; say so plainly
rather than treating it as a failed call. Dates are Pacific Time, and the
last ~2 days are excluded by default (`dataState=FINAL`) since Google hasn't
finished processing them.

**3. Indexing status for one URL is `inspect url`.** `coverageState: "URL is
unknown to Google"` with most other fields empty is the normal shape for a
URL Google has never crawled — again, not an error.

**4. Sitemap changes are immediate, no draft/publish step** — unlike `gtm`,
there's no workspace-then-version flow here. `sitemaps submit` takes effect
right away and is safe to repeat (idempotent, just refreshes the timestamp).
Still worth telling the user what's about to be submitted before doing it,
since it's the one command here that changes anything.

## Commands

`--site` shown below is omittable once `GSC_SITE_URL` is set (see Setup) —
included here for completeness, not because every call needs it typed out.

```
gsc.py sites list
gsc.py sites get      --site S

gsc.py sitemaps list   --site S [--sitemap-index INDEX_URL]
gsc.py sitemaps get    --site S --sitemap SITEMAP_URL
gsc.py sitemaps submit --site S --sitemap SITEMAP_URL
gsc.py sitemaps delete --site S --sitemap SITEMAP_URL

gsc.py analytics query --site S --start YYYY-MM-DD --end YYYY-MM-DD
                        [--dimensions query,page,date,country,device,searchAppearance,hour]
                        [--search-type web|image|video|news|discover|googleNews]
                        [--row-limit N] [--start-row N]
                        [--data-state final|all]
                        [--filter DIMENSION:OPERATOR:EXPRESSION ...]

gsc.py inspect url --site S --url URL [--language-code en-US]
```

Every call prints the API's JSON response (or an `error:` line on stderr).
Full field reference, filter operator/dimension enums, response shapes, and
the Mobile-Friendly Test deprecation note: `reference/api.md`.

## Rules

- **`sitemaps submit`/`delete` are the only mutating commands** — both
  appended to `.gsc-audit.jsonl` at the repo root (auto-detected via the
  nearest `.git`), with timestamp, site, and sitemap URL. Add it to
  `.gitignore`.
- **Domain vs URL-prefix properties are not interchangeable.** A call
  against the wrong form of the same domain 404s exactly like the property
  doesn't exist — if a site that should work 404s, check whether it's
  registered as `sc-domain:` or `https://` before assuming it's a permission
  problem.
- **Empty results are real answers, not failures.** A property with zero
  clicks in range, zero sitemaps, or a never-crawled URL all return
  successful, mostly-empty responses — report them as findings, don't retry
  or treat them as something going wrong.
- **Never call the Mobile-Friendly Test endpoint** — it's in the discovery
  doc but dead server-side (confirmed: 400s on every URL). Use `inspect
  url`'s `mobileUsabilityResult` for whatever mobile signal is still
  available.
