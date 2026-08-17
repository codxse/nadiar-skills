---
name: ga4
description: Query Google Analytics 4 reporting data — traffic, sessions, events, conversions, funnels, realtime activity, custom dimensions/metrics, Google Ads links, annotations — via the official Google analytics-mcp server. Use when the user asks about site traffic, users, sessions, top pages/events, conversion/ROAS numbers, a funnel, or "what's happening right now" on the site. Also use when the user mentions Google Analytics, GA4, or analytics-mcp specifically. Do NOT use for Google Tag Manager (see the gtm skill, which configures *what* fires) or Google Search Console (see the gsc skill, which covers search rankings/indexing) — GA4 is the third, separate leg: it reports on traffic that already happened.
---

# GA4 — Google Analytics 4 via analytics-mcp

Unlike `gtm`/`gsc`, this skill has no custom script for its primary path.
`analytics-mcp` is Google's own MCP server (PyPI: `analytics-mcp`), bundled
as a real MCP server declaration at the **plugin root**
(`plugins/ga4/.mcp.json` — one level up from this file, not next to it) —
once the plugin is enabled *and a session has started after that*, its 9
tools are just available directly, no CLI to shell out to. Every tool is
read-only; there is nothing here that writes, so no audit log.

**If those tools aren't in your tool list** (plugin installed mid-session,
or you're a subagent spawned from a session that predates the install),
`scripts/mcp_client.py` drives the same server directly over stdio as a
fallback — see `reference/api.md`.

## Setup — check before the first call

- **`GA_SERVICE_ACCOUNT_KEY` exported**, pointing at the service account JSON
  key — reuses the exact same file as `gtm`/`gsc`
  (`goldypaper-agent@goldypaper-project-production.iam.gserviceaccount.com`).
  **Deliberately not named `GOOGLE_APPLICATION_CREDENTIALS`** even though
  that's what `analytics-mcp` itself needs: that name is what `gcloud`,
  Terraform/OpenTofu's Google provider, and other tools on this machine
  check too, so exporting it globally could silently redirect them. `.mcp.json`
  remaps `GA_SERVICE_ACCOUNT_KEY` → `GOOGLE_APPLICATION_CREDENTIALS` for the
  `analytics-mcp` subprocess only — the rest of the shell never sees that name.
- **`GA_PROJECT_ID` exported** — the GCP project ID used for API quota
  (`goldypaper-project-production`). Same remap reasoning; `analytics-mcp`
  wants `GOOGLE_PROJECT_ID`.
- On zsh, put both exports in `~/.zshenv`, **not `~/.zshrc`** — `.zshrc` is
  interactive-shell-only, invisible to the non-interactive shell an agent
  runs commands in.
- **The service account must be added inside the GA4 property itself**
  (Admin → Property Access Management → Add users), **Viewer** or above — a
  GCP IAM role grants nothing here, same pattern as `gtm`/`gsc`. Every tool
  in this skill only ever reads, so Viewer is enough even if the account was
  granted more.
- **Two APIs enabled** on the GCP project: Google Analytics **Admin** API
  and Google Analytics **Data** API (`APIs & Services → Library`). An
  unenabled API 403s explicitly on the first call — an empty `{}`/`[]`
  result instead means the APIs are enabled but the service account has no
  property access yet.
- **`pipx` installed** — `analytics-mcp` runs via `pipx run analytics-mcp`,
  which pipx caches after the first launch (no fresh Docker-style install
  every session start).

**Do not use the OAuth-desktop-client / `gcloud auth application-default
login` path** documented upstream unless you specifically need a human
Google identity instead of the service account — it opens a browser consent
screen, and an unverified OAuth client rejects any Google account not
explicitly added as a **Test user** on the OAuth consent screen
(`Error 403: access_denied`, hit live while building this skill). The
service-account path above never touches that screen at all.

## Workflow

**1. Get the property ID first.** `get_account_summaries` (no arguments)
lists every account/property the service account can see, each as
`properties/<number>`. Every other tool needs that number — don't ask the
user for it if `get_account_summaries` can answer it.

**2. Pick the right report tool** — they overlap on purpose:
- `run_report` — the general case: any standard or custom dimension/metric,
  any date range.
- `run_realtime_report` — "what's happening right now"; last ~30 minutes,
  standard dimensions/metrics only (no custom, no `date_ranges` argument).
- `run_funnel_report` — step-by-step drop-off through a defined sequence of
  events.
- `run_conversions_report` — ROAS/ad-cost/attribution metrics specifically;
  the tool description says to prefer this over `run_report` whenever the
  ask is about conversions or ad spend, because those metrics live in a
  fixed allowlist `run_report` doesn't expose (see `reference/api.md`).

**3. Field names are snake_case, not the camelCase the public REST docs
show** — `date_ranges`, `dimension_filter`, `funnel_next_action`, and inside
filter expressions `field_name`, `string_filter`, `case_sensitive`. Copying a
camelCase example from `developers.google.com` verbatim will silently
mismatch the schema. One shape trap this doesn't cover: **`dimensions` and
`metrics` are plain string arrays** (`["date", "activeUsers"]`), not the
REST API's `[{"name": "..."}]` objects — this did trip a live test
(`Input validation error: ... is not of type 'string'`), see
`reference/api.md`.

**4. Empty results are real findings.** `run_report` returns `rows: []`
with `row_count: 0` — a present-but-empty key, not an absent one (contrast
`gsc`'s `analytics query`, which omits the `rows` key entirely for zero
data). A brand-new property with no tracking snippet on the site yet reports
this way; say so plainly rather than treating it as a failed call or retrying.

## Tools

Full args, filter-expression shapes, and the two tools the upstream README
doesn't document (`list_property_annotations`, `run_conversions_report`):
`reference/api.md`.

- `get_account_summaries()` — every account/property this identity can see.
- `get_property_details(property_id)` — one property's settings.
- `list_google_ads_links(property_id)` — linked Ads accounts.
- `list_property_annotations(property_id)` — dated notes a human left in the
  UI (releases, campaign launches, traffic anomalies).
- `get_custom_dimensions_and_metrics(property_id)` — the property's own
  custom fields, needed before referencing one in `run_report`.
- `run_report(property_id, date_ranges, dimensions, metrics, ...)`
- `run_realtime_report(property_id, dimensions, metrics, ...)`
- `run_funnel_report(property_id, funnel_steps, ...)`
- `run_conversions_report(property_id, date_ranges, dimensions, metrics, conversion_spec, ...)`

## Rules

- **Never call anything but the service-account path for auth** — the
  OAuth-desktop flow is a live 403 trap until someone manually adds test
  users on the consent screen; don't suggest it as the default.
- **`GA_SERVICE_ACCOUNT_KEY`/`GA_PROJECT_ID`, never
  `GOOGLE_APPLICATION_CREDENTIALS`/`GOOGLE_PROJECT_ID`, in the shell
  environment** — those are the names `.mcp.json` remaps *to* for the
  subprocess, not what the user exports.
- **Everything here is read-only.** There is no mutating tool, so no
  confirmation gate and no audit log — unlike `gtm` (publish) and `gsc`
  (sitemap submit/delete).
- **Empty is a finding, not an error** (see Workflow #4) — report it, don't
  retry.
