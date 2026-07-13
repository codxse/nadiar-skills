# Navigation

Superglue behaves like a multipage app that intercepts navigation. There is one interception model — UJS data attributes calling into `visit`/`remote` — not separate router/frame/stream concepts.

- **`visit`** — full page transition: fetch, save, swap page component, update browser history/URL/scroll. Only one `visit` in flight at a time; a new one aborts the previous.
- **`remote`** — background update: fetch, save into the store. Does **not** navigate or touch history. Multiple concurrent `remote` calls are fine.

Both wrap `fetch` and are exposed to React via `NavigationContext`. Superglue ships **no** `<Link>`/`<VisitButton>` component — build your own on top of these.

```tsx
import { useContext } from 'react'
import { NavigationContext } from '@thoughtbot/superglue'

const { remote, visit, navigateTo, pageKey, search } = useContext(NavigationContext)
```

## UJS data attributes

### `data-sg-visit`

```html
<a href='/posts/new' data-sg-visit />
<form action='/some_url' data-sg-visit />
```

Click/submit intercepted → JSON request to the `href`/`action` → save payload → swap page component → update history + scroll position.

**Caveat**: no way to set an HTTP method on a `data-sg-visit` `<a>` — it's always GET-style. For POST/PUT/DELETE "links", build a form styled like a link using `form_props` (see `forms.md`), not a plain anchor.

### `data-sg-remote`

```jsx
<a href='/posts?page_num=2&props_at=data.body.postsList' data-sg-remote>
  Next Page
</a>

<form action="/posts" method="GET" data-sg-remote>
  <input type="search" .... />
</form>
```

Updates the **current page** without navigating. Difference from calling `remote()` directly in JS: `data-sg-remote` automatically targets the *current page* as the save key. A bare `remote()` call instead derives the save `pageKey` from the response's own URL unless you pass one explicitly. Pair with `props_at` digging (see `state.md`) to fetch just the fragment of JSON you need — this combo is Superglue's answer to what Turbo Frames does.

### `data-sg-replace`

Not core — generated into your `application_visit.js` by the installer as an example of extending UJS. Pairs with `data-sg-visit` to use `history.replaceState` instead of `pushState`, useful for filter/search controls where you don't want to spam history entries.

### Inventing your own `data-sg-*` attributes

The triggering element's full `dataset` is passed through to your `ApplicationVisit`/`ApplicationRemote` wrapper as `options.dataset`, so you can add arbitrary `data-sg-*` attributes and branch on them there (e.g. `data-sg-hide-progress` for opting a specific link out of a progress bar — see `setup.md`).

## JS API

### `visit(input, options): Promise<VisitResult | ErrorResult>`

```ts
VisitProps = Omit<BaseProps, "signal"> & {
  placeholderKey?: string   // defaults to currentPageKey; shown optimistically while the request resolves
  revisit?: boolean         // GET + true: no history change unless redirected (then "replace")
  method?: string
  body?: BodyInit
  headers?: {[key:string]: string}
  beforeSave?: BeforeSave<JSONMappable>
}
```

### `remote(input, options): Promise<Result | ErrorResult>`

```ts
RemoteProps = BaseProps & {
  method?: string
  body?: BodyInit
  headers?: {[key:string]: string}
  beforeSave?: BeforeSave<JSONMappable>
  pageKey?: string   // where to save; else derived from the response's own URL
  force?: boolean    // bypass componentIdentifier mismatch check
}
```

**Gotcha**: the response's `componentIdentifier` must match the target page's or Superglue throws `MismatchedComponentError`. Pass `force: true` only when you know the shapes are compatible (e.g. grafting a shared header fragment into an unrelated page).

### `beforeSave` — merge incoming data before it's stored

```ts
BeforeSave<U extends SaveResponse<T> | GraftResponse<T>>(prevPage: Page<T> | undefined, nextPage: U): U
```

`prevPage` is `undefined` on first visit (nothing cached yet). Classic use: infinite scroll / pagination merge.

```js
const beforeSave = (prevPage, nextPage) => {
  const prevMessages = prevPage?.data?.messages ?? []
  nextPage.data.messages = [...prevMessages, ...nextPage.data.messages]
  return nextPage
}

remote("/posts", { beforeSave })
```

**Gotcha**: if you concatenate arrays of fragments in `beforeSave`, add `key:` to the Rails-side `json.array!` fragment partial so Superglue can identify fragments in the merged array — otherwise index-based fragment arrays are frozen to prevent silent corruption:

```ruby
json.array!(partial: ["post", fragment: ->(post){"post-#{post.id}"}, key: :id]) do
end
```

### `ApplicationVisit` / `ApplicationRemote` — what you actually implement

These are what you write in `application_visit.js`; UJS and page components call these, not the raw primitives.

```ts
ApplicationVisit(input: string, options?: VisitProps & {dataset?: {[name:string]: string|undefined}}): Promise<VisitResult | ErrorResult>
ApplicationRemote(input: string, options?: RemoteProps & {dataset?: {[name:string]: string|undefined}}): Promise<Result | ErrorResult>
```

Guidance from the docs: terminal error branches (HTTP redirects to an error page, unexpected exceptions) should return a never-settling promise rather than `undefined`, so the promise chain correctly reflects "the browser is unloading" instead of resolving to garbage.

### `navigateTo(path, options?): boolean`

```ts
NavigateTo = (path: Keypath, options?: {
  action?: NavigationAction
  updateContent?: (draft: JSONMappable) => void
}) => boolean
```

`visit` is, fundamentally, fetch → save → call `navigateTo`. Exposed directly for **optimistic/local** navigation without a network round trip (e.g. instant faceted search using data you already have).

- **The target pageKey must already exist in the store**, or it throws — use `copyTo` first to prepopulate a key.
- Returns `true` on success (restores props/component/scroll), `false` if the page wasn't found, or immediately `false` if `options.action === 'none'`.

```js
const nextPageKey = pageKey + "?active=true"
navigateTo(nextPageKey, { action: 'push' })
```

### `copyTo(path): void`

Clones current page state to a new pageKey so `navigateTo` (or a subsequent digging fetch) can target it, while preserving the original for back-button navigation.

### `NavigationContext` shape

```ts
NavigationContextProps = {
  navigateTo: NavigateTo
  copyTo: CopyTo
  visit: ApplicationVisit
  remote: ApplicationRemote
  pageKey: SuperglueState["currentPageKey"]   // pathname + search, no hash
  search: SuperglueState["search"]             // parsed query string of current URL
}
```

## Results & errors

```ts
Result = {
  hasError: false
  pageKey: string
  page: PageResponse
  redirected: boolean
  rsp: Response
  fetchArgs: FetchArgs
  componentIdentifier?: string
  needsRefresh: boolean
}
VisitResult extends Result { navigationAction: NavigationAction }
ErrorResult = { hasError: true; response: Response }
NavigationAction = "push" | "replace" | "none"
```

`hasError` is the discriminant — narrow on it:

```ts
const result = await visit('/posts')
if (result.hasError) {
  // ErrorResult — result.response
} else {
  // VisitResult — result.navigationAction, result.page, ...
}
```

Non-HTTP failures (network error, parse error, abort, thrown bug) **reject the promise** instead of resolving to `ErrorResult` — catch these separately.

## History / back-forward

```ts
HistoryState = { superglue: true; pageKey: string; posX: number; posY: number }

RestoreStrategy = "fromCacheOnly" | "revisitOnly" | "fromCacheAndRevisitInBackground"
```

- `fromCacheOnly` — use only the cached page.
- `revisitOnly` — ignore cache, refetch; `NavigationAction` is `none` on 200, `replace` if redirected.
- `fromCacheAndRevisitInBackground` — show cache immediately, refetch in the background to refresh it.

`restoreStrategy` is set **server-side per response** and governs behavior on history pop (back/forward) — it's a different mechanism from optimistically calling `navigateTo` before a `visit` resolves (below).

## Faking Turbo's "navigate immediately" feel

Default Superglue `visit` always waits for the response before transitioning (unlike Turbo, which optimistically transitions when possible). To replicate that in `application_visit.js`:

```js
import { urlToPageKey } from '@thoughtbot/superglue'

const appVisit = (path, {dataset, ...options} = {}) => {
  const pageKey = urlToPageKey(path)
  navigateTo(pageKey)   // succeeds only if this page is already cached
  return visit(path, options)
    // ...
}
```

## Recipe: SPA pagination

```ruby
# controller
def index
  @posts = Post.all.page(params[:page]).per(10).order(created_at: :desc)
end
```

```ruby
# index.json.props
json.posts do
  json.list do
    json.array! @posts do |post|
      json.id post.id
      json.body post.body
    end
  end

  json.pathToNextPage path_to_next_page(@posts, props_at: 'data.posts')
  json.pathToPrevPage path_to_prev_page(@posts, props_at: 'data.posts')
end
```

```jsx
const { posts, pathToNextPage, pathToPrevPage } = useContent()
// ...
{pathToPrevPage && <a href={pathToPrevPage} data-sg-visit>Prev Page</a>}
{pathToNextPage && <a href={pathToNextPage} data-sg-visit>Next Page</a>}
```

`path_to_next_page`/`path_to_prev_page` (Kaminari) return `nil` at the ends. Adding `props_at: 'data.posts'` to those paths means clicking next/prev only refetches the list, not the rest of the page (the Turbo-Frames-equivalent optimization).

## Recipe: infinite scroll

Builds on pagination above; no built-in component — combine `remote` + `beforeSave` with a scroll-detection lib (e.g. `react-infinite-scroll-hook`):

```jsx
import { useContent, NavigationContext } from '@thoughtbot/superglue'
import useInfiniteScroll from 'react-infinite-scroll-hook'

const { posts, pathToNextPage } = useContent()
const { remote, pageKey } = useContext(NavigationContext)
const [loading, setLoading] = useState(false)
const hasNextPage = !!pathToNextPage

const beforeSave = (prevPage, receivedPage) => {
  receivedPage.data.posts = prevPage.data.posts + receivedPage.data.posts
  return receivedPage
}

const loadMore = () => {
  setLoading(true)
  remote(pathToNextPage, { pageKey, beforeSave }).then(() => setLoading(false))
}

const [sentryRef] = useInfiniteScroll({ loading, hasNextPage, onLoadMore: loadMore })
```

Note `pageKey` is passed explicitly so the fetched next page's posts merge into the **current** page's `data.posts`, instead of being saved under a new key — the manual equivalent of what `data-sg-remote` does automatically for UJS-triggered elements.

## vs. Hotwire Turbo — explicit comparison

Superglue replaces the Turbo/Stimulus/Turbo-Frames/Turbo-Streams stack with one concept: UJS attributes + `visit`/`remote`.

| Turbo concept | Superglue equivalent |
|---|---|
| Turbo Drive (link/form interception, optimistic nav) | `data-sg-visit` (always waits for response — see "faking Turbo's immediate nav" above for the opt-in optimistic version) |
| Turbo Frames (scoped partial reload) | `data-sg-visit`/`data-sg-remote` + `props_at` digging |
| Turbo Streams (server-pushed DOM patches) | Super Turbo Streams (server-pushed fragment/JSON patches) — see `streams.md` |
| Stimulus controllers | Just React components/hooks — no parallel JS framework needed |

## When-to-use-what quick reference

| Situation | Use |
|---|---|
| Full navigation, URL should change | `data-sg-visit` / `visit()` |
| Partial update of current page only | `data-sg-remote` / `remote()` |
| Need a POST/PUT/DELETE "link" | Form styled as a link via `form_props` |
| Optimistic/local nav on cached data | `navigateTo()` (+ `copyTo()` to seed it) |
| Want Turbo-like instant transition | `navigateTo` before `visit` in `application_visit.js` |
| `componentIdentifier` mismatch but graft is intentional | `remote(..., {force: true})` |
| Merge incoming payload into existing store data | `beforeSave` |
| `MismatchedComponentError` thrown | Fix the mismatch, or pass `force: true` if intentional |
| `navigateTo` throws | Target pageKey isn't cached yet — `copyTo`/prepopulate first |
