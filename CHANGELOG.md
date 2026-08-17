# Changelog

Notable changes to plugins in this marketplace, grouped by plugin. Versions follow [Semantic Versioning](https://semver.org/) and match each plugin's `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` `version` field.

## ga4

### 1.0.1 — 2026-08-17

- Fixed via a blind zero-context subagent smoke test (a real natural-language traffic question, no mention of the skill, tools, or that it was a test) run immediately after 1.0.0 shipped:
  - `reference/api.md` never stated that `dimensions`/`metrics` are plain string arrays (`["date", "activeUsers"]`) — the doc's own "snake_case, not camelCase" framing actively implied the REST API's `[{"name": "..."}]` object shape was right, just differently cased. The blind test hit exactly this: `Input validation error: {'name': 'sessions'} is not of type 'string'`. Now documented with an explicit example.
  - `SKILL.md` described `.mcp.json` as "bundled here," read naturally as the skill directory — it actually lives one level up, at the plugin root (`plugins/ga4/.mcp.json`). Fixed to say so explicitly.
- Added `scripts/mcp_client.py` — a single-call stdio JSON-RPC fallback for driving `analytics-mcp` directly when the plugin's registered MCP tools aren't in the current tool list (MCP servers load once at session start, so a plugin installed mid-session — or a subagent spawned from a session that predates the install — won't see them until a fresh session starts, even though `claude mcp list` reports the server `Connected` at the config level). Documents a real gotcha found live: the server exits on stdin EOF before a `tools/call` reply completes its network round trip, which reads as a silent hang rather than an error unless stdin is held open until the response is read.
- Confirmed real end-to-end plugin behavior beyond the earlier manual testing: `claude plugin install ga4@nadiar-skills` from a shell registers `plugin:ga4:analytics-mcp` and `claude mcp list` reports it `Connected` — the `.mcp.json` bundling genuinely works, distinct from the `gtm`/`gsc` skills-dir-symlink-only approach (neither of which is formally plugin-installed on this machine, confirmed via `claude plugin list`)
- Confirmed against the real `goldypaper.com` property (created same day, `create_time: 2026-08-17T05:10:38Z`): zero traffic on every report shape (30-day, all-time, realtime) is a genuine finding — the site has no tracking snippet installed yet, not an auth/API problem, corroborated by `get_property_details` returning full metadata rather than a 403

### 1.0.0 — 2026-08-17

- Initial release: query Google Analytics 4 reporting data — account/property discovery, custom dimensions/metrics, Google Ads links, property annotations, and four report tools (`run_report`, `run_realtime_report`, `run_funnel_report`, `run_conversions_report`) — via Google's own official `analytics-mcp` server (PyPI: `analytics-mcp`), not a custom script like `gtm`/`gsc`
- Bundled as a real MCP server declaration (`plugins/ga4/.mcp.json`), not wrapped — the first plugin in this marketplace to ship an MCP server instead of a stdlib script. Auth env vars are deliberately named `GA_SERVICE_ACCOUNT_KEY`/`GA_PROJECT_ID` rather than `GOOGLE_APPLICATION_CREDENTIALS`/`GOOGLE_PROJECT_ID` (what `analytics-mcp` actually reads) — those generic names are also load-bearing for `gcloud`, Terraform/OpenTofu, and other tools on the same machine, so `.mcp.json` remaps the scoped names to the generic ones only inside the `analytics-mcp` subprocess's own environment
- Verified end-to-end by speaking the real MCP stdio protocol (newline-delimited JSON-RPC, no `Content-Length` framing) to `pipx run analytics-mcp` directly: `initialize`, the live `tools/list` (9 tools — the upstream README documents only 7, missing `list_property_annotations` and `run_conversions_report`), and a live `run_report` call against the real `goldypaper.com` property
- Confirmed live: pointing `GOOGLE_APPLICATION_CREDENTIALS` straight at a service-account key file works as ADC and needs no `gcloud` login — simpler than either of the two `gcloud`-based flows the upstream README documents, and doesn't overwrite the shared `~/.config/gcloud/application_default_credentials.json` the way both of those do
- Caught a live trap in the alternative OAuth-desktop-client auth flow before it shipped as guidance: an unverified OAuth client's consent screen rejects any Google account not on its Test users list with `Error 403: access_denied`, even with a correct `--client-id-file`/`--scopes` invocation — documented in `reference/api.md` as a reason to default to the service-account path instead
- Confirmed the Data API's field names in this MCP server are snake_case (protobuf-derived), not the camelCase the public REST reference docs show — copying a camelCase example verbatim silently mismatches the schema rather than erroring
- Confirmed `run_report`'s empty-result shape always includes a `rows: []` key (never omits it), the opposite convention from `gsc`'s `analytics query` — both documented as legitimate "no data yet" findings, not failures
- `reference/api.md` — auth flow (all three ADC options, ranked), API enablement, full 9-tool catalog, `date_ranges`/filter-expression/`order_bys` shapes, `run_conversions_report`'s fixed dimension/metric allowlist, `run_funnel_report`'s step shape, and the live empty-result example
- No audit log — every tool in this skill is read-only, unlike `gtm` (publish) and `gsc` (sitemap submit/delete)

## gsc

### 1.0.0 — 2026-08-17

- Initial release: read Google Search Console data — search performance (`analytics query`), per-URL indexing status (`inspect url`) — and manage sitemaps (`sitemaps list/get/submit/delete`), via the Search Console API v1
- `scripts/gsc.py` — stdlib Python except for `google-auth`, reusing the exact same service-account auth pattern (and the same `GTM_SERVICE_ACCOUNT_KEY`) as `gtm`, against the single `webmasters` OAuth scope (the readonly scope can't submit/delete sitemaps, so this skill's "read + sitemap management" scope needs the full one regardless)
- Deliberately narrower than `gtm`: no `sites.add`/`sites.delete` — this skill never registers or removes properties from the account, only reads/writes within properties already there
- Path/method table and request/response shapes built from the live discovery document (`googleapis.com/discovery/v1/apis/searchconsole/v1/rest`) and verified against the real `sc-domain:goldypaper.com` property: `sites.list`, `searchanalytics.query` (empty-range response has no `rows` key at all), and `urlInspection.index.inspect` (`coverageState: "URL is unknown to Google"` is the normal shape for a never-crawled URL, not an error) all confirmed live
- Caught the discovery doc's one stale entry before it shipped: `urlTestingTools.mobileFriendlyTest.run` is still listed but the live endpoint 400s on every URL including a known-good one (`google.com`) — Google retired the tool without pruning the schema. This skill does not wrap it; `reference/api.md` documents the finding
- Confirmed `type` (not the deprecated `searchType`) is the correct search-type filter field per Google's own current reference docs
- Every `sitemaps submit`/`delete` appended to a gitignored `.gsc-audit.jsonl` at the repo root
- `SKILL.md` treats empty results (no data in range, no sitemaps, unindexed URL) as real findings to report, not failures to retry — and calls out that domain (`sc-domain:`) and URL-prefix (`https://`) forms of the same site are different properties that 404 identically when confused

## gtm

### 1.0.0 — 2026-08-17

- Initial release: read/write Google Tag Manager configuration via the Tag Manager API v2 — accounts, containers, workspaces, tags, triggers, variables — plus container version create/publish
- `scripts/gtm.py` — stdlib Python except for `google-auth`, used only to RS256-sign the service account's JWT-bearer assertion; every Tag Manager API call itself goes over stdlib `urllib`. Verified against Google's real token endpoint (a syntactically-valid signed JWT from a throwaway key gets `invalid_grant: account not found`, not a signature error, confirming the request shape) and against a live container end to end (`containers get`, `workspaces status`, `tags/triggers/variables list`)
- `--account`/`--container`/`--workspace` fall back to `GTM_ACCOUNT_ID`/`GTM_CONTAINER_ID`/`GTM_WORKSPACE_ID` when set, staying required flags otherwise — so a fixed property never needs its ID typed (or hardcoded) into a command; tag/trigger/variable/version IDs stay always-explicit since they're per-entity
- Path/method table built from the live discovery document (`googleapis.com/discovery/v1/apis/tagmanager/v2/rest`) rather than the HTML docs, including the `tagmanager.googleapis.com` (not `www.googleapis.com`) base URL and the `:create_version`/`:publish` colon-verb path shapes
- `reference/api.md` — auth flow, full path/method table, Tag/Trigger/Variable/Parameter shapes, a caveat that GTM publishes no enum of valid `type` strings (documents the reliable workaround: `get` an existing entity of the same kind and use it as the template), error-code meanings
- Every create/update/delete/publish appended to a gitignored `.gtm-audit.jsonl` at the repo root
- `SKILL.md` treats `version publish` as the one irreversible-in-practice action: workflow requires showing `workspaces status` and the created version before ever calling publish, and forbids chaining create → publish without an explicit per-publish confirmation

## qwen-image

### 1.0.0 — 2026-08-06

- Initial release: image generation and editing against Alibaba Cloud Model Studio's Qwen-Image family (`qwen-image-3.0-pro`, `qwen-image-2.0-pro`, `qwen-image-2.0`, `qwen-image-max`, `qwen-image-plus`, `qwen-image`, `qwen-image-edit-max`, `qwen-image-edit-plus`, `qwen-image-edit`) via the synchronous `multimodal-generation/generation` endpoint
- `scripts/qwenimage.py` — stdlib-only Python, no `pip install`; `generate`/`edit`, up to 3 input images fused per edit, variants via `--n` returned in a single request, never overwrites an existing output, appends every render to a gitignored `.qwenimage.jsonl` with the full prompt, parameters and `request_id`
- Per-model limits validated locally before any request is sent, so a wrong model/size/`n` combination costs nothing; automatic backoff on `Throttling.RateQuota`, which Model Studio workspaces hit easily
- `reference/prompting.md` — checklist, templates and failure modes written around Qwen's own behaviour: the server-side `prompt_extend` rewriter, the real `--negative-prompt` parameter, `--seed` iteration, and CJK text rendering
- `reference/api.md` — endpoints, per-model size/`n` matrix, request/response shapes and error codes, flagging where the published docs disagree with the live API
- Positioned as the alternative to `nano-banana`: triggers on Qwen/Model Studio/DashScope by name, on a rejected nano-banana render, on in-image text (especially Chinese/Japanese/Korean), and on outputs above 2048px per side
- Verified against the live Singapore endpoint: `size` is `width*height` (confirmed by reading the PNG header), output is 8-bit RGB PNG with no alpha, `usage` returns `output_width`/`output_height`/`output_image_count` rather than the documented `width`/`height`/`image_count`, `qwen-image-3.0-pro` accepts area up to 2560² rather than the documented 2048², and `qwen-image-edit` silently ignores an out-of-range `n` — billing every requested render while returning one image

## nano-banana

### 1.0.0 — 2026-08-01

- Initial release: image generation, editing, and multi-image composition against Google's Gemini image models (`gemini-3.1-flash-lite-image`, `gemini-3.1-flash-image`, `gemini-3-pro-image`) via the `v1beta/interactions` endpoint
- `scripts/nanobanana.py` — stdlib-only Python, no `pip install`; `generate`/`edit`/`compose`, variants via `--n`, never overwrites an existing output, appends every render to a gitignored `.nanobanana.jsonl` with the full prompt and cost
- `reference/prompting.md` — prompt-writing checklist, principles, and templates for heroes, og:images, icons, mockups, textures, avatars, and in-image text, plus editing patterns and a failure-mode table
- `reference/api.md` — models, sizes, aspect ratios, request/response shapes, pricing, error codes, and a list of four points where Google's published docs disagree with the live API
- Retina-driven size routing and text-aware model routing baked into `SKILL.md`; image bytes are kept on disk and never routed through the agent's context
- Costs are computed from the `usage` block the API returns rather than a static price table, so `--thinking high` and `--grounding` are reflected in the reported price
- Verified against the live API: output is JPEG-only on every model (no PNG, no alpha), sizes are `512`/`1K`/`2K`/`4K` rather than the documented `512px`, and `lite` rejects 2K and 4K

## superglue

### 1.1.0 — 2026-07-13

- Add Codex plugin manifest (`plugins/superglue/.codex-plugin/plugin.json`)
- Add native Codex marketplace manifest (`.agents/plugins/marketplace.json`) at the repo root, so `codex plugin marketplace add` / `codex plugin add` resolve directly instead of falling back to Claude's manifest
- Verified clean install via both `claude plugin install superglue@nadiar-skills` and `codex plugin add superglue@nadiar-skills`

### 1.0.0 — 2026-07-13

- Initial release: Superglue 2.0 (thoughtbot's Rails+React+Redux framework, v2/beta) reference skill — navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, deferments, decision guide, and a v1-to-v2 migration cheat sheet
- Published as the first plugin in the `nadiar-skills` Claude Code marketplace
- Validated with skill-creator's eval loop: 100% vs 45% pass rate against a no-skill baseline across 4 test cases (`plugins/superglue/skills/superglue/evals/evals.json`)
