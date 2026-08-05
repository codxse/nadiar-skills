# Qwen-Image API reference

Everything the script wraps, plus the per-model limits it enforces. Limits
marked **(probed)** were confirmed against the live Singapore endpoint and in a
few places contradict the published docs — trust the probed value.

## Endpoint

```
POST https://$QWEN_API_HOST/api/v1/services/aigc/multimodal-generation/generation
Authorization: Bearer $QWEN_API_KEY
Content-Type: application/json
```

`$QWEN_API_HOST` is the workspace's dedicated host, e.g.
`ws-xxxxxxxxxxxx.ap-southeast-1.maas.aliyuncs.com`. Singapore and Beijing are
separate installations: separate keys, separate hosts, no cross-calling.

Every call is **synchronous** — the response carries the finished images. There
is a separate async task API (`/api/v1/services/aigc/text2image/image-synthesis`
plus `GET /api/v1/tasks/{id}`) that only `qwen-image` and `qwen-image-plus`
support; the script does not use it, because sync covers every model.

## Request body

```json
{
  "model": "qwen-image-3.0-pro",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": [
          {"image": "data:image/png;base64,..."},
          {"text": "the prompt"}
        ]
      }
    ]
  },
  "parameters": {
    "prompt_extend": true,
    "size": "1664*928",
    "n": 1,
    "negative_prompt": "…",
    "seed": 7,
    "watermark": false
  }
}
```

- Exactly one message, `role: "user"`. Single round only — there is no
  conversation history.
- `content` holds exactly one `text` object and zero or more `image` objects.
  **Zero images means text-to-image; one to three means editing.**
- Images are passed as a public `https://` URL or as a
  `data:{mime};base64,{payload}` URI. The script always base64-encodes local
  files, so nothing needs to be uploaded anywhere first.

### parameters

| Field | Type | Default | Notes |
|---|---|---|---|
| `prompt_extend` | boolean | `true` | Server-side prompt rewriter. Leave on for short prompts; `--no-prompt-extend` when your prompt is already fully specified and you want it followed literally |
| `size` | string | model picks | `"width*height"`, width first (**probed**) |
| `n` | integer | 1 | Images per request, returned in one response — not one call per image |
| `negative_prompt` | string | — | Max 500 characters |
| `seed` | integer | random | `0`–`2147483647` |
| `watermark` | boolean | `false` | Adds a **visible** "Qwen-Image" mark, not an invisible one |

## Per-model limits (probed)

| Model | generate | edit | max `n` | `size` rule |
|---|---|---|---|---|
| `qwen-image-3.0-pro` | yes | yes | 6 | area 262 144–6 553 600 px (512²–2560²) |
| `qwen-image-2.0-pro` | yes | no | 6 | area 262 144–4 194 304 px (512²–2048²) |
| `qwen-image-2.0` | yes | no | 6 | area 262 144–4 194 304 px |
| `qwen-image-max` | yes | no | 1 | each side 512–2048 |
| `qwen-image-plus` | yes | no | 1 | five fixed sizes only |
| `qwen-image` | yes | no | 1 | five fixed sizes only |
| `qwen-image-edit-max` | no | yes | 6 | each side 512–2048 |
| `qwen-image-edit-plus` | no | yes | 6 | each side 512–2048 |
| `qwen-image-edit` | no | yes | 1 | ignores `size` entirely |

The five fixed sizes: `1664*928`, `1472*1104`, `1328*1328`, `1104*1472`,
`928*1664`.

Notes worth the space:

- **Area vs side.** The `3.0`/`2.0` models validate width × height only, so
  `3072*1024` is accepted despite exceeding 2048 on one side. The `max` and
  `edit-*` models validate each side independently.
- **`qwen-image-3.0-pro` is one model for both commands.** Its error message
  spells the rule out: *"0 images = T2I mode, 1~3 images = I2I mode."*
- **`qwen-image-edit` does not validate `n`.** `n: 99` returns HTTP 200 with a
  single image and bills every render. Every other model rejects it for free
  with `InvalidParameter`. This is why the script hard-caps that model at 1.
- **The docs understate `3.0-pro`.** They say 2048×2048; the API accepts area
  up to 2560².

## Input images

- 1–3 per request.
- JPG, JPEG, PNG, BMP, TIFF, WEBP, GIF (first frame only).
- Max 10 MB each.
- 384–3072 px per side.

## Response

```json
{
  "output": {
    "choices": [
      {
        "finish_reason": "stop",
        "message": {
          "role": "assistant",
          "content": [{"image": "https://dashscope-….oss-ap-southeast-1.aliyuncs.com/…png"}]
        }
      }
    ]
  },
  "usage": {
    "output_width": 1664,
    "output_height": 928,
    "input_image_count": 0,
    "input_image_type": "qima_input_1k",
    "output_image_count": 1,
    "output_image_type": "qima_output_1k"
  },
  "request_id": "15b5fdc5-…"
}
```

Output is always **PNG**, at a URL valid for **24 hours**. Download it
immediately; the script does.

The `usage` block shown above is what the live API returns. The published docs
document `width`, `height` and `image_count` instead — the script reads both
shapes. `output_image_type` is the billing tier (`qima_output_1k`,
`qima_output_2k`, …), which is the closest thing to a cost signal the response
carries; per-image USD prices are not in the docs and have to be read off the
Model Studio console.

With `n > 1` the extra images arrive as additional `content` entries in the
same response, so one request produces all of them.

## Errors

```json
{"request_id": "…", "code": "InvalidParameter", "message": "…"}
```

| `code` | Meaning |
|---|---|
| `InvalidParameter` | Bad `size`, `n`, image count, or model name. Free — nothing is billed |
| `InvalidApiKey` | Wrong key, or a Beijing key against a Singapore host |
| `Model.AccessDenied` | The workspace has no access; some models are limited preview and need an application in Model Gallery |
| `Throttling.RateQuota` | Workspace rate limit. Free. The script retries with backoff starting at 5s |
| `AllocationQuota.Exceeded` | Free quota or account balance exhausted |
| `DataInspectionFailed` | Content moderation rejected the prompt or an input image |

Failed calls are not billed and do not consume the new-account free quota.

## Script flags

```
qwenimage.py generate --prompt-file P --out OUT.png [options]
qwenimage.py edit --prompt-file P --input IMG [--input IMG …] --out OUT.png [options]
```

| Flag | Default | Notes |
|---|---|---|
| `--prompt-file` / `--prompt` | required | `-` reads stdin. Prefer the file |
| `--out` | required | Must end `.png`. Never overwritten |
| `--input` | — | Repeat for up to 3. `edit` only |
| `--model` | `qwen-image-3.0-pro` | Any model ID from the table above |
| `--size` | model picks | `1664*928` or `1664x928`. **Quote it in zsh** |
| `--n` | 1 | `>1` writes `<out>-1.png`, `<out>-2.png`, … |
| `--negative-prompt` | — | Max 500 chars |
| `--seed` | random | `0`–`2147483647` |
| `--no-prompt-extend` | off | Disables the server-side rewriter |
| `--watermark` | off | Visible watermark |
| `--log` | `<repo root>/.qwenimage.jsonl` | JSONL, one line per image |
| `--timeout` | 300 | Seconds, per HTTP call |
| `--retries` | 4 | Throttling retries, exponential backoff capped at 60s |

Model, size, `n`, image count, file type and output extension are all validated
locally before any request goes out, so a mistake in those costs nothing.

Typical latency on `qwen-image-3.0-pro`: ~60s for a 1664×928 generate, ~90s for
an edit.
