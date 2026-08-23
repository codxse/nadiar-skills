# ads-cli reference — `meta` v1.1.0 (PyPI `meta-ads`)

Everything here is against v1.1.0, checked by running it. The package ships compiled modules, so `--help` is the only source of truth for flags — and it is a good one: `meta ads campaign create --help` and `meta ads ad create --help` carry the budget-mode rules and the full create sequence inline. **Read the leaf `--help` before composing any write.** This file covers the command map, the decisions, and the things `--help` does not tell you.

Invoke through the wrapper, never `meta` directly:

```
python3 scripts/meta_ads.py [--account act_...] [--business ID] [--dry-run] <cli args...>
python3 scripts/meta_ads.py check --account act_...
python3 scripts/meta_ads.py ads campaign create --help      # help needs no token
```

## Command map — 72 commands

| Group | Commands | Scope |
|---|---|---|
| `auth` | `status` | — (and it lies; use `check`) |
| `ads adaccount` | `list` `get` `current` | system user — no `--account` needed |
| `ads page` | `list` `get` | system user — no `--account` needed |
| `ads campaign` | `list` `get` `create` `update` `delete` | ad account |
| `ads adset` | `list` `get` `create` `update` `delete` | ad account |
| `ads ad` | `list` `get` `create` `update` `delete` | ad account |
| `ads creative` | `list` `get` `create` `update` `delete` | ad account |
| `ads insights` | `get` | ad account |
| `ads guidance` | `list` | ad account |
| `ads study` | `list` | ad account |
| `ads catalog` | `list` `get` `create` `update` `delete` | business, falls back to the ad account |
| `ads product-feed` | `list` `get` `create` `update` `delete` | catalog |
| `ads product-item` | `list` `get` `create` `update` `delete` | catalog |
| `ads product-set` | `list` `get` `create` `update` `delete` | catalog |
| `ads dataset` | `list` `get` `create` `connect` `disconnect` `assign-user` | business, falls back to the ad account |

Global options go before the command: `-o table|json|plain`, `--no-color`, `--no-input`, `--debug`. `-o json` is the right default for anything you are going to reason over.

`--fields` on most read commands is the escape hatch to any Marketing API field the dedicated flags don't cover; names pass straight through and the API errors on an unknown one.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success — **and also `auth status` with no credentials at all** |
| 1 | unhandled crash, printed as a Python traceback |
| 2 | usage error, e.g. `No ad account configured` |
| 4 | API error, e.g. `API error (190): Invalid OAuth access token` |

A traceback on exit 1 is the CLI failing to create `~/.config/meta/`, not an auth problem — it reaches for that directory before checking anything.

## Budget modes — pick exactly one

| Mode | Budget lives on | Bid strategy & pacing on | Flags |
|---|---|---|---|
| CBO (prefer this) | campaign | campaign | `campaign create --daily-budget` or `--lifetime-budget` |
| ABO | each ad set | each ad set | no campaign budget; `adset create --daily-budget`/`--lifetime-budget` |
| Flex / ad set budget sharing | each ad set, up to 20% shared | campaign | `campaign create --adset-budget-sharing` + a **daily** ad set budget |

A budgetless campaign becomes plain ABO on its own — `--adset-budget-sharing` is only for flex. Flex rejects lifetime budgets and rejects `--buying-type RESERVED`. Setting a budget on both levels is the most common create failure; the second most common is leaving `--bid-strategy` on the campaign for a plain ABO campaign, where it belongs on the ad set.

`COST_CAP`, `LOWEST_COST_WITH_BID_CAP`, and `LOWEST_COST_WITH_MIN_ROAS` all require a bid or ROAS input on the ad set. `--pacing-type no_pacing` is only allowed with `LOWEST_COST_WITH_BID_CAP`.

## The create sequence — campaign → ad set → creative → ad

Each create prints the new ID; feed it forward. Everything defaults to PAUSED and stays that way. Each block below is the argument list to `python3 scripts/meta_ads.py`, elided for width.

```
# L3 campaign — CBO, budget here
--account act_1 ads campaign create --name "Q4 Sales" --objective OUTCOME_SALES --daily-budget 5000

# L2 ad set — no budget under CBO; this is where conversion optimisation is wired
--account act_1 ads adset create CAMPAIGN_ID --name "Purchasers ID" \
  --optimization-goal OFFSITE_CONVERSIONS --billing-event IMPRESSIONS \
  --pixel-id PIXEL_ID --custom-event-type PURCHASE --targeting-countries ID

# Creative — Page identity + media + copy
--account act_1 ads creative create --name "Q4 Hero" --image ./hero.jpg \
  --page-id PAGE_ID --body "Diskon 50%" --title "Q4 Sale" \
  --link-url https://example.com --call-to-action SHOP_NOW

# L1 ad — the creative, plus the conversion domain sales objectives require
--account act_1 ads ad create ADSET_ID --name "Q4 Hero Ad" \
  --creative-id CREATIVE_ID --conversion-domain example.com
```

For a conversion campaign all four of these travel together: `--objective OUTCOME_SALES` on the campaign, `--pixel-id` + `--custom-event-type` on the ad set, `--conversion-domain` on the ad. Missing the last one is rejected by Meta, not by the CLI.

`--promoted-object` supersedes `--pixel-id`/`--custom-event-type` when you need the raw JSON. `--targeting` takes a raw targeting spec for anything `--targeting-countries` and `--advantage-audience` don't reach.

## Insights

```
--account act_1 -o json ads insights get --date-preset last_7d \
  --fields spend,impressions,clicks,ctr,cpc,reach --time-increment daily
```

`--date-preset` is one of `today yesterday last_3d last_7d last_14d last_30d last_90d this_month last_month`, default `last_30d`; `--since`/`--until` (YYYY-MM-DD) override it. `--breakdown` is repeatable across `age gender country publisher_platform device_platform platform_position impression_device`. `--campaign-id`/`--adset-id`/`--ad-id` narrow the scope, `--sort` takes `spend_descending`-style values, `-l` defaults to 50. The output is the raw Marketing API response, not a reshaped table.

## Creatives — single vs DCO

Singular flags build one fixed creative: `--image`/`--video`, `--title`, `--body`, `--description`, `--call-to-action`. The plural flags build a Dynamic Creative Optimization asset feed instead: `--images`/`--videos` (up to 10), `--titles`/`--bodies`/`--descriptions` (up to 5 each, repeat the flag), `--call-to-actions`. DCO needs `--dynamic-creative` on the ad set to be used.

To boost something that already exists rather than upload media: `--object-story-id` for a Page post, `--source-instagram-media-id` or `--instagram-permalink-url` for an Instagram post. `--product-set-id` drives catalog / dynamic product ads.

`--asset-feed-spec`, `--object-story-spec`, and `--degrees-of-freedom-spec` take raw JSON for anything the flags don't cover.

## Traps found by running it

- **`.env` is read from any ancestor directory.** From `repo/sub/`, a `repo/.env` with `ACCESS_TOKEN=` is picked up. A real environment variable wins over it, and an empty environment variable still wins — which is how the wrapper neutralises it.
- **`--ad-account-id` and `--business-id` are options of the `ads` *group*.** `ads campaign list --ad-account-id act_1` fails with `No such option`; the CLI's own form is `ads --business-id 123 catalog list`. `dataset connect`/`dataset disconnect` separately take `--ad-account-id` as a leaf option meaning "the account to connect the dataset *to*". The wrapper's `--account`/`--business` sidestep the collision by going through the environment.
- **`delete` cascades and prompts.** `campaign delete` removes its ad sets and ads. Without `--force` it prompts, and it hits the API to fetch the entity *before* prompting — so an auth error surfaces first. In a non-interactive shell the prompt aborts on EOF.
- **`update --status ARCHIVED`** exists on campaign, ad set, and ad, and is reversible in a way `delete` is not.
- **`--no-input` is a global option**, before the command, not after it.
- **Budgets are bare integers in the account currency's smallest unit.** The help text's "cents" is a USD assumption. Check `adaccount get` for the currency first.
- **`ads page list` prints a live Page access token** in its default fields, one per Page. Found live. Anything that captures command output — a transcript, a CI log, a pasted snippet — captures a working credential that can post as the Page. Pipe it through a filter when the Page token is not what you are after: `... ads page list | python3 -c 'import json,sys;print(json.dumps([{k:v for k,v in p.items() if k!="access_token"} for p in json.load(sys.stdin)],indent=2))'`, or select fields explicitly. A leaked Page token dies when the parent system user token is revoked, not before.
- **The package is compiled** (`.so` per module, no readable `.py`). Nothing to inspect when behaviour surprises you — probe it with `--debug` and `--dry-run` instead.
