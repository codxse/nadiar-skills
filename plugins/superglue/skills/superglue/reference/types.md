# TypeScript types & the `props_template` Ruby DSL

Superglue is contract-first, not codegen-first: you hand-write TypeScript types as the UI contract (what `useContent<T>()` should return), then write the `.json.props` template to fulfill that shape. Nothing generates one side from the other.

## Runtime validation (Deepkit, experimental, dev-only)

```
rails g superglue:install --typescript --deepkit
```

Manual bundler wiring:

```js
import { esbuild as deepkitPlugin } from '@thoughtbot/superglue/deepkit'   // or vite / webpack
plugins: isDev ? [deepkitPlugin()] : []
```

The plugin AST-transforms `useContent<T>()`/`useFragment<T>()` calls, injecting a `validate` callback (formalized as `ValidateOption = { validate?: (data: unknown) => void }`) that checks the server response against your declared `T` at runtime and `console.error`s on mismatch.

```tsx
interface Post { id: number; title: string; content: string }
type PostShowProps = { header: string; post: Post }

export default function PostShow() {
  const { header, post } = useContent<PostShowProps>()
  return <div><h1>{header}</h1><li>{post.title}</li></div>
}
```

Workflow: declare the type → run the page → let the console error drive what you write in `.json.props`. **This is dev-only and experimental** — not a production guarantee, not full type generation.

## Core type surface

### JSON primitives (the base family)

```ts
JSONPrimitive = string | number | boolean | null | undefined
JSONObject    = {[key: string]: JSONValue}
JSONMappable  = JSONValue[] | JSONObject
JSONValue     = JSONPrimitive | JSONMappable
FlashState    = Record<string, JSONValue>
```

### Page/response types (the Rails → store pipeline)

```ts
SaveResponse<T> = {
  data: T; componentIdentifier: ComponentIdentifier; assets: string[]; csrfToken?: string
  fragments: FragmentPath[]; defers: Defer[]; flash: FlashState
  action: "savePage"; renderedAt: number; restoreStrategy: RestoreStrategy
}
Page<T> = SaveResponse<T> & { savedAt: number }   // a SaveResponse once actually in the store

GraftResponse<T> = {
  data: T; componentIdentifier: string; assets: string[]; csrfToken?: string
  fragments: FragmentPath[]; defers: Defer[]; flash: FlashState
  action: "graft"; renderedAt: number
  path: string            // keypath replaced
  fragmentContext?: string
}

StreamMessage = { data: JSONMappable; fragmentIds: string[]; handler: "append"|"prepend"|"update"; options: Record<string,string> }
StreamResponse = { data: StreamMessage[]; fragments: FragmentPath[]; assets: string[]; csrfToken?: string; action: "handleStreamResponse"; renderedAt: number; flash: FlashState }

PageResponse = GraftResponse | SaveResponse | StreamResponse   // union any round-trip resolves to; superglue_rails generators handle all three for you
ParsedResponse = { rsp: Response; json: PageResponse }
```

### Fragments

```ts
FragmentPath = { id: string; path: string }        // internal: locates a fragment inside a PageResponse
FragmentRef<T = unknown, Present extends boolean = false> = { __ref: true; __id: string; __type?: T; __present?: Present }

// the type YOU use in page-prop contracts:
Fragment<T, Present = false> = Present extends true ? T & {__id: string} : (T & {__id: string}) | undefined
```

```tsx
type PageData = {
  cart: Fragment<{ items: Item[]; totalCost: number }, true>
  user?: Fragment<{ name: string; email: string }>   // optional fragment
}
const content = useContent<PageData>()
const cart = content.cart   // resolves the fragment ref to actual data

// nesting
interface Post { title: string; author: Fragment<Author, true>; comments: Array<Fragment<Comment, true>> }
```

`Unproxy<T>` — inverse utility, converts `Fragment<U,P>` back to `FragmentRef<U,P>` recursively; what `unproxy()` and `useUpdateFragment` use internally to type-safely mutate.

### Store shape

```ts
SuperglueState = { currentPageKey: string; search: Record<string, string|undefined>; csrfToken?: string; assets: string[] }
RootState<T = JSONMappable> = { superglue: SuperglueState; pages: AllPages<T>; fragments: AllFragments; flash: FlashState; [name: string]: unknown }
AllPages<T> = Record<PageKey, Page<T>>       // "you are encouraged to mutate the Pages in this store"
AllFragments = Record<string, JSONMappable>
SuperglueStore = EnhancedStore<RootState, Action, Tuple<[StoreEnhancer<{dispatch: Dispatch}>, StoreEnhancer]>>   // a Redux Toolkit configureStore result
Dispatch = ThunkDispatch<RootState, ExtraArgument, Action>
```

`RootState` has an index signature specifically so your app can add its own top-level slices alongside `superglue`/`pages`/`fragments`/`flash`.

### Scalar aliases

```ts
PageKey             = string   // pathname + search, e.g. "/posts?foobar=123"
ComponentIdentifier = string
Keypath             = string   // e.g. "data.body.posts.0.title" or "data.body.posts.post_id=foobar.title"
NavigationAction    = "push" | "replace" | "none"
RestoreStrategy     = "fromCacheOnly" | "revisitOnly" | "fromCacheAndRevisitInBackground"
```

### Results

```ts
Result = { hasError: false; pageKey: string; page: PageResponse; redirected: boolean; rsp: Response; fetchArgs: FetchArgs; componentIdentifier?: string; needsRefresh: boolean }
VisitResult extends Result { navigationAction: NavigationAction }
ErrorResult = { hasError: true; response: Response }
```

### App bootstrap types

```ts
CreateAppArgs = {
  initialPage: SaveResponse    // from window.SUPERGLUE_INITIAL_PAGE_STATE
  baseUrl: string
  path: string                 // location.pathname+search+hash
  mapping: Record<string, React.ComponentType>
  buildVisitAndRemote: BuildVisitAndRemote
  history?: History
  cable?: Consumer              // enables useStreamSource
  devTools?: boolean            // default false
}
CreateAppResult = { Provider: ComponentType<ProviderProps>; Outlet: ComponentType; ujs: Handlers }
ProviderProps = { children?: React.ReactNode }
Handlers = { onClick: (e: MouseEvent) => void; onSubmit: (e: FormEvent) => void }

BuildStore(initialState: RootState, reducer: {
  superglue: (state: SuperglueState, action: Action) => SuperglueState
  pages: (state: AllPages, action: Action) => AllPages
  fragments: (state: AllFragments, action: Action) => AllFragments
  flash: (state: FlashState, action: Action) => FlashState
}): SuperglueStore

BuildVisitAndRemote(context: BuildVisitAndRemoteContext): { visit: ApplicationVisit; remote: ApplicationRemote }
BuildVisitAndRemoteContext = {
  navigateTo: NavigateTo
  visit: (path: string, options?: VisitProps) => Promise<VisitResult | ErrorResult>
  remote: (path: string, options?: RemoteProps) => Promise<Result | ErrorResult>
}
```

### Navigation runtime types

```ts
NavigateTo = (path: Keypath, options?: { action?: NavigationAction; updateContent?: (draft: JSONMappable) => void }) => boolean
NavigationContextProps = { navigateTo: NavigateTo; copyTo: CopyTo; visit: ApplicationVisit; remote: ApplicationRemote; pageKey: string; search: Record<string,string|undefined> }
CopyTo = (path: string) => void
HistoryState = { superglue: true; pageKey: string; posX: number; posY: number }
BasicRequestInit = { headers?: {[key:string]: string} } & RequestInit
```

### Thunks (Redux internals, occasionally useful to type against)

```ts
VisitCreator = (input: string | PageKey, options?: VisitProps) => VisitMetaThunk
RemoteCreator = (input: string | PageKey, options?: RemoteProps) => MetaThunk
MetaThunk = ThunkAction<Promise<Result | ErrorResult>, RootState, ExtraArgument, Action>
VisitMetaThunk = ThunkAction<Promise<VisitResult | ErrorResult>, RootState, ExtraArgument, Action>
DefermentThunk = ThunkAction<Promise<void[]>, RootState, ExtraArgument, Action>
```

### Deferred data

```ts
Defer = { url: string; type: "auto" | "manual"; path: string; successAction: string; failAction: string }
```

### Redux action types

```ts
interface GraftingSuccessAction extends Action { type: string; payload: { pageKey: string; keyPath: string } }
interface GraftingErrorAction extends Action { type: string; payload: { pageKey: string; url: string; err: unknown; keyPath: string } }
type FetchArgs = [string, BasicRequestInit]
```

`GraftingSuccessAction`/`GraftingErrorAction` fire on resolve/failure of a digging operation (surfaces as `Result.fetchArgs`).

## `props_template` DSL (Rails side)

`props_template` (gem, Jbuilder-like, direct-to-Oj). `superglue_rails` builds `.json.props` views on top of it.

```ruby
gem 'props_template'
require 'props_template/core_ext'   # needed for Array#member_at/member_by (digging on plain arrays)
```

### Core verbs

```ruby
json.set! :firstName, 'David'   # or: json.firstName 'David'  => {"firstName": "David"}

json.details do    # block = internal node (only blocks support partials/defer/cache/dig)
end

json.extract! user, :id, :email, :first_name
json.extract! user, :id, [:first_name, :firstName], [:last_name, :lastName]

json.array! collection, {...options} do |item|
  json.firstName item[:name]
end
```

Arrays need `member_at(index)`/`member_by(attr, value)` to support digging:

```ruby
class ObjectCollection < SimpleDelegator
  def member_at(index); at(index); end
  def member_by(attr, val); find { |e| e[attr] == val }; end
end

class ApplicationRecord < ActiveRecord::Base
  def self.member_at(index); offset(index).limit(1).first; end
  def self.member_by(attr, value); find_by(Hash[attr, value]); end
end
```

Superglue-specific, wired once in `application.json.props`:

```ruby
json.defers json.deferred!      # metadata for all deferred nodes: [{url, path, type}]
json.fragments json.fragments!  # metadata for all fragment nodes
```

### Options (block form only)

**Partials:**
```ruby
json.one_post partial: ["posts/blog_post", locals: {post: @post}] do
end

json.posts do
  json.array! @posts, partial: ["posts/blog_post", locals: {foo: 'bar'}, as: 'post'] do
  end
end
```

**Fragments** (identity across pages/updates — see `state.md`):
```ruby
json.header partial: ["profile", fragment: "header"] do
end
```
Array form needs `fragment:` as a lambda (see `state.md`).

**Caching** (internal nodes only, fast `push_json` path):
```ruby
json.author(cache: "some_cache_key") { json.firstName "tommy" }
json.profile(cache: "cachekey", partial: ["profile", locals: {foo: 1}]) { }

# arrays, via Rails.cache.read_multi
opts = { cache: ->(i){ ['a', i] } }
json.array! [4,5], opts { |x| json.top "hello#{x}" }
```

**Deferment:**
```ruby
json.dashboard(defer: :manual) { sleep 10; json.someFancyMetric 42 }
json.dashboard(defer: [:manual, placeholder: {}]) { sleep 10; json.someFancyMetric 42 }
json.dashboard(defer: :auto) { sleep 10; json.someFancyMetric 42 }
```
See `state.md` for the full auto-vs-manual semantics.

### Digging

```ruby
json.data(dig: traversal_path) do
  json.details do
    json.employment { }
    json.personal { json.name 'james'; json.zipCode 91210 }
  end
end
json.footer { }   # renders regardless; only the dig:-enabled branch is pruned/kept selectively
```
Only works on **blocks**, never scalar leaves. Missing target keypath ⇒ that whole branch is dropped from output (siblings unaffected).

### Layouts

Single layout, `app/views/layouts/application.json.props`. **Rendering order is inverted** from `.erb`: the layout runs first, your template runs at `yield json`:
```ruby
json.data { yield json }
json.header { json.greeting "Hello" }
json.flash flash.to_h
```
`ActionController::API`-based controllers silently skip layouts unless you `include ActionView::Layouts` — no error, just missing data:
```ruby
module Api
  class BaseController < ActionController::API
    include ActionView::Layouts
    layout "api"
  end
end
```

### Key format (camelize)

Default: **no transformation** (`key.to_s`) — intentional, for JS-side diggability match. To get idiomatic camelCase TS interfaces without hand-camelizing every key, add a global initializer:
```ruby
Props::BaseWithExtensions.class_eval do
  def key_format(key)
    @key_cache ||= {}
    @key_cache[key] ||= key.to_s.camelize(:lower)
  end
  def result!
    result = super
    @key_cache = {}
    result
  end
end
```
Without this, your TS interfaces must match Rails' raw (likely snake_case) keys exactly.

### Escaping

Oj runs in `mode: :rails` — HTML/XML-escapes characters like `&`/`<` automatically.

## Minimal typed end-to-end example

```ruby
# app/views/posts/show.json.props  (camelize initializer active)
json.header "Hello"
json.post do
  json.id 100
  json.title "This is a title"
  json.content "This is a body"
end
```

```tsx
// app/javascript/pages/posts/show.tsx
import { useContent } from '@thoughtbot/superglue'

interface Post { id: number; title: string; content: string }
type PostShowProps = { header: string; post: Post }

export default function PostShow() {
  const { header, post } = useContent<PostShowProps>()
  return (
    <div>
      <h1>{header}</h1>
      <ul><li>{post.id}</li><li>{post.title}</li><li>{post.content}</li></ul>
    </div>
  )
}
```

For a fragment/normalized variant: `post: Fragment<Post, true>` on the TS side, `partial: [..., fragment: "..."]` on the Rails side — Superglue stores `post` in the `fragments` slice and resolves it transparently through `useContent`.

## Gotchas

- Deepkit validation is experimental, dev-only, never a production guarantee — and it only checks what you assert in `T`, it doesn't derive `T` for you.
- Without the camelize initializer, TS interfaces must match Rails' raw key casing exactly.
- Digging (`dig:`) only works on block nodes, never scalar leaves — common source of "why didn't my partial update work" bugs.
- Arrays need `member_at`/`member_by` for digging; even with `core_ext`, `member_by` raises `NotImplementedError` unless you implement it.
- Fragment lambdas: `fragment:` on `json.array!` must be a lambda, not a string.
- Layout rendering order is inverted (layout first, `yield json` triggers the template) — opposite of the usual ERB mental model.
- `Result.hasError`/`ErrorResult.hasError` only discriminates HTTP-level (non-2xx) failures — network errors, parse errors, aborts, and thrown bugs reject the promise instead and need a separate catch.
