import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
import "package:go_router/go_router.dart";
import "package:tailtag_mobile/app/debug/auth_proof_screen.dart";

/// The debug-only route of the Clerk sign-in proof screen.
const String authProofPath = "/debug/auth";

/// Router configuration for the TailTag application.
final GoRouter appRouter = GoRouter(
  routes: <RouteBase>[
    GoRoute(
      path: "/",
      builder: (context, state) {
        return Scaffold(
          body: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text("TailTag"),
                if (kDebugMode)
                  TextButton(
                    onPressed: () => context.push(authProofPath),
                    child: const Text("Auth proof (debug)"),
                  ),
              ],
            ),
          ),
        );
      },
    ),
    if (kDebugMode)
      GoRoute(
        path: authProofPath,
        builder: (context, state) => const AuthProofScreen(),
      ),
  ],
);
