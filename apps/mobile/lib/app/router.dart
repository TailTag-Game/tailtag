import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Router configuration for the TailTag application.
final GoRouter appRouter = GoRouter(
  routes: <RouteBase>[
    GoRoute(
      path: '/',
      builder: (context, state) {
        return const Scaffold(body: Center(child: Text('TailTag')));
      },
    ),
  ],
);
