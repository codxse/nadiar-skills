---
name: meta-ads
description: Manage Meta (Facebook/Instagram) advertising — campaigns, ad sets, ads, creatives, performance insights, product catalogs and feeds, datasets (pixels), A/B and lift studies — via Meta's own two AI connectors: the hosted ads MCP server at mcp.facebook.com/ads and the ads-cli (`meta`, PyPI `meta-ads`). Use when the user asks about Meta/Facebook/Instagram ad spend, ROAS, CPC/CPM/CTR, a campaign or ad set, creating or pausing an ad, budget changes, a product catalog or feed, pixel/signal health, or mentions Ads Manager, Marketing API, ads-cli, or the Meta ads MCP. Do NOT use for Google Analytics (see ga4), Google Tag Manager (see gtm), or Search Console (see gsc) — those measure the site traffic Meta ads send, not the ads themselves.
---

# Meta Ads — hosted MCP server + ads-cli

Two paths onto the same Marketing API, with different auth and different reach. Pick per task, not per session.

- **Hosted MCP server** — `https://mcp.facebook.com/ads`, run by Meta, declared as a real MCP server at the **plugin root** (`plugins/meta-ads/.mcp.json`, one level up from this file). Browser OAuth, no Meta app and no token to manage. Its tools are simply in your tool list once the plugin is enabled *and a session has started after that* — read the actual names from your tool list rather than from any published count, which has already changed once. Meta documents seven areas, and several are things the CLI has no command for at all: benchmarks and opportunity signals, Business Help Center article search, and the account activity log.
- **ads-cli** — `meta`, run locally via `scripts/meta_ads.py`. A Meta **system user access token**. 72 commands with the full flag surface of the Marketing API: DCO creatives with multiple images/titles/bodies, raw `--targeting` / `--promoted-object` / `--asset-feed-spec` JSON, EU DSA payor/beneficiary fields, `--fields` as an escape hatch to any API field. Scriptable, so it is the path for anything batched or repeated.

**Default to the MCP tools for reading and for ordinary campaign work.** Reach for the CLI when the MCP server has no tool for it, when a flag the tools don't expose matters, or when the same operation runs across many entities.

## Never call `meta` directly — go through `scripts/meta_ads.py`

```
python3 scripts/meta_ads.py check --account act_123456
python3 scripts/meta_ads.py --account act_123456 ads campaign list
python3 scripts/meta_ads.py --account act_123456 --dry-run ads campaign create --name "Q4 Sales" --objective OUTCOME_SALES --daily-budget 5000
```

The wrapper exists because the bare CLI has four traps, each verified live against v1.1.0:

1. **`meta auth status` lies.** It prints `Authenticated (token: ****)` and exits 0 for any non-empty string — it checks presence, never validity. `meta_ads.py check` calls the live API instead and exits non-zero when the token is rejected, and again when the token is valid but cannot reach the `--account` you named.
2. **A `.env` anywhere up the directory tree is read automatically**, including from a subdirectory of the repo that holds it. `ACCESS_TOKEN` there wins over nothing at all, so running the CLI from the wrong directory can silently spend from the wrong account. The wrapper always sets the child's `ACCESS_TOKEN`/`AD_ACCOUNT_ID`/`BUSINESS_ID` explicitly — a real environment variable beats `.env`, and an empty one still beats it — and prints which file it ignored.
3. **`ACCESS_TOKEN` is far too generic a name to export globally.** The wrapper reads **`META_ADS_ACCESS_TOKEN`** and remaps it for the subprocess only, the same reasoning as `ga4`'s `GA_SERVICE_ACCOUNT_KEY`.
4. **Silent success on no credentials.** `meta auth status` with nothing configured prints `Not authenticated` and still exits **0**.

`--account act_...` is required on every command except `ads adaccount` and `ads page`, which are system-user-scoped. `--account`/`--business` are the wrapper's own flags, routed to the child environment; pass the CLI's `--ad-account-id` only where it is a genuine leaf option (`ads dataset connect|disconnect`). `--dry-run` prints the resolved command and whether it counts as a write, without running it.

Full command map, budget modes, exit codes, and the rest of the traps: `reference/cli.md`. Hosted-server endpoint, verified OAuth metadata, and how to pin it read-only: `reference/mcp.md`.

## Setup — check before the first call

- **`META_ADS_ACCESS_TOKEN` exported**, holding a Meta **system user** access token with `business_management`, `ads_management`, `pages_show_list`, `pages_read_engagement`, `pages_manage_ads`, `catalog_management`, `read_insights`. On zsh put it in `~/.zshenv`, **not `~/.zshrc`** — `.zshrc` is interactive-shell-only and invisible to the non-interactive shell an agent runs commands in.
- **No env var for the ad account, deliberately.** An ad account is one advertiser's money; it belongs to the task, not the machine. Exported globally it would follow you into every unrelated project and let a budget change land on an account the command never named. `--account` is required on every call for exactly that reason.
- **`uv` installed** — the wrapper runs `uvx --from meta-ads meta` when `meta` is not on `PATH`, which uv caches after the first launch. `pip install meta-ads` also works, as does `META_ADS_CLI` pointing at any command. **Python 3.12+** either way.
- **The system user must have the assets assigned** inside Business Manager — the ad account, the Page, the pixel, the catalog. Being an admin of the business grants none of it; each asset is assigned separately, so a token that lists campaigns fine can still 403 on a Page.
- **The hosted MCP server needs nothing exported.** First use opens a Meta OAuth consent screen in the browser; `/mcp` shows the connection state. It uses authorization-code OAuth with PKCE against `https://www.facebook.com/v26.0/dialog/oauth` and registers its own client dynamically, so there is no app to create and no client ID to configure.

Click-by-click system user creation, token generation, and what each scope buys: `reference/setup.md`.

## Workflow

**1. Resolve the ad account first, don't ask for it.** `ads adaccount list` (CLI, no `--account` needed) or the MCP account tool names every account the identity can reach, with its ID, currency and timezone. **Read the currency before quoting any money.** CLI budgets are bare integers in the account currency's smallest unit; the help text says "cents" because it assumes USD. Currencies whose smallest unit *is* the whole unit (IDR, JPY, KRW, VND) take the whole number instead, so the same `--daily-budget 5000` is $50.00 on one account and 5,000 on another — a 100× error in either direction. Confirm the account's currency from `adaccount list`, and if it is not one you have handled on this account before, confirm the multiplier against the account's own reported budget on an existing campaign before writing a new one.

**2. Read before you write, every time.** `campaign list` → `adset list` → `ad list`, or the MCP insights tools. Never guess an ID; copy it from a list response. An ad references a creative that must already exist, and an ad set references a campaign — the tree only makes sense top-down.

**3. Keep the budget in exactly one place.** CBO puts it on the campaign, ABO on the ad sets, flex (`--adset-budget-sharing`) on the ad sets with up to 20% shared. Setting it in both places is the single most common failure, and the bid strategy and pacing flags move level with the budget. `reference/cli.md` has the decision table.

**4. Create PAUSED and leave it that way.** The CLI defaults every create to `--status PAUSED` — verified in its own `--help`. The hosted server is documented as doing the same and exposes a separate activate tool, which is consistent with it, but that has not been confirmed against a live account here: **check the status field on the entity the tool returns** the first time you create through it, and pause it explicitly if it came back active. Going live is a separate step a human asks for by naming the entity. Never bundle activation into a create.

**5. Empty is a finding.** No campaigns, or insights with zero rows, is a real answer about a new or idle account. Report it plainly; do not retry or widen the date range unasked.

## Writes — the gate

Every `create`, `update`, `delete`, `connect`, `disconnect`, and `assign-user` moves real money or real delivery. There is no draft/publish staging step like `gtm` has: the call lands on the live account immediately.

1. **Discover first** — `list`/`get` the entities involved, so the change is described against what is actually there.
2. **State the change and get an explicit yes.** Name the account ID, the entity, the old value and the new one, and budgets in the account's own currency. `--dry-run` prints the exact command for the user to look at. Do not proceed on an inferred yes.
3. **Run it, then report the real outcome** — the new ID, or the API error verbatim. Meta's errors are specific (`Each action type must use at least one object`, `not eligible to set schedules for individual ads`); pass them through rather than paraphrasing.
4. **Audit.** Every mutating invocation through `meta_ads.py` appends a line to `.meta-ads-audit.jsonl` at the repo root (nearest `.git`, else the working directory) with the timestamp, the redacted argv, the account, and the exit code. **Writes made through the hosted MCP tools do not land there** — Meta's own account activity log is the trail for those, and its activity-log tool is how you read it.
5. **`delete` is a cascade.** `campaign delete` takes its ad sets and ads with it. Without `--force` the CLI prompts, which in a non-interactive agent shell aborts on EOF; `--force` is therefore only ever appropriate after step 2, never as a way to get past a prompt.
6. **`ARCHIVED` is the reversible option.** `update --status ARCHIVED` keeps the entity and its history; `delete` does not. Prefer it whenever the user's intent is "stop this", and say so if they asked for a delete.

## What is verified, and what is not

The read path is exercised: every `list`/`get` command in the map, plus `insights get`, has returned a real response from a live account. The **write path has not** — no `create`/`update`/`delete` has run against a real account, so treat the first one you run as the test, and read the returned object rather than assuming it landed as asked. The hosted MCP server's tool list and OAuth flow are likewise unexercised here; enumerate its tools from your own tool list on first use.

## Rules

- **`META_ADS_ACCESS_TOKEN`, never a bare `ACCESS_TOKEN`, in the shell environment** — that generic name is what the wrapper remaps *to* for the subprocess, and what a stray `.env` uses to hijack the account.
- **`--account` on every call, from the user or from `adaccount list`** — never from an environment variable, never inferred from a previous session.
- **Never activate what you created** — PAUSED on both paths is the default and stays the default until a human names the entity and asks for ACTIVE.
- **Never quote or set a budget without having read the account currency** — the CLI's "cents" wording is a USD assumption, not a fact about the account.
- **Never echo `ads page list` output raw** — it includes a live Page access token per Page (see `reference/cli.md`); strip `access_token` before showing or logging it.
- **`meta auth status` is not verification** — use `meta_ads.py check`.
- **Empty is a finding, not an error** (Workflow #5) — report it, don't retry.
