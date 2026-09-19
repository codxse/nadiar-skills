# X API v2 reference

## Auth: OAuth 1.0a user context, not Bearer / OAuth 2.0

This skill signs every request with OAuth 1.0a (`Authorization: OAuth
oauth_consumer_key="...", oauth_signature="...", ...`), using the four
`X_API_KEY` / `X_API_KEY_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET`
env vars. Two other credential types live on the same Keys & Tokens page
and are deliberately not used:

- **App-Only Bearer Token** authenticates as the *app*, not a user — reads
  public data but **cannot post**, since there's no user context to post as.
- **OAuth 2.0 Client ID/Secret + Access Token** is a separate pair for the
  Authorization Code + PKCE login flow (third-party "Sign in with X"). Not
  used here, but the app setup still requires filling in Callback URI /
  Website URL to save its auth settings at all — those fields exist for
  this flow, not the OAuth 1.0a one this skill actually uses.

The signature base string, **per the OAuth 1.0a spec**, is built from the
HTTP method, the URL, and the request's **query-string parameters only** —
a JSON POST body (like `{"text": "..."}` for `tweets post`) is never part
of it. `x_post.py`'s `oauth1_header()` reflects that: it takes `params`
(query string) separately from `body` (JSON), and only `params` feed the
signature.

## Cost (Pay Per Use plan)

No free tier as of this writing — X deprecated it. Pay Per Use, set up via
console.x.com → Projects → Create Project → Credits → Purchase credits, is
credit-based, no subscription, no minimum:

| Action | Cost |
|---|---|
| `POST /2/tweets`, no URL in text | $0.015 |
| `POST /2/tweets`, text contains a URL | $0.200 |
| Read a tweet (per resource returned) | $0.005 |
| Read a user object (per resource returned) | $0.010 |
| Engagement objects (likes/mutes/blocks lists) | $0.001 |

Resources are deduplicated within a 24h UTC window — re-reading the exact
same tweet twice in one day doesn't double-charge. `users tweets --count
20` costs roughly one user-lookup ($0.010) plus 20 tweet reads ($0.005 ×
20 = $0.10), so ≈$0.11 per call.

The alternative, **Basic**, is a $200/month subscription (100
requests/15min per user, 10,000/24h per app for posting).

## Media upload

`POST https://api.x.com/2/media/upload`, multipart/form-data with a `media`
file part plus `media_category` and `media_type` fields. Returns
`{"data": {"id": "...", "media_key": "..."}}`; the `id` is what
`POST /2/tweets` takes as `media.media_ids`.

Two things that differ from the JSON endpoints:

- **The host is `api.x.com`, not `api.twitter.com`** — this is the v2
  endpoint that replaced v1.1's `upload.twitter.com/1.1/media/upload.json`.
- **The multipart body is not part of the OAuth 1.0a signature**, exactly
  like a JSON body — the base string is still method + URL + query params
  only, so the same `oauth1_header()` signs it unchanged.

An uploaded media id is unattached and invisible until a tweet references
it, and expires on its own if none does — which makes `media upload` the
cheapest end-to-end credential check that touches a write path.

Alt text is **not** part of this endpoint. It needs a separate
`POST /1.1/media/metadata/create` call, which this skill does not make.

## Rate limits (Pay Per Use / Basic-equivalent tier)

- `POST /2/tweets`: 100 requests / 15 min per user, 10,000 / 24h per app.
- `GET /2/users/:id/tweets`: 1,500 requests / 15 min per app.
- `DELETE /2/tweets/:id`: 50 requests / 15 min per user.

A 429 on any of these means genuinely wait, not retry immediately.

## Error codes seen in practice

- **401** — invalid/expired Access Token or signature mismatch. Suspect a
  copy-paste error in the consumer secret or access secret env var, not
  the signing code.
- **403 `client-not-enrolled`** — the app's attached Project has no active
  paid plan. See SKILL.md trap 3 (Project Access). The error body includes
  a `registration_url` pointing at developer.x.com docs, which is stale —
  the actual fix is in console.x.com, not that docs page.
- **403** with no `client-not-enrolled` reason, only on `tweets post` while
  reads work — app permission or stale Access Token. See SKILL.md traps 1
  and 2.
- **429** — rate limited, see above.
- **duplicate content** — X silently rejects (`403` with a `duplicate
  content` detail) an exact repeat of a very recent tweet from the same
  account. Not a bug in the skill; vary the text or wait.

## Fields returned

`tweets get`/`users tweets` request `created_at,public_metrics,lang` (and
`author_id` for `tweets get`) via `tweet.fields`. `public_metrics` on a
freshly-posted tweet will show 0s and a low `impression_count` — that's
real, not a bug, impressions take time to accumulate.

`users me`/`users get` request `public_metrics,description,created_at` via
`user.fields`. `public_metrics.tweet_count` doubles as a sanity check that
the right account is authenticated.
