# API and script reference

Docs: https://ai.google.dev/gemini-api/docs/image-generation

Everything below was verified against the live API on 2026-08-01. Where the published docs disagree, the measured behaviour is what is recorded here — see "Where the docs are wrong" at the end.

## Models

| Alias | Model ID | Sizes | Limits |
|---|---|---|---|
| `lite` | `gemini-3.1-flash-lite-image` | 512, 1K | up to 14 reference objects; no Google Search grounding |
| `flash` | `gemini-3.1-flash-image` | 512, 1K, 2K, 4K | 10 objects + 4 characters + 3 style references |
| `pro` | `gemini-3-pro-image` | 512, 1K, 2K, 4K | 6 objects + 5 characters; best text rendering |

`gemini-2.5-flash-image` (the original Nano Banana) still exists but is superseded; the script does not expose it.

- **Sizes** are `512`, `1K`, `2K`, `4K` — case-sensitive, and *not* `512px`. `lite` rejects 2K and 4K with a confusing `404 Requested entity was not found`.
- **Aspect ratios**, all models: `1:1 3:2 2:3 3:4 4:3 4:5 5:4 9:16 16:9 21:9`.
- **Output is always JPEG.** `image/png` and `image/webp` are rejected on every model. No alpha channel is obtainable; convert and key out afterwards with ImageMagick.
- **Input** reference images may be PNG, JPEG, or WebP. Hard cap of 14.
- Every output carries an invisible SynthID watermark.

## Endpoint

```
POST https://generativelanguage.googleapis.com/v1beta/interactions
x-goog-api-key: $GEMINI_API_KEY
Content-Type: application/json
```

This is the Interactions API, not the older `generateContent` surface — shapes differ from `models/*:generateContent`.

Request body:

```json
{
  "model": "gemini-3.1-flash-image",
  "input": [
    { "type": "text", "text": "..." },
    { "type": "image", "mime_type": "image/png", "data": "<BASE64>" }
  ],
  "response_format": {
    "type": "image",
    "mime_type": "image/jpeg",
    "aspect_ratio": "16:9",
    "image_size": "2K"
  },
  "generation_config": { "thinking_level": "high" },
  "tools": [{ "type": "google_search", "search_types": ["web_search", "image_search"] }]
}
```

`generation_config` and `tools` are optional. `thinking_level` is `minimal` (default) or `high`.

Response, with long strings elided:

```
id: 'v1_Chd...'
status: 'completed'
usage:
  total_input_tokens: 28
  total_output_tokens: 1518
  output_tokens_by_modality: [{ modality: 'image', tokens: 1120 }]
steps:
  [0] type: 'thought'        signature: <1.15 MB string>
  [1] type: 'model_output'   content: [{ type: 'image', mime_type: 'image/jpeg', data: <base64> }]
object: 'interaction'
model: 'gemini-3.1-flash-lite-image'
```

A 1K render returns a ~2 MB JSON body. **Never let a raw response reach an agent's context** — the `thought` step alone is over a megabyte.

The script does not depend on that exact nesting: it walks the whole response for any object carrying an `image/*` mime type alongside a `data` string, and collects `text` parts separately as model notes. Verified to also handle the older `candidates[].content.parts[].inlineData` camelCase shape.

## Script usage

```
nanobanana.py {generate|edit|compose} --prompt-file PATH --out PATH [options]
```

| Flag | Default | Notes |
|---|---|---|
| `--prompt-file PATH` | — | The prompt; `-` reads stdin. Mutually exclusive with `--prompt` |
| `--prompt TEXT` | — | Inline, for short instructions only; long prompts break on shell quoting |
| `--out PATH` | — | Must end `.jpg`/`.jpeg`. Never overwritten. Parent directory must exist |
| `--input PATH` | — | Reference image; repeat per image. PNG, JPEG, or WebP |
| `--model` | `flash` | `lite`, `flash`, `pro` |
| `--size` | `2K` | `512`, `1K`, `2K`, `4K`; validated against the model |
| `--ar` / `--aspect-ratio` | `1:1` | Set this — the default is rarely what you want |
| `--thinking` | `minimal` | `high` for complex composition or exact text |
| `--grounding` | off | Google Search grounding; unsupported on `lite` |
| `--n COUNT` | `1` | Renders variants as `<out>-1`, `<out>-2`, …; one billed call each |
| `--log PATH` | repo root `.nanobanana.jsonl` | JSONL render log |
| `--timeout SECONDS` | `300` | 4K renders are slow |

`edit` requires at least one `--input`; `compose` requires at least two.

On success it prints one line per image — path, mime type, file size, elapsed time, cost — then a total. Nothing else goes to stdout, so it is safe to run without flooding context.

## Cost

The script bills from the `usage` block the API returns, so the printed price includes thinking and grounding tokens rather than assuming a flat per-image rate. Token rates per 1M:

| | input | text output | image output |
|---|---|---|---|
| `lite` | $0.25 | $1.50 | $30 |
| `flash` | $0.50 | $3.00 | $60 |
| `pro` | $2.00 | $12.00 | $120 |

Published per-image prices, used only as a fallback if `usage` is ever missing:

| | 512 | 1K | 2K | 4K |
|---|---|---|---|---|
| `lite` | 0.034 | 0.034 | — | — |
| `flash` | 0.045 | 0.067 | 0.101 | 0.151 |
| `pro` | 0.134 | 0.134 | 0.134 | 0.240 |

Measured on real renders: `lite` 1K `$0.0342`, `flash` 1K edit `$0.0683`, `pro` 1K with `--thinking high` `$0.1365`.

A 1K image is 1120 image tokens. On `lite` and `pro`, `--size 512` also bills 1120 tokens — identical price for a smaller picture, so it is never the right choice there.

**No model has a free tier.** A key without billing fails on the first call.

## Errors

| Code | Meaning |
|---|---|
| 400 | Bad aspect ratio, unsupported `image_size` spelling, or a non-JPEG `mime_type` |
| 401 | Invalid `GEMINI_API_KEY` |
| 403 | Key lacks access, or the API is not enabled on its project |
| 404 | `Requested entity was not found` — usually a size the model does not offer, e.g. `lite` at 2K |
| 429 | Quota exhausted, or billing not enabled — the usual first-run failure |

A `200` with no image part means the model declined the prompt; the script surfaces its text response as the reason.

## Render log

Every image appends one line to `.nanobanana.jsonl`, found by walking up from `--out` to the nearest `.git`:

```json
{"at":"2026-08-01T11:54:04+00:00","out":"app/assets/images/hero.jpg","command":"generate",
 "model":"gemini-3.1-flash-image","size":"4K","aspect_ratio":"16:9","mime_type":"image/jpeg",
 "thinking_level":"minimal","grounding":false,"inputs":[],"prompt":"A wide cinematic...",
 "cost_usd":0.15102,"seconds":18.4,"input_tokens":112,"image_tokens":2518,"text_tokens":0}
```

Read it before editing an existing asset — the stored prompt is what makes a follow-up edit a real revision rather than a reroll. Gitignored by default.

## Where the docs are wrong

Four discrepancies found while building this, all confirmed by live calls:

1. Docs describe `mime_type: "image/jpeg"` **or** `"image/png"`. Only JPEG is accepted, on all three models.
2. Docs give the smallest size as `512px`. The API requires `512`; `512px` is a 400.
3. Docs say 512 is Flash-only and that Flash Lite is 1K-only. In fact all three models accept 512, and `lite` accepts 512 and 1K but not 2K or 4K.
4. Docs describe the per-image price as flat per resolution. Reported usage bills `--thinking high` and grounding on top.
