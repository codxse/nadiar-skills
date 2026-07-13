---
name: superglue
description: Reference for Superglue 2.0 (thoughtbot's Rails+React+Redux framework, v2/beta) — server-rendered props via .json.props+.jsx/.tsx pairs, UJS navigation (data-sg-visit/data-sg-remote), Super Turbo Streams, form_props, fragments/state, digging, deferments. Use this whenever the project has the `superglue` gem in its Gemfile, `@thoughtbot/superglue` in package.json, `.json.props` view files, `data-sg-visit`/`data-sg-remote` attributes, or the user mentions Superglue, Super Turbo Streams, form_props, candy_wrapper, or "Hotwire-style Rails+React". Push hard to consult this before writing or reviewing any Superglue code, controller/props/component trio, navigation link, form, or real-time feature in such a project. Do NOT use for plain Rails+React apps that don't use Superglue, for Hotwire/Turbo-only apps, or for Superglue 1.x codebases without checking reference/setup.md's migration table first — 2.0 is a breaking rewrite of 1.x.
---

# Superglue 2.0

Superglue is a normal server-rendered Rails app where `.json.props` templates replace `.erb`, and a paired React (TypeScript) component renders the JSON instead of Rails rendering HTML. Navigation is link/form interception (UJS), not a client-side router. There is no separate JSON API layer to design — the same routes/controllers/views that would render HTML render props instead.

One sentence per primitive, the rest of the mental model:

- **`.json.props` + `.tsx`** — a Rails view pair. The `.props` file is the "server truth" for a page's data; the `.tsx` file is pure presentation reading that data via `useContent()`. All data shaping/formatting happens in Ruby, never in the component.
- **`visit` / `remote` / UJS** — `data-sg-visit` (full navigation, changes URL) and `data-sg-remote` (background update, same URL) are how links/forms work instead of a router. See `reference/navigation.md`.
- **Fragments** — a Rails partial can be given an identity (`fragment: "id"`) so every page/component referencing it shares and updates the same normalized store entry. See `reference/state.md`.
- **Digging (`props_at`)** — fetch just a keypath subtree of a page's props instead of the whole page. Powers deferments, modals, tabs, infinite scroll. See `reference/state.md`.
- **Super Turbo Streams** — ActionCable broadcasts that patch fragments in every connected client's store (JSON analogue of Hotwire's Turbo Streams). See `reference/streams.md`.
- **`form_props`** — a `form_with` fork that emits `{props, extras, inputs}` JSON instead of HTML `<form>` tags, for React form components. See `reference/forms.md`.

## This is v2 (beta) — do not mix in v1 patterns

Superglue 2.0 is a **near-total breaking rewrite** of 1.x. Most Superglue content you may recall (blog posts, older tutorials, your own training data) is 1.x and will be subtly or badly wrong here. If you're ever unsure which version an example belongs to, assume 1.x-shaped code is wrong for this project. Load-bearing differences:

- Entry point is `createApp({...}) -> { Provider, Outlet, ujs }`, **not** `<Application store={store} .../>`. You attach `ujs.onClick`/`ujs.onSubmit` yourself; there is no more app-managed store you construct by hand.
- Fragments changed shape: `{ __id: "..." }` (double underscore), a `fragments` slice in the store, and hooks `useFragment`/`useUpdateFragment` — not v1's `{ type, path }` tagging.
- `flash` is a first-class store slice (`useFlash()`/`useSetFlash()`), not something you wire up yourself.
- Streaming (Super Turbo Streams, `useStreamSource`) is new in v2 — didn't exist in v1.
- Config is `setConfig()`/`getConfig()` functions, not a mutable `config` object.

Full before/after table: `reference/setup.md` (§ v2 migration).

**Installing it**: the beta is not what plain `gem "superglue"` / `npm install @thoughtbot/superglue` resolves to (those give you the 1.x `latest`). You need the `beta` channel explicitly — see `reference/setup.md` for exact commands and how to check you're not accidentally on 1.x.

## Decision guide

Use these tables to pick the right primitive before writing code. Full API/signatures are in the linked reference file — this table is for *which one*, the reference is for *how*.

### Navigation — which mechanism?

| Situation | Use | Why |
|---|---|---|
| Full page change, URL should update | `data-sg-visit` on `<a>`/`<form>` | Standard nav; Superglue fetches, saves, swaps component, updates history |
| Update just part of the current page, URL unchanged | `data-sg-remote` on `<a>`/`<form>` | AJAX-style; auto-targets current page as save key |
| Need POST/PUT/DELETE styled as a link | A `form_props` form styled to look like a link | UJS links can't carry an HTTP method — this is the one thing Turbo could do that Superglue explicitly can't via `<a>` |
| Instant local nav using data already fetched (facets, filters) | `navigateTo()` (+ `copyTo()` to seed the target key first) | No network round-trip, but the target pageKey must already exist in the store |
| Want Turbo's "navigate immediately, fetch in background" feel | Call `navigateTo` before `visit` inside your `application_visit.js` wrapper | Default Superglue `visit` always waits for the response first; this is the opt-in way to fake optimism |
| Merging paginated/streamed results into existing data (infinite scroll) | `beforeSave` callback on `visit`/`remote` | Runs before the response is saved to the store |

### State — where does this data live?

| Situation | Use | Why |
|---|---|---|
| Data only this page needs, no cross-page sync | Plain nested prop in `.json.props` | Simplest; default choice |
| Same data needed on every page (header, nav), never updated live | Shared partial rendered into the layout | Duplicated per page in the store, but zero extra machinery |
| Same data instance referenced from multiple pages/components, must update everywhere at once (cart count, live comment count) | **Fragment** (`partial: [..., fragment: "id"]`) | Normalized once in the `fragments` slice; any `useUpdateFragment`/stream broadcast to that id updates every consumer |
| A subtree is expensive/optional and not needed at first paint | `defer: :auto` | Placeholder renders immediately, Superglue auto-fetches the real value via digging |
| A subtree should only load on explicit user action (tab, expand) | `defer: :manual` | Placeholder renders; you fire the same digging fetch yourself on the triggering event |
| Ad hoc partial refresh (modal content, search results) not tied to a placeholder pattern | Digging directly (`props_at=...` + `data-sg-remote` or `remote()`) | The general mechanism underneath both deferment modes |

### Real-time — how do other clients find out?

| Situation | Use | Why |
|---|---|---|
| Push a change to *every* connected client | `broadcast_append_to` / `broadcast_prepend_to` / `broadcast_update_to` (or `_later` variants) on the model/controller, over ActionCable | Analogous to Hotwire's `broadcast_*_to`, but patches fragment JSON, not DOM |
| Give the *acting* user's own request immediate feedback in the same round trip as the write | `render layout: "stream"` + `broadcast_*_props` in the response template | HTTP-delivered, not ActionCable — pair this with the broadcast above so others get it live and the actor doesn't wait for their own echo |
| Local optimistic UI before the server confirms | `useUpdateFragment` immediately, then `remote(...)`, roll back in `.catch()` on failure | Not synced with streams automatically — you own the rollback logic |
| Bulk writes that shouldn't spam broadcasts (seeds, imports) | Wrap in `suppressing_superglue_broadcasts do ... end` | Avoids a broadcast per record |

### When would you actually reach for SSR (Humid)?

Only if you need first-paint HTML without JS (SEO, perceived performance on slow devices) — it's a separate, explicitly "early-stage" gem (`humid`) wrapping mini_racer. Don't reach for it by default; plain client rendering is the common case. Details + the fork-safety gotcha: `reference/setup.md`.

## Hard rules worth internalizing

1. **All data shaping happens in Ruby**, inside the `.json.props` file, never client-side. If you're tempted to `.toUpperCase()` or reshape an array in a `.tsx` file, that logic belongs in the props template instead.
2. **`useContent()`/`useFragment()` results are read-only proxies.** Never mutate them directly — always go through `useUpdateFragment`/`useUpdateContent`, which hand you an Immer draft.
3. **Never put `data-sg-visit` on a logout link.** It preserves in-memory store state across a request that's supposed to destroy the session; use a plain full-reload link.
4. **Digging/`dig:` only works on block nodes** (`json.foo do ... end`), never on scalar leaves — and expensive computation must live *inside* the block, not before it, or deferment/digging can't actually skip it.
5. **A `remote()`'s response `componentIdentifier` must match the target page's**, or Superglue raises `MismatchedComponentError`. Pass `force: true` only when you're deliberately grafting compatible-shaped content (e.g. a shared header) across differing pages.

## Reference files

Read the relevant one(s) before writing non-trivial Superglue code — they carry exact signatures, full option lists, and verbatim code patterns that are easy to get subtly wrong from memory:

- `reference/navigation.md` — `visit`/`remote`/`navigateTo`/`copyTo`, all UJS data attributes, `beforeSave`, history/back-forward/`restoreStrategy`, SPA pagination & infinite scroll recipes, explicit Turbo comparison.
- `reference/state.md` — Redux store shape, fragments (normalization, `__id` refs), all state hooks (`useContent`, `useFragment`, `useUpdateFragment`, `useUpdateContent`, `useSuperglue`, `useFlash`, `useSetFlash`), digging, deferments, shared-data-vs-fragment tradeoffs, performance (`unproxy` to avoid over-rendering).
- `reference/streams.md` — Super Turbo Streams end-to-end: `stream_from_props`, `useStreamSource`, `broadcast_*_to`/`broadcast_*_props`, `Superglue::Broadcastable`, stream response layout.
- `reference/forms.md` — `form_props` full helper API, output shape (`props`/`extras`/`inputs`), every field-helper's JSON shape, validation error handling (`useFlash` pattern), `candy_wrapper` UI-kit wrappers, unsupported-helper list.
- `reference/types.md` — full TypeScript type surface (`Fragment`, `FragmentRef`, `SaveResponse`/`GraftResponse`/`StreamResponse`, `RootState`, etc.), the `props_template` Ruby DSL (`json.set!`/`array!`/partials/cache/dig/layouts/camelize), and the experimental Deepkit runtime-validation setup.
- `reference/setup.md` — installation (incl. how to actually get the 2.0 beta, not 1.x), `application.js`/`page_to_page_mapping.js`/`application_visit.js` config, the full v2-migration cheat sheet, SSR via Humid, security notes (CSRF, logout, Devise), performance notes, and the Vite/progress-bar recipes.
- `reference/worked-example.md` — a complete feature built incrementally (Rails model → controller → `.json.props` → `.tsx` → form → flash → toggle → UJS → defer → digging → fragments → streams → optimistic update) plus the modals recipe. Use this as a template for shape/sequencing when scaffolding a new page or feature end-to-end.
