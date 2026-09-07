import "package:flutter/material.dart";
import "package:go_router/go_router.dart";
import "package:tailtag_mobile/features/account_creation.dart";
import "package:tailtag_mobile/features/login.dart";
import "package:tailtag_mobile/features/onboarding.dart";

/// Router configuration for the TailTag application.
final GoRouter appRouter = GoRouter(
  routes: <RouteBase>[
    GoRoute(
      path: "/",
      builder: (context, state) {
        return const OnboardingScreen();
      },
    ),
    GoRoute(
      path: "/login",
      pageBuilder: (context, state) {
        return const MaterialPage(child: LoginScreen());
      }
    ),
    GoRoute(
      path: "/register",
      pageBuilder: (context, state) {
        return const MaterialPage(child: AccountCreationScreen());
      }
    )
  ],
);
