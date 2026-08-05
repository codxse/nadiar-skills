# Writing the prompt

The user gives you one line. You write 80–150 words. That gap is the whole job.

A weak prompt does not produce a weak image — it produces an *arbitrary* image,
technically fine and unusable, and every reroll costs money. Specificity is
control.

## The checklist

Work through all of it before rendering. Anything left unspecified gets decided
for you, badly.

| | Ask |
|---|---|
| **Subject** | What exactly, how many, doing what, in what state? "A ceramic mug" → "a single matte-charcoal ceramic mug, half full, steam rising" |
| **Composition** | Where in the frame? Close-up, mid-shot, wide? What is the focal point, what is background? Where does text or UI overlay later — leave room for it |
| **Camera** | Angle (eye level, low, top-down, three-quarter), lens (35mm wide, 85mm portrait, macro), depth of field |
| **Lighting** | Direction, quality, time of day. "Soft north-facing window light from the left, gentle falloff" beats "good lighting" |
| **Style** | Photograph? Which era, which film stock? Illustration? Flat vector, isometric, hand-inked, watercolour, 3D clay render? Name it precisely |
| **Palette** | Two or three concrete colours. Say the hex if the brand has one — the model approximates it, and approximate-on-brand beats random |
| **Mood** | The adjective that makes a hundred small choices cohere: calm, austere, playful, clinical, nostalgic |
| **Background** | Explicit. Plain seamless studio white? Blurred office? Empty gradient? Left vague, you get clutter |
| **Framing vs size** | Describe framing consistently with `--size` — do not ask for a tall portrait subject at `1664*928` |

## Qwen-specific principles

These are the ones that differ from other image APIs. Get them wrong and the
generic advice above will not save the render.

**`prompt_extend` is on by default, and it rewrites your prompt.** The server
expands a short prompt into a longer one before generating. That is a real help
on a one-liner and a real problem on a 150-word spec you carefully wrote — it
will embellish, and the embellishment is what lands in the image. Once your
prompt is fully specified, pass `--no-prompt-extend` so it is followed
literally. Rule of thumb: **if you did the checklist above, turn it off.**

**There is a real `--negative-prompt`.** Unlike Gemini-family models, Qwen takes
an explicit exclusion list, and it works. Use it for the things that keep
creeping in — `--negative-prompt "text, watermark, extra fingers, blurry,
oversaturated"`. Keep it to concrete nouns and defects; it is capped at 500
characters. Do **not** put composition instructions in there.

**Text rendering is the reason to pick this over nano-banana.** Qwen-Image is
built around legible in-image typography and handles Chinese, Japanese and
Korean characters that most models garble. Quote the exact string and describe
the type, then check every character in the output:

> The words "秋の味" appear across the upper third in a heavy brush-script
> typeface, deep vermilion, slightly off-centre to the left.

**Use `--seed` when iterating.** Fix the seed, change one clause, re-render, and
you see the effect of that clause instead of a fresh roll of the dice. Drop the
seed once you like the direction and want variety.

**Prose beats tag-salad.** `"three-quarter view, 85mm, bokeh, moody, cinematic,
8k"` is worse than a paragraph that says what the picture is of. The model reads
language, not keywords.

**State the intent.** Telling it *what the image is for* — "a hero image for a
wedding-invitation SaaS landing page, calm and premium, with clear negative
space on the right for a headline" — quietly fixes composition, mood and crop at
once. Highest-leverage sentence you can add.

## Templates

Adapt, do not paste. The bracketed parts are the thinking you still have to do.

### Landing-page hero

> A wide cinematic photograph of [subject] in [setting]. Shot at eye level on a
> 35mm lens with a shallow depth of field, the background falling into soft
> blur. Late-afternoon sunlight rakes in from the left, warm and low, casting
> long soft shadows. Muted palette of [colour A], [colour B] and warm neutrals.
> Calm, premium, unhurried mood. The left third of the frame is deliberately
> uncluttered negative space for a headline overlay. Photorealistic, natural
> film grain.

`--model qwen-image-3.0-pro --size '2304*1280' --no-prompt-extend
--negative-prompt "text, lettering, watermark, logo"`

### og:image / social card

> A flat vector illustration on a solid [colour] background, centred
> composition with generous margins on all sides. [Subject] rendered in a
> limited three-colour palette with uniform 2px outlines and no gradients or
> shadows. Simple, bold shapes readable at thumbnail size. Plenty of clear
> space in the lower third.

`--size '1664*928'`, then overlay real text with CSS or ImageMagick. Never ask
the model for the headline on a social card — you need it typographically exact
and re-editable.

### Poster or sign with real text in it

> A [style] poster. The words "[EXACT TEXT]" appear in [heavy condensed
> sans-serif, all caps, tight letter spacing], positioned [where], in [colour].
> [Describe the rest of the composition.]

`--model qwen-image-3.0-pro --no-prompt-extend`. This is Qwen's strong suit, but
still read every character back. If the user only wants text *over* an image,
generate clean art and set real type on top instead.

### App icon / logo mark

> A minimalist app icon of [subject], centred, rendered as a simple geometric
> mark with clean even strokes and generous padding inside the frame. Solid
> [colour] background, single flat accent colour, no gradients, no bevels, no
> drop shadows. Bold and instantly legible when scaled down to 32 pixels.

`--size '1024*1024'`.

### Product / device mockup

> A studio product photograph of [product] on a seamless [colour] backdrop.
> Three-quarter view from slightly above, 85mm lens. Soft large key light from
> the upper left with a subtle fill from the right, producing gentle gradient
> falloff and one soft contact shadow beneath the object. Crisp focus across the
> entire product. Clean commercial catalogue aesthetic, neutral colour grading.

`--model qwen-image-max --size '2048*1536'` — `max` is tuned for exactly this
kind of realism. To place a real logo or screenshot onto a device, use `edit`
with both files as `--input` rather than describing the asset.

### Texture / background

> A seamless abstract background of [material or pattern], filling the entire
> frame edge to edge with even visual weight and no focal point. [Colour A]
> shifting gently into [colour B]. Subtle organic variation, very low contrast,
> no discernible objects or shapes.

`--size '2304*1280'`. Low contrast is the requirement people forget — a busy
background makes overlaid text unreadable.

### Avatar / character

> A friendly portrait illustration of [description], head and shoulders, facing
> slightly to the left, on a plain [colour] background. [Named art style]. Warm
> even lighting, no harsh shadows. Simple shapes, clear silhouette, readable as
> a 64px circular avatar.

`--size '1024*1024'`. For a *consistent* cast across several avatars, generate
the first, then `edit` from it for each variant — a fresh `generate` per person
will not hold the style. `qwen-image-edit-max` is the best of the family at
holding a face across edits.

## Editing

`edit` keeps the subject; `generate` rerolls it. On any "same but…" request, use
`edit` with the previous output as `--input`, and **pass `--size` matching the
input** — left to itself the model picks its own resolution and upscales, which
changes the framing and bills a tier higher.

Say what changes and what must not:

> Change only the lighting to cool blue overcast daylight. Keep the subject,
> pose, framing and background composition exactly as they are.

Patterns that work:

- **Add** — "Add a small potted fern on the left edge of the desk, matching the
  existing lighting direction and perspective."
- **Remove** — "Remove the cable running across the foreground and reconstruct
  the surface texture continuously beneath it."
- **Restyle** — "Redraw this in flat vector style with uniform outlines and a
  four-colour palette, preserving the exact composition, proportions and camera
  angle."
- **Recolour** — "Change the jacket to deep forest green. Leave every other
  colour, the lighting and the shadows untouched."
- **Fuse** — pass two or three `--input` files and say which contributes what:
  "Place the product from the first image onto the marble surface from the
  second, matching the second image's lighting direction and shadow softness."

Recover the original prompt from `.qwenimage.jsonl` at the repo root before
editing an existing asset, so the edit builds on the real spec instead of your
guess at it.

## Transparency

The API returns PNG, but 8-bit **RGB with no alpha channel** — asking for "a
transparent background" gets you a painted checkerboard.

For a cut-out asset — icon, logo, sticker — ask for the subject **isolated on a
flat, uniform background in a colour absent from the subject**, then key it out:

```bash
magick icon.png -fuzz 10% -transparent white icon-cutout.png
```

Say the background colour explicitly in the prompt and pick one the subject does
not contain, or the fuzz threshold will eat into the artwork. PNG output means
no compression halo to fight, so a tighter `-fuzz` works here than it would on a
JPEG source.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| The render ignores half your carefully written spec | `prompt_extend` rewrote it | `--no-prompt-extend` |
| A one-line prompt gives a flat, generic image | `prompt_extend` had nothing to work with | Write the full 80–150 words yourself |
| Garbled characters in text | Under-specified type, or wrong model | Quote the exact string, describe the typeface, use `qwen-image-3.0-pro` |
| The thing you excluded is present | Not using the parameter | Put it in `--negative-prompt`, not the prompt body |
| Wrong aspect or awkward crop | Prompt fights `--size` | Describe framing that suits the ratio, and say where empty space goes |
| Generic, styleless result | Under-specified style | Name the medium, era and technique explicitly |
| Cluttered background | Background unspecified | Always state it, even as "plain seamless white" |
| Subject drifts between renders | Using `generate` to iterate | Switch to `edit` with the previous file as `--input` |
| Edit came back larger and recomposed | No `--size` on `edit` | Pass the input's own dimensions |
| Every variant looks identical | Fixed `--seed` | Drop the seed |
