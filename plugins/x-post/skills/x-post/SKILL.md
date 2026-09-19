---
name: x-post
description: Post and read on X (Twitter) via API v2 — post a tweet, post a multi-tweet thread with images plus alt text and a randomised delay between tweets, read a user's recent tweets, delete a tweet. Use when the user asks to post/tweet something, draft a tweet or a thread, attach an image to a tweet, read their own or someone's recent posts, check their X account, or delete a tweet. Also use when X, Twitter, tweeting, a thread, or a tweet draft is mentioned directly. Do NOT use for DMs, likes/retweets, follows, Spaces, alt text on images, or analytics beyond public_metrics on a single tweet/user — none of that is wired up here, only posting, threading, uploading images, reading, and deleting.
---

# X — post and read via API v2

Stdlib only — OAuth 1.0a signing is HMAC-SHA1, which `hmac`/`hashlib` cover natively.

## Setup — check before the first call

Four env vars, all from **console.x.com** (not developer.x.com's old UI, which now redirects there) → the app → **Keys & Tokens**:

- `X_API_KEY`, `X_API_KEY_SECRET` — consumer keys (OAuth 1.0a "API Key and Secret").
- `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` — user-context token, scoped to one X account.

On zsh, export them in `~/.zshenv`, **not `~/.zshrc`** — zsh only reads `.zshrc` for interactive shells, invisible to the non-interactive shell an agent runs commands in.

**Three traps, each found live setting this up, each one that silently breaks posting without breaking reads (or vice versa) — check all three, not just the one that seems relevant:**

1. **The app's permission must be "Read and write."** Default for any app is Read-only. Fix: app → Settings → **User authentication settings** → App permissions → **Read and write**. Type of App → **Web App, Automated App or Bot**. Callback URI and Website URL are required fields to save even though this skill never uses the OAuth 2.0 login flow they're for — any valid-looking URL works (e.g. `https://<your-site>/callback`).

2. **An Access Token generated *before* that permission change stays Read-only forever — it does not retroactively gain write access.** Symptom: posting 403s while `users me`/reads work fine. Fix: after setting Read and write, go to Keys & Tokens → **Access Token and Secret** → **Regenerate**, and re-export the new pair. The page shows the full secret exactly once; the old token stops working the moment you regenerate (nothing else needs to change — API Key/Secret are unaffected by this).

3. **The app must be attached to a *paid* Project — Free is deprecated.** Symptom: every call, including `users me`, fails with `HTTP 403 client-not-enrolled`, even though the app clearly shows some project attached in the app list. That's because an app created a while back is still attached to whatever project existed then (shows as "Standard Basic" or similar), and that project's plan has since been deprecated — attachment ≠ an active plan. Fix, cheapest option for occasional posting:
   1. **console.x.com** → **Projects** → **Create Project**, use case "Making a bot" (or whatever fits) → this creates a **Pay Per Use** project, no subscription. The create-project modal is flaky in practice: it can spin forever or silently reset to a blank form — if that happens, just retry, the values you typed often survive.
   2. **Credits** (left sidebar) → **Purchase credits** → buy e.g. $5. No minimum, no monthly commitment — see `reference/api.md` for the per-action price table. Far cheaper for occasional posting than the deprecated Free tier's replacement, **Basic**, a **$200/month** subscription.
   3. **App → Project Access → Manage** → the paid project will show a **"Move here: Development"** button (not "Connect" — the UI's own label). Click it. This is the step that's easy to miss: creating the Pay Per Use project and buying credit does *nothing* for an app that's still pointed at the old one — moving is a separate, explicit step. Confirms API keys/tokens are unchanged, only the plan/billing target moves.

Verify all three are right with the cheapest possible call: `python3 scripts/x_post.py users me` — if that 403s, it's usually trap 3 (enrollment); if reads work but `tweets post` 403s, it's trap 1 or 2 (permission or stale token).

## Workflow

**1. Draft the exact text and get a fresh, explicit yes on it before calling `tweets post`.** A tweet is public and effectively permanent (deleting removes it from the timeline, but it may already be cached, quoted, or screenshotted elsewhere) — the one irreversible-in-practice action in this skill. Never post on an implicit "sounds good" from earlier in the conversation.

**2. To match the user's voice, read their recent tweets first, don't guess:**

```
python3 scripts/x_post.py users tweets --username <handle> --count 20
```

Read the actual `text` fields. Skim for the general register — formal/casual, code-switching between languages, typical length, emoji density, whether em dashes appear at all — rather than mechanically reproducing one spotted quirk. The user's own edits in the conversation always win over an inferred pattern.

**3. Post**, preferring `--text-file` over `--text` once there's a line break or special character (shell quoting mangles both):

```
python3 scripts/x_post.py tweets post --text-file /path/to/draft.txt
```

**4. The command does not print a live tweet URL** — construct it as `https://x.com/<username>/status/<id>` from the returned `data.id` and the account's known username, and hand that back to the user as confirmation the post is live.

## Threads

A thread is a JSON file: a list of objects, each with a `text` and an optional `media` list of image paths (max 4 per tweet, in display order).

```json
[
  { "text": "First tweet." },
  {
    "text": "Second, with a before/after pair.",
    "media": [
      { "path": "before.png", "alt": "What the before shot shows." },
      { "path": "after.png", "alt": "What the after shot shows." }
    ]
  }
]
```

```
python3 scripts/x_post.py tweets thread --file thread.json --dry-run --require-alt
python3 scripts/x_post.py tweets thread --file thread.json
```

**Always `--dry-run` first.** It validates every tweet's length and every media path while posting nothing, which is the whole point: a thread that fails on tweet 3 has already left two orphans on the timeline reading as a broken half-thought.

Each tweet replies to the one before it. Between them the command sleeps a random 60–300s (`--min-delay` / `--max-delay`) so the thread doesn't land as one machine-gun burst.

**So a 5-tweet thread takes 4–20 minutes to finish.** Run it in the background instead of blocking on it, and don't start a second thread while one is in flight.

If a tweet fails partway, the error names the ids already posted and prints the remaining tweets as JSON — resume with `--reply-to <last posted id>` rather than re-running the file and duplicating the first half.

## Media

```
python3 scripts/x_post.py tweets post --text-file draft.txt --media before.png after.png --alt "..." "..."
python3 scripts/x_post.py media upload --file shot.png --alt "..."
```

Images only, via `POST /2/media/upload` (the v2 endpoint, not v1.1's `upload.twitter.com`). `media upload` alone returns a `media_id` — a safe way to check credentials, since an uploaded image is invisible until a tweet references it and expires on its own if none ever does.

**Alt text can only be set here, at upload time.** `POST /2/media/metadata` accepts a media id that no tweet references yet, and X offers no way to edit alt text once a post is live — the only remedy afterwards is deleting the post and rebuilding it, which in a thread breaks the reply chain below it. So an image posted without alt text stays that way.

`--alt` takes one text per `--media`, in the same order, and a count mismatch is refused rather than silently leaving the last image bare. In a thread file, alt text rides on each media entry. `--require-alt` turns a missing description into a refusal, which is worth passing whenever the images carry part of the argument.

X's limit is 1000 characters per description.

## Commands

```
x_post.py tweets post   --text "..." | --text-file FILE [--media FILE ...] [--reply-to ID]
x_post.py tweets thread --file THREAD.json [--min-delay S] [--max-delay S] [--reply-to ID] [--dry-run]
x_post.py tweets get    --id ID
x_post.py tweets delete --id ID

x_post.py media upload  --file FILE

x_post.py users me
x_post.py users get     --username U
x_post.py users tweets  --username U [--count N] [--include-replies]
```

`users tweets` excludes retweets always, and excludes replies unless `--include-replies` is passed — replies are usually noise when the goal is learning someone's standalone-post voice.

Every call prints the API's JSON response (or an `error:` line on stderr with a hint for 401/403/429 — see `reference/api.md` for the full list of what each means here).

## Rules

- **Never post without a fresh, explicit "yes" on the literal final text**, shown right before the call — not a paraphrase. For a thread, that means a yes on every tweet in it, since one call publishes all of them.
- **A URL in the text costs $0.200 to post instead of $0.015** (see `reference/api.md`), so where a link sits in a thread is a real cost decision, not only an editorial one.
- **`tweets post` and `tweets delete` are logged** to a gitignored `.x-audit.jsonl` at the repo root (auto-detected via the nearest `.git`), with timestamp, action, tweet id, and text for posts.
- **Reads cost money too** (Pay Per Use, not free, see `reference/api.md` for the numbers) — don't loop `users tweets`; cache the result in the conversation rather than re-fetching the same handle's tweets twice.
- **A picked username is never assumed** — `users tweets`/`users get` always take `--username` explicitly.
