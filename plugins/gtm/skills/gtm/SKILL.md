---
name: gtm
description: Read and write Google Tag Manager configuration — accounts, containers, workspaces, tags, triggers, variables — and publish container versions, via the Tag Manager API v2. Use when the user asks to inspect, audit, create, or edit a GTM tag/trigger/variable, check what changed in a GTM workspace, create a container version, or publish a GTM container to live. Also use when the user mentions Google Tag Manager, GTM, a container ID (GTM-XXXXXXX), or tag/trigger/variable management for a specific site. Do NOT use for Google Analytics (GA4) reporting or admin — that's a separate concern — or for editing a theme/app's own inline script tags in a codebase, which never go through GTM.
---

# GTM — Google Tag Manager via the API

A single stdlib-Python script over the Tag Manager API v2. The one non-stdlib
piece is `google-auth`, used only to RS256-sign the service account's JWT —
every actual API call still goes over plain `urllib`.

## Setup — check before the first call

- **`GTM_SERVICE_ACCOUNT_KEY`** exported, pointing at the service account JSON
  key downloaded from Google Cloud Console (IAM & Admin → Service Accounts).
  On zsh, put the export in `~/.zshenv`, **not `~/.zshrc`** — zsh only reads
  `.zshrc` for interactive shells, invisible to the non-interactive shell an
  agent runs commands in.
- **That same service account must be added as a user inside GTM itself**
  (tagmanager.google.com → the container → Admin → User Management), with
  container permission **Publish** (which includes Edit). A GCP IAM role does
  nothing here — GTM access is granted entirely inside the GTM UI, not Cloud
  Console.
- **`pip install google-auth`** once. Nothing else to install.
- **Tag Manager API enabled** on the service account's GCP project (APIs &
  Services → Library → "Tag Manager API").
- **Optionally, `GTM_ACCOUNT_ID`/`GTM_CONTAINER_ID`/`GTM_WORKSPACE_ID`
  exported** for whichever property is worked on most — every command falls
  back to these instead of requiring `--account`/`--container`/`--workspace`
  on every call. Without them, those three flags are required explicitly.

## Finding IDs

Never hardcode an ID into a command when the matching env var covers it
(see Setup); if a task needs a property that has no env var yet, ask the
user to export one rather than typing the raw ID inline.

The fastest way to find an ID: open the container in the GTM UI, click into
any workspace, and read the URL —
`.../accounts/{accountId}/containers/{containerId}/workspaces/{workspaceId}/...`.
The container's public snippet ID (`GTM-XXXXXXX`) is **not** the same as
`{containerId}` — the API needs the numeric internal ID from that URL, not
the public one.

## Workflow

**1. Discover before you touch anything.** `containers list` / `workspaces
list` / `tags list` / `triggers list` / `variables list` to see what exists.
`tags get` / `triggers get` / `variables get` on a live entity of the kind
you're about to create is the fastest way to learn its exact `type` string
and `parameter` shape — see `reference/api.md` for why guessing that shape is
a bad idea.

**2. Write the body to a file**, not inline — Tag/Trigger/Variable bodies are
nested JSON (a `parameter` array, sometimes maps and lists within it) that
shell-quoting mangles. Put it in the scratchpad directory as `<name>.json`,
then pass `--body-file`.

**3. Create or update** the entity. This only ever touches the **workspace**
(a draft) — nothing is live yet, no matter which entity command you run.

**4. Before creating a version, show the user `workspaces status`** — it
lists every pending change in the workspace. Let them see the diff-equivalent
before it gets bundled into a version.

**5. `version create`** turns the workspace's current state into a numbered,
immutable container version. Still not live.

**6. `version publish` is the only command that ships to the real site.**
**Always get explicit confirmation from the user after step 4/5, right before
this call** — never chain create → publish without a pause, even when asked
to "add and publish this tag": show what's about to go out, then publish on a
clear yes. This is what "full edit + publish" access was scoped for, so treat
the confirmation as the safety boundary, not the API permission.

## Commands

(flags below are omittable via env vars — see Setup)

```
gtm.py accounts list
gtm.py containers list   --account A
gtm.py containers get    --account A --container C
gtm.py workspaces list   --account A --container C
gtm.py workspaces get    --account A --container C --workspace W
gtm.py workspaces status --account A --container C --workspace W

gtm.py tags|triggers|variables list   --account A --container C --workspace W
gtm.py tags|triggers|variables get    --account A --container C --workspace W --tag|--trigger|--variable ID
gtm.py tags|triggers|variables create --account A --container C --workspace W --body-file body.json
gtm.py tags|triggers|variables update --account A --container C --workspace W --tag|--trigger|--variable ID --body-file body.json [--fingerprint F]
gtm.py tags|triggers|variables delete --account A --container C --workspace W --tag|--trigger|--variable ID

gtm.py version create  --account A --container C --workspace W --name "..." [--notes "..."]
gtm.py version get     --account A --container C --version V
gtm.py version publish --account A --container C --version V [--fingerprint F]
```

Every call prints the API's JSON response (or an `error:` line on stderr).
Full field reference, `Parameter` object shape, known tag/trigger type
strings, and error-code meanings: `reference/api.md`.

## Rules

- **Never publish without a fresh, explicit "yes" from the user for that
  specific publish**, given right after showing them what's in the version.
  This is the one irreversible-in-practice action (the old version stays in
  history, but traffic is already served the new one).
- **Update needs the current entity, not a hand-edited guess.** `get` it
  first, edit the JSON, then `update` — never construct a Tag/Trigger/Variable
  body from memory. A `409` on update means someone (or something) changed it
  since your last `get`; re-fetch, don't retry blind.
- **Every create/update/delete/publish is appended to `.gtm-audit.jsonl`** at
  the repo root (auto-detected via the nearest `.git`), with timestamp,
  resource, IDs, and name/type where available — add it to `.gitignore`. GTM's
  own version history has the full config; this log exists to answer "did
  Claude touch this, and when" without opening the GTM UI.
- **One workspace is a shared draft.** If a human is also editing the same
  container in the GTM UI, your changes and theirs land in the same
  workspace unless you're pointed at a dedicated one — check `workspaces
  list` first if that matters for the task.
