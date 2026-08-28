# Mobile contributor environment (current scaffold and future contract)

TailTag's Flutter V0 scaffold now exists at `apps/mobile/`, with its
repository-owned FVM configuration at `apps/mobile/.fvmrc`. This guide records
the current scaffold and the contributor environment contract that later child
issues will implement. It does not yet define supported root mobile commands,
runtime configuration, or diagnostics.

The application uses its repository-owned FVM configuration to pin exact stable
Flutter `3.47.1` in `apps/mobile/.fvmrc`, rather than following a moving
`stable` channel. That
Flutter SDK bundles Dart `3.13.1`; Dart is not independently pinned. A Flutter
upgrade requires an explicit, reviewed pull request.

## Prerequisites

All future mobile contributors need the following. IDE choice is deliberately
not mandated.

| Area | Required baseline | Notes |
| --- | --- | --- |
| Common | Git, FVM, the repository-pinned Flutter SDK, future dependency resolution, the future repository-owned validation command, and one supported target | FVM selects Flutter `3.47.1` from `apps/mobile/.fvmrc`; use its bundled Dart `3.13.1`. |
| Android | A compatible JDK, Android SDK and tooling, plus an Android API 24-or-newer emulator | Android is supported on Windows, Linux, and macOS. Android Studio is recommended, but equivalent command-line tooling is sufficient when it satisfies future diagnostics. |
| iOS | macOS, Xcode with its command-line tools selected, completed Xcode first-run/license setup, and an iOS 15.1-or-newer Simulator runtime | CocoaPods is required when native Flutter plugins require it. Windows and Linux contributors do not need Xcode or iOS support. |

macOS contributors may validate either Android or iOS. Phones are the primary
V0 UX target; tablets remain compatible but have no V0-specific optimization
requirement. Launching on a physical device is permitted, but optional.

## Future setup and validation

Once the child issues land, a successful mobile environment means all of the
following:

1. The FVM-selected, repository-pinned Flutter toolchain resolves the future
   mobile dependencies.
2. The future repository-owned mobile validation command succeeds.
3. The app actually launches on at least one supported Android emulator or iOS
   Simulator.

The future root `make mobile-*` commands, configuration flow, and diagnostics
are issue #132 work. Do not infer or rely on those commands before that issue
lands. Issue #131 implements the scaffold and proves initial Android and iOS
builds and launches; issue #133 adds CI; issue #134 adds OpenAPI; issue #135
proves live Clerk; and issue #136 independently validates clean onboarding.

## Future runtime configuration

TailTag will own a typed `AppConfig` populated by compile-time Dart defines.
The configuration selects the API, rather than using flavors or schemes:

| Environment | Approved backend API root |
| --- | --- |
| Local | `http://127.0.0.1:8000` |
| Railway Development | `https://api-development-8fa7.up.railway.app` |

The Local row names the API on the contributor host; it is not a portable
device URL. In the standard Android Emulator, `127.0.0.1` is the emulator
itself. Reaching the host API requires `http://10.0.2.2:8000` or an equivalent
`adb reverse` setup that preserves the approved Local API root. Issue #132 owns
the final commands, configuration mapping, and launch proof. Until that issue
lands, Android Local connectivity is not a supported contributor workflow.

The authentication transport rule is invariant across environments: attach a
Clerk session token as `Authorization: Bearer` only to an HTTPS request within
the configured TailTag API origin. For an HTTP base URL, omit the header; that
configuration cannot exercise authenticated endpoints. Authenticated requests
must not follow redirects automatically. A redirect may be followed only by
validating that its target remains HTTPS and within the configured API origin
before issuing a new request with the header. Use HTTPS termination for
authenticated Local testing or use Railway Development. Never transmit a Clerk
session token over cleartext HTTP or to another origin.

Android apps targeting API 28 or newer reject cleartext HTTP by default. If
issue #132 retains unauthenticated Local HTTP, it must use a narrowly scoped
debug policy rather than a release-wide cleartext exception and must cover the
API 28+ behavior in its validation. The transport rule above still forbids
attaching a Clerk token to those requests.

Future configuration also includes the Clerk Development publishable
configuration. Publishable values are not application secrets, but
compile-time defines are embedded in the app. They must never contain Clerk
secret keys, bearer tokens, signing material, or any other secret.

`clerk_flutter` is the initial SDK direction. Clerk owns session/token refresh
and persistence; TailTag will not create separate persistent bearer-token
storage.

## Scope and references

Issue #130 was documentation-only. Issue #131 implements `apps/mobile/`,
`.fvmrc`, dependencies, platform projects, and application files; Make targets,
runtime configuration, and diagnostics remain assigned to their child issues.

- [FVM project configuration](https://fvm.app/documentation/getting-started/configuration)
  and [basic commands](https://fvm.app/documentation/guides/basic-commands)
- [Flutter SDK archive](https://docs.flutter.dev/install/archive) and
  [supported platforms](https://docs.flutter.dev/reference/supported-platforms)
- [Android setup](https://docs.flutter.dev/platform-integration/android/setup)
  and [iOS setup](https://docs.flutter.dev/platform-integration/ios/setup)
- [Android Emulator host networking](https://developer.android.com/studio/run/emulator-networking-address)
  and [Android network security configuration](https://developer.android.com/privacy-and-security/security-config)
- [Dart compile-time configuration](https://dart.dev/libraries/core/environment-declarations)
  and [app-embedded values](https://docs.flutter.dev/deployment/obfuscate)
