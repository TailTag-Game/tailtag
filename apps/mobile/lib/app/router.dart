import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
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
import "package:tailtag_mobile/features/conventions/convention_home_screen.dart";
import "package:tailtag_mobile/features/conventions/convention_picker_screen.dart";
import "package:tailtag_mobile/features/onboarding/onboarding_screen.dart";
import "package:tailtag_mobile/features/passkeys/passkey_screen.dart";

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

  /// Code entry after an email attempt, a child of [email].
  static const code = "/access/email/code";

  /// Code entry after a provider attempt, such as Google, a child of
  /// [access].
  static const providerCode = "/access/code";

  /// Sign-out is running.
  static const signingOut = "/signing-out";

  /// Sign-out failed.
  static const signOutFailed = "/sign-out-failed";

  /// The identity read is running.
  static const identity = "/identity";

  /// The identity read failed. It is not a child of [identity], so Back
  /// cannot show the loading screen.
  static const identityFailed = "/identity-error";

  /// The passkey screen.
  static const passkeys = "/passkeys";

  /// The onboarding form.
  static const onboarding = "/onboarding";

  /// The disabled-profile screen.
  static const accountUnavailable = "/account-unavailable";

  /// The convention picker.
  static const conventionPicker = "/conventions";

  /// The home of the selected convention.
  static const home = "/";

  /// The debug-only Clerk proof screen, above the picker or the home.
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
  EntryPasskeys() => AppPaths.passkeys,
  EntryOnboarding() => AppPaths.onboarding,
  EntryAccountUnavailable() => AppPaths.accountUnavailable,
  EntryConventionPicker() => AppPaths.conventionPicker,
  EntryConventionHome() => AppPaths.home,
};

/// Where [location] must go for [stage], or null when it can stay.
///
/// Each stage allows only its own screens. Any other location, including a
/// deep link to protected content, goes to the stage's screen. Code entry
/// also needs a sent code, and each code screen needs a code from its own
/// kind of attempt: email or provider ([viaProvider]).
@visibleForTesting
String? redirectFor(
  EntryStage stage,
  String location, {
  required bool codeSent,
  bool viaProvider = false,
}) {
  final home = pathForStage(stage);
  final allowed = switch (stage) {
    EntrySignedOut() =>
      location == AppPaths.access ||
          location == AppPaths.email ||
          (location == AppPaths.code && codeSent && !viaProvider) ||
          (location == AppPaths.providerCode && codeSent && viaProvider),
    EntryConventionPicker() || EntryConventionHome() =>
      location == home || (kDebugMode && location == AppPaths.authProof),
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
    redirect: (context, state) {
      final flow = ref.read(accessFlowProvider);
      return redirectFor(
        refresh.value,
        state.uri.path,
        codeSent: flow.codeSent,
        viaProvider: flow.viaProvider,
      );
    },
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
        builder: (context, state) => AccountAccessScreen(
          onChoose: () => context.go(AppPaths.email),
          onProviderCode: () => context.go(AppPaths.providerCode),
        ),
        routes: [
          GoRoute(
            path: "code",
            builder: (context, state) =>
                CodeEntryScreen(onLeave: () => context.go(AppPaths.access)),
          ),
          GoRoute(
            path: "email",
            builder: (context, state) =>
                EmailEntryScreen(onCodeSent: () => context.go(AppPaths.code)),
            routes: [
              GoRoute(
                path: "code",
                builder: (context, state) =>
                    CodeEntryScreen(onLeave: () => context.go(AppPaths.email)),
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
        builder: (context, state) => EntryLoadingScreen(
          label: EntryStrings.loadingAccount,
          onSignOut: ref.read(entryControllerProvider.notifier).signOut,
        ),
      ),
      GoRoute(
        path: AppPaths.identityFailed,
        builder: (context, state) => const IdentityFailedScreen(),
      ),
      GoRoute(
        path: AppPaths.passkeys,
        builder: (context, state) {
          final entry = ref.read(entryControllerProvider.notifier);
          return PasskeyScreen(
            onClose: entry.closePasskeys,
            onSignOut: entry.signOut,
          );
        },
      ),
      GoRoute(
        path: AppPaths.onboarding,
        builder: (context, state) {
          final entry = ref.read(entryControllerProvider.notifier);
          return OnboardingScreen(
            onResolved: entry.acceptProfile,
            onManagePasskeys: entry.openPasskeys,
            onSignOut: entry.signOut,
          );
        },
      ),
      GoRoute(
        path: AppPaths.accountUnavailable,
        builder: (context, state) => const AccountUnavailableScreen(),
      ),
      GoRoute(
        path: AppPaths.conventionPicker,
        builder: (context, state) {
          final entry = ref.read(entryControllerProvider.notifier);
          final stage = ref.read(entryControllerProvider);
          return ConventionPickerScreen(
            onEntered: entry.acceptSelection,
            onIneligible: entry.acceptIneligibleProfile,
            onClose: stage is EntryConventionPicker && stage.current != null
                ? entry.closeConventionPicker
                : null,
            onManagePasskeys: entry.openPasskeys,
            onSignOut: entry.signOut,
            onOpenAuthProof: kDebugMode
                ? () => context.push(AppPaths.authProof)
                : null,
          );
        },
      ),
      GoRoute(
        path: AppPaths.home,
        builder: (context, state) => _ConventionHomeRoute(
          onOpenAuthProof: kDebugMode
              ? () => context.push(AppPaths.authProof)
              : null,
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

/// Gives the home screen the state of its stage.
class _ConventionHomeRoute extends ConsumerWidget {
  const new({required this.onOpenAuthProof});

  final VoidCallback? onOpenAuthProof;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stage = ref.watch(entryControllerProvider);
    if (stage is! EntryConventionHome) {
      return const EntryLoadingScreen(label: EntryStrings.loadingAccount);
    }
    final entry = ref.read(entryControllerProvider.notifier);
    return ConventionHomeScreen(
      enrollment: stage.enrollment,
      refreshing: stage.refreshing,
      refreshFailure: stage.refreshFailure,
      apiAccess: stage.apiAccess,
      onChangeConvention: entry.openConventionPicker,
      onRefresh: entry.refreshHome,
      onManagePasskeys: entry.openPasskeys,
      onSignOut: entry.signOut,
      onOpenAuthProof: onOpenAuthProof,
    );
  }
}
