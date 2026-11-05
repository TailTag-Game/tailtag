# Shared UI

This folder holds the TailTag theme and the shared widgets. A shared widget is a user interface part that more than one feature uses. The design source of truth is in `docs/design/`:

- [`tokens.json`](../../../../../docs/design/tokens.json) holds every design token value. A design token is a named design value, such as a color.
- [`components.md`](../../../../../docs/design/components.md) defines each shared component, its states, and its accessibility rules.

## What is here

| File | Contents |
|------|----------|
| `tokens.dart` | The token values as Dart constants, for example `TokenSpacing.lg` |
| `tailtag_theme.dart` | `buildTailTagTheme()`, the status colors, and `context.tailTag` |
| `delayed_visibility.dart` | The 500 ms loading delay and `DelayedVisibility` |
| `generic_error.dart` | The generic error banner text and `genericErrorFor` |
| `ui_strings.dart` | The English text that shared UI owns |
| `widgets/` | The five TailTag widgets |

## How a feature uses it

- Use the Material widget that `components.md` names, for example `Card` or `ListTile`. The theme styles it, so set no colors, shapes, or text styles on it.
- Use `TailTagButton` for every button. Pick its variant. Set `loading` while the action runs.
- Use `StatusBadge` for a status label. In a `ListTile`, place it with `StatusBadge.rowTrailing` and `StatusBadge.rowSubtitle`.
- Use `TailTagAvatar`, `EmptyState`, and `StatusBanner` for those parts.
- For a server error, call `genericErrorFor`. If it returns an error, show it in a `StatusBanner`. If it returns null, the feature decides what to show.
- Wrap a loading indicator in `DelayedVisibility`, so a fast response does not flash.
- For padding and gaps, use the `Token` constants, for example `TokenSpacing.lg`. Do not write a literal size or color.

## Rules

- Shared UI makes no API calls. It imports no Clerk code, repository, router, provider, or feature code. `test/core/api/import_guard_test.dart` checks this. The one exception is `api_failure.dart`, which `generic_error.dart` maps.
- A feature must not copy a shared widget to change it. If a shared widget does not fit a need, change it here through the request process below.

## How to change a token

1. Change `docs/design/tokens.json` and the design README in one pull request, as the design README says.
2. In the same pull request, change the value in `tokens.dart`.
3. Run `task mobile-check`. The token parity test fails until both files match.

## How to request a new shared widget or variant

1. Open a pull request that changes `docs/design/components.md`. The new part must name at least one V0 flow as its consumer. See "Source of truth and changes" in that file.
2. The project owner approves and merges it.
3. Then add the widget here, with tests in `test/core/ui/`.
