# GA4 / analytics-mcp reference

Ground truth for this doc: the live `tools/list` and `tools/call` responses
from `pipx run analytics-mcp` (v1.0.0, MCP protocol `2024-11-05`) against the
real `goldypaper.com` GA4 property, not just the upstream README — the
README undercounts the tool set (lists 7, server exposes 9) and doesn't
mention the OAuth consent-screen trap below.

## Auth

`analytics-mcp` authenticates via Application Default Credentials (ADC),
resolved through `GOOGLE_APPLICATION_CREDENTIALS`. Three ways to produce
that, in order of preference for this setup:

1. **Point `GOOGLE_APPLICATION_CREDENTIALS` straight at a service account
   key file.** Not in the upstream README (it only documents the two
   `gcloud`-based flows below), but standard ADC behavior — `google-auth`
   resolves a raw service-account JSON the same way `gcloud`-generated ADC
   files resolve. No `gcloud` login, no browser, doesn't touch
   `~/.config/gcloud/application_default_credentials.json`. **This is what
   this skill uses**, via `.mcp.json`'s env remap (see `SKILL.md`).

2. **OAuth Desktop/Web client + interactive login:**
   ```
   gcloud auth application-default login \
     --scopes https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform \
     --client-id-file=YOUR_CLIENT_JSON_FILE
   ```
   **Live trap hit while building this skill:** if the OAuth client's
   consent screen is still in "Testing" publishing status (the default for
   a newly created client), any Google account not explicitly added as a
   **Test user** gets `Error 403: access_denied` — "has not completed the
   Google verification process." Fix is either adding the signing-in
   account under OAuth consent screen → Test users, or publishing the app.
   This flow authenticates as a human, not the service account — only
   reach for it if that distinction actually matters.

3. **Service-account impersonation:**
   ```
   gcloud auth application-default login \
     --impersonate-service-account=SERVICE_ACCOUNT_EMAIL \
     --scopes=https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform
   ```
   Requires the `gcloud`-authenticated human to already hold
   `roles/iam.serviceAccountTokenCreator` on the service account, and (like
   #2) overwrites the same shared ADC file. No real advantage over #1 for a
   single fixed service account.

Options 2 and 3 both write to the **same well-known path**
(`~/.config/gcloud/application_default_credentials.json`) with no way to
redirect the output — running either overwrites whatever was there, which on
a shared machine may belong to something else. Option 1 never touches it.

**Property-level access is separate from GCP IAM**, same as `gtm`/`gsc`: add
the service account inside GA4 itself — Admin → Property Access Management
→ Add users → the service account's email → **Viewer** (minimum; every tool
below only reads). A GCP IAM role on the service account grants nothing
inside GA4.

## APIs to enable

On the GCP project referenced by `GA_PROJECT_ID`:
- `analyticsadmin.googleapis.com` (Google Analytics Admin API)
- `analyticsdata.googleapis.com` (Google Analytics Data API)

An unenabled API returns an explicit 403 on the first call. An empty
`accountSummaries: []`-shaped response means the APIs *are* enabled but the
identity has no property access yet (Property Access Management step
skipped) — these are two different failure shapes, don't conflate them.

## Tool catalog (live, 9 tools)

Two of these aren't in the upstream README at all —
`list_property_annotations` and `run_conversions_report`.

| Tool | Required args | Notes |
|---|---|---|
| `get_account_summaries` | none | Every account/property the identity can see. Returns `[]` if none. |
| `get_property_details` | `property_id` | |
| `list_google_ads_links` | `property_id` | |
| `list_property_annotations` | `property_id` | Dated notes a human left in the GA4 UI — releases, campaign launches, traffic anomalies. |
| `get_custom_dimensions_and_metrics` | `property_id` | Call this before referencing a custom field in `run_report`/`run_conversions_report` — custom fields aren't in the standard dimension/metric tables. |
| `run_report` | `property_id`, `date_ranges`, `dimensions`, `metrics` | General-purpose report. |
| `run_realtime_report` | `property_id`, `dimensions`, `metrics` | No `date_ranges` param at all — always "now" (~last 30 min). Standard fields only, no custom metrics. |
| `run_funnel_report` | `property_id`, `funnel_steps` | `date_ranges` is optional here (unlike `run_report`). |
| `run_conversions_report` | `property_id`, `date_ranges`, `dimensions`, `metrics`, `conversion_spec` | Fixed dimension/metric allowlist, see below. |

`property_id` accepts either a bare number (`549905304`) or
`"properties/549905304"`.

## `dimensions` / `metrics` are plain strings, not objects

```json
{"dimensions": ["date", "sessionDefaultChannelGroup"], "metrics": ["activeUsers", "sessions"]}
```

**Not** `[{"name": "sessions"}]` — that's the REST API's JSON body shape,
and this server rejects it: `Input validation error: {'name': 'sessions'}
is not of type 'string'`. Every other structured argument here
(`date_ranges`, `dimension_filter`, `order_bys`, `conversion_spec`) *is* an
object or list of objects — `dimensions`/`metrics` are the one exception,
a bare list of field-name strings.

## Field naming: snake_case, not the public REST docs' camelCase

The Data API's own REST reference
(`developers.google.com/analytics/devguides/reporting/data/v1beta`) uses
camelCase (`dateRanges`, `dimensionFilter`). This MCP server instead speaks
the **protobuf** field names — snake_case — because it's built on the
protocol buffer definitions
(`github.com/googleapis/googleapis/tree/master/google/analytics/data/v1beta`),
not the REST JSON mapping. Copying a camelCase example from the public docs
verbatim will silently mismatch the schema instead of erroring clearly.

## `date_ranges` shape

```json
[{"start_date": "2025-01-01", "end_date": "2025-01-31", "name": "Jan2025"}]
```

Relative shortcuts work directly in `start_date`/`end_date`: `"today"`,
`"yesterday"`, `"NdaysAgo"` (e.g. `"30daysAgo"`). Multiple ranges in one call
are allowed (comparison reports).

## Filter expression shape (`dimension_filter` / `metric_filter`)

Recursive tree of `filter` / `not_expression` / `and_group` / `or_group`:

```json
{"filter": {"field_name": "eventName", "string_filter": {"match_type": 2, "value": "add", "case_sensitive": false}}}
{"not_expression": {"filter": {...}}}
{"filter": {"field_name": "source", "empty_filter": {}}}
{"and_group": {"expressions": [{"filter": {...}}, {"filter": {...}}]}}
{"or_group": {"expressions": [{"filter": {...}}, {"filter": {...}}]}}
```

Numeric filters take an `operation` enum plus a typed value:

```json
{"filter": {"field_name": "eventCount", "numeric_filter": {"operation": 4, "value": {"int64_value": "10"}}}}
{"filter": {"field_name": "purchaseRevenue", "between_filter": {"from_value": {"double_value": 10.0}, "to_value": {"double_value": 25.0}}}}
```

`dimension_filter` and `metric_filter` are applied **independently** — a
condition that needs a dimension test AND a metric test to hold *together*,
combined with OR across two different dimension/metric pairs, can't be
expressed in one call. Split into multiple report calls (filter by the
dimension side, apply each metric condition client-side) or run one report
per combination — see the tool's own description for the worked example.

## `order_bys` shape

```json
[{"dimension": {"dimension_name": "eventName", "order_type": 1}, "desc": false}]
[{"metric": {"metric_name": "eventCount"}, "desc": true}]
```

Every dimension/metric named in `order_bys` must also appear in the
request's own `dimensions`/`metrics` list.

## `run_conversions_report` — fixed allowlists

Unlike `run_report`, `dimensions` and `metrics` here are **not** open to the
full standard dimension/metric tables — only:

- **Dimensions**: `campaignName`, `continent`, `country`,
  `defaultChannelGroup`, `deviceCategory`, `medium`, `platform`,
  `primaryChannelGroup`, `source`, `sourceMedium`, `sourcePlatform`,
  `subcontinent`
- **Metrics**: `advertiserAdClicks`, `advertiserAdCost`,
  `advertiserAdCostPerAllConversionsByConversionDate`,
  `advertiserAdCostPerAllConversionsByInteractionDate`,
  `advertiserAdCostPerClick`, `advertiserAdImpressions`,
  `allConversionsByConversionDate`, `allConversionsByInteractionDate`,
  `returnOnAdSpendByConversionDate`, `returnOnAdSpendByInteractionDate`,
  `totalRevenueByConversionDate`, `totalRevenueByInteractionDate`

`conversion_spec` is required:
```json
{"conversion_actions": ["conversionActions/12345"], "attribution_model": "DATA_DRIVEN"}
```
Pass `"conversion_actions": []` for all conversion actions.
`attribution_model` is `"DATA_DRIVEN"` or `"LAST_CLICK"`.

## `run_funnel_report` — steps

Each step is either a simple event name or a full filter expression:
```json
{"name": "Purchase", "filter_expression": {"or_group": {"expressions": [{"funnel_event_filter": {"event_name": "purchase"}}, {"funnel_event_filter": {"event_name": "in_app_purchase"}}]}}, "is_directly_followed_by": false}
```
Optional `funnel_breakdown` (`{"breakdown_dimension": "deviceCategory"}`)
segments the funnel; `funnel_next_action`
(`{"next_action_dimension": "eventName", "limit": 5}`) reports what users do
after completing or dropping off.

## Empty-result shape

`run_report`/`run_realtime_report`/`run_conversions_report` always include a
`rows` key, empty (`[]`) when there's no data — never omitted. Live example
against `goldypaper.com` (brand-new property, no tracking snippet installed
on the site yet):

```json
{
  "dimension_headers": [{"name": "date"}],
  "metric_headers": [{"name": "activeUsers", "type_": "TYPE_INTEGER"}, {"name": "sessions", "type_": "TYPE_INTEGER"}],
  "metadata": {"currency_code": "USD", "time_zone": "Asia/Jakarta", "data_loss_from_other_row": false, "sampling_metadatas": []},
  "rows": [],
  "row_count": 0
}
```

`metadata.time_zone`/`currency_code` echo the property's own settings —
useful as a live confirmation the report hit the right property without a
separate `get_property_details` call.

## MCP transport notes

`analytics-mcp` speaks standard MCP over stdio — newline-delimited JSON-RPC
2.0, no `Content-Length` framing. `initialize` → `notifications/initialized`
→ `tools/list` / `tools/call`, same as any other MCP stdio server. First
launch of `pipx run analytics-mcp` builds and caches a venv (slow, one-time);
subsequent launches reuse the pipx cache and start immediately.

**stdin must stay open until the response is read.** The server exits on
stdin EOF before a `tools/call` reply completes its network round trip —
closing stdin (or letting a `printf ... | pipx run analytics-mcp` pipeline
end) right after sending the request reads as a silent hang, not an error.
Hold the pipe open, read the matching response by `id`, and only then close
stdin — see `scripts/mcp_client.py`.

## If the plugin's MCP tools aren't in your tool list

MCP servers load once at session start. Installing the `ga4` plugin
mid-session (or being a subagent spawned from a session that predates the
install) means the registered `analytics-mcp` tools won't show up until a
fresh session starts — `claude mcp list` can report the server `Connected`
at the config level while the *current* session still doesn't have it. Two
ways to confirm which situation you're in:
- Registered tools missing entirely (not even via `ToolSearch`): plugin
  needs a fresh session, not a fix in this skill.
- Need an answer now anyway: `scripts/mcp_client.py <tool_name> '<json_args>'`
  drives the same server directly over stdio, reading `GA_SERVICE_ACCOUNT_KEY`/
  `GA_PROJECT_ID` from the environment exactly like the plugin does.
