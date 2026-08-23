# nadiar-skills

Personal skills marketplace, one plugin per skill. Each plugin ships both a **Claude Code** manifest (`.claude-plugin/plugin.json`) and a **Codex** manifest (`.codex-plugin/plugin.json`) pointing at the same underlying `skills/<name>/SKILL.md`, so the skill content is written once and works in either tool.

## Install — Claude Code

Requires [Claude Code](https://claude.com/code).

**Inside a Claude Code session:**

```
/plugin marketplace add codxse/nadiar-skills
/plugin install superglue@nadiar-skills
/plugin install nano-banana@nadiar-skills
/plugin install qwen-image@nadiar-skills
/plugin install gtm@nadiar-skills
/plugin install gsc@nadiar-skills
/plugin install ga4@nadiar-skills
/plugin install meta-ads@nadiar-skills
```

**From a shell** (equivalent, e.g. for scripting/dotfiles):

```
claude plugin marketplace add codxse/nadiar-skills
claude plugin install superglue@nadiar-skills
```

Restart Claude Code (or start a new session) so the plugin loads. Verify it's installed:

```
/plugin
# or: claude plugin list
```

**Updating**, once this repo gets new commits:

```
/plugin marketplace update nadiar-skills
/plugin update superglue
```

**Uninstalling:**

```
/plugin uninstall superglue
/plugin marketplace remove nadiar-skills
```

## Install — Codex

Requires the [Codex CLI](https://github.com/openai/codex). It reads the same `.claude-plugin/marketplace.json` this repo already has, so the flow is a straight parallel to the Claude Code one — verified working with `codex-cli 0.144.1`:

```
codex plugin marketplace add codxse/nadiar-skills
codex plugin add superglue@nadiar-skills
```

Verify:

```
codex plugin list
```

**Updating / removing:**

```
codex plugin marketplace upgrade nadiar-skills
codex plugin remove superglue@nadiar-skills
```

**Alternative** for repo-scoped use without going through a marketplace at all: Codex also scans plain `.agents/skills` directories (repo-local) and `~/.agents/skills` (every repo). Copying `plugins/superglue/skills/superglue/` in there works too, since `SKILL.md`'s `name`/`description` frontmatter is the same format Claude Code uses.

Each plugin also carries a dedicated `.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) matching Codex's own manifest schema, for the formal, reviewed [Codex plugin directory](https://learn.chatgpt.com/codex/submit-plugins) path if it's ever worth submitting there — see [Build plugins](https://learn.chatgpt.com/codex/build-plugins). That submission flow (OpenAI org verification, review) is separate and not done as part of this repo.

## Plugins

### `superglue`

Reference skill for [Superglue 2.0](https://github.com/thoughtbot/superglue) (thoughtbot's Rails+React+Redux framework, v2/beta). Triggers when a project uses the `superglue` gem, `.json.props` files, `data-sg-visit`/`data-sg-remote`, or Superglue is mentioned directly. Covers navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, and deferments — plus a decision guide for which primitive to reach for and a v1→v2 migration cheat sheet, since 2.0 is a breaking rewrite of 1.x.

Source: `plugins/superglue/skills/superglue/`. Includes `evals/` with the test prompts and assertions used to validate it (100% vs 45% pass rate against a no-skill baseline across 4 test cases — see `evals/evals.json`).

### `nano-banana`

Generate, edit, and compose images with Google's [Gemini image models](https://ai.google.dev/gemini-api/docs/image-generation) — Nano Banana and Nano Banana Pro — and land the file directly in your workspace. Triggers on any mid-task need for a raster asset: hero images, og:image cards, icons, avatars, textures, product mockups, placeholder art, or editing an image already on disk.

The point is that you don't write the prompt. "I need a hero image for the pricing page" is enough; the skill expands it into a fully specified prompt, picks the model (Pro when the image contains text, Flash otherwise) and the resolution (retina-aware — 4K for heroes, 2K for content images), renders, checks the result, and writes it to a path you confirm.

**Requirements:**

- `GEMINI_API_KEY` exported — get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). On zsh put it in **`~/.zshenv`, not `~/.zshrc`**: zsh only reads `.zshrc` for interactive shells, so a key exported there is invisible to the non-interactive shell your coding agent actually runs commands in.
- **Billing enabled on that key's project.** The image models have no free tier; an unbilled key fails with HTTP 429 on the very first call. This is the one thing that makes it look broken.
- `python3` (3.8+). The bundled script is stdlib-only — nothing to `pip install`.
- ImageMagick, optionally — the API only ever returns JPEG, so PNGs and cut-outs need one conversion step afterwards.

Renders cost roughly $0.03–0.24 each depending on model and resolution; the script bills from the token usage the API reports, prints the cost of every call, and appends a full record — prompt, parameters, price — to a gitignored `.nanobanana.jsonl` at your repo root, so a later "same but warmer lighting" is a real edit rather than a reroll.

Source: `plugins/nano-banana/skills/nano-banana/`.

### `qwen-image`

The same job as `nano-banana`, against Alibaba Cloud [Model Studio](https://modelstudio.console.alibabacloud.com/)'s Qwen-Image family instead of Gemini. It exists so there is a second opinion available when a render gets rejected — and because Qwen is meaningfully better at two things: **legible text inside the image**, including Chinese, Japanese and Korean, and **large outputs**, up to roughly 2560×2560 on `qwen-image-3.0-pro`.

Triggers on Qwen / Model Studio / DashScope / Aliyun by name, on "try that again with something else" after a nano-banana render, on in-image typography, and on editing or fusing up to three images already on disk.

**Requirements:**

- `QWEN_API_KEY` and `QWEN_API_HOST` exported. Both come from the Model Studio console; the host is your workspace's dedicated endpoint, e.g. `ws-xxxxxxxxxxxx.ap-southeast-1.maas.aliyuncs.com`. Same zsh caveat as above — **`~/.zshenv`, not `~/.zshrc`**.
- **Region matters.** Singapore (`ap-southeast-1`) and Beijing (`cn-beijing`) issue separate keys against separate hosts and cannot be mixed; a Beijing key on a Singapore host fails with `InvalidApiKey`.
- `python3` (3.9+). Stdlib-only script — nothing to `pip install`.
- ImageMagick, optionally — output is PNG but 8-bit RGB with no alpha, so cut-outs need one keying step afterwards.

Renders are billed per image at a tier the script prints and logs (`qima_output_1k`, `qima_output_2k`, …); per-image prices aren't published in the docs, so check the console for the current rate. Failed calls are free, and the script validates model, size and `--n` locally before spending a request. Every render is appended to a gitignored `.qwenimage.jsonl` at your repo root with the full prompt and parameters.

Source: `plugins/qwen-image/skills/qwen-image/`. Includes `evals/` with the test prompts and assertions used to validate it.

### `gtm`

Read and write [Google Tag Manager](https://tagmanager.google.com) configuration via the Tag Manager API v2 — accounts, containers, workspaces, tags, triggers, variables — and publish container versions. Triggers on any request to inspect, audit, create, or edit a GTM tag/trigger/variable, check what changed in a workspace, or publish a container.

The point is the safety boundary: every mutating call is logged to a gitignored `.gtm-audit.jsonl` at the repo root, and creating a container version never auto-publishes — the skill always shows what's about to ship and waits for an explicit yes before the one command (`version publish`) that actually goes live.

**Requirements:**

- `GTM_SERVICE_ACCOUNT_KEY` exported, pointing at a service account JSON key from Google Cloud Console. The same service account must be added as a user inside the GTM container itself (Admin → User Management, **Publish** permission) — a GCP IAM role alone grants nothing there.
- `pip install google-auth` once — used only to RS256-sign the service account's JWT; every actual API call goes over stdlib `urllib`.
- Tag Manager API enabled on the service account's GCP project.
- No env var for account/container/workspace, deliberately — those flags are required on every command that takes them. An ID identifies one site, so it belongs to the task, not to the machine: exported globally it would follow you into every unrelated project and let `version publish` ship to a container the command never named.

Source: `plugins/gtm/skills/gtm/`.

### `gsc`

Read [Google Search Console](https://search.google.com/search-console) data — search performance (clicks, impressions, CTR, position by query/page/date/country/device), per-URL indexing status — and manage sitemaps, via the Search Console API v1. Triggers on any question about search traffic, rankings, top queries/pages, why a URL isn't indexed, or resubmitting a sitemap after publishing content.

Narrower than `gtm` by design: search performance and indexing status are read-only, and the only writes are `sitemaps submit`/`delete` — this skill doesn't register or remove properties from the account. Every sitemap change is logged to a gitignored `.gsc-audit.jsonl` at the repo root.

**Requirements:**

- `GTM_SERVICE_ACCOUNT_KEY` exported — reuses the exact same service account key as `gtm`. That service account must additionally be added as a user inside Search Console itself (Settings → Users and permissions, **Full** permission — Restricted can't submit/delete sitemaps) — a GCP IAM role alone grants nothing there, same as GTM.
- `pip install google-auth` once — already installed if `gtm` is set up.
- Search Console API enabled on the service account's GCP project.
- No env var for the site, deliberately — `--site` is required on every command that takes it, for the same reason as `gtm`'s IDs. Note a domain property (`sc-domain:example.com`) and a URL-prefix property (`https://example.com/`) are different properties, not interchangeable.

Source: `plugins/gsc/skills/gsc/`.

### `ga4`

[Google Analytics 4](https://analytics.google.com): query reporting data — traffic, sessions, events, conversions, funnels, realtime activity, custom dimensions/metrics — via Google's own official [`analytics-mcp`](https://github.com/googleanalytics/google-analytics-mcp) server, and manage property configuration — custom dimensions/metrics, key events (conversions), data streams — via the Analytics Admin API. Triggers on any question about site traffic, users, top pages/events, conversion or ROAS numbers, a funnel, what's happening on the site right now, or marking an event as a conversion.

Two paths, structurally different from each other and from `gtm`/`gsc`. Reporting has no custom script: `analytics-mcp` is a real MCP server, bundled via `plugins/ga4/.mcp.json` — once the plugin is enabled its 9 tools (`get_account_summaries`, `run_report`, `run_realtime_report`, `run_funnel_report`, `run_conversions_report`, and others) are just available directly, and every one of them is read-only. Configuration writes go through `scripts/ga4_admin.py` instead, a custom script against the Admin API v1beta — `analytics-mcp` has no write tool at all, so this is the only way to create a custom dimension/metric, mark an event as a key event (conversion), or manage a data stream. Every write there is logged to a gitignored `.ga4-audit.jsonl` at the repo root, same pattern as `gtm`/`gsc`.

**Requirements:**

- `GA_SERVICE_ACCOUNT_KEY` and `GA_PROJECT_ID` exported — reuses the same service account key as `gtm`/`gsc`, plus the GCP project ID for API quota. Deliberately *not* named `GOOGLE_APPLICATION_CREDENTIALS`/`GOOGLE_PROJECT_ID` (what `analytics-mcp` itself needs) — those generic names are also read by `gcloud`, Terraform/OpenTofu, and other tools, so `.mcp.json` remaps the scoped names to the generic ones only for the `analytics-mcp` subprocess. Same zsh caveat as the other skills — **`~/.zshenv`, not `~/.zshrc`**.
- That service account must additionally be added inside the GA4 property itself (Admin → Property Access Management) — a GCP IAM role alone grants nothing there, same as `gtm`/`gsc`. **Viewer** covers the reporting tools; **Editor or above** is required for `ga4_admin.py`'s writes.
- No env var for the property, deliberately — `ga4_admin.py --property` is required on every call, and the reporting tools take `property_id` as a call argument. `GA_PROJECT_ID` above is the exception: it names the GCP project billed for API quota, which travels with the key rather than with any GA4 property.
- Google Analytics **Admin** API and **Data** API enabled on the service account's GCP project.
- `pipx` installed — `analytics-mcp` runs via `pipx run analytics-mcp`, cached after the first launch. `pip install google-auth` once for `ga4_admin.py` — already done if `gtm`/`gsc` are set up.

Source: `plugins/ga4/skills/ga4/`.

### `meta-ads`

[Meta Ads](https://business.facebook.com): manage Facebook/Instagram advertising — campaigns, ad sets, ads, creatives, performance insights, product catalogs and feeds, datasets (pixels), A/B and lift studies — through Meta's own two [ads AI connectors](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/). Triggers on any question about Meta ad spend, ROAS, CPC/CPM/CTR, a campaign or ad set, creating or pausing an ad, a budget change, a product feed, or pixel/signal health.

Two paths, deliberately kept side by side. The **hosted MCP server** at `https://mcp.facebook.com/ads` is bundled via `plugins/meta-ads/.mcp.json` — Meta runs it, browser OAuth with PKCE and dynamic client registration means there is no Meta app, no client ID and no token to manage, and it exposes **98 tools** (counted live, against the 29 published write-ups claim), several of them features the CLI has no command for at all: custom audiences, pixel event and parameter configuration, writable A/B and lift tests, ad preview, delivery-error lookup, Ads Library competitor search, activity logs, benchmarks and opportunity score. The **[ads-cli](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/setup/get-started)** (`meta`, PyPI [`meta-ads`](https://pypi.org/project/meta-ads/)) covers the other direction: 72 commands with the full Marketing API flag surface — DCO asset feeds, raw targeting JSON, EU DSA fields, `--fields` as an escape hatch — which makes it the path for anything batched or flag-specific.

The CLI is never called directly. `scripts/meta_ads.py` wraps it to fix four things verified live against v1.1.0: `meta auth status` reports `Authenticated` for any non-empty string and exits 0 without ever calling the API (`meta_ads.py check` calls it); a `.env` in *any* ancestor directory is read automatically, so the account a write lands on could depend on the working directory; `ACCESS_TOKEN` is too generic a name to export globally, so the wrapper reads `META_ADS_ACCESS_TOKEN` and remaps it for the subprocess only; and `auth status` with nothing configured exits 0. Every mutating CLI invocation is logged to a gitignored `.meta-ads-audit.jsonl` at the repo root, same pattern as `gtm`/`gsc`/`ga4` — writes made through the MCP tools are not, and Meta's own account activity log is the trail for those.

**Requirements:**

- `META_ADS_ACCESS_TOKEN` exported — a Meta **system user** access token (Business Suite → Settings → Users → System Users), with `ads_management`, `ads_read`, `business_management`, `pages_show_list`, `pages_read_engagement`, `pages_manage_ads`, `catalog_management`, `read_insights`. Same zsh caveat as the other skills — **`~/.zshenv`, not `~/.zshrc`**. Needed for the CLI path only; the hosted MCP server needs nothing exported.
- Each asset assigned to that system user individually inside Business Manager — the ad account, the Page, the pixel, the catalog. Business-admin role alone grants none of it, so a token that lists campaigns can still 403 on a Page.
- No env var for the ad account, deliberately — `--account act_...` is required on every account-scoped call. An ad account is one advertiser's money; exported globally it would follow you into every unrelated project and let a budget change land on an account the command never named.
- `uv` installed — the wrapper runs `uvx --from meta-ads meta` when `meta` isn't on `PATH`, cached after the first launch. `pip install meta-ads` works too, as does `META_ADS_CLI` pointing at any command. **Python 3.12+** either way.

Source: `plugins/meta-ads/skills/meta-ads/`.

## Adding a new skill

1. `mkdir -p plugins/<name>/skills/<name>` and put the skill there (`SKILL.md` + any `reference/`/`scripts/`/`assets/`).
2. Add a `plugins/<name>/.claude-plugin/plugin.json` (see `plugins/superglue/.claude-plugin/plugin.json` for the shape).
3. Add an entry to `.claude-plugin/marketplace.json`'s `plugins` array, `"source": "./plugins/<name>"`.
4. Add a `plugins/<name>/.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) with `"skills": "./skills/"` so Codex resolves the same skill folder.
