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

## Enumerate the tools, don't trust a list

Read the tool names from your own tool list. Published counts and names are third-party and have already moved once; Meta's own overview documents seven areas rather than a fixed roster:

1. Comprehensive reporting — campaign performance insights and analytics
2. Ad creation and management — campaigns, ad sets, ads
3. Catalog creation and management — product data, feed troubleshooting
4. Signals and datasets — signal health and quality metrics
5. Help and troubleshooting — Meta Business Help Center article search
6. A/B tests and conversion lift studies — create, manage, retrieve
7. Activity logs — account change history, as in Ads Manager

Areas 5 and 7, and the benchmark/opportunity-score side of 1, have **no ads-cli equivalent** — that is the main reason to reach for this path. Conversely the CLI reaches flags no tool exposes (DCO asset feeds, raw targeting JSON, EU DSA fields, `--fields`), which is the reason to keep both.

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
