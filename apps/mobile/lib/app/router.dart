import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";
import "package:tailtag_mobile/app/debug/auth_proof_screen.dart";
import "package:tailtag_mobile/app/entry/entry_controller.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_screen.dart";
import "package:tailtag_mobile/features/account_access/code_entry_screen.dart";
import "package:tailtag_mobile/features/account_access/email_entry_screen.dart";

/// The route paths of the entry stages and the account-access flow.
abstract final class AppPaths {
  /// The native SDK is loading the session.
  static const restoring = "/start";

  /// The native SDK failed.
  static const recovery = "/recovery";

  /// The signed-out account screen.
  static const access = "/access";

  /// Email entry, a child of [access].
  static const email = "/access/email";

  /// Code entry, a child of [email].
  static const code = "/access/email/code";

  /// Sign-out is running.
  static const signingOut = "/signing-out";

  /// Sign-out failed.
  static const signOutFailed = "/sign-out-failed";

  /// The identity read is running.
  static const identity = "/identity";

  /// The identity read failed. It is not a child of [identity], so Back
  /// cannot show the loading screen.
  static const identityFailed = "/identity-error";

  /// The neutral landing.
  static const landing = "/";

  /// The debug-only Clerk proof screen, a child of [landing].
  static const authProof = "/debug/auth";
}

/// The path of the screen that [stage] shows.
String pathForStage(EntryStage stage) => switch (stage) {
  EntryRestoring() => AppPaths.restoring,
  EntryAuthRecovery() => AppPaths.recovery,
  EntrySignedOut() => AppPaths.access,
  EntrySigningOut() => AppPaths.signingOut,
  EntrySignOutFailed() => AppPaths.signOutFailed,
  EntryIdentityLoading() => AppPaths.identity,
  EntryIdentityFailed() => AppPaths.identityFailed,
  EntryReady() => AppPaths.landing,
};

/// Where [location] must go for [stage], or null when it can stay.
///
/// Each stage allows only its own screens. Any other location, including a
/// deep link to protected content, goes to the stage's screen. Code entry
/// also needs a sent code.
@visibleForTesting
String? redirectFor(
  EntryStage stage,
  String location, {
  required bool codeSent,
}) {
  final home = pathForStage(stage);
  final allowed = switch (stage) {
    EntrySignedOut() =>
      location == AppPaths.access ||
          location == AppPaths.email ||
          (location == AppPaths.code && codeSent),
    EntryReady() =>
      location == AppPaths.landing ||
          (kDebugMode && location == AppPaths.authProof),
    _ => location == home,
  };
  if (allowed) {
    return null;
  }
  if (stage is EntrySignedOut && location == AppPaths.code) {
    return AppPaths.email;
  }
  return home;
}

/// The application router.
///
/// The entry coordinator decides the stage, and `redirect` keeps the
/// location inside that stage's screens. A stage change replaces the whole
/// navigation stack, so Back cannot reopen an earlier stage.
final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<EntryStage>(ref.read(entryControllerProvider));
  ref
    ..listen(entryControllerProvider, (_, next) => refresh.value = next)
    ..onDispose(refresh.dispose);

  final router = GoRouter(
    initialLocation: pathForStage(refresh.value),
    refreshListenable: refresh,
    redirect: (context, state) => redirectFor(
      refresh.value,
      state.uri.path,
      codeSent: ref.read(accessFlowProvider).codeSent,
    ),
    routes: [
      GoRoute(
        path: AppPaths.restoring,
        builder: (context, state) =>
            const EntryLoadingScreen(label: EntryStrings.restoring),
      ),
      GoRoute(
        path: AppPaths.recovery,
        builder: (context, state) => const AuthRecoveryScreen(),
      ),
      GoRoute(
        path: AppPaths.access,
        builder: (context, state) =>
            AccountAccessScreen(onChoose: () => context.go(AppPaths.email)),
        routes: [
          GoRoute(
            path: "email",
            builder: (context, state) =>
                EmailEntryScreen(onCodeSent: () => context.go(AppPaths.code)),
            routes: [
              GoRoute(
                path: "code",
                builder: (context, state) => CodeEntryScreen(
                  onChangeEmail: () => context.go(AppPaths.email),
                ),
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        path: AppPaths.signingOut,
        builder: (context, state) =>
            const EntryLoadingScreen(label: EntryStrings.signingOut),
      ),
      GoRoute(
        path: AppPaths.signOutFailed,
        builder: (context, state) => const SignOutFailedScreen(),
      ),
      GoRoute(
        path: AppPaths.identity,
        builder: (context, state) =>
            const EntryLoadingScreen(label: EntryStrings.loadingAccount),
      ),
      GoRoute(
        path: AppPaths.identityFailed,
        builder: (context, state) => const IdentityFailedScreen(),
      ),
      GoRoute(
        path: AppPaths.landing,
        builder: (context, state) => NeutralLandingScreen(
          onOpenAuthProof: () => context.push(AppPaths.authProof),
        ),
      ),
      if (kDebugMode)
        GoRoute(
          path: AppPaths.authProof,
          builder: (context, state) => const AuthProofScreen(),
        ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
