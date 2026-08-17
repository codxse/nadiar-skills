---
name: ga4
description: Query Google Analytics 4 reporting data — traffic, sessions, events, conversions, funnels, realtime activity, custom dimensions/metrics, Google Ads links, annotations — via the official Google analytics-mcp server, and manage GA4 property configuration — custom dimensions/metrics, key events (conversions), data streams — via the Analytics Admin API. Use when the user asks about site traffic, users, sessions, top pages/events, conversion/ROAS numbers, a funnel, "what's happening right now" on the site, or wants to mark an event as a conversion, add a custom dimension/metric, or manage a data stream. Also use when the user mentions Google Analytics, GA4, or analytics-mcp specifically. Do NOT use for Google Tag Manager (see the gtm skill, which configures *what* fires) or Google Search Console (see the gsc skill, which covers search rankings/indexing) — GA4 is the third, separate leg: it reports on traffic that already happened, and configures how that traffic is measured.
---

# GA4 — Google Analytics 4 via analytics-mcp + the Admin API

Two separate paths, for two separate concerns:

- **Reporting (read-only)** — `analytics-mcp`, Google's own MCP server
  (PyPI: `analytics-mcp`), bundled as a real MCP server declaration at the
  **plugin root** (`plugins/ga4/.mcp.json` — one level up from this file,
  not next to it). Once the plugin is enabled *and a session has started
  after that*, its 9 tools are just available directly, no CLI to shell out
  to. Every one of those 9 tools only reads — `analytics-mcp` requests only
  the `analytics.readonly` scope in its own source, so it cannot write no
  matter what role the service account holds.
- **Configuration (writes)** — `scripts/ga4_admin.py`, a custom script
  against the Analytics Admin API v1beta directly, the same pattern as
  `gtm`/`gsc`. This is the only way to create/change custom dimensions,
  custom metrics, key events (what GA4 calls marking an event as a
  conversion), or data streams — `analytics-mcp` has no tool for any of it.

**If the reporting tools aren't in your tool list** (plugin installed
mid-session, or you're a subagent spawned from a session that predates the
install), `scripts/mcp_client.py` drives the same server directly over
stdio as a fallback — see `reference/api.md`.

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
  (Admin → Property Access Management → Add users) — a GCP IAM role grants
  nothing here, same pattern as `gtm`/`gsc`. **Viewer** is enough for the
  `analytics-mcp` reporting tools; **`ga4_admin.py`'s writes need Editor or
  above** (a 403 from `ga4_admin.py` with Viewer-level access is expected,
  not a bug).
- **Optionally, `GA_PROPERTY_ID` exported** for whichever property is used
  most, so `ga4_admin.py`'s `--property` never needs to be typed (or
  hardcoded) into a command. Without it, `--property` is required
  explicitly. `analytics-mcp`'s reporting tools take `property_id` as a call
  argument regardless — there's no equivalent env var for those.
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

## Tools (reporting, read-only)

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

## Configuration writes — `ga4_admin.py`

Four resources, each with `list`/`get`/`create`/`patch`/`archive-or-delete`:

```
ga4_admin.py dimensions list|get|create|patch|archive  --property P | --name N ...
ga4_admin.py metrics    list|get|create|patch|archive  --property P | --name N ...
ga4_admin.py events     list|get|create|patch|delete   --property P | --name N ...
ga4_admin.py streams    list|get|create|patch|delete   --property P | --name N ...
```

`--property` falls back to `GA_PROPERTY_ID`; `--name` is the full resource
name (`properties/P/keyEvents/ID`, etc.) — copy it straight from a `list`
response rather than reconstructing it. Full flags, field/enum reference,
and the deprecated-resource note below: `reference/api.md`.

**Workflow — same discover-before-mutate discipline as `gtm`/`gsc`:**
1. `list` the resource first. Don't create something that already exists,
   and don't guess a `--name` for `patch`/`archive`/`delete` — copy it from
   the list.
2. State plainly what's about to be created/changed/removed and get an
   explicit yes before the call — there's no draft/publish staging step
   here like `gtm`; every one of these calls takes effect immediately on
   the real property.
3. **"Create an event" almost always means `events create`** (a **key
   event** — GA4's current term for "conversion event"; deprecation note in
   `reference/api.md`). Creating a key event doesn't require the underlying
   GA4 event to exist yet or ever fire — it just marks that event name as a
   conversion whenever it does.
4. **`archive` (dimensions/metrics) is not the same guarantee as `delete`
   (events/streams).** A `429`/quota error on `create` means check `list`
   first — a property has a limited number of custom dimension/metric
   slots.

## Rules

- **Never call anything but the service-account path for auth** — the
  OAuth-desktop flow is a live 403 trap until someone manually adds test
  users on the consent screen; don't suggest it as the default.
- **`GA_SERVICE_ACCOUNT_KEY`/`GA_PROJECT_ID`, never
  `GOOGLE_APPLICATION_CREDENTIALS`/`GOOGLE_PROJECT_ID`, in the shell
  environment** — those are the names `.mcp.json` remaps *to* for the
  subprocess, not what the user exports.
- **The reporting tools (`analytics-mcp`) are read-only** — no confirmation
  gate, no audit log needed there. **`ga4_admin.py` is not** — every
  `create`/`patch`/`archive`/`delete` is appended to `.ga4-audit.jsonl` at
  the repo root (auto-detected via the nearest `.git`), and needs the
  explicit-confirmation step in Configuration writes #2 above before the
  call is made, unlike the reporting tools.
- **Empty is a finding, not an error** (see Workflow #4) — report it, don't
  retry.
