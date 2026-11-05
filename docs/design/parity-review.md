# V0 design and code parity review

This file records the V0 review of the shared Flutter components against the design source. A parity review is a check that the code matches the approved design. It also records the V0 accessibility pass. #140 owns this review.

## What was reviewed

| Item | Value |
|------|-------|
| Design source | [`tokens.json`](tokens.json), [`components.md`](components.md), and the design [README](README.md) on `main` at `406e290` |
| Code | `apps/mobile/lib/core/ui/` and the showcase in `apps/mobile/lib/showcase/` at `1c5aa20` |
| Date | 2026-11-05 |
| Reviewer | The #140 implementation agent. The project owner approves this record in the #140 pull request. |

## Method

- The agent ran the showcase with `task mobile-showcase`. It walked every section on an iPhone 17 simulator (iOS 26.5) and a Pixel 6 emulator (Android API 35).
- Each section was checked at 100% and at 200% text scale against the states table of its component in `components.md`.
- The agent opened the live examples. These are the loading buttons, the dialog and its loading state, the choice sheet with its loading and error states, and the snackbar.
- The agent walked keyboard focus with Tab on both platforms.
- The agent read the iOS accessibility tree of every tab with `idb ui describe-all`.
- Automated checks ran in `task mobile-check`. See [Automated checks](#automated-checks).

## Tokens

| Check | Result |
|-------|--------|
| Every token in `tokens.json` has the same Dart value | Pass. `token_parity_test.dart` checks both directions against the catalog in `lib/showcase/token_catalog.dart`. |
| The theme takes each color role and text style from the tokens | Pass. The same test checks the `ColorScheme`, the `TextTheme`, and the status colors. |
| The Tokens tab shows every token | Pass. `showcase_test.dart` finds each catalog name on the tab. The walk found no wrong swatch, text style, or size. |

## Components

Each row lists the states of the states table that apply. "Live" means that the state shows only during a real press, focus, or server wait. See [Showcase limits](#showcase-limits).

| Component | States checked | iOS | Android | Mismatch | Decision | Follow-up |
|-----------|----------------|-----|---------|----------|----------|-----------|
| Button | Normal, pressed, focused, disabled, loading for all four variants. Leading icon. 200% wrap. | Pass | Pass | None | None | None |
| Icon button | Normal, pressed, focused, disabled. Tooltip label. | Pass | Pass | None | None | None |
| Text field | Normal, focused, error, disabled. Helper text to three lines. Counter. Live validation. | Pass | Pass | None | None | None |
| Card | Normal with buttons, tappable card (pressed and focused live), two-line title, three-line text | Pass | Pass | None | Focus layer: see [Focus state layer](#focus-state-layer) | F-1 |
| List row | Navigation, info, disabled, and selected choice rows. Two-line title and subtitle. Badge below the title above 1.3 text scale. Pressed and focused live. | Pass | Pass | None | Focus layer: see [Focus state layer](#focus-state-layer) | F-1 |
| Avatar | Image, initials, one word, empty player, empty fursuit, photo, loading, error | Pass | Pass | None | None | None |
| Badge | Neutral with icon, neutral, success, warning, error | Pass | Pass | None | None | None |
| Chip | Normal, selected, focused, disabled. Long name wraps to two lines. Pressed live. | Pass | Pass | None | None | None |
| Dialog | Normal, loading confirm with Cancel disabled, error closes the dialog and shows a banner | Pass | Pass | None | None | None |
| Bottom sheet | Choice sheet, loading list, error banner at the top, photo choices, form sheet | Pass | Pass | None | None | None |
| Snackbar | Normal | Pass | Pass | None | None | None |
| Switch | On, off, loading with "Updating" after 500 ms, error keeps the old position, disabled, confirm before off. Pressed and focused live. | Pass | Pass | None | Focus layer: see [Focus state layer](#focus-state-layer) | F-1 |
| Loading indicator | Screen and small sizes, 500 ms delay, pull to refresh | Pass | Pass | None | None | None |
| Empty state | With and without an action | Pass | Pass | None | None | None |
| Status banner | Error (three generic texts), warning, neutral, loading action | Pass | Pass | None | None | None |
| Top app bar | Normal, scrolled under, long title, two actions, overflow menu | Pass | Pass | None | The title stops growing at about 134% text scale. See [Text scale limits](#text-scale-limits). | None |
| Bottom navigation bar | Normal, selected. Pressed and focused live. | Pass | Pass | None | Focus layer and labels: see [Focus state layer](#focus-state-layer) and [Text scale limits](#text-scale-limits) | F-1 |

The review found no place where the code differs from `components.md` or `tokens.json`.

## Accessibility pass

| Area | Result |
|------|--------|
| Semantics | Pass. Every control in the iOS accessibility tree has a label. Chips, choice rows, and navigation destinations report "selected". Switches report on or off. Loading buttons report "Loading". Avatars stay out of the tree, and a row badge is part of the row label. |
| Target size | Pass. Every control is at least 48 by 48 points. The four Flutter guidelines pass on every showcase tab. |
| Contrast | Pass for text and control edges. `textContrastGuideline` passes on every tab, and the design README contrast table covers the token pairs. The focus state layer does not pass. See [Focus state layer](#focus-state-layer). |
| Text scale | Pass. At 200%, nothing clips on either platform, and buttons, banners, and rows grow. A build test covers each tab at 200% on a 360 by 640 screen. |
| Non-color state | Pass. Badges and banners have status icons. Switches have check and close icons. Selected chips and navigation destinations change their fill and icon. |
| Focus order | Finding. See [Focus order](#focus-order). |

The iOS Accessibility Inspector app needs a person at the Mac. The agent read the same accessibility tree with `idb ui describe-all` instead. The project owner can run an Inspector audit as an extra check.

### Focus state layer

List rows, tappable cards, switch rows, and navigation destinations show focus as a Material state layer. On both platforms the layer is hard to see. It does not meet the 3:1 focus indicator minimum in the design README.

Decision: V0 accepts this gap. Keyboard and switch access are rare in the V0 flows, and a ring needs a shared widget change. Follow-up F-1 tracks a possible ring.

### Focus order

In the first walk, Tab moved from page content into the bottom navigation bar, and then back to the page. Flutter sorts focus in reading order, so the always-visible bar sits between the visible content and the content below it.

The showcase now wraps its page in a `FocusTraversalGroup`. With the group, Tab visits the whole page before the bar. App screens need the same rule, and `components.md` does not state it. Follow-up F-2 adds the rule.

### Text scale limits

Flutter limits two text styles below 200%. The bottom navigation bar labels stop at 130%, and the top app bar title stops at about 134%. These limits are Flutter defaults. The labels stay on one line, as `components.md` asks. V0 accepts them.

## Showcase limits

- Flutter draws the pressed and focused state layer of rows, cards, switch rows, and navigation destinations only during a real press or focus. The showcase shows these states live only.
- Buttons, icon buttons, and chips show the focused look as fixed examples. The showcase resolves the real theme style in the focused state. Buttons and icon buttons also show a fixed pressed layer that the showcase paints at the Material pressed opacity.
- The avatar image comes from a local server inside the showcase, so the review used the real `Image.network` path with no external host.

## Automated checks

| Check | File |
|-------|------|
| Token values match `tokens.json` | `test/core/ui/token_parity_test.dart` |
| Each tab builds at 100% and 200% with no setup and no network | `test/showcase/showcase_test.dart` |
| The showcase sections match the `components.md` inventory | `test/showcase/showcase_test.dart` |
| The Tokens tab shows every token | `test/showcase/showcase_test.dart` |
| Each tab meets the four Flutter accessibility guidelines | `test/showcase/showcase_test.dart` |
| The showcase imports no API, Clerk, configuration, or app code, and no app code imports it | `test/core/api/import_guard_test.dart` |

## Follow-ups

The project owner approves each follow-up before an issue opens.

| ID | Follow-up | Issue |
|----|-----------|-------|
| F-1 | Decide whether list rows, tappable cards, switch rows, and navigation destinations need a focus ring that meets 3:1 | Pending |
| F-2 | Add a focus order rule to `components.md`: a screen puts its body and its bottom navigation bar in separate focus groups | Pending |
