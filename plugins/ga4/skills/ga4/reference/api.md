# GA4 / analytics-mcp reference

Ground truth for this doc: the live `tools/list` and `tools/call` responses
from `pipx run analytics-mcp` (v1.0.0, MCP protocol `2024-11-05`) against the
real `goldypaper.com` GA4 property, not just the upstream README — the
README undercounts the tool set (lists 7, server exposes 9).

**Setup and auth are covered once, in `SKILL.md` — not repeated here.**
`analytics-mcp`'s own tool descriptions already carry most argument-shape
docs live (visible in your tool list) — this file covers what those don't:
transport/session-lifecycle mechanics, the empty-result convention, and a
schema-free fallback reference for `scripts/mcp_client.py`.

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

## Admin API writes — `ga4_admin.py`

Everything below is a separate concern from `analytics-mcp` above: the
Analytics Admin API v1beta's write methods, called directly by
`scripts/ga4_admin.py`, not exposed by any `analytics-mcp` tool. Ground
truth is the live discovery document
(`analyticsadmin.googleapis.com/$discovery/rest?version=v1beta`), cross-checked
against a real create → patch → delete round trip on `goldypaper.com`.

**Scope**: `https://www.googleapis.com/auth/analytics.edit` — confirmed
live to cover both reads and writes through this API (no need to also
request `analytics.readonly`). **Requires Editor or above** at the GA4
property level (Admin → Property Access Management) — Viewer 403s on every
`ga4_admin.py` call.

**`properties.conversionEvents` is deprecated.** Google's own reference
docs state outright: *"Deprecated: Use `CreateKeyEvent`, `DeleteKeyEvent`,
`GetKeyEvent`, `ListKeyEvents`, and `UpdateKeyEvent` instead."*
`ga4_admin.py` only ever calls `properties.keyEvents` — don't add a
`conversionEvents` path even though the discovery doc still lists it as a
live resource.

**`properties.audiences` only exists in `v1alpha`**, not the `v1beta` every
other resource here uses — left out of `ga4_admin.py` deliberately (a
noticeably less stable API surface). Not implemented; ask before adding it
if it's ever needed.

### Resource → method → path

| Resource | list | get | create | patch | archive/delete |
|---|---|---|---|---|---|
| `customDimensions` | `GET .../customDimensions` | `GET {name}` | `POST .../customDimensions` | `PATCH {name}?updateMask=...` | `POST {name}:archive` |
| `customMetrics` | `GET .../customMetrics` | `GET {name}` | `POST .../customMetrics` | `PATCH {name}?updateMask=...` | `POST {name}:archive` |
| `keyEvents` | `GET .../keyEvents` | `GET {name}` | `POST .../keyEvents` | `PATCH {name}?updateMask=...` | `DELETE {name}` |
| `dataStreams` | `GET .../dataStreams` | `GET {name}` | `POST .../dataStreams` | `PATCH {name}?updateMask=...` | `DELETE {name}` |

`updateMask` is a comma-separated list of the exact camelCase body field
names being changed (e.g. `displayName,description`) — **confirmed
live**: sending only the changed fields in both the mask and the body
patches cleanly, no need to resend the full resource.

### `customDimensions` fields

- `displayName` (required, ≤82 chars), `parameterName` (required, immutable
  — the tagging parameter name), `scope` (required, immutable, enum:
  `EVENT` | `USER` | `ITEM`), `description` (optional, ≤150 chars),
  `disallowAdsPersonalization` (optional bool).
- Patchable: `displayName`, `description`, `disallowAdsPersonalization`.
  `parameterName`/`scope` are immutable after creation.

### `customMetrics` fields

- `displayName` (required), `parameterName` (required, immutable), `scope`
  (required, immutable — the enum only has one real value, `EVENT`),
  `measurementUnit` (required, enum: `STANDARD` | `CURRENCY` | `FEET` |
  `METERS` | `KILOMETERS` | `MILES` | `MILLISECONDS` | `SECONDS` |
  `MINUTES` | `HOURS`), `description` (optional), `restrictedMetricType`
  (optional array, enum: `COST_DATA` | `REVENUE_DATA` — required if
  `measurementUnit` is `CURRENCY`).
- Patchable: `displayName`, `description`, `measurementUnit`.

### `keyEvents` fields

- `eventName` (required, immutable — the raw GA4 event name, e.g.
  `purchase`, not a display label), `countingMethod` (required, enum:
  `ONCE_PER_EVENT` | `ONCE_PER_SESSION`), `defaultValue` (optional object:
  `{"currencyCode": "USD", "numericValue": 10.0}` — backfills a value for
  occurrences that don't set one themselves).
- Patchable: `countingMethod`, `defaultValue`.
- `custom: true` in the response means it's a property-specific key event a
  human or this script created; property creation auto-generates some
  (`purchase`, and lead-gen ones like `close_convert_lead`/`qualify_lead`
  when "Generate leads" is picked as a business objective during setup —
  seen live on `goldypaper.com`). `deletable: false` on a response means
  don't bother calling `delete` — it'll reject.

### `dataStreams` fields

- `type` (required, immutable, enum: `WEB_DATA_STREAM` |
  `ANDROID_APP_DATA_STREAM` | `IOS_APP_DATA_STREAM`), `displayName`
  (required for web streams). Exactly one of `webStreamData`
  (`defaultUri`), `androidAppStreamData` (`packageName`), `iosAppStreamData`
  (`bundleId`) — must match `type`.
- `webStreamData.measurementId` (`G-XXXXXXX`) is **output only** — it's
  assigned by Google on create, never supplied.
- Patchable: `displayName`, `webStreamData.defaultUri` (nested field path
  in the mask, confirmed by schema — not live-tested).

### Live-verified round trip

`events create` → `events patch` → `events delete` against the real
`goldypaper.com` property, full cycle, cleaned up after itself:
```
$ ga4_admin.py events create --property 549905304 --event-name ga4_skill_verify_test --counting-method ONCE_PER_EVENT
{"name": "properties/549905304/keyEvents/15447928506", "eventName": "ga4_skill_verify_test", "deletable": true, "custom": true, "countingMethod": "ONCE_PER_EVENT", ...}
$ ga4_admin.py events patch --name properties/549905304/keyEvents/15447928506 --counting-method ONCE_PER_SESSION
{"countingMethod": "ONCE_PER_SESSION", ...}
$ ga4_admin.py events delete --name properties/549905304/keyEvents/15447928506
deleted properties/549905304/keyEvents/15447928506
```
`dimensions`/`metrics` create+archive and `streams` create+delete were
**not** live-tested the same way — archiving a dimension/metric isn't
confirmed side-effect-free against the property's slot quota the way
deleting a key event is, and creating a real data stream assigns a real,
visible Measurement ID. Field names for both come straight from the
verified discovery-doc schema; a wrong field name 400s loudly rather than
silently misbehaving, so the risk of an untested call is a clear error, not
silent corruption.

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
