# TailTag V0 shared components

This file defines the shared components for the TailTag V0 app. A shared component is a user interface part that more than one screen uses, such as a button or a list row. #139 builds these components in Flutter. The [showcase](../../apps/mobile/lib/core/ui/README.md#showcase) shows each component in its states. The [parity review](parity-review.md) records how the code matches this file.

This file uses the design tokens in [`tokens.json`](tokens.json). A design token is a named design value, such as a color or a spacing step. The [design README](README.md) explains each token group. This file names tokens, for example `color.scheme.primary`, but it does not repeat their values.

## How to use this file

### Source of truth and changes

The current approved definition is the version of this file on `main`.

To add or change a component:

1. Open one pull request that changes this file.
2. If the change needs a new or changed token, change `tokens.json` and the design README in the same pull request.
3. A new component must name at least one V0 flow from [V0 flows](#v0-flows) as its consumer. If no flow needs a component, it does not go in this file.
4. The project owner approves and merges the pull request.

gtrotsuka and RadiantCyrus can review a change before or after the merge. If a designer raises a concern after the merge, a new pull request revises or reverts the change.

### Material first

Each component is a Material 3 widget that ships with Flutter. #139 styles it through a `ThemeData` component theme, for example `FilledButtonThemeData`. TailTag status colors go in a `ThemeExtension`. Spacing, radii, sizes, and elevations are Dart constants, so widgets can use them in `const` values.

Material has no widget for five parts. Only these five are TailTag widgets:

1. The [avatar](#avatar) with its image placeholder
2. The [empty state](#empty-state)
3. The [status banner](#status-banner)
4. The [button](#button), for its variants and its loading state
5. The [badge](#badge), because the chip theme cannot style a badge apart from a filter chip

### Component section template

Each component section has the same headings:

| Heading | Contents |
|---------|----------|
| Use | When to use the component, and the V0 flows that use it |
| Do not use | Cases where another component fits better |
| Flutter widget | The Material widget, its theme class, and any TailTag widget |
| Content limits | Text length, line limits, and the number of items |
| Variants | The visual versions of the component |
| States | A table with one row for each state |
| Accessibility | Semantics, touch target, focus, and text scale |
| Tokens | The tokens that the component uses |

The states table always has six rows: normal, pressed, focused, disabled, loading, and error. A row that does not apply says "Not applicable". Some components add a selected row.

### Shared state rules

These rules apply to every component unless its section says otherwise.

- Pressed: the Material pressed state layer shows over the component. A state layer is a see-through overlay in the content color.
- Focused: keyboard, switch access, and screen reader focus use this state. The look depends on the component:
  - Buttons, icon buttons, and chips show a focus ring. The ring color follows the [focus rule](README.md#accessibility) in the design README.
  - Text fields show a thicker `color.scheme.primary` border.
  - List rows, tappable cards, switch rows, and navigation destinations show the Material focus state layer. Flutter cannot draw a ring on these widgets through the theme.
- Focus ring shape: the ring is `size.focusRing.width` wide. It sits `size.focusRing.gap` outside the component edge. The gap keeps a `color.scheme.primary` ring visible next to a primary or destructive fill, so every button variant uses the same ring color.
- Disabled: the component uses the Material disabled colors, which are `color.scheme.onSurface` at reduced opacity. WCAG does not set a contrast minimum for disabled controls. A disabled control must not be the only way to explain why an action is not available.

## Visual direction

The components share one look, called "Con badge". A con badge is the name badge that an attendee wears at a convention. It is bright, made of printed card, and easy to read from a few steps away. TailTag components aim for the same feel.

### Where players use the app

- Players use TailTag in crowded convention halls, hotel lobbies, and dim event rooms.
- They often hold the phone in one hand and look at it for a few seconds at a time.
- A fursuiter can use the app in fursuit paws, with limited vision through the head. Fursuiters use the activation, catch session, and QR credential flows (F5 to F7).

So controls are large, states show from a distance, and color is never the only signal.

### Rules

| Topic | Rule |
|-------|------|
| Size | A control that the player presses fills `size.minTarget` with its visible shape, not only with an invisible touch area. A button is at least `size.minTarget` high. |
| Shape | A pill (stadium shape) means "press me". Buttons, chips, the switch, and the navigation bar indicator are pills. Containers have rounded corners, and a larger container has a larger radius: badges `radius.small`, text fields `radius.medium`, cards and banners `radius.large`, dialogs and sheets `radius.extraLarge`. |
| Surfaces | The screen is `color.scheme.surface`. A surface that holds content on top of the screen is white card stock, `color.scheme.surfaceContainerLowest`. Cards, dialogs, bottom sheets, and text fields use it. Bars use `color.scheme.surfaceContainer`. |
| Color | Violet owns every action. The primary button is `color.scheme.primary`. The secondary button is tonal, in `color.scheme.primaryContainer`. A selected chip or navigation destination is solid `color.scheme.primary`, so it shows from a distance. Tertiary pink marks fursuits in image placeholders. Status colors appear only in badges and banners. |
| Type | Names and labels that the player acts on use the medium-weight styles: `typography.titleMedium` for button labels and list row titles. Card titles and empty state titles use `typography.titleLarge`. The heading styles `typography.headlineSmall`, `typography.titleLarge`, and `typography.titleMedium` have weight 600 in `tokens.json`. Text uses the token styles only. No component changes a font weight. |
| Depth | Cards use `elevation.level1` with a shadow in `color.scheme.primary`, so the shadow matches the violet surfaces. Other parts are flat until content scrolls under them. |
| Motion | Components use the Material default motion. V0 adds no custom animation. |

The design README [Shape](README.md#shape) table and [image placeholders](README.md#image-placeholders) follow these rules. No token value changes.

## V0 flows

These flows are the known consumers of the V0 components. Each component names its flows by ID. The flows come from the V0 API, because no product screen issue exists yet. The [Wave 2](../development/wave-2-participation-validation.md) and [Wave 3](../development/wave-3-catching-validation.md) validation docs prove these flows end to end.

| ID | Flow | What the player does | API paths |
|----|------|----------------------|-----------|
| F1 | Sign-in | Signs in with an email code through Clerk. The app then loads the TailTag user. | Clerk sign-in, then `GET /api/me/` |
| F2 | Profile | Sets a display name and handle, and adds or removes an avatar photo. | `GET`, `PUT`, and `PATCH /api/profile/`. `PUT` and `DELETE /api/profile/avatar/` |
| F3 | Conventions | Browses conventions, enrolls in one, and picks the active convention. | `GET /api/conventions/`. `GET /api/conventions/{id}/`. `GET` and `POST /api/conventions/enrollments/`. `GET` and `PUT /api/conventions/active/` |
| F4 | Fursuits | Creates and edits a fursuit, and adds its photo. | `GET` and `POST /api/fursuits/`. `GET` and `PATCH /api/fursuits/{id}/`. `PUT /api/fursuits/{id}/photo/` |
| F5 | Activation | Turns a fursuit on or off for a convention. | `GET /api/conventions/{convention_id}/fursuit-activations/`. `PUT /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/` |
| F6 | Catch session | Marks a fursuit as out and catchable, or not. | `PUT /api/conventions/{convention_id}/fursuit-activations/{fursuit_id}/catch-session/` |
| F7 | QR credential | Shows the fursuit QR code, and rotates it to a new code. | `GET .../fursuit-activations/{fursuit_id}/catch-credential/`. `POST .../catch-credential/rotate/` |
| F8 | Catch | Scans a QR code, sees a preview of the fursuit, and confirms the catch. | `POST /api/conventions/{convention_id}/catch-credentials/resolve/`. `POST /api/catches/confirm/` |
| F9 | Catch history | Sees the fursuits that the player caught, and filters them by convention. | `GET /api/catches/`, with an optional `convention_id` |

## Inventory

The V0 inventory has these components and no others.

| Component | Flutter widget | TailTag widget | Flows |
|-----------|----------------|----------------|-------|
| [Button](#button) | `FilledButton`, `TextButton` | Yes: variants and loading state | F1 to F8 |
| [Icon button](#icon-button) | `IconButton` | No | F2, F4, F7 |
| [Text field](#text-field) | `TextFormField` | No | F1, F2, F4 |
| [Card](#card) | `Card` | No | F3, F4, F7, F8 |
| [List row](#list-row) | `ListTile` | No | F2 to F5, F9 |
| [Avatar](#avatar) | `ClipOval`, `ClipRRect`, and `Image.network` | Yes | F2, F4, F8, F9 |
| [Badge](#badge) | `Chip` | Yes | F3, F5, F6, F8 |
| [Chip](#chip) | `FilterChip` | No | F9 |
| [Dialog](#dialog) | `AlertDialog` | No | F5, F7 |
| [Bottom sheet](#bottom-sheet) | `showModalBottomSheet` | No | F2, F3, F4 |
| [Snackbar](#snackbar) | `SnackBar` | No | F2, F4, F6, F7, F8 |
| [Switch](#switch) | `SwitchListTile` | No | F5, F6 |
| [Loading indicator](#loading-indicator) | `CircularProgressIndicator`, `RefreshIndicator` | No | F1 to F9 |
| [Empty state](#empty-state) | None | Yes | F3, F4, F5, F9 |
| [Status banner](#status-banner) | None | Yes | F1 to F9 |
| [Top app bar](#top-app-bar) | `AppBar` | No | F1 to F9 |
| [Bottom navigation bar](#bottom-navigation-bar) | `NavigationBar` | No | F1 to F9 |

### Feature-owned parts

These parts are not shared components. The feature that uses them owns them, because each one has one consumer.

| Part | Owner flow | Reason |
|------|------------|--------|
| QR code display | F7 | One consumer. It needs a QR drawing package. |
| QR scanner view | F8 | One consumer. It needs a camera package and camera permission screens. |
| Photo picker field | F2, F4 | It needs a photo package. The feature builds it from an [avatar](#avatar), a [button](#button), and a [bottom sheet](#bottom-sheet). |

### Not in V0

No V0 flow needs these parts. A later change can add one with the [change process](#source-of-truth-and-changes).

- Skeletons. V0 uses the [loading indicator](#loading-indicator) only.
- Segmented buttons and tabs.
- A floating action button. Use a primary [button](#button).
- A navigation drawer.
- The Material `Badge` count dot.
- Checkboxes, radio buttons, sliders, date pickers, search bars, and carousels.

## Shared rules

### Loading

- Given a wait is longer than 500 ms, a [loading indicator](#loading-indicator) shows. Given a wait is shorter, no loading indicator shows. This stops a flash on a fast response.
- V0 has no skeletons.
- Every loading state has visible text or a screen reader label, for example "Loading catches". No loading state uses only motion.
- The 500 ms delay is a rule, not a separate component. `DelayedVisibility` in `apps/mobile/lib/core/ui/` holds its shared code.

### Forms and validation

- Given a form, when the player submits it the first time, then each field validates.
- After the first submit, each field validates again as the player types.
- No field shows an error before the first submit.
- The submit button stays enabled when the form has errors. A submit shows the errors.
- Client checks match the server limits in [Names and long text](#names-and-long-text).

### Server errors

The app keeps the server error `code` but never the server `detail` text. So the app writes all text that a player reads.

- Given a server error with a known `code`, the feature shows its own text on the field or in a [status banner](#status-banner).
- Given an unknown `code`, or a field error with no `code`, a status banner shows the unknown error text from [Generic error text](#generic-error-text).
- Profile and fursuit field errors from the server have no `code`. The client checks prevent most of them.

### Generic error text

The [status banner](#status-banner) uses this text for errors that every flow can get. Features write all other text.

| Failure | Mobile failure type | Banner text | Action |
|---------|---------------------|-------------|--------|
| No connection | `ApiConnectivityFailure` | "No internet connection. Check your connection, then try again." | "Try again" |
| Timeout | `ApiTimeoutFailure` | "The server is taking too long to answer. Try again." | "Try again" |
| Unknown error | `ApiServerFailure`, `ApiUnexpectedFailure`, an unknown `code`, or a field error with no `code` | "Something went wrong. Try again." | "Try again" |

These failures do not use a generic banner:

- `ApiCancelledFailure` shows nothing, because the app cancelled the request.
- `ApiUnauthenticatedFailure` sends the player to sign-in. The auth flow owns it.
- `ApiPermissionFailure`, `ApiNotFoundFailure`, `ApiConflictFailure`, and `ApiValidationFailure` with a known `code` get feature text.

### Names and long text

| Place | Rule |
|-------|------|
| List rows and cards | A name wraps to two lines and then ends with an ellipsis. |
| Detail screens | The full name shows. It wraps with no line limit. |
| Top app bar title | One line, then an ellipsis. The full name shows in the screen body. |
| Any text at 200% text scale | Rows and cards grow taller. They do not clip text. |

Text fields show a character counter at the server limit:

| Field | Limit |
|-------|-------|
| Display name | 50 characters |
| Fursuit name | 50 characters |
| Handle | 32 characters |

A convention name can have up to 255 characters. The app shows it but does not edit it.

### Confirmation

- A confirmation [dialog](#dialog) shows only before these two actions. Both revoke the QR credential for good.
  - Credential rotation (F7)
  - Fursuit deactivation at a convention (F5). Deactivation also ends the catch session.
- The confirm button uses the destructive [button](#button) variant.
- Other actions run at once and show a [snackbar](#snackbar). For example, ending a catch session runs at once, because the player can start it again.
- Dialogs are for decisions. Bottom sheets are for choices and short forms.

### Platform look

- Components use the Material look on Android and iOS. For example, the top app bar title starts at the leading edge on both platforms.
- Status icons are outline glyphs. The error icon is `Icons.error_outline`, because `Icons.error_outlined` draws a filled disc that looks heavier than the info, warning, and success icons.
- Icons use `Icons.adaptive` for back, share, and more, as the design README says.
- No component uses another `.adaptive` constructor, such as `Switch.adaptive` or `AlertDialog.adaptive`. On iOS those show Cupertino widgets, which do not use the TailTag tokens or the contrast table.

### Component color pairs

The [contrast table](README.md#contrast-table) in the design README covers the token pairs. Some components put a color on a container surface that the table does not list. This table adds those pairs. The ratios use the same WCAG 2.2 formula on the values in `tokens.json`.

| Foreground | Background | Kind | Ratio | Minimum | Result | Where |
|---|---|---|---|---|---|---|
| `primary` | `surfaceContainerLowest` | Text | 6.46:1 | 4.5:1 | Pass | Text button label and selected title in a dialog, sheet, or card |
| `error` | `surfaceContainerLowest` | Text | 6.46:1 | 4.5:1 | Pass | Text field error text and label inside a white field or sheet |
| `primary` | `surfaceContainer` | Text | 5.55:1 | 4.5:1 | Pass | Selected navigation bar label |
| `outline` | `surfaceContainerLowest` | Component edge | 4.46:1 | 3:1 | Pass | Text field and chip edge on white |
| `primary` | `surfaceContainerLowest` | Focus indicator | 6.46:1 | 3:1 | Pass | Focus ring on a button or chip in a card, sheet, or dialog, and the focused text field border |

These pairs come from the design README contrast table and also cover new uses in this file:

- `onPrimaryContainer` on `primaryContainer` (7.28:1): the secondary button, the selected choice row, and the player image placeholder.
- `onTertiaryContainer` on `tertiaryContainer` (7.25:1): the fursuit image placeholder.
- `onPrimary` on `primary` (6.46:1): the selected chip and the selected navigation icon.

The secondary button fill, `primaryContainer`, has a 1.22:1 ratio on `surface`. The fill is not the only cue, because the label in `onPrimaryContainer` names the control, as with any Material tonal button.

If a token value changes, update this table with the README contrast table.

### Pull to refresh

- Lists that show server data use pull to refresh: conventions (F3), fursuits (F4), activations (F5), and catch history (F9).
- The widget is `RefreshIndicator`, not `RefreshIndicator.adaptive`.
- Pull to refresh is never the only way to reload. A screen also reloads when it opens, and an error banner has a "Try again" action. This gives a way to reload without a drag gesture.

## Components

### Button

#### Use

Use a button for an action that the player starts, such as save, enroll, or confirm a catch.

Flows: F1 sign-in, F2 save profile, F3 enroll, F4 save fursuit, F5 and F7 confirm in a dialog, F8 confirm a catch.

#### Do not use

- Do not use a button to go to another screen from a list. Use a [list row](#list-row).
- Do not use a button for an on or off setting. Use a [switch](#switch).
- Do not use a button with only an icon. Use an [icon button](#icon-button).

#### Flutter widget

| Variant | Widget | Theme class |
|---------|--------|-------------|
| Primary | `FilledButton` | `FilledButtonThemeData` |
| Secondary | `FilledButton` with the primary container colors | `FilledButtonThemeData` |
| Secondary, inside a dialog or banner | `TextButton` | `TextButtonThemeData` |
| Destructive | `FilledButton` with the error colors | `FilledButtonThemeData` |

Flutter gives `FilledButton.tonal` the secondary container colors by default. The theme cannot tell one filled button variant from another, so `TailTagButton` sets the secondary and destructive colors on each button. The shape, size, and text style come from the theme.

The TailTag widget `TailTagButton` builds every variant and the loading state. It wraps the Material button. Features use it for every button, so no feature sets the tonal or destructive colors itself. See the loading row in the states table.

#### Content limits

- The label is a verb or a short verb phrase, for example "Save" or "Confirm catch". It has at most three words.
- The label never says "OK" or "Yes". It names the action.
- A button can have one leading icon. The icon comes before the label.
- A screen has at most one primary button.
- At 200% text scale, the label wraps and the button grows taller. The label never clips.

#### Variants

| Variant | Use |
|---------|-----|
| Primary | The main action on a screen or in a sheet. A solid violet pill. |
| Secondary | Other actions. A tonal pill in the primary container colors. Inside a dialog or a banner, the secondary button is a text button with no fill. |
| Destructive | Only the confirm action in a confirmation dialog. See [Confirmation](#confirmation). |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | Variant colors | Starts the action on tap |
| Pressed | Pressed state layer | Not applicable |
| Focused | Focus ring | Enter or space starts the action |
| Disabled | Disabled colors | No action. Use it only while another action runs, not to show form errors. |
| Loading | The label is hidden but keeps its space. A small spinner shows in the center. | The button is disabled and keeps its size. It shows the spinner after 500 ms. |
| Error | Not applicable | The screen shows the error in a status banner. |

#### Accessibility

- Role: button. The label is the button text.
- Loading: the screen reader still reads the label, with the value "Loading".
- Touch target: at least `size.minTarget` wide and high.
- Focus: focus ring, from the shared state rules.
- 200% text scale: the label wraps and the button grows taller.

#### Tokens

- Primary: `color.scheme.primary`, `color.scheme.onPrimary`
- Secondary: `color.scheme.primaryContainer` for the fill, `color.scheme.onPrimaryContainer` for the label
- Secondary in a dialog or banner: `color.scheme.primary` for the label, or the banner text color
- Destructive: `color.scheme.error`, `color.scheme.onError`
- Text: `typography.titleMedium`
- Shape: stadium shape. See [Shape](README.md#shape).
- Height: the visible button is at least `size.minTarget` high.
- Side padding: `spacing.xl`. A text button uses `spacing.lg`.
- Icon: `size.icon.small`. Gap between icon and label: `spacing.xs`.
- Spinner: `size.icon.small`
- Target: `size.minTarget`

### Icon button

#### Use

Use an icon button for a common action when an icon is clear without text, such as share or more.

Flows: F7 share the QR code, F2 and F4 edit the photo, and the top app bar actions in every flow.

#### Do not use

- Do not use an icon button when the icon meaning is not clear. Use a [button](#button) with a label.
- Do not use an icon button for the main action on a screen.

#### Flutter widget

`IconButton` (the standard variant), styled through `IconButtonThemeData`.

#### Content limits

- One Material icon, in the Outlined style.
- The `tooltip` is required. It gives the screen reader label and the long-press hint.
- The tooltip text is a short verb phrase, for example "Share QR code".

#### Variants

Standard only. V0 has no filled or tonal icon buttons.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.onSurfaceVariant` icon | Starts the action on tap |
| Pressed | Pressed state layer | Not applicable |
| Focused | Focus ring | Enter or space starts the action |
| Disabled | Disabled colors | No action |
| Loading | Not applicable | Not applicable |
| Error | Not applicable | Not applicable |

#### Accessibility

- Role: button. The label comes from `tooltip`.
- Touch target: at least `size.minTarget` wide and high.
- Focus: focus ring.
- 200% text scale: icons do not scale with text. The tooltip text scales.

#### Tokens

- `color.scheme.onSurfaceVariant`
- `size.icon.medium`
- `size.minTarget`

### Text field

#### Use

Use a text field for text that the player types.

Flows: F1 email and sign-in code, F2 display name and handle, F4 fursuit name.

#### Do not use

- Do not use a text field to show a value that the player cannot change. Show it in an info [list row](#list-row).
- Do not use a text field to pick from a fixed list. Use a [bottom sheet](#bottom-sheet) with choice rows.

#### Flutter widget

`TextFormField` inside a `Form`, with an `InputDecoration` and an `OutlineInputBorder`. The field is filled white, like a write-in box on a form. The theme class is `InputDecorationThemeData`.

#### Content limits

- The label is always visible. It has at most three words. A hint inside the field never replaces the label.
- Helper text is optional. It is one short sentence below the field.
- Error text is one sentence. It says what is wrong and how to fix it, for example "Enter a name".
- Helper and error text wrap to at most three lines.
- A field with a server limit shows a counter and stops input at the limit. See [Names and long text](#names-and-long-text).
- An optional field adds "(optional)" to its label. A required field has no mark.

#### Variants

Outlined only, with a white fill. V0 has no Material filled text fields, which have only a bottom line.

Keyboard settings depend on the field:

| Field | Keyboard type | Autofill hint | Other |
|-------|---------------|---------------|-------|
| Email | Email | Email | No autocorrect |
| Sign-in code | Number | One-time code | No autocorrect |
| Display name and fursuit name | Text | None | Capitalize words |
| Handle | Text | Username | No autocorrect, no capitals |

Each field except the last uses the "next" keyboard action. The last field uses "done", and "done" submits the form.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.outline` border | Accepts input |
| Pressed | Not applicable | A tap focuses the field. |
| Focused | Thicker `color.scheme.primary` border, label in `color.scheme.primary` | The keyboard opens. |
| Disabled | Disabled colors | No input. Fields are disabled only while their form saves. |
| Loading | Not applicable | The form shows loading on its submit button. |
| Error | `color.scheme.error` border and label. Error text replaces helper text. The field shows no error icon. | Validation follows [Forms and validation](#forms-and-validation). |

#### Accessibility

- Role: text field. The screen reader reads the label, the value, the helper or error text, and the counter.
- Error: the error text below the field is the non-color cue. Color is never the only signal. The field has no error icon, because the theme cannot add one and a per-field icon depends on each feature to remember it.
- Touch target: the field is at least `size.minTarget` high.
- Focus: the focused border meets the 3:1 focus contrast in the design README.
- 200% text scale: the label, value, helper, and error text grow. The field grows taller. Helper and error text wrap.

#### Tokens

- `color.scheme.outline`, `color.scheme.primary`, `color.scheme.error`, `color.scheme.onSurface`, `color.scheme.onSurfaceVariant`
- `color.scheme.surfaceContainerLowest` for the fill
- `typography.bodyLarge` for input, `typography.bodySmall` for helper, error, and counter text
- `radius.medium`
- `spacing.lg` between fields
- `size.minTarget`

### Card

#### Use

Use a card to group content about one thing, such as one fursuit or one convention, on a screen with other content.

Flows: F3 the active convention summary, F4 the fursuit detail header, F7 the frame around the QR code, F8 the fursuit preview before a catch.

#### Do not use

- Do not use a card for the items of a long list. Use a [list row](#list-row).
- Do not put a card inside another card.
- Do not use a card only as decoration.

#### Flutter widget

`Card` (the elevated default), styled through `CardThemeData`. A card that opens something wraps its content in an `InkWell`, so the whole card is one target.

#### Content limits

- One title. A name in the title follows the two-line rule in [Names and long text](#names-and-long-text).
- At most three lines of supporting text, then an ellipsis.
- An optional [avatar](#avatar) or fursuit photo. A photo at the top of a card sits `spacing.sm` from the card edges, like the art on a trading card. Its `radius.small` corners plus the `spacing.sm` gap match the `radius.large` card corners.
- A card is either one tap target, or it has its own buttons. It is never both.
- At most two buttons in a card.

#### Variants

Elevated only.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.surfaceContainerLowest` fill, `elevation.level1` with a `color.scheme.primary` shadow | A tappable card opens its target. |
| Pressed | Pressed state layer over the card (tappable cards only) | Not applicable |
| Focused | Focus state layer (tappable cards only) | Enter or space opens the target. |
| Disabled | Not applicable | Not applicable |
| Loading | Not applicable | The screen shows the loading indicator. |
| Error | Not applicable | The screen shows a status banner. |

#### Accessibility

- A tappable card is one semantics node with the button role. Its label joins the title and the key text.
- A card with buttons is a group. Each button is its own target.
- Touch target: a tappable card is at least `size.minTarget` high.
- 200% text scale: the card grows taller. Text never clips.
- Focus: a tappable card shows the focus state layer. A card with buttons takes no focus of its own. Its buttons do.

#### Tokens

- `color.scheme.surfaceContainerLowest`, `color.scheme.onSurface`, `color.scheme.onSurfaceVariant`
- `color.scheme.primary` for the shadow
- `elevation.level1`
- `radius.large`
- `spacing.lg` for padding, `spacing.md` between parts, `spacing.sm` around a top photo
- `typography.titleLarge` for the title, `typography.bodyMedium` for supporting text

### List row

#### Use

Use a list row for one item in a list, or for one setting or value.

Flows: F2 profile values, F3 conventions, F4 fursuits, F5 activations, F9 catch history.

#### Do not use

- Do not use a list row for an on or off setting. Use a [switch](#switch), which is a switch list row.
- Do not use a list row for a single item that needs a photo and several actions. Use a [card](#card).

#### Flutter widget

`ListTile`, styled through `ListTileThemeData`.

#### Content limits

- Leading: an optional [avatar](#avatar) or one icon.
- Title: one name or label. A name follows the two-line rule in [Names and long text](#names-and-long-text).
- Subtitle: optional. It wraps to two lines and then ends with an ellipsis.
- Trailing: optional. One [badge](#badge), or one icon.
- No dividers between rows. If a list needs dividers, they use `color.scheme.outlineVariant`, which is decorative only.

#### Variants

| Variant | Use | Trailing |
|---------|-----|----------|
| Navigation row | Opens a detail screen, for example a fursuit | Optional badge |
| Info row | Shows a value that the player cannot change here, for example the handle | None |
| Choice row | One choice in a bottom sheet, for example a convention | `Icons.check` when selected |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | Transparent background on the screen surface | A navigation or choice row acts on tap. |
| Pressed | Pressed state layer with `radius.large` corners | Not applicable |
| Focused | Focus state layer | Enter or space acts. |
| Disabled | Disabled colors | No action. Use it only when the reason shows on the screen. |
| Loading | Not applicable | The list shows the loading indicator. |
| Error | Not applicable | The list shows a status banner. |
| Selected (choice row) | `color.scheme.primaryContainer` fill with `radius.large` corners. Title and `Icons.check` in `color.scheme.onPrimaryContainer`. | The screen reader reads "selected". |

#### Accessibility

- Each row is one semantics node. Its label joins the title, subtitle, and badge text.
- A navigation row and a choice row have the button role. An info row has no role.
- A choice row reports its selected state.
- Touch target: at least `size.minTarget` high.
- Focus: focus state layer.
- 200% text scale: the row grows taller. The leading avatar stays at the top.

#### Tokens

- `color.scheme.onSurface` for the title, `color.scheme.onSurfaceVariant` for the subtitle and icons
- `color.scheme.primaryContainer` for the selected fill, `color.scheme.onPrimaryContainer` for the selected title and check
- `typography.titleMedium` for the title, `typography.bodyMedium` for the subtitle
- `radius.large` for the pressed and selected shape
- `spacing.lg` side padding, `spacing.md` between parts
- `size.icon.medium`, `size.minTarget`

### Avatar

#### Use

Use an avatar for the image of a player or a fursuit. It also shows the [image placeholder](README.md#image-placeholders) when there is no image.

Flows: F2 the player avatar, F4 the fursuit photo, F8 the catch preview, F9 the fursuits in catch history.

#### Do not use

- Do not use an avatar for an icon. Use the icon on its own.
- Do not use an avatar without the name next to it.

#### Flutter widget

A TailTag widget. It clips the image to a circle with `ClipOval` for the circle variants, and with `ClipRRect` for the photo variant. It loads the image with `Image.network`, so the placeholder shows while the image loads and when it fails.

The widget takes an image URL, a name, and a kind: player or fursuit.

#### Content limits

- The image fills the shape and is cropped to fit. The server stores the original image without a crop, so the crop is only visual.
- The placeholder shows up to two initials. The initials are the first character of the first two words of the name.
- If the name is empty, the placeholder shows `Icons.person_outlined` for a player or `Icons.pets_outlined` for a fursuit.
- A player placeholder is violet and a fursuit placeholder is pink, so a list of placeholders looks like a sheet of stickers. The name and the empty-name icon tell the kinds apart, not the color.

#### Variants

| Variant | Shape | Use |
|---------|-------|-----|
| Small | Circle, `size.avatar.small` | List rows |
| Large | Circle, `size.avatar.large` | The profile header and the fursuit detail header |
| Photo | Square with `radius.small` corners, the full width of its card less `spacing.sm` on each side | The catch preview (F8) |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | The image | Not applicable |
| Pressed | Not applicable | An avatar has no action. A list row or card around it has the action. |
| Focused | Not applicable | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | The placeholder shows until the image loads. | No spinner shows. |
| Error | The placeholder shows if the image fails to load. | No error text shows. |

#### Accessibility

- The avatar is excluded from semantics, because the name always shows next to it.
- The initials do not scale with text. They scale with the avatar size, so they never overflow the circle.
- The placeholder colors meet the contrast table in the design README.
- Touch target: not applicable. An avatar has no action.
- Focus: not applicable. Focus goes to the row or card around the avatar.
- 200% text scale: the avatar keeps its size. The name next to it grows.

#### Tokens

- Player placeholder: `color.scheme.primaryContainer` background, `color.scheme.onPrimaryContainer` initials and icon
- Fursuit placeholder: `color.scheme.tertiaryContainer` background, `color.scheme.onTertiaryContainer` initials and icon
- `typography.titleMedium` for small initials, `typography.headlineMedium` for large and photo initials
- `radius.small` for the photo variant
- `size.icon.medium` for the placeholder icon
- `size.avatar.small` and `size.avatar.large` for the circle variants

### Badge

#### Use

Use a badge for a short label that shows the state of an item. A badge has no action.

Flows: F3 the active convention, F5 the activation state of a fursuit, F6 a fursuit that is out, F8 a fursuit that the player already caught.

#### Do not use

- Do not use a badge for an action or a filter. Use a [chip](#chip).
- Do not use a badge for a count.
- Do not use a badge for a long message. Use a [status banner](#status-banner).

#### Flutter widget

A TailTag widget, `StatusBadge`. It builds a `Chip` with no action and no border. The chip theme styles filter chips as pills, so the badge sets its own shape and its variant colors from the `ThemeExtension`.

#### Content limits

- The label has one or two words, for example "Active" or "Out now". Features write the label.
- The label is one line. The badge never uses an ellipsis, so the label must be short.
- Success, warning, and error badges have their status icon. A neutral badge can have one Outlined icon.
- A badge is a label, not a control, so it is a rounded rectangle and not a pill. This keeps it apart from a [chip](#chip).

#### Variants

Variants use status meanings only. Features map their states onto these variants. No variant names a business state.

| Variant | Background | Text and icon | Icon |
|---------|------------|---------------|------|
| Neutral | `color.scheme.surfaceContainerHighest` | `color.scheme.onSurfaceVariant` | Optional |
| Success | `color.status.successContainer` | `color.status.onSuccessContainer` | `Icons.check_circle_outlined` |
| Warning | `color.status.warningContainer` | `color.status.onWarningContainer` | `Icons.warning_amber_outlined` |
| Error | `color.scheme.errorContainer` | `color.scheme.onErrorContainer` | `Icons.error_outline` |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | Variant colors | No action |
| Pressed | Not applicable | Not applicable |
| Focused | Not applicable | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | Not applicable | Not applicable |
| Error | Not applicable. The error variant is a meaning, not a state. | Not applicable |

#### Accessibility

- The badge text is part of the label of the row or card around it. The badge has no role of its own.
- The icon and the text are the non-color cue.
- 200% text scale: the badge grows. If it does not fit next to the title, it moves below the title. In a list row, `StatusBadge.rowTrailing` and `StatusBadge.rowSubtitle` move it below the title when the text scale is above 1.3.
- Touch target: not applicable. A badge has no action.
- Focus: not applicable. Focus goes to the row or card around the badge.

#### Tokens

- The variant colors in the table above
- `typography.labelLarge`
- `radius.small`
- `spacing.xs` between the icon and the label, and at each side
- `size.icon.small`

### Chip

#### Use

Use a filter chip to narrow a list.

Flows: F9 filter catch history by convention.

#### Do not use

- Do not use a chip to show a state. Use a [badge](#badge).
- Do not use a chip for a main action. Use a [button](#button).

#### Flutter widget

`FilterChip`, styled through `ChipThemeData`.

#### Content limits

- The label has one to three words. A convention name in a chip wraps to two lines and then ends with an ellipsis.
- Chips sit in a `Wrap`, so they move to a new line when they do not fit. They do not scroll sideways.
- A group of filter chips allows one choice unless the feature needs more. An "All" chip clears the filter.

#### Variants

Filter only. V0 has no assist, input, or suggestion chips.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.surfaceContainerLowest` fill, `color.scheme.outline` border, label in `color.scheme.onSurfaceVariant` | Selects on tap |
| Pressed | Pressed state layer | Not applicable |
| Focused | Focus ring | Enter or space selects. |
| Disabled | Disabled colors | No action. Use it only while the list reloads. |
| Loading | Not applicable | The list shows the loading indicator. |
| Error | Not applicable | The list shows a status banner. |
| Selected | Solid `color.scheme.primary` fill, label and check mark in `color.scheme.onPrimary`, and no border | The screen reader reads "selected". |

#### Accessibility

- Role: button, with a selected state.
- The check mark is the non-color cue for selection.
- Touch target: at least `size.minTarget` high, with Material tap target padding.
- Focus: focus ring.
- 200% text scale: chips grow and wrap to new lines.

#### Tokens

- `color.scheme.surfaceContainerLowest`, `color.scheme.outline`, `color.scheme.onSurfaceVariant`
- `color.scheme.primary`, `color.scheme.onPrimary` for the selected chip
- `typography.labelLarge`
- Shape: stadium shape, because a chip is pressable
- `spacing.sm` side padding and `spacing.xs` top and bottom padding, `spacing.sm` between chips
- `size.icon.small`, `size.minTarget`

### Dialog

#### Use

Use a dialog for a decision that the player must make before the app continues. In V0 this is only the confirmation before an action that cannot be undone. See [Confirmation](#confirmation).

Flows: F5 deactivation, F7 credential rotation.

#### Do not use

- Do not use a dialog for a choice from a list or for a form. Use a [bottom sheet](#bottom-sheet).
- Do not use a dialog to report success. Use a [snackbar](#snackbar).
- Do not use a dialog for an error. Use a [status banner](#status-banner).

#### Flutter widget

`AlertDialog` shown with `showDialog`, styled through `DialogThemeData`. Not `AlertDialog.adaptive`.

#### Content limits

- Title: one question that names the action, for example "Rotate this QR code?".
- Body: at most two sentences. They say what happens, for example "Players can no longer catch with the old code."
- Actions: two buttons. The secondary button "Cancel" comes first. The confirm button comes second and uses a verb, for example "Rotate code".

#### Variants

Confirmation only.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.surfaceContainerLowest` fill over a scrim | Cancel, back, and a tap on the scrim close the dialog with no action. |
| Pressed | Not applicable. The buttons have their own states. | Not applicable |
| Focused | Not applicable. The buttons have their own states. | Focus stays inside the dialog. |
| Disabled | Not applicable | Not applicable |
| Loading | The confirm button shows its loading state. | The dialog stays open until the server answers. Cancel is disabled. |
| Error | Not applicable | The dialog closes, and the screen shows a status banner. |

After success, the dialog closes and a snackbar confirms the action.

#### Accessibility

- Role: dialog. The screen reader starts on the title.
- Focus stays inside the dialog until it closes.
- 200% text scale: the body scrolls. The buttons stack in a column when they do not fit in a row.
- Touch target: each button is at least `size.minTarget` high.

#### Tokens

- `color.scheme.surfaceContainerLowest`, `color.scheme.onSurface`, `color.scheme.onSurfaceVariant`, `color.scheme.scrim`
- `elevation.level3`
- `radius.extraLarge`
- `typography.headlineSmall` for the title, `typography.bodyMedium` for the body
- `spacing.xl` for padding

### Bottom sheet

#### Use

Use a bottom sheet for a choice from a short list or for a short form.

Flows: F2 and F4 the photo choices (take photo, choose photo, remove photo), F3 pick the active convention.

#### Do not use

- Do not use a bottom sheet for a decision about an action that cannot be undone. Use a [dialog](#dialog).
- Do not open a bottom sheet from another bottom sheet.
- Do not use a bottom sheet for a long form. Use a full screen.

#### Flutter widget

`showModalBottomSheet` with `showDragHandle: true` and `useSafeArea: true`, styled through `BottomSheetThemeData`. A sheet with a text field also uses `isScrollControlled: true`, so the keyboard does not cover the field.

#### Content limits

- An optional title.
- A choice sheet has choice [list rows](#list-row). It scrolls when the list is long.
- Rows sit `spacing.sm` in from the sheet edges, so the rounded selected fill does not touch them. The title lines up with the row text, at `spacing.xl` from the sheet edge.
- A form sheet has at most three text fields and one primary button.

#### Variants

| Variant | Contents | Closes when |
|---------|----------|-------------|
| Choice | Choice list rows | The player picks a row |
| Form | Text fields and a primary button | The form saves |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.surfaceContainerLowest` fill over a scrim | A drag down, back, a tap on the scrim, or the drag handle closes the sheet. |
| Pressed | Not applicable. The rows and buttons have their own states. | Not applicable |
| Focused | Not applicable. The rows and buttons have their own states. | Focus stays inside the sheet. |
| Disabled | Not applicable | Not applicable |
| Loading | A choice sheet shows the loading indicator while its list loads. | The loading rule applies. |
| Error | A status banner shows at the top of the sheet. | The sheet stays open. |

#### Accessibility

- The drag handle has the screen reader label "Dismiss". It closes the sheet without a drag gesture.
- Focus stays inside the sheet until it closes.
- 200% text scale: the sheet content scrolls.
- Touch target: the drag handle, each row, and each button are at least `size.minTarget` high.

#### Tokens

- `color.scheme.surfaceContainerLowest`, `color.scheme.onSurfaceVariant` for the drag handle, `color.scheme.scrim`
- `elevation.level1`
- `radius.extraLarge` for the top corners
- `typography.titleLarge` for the title
- `spacing.lg` for padding, `spacing.sm` beside the rows of a choice sheet, `spacing.xl` beside its title

### Snackbar

#### Use

Use a snackbar for a short message after an action succeeds.

Flows: F2 "Profile saved", F4 "Fursuit saved", F6 "Catch session ended", F7 "QR code rotated", F8 "Catch confirmed".

#### Do not use

- Do not use a snackbar for an error. Use a [status banner](#status-banner), which stays until the problem is fixed.
- Do not use a snackbar for anything that the player must act on.

#### Flutter widget

`SnackBar` shown through `ScaffoldMessenger`, with `SnackBarBehavior.floating`. The theme class is `SnackBarThemeData`.

#### Content limits

- One short sentence, for example "Catch confirmed".
- No action in V0. No icon.
- One snackbar at a time. A new one replaces the old one.

#### Variants

One. A snackbar uses no status color, so its text carries the whole meaning.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.inverseSurface` fill | It closes after the Flutter default time. |
| Pressed | Not applicable | Not applicable |
| Focused | Not applicable | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | Not applicable | Not applicable |
| Error | Not applicable | Errors use a status banner. |

#### Accessibility

- Flutter announces the snackbar text to the screen reader.
- 200% text scale: the text wraps and the snackbar grows taller.
- Touch target: not applicable. A V0 snackbar has no action.
- Focus: not applicable. The snackbar does not take focus.

#### Tokens

- `color.scheme.inverseSurface`, `color.scheme.onInverseSurface`
- `typography.bodyMedium`
- `radius.medium`
- `spacing.lg` from the screen edges

### Switch

#### Use

Use a switch for an on or off setting that changes at once on the server.

Flows: F5 a fursuit is active at a convention, F6 a fursuit is out for catching.

#### Do not use

- Do not use a switch for an action that runs once. Use a [button](#button).
- Do not use a switch inside a form that saves with a button.

#### Flutter widget

`SwitchListTile`, styled through `SwitchThemeData` and `ListTileThemeData`. Not `Switch.adaptive`.

#### Content limits

- The title says what is true when the switch is on, for example "Out for catching".
- The optional subtitle says what the setting does. It wraps to two lines.

#### Variants

One. The whole row is the target.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | Off: `color.scheme.outline` track border, `Icons.close` in the thumb. On: `color.scheme.primary` track, `Icons.check` in the thumb. | A tap sends the change to the server. |
| Pressed | Pressed state layer on the row | Not applicable |
| Focused | Focus state layer on the row | Enter or space toggles. |
| Disabled | Disabled colors | No action |
| Loading | The row is disabled. After 500 ms, the subtitle says "Updating" and a small spinner shows. | The switch stays in its old position until the server answers. Then it moves. |
| Error | The switch stays in its old position. | The screen shows a status banner. |

The switch waits for the server, because a wrong "out" state misleads other players at the convention.

Turning activation off (F5) shows the confirmation dialog first. See [Confirmation](#confirmation).

#### Accessibility

- Role: switch. The screen reader reads the title and "on" or "off".
- The thumb icon and the thumb position are the non-color cue for on and off.
- Loading: the "Updating" subtitle is the non-motion cue.
- Touch target: the whole row, at least `size.minTarget` high.
- Focus: focus state layer.
- 200% text scale: the row grows taller. The switch stays at the end of the row.

#### Tokens

- `color.scheme.primary`, `color.scheme.onPrimary`, `color.scheme.outline`, `color.scheme.surfaceContainerHighest`
- `typography.titleMedium` for the title, `typography.bodyMedium` for the subtitle, from the list row theme
- `size.icon.small` for the spinner
- `size.minTarget`

### Loading indicator

#### Use

Use a loading indicator while the app waits for the server. See [Loading](#loading).

Flows: every flow.

#### Do not use

- Do not show a loading indicator for a wait shorter than 500 ms.
- Do not use a skeleton. V0 has no skeletons.
- Do not use a loading indicator inside a button. The button has its own loading state.

#### Flutter widget

- `CircularProgressIndicator`, indeterminate, styled through `ProgressIndicatorThemeData`. Not `CircularProgressIndicator.adaptive`.
- `RefreshIndicator` for pull to refresh. See [Pull to refresh](#pull-to-refresh).

#### Content limits

- One indicator per loading area.
- Every indicator has a `semanticsLabel`, for example "Loading fursuits".

#### Variants

| Variant | Size | Use |
|---------|------|-----|
| Screen | The Material default size | A screen or list with no content yet. It shows in the center. |
| Small | `size.icon.small` | Inside a button or a switch row |
| Refresh | The Material default size | Pull to refresh on a list that already shows content |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.primary` spinner with round ends | Shows after 500 ms |
| Pressed | Not applicable | Not applicable |
| Focused | Not applicable | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | This component is the loading state. | Not applicable |
| Error | Not applicable | When the wait ends in an error, the indicator closes and a status banner shows. |

#### Accessibility

- The screen reader reads the `semanticsLabel`.
- The label is the non-motion cue. It covers players who turn off animation.
- Touch target: not applicable. A loading indicator has no action.
- Focus: not applicable. A loading indicator does not take focus.
- 200% text scale: not applicable. The indicator has no text, and its size does not change.

#### Tokens

- `color.scheme.primary`
- `size.icon.small`

### Empty state

#### Use

Use an empty state when a list loads with no items.

Flows: F3 no conventions are open, F4 the player has no fursuits, F5 no fursuit is active at the convention, F9 the player has no catches.

#### Do not use

- Do not use an empty state when the list failed to load. Use a [status banner](#status-banner).
- Do not use an empty state while the list loads. Use a [loading indicator](#loading-indicator).

#### Flutter widget

A TailTag widget. It takes an icon, a title, a body, and an optional action.

A dashed outline frames the content. It looks like an empty slot in a card binder that waits for its first card. The widget fills the width of its parent. It does not sit in a [card](#card).

#### Content limits

- One Outlined icon.
- A title that says what is empty, for example "No fursuits yet".
- One line of body text that says how to fill the list, for example "Add a fursuit to start playing."
- One optional action: a primary or secondary [button](#button).
- Features write the text.

#### Variants

One.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | The icon, title, body, and action in a centered column inside a dashed outline | The action starts on tap. |
| Pressed | Not applicable. The button has its own states. | Not applicable |
| Focused | Not applicable. The button has its own states. | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | Not applicable | Not applicable |
| Error | Not applicable | Not applicable |

#### Accessibility

- The icon is excluded from semantics.
- The title is a header for the screen reader.
- 200% text scale: the text wraps, and the column scrolls if it does not fit.
- Touch target: the action follows the [button](#button) rules. The rest has no action.
- Focus: only the action takes focus.

#### Tokens

- `color.scheme.primary` for the icon, `color.scheme.onSurface` for the title, `color.scheme.onSurfaceVariant` for the body
- `color.scheme.outline` for the dashed outline, which is decorative
- `radius.large` for the outline corners. Dashes and gaps are `spacing.sm` long.
- `typography.titleLarge` for the title, `typography.bodyMedium` for the body
- `spacing.xxl` above and below the content inside the outline, `spacing.xl` at each side
- `spacing.md` below the icon, `spacing.sm` below the title, `spacing.xl` above the action
- `spacing.lg` from the screen edges
- `size.icon.large`

### Status banner

#### Use

Use a status banner for a message that must stay on screen until the problem is fixed or the player acts.

Flows: every flow, for the [generic error text](#generic-error-text). F8 also uses it for a fursuit that is not out, and for a fursuit that the player already caught.

#### Do not use

- Do not use a status banner for success. Use a [snackbar](#snackbar).
- Do not use a status banner for an error on one field. Show the error on the [text field](#text-field).

#### Flutter widget

A TailTag widget. It is a rounded block at the top of the content area, below the top app bar. It sits `spacing.lg` from the screen edges, like a card. It is not the Material `MaterialBanner`.

#### Content limits

- One status icon.
- One or two sentences. The text says what happened and what to do next.
- One optional action: a secondary [button](#button) without an outline, for example "Try again". Its label uses the text color of the banner variant.
- One banner at a time. A new banner replaces the old one.
- The banner has no close button. It goes away when the problem is fixed or the player acts.

#### Variants

| Variant | Background | Text and icon | Icon | Example |
|---------|------------|---------------|------|---------|
| Error | `color.scheme.errorContainer` | `color.scheme.onErrorContainer` | `Icons.error_outline` | The generic error text |
| Warning | `color.status.warningContainer` | `color.status.onWarningContainer` | `Icons.warning_amber_outlined` | "This fursuit is not out right now." (F8) |
| Neutral | `color.scheme.surfaceContainerHighest` | `color.scheme.onSurfaceVariant` | `Icons.info_outlined` | "You already caught this fursuit." (F8) |

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | Variant colors | Stays until the problem is fixed or the player acts |
| Pressed | Not applicable. The action button has its own states. | Not applicable |
| Focused | Not applicable. The action button has its own states. | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | The action button shows its loading state after "Try again". | The banner stays until the retry ends. |
| Error | Not applicable. The error variant is a meaning, not a state. | Not applicable |

#### Accessibility

- The banner is a live region, so the screen reader reads it when it shows.
- The icon is excluded from semantics, because the text says the same thing.
- The icon and the text are the non-color cue.
- 200% text scale: the text wraps and the banner grows taller.
- Touch target: the action is at least `size.minTarget` high.
- Focus: only the action takes focus. The live region does not move focus.

#### Tokens

- The variant colors in the table above
- `typography.bodyMedium`
- `radius.large`
- `spacing.lg` for padding. When the banner has an action, the bottom padding is `spacing.sm`, because the action button has its own padding.
- `spacing.md` between the icon and the text, `spacing.lg` from the screen edges
- `size.icon.medium`

### Top app bar

#### Use

Use a top app bar at the top of each screen. It shows the screen title, the back button, and up to two actions.

Flows: every flow.

#### Do not use

- Do not use a medium or large app bar that collapses on scroll. V0 uses the small app bar only.
- Do not put a search field in the app bar.

#### Flutter widget

`AppBar`, styled through `AppBarThemeData`. Flutter adds the back button when the screen can go back. The back button uses `Icons.adaptive.arrow_back`. The Flutter default iOS back icon is a different shape, so #139 sets the back icon through `ActionIconThemeData`.

#### Content limits

- Title: one line, then an ellipsis. The full name shows in the screen body.
- The title starts at the leading edge on Android and iOS. Flutter centers it on iOS by default, so the theme sets `centerTitle` to false. This keeps the Material look on both platforms.
- Actions: at most two [icon buttons](#icon-button).
- More actions go in an overflow menu, a `PopupMenuButton` with `Icons.adaptive.more`.

#### Variants

Small only.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.surface` fill, `elevation.level0` | Not applicable |
| Pressed | Not applicable. The buttons have their own states. | Not applicable |
| Focused | Not applicable. The buttons have their own states. | Not applicable |
| Disabled | Not applicable | Not applicable |
| Loading | Not applicable | Not applicable |
| Error | Not applicable | Not applicable |
| Scrolled under | `color.scheme.surfaceContainer` fill, `elevation.level2` | Shows when content scrolls under the bar |

#### Accessibility

- The title is a header for the screen reader.
- The back button has the label "Back".
- 200% text scale: the title stays on one line with an ellipsis. #139 tests that the title does not clip.
- Touch target: the back button, each action, and the overflow menu are at least `size.minTarget` wide and high.
- Focus: each button shows the focus ring.

#### Tokens

- `color.scheme.surface`, `color.scheme.surfaceContainer`, `color.scheme.onSurface`, `color.scheme.onSurfaceVariant`
- `elevation.level0`, `elevation.level2`
- `typography.titleLarge`
- `size.icon.medium`, `size.minTarget`

### Bottom navigation bar

#### Use

Use a bottom navigation bar to move between the top-level sections of the app. This file sets the rules for the bar. It does not name the sections. Navigation design names them later.

Flows: every flow that has a top-level section.

#### Do not use

- Do not use the bar for fewer than three or more than five sections.
- Do not use the bar for an action. Use a [button](#button).
- Do not hide the bar when content scrolls.

#### Flutter widget

`NavigationBar` with `NavigationDestination` items, styled through `NavigationBarThemeData`. Labels use `NavigationDestinationLabelBehavior.alwaysShow`.

#### Content limits

- Three to five destinations.
- Each label is one short word, so it fits at 200% text scale.
- Each destination has an Outlined icon and a Filled icon for the selected state.

#### Variants

One.

#### States

| State | Look | Behavior |
|-------|------|----------|
| Normal | `color.scheme.surfaceContainer` fill, `elevation.level2`. Outlined icon and label in `color.scheme.onSurfaceVariant`. | A tap opens the section. |
| Pressed | Pressed state layer on the destination | Not applicable |
| Focused | Focus state layer on the destination | Enter or space opens the section. |
| Disabled | Not applicable | Not applicable |
| Loading | Not applicable | Not applicable |
| Error | Not applicable | Not applicable |
| Selected | Filled icon in `color.scheme.onPrimary` on a solid `color.scheme.primary` pill. Label in `color.scheme.primary`. | The screen reader reads "selected". |

#### Accessibility

- Each destination is a tab with a selected state.
- The change from the Outlined icon to the Filled icon is the non-color cue for selection.
- Touch target: each destination is at least `size.minTarget` wide and high.
- Focus: focus state layer.
- 200% text scale: labels stay on one line. #139 tests that they do not clip.

#### Tokens

- `color.scheme.surfaceContainer`, `color.scheme.primary`, `color.scheme.onPrimary`, `color.scheme.onSurfaceVariant`
- `elevation.level2`
- `typography.labelMedium`
- `size.icon.medium`, `size.minTarget`
