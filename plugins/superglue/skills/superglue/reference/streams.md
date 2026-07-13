# Super Turbo Streams

Superglue's real-time system — functionally parallel to Hotwire's Turbo Streams, but the wire payload is **JSON** (a rendered `.json.props` partial → fragment data) and the client applies it to the normalized **fragment store**, not the DOM. React re-renders because the fragment a component reads changed, not because a DOM node was patched.

## Server: subscribe (`stream_from_props`)

Equivalent of Turbo Rails' `turbo_stream_from`, called inside a `.json.props` template:

```ruby
# app/views/messages/index.json.props
json.streamFromMessages stream_from_props("messages")

json.messages(partial: ["message_list", fragment: "messages"]) do
end
```

Returns `{ channel: "Superglue::StreamsChannel", signed_stream_name: "..." }` — travels to the client as an ordinary prop.

Custom channel/params, multiple streams:

```ruby
json.streamFromRoomMessages stream_from_props("room_#{@room.id}", channel: RoomChannel, room: @room)
json.streamFromNotifications stream_from_props("notifications")
```

## Client: subscribe (`useStreamSource`)

### App bootstrap — pass a cable consumer to `createApp`

```jsx
import { createConsumer } from '@rails/actioncable'
// or: import { createConsumer } from "@anycable/web"

const { Provider, Outlet, ujs } = createApp({
  // ...
  cable: createConsumer(),
})
```

If `cable` is omitted, `useStreamSource` has nothing to subscribe with — no subscription is created.

### The hook

```ts
useStreamSource(channel: string | ChannelNameWithParams): { connected: boolean; subscription: Subscription | null }
```

```jsx
import { useContent, useStreamSource } from '@thoughtbot/superglue'

export default function MessagesIndex() {
  const { streamFromMessages, messages } = useContent()
  const { connected } = useStreamSource(streamFromMessages)

  return (
    <div>
      <h1>Messages {connected ? '🟢' : '🔴'}</h1>
      {messages().map(m => <Message key={m.id} {...m} />)}
    </div>
  )
}
```

Other call forms:

```tsx
useStreamSource('ChatChannel')
useStreamSource({ channel: 'ChatChannel', room_id: roomId })
```

Multiple streams in one component = multiple hook calls:

```jsx
useStreamSource(content.streamFromMessages)
useStreamSource(content.streamFromNotifications)
```

`subscription` (raw ActionCable subscription) is "rarely needed" — normal usage only reads `connected`.

### What actually happens on message receipt

Wire shape:

```ts
StreamMessage = {
  action: "handleStreamMessage"
  data: JSONMappable
  fragmentIds: string[]
  handler: "append" | "prepend" | "update"
  options: Record<string, string>
  fragments: FragmentPath[]
}
```

Internally, `StreamActions.handle(rawMessage)` parses this and routes to `append`/`prepend`/`update` against the named fragment(s) in the Redux store — the same store `useContent`/`useUpdateFragment` read/write. Components subscribed to that fragment re-render.

## Server: broadcast (push to all other clients)

Given partials `_message_list.json.props` / `_message.json.props`:

```ruby
# Append
@message.broadcast_append_to "messages"
@message.broadcast_append_to "chat_room", target: "room_messages"
@message.broadcast_append_to(
  [current_user, "chat_room"],
  target: "my_message_list",
  save_as: "message-#{@message.id}",
  partial: "messages/_another_message",
  locals: { highlight: true }
)
@message.broadcast_append_to_later "messages"   # async/job-queued variant

# Prepend — same option shape as append
@message.broadcast_prepend_to "messages"
@message.broadcast_prepend_to_later "messages"

# Update (replace) — most common for single-record updates
@message.broadcast_update_to "messages"
@message.broadcast_update_to "messages", target: "spotlight-message"
@message.broadcast_update_to_later "messages"
```

- Target fragment id defaults to `ActionView::RecordIdentifier.dom_id`; override with `target:`.
- `save_as:` also persists the rendered partial as its own addressable fragment before appending/prepending it elsewhere — needed if that record must later be independently `update`d.
- Every action has a `_later` variant (job-queued, async) — prefer these over blocking the triggering request/callback.

## Server: give the *acting* user immediate feedback (stream response, HTTP not ActionCable)

Use alongside a broadcast so the requester doesn't wait for their own echo over the socket:

```ruby
class MessagesController < ApplicationController
  def create
    @message = Message.create(message_params)
    respond_to do |format|
      format.html { redirect_to messages_path }
      format.json { render layout: "stream" }
    end
  end
end
```

```ruby
# create.json.props
broadcast_append_props(model: @message)
broadcast_append_props(model: @message, target: "recent_messages")
broadcast_append_props(model: @message, save_target: @message)  # save rendered partial as its own fragment first

# also available: broadcast_prepend_props, broadcast_update_props (same option shapes)
```

The `stream` layout wraps output in a `StreamResponse` (`action: "handleStreamResponse"`) and **always includes flash** — for a flash-only response with no fragment change, leave the `.json.props` template empty:

```ruby
def create
  @message = Message.new(message_params)
  if @message.save
    flash[:notice] = "Message created"
  else
    flash[:error] = "Could not create message"
  end
  render layout: "stream"   # empty create.json.props
end
```

## Model-level auto-broadcasting

```ruby
class Message < ApplicationRecord
  include Superglue::Broadcastable
  # default: broadcasts to model-name stream
end

class Article < ApplicationRecord
  include Superglue::Broadcastable
  broadcasts "articles_stream", target: "article_list"
end

class Comment < ApplicationRecord
  include Superglue::Broadcastable
  broadcasts_to ->(comment) { [comment.article, :comments] },
    fragment: ->(comment) { "article_#{comment.article_id}_comments" },
    partial: "comments/comment",
    locals: { highlight: true }
end
```

`include Superglue::Broadcastable` + `broadcasts`/`broadcasts_to` gives create/update auto-broadcasting (analogous to Turbo's `broadcasts_to`), as an alternative to calling `broadcast_*_to` manually in a controller/callback.

### Suppressing broadcasts

```ruby
suppressing_superglue_broadcasts do
  Message.create(content: "Silent message")
  @message.update(content: "Updated silently")
end
```

Use for bulk operations (seeds, imports) to avoid a broadcast storm.

## Full example (chat)

```ruby
# app/models/message.rb
class Message < ApplicationRecord
  include Superglue::Broadcastable
end
```

```ruby
# app/controllers/messages_controller.rb
def create
  @message = Message.create!(message_params)
  @message.broadcast_append_to "messages"   # pushes to everyone else

  respond_to do |format|
    format.json { render layout: "stream" }  # immediate feedback to the requester
  end
end
```

```ruby
# create.json.props
broadcast_append_props(model: @message)
```

```ruby
# index.json.props
json.streamFromMessages stream_from_props("messages")
json.messages(partial: ["message_list", fragment: "messages"]) do
end
```

```jsx
// index.tsx
import { useContent, useStreamSource } from '@thoughtbot/superglue'

export default function MessagesIndex() {
  const { streamFromMessages, messages } = useContent()
  const { connected } = useStreamSource(streamFromMessages)
  return (
    <div>
      <h1>Messages {connected ? '🟢' : '🔴'}</h1>
      {messages().map(m => <Message key={m.id} {...m} />)}
    </div>
  )
}
```

Flow: create → `broadcast_append_to "messages"` renders the partial to fragment JSON, pushes over `Superglue::StreamsChannel` on the `"messages"` signed stream → every subscriber's `useStreamSource` receives it → `StreamActions.handle` applies `append`/`prepend`/`update` to the fragment store → subscribed components re-render.

## Client-only updates (no server round trip)

Distinct from streaming — for optimistic UI / local-only state. See `state.md` for the full `useUpdateFragment`/`useUpdateContent` reference; the pattern relevant to real-time features is optimistic-update-then-sync:

```jsx
import { useContext } from 'react'
import { useContent, useUpdateFragment, toFragmentRef, NavigationContext } from '@thoughtbot/superglue'

function LikeButton({ postId }) {
  const content = useContent()
  const update = useUpdateFragment()
  const { remote } = useContext(NavigationContext)

  const toggleLike = async () => {
    update(toFragmentRef(`post_${postId}`), draft => {
      draft.liked = !draft.liked
      draft.likeCount += draft.liked ? 1 : -1
    })
    try {
      await remote(`/posts/${postId}/toggle_like`, { method: 'POST' })
    } catch {
      update(`post_${postId}`, draft => {
        draft.liked = !draft.liked
        draft.likeCount += draft.liked ? 1 : -1
      })
    }
  }

  const post = content.post
  return <button onClick={toggleLike}>{post.liked ? '❤️' : '🤍'} {post.likeCount}</button>
}
```

`useUpdateFragment`/`useUpdateContent` are **local-only** — they don't talk to ActionCable or the server. If you need server sync, pair manually with `remote(...)` and your own rollback, as above; there's no automatic reconciliation.

## Decision guide

| Situation | Use |
|---|---|
| Push a change to every *other* connected client | `broadcast_append_to`/`broadcast_prepend_to`/`broadcast_update_to` (or `_later`) |
| Give the acting user's own request instant feedback without waiting on the socket | `render layout: "stream"` + `broadcast_*_props`, alongside the broadcast above |
| No fragment change, just a flash message over the stream response | Empty `.json.props`, still `render layout: "stream"` — flash is always included |
| Local optimistic UI, no need to notify others | `useUpdateFragment`/`useUpdateContent` alone |
| Local optimistic UI that also needs to notify others | `useUpdateFragment` + `remote(...)` + manual rollback on error, and a server-side broadcast in the same action |
| Bulk writes (seed/import) | `suppressing_superglue_broadcasts do ... end` |
