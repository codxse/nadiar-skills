# State: store shape, fragments, hooks, digging, deferments

## Redux store shape

```js
{
  superglue: { csrfToken, currentPageKey, search, assets },  // read-only, app-level
  pages: {
    '/dashboard': { /* page received from /dashboard */ },
    '/posts?foo=123': { /* page received from /posts?foo=123 */ },
  },
  fragments: {},  // normalized denormalized-partial store, keyed by fragment id
  flash: {},      // Rails flash, auto-cleared before each visit
}
```

- **`pages`** keyed by `pageKey` (pathname + query string, no hash — `/posts#foo` and `/posts` share a key).
- **`superglue`** is read-only — never write to it. Access via `useSuperglue()`.
- **`flash`** — `useFlash()` to read, `useSetFlash()` to write/clear.

### A "page" object has 4 response varieties

- **`SaveResponse`** — the standard full-page response (`action: "savePage"`): `data`, `componentIdentifier` (set via `json.componentIdentifier active_template_virtual_path`, mapped to a component in your page mapping), `defers`, `assets`, `csrfToken`, `renderedAt`, `fragments` (array of `{id, path}` locating fragments within `data`), `restoreStrategy`, `flash`.
- **`GraftResponse`** — produced by digging (`props_at` present, `action: "graft"`): `data` is just the found subtree, `path` is the keypath grafted into the store, `fragmentContext` is set instead of `path` if digging crosses into a fragment (fragments are denormalized, so path resets to `[]`).
- **`StreamResponse`** — Turbo-Stream-style (`action: "handleStreamResponse"`): `data` is an array of `StreamMessage`s. **Deferments are disabled** for stream responses/messages.
- **`StreamMessage`** — `{ data, fragmentIds, handler: "append"|"prepend"|"update", options }`.

## Fragments

A fragment is a rendered Rails partial with frontend identity — update it once by id, every page/component referencing it re-renders with the new data.

### Marking a partial as a fragment (Rails)

```ruby
json.cart(partial: ["user/cart", fragment: "userCart"]) do
end
```

With arrays, `fragment:` **must be a lambda**:

```ruby
require 'props_template/core_ext'
json.array!(@posts, partial: ["post", fragment: ->(post){"post-#{post.id}"}, key: :id]) do
end
```

### Wire format vs. denormalized client store

Wire (as sent over HTTP): the fragment's location is listed in a top-level `fragments: [{ type: "userCart", path: ["cart"] }]` array alongside normal `data`.

Client store (denormalized):

```js
{
  pages: { "/current-page": { data: { title: "Hello", cart: { __id: "userCart" } } } },
  fragments: {
    userCart: {
      items: [...], totalCost: 69.97, itemCount: 3,
      availableCoupons: { __id: "userCoupons" }  // fragments can nest
    },
    userCoupons: [{ title: "free shipping", code: "abc123" }]
  }
}
```

`{ __id: "..." }` (double underscore) is the fragment-reference marker. `useContent`/`useFragment` transparently resolve these while you traverse — no manual dereferencing.

```jsx
const content = useContent()
content.cart.items.length   // just works, fragment resolved automatically
```

### Mutating fragments

Proxies from `useContent`/`useFragment` are **read-only by design** — use `useUpdateFragment`, which hands you an Immer draft:

```jsx
const update = useUpdateFragment()

update(content.cart, cartDraft => { cartDraft.totalCost = 100 })
// equivalently, by id:
update(toFragmentRef("userCart"), cartDraft => { cartDraft.totalCost = 100 })
```

Nested fragment updates — a draft's own fragment-ref fields can be passed straight back into `update`:

```jsx
update(toFragmentRef('userCart'), cartDraft => {
  update(cartDraft.availableCoupons, couponsDraft => {
    couponsDraft[0].title = "super free shipping"
  })
})
```

## Hooks

### `useContent<T>(pageKey?): T`

No args → proxy for the **current** page's data. With a `pageKey` → proxy for a specific page's data (or `undefined` if not in the store).

```tsx
const page = useContent()
const posts = useContent('/posts')
```

### `useFragment<T>(fragmentRef, options?): T`

Proxy scoped to a **single fragment** — re-renders only when that specific fragment changes (see Performance below for why this matters).

```tsx
import { toFragmentRef } from '@thoughtbot/superglue'
const author = useFragment(toFragmentRef<Author>("author_123"))
```

### `useUpdateFragment()`

```ts
useUpdateFragment(): {
  <T, P extends boolean>(fragmentRef: FragmentRef<T,P>, updater: (draft: Unproxy<T>) => void): void
  <T extends {__id: string}>(fragment: T, updater: (draft: Unproxy<Unpack<T>>) => void): void
}
```

Accepts a `FragmentRef`, a fragment-shaped proxy/object (has `__id`), or a bare id string; `updater` gets an Immer draft, mutate freely, no return value needed.

### `useUpdateContent()`

Mutates a whole **page's** content by `pageKey` (not a single fragment):

```jsx
const updateContent = useUpdateContent()
updateContent('/posts', draft => { draft.title = "Updated Title" })
```

### `useSuperglue()`

```ts
useSuperglue(): SuperglueState   // { csrfToken, currentPageKey, search, assets }
```

### `useFlash<T>()` / `useSetFlash()`

```ts
useFlash<T = FlashState>(): T
useSetFlash(): { setFlash: (flash: FlashState) => void; clearFlash: (key?: string) => void }
```

```ts
const flash = useFlash<{ notice?: string; alert?: string }>()
const { setFlash, clearFlash } = useSetFlash()
setFlash({ notice: 'Saved!' })
clearFlash('notice')   // or clearFlash() to clear all
```

### `unproxy(proxy)`

Extracts the raw underlying value from a `useContent`/`useFragment` proxy — untracked, doesn't subscribe the caller to re-renders. Also the tool for getting a **stable reference** for `useMemo`/`useEffect` deps or `React.memo`:

```js
const rawCart = unproxy(content.cart)
const memoized = useMemo(() => expensiveCalc(rawCart), [rawCart])
```

## Digging (`props_at`)

Selective, partial fetch of a page's props tree — good for modals, tabs, async widgets, and the substrate both deferment modes are built on.

```
/some_current_page?props_at=data.rightDrawer.dailySpecials
```

Rails side:

```ruby
path = param_to_dig_path(params[:props_at])
json.data(dig: path) do
  json.header { json.search { json.results Post.search(params[:q]) } }
  json.content { json.barChart { } }
end
```

Combine with `data-sg-remote`/`remote()` for async fetch; also works with `data-sg-visit`.

### Collections: index-based vs. attribute-based selection

**Index-based** (order-dependent — can go stale if the store changes before the response returns):

```ruby
json.posts { json.array! @posts { |post| json.details { json.title post.title } } }
```
```js
remote('/dashboard?props_at=data.posts.0.details')
```
Requires `member_at(index)` on the collection — `require 'props_template/core_ext'` monkeypatches plain `Array` with this.

**Attribute-based** (stable identity — prefer this when list order/content can change between request and response):

```js
remote('/dashboard?props_at=data.posts.some_id=1.details')
```
```ruby
json.posts { json.array! @posts, key: :some_id { |post| json.details { json.title post.title } } }
```
Requires `member_by(attribute, value)` on the collection **and** `key:` on `json.array!`. For ActiveRecord, implement class methods `self.member_at(index)` / `self.member_by(attr, value)`.

### Gotcha

Digging **only works on block nodes** (`json.foo do ... end`), never scalar leaves. If the target keypath doesn't exist, the whole `dig:`-enabled branch is dropped from output (siblings still render). Response type is `GraftResponse` (see above).

## Deferments

Load slow/optional page parts after initial paint — built entirely with Ruby view syntax, no client-side orchestration needed.

### `defer: :auto`

```ruby
json.metrics(defer: [:auto, placeholder: {totalVisitors: 0}]) do
  sleep 10   # expensive
  json.totalVisitors 30
end
```

Behind the scenes: initial response has `metrics: {totalVisitors: 0}` (the placeholder) plus `defers: [{url: '/dashboard?props_at=data.metrics', type: "auto"}]`. Component renders instantly with the placeholder; Superglue auto-fires `remote("/dashboard?props_at=data.metrics")` — i.e., **deferment is digging, automated**. On resolve, the real payload is immutably grafted at `data.metrics` and the component re-renders.

Optional callbacks — Redux action types dispatched on resolve/reject:

```ruby
json.metrics(defer: [:auto, placeholder: {...}, success_action: "SUCCESS", fail_action: "FAIL"]) do
end
```

### `defer: :manual`

Same placeholder mechanics, but nothing auto-fetches — you trigger the load yourself (e.g. on tab click) with the identical digging call:

```ruby
json.metrics(defer: [:manual, placeholder: {totalVisitors: 0}]) do
  sleep 10
  json.totalVisitors 30
end
```
```js
remote("/dashboard?props_at=data.metrics")
```

Array deferment defaults to index-based identification; to identify by attribute instead, pass `key:` to `json.array!` (same mechanism as digging's attribute-based selection above).

### Perf tip: put expensive work *inside* the block

```ruby
# ❌ — runs even if this branch is skipped by digging/deferment
num_of_foo = 3.tap { sleep 4 }
json.foo { json.amount num_of_foo }

# ✅ — only runs when this branch is actually requested
json.foo do
  num_of_foo = 3.tap { sleep 4 }
  json.amount num_of_foo
end
```

## Shaping state (philosophy)

The server drives UI state — `.props` templates are a presentational layer analogous to `.erb`. All data transformation happens server-side in Ruby, **never** client-side in JS:

```ruby
# ✅
json.title @post.title.upcase
```
```js
// ❌ — don't do this
const title = content.title.toUpperCase()
```

Reasoning stated in the docs: Ruby/Rails view helpers shape state as well as or better than JS; UI patterns (headers/footers/lists) are universal enough that devs can guess the store shape without reading code; and digging means "the path IS the query" — `props_at=data.content.barChart` queries the server and grafts the response at the exact same store location, eliminating a separate API layer.

`.props` templates lack ERB's structural markup, so more inline logic in views is expected/acceptable than you'd write in `.erb`.

## Shared data vs. fragment — decision rule

For data needed on **every page** (e.g. a header), the simple option is rendering it into the layout or via a shared partial:

```ruby
# application.json.props
json.data(dig: path) do
  json.header(partial: 'shared/header') { }
  yield json
end
```

This **duplicates** the JSON node into every page's stored `data` — fine for static/simple content, but updating it once will **not** propagate to other cached pages (no referential identity).

**Decision rule**: shared-layout-data = static/duplicated-per-page, no sync needed. Fragment (`partial: [..., fragment: "id"]`) = single normalized instance, id-addressable, updates propagate everywhere it's referenced (required for "update once, reflect everywhere" UI like cart counts, or anything targeted by Super Turbo Streams).

## Performance: avoiding over-rendering

`useContent()` re-renders a component when the current page **or any fragment it read** changes — not on unrelated global state changes. But passing `content.cart` straight into a child means the *parent* (which called `useContent()`) is also subscribed to that fragment, so both re-render on change even though only the child cares.

Fix: `unproxy` the raw fragment ref, pass the raw ref down, and have the child scope its own tracking via `useFragment`:

```jsx
// parent
import { unproxy } from '@thoughtbot/superglue'
const content = useContent()
const cartRef = unproxy(content).cart
<SlidingCart cartRef={cartRef} />
```
```jsx
// child
import { useFragment } from '@thoughtbot/superglue'
const SlidingCart = ({ cartRef }) => {
  const cart = useFragment(cartRef)
  // only this component re-renders when `cart` changes
}
```

## Cross-cutting caveats

- Fragment vs. plain nested prop vs. shared-layout-data: see decision rule above.
- `useContent`/`useFragment` proxies are read-only — always mutate via `useUpdateFragment`/`useUpdateContent`.
- Digging is the substrate for both deferment modes and ad hoc partial reloads — same keypath mechanism, same `GraftResponse`/grafting behavior.
- Deferments/digging are disabled inside `StreamResponse`/`StreamMessage` contexts.
- Collection digging by index is fragile if list order/content can change before the response arrives — prefer attribute/key-based digging (`member_by` + `key:`) in that case.
- Do all data formatting server-side in Ruby, never client-side in JS — this is a stated hard convention.
