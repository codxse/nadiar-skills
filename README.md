# nadiar-skills

Personal Claude Code plugin marketplace. One plugin per skill, added here as it's built.

## Install

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

## Plugins

### `superglue`

Reference skill for [Superglue 2.0](https://github.com/thoughtbot/superglue) (thoughtbot's Rails+React+Redux framework, v2/beta). Triggers when a project uses the `superglue` gem, `.json.props` files, `data-sg-visit`/`data-sg-remote`, or Superglue is mentioned directly. Covers navigation (`visit`/`remote`/UJS), Super Turbo Streams, `form_props`, fragments/state, digging, and deferments — plus a decision guide for which primitive to reach for and a v1→v2 migration cheat sheet, since 2.0 is a breaking rewrite of 1.x.

Source: `plugins/superglue/skills/superglue/`. Includes `evals/` with the test prompts and assertions used to validate it (100% vs 45% pass rate against a no-skill baseline across 4 test cases — see `evals/evals.json`).

## Adding a new skill

1. `mkdir -p plugins/<name>/skills/<name>` and put the skill there (`SKILL.md` + any `reference/`/`scripts/`/`assets/`).
2. Add a `plugins/<name>/.claude-plugin/plugin.json` (see `plugins/superglue/.claude-plugin/plugin.json` for the shape).
3. Add an entry to `.claude-plugin/marketplace.json`'s `plugins` array, `"source": "./plugins/<name>"`.
