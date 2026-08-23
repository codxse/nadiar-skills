# Setup — system user token (ads-cli) and OAuth (hosted MCP)

Two independent credentials. The hosted MCP server needs the second one only; the CLI needs the first one only. Set up whichever path the task uses.

## 1. ads-cli: a system user access token

A system user is a non-human Business Manager identity whose token does not expire when a person leaves or changes their password. That is why the CLI uses one rather than a personal login.

**Create the system user** — Meta Business Suite → **Settings** → **Users** → **System Users** → **Add**. Give it the **Admin** role. Admin here means admin *of the business*, which by itself grants access to nothing.

**Assign the assets, one at a time.** Still on the system user, **Add Assets** → assign each of: the **ad account** (Manage campaigns), the **Page** (Manage Page or at least Create ads), the **pixel/dataset**, the **product catalog**. This is the step that is almost always the cause of a 403 on one resource while everything else works — a token that lists campaigns fine will fail on `page list` if the Page was never assigned.

**Add the system user as an App Admin** in Meta for Developers, on the app whose ID the token will be issued against.

**Generate the token** — back on the system user, **Generate New Token**, pick the app, and grant:

| Scope | What breaks without it |
|---|---|
| `ads_management` | every create/update/delete on campaigns, ad sets, ads, creatives |
| `ads_read` | `insights get`, and reading campaign/ad set/ad structure |
| `business_management` | `adaccount list`, dataset and catalog ownership, anything business-scoped |
| `pages_show_list` | `page list` — and therefore finding the `--page-id` a creative needs |
| `pages_read_engagement` | boosting an existing Page post (`--object-story-id`) |
| `pages_manage_ads` | creating ads that use the Page as their identity |
| `catalog_management` | catalogs, product feeds, product sets, product items |
| `read_insights` | the reporting fields beyond the basic delivery metrics |

Copy the token immediately — it is shown once.

**Store it** as `META_ADS_ACCESS_TOKEN`, not `ACCESS_TOKEN`. In `~/.zshenv` (not `~/.zshrc`, which a non-interactive agent shell never sources):

```sh
export META_ADS_ACCESS_TOKEN='EAA...'
```

The CLI's own documented options — an `.env` file with `ACCESS_TOKEN=`, or exporting `ACCESS_TOKEN` globally — are both deliberately unused here: `ACCESS_TOKEN` is generic enough to collide with anything, and `.env` is read from any ancestor directory, which makes the account a write lands on depend on the working directory. `scripts/meta_ads.py` remaps the namespaced variable for the subprocess and blanks the generic ones.

**Verify against the live API:**

```
python3 scripts/meta_ads.py check --account act_123456
```

This is the only real verification. `meta auth status` reports `Authenticated (token: ****)` for any non-empty string, including `bogus`, and exits 0 — it never calls the API.

## Finding the IDs

**Ad account ID** — `python3 scripts/meta_ads.py --account act_x ads adaccount list` once the token works, or Business Settings → Accounts → Ad Accounts. Always `act_` followed by digits; the bare number alone is rejected.

**Business ID** — Business Settings → **Business Info** (`business.facebook.com/settings/info`), or read `business_id=` out of the URL of any Business Suite settings page. With a token: `curl -sG https://graph.facebook.com/v26.0/me/businesses -d fields=id,name -d access_token="$META_ADS_ACCESS_TOKEN"`. The CLI cannot answer this one — `adaccount get`/`list` take no `--fields`, so the account's `business` field is out of reach from there.

`--business` is optional. `catalog` and `dataset` fall back to the ad account when it is absent, and nothing else uses it — so reach for it only when the catalog or pixel is owned by the business rather than the account. When `/me/businesses` returns more than one, the right one is whichever owns the `--account` in play, not the first in the list.

**Page ID** — `ads page list`, which needs `pages_show_list` on the token and the Page assigned to the system user. A creative needs it for `--page-id`.

**Pixel / dataset ID** — `ads dataset list`, or Events Manager → Data Sources.

## 2. Hosted MCP server: browser OAuth

Nothing to create and nothing to export. The plugin ships the server declaration; the first tool call (or `/mcp`) opens Meta's consent screen in a browser.

Verified metadata, fetched from the live endpoint:

| | |
|---|---|
| MCP endpoint | `https://mcp.facebook.com/ads` (Streamable HTTP) |
| Protected resource metadata | `https://mcp.facebook.com/.well-known/oauth-protected-resource/ads` |
| Authorization server metadata | `https://mcp.facebook.com/.well-known/oauth-authorization-server/ads` |
| Issuer | `https://www.facebook.com` |
| Authorize | `https://www.facebook.com/v26.0/dialog/oauth` |
| Token | `https://graph.facebook.com/v26.0/oauth/access_token` |
| Grants | `authorization_code`, `refresh_token` |
| PKCE | `S256` (required) |
| Client auth | `none` — public client |
| Dynamic client registration | `https://mcp.facebook.com/.well-known/register/ads` |

Because the client registers dynamically and authenticates with no secret, there is no Meta app to create for this path and no client ID to configure — which is the main reason to prefer it for interactive work.

The Facebook account doing the OAuth still needs the underlying Business Manager permissions on the ad account. OAuth grants the *scopes*; it does not grant *asset access*.

## Diagnosing a token in one call

When a token authenticates but sees nothing, `debug_token` answers why faster than any amount of clicking. A system user token can inspect itself:

```
curl -sG https://graph.facebook.com/v26.0/debug_token \
  -d input_token="$META_ADS_ACCESS_TOKEN" \
  -d access_token="$META_ADS_ACCESS_TOKEN" | python3 -m json.tool
```

Read three things in the response:

- **`scopes`** — the flat list actually granted. A token issued for a different purpose typically shows something minimal like `["ads_management", "public_profile"]`, and every missing scope in the table above becomes a specific failure rather than a general one. `business_management` in particular is what `/me/businesses` needs; without it that call returns `(#100) Missing Permission`, not an empty list.
- **`granular_scopes`** — each scope with the `target_ids` it applies to. **A scope present here with no `target_ids` means the permission was granted but no asset was attached to it.** That is the state that makes `/me/adaccounts` return `{"data": []}` while the token is perfectly valid — the fix is assigning the asset, not reissuing the token.
- **`is_valid` and `expires_at`** — `expires_at: 0` is correct for a system user token and means it does not expire. A personal token shows a real timestamp, which is the tell that the wrong kind of token is in use.

`GET /me?fields=id,name` alongside it names the identity the token belongs to, which is how you catch a token that works but belongs to a system user created for something else entirely.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Error: API error (190): Invalid OAuth access token` | the token is malformed, expired, or revoked — regenerate it |
| `Error: API error (190)` with a subcode about a changed password | a *personal* token was used; system user tokens are what survive this |
| `Authenticated (token: ****)` but every call 190s | `auth status` only checked that a string exists — see above |
| `Not authenticated` and exit code 0 | nothing configured at all; the CLI does not treat this as a failure |
| 403 on one resource only | that asset was never assigned to the system user (step: Assign the assets) |
| `Error: No ad account configured` | reached the CLI without an account — pass `--account act_...` |
| Writes succeed but land somewhere unexpected | an `.env` up the tree supplied a different `AD_ACCOUNT_ID`; the wrapper prints the file it ignored |
| MCP tools absent from the tool list | the plugin was enabled mid-session — restart the session |
| MCP 403 `insufficient_scope` | the scope set in `plugins/meta-ads/.mcp.json` is narrower than the tool needs |
