# Worked example: a feature built incrementally

A collaborative shopping list, built up feature by feature. Use this as a template for shape/sequencing when scaffolding a new page end-to-end — each numbered step is a working checkpoint you can run before moving to the next. Finished reference repo: https://github.com/thoughtbot/shopping_list

## 0. Project setup

```bash
rails new shopping_list -j esbuild --skip-hotwire
```
Then follow `setup.md`'s installation steps (gem, generator, TypeScript flag if wanted).

## 1. Hello world (plain props, no forms/UJS/streams yet)

```bash
rails generate model Item name:string completed:boolean
rails db:migrate
```

```ruby
# config/routes.rb
root 'shopping_lists#show'
resource :shopping_list, only: [:show]
resources :items, only: [:show]
```

```ruby
# app/controllers/application_controller.rb — required once, globally
class ApplicationController < ActionController::Base
  before_action :use_jsx_rendering_defaults
end
```

```ruby
# app/controllers/shopping_lists_controller.rb
class ShoppingListsController < ApplicationController
  def show
    @items = Item.all
  end
end
```

```ruby
# app/views/shopping_lists/show.json.props
json.header do
  json.title "Family Shopping List"
end

json.items do
  json.array! @items do |item|
    json.id item.id
    json.name item.name
    json.completed item.completed
    json.detailPath item_path(item)
  end
end
```

```tsx
// app/views/shopping_lists/show.tsx
import { useContent } from '@thoughtbot/superglue'

export default function ShoppingListsShow() {
  const { header, items } = useContent()
  return (
    <div>
      <h1>{header.title}</h1>
      <ul>
        {items.map(item => (
          <li key={item.id}>
            <input type="checkbox" checked={item.completed} readOnly />
            {item.name}
            <a href={item.detailPath}>Details</a>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

```js
// app/javascript/page_to_page_mapping.js
import ShoppingListsShow from '../views/shopping_lists/show'
export const pageIdentifierToPageComponent = { 'shopping_lists/show': ShoppingListsShow }
```

```bash
rails db:seed   # after adding some Item.create!([...]) rows
bin/dev
```

## 2. Add create — a form via `form_props`

```ruby
# show.json.props — add
json.newItemForm do
  form_props(model: Item.new, url: items_path) do |f|
    f.text_field :name, placeholder: "Add item..."
    f.submit "Add"
  end
end
```

```tsx
import { Form, TextField, SubmitButton } from '@javascript/components'

const { header, items, newItemForm } = useContent()
const { form, extras, inputs } = newItemForm
// ...
<Form {...form} extras={extras}>
  <TextField {...inputs.name} />
  <SubmitButton {...inputs.submit} />
</Form>
```

```ruby
# config/routes.rb
resources :items, only: [:show, :create]
```
```ruby
# items_controller.rb
def create
  @item = Item.new(item_params.merge(completed: false))
  if @item.save
    redirect_to root_path, notice: 'Item added successfully!'
  else
    redirect_to root_path, alert: 'Failed to add item'
  end
end
private
def item_params = params.require(:item).permit(:name)
```

## 3. Flash — `useFlash`

```tsx
import { useFlash } from '@thoughtbot/superglue'
const flash = useFlash()
// ...
{flash.notice && <p>{flash.notice}</p>}
{flash.alert && <p>{flash.alert}</p>}
```

## 4. Update — toggle completed

```ruby
# inside the item loop in show.json.props
json.toggleForm do
  form_props(model: item) do |f|
    f.submit "Toggle"
  end
end
```

```tsx
{item.completed ? "✅" : "❌"}
<Form {...item.toggleForm.form} extras={item.toggleForm.extras}>
  <SubmitButton {...item.toggleForm.inputs.submit} />
</Form>
```

```ruby
resources :items, only: [:show, :create, :update]
```
```ruby
def update
  @item = Item.find(params[:id])
  @item.update!(completed: !@item.completed)
  redirect_to root_path
end
```

## 5. UJS — `data-sg-remote` / `data-sg-visit`

```tsx
<Form {...item.toggleForm.form} extras={item.toggleForm.extras} data-sg-remote>
  <SubmitButton {...item.toggleForm.inputs.submit} />
</Form>
{item.name}
<a href={item.detailPath} data-sg-visit>Details</a>
// ...
<Form {...form} extras={extras} data-sg-remote>
  <TextField {...inputs.name} />
  <SubmitButton {...inputs.submit} />
</Form>
```

Now both mutations stay on-page (AJAX) and navigation to item details doesn't full-reload — no client router involved, just Rails routes/controllers underneath.

## 6. Motivate deferment — simulate a slow endpoint

```ruby
json.totalCost do
  sleep 3   # simulate an expensive external price lookup
  json.amount "$23.45"
  json.message "Estimated total based on current prices"
end
```

Page now takes 3s. Fix with deferment:

## 7. `defer: :auto`

```ruby
json.totalCost(defer: [:auto, placeholder: { amount: "Calculating...", message: "Getting current prices" }]) do
  sleep 3
  json.amount "$23.45"
  json.message "Estimated total based on current prices"
end
```

Page now loads instantly with the placeholder; Superglue auto-fetches `GET /shopping_list?props_at=data.totalCost` in the background and grafts the result in when it resolves.

## 8. Manual digging

```tsx
<a href="/shopping_list?props_at=data.totalCost" data-sg-remote>Refresh Cost</a>
<a href="/shopping_list?props_at=data.items" data-sg-remote>Refresh List</a>
```

## 9. Super Turbo Streams — surgical HTTP-delivered updates

Give items fragment identity first:

```ruby
# show.json.props — replace the inline items array with:
json.items(partial: ["item_list", fragment: "shopping_list"]) do
end
```

```ruby
# _item_list.json.props (new)
json.array!(@items, partial: ['item', fragment: ->(item){"item_#{item.id}"}]) do |item|
end
```

```ruby
# _item.json.props (new)
json.id item.id
json.name item.name
json.completed item.completed
json.detailPath item_path(item)
json.toggleForm do
  form_props(model: item) { |f| f.submit "Toggle" }
end
```

Controller responds with the `stream` layout on success:

```ruby
def create
  @item = Item.new(item_params.merge(completed: false))
  if @item.save
    respond_to do |format|
      flash[:notice] = "Item added succesfully"
      format.html { redirect_to root_path }
      format.json { render layout: "stream" }
    end
  else
    redirect_to root_path, alert: 'Failed to add item'
  end
end

def update
  @item = Item.find(params[:id])
  @item.update!(completed: !@item.completed)
  respond_to do |format|
    format.html { redirect_to root_path }
    format.json { render layout: "stream" }
  end
end
```

```ruby
# app/views/items/create.json.props (new)
broadcast_append_props(model: @item, save_as: "item_#{@item.id}", target: "shopping_list", partial: "shopping_lists/item")
```
```ruby
# app/views/items/update.json.props (new)
broadcast_update_props(model: @item, target: "item_#{@item.id}", partial: "shopping_lists/item")
```

## 10. Super Turbo Streams — live ActionCable subscriptions

```ruby
# show.json.props — add
json.streamFromShopping stream_from_props("shopping")
json.items(partial: ["item_list", fragment: "shopping_list"]) do
end
```

```tsx
import { useContent, useStreamSource } from '@thoughtbot/superglue'

const { header, items, newItemForm, totalCost, streamFromShopping } = useContent()
const { connected } = useStreamSource(streamFromShopping)
// render connected ? '🟢 Live Updates' : '🔴 Connecting...' somewhere
```

```ruby
# app/models/item.rb
class Item < ApplicationRecord
  include Superglue::Broadcastable
end
```

```ruby
# items_controller.rb — broadcast to every OTHER client, plus stream-respond to the actor
def create
  @item = Item.new(item_params.merge(completed: false))
  if @item.save
    @item.broadcast_append_later_to("shopping", save_as: "item_#{@item.id}", target: "shopping_list", partial: "shopping_lists/item")
    respond_to do |format|
      flash[:notice] = "Item added succesfully"
      format.html { redirect_to root_path }
      format.json { render layout: "stream" }
    end
  else
    respond_to do |format|
      format.html { redirect_to root_path }
      format.json { render layout: "stream" }
    end
  end
end

def update
  @item = Item.find(params[:id])
  @item.update!(completed: !@item.completed)
  @item.broadcast_update_later_to("shopping", target: "item_#{@item.id}", partial: "shopping_lists/item")
  respond_to do |format|
    format.html { redirect_to root_path }
    format.json { render layout: "stream" }
  end
end
```

Two browser tabs open now see each other's changes instantly.

## 11. Performance — fragment refs to avoid parent re-renders

Problem: calling `useContent()` at the top of the page subscribes the *whole page component* to every fragment read anywhere below it. Fix: pass raw fragment refs down and let children scope their own subscriptions via `useFragment`.

```tsx
// show.tsx
import { useContent, useStreamSource, unproxy } from '@thoughtbot/superglue'
import ItemsList from '@javascript/components/ItemsList'

export default function ShoppingListsShow() {
  const content = useContent()
  const { header, newItemForm, totalCost, streamFromShopping } = content
  const { connected } = useStreamSource(streamFromShopping)
  const itemsRef = unproxy(content).items   // raw ref, not tracked by this component

  return (
    <div>
      <h1>{header.title}</h1>
      {/* totalCost, connected indicator, form, flash unchanged */}
      <ItemsList itemsRef={itemsRef} />
    </div>
  )
}
```

```tsx
// app/javascript/components/ItemsList.tsx (new)
import { useFragment, unproxy } from '@thoughtbot/superglue'
import { Form, SubmitButton } from '@javascript/components'

const Item = ({ itemRef }) => {
  const { name, completed, detailPath, toggleForm } = useFragment(itemRef)
  return (
    <li>
      {completed ? "✅" : "❌"}
      <Form {...toggleForm.form} extras={toggleForm.extras} data-sg-remote>
        <SubmitButton {...toggleForm.inputs.submit} />
      </Form>
      {name}
      <a href={detailPath} data-sg-visit>Details</a>
    </li>
  )
}

export default function ItemsList({ itemsRef }) {
  const items = useFragment(itemsRef)
  return (
    <ul>
      {unproxy(items).map(itemRef => <Item key={itemRef.__id} itemRef={itemRef} />)}
    </ul>
  )
}
```

Only `Item` components whose own fragment changed re-render now — `ShoppingListsShow` and unrelated `Item`s don't.

## 12. Client-side optimistic updates — `useUpdateFragment`

```tsx
import { useContext } from 'react'
import { useFragment, useUpdateFragment, NavigationContext } from '@thoughtbot/superglue'

const Item = ({ itemRef }) => {
  const { id, name, completed, detailPath, toggleForm } = useFragment(itemRef)
  const update = useUpdateFragment()
  const { remote } = useContext(NavigationContext)

  const handleToggle = (currentState) => {
    update(`item_${id}`, draft => { draft.completed = !currentState })   // optimistic
    remote(`/items/${id}`, { method: 'PATCH' }).catch(() => {
      update(`item_${id}`, draft => { draft.completed = currentState })  // rollback
    })
  }

  return (
    <li>
      {completed ? "✅" : "❌"}
      <button onClick={() => handleToggle(completed)}>Toggle</button>
      {name}
      <a href={detailPath} data-sg-visit>Details</a>
    </li>
  )
}
```

`remote(...)` here uses arbitrary HTTP methods (`PATCH`) directly, bypassing the form — useful once you're doing manual optimistic mutation instead of a UJS form submit.

---

## Recipe: Modals (same route, two controller actions, one component)

Pattern: two routes render the *same* template/component, but the `componentIdentifier` differs by action, letting the component decide whether to show a modal based on a server-set flag.

```ruby
# posts_controller.rb
def index
  @posts = Post.all
  @show_modal = false
end

def new
  @posts = Post.all
  @show_modal = true
  render :index
end
```

```js
// page_to_page_mapping.js
export const pageIdentifierToPageComponent = {
  'posts/index': PostIndex,
  'posts/new': PostIndex,   // same component for both
}
```

```ruby
# index.json.props
json.newPostPath new_post_path(props_at: 'data.createPostModal')   # dig for just the modal on click

json.createPostModal do
  json.greeting "Hello World"
  json.showModal @show_modal
end
```

```jsx
// index.js
import Modal from './Modal'

const { newPostPath, createPostModal, ...rest } = useContent()
// ...
<a href={newPostPath} data-sg-visit>New Post</a>
<Modal {...createPostModal} />
```

```jsx
// Modal.js
export default Modal = ({ greeting, showModal }) => (
  showModal && <div className="my-modal">{greeting}</div>
)
```

Navigation sequence with `data-sg-visit` + `props_at` together: copy state from `/posts` to `/posts/new` in the store → fetch only `/posts/new?props_at=data.createPostModal` → graft the result in → swap page components → change the URL. Only the modal fragment is fetched, not the whole page — this is what the docs call the Turbo-Frames-equivalent optimization applied to a modal.

## Known doc inconsistency (harmless, but don't copy verbatim)

The upstream tutorial's optimistic-update catch block calls a `set(...)` function that's never imported/defined in that snippet — it should be `update(...)` (the `useUpdateFragment()` return value), as used correctly earlier in the same example and shown correctly in step 12 above.
