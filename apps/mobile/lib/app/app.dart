import 'package:flutter/material.dart';
import 'package:tailtag_mobile/app/router.dart';

class TailTagApp extends StatelessWidget {
  const TailTagApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(title: 'TailTag', routerConfig: appRouter);
  }
}
