# nadiar-skills

Personal skills marketplace, one plugin per skill. Each plugin ships both a **Claude Code** manifest (`.claude-plugin/plugin.json`) and a **Codex** manifest (`.codex-plugin/plugin.json`) pointing at the same underlying `skills/<name>/SKILL.md`, so the skill content is written once and works in either tool.

## Install — Claude Code

Requires [Claude Code](https://claude.com/code).

**Inside a Claude Code session:**

```
/plugin marketplace add codxse/nadiar-skills
/plugin install superglue@nadiar-skills
```

**From a shell** (equivalent, e.g. for scripting/dotfiles):

```
claude plugin marketplace add codxse/nadiar-skills
claude plugin install superglue@nadiar-skills
```

Restart Claude Code (or start a new session) so the plugin loads. Verify it's installed:

```
/plugin
# or: claude plugin list
```

**Updating**, once this repo gets new commits:

```
/plugin marketplace update nadiar-skills
/plugin update superglue
```

**Uninstalling:**

```
/plugin uninstall superglue
/plugin marketplace remove nadiar-skills
```

## Install — Codex / ChatGPT

Codex discovers skills by scanning plain directories (`.agents/skills` in a repo, or `~/.agents/skills` for every repo) — no submission/review needed for personal use. Copy (or symlink) the skill folder in:

```
git clone https://github.com/codxse/nadiar-skills.git /tmp/nadiar-skills

# repo-local (only active in this one project):
mkdir -p .agents/skills
cp -r /tmp/nadiar-skills/plugins/superglue/skills/superglue .agents/skills/superglue

# or user-global (active in every project):
mkdir -p ~/.agents/skills
cp -r /tmp/nadiar-skills/plugins/superglue/skills/superglue ~/.agents/skills/superglue
```

Codex picks it up automatically on the next run — `SKILL.md`'s `name`/`description` frontmatter is the same format Claude Code uses, so no edits are needed.

Each plugin also carries a `.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) for the formal, reviewed [Codex plugin directory](https://learn.chatgpt.com/codex/submit-plugins) path, if it's ever worth submitting there — see [Build plugins](https://learn.chatgpt.com/codex/build-plugins) for what that process involves. That's a separate, heavier flow (OpenAI org verification, review) not done as part of this repo.

## Plugins

### `superglue`

Reference skill for [Superglue 2.0](https://github.com/thoughtbot/superglue) (thoughtbot's Rails+React+Redux framework, v2/beta). Triggers when a project uses the `superglue` gem, `.json.props` files, `data-sg-visit`/`data-sg-remote`, or Superglue is mentioned directly. Covers navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, and deferments — plus a decision guide for which primitive to reach for and a v1→v2 migration cheat sheet, since 2.0 is a breaking rewrite of 1.x.

Source: `plugins/superglue/skills/superglue/`. Includes `evals/` with the test prompts and assertions used to validate it (100% vs 45% pass rate against a no-skill baseline across 4 test cases — see `evals/evals.json`).

## Adding a new skill

1. `mkdir -p plugins/<name>/skills/<name>` and put the skill there (`SKILL.md` + any `reference/`/`scripts/`/`assets/`).
2. Add a `plugins/<name>/.claude-plugin/plugin.json` (see `plugins/superglue/.claude-plugin/plugin.json` for the shape).
3. Add an entry to `.claude-plugin/marketplace.json`'s `plugins` array, `"source": "./plugins/<name>"`.
4. Add a `plugins/<name>/.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) with `"skills": "./skills/"` so Codex resolves the same skill folder.
