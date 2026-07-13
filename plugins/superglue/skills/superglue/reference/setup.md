# Setup, configuration, v2 migration, SSR, security, performance

## Installing the 2.0 beta (important — don't accidentally install 1.x)

Plain `gem "superglue"` / `npm install @thoughtbot/superglue` resolve to the **1.x `latest`** tag, not the 2.0 beta. You must pin the beta explicitly.

At time of writing: RubyGems `superglue` beta channel is at `2.0.0.beta.3`; npm `@thoughtbot/superglue` has a `beta` dist-tag (`2.0.0-beta.11`). This moves fast — verify current versions before trusting these numbers:

```bash
gem list -r superglue --prerelease          # check latest gem beta
npm view @thoughtbot/superglue dist-tags    # check latest npm beta tag
```

```ruby
# Gemfile — pin to the beta explicitly, plain `gem "superglue"` will NOT get this
gem "superglue", ">= 2.0.0.beta.3"
```
```bash
bundle install
npm install @thoughtbot/superglue@beta
# or: yarn add @thoughtbot/superglue@beta
```

**Sanity check if something looks off**: if you see `<Application>`, `store` props passed to it, or `config.baseUrl = ...` anywhere in the app or in an example you're copying from, that's 1.x — see the migration table below before trusting it.

## Installation (generators)

Prerequisite: a JS bundler via [jsbundling-rails](https://github.com/rails/jsbundling-rails) — esbuild, bun, rollup, or webpack.

```bash
rails javascript:install:esbuild   # or bun / rollup / webpack, if not already set up
```

```ruby
gem "superglue", ">= 2.0.0.beta.3"
```
```bash
bundle
rails g superglue:install                    # detects bundler, configures JSX/TSX, installs deps
rails g superglue:install --bundler=esbuild  # skip interactive prompt
rails g superglue:install --typescript                 # TypeScript project
rails g superglue:install --typescript --deepkit        # + experimental runtime type validation
```

Generated files:

```
app/javascript/
├─ application.js              # entry point: createApp(...), mounts Provider+Outlet
├─ application_visit.js        # your buildVisitAndRemote customization point
└─ page_to_page_mapping.js     # componentIdentifier -> page component
```

Scaffold a resource (controller + `.json.props` + `.tsx`/`.jsx` pair):

```bash
rails g superglue:scaffold post body:string
rails g superglue:scaffold post body:string --typescript
```

## `application.js` — entry point

```jsx
import { createConsumer } from '@rails/actioncable'
// or: import { createConsumer } from "@anycable/web"

const { Provider, Outlet, ujs } = createApp({
  baseUrl: location.origin,
  initialPage: window.SUPERGLUE_INITIAL_PAGE_STATE,   // set by your erb layout
  path: location.pathname + location.search + location.hash,
  buildVisitAndRemote,
  mapping: pageIdentifierToPageComponent,
  cable: createConsumer(),                              // enables useStreamSource
  devTools: process.env.NODE_ENV !== 'production',
});

const root = createRoot(appEl);
root.render(
  <div onClick={ujs.onClick} onSubmit={ujs.onSubmit}>
    <Provider>
      <MyLayout>
        <Outlet />
      </MyLayout>
    </Provider>
  </div>,
);
```

Config knobs: `baseUrl`, `initialPage`, `path`, `buildVisitAndRemote`, `mapping`, `cable`, `devTools`.

## `page_to_page_mapping.js`

```js
const pageIdentifierToPageComponent = {
  'posts/edit': PostsEdit,
  'posts/new': PostsNew,
  'posts/show': PostsShow,
  'posts/index': PostsIndex,
}
```

Not needed at all with bun/rollup/webpack setups that support glob imports; Vite users need it — see the Vite recipe below for an auto-generating version.

## `application_visit.js` — the customization point

```js
export const buildVisitAndRemote = ({ navigateTo, visit, remote }) => {
  // add progress bars, error handling, custom UJS attributes, analytics here
  return { visit: appVisit, remote: appRemote }
}
```

Every UJS-triggered request and every manual `visit`/`remote` call in your app funnels through whatever you return here. See the progress-bar recipe below for a worked example, and `navigation.md` for the `dataset`-based custom-attribute pattern.

## Runtime config

```ts
import { setConfig, getConfig } from '@thoughtbot/superglue'
setConfig({ baseUrl: '/api', maxPages: 10 })
const current = getConfig()   // readonly
```
`baseUrl` is normally set via `createApp` and rarely needs manual configuration outside that.

## v2 migration cheat sheet (if you see 1.x code or examples)

| Concern | v1 | v2 |
|---|---|---|
| Entry point | `<Application store={store} initialPage={...} .../>` | `createApp({...}) -> { Provider, Outlet, ujs }`; attach `ujs.onClick`/`onSubmit` yourself, wrap `<Outlet/>` in your own layout |
| Store setup | You built it yourself; `superglueReducer`/`pageReducer`/`rootReducer`/`prepareStore`/`setup` exported | Store is created internally by `createApp` — none of those exports exist anymore |
| `buildVisitAndRemote` signature | `(navigatorRef, store)` positional | `({ navigateTo, visit, remote })` single context object |
| Full-page response type | `VisitResponse` | `SaveResponse` (adds `flash`, `action: 'savePage'`) |
| Fragment wire tag | `{ type, path }` | `{ id, path }` (`FragmentPath`) — `type` renamed `id` |
| Fragment client marker | — | `{ __id: "..." }`, stored in a new `fragments` slice |
| Fragment actions | `updateFragments` | `saveFragment`, `updateFragment`, `appendToFragment`, `prependToFragment`, `removeFragments` |
| Fragment hooks | — | `useFragment(id)`, `useUpdateFragment(id)` |
| Flash | user-managed Redux slice | first-class: `useFlash()` / `useSetFlash()`, populated from `SaveResponse.flash` |
| `slices` field on response | present, for extra Redux data | removed — use flash or fragments instead |
| Streaming | doesn't exist | new: `cable` option on `createApp`, `useStreamSource`, Super Turbo Streams |
| Config | mutable `config.baseUrl = '/api'` | `setConfig({...})` / `getConfig()` functions |
| `visit`/`remote` return value | single `Meta` type | discriminated union — check `result.hasError` to narrow `ErrorResult` vs `VisitResult`/`Result` |
| Peer deps | `@reduxjs/toolkit`/`react-redux` installed separately | bundled as direct deps; new: `immer`, `uuid`, `lodash.debounce` internally; optional `@rails/actioncable` or `@anycable/web` for streaming |
| New exports | — | `webVisit`, `webRemote`, `SuperglueResponseError`, `NavigationOutlet`, `unproxy`, `copyTo` on `NavigationContext` |
| Removed exports | — | `Application`, `setup`, `prepareStore`, `superglueReducer`, `pageReducer`, `rootReducer`, `updateFragments`, `GRAFTING_SUCCESS`, `GRAFTING_ERROR` |

### Migration checklist (if upgrading an existing v1 app)

1. Replace `<Application>` with `createApp()`; render `<Provider>` + `<Outlet>` separately, with your own layout wrapping `<Outlet/>`.
2. Delete custom store setup — `createApp` handles it now.
3. Update `buildVisitAndRemote` to accept a context object, not positional args.
4. Rename `VisitResponse` → `SaveResponse` in type annotations.
5. Update fragment usage: `type` → `id`; adopt `useFragment`/`useUpdateFragment`.
6. Replace custom flash slices with `useFlash()`/`useSetFlash()`.
7. Remove `slices` from server responses.
8. Remove imports of removed exports (`superglueReducer`, `pageReducer`, `rootReducer`, `setup`, `prepareStore`).
9. Handle the new discriminated-union return types from `visit`/`remote` (`hasError` check).
10. (Optional) Add streaming via the `cable` option.

## SSR via Humid

Superglue's generators do **not** include SSR. Use [Humid](https://github.com/thoughtbot/humid) — thoughtbot's mini_racer wrapper, built for Superglue but works with any JS function returning an HTML string. **Explicitly early-stage**: "interface, behavior, and name are likely to change drastically" — don't reach for this unless you have a concrete need (SEO, perceived performance on slow devices); plain client rendering is the default.

```ruby
gem 'humid'
```
```bash
yarn add source-map-support   # for source-map support
```

```ruby
# config/initializers/humid.rb
Humid.configure do |config|
  config.application_path = Rails.root.join('app', 'assets', 'builds', 'server_rendering.js')  # separate build from application.js
  config.source_map_path = Rails.root.join('app', 'assets', 'builds', 'server_rendering.js.map')
  config.raise_render_errors = Rails.env.development? || Rails.env.test?
  config.logger = Rails.logger
  config.context_options = { timeout: 1000, ensure_gc_after_idle: 2000 }
end

if Rails.env.test?
  MiniRacer::Platform.set_flags! :single_threaded
  Humid.create_context
end
```

```ruby
# config/puma.rb
workers ENV.fetch("WEB_CONCURRENCY") { 1 }
on_worker_boot { Humid.create_context }
on_worker_shutdown { Humid.dispose }
```

**Fork-safety gotcha**: `mini_racer` is thread-safe but **not fork-safe** — only call `Humid.create_context` inside `on_worker_boot` on forked processes, never on the master process.

**Missing globals in mini_racer**: no `setTimeout`/`clearTimeout`/`setInterval`/`clearInterval`/`setImmediate`/`clearImmediate`. `console.*` delegates to the configured logger. Move any `require` of browser-dependent libraries into `useEffect` so they never load during SSR:

```js
useEffect(() => { const svgPanZoom = require('svg-pan-zoom') }, [])
```

Server entry (`app/javascript/server_rendering.js`, esbuild example):

```jsx
import { createApp } from '@thoughtbot/superglue'
import { buildVisitAndRemote } from './application_visit'
import { pageIdentifierToPageComponent } from './page_to_page_mapping'
import { renderToString } from 'react-dom/server'

require("source-map-support").install({
  retrieveSourceMap: filename => ({ url: filename, map: readSourceMap(filename) })
})

setHumidRenderer((json, baseUrl, path) => {
  const initialState = JSON.parse(json)
  const { Provider, Outlet } = createApp({ baseUrl, initialPage: initialState, path, buildVisitAndRemote, mapping: pageIdentifierToPageComponent })
  return renderToString(<Provider><Outlet /></Provider>)
})
```

Separate esbuild build config targeting `platform: "browser"` with `esbuild-plugin-polyfill-node`, plus a `shim.js` polyfilling `TextEncoder`/`TextDecoder`/`URL`/`MessageChannel`/`navigator` for the v8 isolate environment — see the `humid` repo for the full script if you actually need this.

Layout template — switch to `Humid.render`, and **do not add whitespace inside the mount div** (breaks hydration):

```erb
<% initial_state = render_props %>
<script>window.SUPERGLUE_INITIAL_PAGE_STATE=<%= initial_state %>;</script>
<div id="app"><%= Humid.render(initial_state, request.scheme + '://' + request.host_with_port, request.fullpath).html_safe %></div>
```

Client switches `createRoot` → `hydrateRoot`, guarded for non-browser bundling:

```jsx
if (typeof window !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    const { Provider, Outlet, ujs } = createApp({ /* ... */ })
    hydrateRoot(appEl, <div onClick={ujs.onClick} onSubmit={ujs.onSubmit}><Provider><Layout><Outlet /></Layout></Provider></div>)
  })
}
```

## Recipe: Vite

Any bundler works; Vite needs a couple of extra steps `vite_rails` doesn't do automatically.

```
# vite.config.mts
resolve: {
  alias: {
    "@views": path.resolve(__dirname, "app/views"),
    "@javascript": path.resolve(__dirname, "app/javascript"),
  },
},
plugins: [RubyPlugin()],
```

`application.html.erb`: `<%= vite_javascript_tag 'application.jsx' %>`.

Auto-generate `page_to_page_mapping.js` instead of maintaining it by hand:

```js
const pageIdentifierToPageComponent = {}
const pages = import.meta.glob('../views/**/*.jsx', { eager: true })

for (const key in pages) {
  const identifier = key.replace("../views/", "").split('.')[0]
  if (!pages[key].default) throw new Error(`View ${identifier} did not export default component`)
  pageIdentifierToPageComponent[identifier] = pages[key].default
}

export { pageIdentifierToPageComponent }
```

## Recipe: progress bar

No built-in component (intentionally — style/behavior is app-specific). Hook point is `application_visit.js`:

```js
import { requestStripe } from 'request-stripe'   // yarn add request-stripe

export const buildVisitAndRemote = ({ navigateTo, visit, remote }) => {
  const appRemote = (path, { dataset, ...options } = {}) => {
    const done = requestStripe()
    return remote(path, options).finally(() => done())
  }

  const appVisit = (path, { dataset, ...options } = {}) => {
    const done = requestStripe()
    return visit(path, options)
      .then(result => {
        const navigationAction = !!dataset?.sgReplace ? "replace" : result.navigationAction
        navigateTo(result.pageKey, { action: navigationAction })
        return result
      })
      .finally(() => done())
  }

  return { visit: appVisit, remote: appRemote }
}
```

Per-link opt-out via a custom `data-sg-*` attribute, arriving camelCased on `dataset`:

```html
<a href="/posts?props_at=data.header" data-sg-remote data-sg-hide-progress>Click me</a>
```
Read as `dataset.sgHideProgress` inside the wrapper.

## Security

- **In-memory state**: Superglue keeps content in memory; only a full-page HTML navigation destroys it.
- **Logout must use a plain full-reload link, never `data-sg-visit`** — an SPA-style logout leaves stale in-memory state around:
  ```
  ✅ <a href="/users/logout">Logout</a>
  ❌ <a data-sg-visit href="/users/logout">Logout</a>
  ```
- **Devise**: enable JSON as a navigational format or Devise's redirects break under Superglue's JSON requests:
  ```ruby
  # config/initializers/devise.rb
  config.navigational_formats = ["/", :html, :json]
  ```
- **CSRF**: `form_props` generates a unique CSRF token per form. For `remote`/`visit` calls (non-GET), use the page-level CSRF token from `useSuperglue()`'s state (refreshed on every page response) — also usable for custom `fetch` calls.
- Works with any standard Rails auth system (Devise, Authentication Zero, etc.) — Superglue doesn't require anything auth-specific beyond the navigational_formats note above.

## Performance

- **Frontend**: `useContent`/`useFragment` re-render a component only when the current page or the specifically-consumed fragments change — not on unrelated global state updates. See `state.md` § Performance for the `unproxy` + child-level `useFragment` pattern to stop parent components from re-rendering on changes only a child cares about.
- **Backend**: `props_template` is described as "one of the fastest JSON builders in the rubyverse" — a linked case study cites a 30% rendering-time reduction after adopting it in an API.

## Primitives — the mental model behind all of this

Superglue deliberately avoids feature-specific APIs (no infinite-scroll API, no modal library, no virtual-table component) in favor of a small composable primitive set:

| Category | Primitive |
|---|---|
| Read state | `useContent`, `useFragment` |
| Mutate state | `useUpdateFragment`, `useUpdateContent` |
| Fetch | `visit`, `remote`, `props_at` digging |
| Navigate | `copyTo`, `navigateTo` |
| Stream | `useStreamSource` (client), `broadcast_*_to` (server) |

Every recipe in this skill (modals, pagination, infinite scroll, progress bars, optimistic updates, real-time lists) is these primitives composed, not a separate feature API. When you hit a UI pattern not explicitly documented, look for which 2-3 of these primitives combine to produce it rather than expecting a dedicated helper.
