# Changelog

Notable changes to plugins in this marketplace, grouped by plugin. Versions follow [Semantic Versioning](https://semver.org/) and match each plugin's `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` `version` field.

## superglue

### 1.1.0 — 2026-07-13

- Add Codex plugin manifest (`plugins/superglue/.codex-plugin/plugin.json`)
- Add native Codex marketplace manifest (`.agents/plugins/marketplace.json`) at the repo root, so `codex plugin marketplace add` / `codex plugin add` resolve directly instead of falling back to Claude's manifest
- Verified clean install via both `claude plugin install superglue@nadiar-skills` and `codex plugin add superglue@nadiar-skills`

### 1.0.0 — 2026-07-13

- Initial release: Superglue 2.0 (thoughtbot's Rails+React+Redux framework, v2/beta) reference skill — navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, deferments, decision guide, and a v1-to-v2 migration cheat sheet
- Published as the first plugin in the `nadiar-skills` Claude Code marketplace
- Validated with skill-creator's eval loop: 100% vs 45% pass rate against a no-skill baseline across 4 test cases (`plugins/superglue/skills/superglue/evals/evals.json`)
