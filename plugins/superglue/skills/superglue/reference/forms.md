# Forms (`form_props`)

Superglue ships `form_props`, a fork of Rails' `form_with` that outputs **props (JSON)** instead of HTML tags. You keep Rails form-builder semantics (models, validations, i18n) while rendering the form in React.

```ruby
# instead of ERB's form_with...
json.postForm do
  form_props model: @post do |f|
    f.text_field :title
    f.text_area :body
    f.submit
  end
end
```

```jsx
const { form, extras, inputs } = postForm

<Form {...form} extras={extras}>
  <TextField {...inputs.title} label="Post title" />
  <TextField {...inputs.body} label="Post body" />
  <SubmitButton {...inputs.submit} />
</Form>
```

`Form`, `TextField`, `SubmitButton` are **not part of `form_props`** — they're components you write, or copy from `candy_wrapper` (§ below). `form_props` only guarantees the *shape* of the data; tag structure and submission wiring are the frontend's job.

## Install

```ruby
gem "form_props"
```

## Output shape: `props` / `extras` / `inputs`

```json
{
  "someForm": {
    "props": { "id": "create-post", "action": "/posts/123", "acceptCharset": "UTF-8", "method": "post" },
    "extras": {
      "method": { "name": "_method", "type": "hidden", "defaultValue": "patch", "autoComplete": "off" },
      "utf8":   { "name": "utf8", "type": "hidden", "defaultValue": "✓", "autoComplete": "off" },
      "csrf":   { "name": "authenticity_token", "type": "hidden", "defaultValue": "...", "autoComplete": "off" }
    },
    "inputs": {
      "title":  { "name": "post[title]", "id": "post_title", "type": "text", "defaultValue": "hello" },
      "submit": { "type": "submit", "value": "Update a Post" }
    }
  }
}
```

- **`props`** — spread directly onto `<form>` (`id`, `action`, `acceptCharset`, `method`).
- **`extras`** — hidden inputs generated indirectly (CSRF token, Rails `_method` override, `utf8` marker):
  ```jsx
  {Object.values(extras).map(hiddenProps => <input {...hiddenProps} key={hiddenProps.name} />)}
  ```
- **`inputs`** — one entry per field helper called, keyed by attribute name (camelCased). Keys are camelized by `props_template`'s default key format (`defaultValue`, `acceptCharset`, etc — see `types.md` § camelize).

`form_props` only cares about attributes — tag nesting is entirely up to you:

```jsx
<label htmlFor={inputs.name.id}>Your Name</label>
<input {...inputs.name} />
```

## `form_props` API differences from `form_with`

1. `remote`/`local` options are **removed** — submission mechanics belong to your `Form` wrapper component, not to `form_props`.
2. `controlled: true` renames the value key from `defaultValue` to `value` on every generated input (default `false`, i.e. uncontrolled).

```ruby
form_props(model: @post, controlled: true) do |f|
  f.text_field :title
end
```

The yielded `f` is a fork of `ActionView::Helpers::FormBuilder`, so it inherits Rails form-builder behavior generally, except:

- **`f.label` does not exist.** Always use a bare `<label>` tag. Blocks passed to helpers for label-yielding (e.g. `collection_radio_buttons { |b| b.label { b.radio_button + b.text } }`) are unsupported.
- **`defaultValue` is not HTML-escaped** — escaping is `props_template`'s job.
- **`defaultValue` key is omitted entirely** if no value was set (never emitted as `null`/`""`) — guard for its absence.
- **`data-disable-with` removed** from submit buttons, **`data-remote` removed** from form props — no automatic double-submit prevention; reimplement in React if wanted.
- **`select`-family helpers never render `selected` on `options`** — selection state always lives on the input's `defaultValue`/`value` (React convention). Only `disabled` stays per-option.
- **Choices for `select` cannot be a raw HTML string** — must be an array/collection.

### Unsupported helpers (and what to use instead)

| Removed | Use instead |
|---|---|
| `label` | Bare `<label htmlFor={inputs.x.id}>` |
| `rich_text_area` | `f.text_area` + Trix wrapped in React, or TinyMCE's React component |
| `button` | Bare `<button>` |
| `date_select`/`time_select`/`datetime_select` | e.g. `react-date-picker` + the supported date field helpers |

### Full list of supported helpers

```
check_box                 file_field                submit
collection_check_boxes    grouped_collection_select tel_field
collection_helpers        hidden_field              text_area
collection_radio_buttons  month_field               text_field
collection_select         number_field              time_field
color_field               password_field            time_zone_select
date_field                radio_button              url_field
datetime_field            range_field               week_field
datetime_local_field      search_field              weekday_select
email_field               select
```

## Helper-by-helper output shapes

**Text-like** (`text_field`, `email_field`, `tel_field`, `file_field`, `url_field`, `hidden_field`, `password_field`, `search_field`, `color_field`) — same args as Rails:

```ruby
f.text_field(:title)
# => { "type": "text", "defaultValue": "Hello World", "name": "post[title]", "id": "post_title" }
```

**Date-like** (`date_field`, `datetime_field`, `datetime_local_field`, `month_field`, `week_field`):

```ruby
f.datetime_field(:created_at)
# => { "type": "datetime-local", "defaultValue": "2004-06-15T01:02:03", "name": "post[created_at]", "id": "post_created_at" }
```

**Number-like** (`number_field`, `range_field`):

```ruby
f.range_field(:favs, in: 1...10)
# => { "type": "range", "defaultValue": "2", "name": "post[favs]", "min": 1, "max": 9, "id": "post_favs" }
```

**Checkbox** — unchecked-value/hidden behavior is passed through as data instead of Rails auto-rendering a hidden input; needs a custom render component:

```ruby
f.check_box(:admin, {}, "on", "off")
# => { "type": "checkbox", "defaultValue": "on", "uncheckedValue": "off", "name": "post[admin]", "id": "post_admin", "includeHidden": true }
```

**Radio** — `inputs` key combines attribute + value (camelCased), e.g. `inputs.adminTrue`/`inputs.adminFalse`:

```ruby
f.radio_button(:admin, true)
f.radio_button(:admin, false)
# => inputs.adminTrue: { "type": "radio", "defaultValue": "true", "name": "post[admin]", "id": "post_admin_true" }
# => inputs.adminFalse: { "type": "radio", "defaultValue": "false", "name": "post[admin]", "id": "post_admin_false", "checked": true }
```

**Select** — needs a custom component (options are nested data, not markup):

```ruby
f.select(:category, ["lifestyle", "programming", "spiritual"],
  { selected: "", disabled: "", prompt: "Choose one" }, { required: true })
```
```json
{
  "type": "select", "required": true, "name": "post[category]", "id": "post_category",
  "defaultValue": "lifestyle",
  "options": [
    { "disabled": true, "value": "", "label": "Choose one" },
    { "value": "lifestyle", "label": "lifestyle" },
    { "value": "programming", "label": "programming" },
    { "value": "spiritual", "label": "spiritual" }
  ]
}
```
`multiple: true` → `defaultValue` becomes an array. If the current value isn't among `options`, `defaultValue` is omitted entirely. Grouped options (`[[label, [[label,value],...]], ...]`) produce nested `{label, options: [...]}` groups — same for `grouped_collection_select` and `collection_select`.

**Collection checkboxes/radios** (`collection_radio_buttons`, `collection_check_boxes`):

```json
{
  "collection": [
    { "name": "user[other_category_ids][]", "type": "checkbox", "defaultValue": "1", "uncheckedValue": "", "id": "user_category_ids_1", "label": "Category 1" },
    { "name": "user[other_category_ids][]", "type": "checkbox", "defaultValue": "2", "uncheckedValue": "", "id": "user_category_ids_2", "label": "Category 2" }
  ],
  "name": "user[other_category_ids][]",
  "includeHidden": true
}
```

All of select/checkbox/radio-collection helpers need a **custom render component** — `form_props` gives you data (`options`, `collection`, `includeHidden`, `uncheckedValue`), not tag structure. Reference implementations exist in the `form_props` repo's test components and in `candy_wrapper`.

## Third-party components

Any helper's props can be splatted into an arbitrary component:

```jsx
import Select from 'react-select'
<Select {...inputs.timeZone} isMulti={inputs.timeZone.multiple} />
```

## jbuilder support

`form_props` works natively in `props_template`. For **jbuilder** templates, call `FormProps.set(json, self)` first:

```ruby
FormProps.set(json, self)
json.form do
  form_props(model: User.new, url: "/") do |f|
    f.text_field(:email)
    f.submit
  end
end
```

## Validation errors (not automatic — two patterns)

### A. Manual `errors` key alongside the form

```ruby
json.someForm do
  form_props(model: @post) do |f|
    f.text_field :title
  end
  json.errors @post.errors.to_hash(true)
end
```

### B. Recommended: Rails `flash` + `useFlash` (matches the worked example in `worked-example.md`)

```diff
  def create
    @post = Post.new(post_params)
    if @post.save
      redirect_to :index
    else
+     flash.now[:postFormErrors] = @post.errors.as_json
      render :new
    end
  end
```

```jsx
import { useFlash } from '@thoughtbot/superglue'

const flash = useFlash()
const validationErrors = flash.postFormErrors
const { form, extras, inputs } = postForm

<Form {...form} extras={extras} validationErrors={validationErrors}>
  <TextField {...inputs.title} label="Post title" errorKey="post_title" />
  <SubmitButton {...inputs.submit} />
</Form>
```

`errorKey` matches the underscored `model_attribute` key format from `errors.as_json`/`to_hash`, **not** the camelCased `inputs` key.

## `candy_wrapper` — prebuilt UI-kit wrappers

Separate, early-stage companion project: copyable (not installed as a dependency) React wrapper components around popular UI kits (Vanilla HTML, Mantine) built to consume `form_props` output directly, including inline error display via `validationErrors` + `errorKey`.

```jsx
import { Form, TextField, SubmitButton } from './copied_components_for_mantine'
```

Mantine variant needs `yarn add dayjs @mantine/core @mantine/dates` before copying its components in. `npm install -D candy_wrapper` only pulls in types, not the components themselves — copy-paste the actual component source from the repo and customize.

## Gotchas

- No `remote`/`local` options — submission behavior is entirely your `Form` wrapper's responsibility.
- No `f.label` — always a bare `<label>`.
- `defaultValue` may be absent — don't assume the key exists.
- `select` choices must be an array/collection, never a raw HTML string.
- File uploads: `file_field` is "same arguments as Rails" but neither multipart-encoding behavior nor auto `enctype` is documented — don't assume it's handled for you.
- Nested attributes/`fields_for` associations: **undocumented** in the source docs — don't invent syntax for it.
- `form_props`'s own README calls it early-stage: "interface, behavior, and name are likely to change drastically before a major version release."
