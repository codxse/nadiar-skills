# Hosted MCP server — `https://mcp.facebook.com/ads`

Meta-hosted, so there is no process to run, no version to pin, and no token to rotate. The plugin declares it at `plugins/meta-ads/.mcp.json`; enabling the plugin starts it, and `/mcp` shows and toggles it.

```json
{
  "mcpServers": {
    "meta-ads": {
      "type": "http",
      "url": "https://mcp.facebook.com/ads",
      "oauth": {
        "scopes": "ads_management ads_read catalog_management business_management pages_show_list instagram_basic ads_mcp_management"
      }
    }
  }
}
```

`oauth.scopes` is pinned rather than left to discovery so the grant is visible in the repo and editable in one place. It is exactly the set the server advertises in its `WWW-Authenticate` header, which is what Claude Code would request anyway — pinning changes nothing about the default grant, it just makes it explicit.

## The tool inventory — 98 tools, counted from a live connection

Published figures said 29. The real list, read from a connected session on 2026-08-23, is **98**. Read your own tool list rather than any number, this one included — but the shape is stable enough to plan against:

| Group | Count | What only lives here |
|---|---|---|
| `ads_catalog_*` | 34 | feed rules, upload sessions, diagnostics, dynamic-ads health, product search |
| reads & discovery (`ads_get_*`) | 21 | **ad preview**, delivery **errors**, **field context**, help articles, opportunity score, IG media |
| `ads_pixel_event_*` / `ads_pixel_parameter_*` | 8 | **custom conversion + parameter CRUD** |
| custom audiences | 7 | **the whole feature** — create/update/delete, membership updates |
| `ads_experiment_*` | 7 | **creating** A/B and lift tests |
| creative media | 7 | image/video upload, local-image staging and finalize |
| `ads_insights_*` | 5 | performance trend, anomaly signal, auction-ranking and industry **benchmarks**, advertiser context |
| structure creates | 4 | — (campaign, ad set, ad, creative; the CLI has these too) |
| entity mutation | 2 | `ads_update_entity`, `ads_activate_entity` |
| misc | 3 | **activity logs**, **Ads Library search**, IG post boost |

**Where this beats the CLI**, and the reason to keep both paths: custom audiences and pixel event/parameter configuration have **no CLI command at all**; experiments are read-only in the CLI (`study list`) but writable here; and ad preview, delivery-error lookup, field-context/alias resolution, Ads Library competitor search, activity logs, benchmarks and opportunity score are all MCP-only. The CLI keeps DCO asset feeds, raw `--targeting`/`--promoted-object`/`--asset-feed-spec` JSON, EU DSA fields, and `--fields`.

`ads_get_ad_entities` is the general query tool the others point at; `ads_get_field_context` resolves aliases (`spend` → `amount_spent`, `actions:lead` → `lead`) and lists which levels support a field, so call it before guessing a field name.

## Two call contracts every tool enforces

**`client_conversation_id` is required on every call.** A 20-character random string of `A-Za-z0-9` — generate one on the first Meta Ads call of a conversation and send that identical value on every Meta Ads call afterwards, including after the topic changes. Never derive it from an ad account, business, user or campaign id, never send it to a tool from a different MCP server, and only start a new one when a genuinely new conversation begins.

**`advertiser_request` wants the user's own words, verbatim.** Quote them rather than paraphrasing: no summarising, no shifting into a more formal register, no upgrading plain words into industry terms, no metric abbreviations or system field names they did not say, and **no translating** — keep the language they used. A question or lookup counts as a request. When they stated a goal early and only approved later, combine both into one request that keeps the original subject, rather than capturing the bare "yes". Leave it empty only for pure greeting or acknowledgement, and never invent a request. **Never put names, contact details, or other personal information in it** — this field travels to Meta.

## Account gating — check two flags before using an id

`ads_get_ad_accounts` returns `is_ads_mcp_enabled` and `is_queryable` per account. **If `is_ads_mcp_enabled` is false, do not use that account id or any object under it in any later call.** If `is_queryable` is false, do not call `ads_get_ad_entities` for it — surface `not_queryable_reason` instead. Both were true for both accounts here, but the flags exist because they are not always.

The same response carries `currency`, `has_payment_method`, `account_status`, and `min_daily_budget_cents`. **`min_daily_budget_cents` is misnamed for currencies with no subunit** — verified live: an IDR account returned `18014`, which is Rp 18,014, while a USD account returned `100`, which is $1.00. Read it as "smallest unit of this account's currency", and let it be the anchor for what a budget integer means on that account.

`business_id`/`business_name` reflect the **owning** business only, and are empty for an account with no owning business — a personal ad account shows up exactly that way. Accounts shared with agencies may have other businesses with access that this response does not show.

## What `ads_get_errors` does not cover

Delivery-blocking errors on campaigns, ad sets and ads only. It explicitly does **not** report a disabled or restricted ad account, ad rejections, or performance/pacing/optimization problems. A restricted account therefore looks error-free through this tool — check `account_status` from `ads_get_ad_accounts` for that.

## Verified OAuth facts

Fetched live from the endpoint, not from documentation:

```
WWW-Authenticate: Bearer resource_metadata="https://mcp.facebook.com/.well-known/oauth-protected-resource/ads",
  scope="ads_management ads_read catalog_management business_management pages_show_list instagram_basic ads_mcp_management"
```

| | |
|---|---|
| issuer | `https://www.facebook.com` |
| authorization_endpoint | `https://www.facebook.com/v26.0/dialog/oauth` |
| token_endpoint | `https://graph.facebook.com/v26.0/oauth/access_token` |
| grant_types_supported | `authorization_code`, `refresh_token` |
| code_challenge_methods_supported | `S256` |
| token_endpoint_auth_methods_supported | `none` |
| registration_endpoint | `https://mcp.facebook.com/.well-known/register/ads` |

A public client with dynamic registration and PKCE means no Meta app, no client ID, no client secret. An unauthenticated request returns `401` with `{"title":"Authentication Required"}`.

Note `/.well-known/oauth-authorization-server` at the root returns `404 MCP server not found` — the metadata is per-path, under `/ads`. Only relevant if you ever need to set `authServerMetadataUrl`, which this configuration does not.

## Narrowing to read-only

To take writes off this path entirely, drop the write scopes from `oauth.scopes` and re-authenticate:

```json
"oauth": { "scopes": "ads_read business_management pages_show_list" }
```

Any write tool then fails with `403 insufficient_scope` rather than succeeding. Two caveats: the failure surfaces as a tool error at call time, not as the tool disappearing, and a scope change needs a fresh OAuth consent — Claude Code re-authenticates with the pinned set. Leave `ads_mcp_management` out only if nothing you use needs the server's own management tools.

If the authorization server advertises `offline_access`, Claude Code appends it so the access token refreshes without another browser sign-in.

## What the audit log does not cover

`scripts/meta_ads.py` writes `.meta-ads-audit.jsonl` for CLI writes only. A write made by an MCP tool never passes through it. Meta's account activity log is the trail for those, and this server's activity-log tools are how to read it — so when the question is "what changed on this account and who changed it", that is the tool to reach for, not the local file.
