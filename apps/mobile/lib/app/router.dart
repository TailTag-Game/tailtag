import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";
import "package:tailtag_mobile/app/debug/auth_proof_screen.dart";
import "package:tailtag_mobile/app/entry/entry_controller.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_screen.dart";
import "package:tailtag_mobile/features/account_access/code_entry_screen.dart";
import "package:tailtag_mobile/features/account_access/email_entry_screen.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";
import "package:tailtag_mobile/features/catches/catches_controller.dart";
import "package:tailtag_mobile/features/catches/catches_screen.dart";
import "package:tailtag_mobile/features/catches/requests_controller.dart";
import "package:tailtag_mobile/features/catches/requests_screen.dart";
import "package:tailtag_mobile/features/catches/scan_screen.dart";
import "package:tailtag_mobile/features/conventions/convention_home_screen.dart";
import "package:tailtag_mobile/features/conventions/convention_picker_screen.dart";
import "package:tailtag_mobile/features/fursuits/suit_detail_screen.dart";
import "package:tailtag_mobile/features/fursuits/suit_list_screen.dart";
import "package:tailtag_mobile/features/fursuits/suit_register_screen.dart";
import "package:tailtag_mobile/features/fursuits/suits_controller.dart";
import "package:tailtag_mobile/features/fursuits/tag_screen.dart";
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

  /// The suit list, above the home.
  static const suits = "/fursuits";

  /// The register form, above the suit list.
  static const registerSuit = "/fursuits/new";

  /// The suit screen of suit [id], above the suit list.
  static String suit(int id) => "/fursuits/$id";

  /// The tag screen of suit [id], full screen above the bar.
  static String suitTag(int id) => "/fursuits/$id/tag";

  /// The scanner, full screen above the bar.
  static const scan = "/scan";

  /// The collection section.
  static const catches = "/catches";

  /// The request list section.
  static const requests = "/requests";
}

/// The bar sections of the convention home stage, in bar order (#511 G2).
const List<String> _sectionPaths = [
  AppPaths.home,
  AppPaths.catches,
  AppPaths.requests,
  AppPaths.suits,
];

/// Whether [location] is a suit screen or a suit's tag screen. A suit ID
/// must fit in an `int`.
bool _isSuitPath(String location) {
  if (location == AppPaths.suits || location == AppPaths.registerSuit) {
    return true;
  }
  final match = RegExp(r"^/fursuits/([1-9][0-9]*)(/tag)?$")
      .firstMatch(location);
  return match != null && int.tryParse(match.group(1)!) != null;
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
    EntryConventionHome() =>
      location == home ||
          _isSuitPath(location) ||
          location == AppPaths.scan ||
          location == AppPaths.catches ||
          location == AppPaths.requests ||
          (kDebugMode && location == AppPaths.authProof),
    EntryConventionPicker() =>
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

  final rootKey = GlobalKey<NavigatorState>();
  final router = GoRouter(
    navigatorKey: rootKey,
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
      // The convention home stage: four sections with a bottom navigation
      // bar. Each section keeps its own stack (#511 AC1, AC2).
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => _HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppPaths.home,
                builder: (context, state) => _ConventionHomeRoute(
                  onOpenAuthProof: kDebugMode
                      ? () => context.push(AppPaths.authProof)
                      : null,
                ),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppPaths.catches,
                builder: (context, state) => _SuitsRoute(
                  builder: (convention) =>
                      CatchesScreen(convention: convention),
                ),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppPaths.requests,
                builder: (context, state) => _SuitsRoute(
                  builder: (convention) => RequestsScreen(
                    convention: convention,
                    onReloadHome: ref
                        .read(entryControllerProvider.notifier)
                        .refreshHome,
                  ),
                ),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppPaths.suits,
                builder: (context, state) => _SuitsRoute(
                  builder: (convention) => SuitListScreen(
                    convention: convention,
                    onOpenSuit: (id) => context.push(AppPaths.suit(id)),
                    onRegister: () => context.push(AppPaths.registerSuit),
                  ),
                ),
                routes: [
                  GoRoute(
                    path: "new",
                    builder: (context, state) => _SuitsRoute(
                      builder: (convention) => SuitRegisterScreen(
                        onCreated: (fursuit) {
                          ref
                              .read(
                                suitsControllerProvider(convention.id).notifier,
                              )
                              .created(fursuit);
                          context.pushReplacement(AppPaths.suit(fursuit.id));
                        },
                        onOutcomeUnknown: () => ref
                            .read(
                              suitsControllerProvider(convention.id).notifier,
                            )
                            .createOutcomeUnknown(),
                      ),
                    ),
                  ),
                  GoRoute(
                    path: ":id",
                    builder: (context, state) {
                      final id = int.parse(state.pathParameters["id"]!);
                      return _SuitsRoute(
                        builder: (convention) => SuitDetailScreen(
                          convention: convention,
                          fursuitId: id,
                          onOpenTag: () => context.push(AppPaths.suitTag(id)),
                        ),
                      );
                    },
                    routes: [
                      // The large QR code needs the whole screen (#511 G15).
                      GoRoute(
                        path: "tag",
                        parentNavigatorKey: rootKey,
                        builder: (context, state) => _SuitsRoute(
                          builder: (convention) => TagScreen(
                            convention: convention,
                            fursuitId: int.parse(state.pathParameters["id"]!),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
      // The scanner needs the whole screen (#511 G15).
      GoRoute(
        path: AppPaths.scan,
        builder: (context, state) => _SuitsRoute(
          builder: (convention) => ScanScreen(
            convention: convention,
            onOpenRequests: () => context.go(AppPaths.requests),
            onOpenCatches: () => context.go(AppPaths.catches),
            onReloadHome: ref
                .read(entryControllerProvider.notifier)
                .refreshHome,
            onClose: () => context.go(AppPaths.home),
          ),
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

/// The bar of the convention home stage and the shown section.
class _HomeShell extends ConsumerWidget {
  const new({required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: shell,
      bottomNavigationBar: NavigationBar(
        key: const Key("home-bar"),
        selectedIndex: shell.currentIndex,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (index) {
          shell.goBranch(index, initialLocation: index == shell.currentIndex);
          _readOnOpen(ref, _sectionPaths[index]);
        },
        destinations: const [
          NavigationDestination(
            key: Key("nav-home"),
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: CatchStrings.navHome,
          ),
          NavigationDestination(
            key: Key("nav-catches"),
            icon: Icon(Icons.collections_bookmark_outlined),
            selectedIcon: Icon(Icons.collections_bookmark),
            label: CatchStrings.navCatches,
          ),
          NavigationDestination(
            key: Key("nav-requests"),
            icon: Icon(Icons.outbox_outlined),
            selectedIcon: Icon(Icons.outbox),
            label: CatchStrings.navRequests,
          ),
          NavigationDestination(
            key: Key("nav-suits"),
            icon: Icon(Icons.pets_outlined),
            selectedIcon: Icon(Icons.pets),
            label: CatchStrings.navSuits,
          ),
        ],
      ),
    );
  }

  /// A section that stays alive in the bar reads again each time it opens
  /// (#511 AC25, AC29). A new section reads when its screen starts.
  void _readOnOpen(WidgetRef ref, String path) {
    final stage = ref.read(entryControllerProvider);
    if (stage is! EntryConventionHome) {
      return;
    }
    final conventionId = stage.enrollment.convention.id;
    switch (path) {
      case AppPaths.catches:
        final provider = catchesControllerProvider(conventionId);
        if (ref.read(provider.exists)) {
          unawaited(ref.read(provider.notifier).read());
        }
      case AppPaths.requests:
        if (ref.read(requestsControllerProvider.exists)) {
          unawaited(ref.read(requestsControllerProvider.notifier).read());
        }
    }
  }
}

/// Gives a suit screen the selected convention of the home stage.
class _SuitsRoute extends ConsumerWidget {
  const new({required this.builder});

  final Widget Function(Convention convention) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stage = ref.watch(entryControllerProvider);
    if (stage is! EntryConventionHome) {
      return const EntryLoadingScreen(label: EntryStrings.loadingAccount);
    }
    return builder(stage.enrollment.convention);
  }
}

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
      onScan: () => context.push(AppPaths.scan),
      onManagePasskeys: entry.openPasskeys,
      onSignOut: entry.signOut,
      onOpenAuthProof: onOpenAuthProof,
    );
  }
}
