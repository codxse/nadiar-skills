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

## Install — Codex

Requires the [Codex CLI](https://github.com/openai/codex). It reads the same `.claude-plugin/marketplace.json` this repo already has, so the flow is a straight parallel to the Claude Code one — verified working with `codex-cli 0.144.1`:

```
codex plugin marketplace add codxse/nadiar-skills
codex plugin add superglue@nadiar-skills
```

Verify:

```
codex plugin list
```

**Updating / removing:**

```
codex plugin marketplace upgrade nadiar-skills
codex plugin remove superglue@nadiar-skills
```

**Alternative** for repo-scoped use without going through a marketplace at all: Codex also scans plain `.agents/skills` directories (repo-local) and `~/.agents/skills` (every repo). Copying `plugins/superglue/skills/superglue/` in there works too, since `SKILL.md`'s `name`/`description` frontmatter is the same format Claude Code uses.

Each plugin also carries a dedicated `.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) matching Codex's own manifest schema, for the formal, reviewed [Codex plugin directory](https://learn.chatgpt.com/codex/submit-plugins) path if it's ever worth submitting there — see [Build plugins](https://learn.chatgpt.com/codex/build-plugins). That submission flow (OpenAI org verification, review) is separate and not done as part of this repo.

## Plugins

### `superglue`

Reference skill for [Superglue 2.0](https://github.com/thoughtbot/superglue) (thoughtbot's Rails+React+Redux framework, v2/beta). Triggers when a project uses the `superglue` gem, `.json.props` files, `data-sg-visit`/`data-sg-remote`, or Superglue is mentioned directly. Covers navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, and deferments — plus a decision guide for which primitive to reach for and a v1→v2 migration cheat sheet, since 2.0 is a breaking rewrite of 1.x.

Source: `plugins/superglue/skills/superglue/`. Includes `evals/` with the test prompts and assertions used to validate it (100% vs 45% pass rate against a no-skill baseline across 4 test cases — see `evals/evals.json`).

## Adding a new skill

1. `mkdir -p plugins/<name>/skills/<name>` and put the skill there (`SKILL.md` + any `reference/`/`scripts/`/`assets/`).
2. Add a `plugins/<name>/.claude-plugin/plugin.json` (see `plugins/superglue/.claude-plugin/plugin.json` for the shape).
3. Add an entry to `.claude-plugin/marketplace.json`'s `plugins` array, `"source": "./plugins/<name>"`.
4. Add a `plugins/<name>/.codex-plugin/plugin.json` (see `plugins/superglue/.codex-plugin/plugin.json`) with `"skills": "./skills/"` so Codex resolves the same skill folder.
