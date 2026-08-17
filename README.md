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
- Optionally `GTM_ACCOUNT_ID`/`GTM_CONTAINER_ID`/`GTM_WORKSPACE_ID` exported for the property used most, so `--account`/`--container`/`--workspace` never need to be typed (or hardcoded) into a command.

Source: `plugins/gtm/skills/gtm/`.

### `gsc`

Read [Google Search Console](https://search.google.com/search-console) data — search performance (clicks, impressions, CTR, position by query/page/date/country/device), per-URL indexing status — and manage sitemaps, via the Search Console API v1. Triggers on any question about search traffic, rankings, top queries/pages, why a URL isn't indexed, or resubmitting a sitemap after publishing content.

Narrower than `gtm` by design: search performance and indexing status are read-only, and the only writes are `sitemaps submit`/`delete` — this skill doesn't register or remove properties from the account. Every sitemap change is logged to a gitignored `.gsc-audit.jsonl` at the repo root.

**Requirements:**

- `GTM_SERVICE_ACCOUNT_KEY` exported — reuses the exact same service account key as `gtm`. That service account must additionally be added as a user inside Search Console itself (Settings → Users and permissions, **Full** permission — Restricted can't submit/delete sitemaps) — a GCP IAM role alone grants nothing there, same as GTM.
- `pip install google-auth` once — already installed if `gtm` is set up.
- Search Console API enabled on the service account's GCP project.
- Optionally `GSC_SITE_URL` exported for the property used most, so `--site` never needs to be typed (or hardcoded) into a command. Note a domain property (`sc-domain:example.com`) and a URL-prefix property (`https://example.com/`) are different properties, not interchangeable.

Source: `plugins/gsc/skills/gsc/`.

### `ga4`

Query [Google Analytics 4](https://analytics.google.com) reporting data — traffic, sessions, events, conversions, funnels, realtime activity, custom dimensions/metrics — via Google's own official [`analytics-mcp`](https://github.com/googleanalytics/google-analytics-mcp) server. Triggers on any question about site traffic, users, top pages/events, conversion or ROAS numbers, a funnel, or what's happening on the site right now.

Structurally different from `gtm`/`gsc`: there's no custom script here. `analytics-mcp` is a real MCP server, bundled via `plugins/ga4/.mcp.json` — once the plugin is enabled its 9 tools (`get_account_summaries`, `run_report`, `run_realtime_report`, `run_funnel_report`, `run_conversions_report`, and others) are just available directly. Every tool is read-only, so there's no audit log and no confirmation gate, unlike `gtm`'s publish step or `gsc`'s sitemap writes.

**Requirements:**

- `GA_SERVICE_ACCOUNT_KEY` and `GA_PROJECT_ID` exported — reuses the same service account key as `gtm`/`gsc`, plus the GCP project ID for API quota. Deliberately *not* named `GOOGLE_APPLICATION_CREDENTIALS`/`GOOGLE_PROJECT_ID` (what `analytics-mcp` itself needs) — those generic names are also read by `gcloud`, Terraform/OpenTofu, and other tools, so `.mcp.json` remaps the scoped names to the generic ones only for the `analytics-mcp` subprocess. Same zsh caveat as the other skills — **`~/.zshenv`, not `~/.zshrc`**.
- That service account must additionally be added inside the GA4 property itself (Admin → Property Access Management, **Viewer** or above) — a GCP IAM role alone grants nothing there, same as `gtm`/`gsc`.
- Google Analytics **Admin** API and **Data** API enabled on the service account's GCP project.
- `pipx` installed — `analytics-mcp` runs via `pipx run analytics-mcp`, cached after the first launch.

Source: `plugins/ga4/skills/ga4/`.

## Adding a new skill

1. `mkdir -p plugins/<name>/skills/<name>` and put the skill there (`SKILL.md` + any `reference/`/`scripts/`/`assets/`).
2. Add a `plugins/<name>/.claude-plugin/plugin.json` (see `plugins/superglue/.claude-plugin/plugin.json` for the shape).
3. Add an entry to `.claude-plugin/marketplace.json`'s `plugins` array, `"source": "./plugins/<name>"`.
4. Add a `plugins/<name>/.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) with `"skills": "./skills/"` so Codex resolves the same skill folder.
