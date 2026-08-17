# Tag Manager API v2 reference

Ground truth pulled from Google's live discovery document
(`https://www.googleapis.com/discovery/v1/apis/tagmanager/v2/rest`), not from
the HTML docs — the discovery doc is what the API actually enforces.

## Auth

Service-account JWT-bearer flow, no user consent screen — see `access_token()`
in `gtm.py` for the exact request shape. Scopes in use:
`tagmanager.edit.containers` (read/write config) and `tagmanager.publish`
(create/publish versions). `google-auth`'s `google.auth.crypt.RSASigner` +
`google.auth.jwt.encode` do the signing — verified against the real token
endpoint (a syntactically-valid JWT signed with a throwaway key gets
`invalid_grant: account not found` back, not a signature error, confirming
the request shape is correct).

## Base URL and path shape

`https://tagmanager.googleapis.com/tagmanager/v2/` (not the commonly-guessed
`www.googleapis.com`) + a resource path built from IDs — there is no separate
`accountId=`/`containerId=` query-param style; the hierarchy is baked into
the path itself (see the method table below for the full shape). Custom
"verb" methods append a colon directly to the resource path, no slash:
`.../workspaces/{id}:create_version`, `.../workspaces/{id}/status` (this one's
an actual sub-path, not a colon verb), `.../versions/{id}:publish`.

## Method table (the subset this skill wraps)

| Command | HTTP | Path |
|---|---|---|
| `accounts list` | GET | `accounts` |
| `containers list` | GET | `accounts/{a}/containers` |
| `containers get` | GET | `accounts/{a}/containers/{c}` |
| `workspaces list` | GET | `.../containers/{c}/workspaces` |
| `workspaces get` | GET | `.../workspaces/{w}` |
| `workspaces status` | GET | `.../workspaces/{w}/status` |
| `{tags,triggers,variables} list` | GET | `.../workspaces/{w}/{kind}` |
| `{tags,triggers,variables} get` | GET | `.../workspaces/{w}/{kind}/{id}` |
| `{tags,triggers,variables} create` | POST | `.../workspaces/{w}/{kind}` |
| `{tags,triggers,variables} update` | PUT | `.../workspaces/{w}/{kind}/{id}` (+`?fingerprint=`) |
| `{tags,triggers,variables} delete` | DELETE | `.../workspaces/{w}/{kind}/{id}` |
| `version create` | POST | `.../workspaces/{w}:create_version` |
| `version get` | GET | `accounts/{a}/containers/{c}/versions/{v}` |
| `version publish` | POST | `.../versions/{v}:publish` (+`?fingerprint=`) |

`fingerprint` on update/publish is optional optimistic-concurrency: pass the
value from a prior `get`/`create` response and the API 409s if the entity
changed since; omit it and the write always applies (last write wins).

## Tag / Trigger / Variable shape

All three share the same skeleton — `name`, `type`, `parameter` (array), plus
IDs the API fills in on create. `accountId`/`containerId`/`workspaceId` in the
body are optional on create (derived from the URL path) but required (and
must match) on update.

`parameter` entries:

```json
{"type": "template", "key": "someField", "value": "literal or {{Variable Reference}}"}
{"type": "boolean",  "key": "someFlag",  "value": "true"}
{"type": "list", "key": "someList", "list": [{"type": "template", "value": "a"}]}
{"type": "map",  "key": "someMap",  "map": [{"type": "template", "key": "k", "value": "v"}]}
```

**There is no published enum of valid `type`/`parameter` combinations per tag
or trigger kind** — the discovery schema leaves `type` as a plain string.
The reliable way to build a new tag/trigger/variable is: find an existing one
of the same kind (in this container, a sibling container, or the GTM UI's
"Export container" JSON), `get` it, and use its `type` and `parameter` keys
as the template. Do not invent a `parameter` key name from guessing.

Tag `type` strings confirmed in public GTM documentation and community use —
useful as a starting point, not exhaustive:

| `type` | Tag |
|---|---|
| `html` | Custom HTML |
| `img` | Custom Image |
| `sp` | Custom Script |
| `gaawc` | Google Analytics: GA4 Configuration |
| `gaawe` | Google Analytics: GA4 Event |
| `ua` | Google Analytics: Universal Analytics (legacy) |
| `awct` | Google Ads Conversion Tracking |
| `flc` | Floodlight Counter |

Trigger `type` strings likewise unpublished as an enum; common ones seen in
practice: `pageview`, `domReady`, `windowLoaded`, `click`, `linkClick`,
`formSubmission`, `customEvent`, `timer`, `historyChange`.

### Example: minimal Custom HTML tag body

```json
{
  "name": "My Custom HTML Tag",
  "type": "html",
  "parameter": [
    {"type": "template", "key": "html", "value": "<script>console.log('hi')</script>"},
    {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}
  ],
  "firingTriggerId": ["2147479553"]
}
```

`firingTriggerId` is a list of trigger IDs (as strings) — `2147479553` is
GTM's built-in "All Pages" trigger, present in every container.

## `version create` request body

`CreateContainerVersionRequestVersionOptions`: `{"name": "...", "notes":
"..."}` (both optional, but always pass `name` — an unnamed version is hard
to identify later in the GTM UI's version history).

## Errors

| HTTP | Meaning here |
|---|---|
| 400 | malformed body — usually a `parameter` shape the tag/trigger type doesn't accept |
| 401 | access token invalid/expired — a fresh `access_token()` call gets a new one automatically |
| 403 | service account has no permission on this account/container — check GTM User Management, not IAM |
| 404 | wrong ID, or the service account can't see this resource at all (403 and 404 look the same for a resource you have zero access to — GTM doesn't leak existence) |
| 409 | fingerprint mismatch on update/publish — re-`get` and retry with the current value or omit `--fingerprint` |
