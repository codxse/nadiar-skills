# Changelog

Notable changes to plugins in this marketplace, grouped by plugin. Versions follow [Semantic Versioning](https://semver.org/) and match each plugin's `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` `version` field.

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
