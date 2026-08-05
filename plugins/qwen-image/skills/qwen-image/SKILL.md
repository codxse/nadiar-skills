---
name: qwen-image
description: Generate and edit images with Alibaba Cloud Model Studio's Qwen-Image models, written straight into the workspace. Use whenever the user names Qwen, Model Studio, DashScope or Aliyun; wants an alternative to nano-banana on a render they rejected; needs legible text inside the image, especially Chinese, Japanese or Korean; or wants to edit an image file or fuse two or three of them. Not for charts or data visualisation (use dataviz), diagrams (use mermaid or SVG), or resize/crop/format conversion (use ImageMagick).
---

# Qwen-Image — image generation into the workspace

Alibaba Cloud Model Studio's Qwen-Image family behind a single stdlib-Python
script. Same shape as the `nano-banana` skill, different provider — reach for
this one when Qwen is asked for by name, when nano-banana produced something
the user rejected, or when the asset needs text rendered inside it.

Two things this skill exists to do:

1. **Write the prompt for the user.** They should never have to. A one-line
   request becomes a fully specified prompt covering subject, composition,
   lighting, style and palette. See `reference/prompting.md`.
2. **Land the file in the right place.** The API returns a URL that expires in
   24 hours; the script downloads it straight to the path you name.

## Setup — check before the first render

- **`QWEN_API_KEY` and `QWEN_API_HOST` exported.** Both come from the Model
  Studio console. The host is your workspace's dedicated endpoint and looks
  like `ws-xxxxxxxxxxxx.ap-southeast-1.maas.aliyuncs.com`.
- **Region matters.** Singapore (`ap-southeast-1`) and Beijing (`cn-beijing`)
  issue separate keys against separate endpoints and **cannot** be mixed. A
  Beijing key on a Singapore host fails with `InvalidApiKey`.
- On zsh put the exports in `~/.zshenv`, **not `~/.zshrc`** — zsh only reads
  `.zshrc` for interactive shells, so a key defined there is invisible to the
  non-interactive shell an agent runs commands in.
- **`python3`** (3.9+). Stdlib only — nothing to `pip install`.

## Workflow

**1. Confirm the destination path.** Always ask, unless the user already said
where it goes. Propose one from the project's conventions
(`app/assets/images/`, `public/`, `static/img/`, `assets/`) and let them
confirm. Never invent a location silently.

**2. Write the prompt to a file** in the scratchpad directory — not inline on
the command line. Prompts run 80–150 words and shell quoting mangles them.
Read `reference/prompting.md` first; a vague prompt is the biggest cause of a
bad render, and rerolling costs real money.

**3. Pick model and size** from the tables below, then render:

```bash
python3 scripts/qwenimage.py generate \
  --prompt-file /path/to/prompt.txt \
  --out app/assets/images/hero.png \
  --size '1664*928'
```

Quote `--size` — the `*` is a glob character and an unquoted `1664*928` dies in
zsh before the script ever sees it.

**The API only returns PNG**, so `--out` must end in `.png`. If the asset needs
to be a JPEG, convert after rendering: `magick hero.png hero.jpg`.

**4. Look at the result.** Read the written file with the Read tool and check
it against the spec. Re-render only for a concrete violation — misspelled or
garbled text, wrong object count, wrong aspect ratio, visible artifacts, a
subject that contradicts the brief. Do not re-render for taste; that spends the
user's money chasing a subjective "better". One automatic retry maximum, then
hand it over and say what is off.

**5. Report the path.** The script prints it along with the output dimensions
and the billing tier the API reported.

## Choosing the model

`generate` (text to image):

| Use | Model | Why |
|---|---|---|
| Default — anything, including text in the image | `qwen-image-3.0-pro` | Best quality, the largest size ceiling (up to ~2560²), and the only generate model that also edits |
| Photoreal work where the render must not look AI-made | `qwen-image-max` | Vendor-tuned for realism and fewer generation artifacts; capped at 2048 per side, `--n 1` only |
| Batches of variants to choose from | `qwen-image-2.0` | Cheaper than the pro tiers and takes `--n` up to 6 |
| Stylised or illustrative work on a budget | `qwen-image-plus` | Cheapest; locked to five fixed sizes and `--n 1` |

`edit` (1–3 input images plus an instruction):

| Use | Model | Why |
|---|---|---|
| Default — edits, restyles, "same but…" follow-ups | `qwen-image-3.0-pro` | Strongest subject consistency; one model for both commands |
| Fusing several references, character consistency across edits | `qwen-image-edit-max` | Purpose-built for multi-image fusion and geometric reasoning |
| Cheap single edits | `qwen-image-edit` | Ignores `--n` and `--size` entirely — see the trap below |

Also available and accepted by the script: `qwen-image-2.0-pro`,
`qwen-image-edit-plus`, `qwen-image`. Full per-model limits are in
`reference/api.md`.

## Choosing the size

Omitting `--size` lets the model pick from the prompt, which is fine for
exploration but unpredictable for a real asset — **pass `--size` for anything
going into a repo.** Assets are viewed on retina displays, so target
**rendered CSS width × 2**:

| Asset | Render at |
|---|---|
| Icon, avatar, small thumbnail (≤256px CSS) | `1024*1024` |
| Card image, inline content image | `1328*1328`, or `1472*1104` for 4:3 |
| Hero, full-bleed background | `2048*1152` (16:9), `2304*1280` on `3.0-pro` |
| og:image / social card (fixed 1200×630) | `1664*928` |

`qwen-image-3.0-pro` and the `2.0` models validate **total area**, not each
side, so any aspect ratio is allowed as long as width × height stays in range.
`qwen-image` and `qwen-image-plus` accept only these five, and nothing else:
`1664*928`, `1472*1104`, `1328*1328`, `1104*1472`, `928*1664`.

The script checks your `--size` against the chosen model before spending a
request, so a bad combination costs nothing.

## The two commands

- **`generate`** — text to image. Most requests are this.
- **`edit`** — one to three `--input` images plus an instruction. Reach for it
  on "same but…" follow-ups; it preserves the subject where a fresh `generate`
  would reroll it entirely. Two or three inputs fuses them: a product onto a
  background, a logo onto a device mockup.

Full flag reference, per-model limits and response details: `reference/api.md`.

## Rules

- **Never pass image data through the conversation.** The script reads and
  writes bytes on disk. Do not `base64` a file in a shell command, do not paste
  encoded data into a prompt, do not `cat` a raw API response. Reading a
  *rendered* image back with the Read tool is fine and cheap; that is step 4.
- **`qwen-image-edit` silently ignores `--n`.** Ask it for 6 images and it
  bills 6 renders and returns 1. The script caps that model at `--n 1` for
  exactly this reason; do not work around the cap. Every other model rejects an
  out-of-range `--n` for free.
- **Pass `--size` on `edit`.** With no `--size` the model picks its own output
  resolution and will happily upscale — a 1664×928 input came back as
  2736×1520, billed one tier higher. Passing the input's own dimensions keeps
  the edit in place and cheaper.
- **Expect rate limiting.** Model Studio workspaces are throttled tightly and
  bursts return `Throttling.RateQuota`. That costs nothing; the script retries
  with backoff. Render serially rather than firing several at once.
- **Every successful render is billed**, per image, at a tier the script prints
  and logs (`qima_output_1k`, `qima_output_2k`, …). Failed calls are free.
  Per-image prices are not published in the docs — check the Model Studio
  console for the current rate. Do not render speculatively.
- **The script never overwrites.** An existing `--out` is an error with a
  suggested free name. To genuinely replace an asset, let the user delete the
  old one.
- **Every render is appended to `.qwenimage.jsonl`** at the repo root with the
  full prompt, parameters and `request_id`. Read it to recover the exact prompt
  behind an existing asset before tweaking it — that makes "same, but warmer
  lighting" reproducible instead of a reroll. Add it to `.gitignore`.
- **Result URLs expire after 24 hours.** The script downloads immediately, so
  this only matters if you are reading the log later — the file on disk is the
  artifact, the URL in the log is not.
