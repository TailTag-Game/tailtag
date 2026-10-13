# Flutter contributor tooling, configuration, and diagnostics — implementation contract

Issue: [#132](https://github.com/TailTag-Game/tailtag/issues/132) (parent #128,
child A3). The approved refinement is recorded as an
[issue comment](https://github.com/TailTag-Game/tailtag/issues/132#issuecomment-6131858321);
its acceptance criteria AC1–AC25 are the Acceptance Contract and are not
restated here. This document freezes the interfaces that implementation and
tests share.
([Implementation plan](2026-10-12-mobile-contributor-tooling-implementation-plan.md))

## Decisions carried from refinement

- G1 opt-in `./scripts/doctor.sh --mobile`; G2 `adb reverse` for Android Local;
  G3 no cleartext policy (Dart-owned sockets are not governed by Android network
  security config or iOS ATS); G4 gitignored JSON via `--dart-define-from-file`
  and one pure-Dart validator; G5 origin-only URL, `https` or loopback `http`;
  G6 contributor-supplied `pk_test_` key; G7 `mobile-check` does not build;
  G8 required `DEVICE`, no auto-boot or auto-install; G9 macOS/Linux Make,
  documented raw `fvm` commands on Windows; G10 host `/health/live` probe with
  WARN on unreachable; G11 LAN-IP Local unsupported; G12 Dart unit tests plus
  `scripts/test_doctor.sh` fakes; G13 throwaway, uncommitted in-app probe.

## Scope guard

- **Outcome:** AC1–AC25.
- **Non-goals:** CI workflow changes (#133); HTTP client, `package:http`, or
  OpenAPI (#134); Clerk SDK (#135); product UI; Android network security config
  or iOS ATS changes; `DJANGO_ALLOWED_HOSTS` or any backend change; new
  dependencies; Windows Make support; a `mobile-build` target.
- **Expected change surface:** `Makefile`, `scripts/doctor.sh`,
  `scripts/test_doctor.sh`, new `scripts/mobile_run.sh`,
  `apps/mobile/lib/core/config/app_config.dart`, `apps/mobile/lib/main.dart`,
  new `apps/mobile/tool/check_config.dart`,
  new `apps/mobile/config/development.example.json`, `apps/mobile/.gitignore`,
  `apps/mobile/test/` (config tests, startup test), `apps/mobile/README.md`,
  `docs/development/mobile.md`, `docs/development/getting-started.md`,
  `docs/architecture.md` (replace the superseded `10.0.2.2`/cleartext paragraph),
  `docs/adrs/0006-use-flutter-for-mobile-v0.md` (one pointer sentence),
  `docs/specs/README.md`, and this contract and its plan.
- **Reversibility:** two-way door. All changes are contributor tooling and
  documentation; no persistence, public API, or deployed configuration changes.

## U1 — Dart configuration (AC8–AC11, AC23)

### `AppConfig` (`apps/mobile/lib/core/config/app_config.dart`)

Pure Dart; must not import `package:flutter` (directly or transitively) so
`fvm dart run` can execute the validation tool.

```dart
const String apiBaseUrlKey = "TAILTAG_API_BASE_URL";
const String clerkPublishableKeyKey = "CLERK_PUBLISHABLE_KEY";

final class AppConfig {
  // apiBaseUrl is the normalized origin: scheme://host[:port], no trailing "/".
  final Uri apiBaseUrl;
  final String clerkPublishableKey;

  /// Validates raw string values keyed by the two key names. Missing keys are
  /// treated as empty strings. Throws AppConfigException listing every
  /// problem (not just the first), in key order: API URL first, then Clerk.
  static AppConfig parse(Map<String, String> values);

  /// Parses the text of a `--dart-define-from-file` JSON object. Non-object
  /// JSON, malformed JSON, or a non-string value for either required key is a
  /// problem; other keys are ignored.
  static AppConfig parseDefinesJson(String jsonText);

  /// Reads both keys with `const String.fromEnvironment` and calls parse.
  factory AppConfig.fromEnvironment();
}

final class AppConfigProblem {
  final String key;      // one of the two key names, or "file" for JSON shape
  final String message;  // must never contain the offending value
}

final class AppConfigException implements Exception {
  final List<AppConfigProblem> problems; // non-empty
  // toString(): one line per problem: "<key>: <message>"
}
```

**URL rules (AC10).** Accept only when, after `Uri.tryParse`, the value: is
non-empty; has scheme `https`, or `http` with host exactly `127.0.0.1` or
`localhost` (case-insensitive); has a non-empty host; has no userinfo, query,
or fragment; and has an empty path or exactly `/`. An explicit port is allowed.
Normalize by dropping a trailing `/`. Leading/trailing whitespace is a problem,
not trimmed.

**Clerk rules (AC11).** Reject when empty; when it starts with `pk_live_` or
`sk_` (message says live/secret keys are forbidden); when it does not start
with `pk_test_`; or when it equals `pk_test_` with nothing after it.

**No value echo (AC9).** No problem message or exception text may include any
part of the supplied value beyond the key name.

### Startup (`apps/mobile/lib/main.dart`)

```dart
void main() => runTailTagApp(AppConfig.fromEnvironment());

/// Starts the app with validated configuration available to Riverpod.
void runTailTagApp(AppConfig config);
```

`runTailTagApp` calls `runApp(ProviderScope(overrides: [appConfigProvider
.overrideWithValue(config)], child: const TailTagApp()))`. `appConfigProvider`
lives next to `AppConfig` in a Flutter-importing file
(`apps/mobile/lib/core/config/app_config_provider.dart`) and throws
`StateError` if read without an override. `main()` with no defines must throw
`AppConfigException` before `runApp` (fail fast).

### Validation tool (`apps/mobile/tool/check_config.dart`)

`fvm dart run tool/check_config.dart <path>` run from `apps/mobile/`.

| Situation | stdout | stderr | exit |
| --- | --- | --- | --- |
| Valid | normalized origin, one line | — | 0 |
| File missing | — | `missing: <path>` | 2 |
| Invalid | — | one line per problem, `<key>: <message>` | 1 |
| No/extra arguments | — | usage line | 64 |

The tool contains only file I/O and exit-code mapping; all validation is in
`AppConfig.parseDefinesJson`.

### Configuration files

- `apps/mobile/config/development.example.json` (committed):
  `{"TAILTAG_API_BASE_URL": "https://dev.tailtag.app", "CLERK_PUBLISHABLE_KEY": ""}`.
  The empty key deliberately fails validation until a contributor supplies it.
- `apps/mobile/config/development.json` is gitignored via
  `apps/mobile/.gitignore` entry `/config/development.json`.

## U2 — Shell tooling (AC1–AC7, AC12–AC14, AC24)

### Shared host guard

Every `mobile-*` Make target first fails with exit 1 and
`Mobile commands run on the host, not in the TailTag devcontainer.` when
`TAILTAG_DEVCONTAINER=1`.

### Make targets (`Makefile`)

All run Flutter/Dart through `fvm` from `apps/mobile/`; `help` header becomes
`TailTag developer commands:` and its description `List the canonical
developer commands.`

| Target | Behavior |
| --- | --- |
| `mobile-setup` | Fail with an install hint if `fvm` is missing; fail with `fvm install` hint (run from `apps/mobile`) if the pinned SDK is not installed (same detection as doctor); otherwise `fvm flutter pub get --enforce-lockfile`. Never runs `fvm install`. |
| `mobile-format-check` | `fvm dart format --output=none --set-exit-if-changed .` |
| `mobile-analyze` | `fvm flutter analyze` |
| `mobile-test` | `fvm flutter test` (no defines) |
| `mobile-check` | `mobile-format-check mobile-analyze mobile-test`; help text states it does not build. Listed in `.NOTPARALLEL`. |
| `mobile-run` | `DEVICE=$(DEVICE) ./scripts/mobile_run.sh` |
| `mobile-doctor` | `./scripts/doctor.sh --mobile` |

### `scripts/mobile_run.sh`

Runs from the repository root. Order:

1. Devcontainer guard; require `fvm`.
2. Resolve the device: `DEVICE` must match `^[A-Za-z0-9._:-]+$`; strip all
   whitespace from `fvm flutter devices --machine` and read the
   `targetPlatform` value that follows `"id":"<DEVICE>"` within the same device
   object. If `DEVICE` is empty, malformed, or not listed, print the
   `fvm flutter devices` output and
   `Start one with: fvm flutter emulators --launch <emulator-id>`, and exit 1.
   If its platform is neither `android*` nor `ios`, exit 1 stating TailTag
   supports Android and iOS targets. Never boot a device.
3. Run the validation tool on `apps/mobile/config/development.json`. On exit 2
   print `Copy the template: cp apps/mobile/config/development.example.json apps/mobile/config/development.json`
   then exit 1; on other non-zero, print the tool's problems and exit 1.
4. If the origin starts with `http://` (Local) and the platform is Android,
   require `adb` (fail with an install/PATH hint if missing) and run
   `adb -s "$DEVICE" reverse tcp:<port> tcp:<port>`, where `<port>` is the
   origin's port or `80`; fail if it fails.
5. `exec fvm flutter run -d "$DEVICE" --dart-define-from-file=config/development.json`
   from `apps/mobile/`.

### Pinned SDK detection

The pinned version is the `flutter` value in `apps/mobile/.fvmrc`. It is
installed when the `versions` array of `fvm api list --compress` has an entry
whose `name` equals it. Entries under `projects` must not count. Never call
`fvm api context` (it prints the whole process environment).

### `scripts/doctor.sh --mobile` (AC12–AC14)

Default (no argument): behavior and exit status unchanged; append one line
after the section output: `Mobile checks: run ./scripts/doctor.sh --mobile on the host.`
Unknown argument: usage to stderr, exit 2.

With `--mobile`: run the existing Repository section, then a
`Mobile environment (host)` section; backend Host/devcontainer sections are
not run. Exit 1 if any FAIL.

| Check | Result |
| --- | --- |
| `TAILTAG_DEVCONTAINER=1` | `FAIL  Mobile checks run on the host, not in the TailTag devcontainer` and skip the rest of the section |
| `fvm` missing | `FAIL  FVM is not installed; ...` with install link; skip SDK-dependent checks with `WARN  ... skipped` |
| pinned SDK missing | `FAIL  Flutter <v> (pinned in apps/mobile/.fvmrc) is not installed; run: (cd apps/mobile && fvm install)` |
| toolchains | Parse `fvm flutter doctor` output lines `[✓]`/`[!]`/`[✗]` for `Android toolchain` and `Xcode`. `[✓]` PASS; `[!]` WARN (usable, see `fvm flutter doctor -v`); `[✗]` or absent = not usable. FAIL when neither is usable; WARN for the one that is not usable when the other is; on non-macOS (`uname -s` ≠ `Darwin`) report iOS as `PASS  iOS is not applicable on this host` style informational line instead of a WARN. |
| devices | WARN when `fvm flutter devices --machine` lists no device whose `targetPlatform` starts with `android` or equals `ios`, with hint `fvm flutter emulators --launch <emulator-id>` |
| config missing | `WARN  Mobile configuration is missing; run: cp apps/mobile/config/development.example.json apps/mobile/config/development.json` |
| config invalid | `FAIL  Mobile configuration is invalid` followed by the tool's problem lines |
| API reachable | With valid config: `curl -fsS --max-time 5 <origin>/health/live` success → PASS naming the origin, failure → WARN; both lines state host reachability does not prove device reachability. `curl` missing → WARN. |

## U3 — Documentation (AC15–AC21)

- `docs/development/mobile.md`: replace "future" sections with the implemented
  command table (with `make api-*` relationship and the deterministic vs
  interactive/live split), configuration flow, connectivity matrix (iOS
  Simulator loopback; Android emulator and USB Android via `adb reverse`; iOS
  devices and Wi-Fi Android via Railway Development; LAN-IP Local unsupported),
  Railway Development guidance (approved root `https://dev.tailtag.app`
  supplied in the config file, no production access implied), Clerk key
  source, Windows raw-command table, and the G3 cleartext note.
- ADR 0006: one sentence in "Validation and future migration" pointing to the
  G3 note in `docs/development/mobile.md`.
- `apps/mobile/README.md`, `docs/development/getting-started.md`: point to the
  implemented commands; stop deferring to #132.
- `docs/specs/README.md`: list this contract.

## Frozen test surface and failure/value map

Observation points: the public Dart API above; `tool/check_config.dart`
stdout/stderr/exit; `doctor.sh` stdout lines and exit status under the
existing `scripts/test_doctor.sh` fake-tool PATH harness; Make/run-script
behavior by recorded manual evidence (AC24).

| Failure mode | Consequence | Test |
| --- | --- | --- |
| URL rules accept a non-loopback `http`, a path, query, userinfo, or fragment; reject a valid `https`/loopback origin | Cleartext to arbitrary hosts or contributor lockout | Table-driven `AppConfig.parse` cases |
| Clerk rules accept `pk_live_`/`sk_`/empty/bare `pk_test_` | Live or secret keys embedded in app | Same table |
| Problem text echoes values | Key or URL leaks into logs | Assertion over every rejection case |
| Only first problem reported | Slow fix loop | One case with both keys invalid |
| JSON shape errors crash instead of reporting | Unclear failure | `parseDefinesJson` cases: malformed, non-object, non-string value, extra keys ignored |
| `main()` launches without valid defines | Silent misconfiguration | Startup test: `main()` throws `AppConfigException`; existing placeholder test switches to `runTailTagApp(validConfig)` |
| Doctor default run changes | Backend/docs contributors broken | Existing default-path tests stay green plus hint-line assertion |
| Doctor mis-classifies mobile states | Wrong next step | One fake-tool case per row of the doctor table, including a `projects`-only SDK false positive |

No test covers Flutter, FVM, or `adb` behavior itself.
