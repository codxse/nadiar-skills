# nadiar-skills: personal Claude Code + Codex plugin marketplace

Each plugin lives under `plugins/<name>/`, with the actual skill nested one level deeper at `plugins/<name>/skills/<name>/SKILL.md`.

## Gotchas & conventions

- **Dual marketplace manifests, both required at repo root**: `.claude-plugin/marketplace.json` (Claude Code) and `.agents/plugins/marketplace.json` (Codex). Codex silently falls back to reading Claude's manifest if its own is missing — don't rely on that fallback; keep both files in sync whenever a plugin is added or removed.
- **Dual plugin manifests per plugin, different `skills` field shape**: `plugins/<name>/.claude-plugin/plugin.json` uses an array (`"skills": ["./skills/<name>"]`); `plugins/<name>/.codex-plugin/plugin.json` uses a single string path to the parent dir (`"skills": "./skills/"`). Copy-pasting one into the other without adjusting the shape silently breaks that tool's plugin loading.
- **Version + CHANGELOG bump is mandatory on every content change.** Any edit under `plugins/<name>/skills/` (SKILL.md, `reference/`, etc.) must: (1) bump `version` in BOTH `plugins/<name>/.claude-plugin/plugin.json` and `plugins/<name>/.codex-plugin/plugin.json` — same semver value, kept in sync — and (2) add a new entry at the top of that plugin's section in `CHANGELOG.md`. `claude plugin update` / `codex plugin marketplace upgrade` are meaningless to end users if the version never moves. Skipping this is the single biggest mistake to avoid here.
- See `README.md` for the mechanical steps to add a new plugin (marketplace + manifest entries) — not repeated here.

> If the code contradicts anything above, the code wins — update this file in the same change.
