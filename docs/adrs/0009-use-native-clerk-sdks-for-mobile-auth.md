# Use the native Clerk SDKs for mobile authentication

**Status:** accepted (2026-10-16)

## Context and constraints

ADR 0006 chose `clerk_flutter` as an initial beta direction and asked issue #135 to reassess it. The reassessment found two problems.

- `clerk_flutter` and `clerk_auth` (`0.0.18-beta`) are community-maintained. Clerk does not support them.
- By default, `clerk_flutter` stores the client token in a plaintext file in the app Documents folder.

Clerk supports its own native SDKs: `clerk-ios` and `clerk-android`. Both are at version 1. Both have headless functions (functions without prebuilt screens) for sign-in, `getToken`, and `signOut`. Both keep the session in secure storage by default.

ADR 0003 still holds. Clerk stays the player authentication authority. ADR 0006 still holds for bearer tokens, origins, redirects, and token storage. TailTag adds no token store of its own.

## Decision

Use the official native Clerk SDKs through a TailTag-owned bridge:

- iOS uses `ClerkKit` `1.6.1`, installed with Swift Package Manager and pinned to `exact: "1.6.1"`.
- Android uses `com.clerk:clerk-android-api:1.2.1`.
- Both platforms use headless functions only.
- The local plugin package `apps/mobile/packages/tailtag_clerk/` connects the SDKs to Flutter with one MethodChannel and one EventChannel. Its Swift and Kotlin code is the only code that imports Clerk.
- Only `lib/core/auth/` in the Dart app imports the bridge. The rest of the app uses the TailTag `AuthSession`, `AuthState`, and `AuthFailure` types.
- Clerk prebuilt UI (`ClerkKitUI`, `clerk-android-ui`) is not used.
- Clerk telemetry is off on both platforms.

The iOS minimum version becomes 17.0. Android `minSdk` stays 26.

## Alternatives considered

- `clerk_flutter` and `clerk_auth`. Rejected because a community group maintains them, Clerk does not support them, and the default storage is a plaintext file.
- A TailTag-owned client for the Clerk Frontend API. Rejected because TailTag would own the sign-in protocol and the session lifecycle. This is the work that ADR 0003 avoids.
- Revisit Clerk (ADR 0003). Not needed. The problem is the Flutter package, not Clerk.

## Consequences and risks

- iOS 17.0 is the minimum. These devices can no longer install the app: iPhone 8, 8 Plus, X, and older; iPad (5th generation), iPad Pro 9.7-inch, iPad Pro 12.9-inch (1st generation), and older.
- iOS contributors need Xcode 26 or later (Swift 6.2). `clerk-ios` installs only through Swift Package Manager. The CI `macos-latest` runner must keep meeting this requirement.
- Each SDK uses its default secure storage. iOS uses the Keychain, for this device only. Android uses preferences that a Keystore key encrypts. TailTag adds no storage.
- Native bearer tokens likely carry no `azp` claim. The `azp` claim names the web origin that asked for the token. The backend rejects a token without `azp` when `CLERK_AUTHORIZED_PARTIES` is set, and that setting is required. The live proof cannot return 200 until the backend accepts native tokens. This needs a backend SECURITY follow-up before the live proof. Issue #135 does not change the backend. It only records whether `azp` exists.
- Each SDK upgrade needs a review and a new live proof. The Clerk `@FrameworkIntegrationApi` functions can change in minor releases, so the app does not use them.
- The bridge adds Swift and Kotlin code to maintain. It is small: five calls and one state event stream.

## Validation and rollback

Issue #135 validates the decision with Dart tests (a fake `AuthSession`, a channel-contract test, and an import guard) and a live proof on an Android emulator and an iOS simulator against the Development API. To roll back, replace the bridge with another implementation of `AuthSession`. No other app code changes, because only `lib/core/auth/` knows the bridge.

## References

- [`clerk-ios`](https://github.com/clerk/clerk-ios) and [`clerk-android`](https://github.com/clerk/clerk-android)
- Issue #135 and ADR 0006
