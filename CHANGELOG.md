# Changelog

Notable changes to plugins in this marketplace, grouped by plugin. Versions follow [Semantic Versioning](https://semver.org/) and match each plugin's `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` `version` field.

## qwen-image

### 1.0.0 — 2026-08-06

- Initial release: image generation and editing against Alibaba Cloud Model Studio's Qwen-Image family (`qwen-image-3.0-pro`, `qwen-image-2.0-pro`, `qwen-image-2.0`, `qwen-image-max`, `qwen-image-plus`, `qwen-image`, `qwen-image-edit-max`, `qwen-image-edit-plus`, `qwen-image-edit`) via the synchronous `multimodal-generation/generation` endpoint
- `scripts/qwenimage.py` — stdlib-only Python, no `pip install`; `generate`/`edit`, up to 3 input images fused per edit, variants via `--n` returned in a single request, never overwrites an existing output, appends every render to a gitignored `.qwenimage.jsonl` with the full prompt, parameters and `request_id`
- Per-model limits validated locally before any request is sent, so a wrong model/size/`n` combination costs nothing; automatic backoff on `Throttling.RateQuota`, which Model Studio workspaces hit easily
- `reference/prompting.md` — checklist, templates and failure modes written around Qwen's own behaviour: the server-side `prompt_extend` rewriter, the real `--negative-prompt` parameter, `--seed` iteration, and CJK text rendering
- `reference/api.md` — endpoints, per-model size/`n` matrix, request/response shapes and error codes, flagging where the published docs disagree with the live API
- Positioned as the alternative to `nano-banana`: triggers on Qwen/Model Studio/DashScope by name, on a rejected nano-banana render, on in-image text (especially Chinese/Japanese/Korean), and on outputs above 2048px per side
- Verified against the live Singapore endpoint: `size` is `width*height` (confirmed by reading the PNG header), output is 8-bit RGB PNG with no alpha, `usage` returns `output_width`/`output_height`/`output_image_count` rather than the documented `width`/`height`/`image_count`, `qwen-image-3.0-pro` accepts area up to 2560² rather than the documented 2048², and `qwen-image-edit` silently ignores an out-of-range `n` — billing every requested render while returning one image

## nano-banana

### 1.0.0 — 2026-08-01

- Initial release: image generation, editing, and multi-image composition against Google's Gemini image models (`gemini-3.1-flash-lite-image`, `gemini-3.1-flash-image`, `gemini-3-pro-image`) via the `v1beta/interactions` endpoint
- `scripts/nanobanana.py` — stdlib-only Python, no `pip install`; `generate`/`edit`/`compose`, variants via `--n`, never overwrites an existing output, appends every render to a gitignored `.nanobanana.jsonl` with the full prompt and cost
- `reference/prompting.md` — prompt-writing checklist, principles, and templates for heroes, og:images, icons, mockups, textures, avatars, and in-image text, plus editing patterns and a failure-mode table
- `reference/api.md` — models, sizes, aspect ratios, request/response shapes, pricing, error codes, and a list of four points where Google's published docs disagree with the live API
- Retina-driven size routing and text-aware model routing baked into `SKILL.md`; image bytes are kept on disk and never routed through the agent's context
- Costs are computed from the `usage` block the API returns rather than a static price table, so `--thinking high` and `--grounding` are reflected in the reported price
- Verified against the live API: output is JPEG-only on every model (no PNG, no alpha), sizes are `512`/`1K`/`2K`/`4K` rather than the documented `512px`, and `lite` rejects 2K and 4K

## superglue

### 1.1.0 — 2026-07-13

- Add Codex plugin manifest (`plugins/superglue/.codex-plugin/plugin.json`)
- Add native Codex marketplace manifest (`.agents/plugins/marketplace.json`) at the repo root, so `codex plugin marketplace add` / `codex plugin add` resolve directly instead of falling back to Claude's manifest
- Verified clean install via both `claude plugin install superglue@nadiar-skills` and `codex plugin add superglue@nadiar-skills`

### 1.0.0 — 2026-07-13

- Initial release: Superglue 2.0 (thoughtbot's Rails+React+Redux framework, v2/beta) reference skill — navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, deferments, decision guide, and a v1-to-v2 migration cheat sheet
- Published as the first plugin in the `nadiar-skills` Claude Code marketplace
- Validated with skill-creator's eval loop: 100% vs 45% pass rate against a no-skill baseline across 4 test cases (`plugins/superglue/skills/superglue/evals/evals.json`)
