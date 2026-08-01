# Writing the prompt

The user gives you one line. You write 80–150 words. That gap is the whole job.

A weak prompt does not produce a weak image — it produces an *arbitrary* image, technically fine and unusable, and every reroll costs money. Specificity is control.

## The checklist

Work through all of it before rendering. Anything left unspecified gets decided for you, badly.

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
| **Aspect ratio** | Set via `--ar`, but describe framing consistently with it — do not ask for a tall portrait subject at `16:9` |

## Principles

**Describe the scene, do not list the tags.** Prose outperforms comma-salad. `"three-quarter view, 85mm, bokeh, moody, cinematic, 8k"` is worse than a paragraph that says what the picture is of. The model reads language, not keywords.

**State the intent.** Telling it *what the image is for* — "a hero image for a wedding-invitation SaaS landing page, calm and premium, with clear negative space on the right for a headline" — quietly fixes composition, mood, and crop at once. This is the highest-leverage sentence you can add.

**Negatives must be semantic.** There is no negative-prompt parameter, and "no cars, no people" tends to summon cars and people. Describe the positive state instead: not "no people" but "a deserted street at dawn, completely empty". Not "no text" but "an unbroken surface with no lettering or signage".

**Name the style precisely.** "Illustration" is meaningless. "Flat vector illustration with 2px uniform outlines, limited four-colour palette, no gradients" is a specification. Same for photos: "shot on 35mm Portra 400, natural grain, slightly warm cast".

**Sequence complex scenes.** For multi-element compositions, walk the model through it in order: establish the setting, then place the subject, then the secondary elements, then the lighting. This works better than one dense sentence and pairs with `--thinking high`.

**Reach for `--thinking high`** on compositions with several interacting elements, specific spatial relationships, or text that must be exact. It costs a little more in text tokens and takes longer. Skip it for a single subject on a plain background.

**Reach for `--grounding`** when the image must match something real — a specific landmark, a real product's actual shape, current fashion. Not available on `lite`.

## Templates

Adapt, do not paste. The bracketed parts are the thinking you still have to do.

### Landing-page hero

> A wide cinematic photograph of [subject] in [setting]. Shot at eye level on a 35mm lens with a shallow depth of field, the background falling into soft blur. Late-afternoon sunlight rakes in from the left, warm and low, casting long soft shadows. Muted palette of [colour A], [colour B], and warm neutrals. Calm, premium, unhurried mood. The left third of the frame is deliberately uncluttered negative space for a headline overlay. Photorealistic, natural film grain, no text or lettering anywhere in the image.

Render `--model flash --size 4K --ar 16:9`.

### og:image / social card

> A flat vector illustration on a solid [colour] background, centred composition with generous margins on all sides. [Subject] rendered in a limited three-colour palette with uniform 2px outlines and no gradients or shadows. Simple, bold shapes readable at thumbnail size. Plenty of clear space in the lower third. No text.

Render `--model flash --size 2K --ar 16:9`, then overlay real text with CSS or ImageMagick. Never ask the model for the headline text on a social card — you need it typographically exact and re-editable.

### App icon / logo mark

> A minimalist app icon of [subject], centred, rendered as a simple geometric mark with clean even strokes and generous padding inside the frame. Solid [colour] background, single flat accent colour, no gradients, no bevels, no drop shadows. Bold and instantly legible when scaled down to 32 pixels.

Render `--model pro --size 1K --ar 1:1`. Pro because marks usually carry lettering, and this is where the other models fail.

### Product / device mockup

> A studio product photograph of [product] on a seamless [colour] backdrop. Three-quarter view from slightly above, 85mm lens. Soft large key light from the upper left with a subtle fill from the right, producing gentle gradient falloff and one soft contact shadow beneath the object. Crisp focus across the entire product. Clean commercial catalogue aesthetic, neutral colour grading.

Render `--model flash --size 2K`. For placing a real logo or screenshot onto a device, use `compose` with the asset as a reference image rather than describing it.

### Texture / background

> A seamless abstract background of [material or pattern], filling the entire frame edge to edge with even visual weight and no focal point. [Colour A] shifting gently into [colour B]. Subtle organic variation, very low contrast, no discernible objects, shapes, or lettering. Designed to sit behind body text without competing with it.

Render `--size 4K`. Low contrast is the requirement people forget — a busy background makes overlaid text unreadable.

### Avatar / character

> A friendly portrait illustration of [description], head and shoulders, facing slightly to the left, on a plain [colour] background. [Named art style]. Warm even lighting, no harsh shadows. Simple shapes, clear silhouette, readable as a 64px circular avatar.

Render `--size 1K --ar 1:1`. For a *consistent* cast across several avatars, generate the first, then `edit` from it for each variant — a fresh `generate` per person will not hold the style.

### Text inside the image

Only when the text genuinely belongs to the artwork — a poster, a shop sign, a book cover.

> A [style] poster. The words "[EXACT TEXT]" appear in [describe the typeface: heavy condensed sans-serif, all caps, tight letter spacing], positioned [where], in [colour]. [Describe the rest of the composition.]

Render `--model pro --thinking high`, and check every character in the output. If the user only wants text *over* an image, do not do this — generate a clean image and set real type on top.

## Editing

`edit` keeps the subject; `generate` rerolls it. On any "same but…" request, use `edit` with the previous output as `--input`.

Say what changes and what must not:

> Change only the lighting to cool blue overcast daylight. Keep the subject, pose, framing, and background composition exactly as they are.

Patterns that work:

- **Add** — "Add a small potted fern on the left edge of the desk, matching the existing lighting direction and perspective."
- **Remove** — "Remove the cable running across the foreground and reconstruct the surface texture continuously beneath it."
- **Restyle** — "Redraw this in flat vector style with uniform outlines and a four-colour palette, preserving the exact composition, proportions, and camera angle."
- **Recolour** — "Change the jacket to deep forest green. Leave every other colour, the lighting, and the shadows untouched."
- **Upscale** — pass the draft as `--input`, reuse the original prompt, request a larger `--size`.

Recover the original prompt from `.nanobanana.jsonl` at the repo root before editing an existing asset, so the edit builds on the real spec instead of your guess at it.

## Transparency

There is none. The API returns JPEG on every model, so an alpha channel is not on the table — asking for "a transparent background" gets you a painted checkerboard.

For a cut-out asset — icon, logo, sticker — ask for the subject **isolated on a flat, uniform background in a colour absent from the subject**, then key it out afterwards:

```bash
magick icon.jpg -fuzz 12% -transparent white icon.png
```

Say the background colour explicitly in the prompt and pick one the subject does not contain, or the fuzz threshold will eat into the artwork. Widen `-fuzz` if JPEG compression leaves a halo.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Garbled or misspelled words | Wrong model | `--model pro --thinking high`, or drop the text and set real type on top |
| The thing you excluded is present | Literal negative | Restate positively as the desired end state |
| Composition ignores your crop | Prompt fights the ratio | Describe framing that suits `--ar`, and say where the empty space goes |
| Generic, styleless result | Under-specified style | Name the medium, era, and technique explicitly |
| Cluttered background | Background unspecified | Always state it, even as "plain seamless white" |
| Subject drifts between renders | Using `generate` to iterate | Switch to `edit` with the previous file as `--input` |
| Soft, low-detail at large size | Rendered small | Match `--size` to the retina table in SKILL.md |
