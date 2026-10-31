# TailTag V0 design tokens

This folder is the source of truth for the TailTag V0 design tokens. A design token is a named design value, such as a color or a spacing step. The tokens set color roles, text styles, spacing, shape, elevation, icon rules, and the accessibility baseline. Shared Flutter widgets (#139) and the component set (#138) use them.

This folder has two files:

| File | Contents |
|------|----------|
| [`tokens.json`](tokens.json) | Every token value. It is the only source of values. |
| `README.md` | The meaning and usage of each token group, and the rules that go with them. |

This README does not repeat token values. To find a value, look it up in `tokens.json` by its token name, for example `color.scheme.primary`.

## Format

`tokens.json` uses the [Design Tokens Format Module 2025.10](https://www.designtokens.org/TR/2025.10/format/). This format is a stable JSON format from a W3C community group. Design tools such as Tokens Studio for Figma can read and write it.

- Each token has a `$type` and a `$value`.
- A color value is an sRGB object with `components` and a `hex` fallback.
- A `px` value is one Flutter logical pixel. That is one dp on Android and one pt on iOS.
- A text style `lineHeight` is a multiplier of the font size. It is the same number as the Flutter `TextStyle.height` value.

## Change process

The current approved definition is the version of this folder on `main`.

To propose a change:

1. Open one pull request that changes `tokens.json` and this README together.
2. If a value changes, update the contrast table in this README.
3. The project owner approves and merges the pull request.

gtrotsuka and RadiantCyrus can review a change before or after the merge. If a designer raises a concern after the merge, a new pull request revises or reverts the change.

## Color

### How the palette was made

The color roles come from one seed color. A seed color is the single brand color that a palette is generated from.

| Item | Value |
|------|-------|
| Seed color | `#7C4DFF` (violet) |
| Scheme variant | `DynamicSchemeVariant.vibrant` |
| Tool | `ColorScheme.fromSeed` in Flutter 3.47.2 |

The project owner chose the Vibrant variant over the default Tonal Spot variant. Tonal Spot mutes this seed to a dusty violet.

To make the palette again, run this in Flutter 3.47.2 and read each role:

```dart
ColorScheme.fromSeed(
  seedColor: const Color(0xFF7C4DFF),
  dynamicSchemeVariant: DynamicSchemeVariant.vibrant,
);
```

Shared widgets read the values from `tokens.json`. They do not call `ColorScheme.fromSeed` at run time. A later Flutter version can then change its generator without changing the TailTag palette.

### Material color roles

The `color.scheme` group holds each non-deprecated Material 3 `ColorScheme` role in Flutter 3.47.2. Each token name is the Flutter property name. An "on" role is the text and icon color for the role that it names.

| Roles | Use |
|-------|-----|
| `primary`, `onPrimary` | The main action on a screen and active states, for example a filled button or a selected tab |
| `primaryContainer`, `onPrimaryContainer` | A softer primary fill, for example a tonal button or the selected navigation pill |
| `secondary` and its container roles | Less prominent controls, for example filter chips |
| `tertiary` and its container roles | A contrasting accent where primary and secondary do not fit |
| `error` and its container roles | Errors and destructive actions |
| `surface`, `surfaceDim`, `surfaceBright` | Screen backgrounds |
| `surfaceContainerLowest` to `surfaceContainerHighest` | Backgrounds that sit on a surface, for example cards, sheets, and text fields. Higher levels sit on top of lower levels. |
| `onSurface` | Main text and icons on any surface role |
| `onSurfaceVariant` | Secondary text, hints, and icons on any surface role |
| `outline` | Edges that a user must see, for example a text field border or an outlined button |
| `outlineVariant` | Decorative dividers only. It has a contrast of 1.61:1, so it must not mark a meaningful edge. |
| `inverseSurface`, `onInverseSurface`, `inversePrimary` | Elements that sit in reverse colors, for example a snackbar and its action |
| The `Fixed` roles | Colors that stay the same in light and dark themes. V0 is light only, so they are rarely needed. |
| `shadow`, `scrim`, `surfaceTint` | Shadows, the dim layer behind a dialog, and the tint that Material adds to raised surfaces |

### Status colors

Material 3 has an error role but no success or warning role. The `color.status` group adds them in the same four-role shape as `error`.

| Roles | Use | Source color |
|-------|-----|--------------|
| `success`, `onSuccess`, `successContainer`, `onSuccessContainer` | A completed action, for example a confirmed catch | `#2E7D32` |
| `warning`, `onWarning`, `warningContainer`, `onWarningContainer` | A state that needs attention but is not an error, for example a slow connection | `#FFB300` |

Each status palette uses the Material custom color tones. Tone 40 is the color and tone 100 is its "on" color. Tone 90 is the container and tone 10 is its "on" color. The status colors are not harmonized with the seed. Harmonizing moves a color toward the seed hue, and here it moves warning toward error.

### Status needs more than color

Color alone must never carry a status. Each status also has an icon and a text label.

| Status | Icon | Text label |
|--------|------|------------|
| Success | `Icons.check_circle_outlined` | Says what succeeded, for example "Catch confirmed" |
| Warning | `Icons.warning_amber_outlined` | Says what needs attention |
| Error | `Icons.error_outlined` | Says what failed and what to do next |
| Selected | The Filled version of the icon replaces the Outlined version | The control label stays visible or readable by a screen reader |

## Light and dark themes

V0 supports the light theme only. The app stays light when the device uses dark mode. This is a known V0 limitation.

The token names are Material role names, so a later dark set can use the same names with new values. A dark theme needs its own contrast table.

## Typography

Text uses the platform system font, `font.family.system`. Flutter uses Roboto on Android and SF Pro on iOS. The repository bundles no font file.

The `typography` group holds the 15 Material 3 text styles from Flutter 3.47.2 `Typography.englishLike2021`.

| Styles | Use |
|--------|-----|
| `displayLarge`, `displayMedium`, `displaySmall` | Large short text, for example a catch count |
| `headlineLarge`, `headlineMedium`, `headlineSmall` | Screen headings |
| `titleLarge`, `titleMedium`, `titleSmall` | App bar titles, section titles, and card titles |
| `bodyLarge`, `bodyMedium`, `bodySmall` | Paragraphs and list row text |
| `labelLarge`, `labelMedium`, `labelSmall` | Buttons, chips, tabs, and captions |

The sizes are for a text scale of 1.0. Flutter multiplies them by the user's text scale. See [Accessibility](#accessibility).

The app name shows as a plain-text "TailTag" wordmark in the system font. See [Brand](#brand).

## Spacing

The `spacing` group is a 4 px grid. Use these steps for padding and gaps. Do not use other values in shared widgets.

| Token | Use |
|-------|-----|
| `spacing.xs` | The gap between an icon and its label |
| `spacing.sm` | Gaps inside a compact group, for example between chips |
| `spacing.md` | Gaps between the parts of a list row or card |
| `spacing.lg` | Screen side padding and card padding |
| `spacing.xl` | Gaps between sections of a screen |
| `spacing.xxl` | Large breaks, for example above a screen's first section |
| `spacing.xxxl` | The space around an empty state |

## Shape

The `radius` group is the Material 3 shape scale. It sets corner radii.

| Token | Use |
|-------|-----|
| `radius.none` | Edge-to-edge images and full-width bars |
| `radius.extraSmall` | Text fields, menus, and snackbars |
| `radius.small` | Chips |
| `radius.medium` | Cards |
| `radius.large` | Side sheets and large floating buttons |
| `radius.extraLarge` | Dialogs and bottom sheets |

Buttons and other pill-shaped controls use a stadium shape (`StadiumBorder`). A stadium shape has fully round ends, so it has no radius token.

## Elevation

The `elevation` group holds the Material 3 elevation levels. Material 3 shows elevation mostly with the surface tint, not with heavy shadows.

| Token | Use |
|-------|-----|
| `elevation.level0` | Flat surfaces |
| `elevation.level1` | Elevated cards and elevated buttons |
| `elevation.level2` | The navigation bar, menus, and an app bar while content scrolls under it |
| `elevation.level3` | Floating action buttons, dialogs, and search bars |
| `elevation.level4` | The hover and focus state of a level 3 element |
| `elevation.level5` | The pressed or dragged state of a level 3 element |

## Icons

Icons come from Material Icons. Flutter includes them through `uses-material-design: true` in `apps/mobile/pubspec.yaml`, so they need no new dependency.

- The default style is Outlined, for example `Icons.home_outlined`.
- The Filled version marks a selected state, for example `Icons.home` on the selected tab.
- Back, share, and more use `Icons.adaptive.arrow_back`, `Icons.adaptive.share`, and `Icons.adaptive.more`. On iOS these show the iOS-style shapes.
- Icons inside buttons and chips use `size.icon.small`. All other icons use `size.icon.medium`.
- Every icon-only control must have a text label for screen readers, for example through `tooltip` or `Semantics`.

## Image placeholders

A player or fursuit without an image shows a placeholder.

- The placeholder shows initials from the display name or fursuit name. It uses up to two initials.
- The background is `surfaceContainerHighest` and the initials are `onSurfaceVariant`.
- If the name is empty, the placeholder shows `Icons.person_outlined` for a player or `Icons.pets_outlined` for a fursuit, in the same colors.

## Accessibility

These rules are the V0 accessibility baseline. Shared widgets (#139) must meet them.

| Rule | Requirement |
|------|-------------|
| Text contrast | At least 4.5:1 for body text. This is WCAG 2.2 level AA. |
| Large text and UI contrast | At least 3:1 for large text, UI component edges, and focus indicators |
| Touch target | At least `size.minTarget` wide and high on Android and iOS |
| Text scale | Core controls stay usable at 200% text scale |
| Status | Color is never the only signal. See [Status needs more than color](#status-needs-more-than-color). |
| Selected state | A selected or toggled control tells screen readers its state. Use a standard Material control, or set `selected` or `toggled` in `Semantics` on a custom control. |
| Focus | The focus indicator color depends on the background. Use `primary` on `surface`, `surfaceDim`, `surfaceBright`, and the `surfaceContainer` roles. Use `inversePrimary` on `inverseSurface`, for example on a snackbar action. |

The `size.minTarget` minimum also covers the 44 pt minimum in the Apple guidelines.

#139 will use these `flutter_test` checks to prove the contrast, target, and label rules:

- `androidTapTargetGuideline`
- `iOSTapTargetGuideline`
- `textContrastGuideline`
- `labeledTapTargetGuideline`

These four checks do not test text scale or selected state. #139 will add two widget tests for those rules:

- A text-scale test sets `TextScaler.linear(2.0)`. It makes sure that no text overflows and that each core control can still be tapped.
- A selected-state test uses `matchesSemantics` to make sure that a selected control reports its state.

### Contrast table

The ratios use the WCAG 2.2 contrast formula on the values in `tokens.json`. The table includes every text and background pair in the tokens. It also includes the status pairs and the placeholder pair (`onSurfaceVariant` on `surfaceContainerHighest`).

| Foreground | Background | Kind | Ratio | Minimum | Result |
|---|---|---|---|---|---|
| `onPrimary` | `primary` | Text | 6.46:1 | 4.5:1 | Pass |
| `onPrimaryContainer` | `primaryContainer` | Text | 7.28:1 | 4.5:1 | Pass |
| `onSecondary` | `secondary` | Text | 6.46:1 | 4.5:1 | Pass |
| `onSecondaryContainer` | `secondaryContainer` | Text | 7.20:1 | 4.5:1 | Pass |
| `onTertiary` | `tertiary` | Text | 6.44:1 | 4.5:1 | Pass |
| `onTertiaryContainer` | `tertiaryContainer` | Text | 7.25:1 | 4.5:1 | Pass |
| `onError` | `error` | Text | 6.46:1 | 4.5:1 | Pass |
| `onErrorContainer` | `errorContainer` | Text | 7.24:1 | 4.5:1 | Pass |
| `onSuccess` | `success` | Text | 6.44:1 | 4.5:1 | Pass |
| `onSuccessContainer` | `successContainer` | Text | 13.18:1 | 4.5:1 | Pass |
| `onWarning` | `warning` | Text | 6.46:1 | 4.5:1 | Pass |
| `onWarningContainer` | `warningContainer` | Text | 13.26:1 | 4.5:1 | Pass |
| `onPrimaryFixed` | `primaryFixed` | Text | 13.31:1 | 4.5:1 | Pass |
| `onPrimaryFixed` | `primaryFixedDim` | Text | 10.04:1 | 4.5:1 | Pass |
| `onPrimaryFixedVariant` | `primaryFixed` | Text | 7.28:1 | 4.5:1 | Pass |
| `onPrimaryFixedVariant` | `primaryFixedDim` | Text | 5.49:1 | 4.5:1 | Pass |
| `onSecondaryFixed` | `secondaryFixed` | Text | 13.20:1 | 4.5:1 | Pass |
| `onSecondaryFixed` | `secondaryFixedDim` | Text | 10.03:1 | 4.5:1 | Pass |
| `onSecondaryFixedVariant` | `secondaryFixed` | Text | 7.20:1 | 4.5:1 | Pass |
| `onSecondaryFixedVariant` | `secondaryFixedDim` | Text | 5.47:1 | 4.5:1 | Pass |
| `onTertiaryFixed` | `tertiaryFixed` | Text | 13.25:1 | 4.5:1 | Pass |
| `onTertiaryFixed` | `tertiaryFixedDim` | Text | 10.08:1 | 4.5:1 | Pass |
| `onTertiaryFixedVariant` | `tertiaryFixed` | Text | 7.25:1 | 4.5:1 | Pass |
| `onTertiaryFixedVariant` | `tertiaryFixedDim` | Text | 5.51:1 | 4.5:1 | Pass |
| `onSurface` | `surface` | Text | 16.26:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceDim` | Text | 12.21:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceBright` | Text | 16.26:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceContainerLowest` | Text | 17.14:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceContainerLow` | Text | 15.52:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceContainer` | Text | 14.72:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceContainerHigh` | Text | 13.94:1 | 4.5:1 | Pass |
| `onSurface` | `surfaceContainerHighest` | Text | 13.28:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surface` | Text | 8.82:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceDim` | Text | 6.62:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceBright` | Text | 8.82:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceContainerLowest` | Text | 9.29:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceContainerLow` | Text | 8.42:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceContainer` | Text | 7.98:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceContainerHigh` | Text | 7.56:1 | 4.5:1 | Pass |
| `onSurfaceVariant` | `surfaceContainerHighest` | Text | 7.20:1 | 4.5:1 | Pass |
| `primary` | `surface` | Text | 6.13:1 | 4.5:1 | Pass |
| `error` | `surface` | Text | 6.13:1 | 4.5:1 | Pass |
| `success` | `surface` | Text | 6.11:1 | 4.5:1 | Pass |
| `warning` | `surface` | Text | 6.13:1 | 4.5:1 | Pass |
| `onInverseSurface` | `inverseSurface` | Text | 11.56:1 | 4.5:1 | Pass |
| `inversePrimary` | `inverseSurface` | Text | 7.68:1 | 4.5:1 | Pass |
| `outline` | `surface` | Component edge | 4.23:1 | 3:1 | Pass |
| `outline` | `surfaceContainerHighest` | Component edge | 3.45:1 | 3:1 | Pass |
| `primary` | `surface` | Focus indicator | 6.13:1 | 3:1 | Pass |
| `primary` | `surfaceDim` | Focus indicator | 4.60:1 | 3:1 | Pass |
| `inversePrimary` | `inverseSurface` | Focus indicator | 7.68:1 | 3:1 | Pass |
| `outlineVariant` | `surface` | Decorative divider | 1.61:1 | None | Decorative only |

## Brand

Finn the Panther (GitHub `FinnThePanther`) owns the TailTag name and brand.

The TailTag code uses the [Apache License 2.0](../../LICENSE). Section 6 of that license grants no permission to use the TailTag name, logos, or other marks.

- V0 has no logo. The app name shows as a plain-text "TailTag" wordmark in the system font.
- Brand files, such as a future logo, go in `docs/design/brand/`. Each brand file must state its own license terms.
- The Flutter default launcher icon and splash screen stay in V0 until a logo exists. #432 tracks the logo, the launcher icon, and the splash screen.
