---
name: nano-banana
description: Generate, edit, and compose raster images with Google's Gemini image models (Nano Banana / Nano Banana Pro) and write them straight into the workspace. Use whenever an image asset is needed mid-task — hero images, og:image cards, app icons, avatars, illustrations, textures, backgrounds, product or device mockups, placeholder art, sprite/marketing assets — or when the user says "generate an image", "make me a picture/illustration/icon/logo mockup", "I need a photo of...", asks to edit or restyle an existing image file, combine reference images, or mentions nano banana, Gemini image, or imagen. The skill writes a full specified prompt on the user's behalf, so a one-line request like "I need a hero image for the pricing page" is enough to trigger it. Do NOT use for charts, graphs, or data visualisation (use the dataviz skill), for architecture/flow diagrams (use mermaid or hand-written SVG, which stay editable and diffable), for icons that a standard icon set already covers, or for mechanical transforms of an existing file like resize, crop, or format conversion (use ImageMagick).
---

# Nano Banana — image generation into the workspace

Google's Gemini image models behind a single stdlib-Python script. Two things this skill exists to do:

1. **Write the prompt for the user.** They should never have to. A one-line request becomes a fully specified prompt covering subject, composition, lighting, style, and palette. This is where the quality comes from — see `reference/prompting.md`.
2. **Land the file in the right place.** The script decodes straight to the given path. No downloads, no moving files around.

## Setup — check before the first render

- **`GEMINI_API_KEY` exported.** Get one at https://aistudio.google.com/apikey. On zsh, put the export in `~/.zshenv`, **not `~/.zshrc`** — zsh only reads `.zshrc` for interactive shells, so a key defined there is invisible to the non-interactive shell an agent runs commands in.
- **Billing enabled on that key's project.** None of the image models have a free tier; an unbilled key fails with HTTP 429 on the first call. This is the most common install failure.
- **`python3`** (3.8+). Stdlib only — nothing to `pip install`.

## Workflow

**1. Confirm the destination path.** Always ask, unless the user already said where it goes. Propose one from the project's conventions (`app/assets/images/`, `public/`, `static/img/`, `assets/`) and let them confirm. Never invent a location silently.

**2. Write the prompt to a file**, in the scratchpad directory — not inline on the command line. Prompts run 80–150 words and shell quoting mangles them. Read `reference/prompting.md` first and work through its checklist; a vague prompt is the single biggest cause of a bad render, and rerolling costs real money.

**3. Pick model and size** from the tables below, then render:

```bash
python3 scripts/nanobanana.py generate \
  --prompt-file /path/to/prompt.txt \
  --out app/assets/images/hero.jpg \
  --model flash --size 4K --ar 16:9
```

**The API only returns JPEG** — no PNG, no WebP, no alpha channel, on any model. `--out` must end in `.jpg`/`.jpeg`. If the asset needs to be a PNG, convert after rendering: `magick hero.jpg hero.png`.

**4. Look at the result.** Read the written file with the Read tool and check it against the spec. Re-render only for a concrete violation — misspelled or garbled text, wrong object count, wrong aspect ratio, visible artifacts, a subject that contradicts the brief. Do not re-render for taste; that spends the user's money chasing a subjective "better". One automatic retry maximum, then hand it over and say what is off.

**5. Report the path and the cost.** The script prints both.

## Choosing the model

| Use | Model | Why |
|---|---|---|
| Any legible text in the image — logos, signage, posters, UI mockups, labelled diagrams | `pro` | Materially better text rendering; the others garble words |
| Everything else — photos, illustrations, textures, backgrounds, avatars | `flash` | Default. Handles 4K and up to 10 objects + 4 characters + 3 style refs |
| Cheap variants when the user wants options to choose from | `lite` | Maxes out at 1K, no Google Search grounding |

Do not silently upgrade to `pro` for non-text work — it is roughly double the price for no gain.

## Choosing the size

Assets are viewed on retina displays, so the target is **rendered CSS width × 2**:

| Asset | Render at |
|---|---|
| Icon, avatar, small thumbnail (≤256px CSS) | `1K` |
| Card image, inline content image (~400–800px CSS) | `2K` |
| Hero, full-bleed background (1200px+ CSS) | `4K` |
| og:image / social card (fixed 1200×630) | `2K`, `--ar 16:9` |

`2K` is the default and the right answer when unsure. Shipping a `1K` hero is the mistake this table exists to prevent.

Aspect ratios, exhaustively: `1:1 3:2 2:3 3:4 4:3 4:5 5:4 9:16 16:9 21:9`. Nothing else is accepted. Crop afterwards for anything else.

## Cost per image (USD)

| | 512 | 1K | 2K | 4K |
|---|---|---|---|---|
| `lite` | 0.034 | 0.034 | — | — |
| `flash` | 0.045 | 0.067 | 0.101 | 0.151 |
| `pro` | 0.134 | 0.134 | 0.134 | 0.240 |

Two measured surprises worth knowing: **`lite` maxes out at 1K** (2K and 4K are rejected), and **`--size 512` bills the same as `1K` on `lite` and `pro`** — same image-token count — so it saves nothing there. Reach for `lite --size 1K` when you want cheap, never `--size 512`.

The script bills from the token usage the API actually reports, not this table, so `--thinking high` and `--grounding` show up in the printed price. Expect it to land a few percent above the figures here.

Render **one good image** by default. Drafting several and picking is opt-in, for when the user says they want options:

```bash
python3 scripts/nanobanana.py generate --prompt-file p.txt \
  --out /scratch/draft.jpg --model lite --size 1K --n 3
```

Then promote the chosen draft by passing it back as a reference image, which keeps the composition while re-rendering at full resolution:

```bash
python3 scripts/nanobanana.py edit --input /scratch/draft-2.jpg \
  --prompt-file p.txt --out app/assets/images/hero.jpg --size 4K --ar 16:9
```

## The three commands

- **`generate`** — text to image. The default; most requests are this.
- **`edit`** — one `--input` image plus an instruction. Reach for this on "same but…" follow-ups; it preserves the subject where a fresh `generate` would reroll it entirely.
- **`compose`** — two or more `--input` images. Product onto a background, a logo onto a device mockup, several people into one group shot. Up to 14 references.

Full flag reference and API details: `reference/api.md`.

## Rules

- **Never pass image data through the conversation.** The script reads and writes bytes on disk. Do not `base64` a file in a shell command, do not paste encoded data into a prompt, do not `cat` a raw API response — one 1K render comes back as ~800 KB of base64 inside a ~2 MB JSON body and will blow the context window. Reading a *rendered* image back with the Read tool is fine and cheap; that is how step 4 works.
- **The script never overwrites.** An existing `--out` is an error with a suggested free name. To genuinely replace an asset, let the user delete the old one.
- **Every render is billed.** No free tier, no exceptions. Do not render speculatively, and do not run `--n` above 3 without being asked.
- **Every render is appended to `.nanobanana.jsonl`** at the repo root, with the full prompt and parameters. Read it to recover the exact prompt behind an existing asset before tweaking it — that is what makes "same, but warmer lighting" reproducible instead of a reroll. Add it to `.gitignore`.
- **Outputs carry an invisible SynthID watermark.** Mention this once if the user is shipping assets commercially.
