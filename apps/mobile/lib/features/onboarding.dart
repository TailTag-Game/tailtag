import "package:flutter/material.dart";
import "package:go_router/go_router.dart";

class OnboardingScreen extends StatelessWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: Center(
              child: Text(
                "Welcome to Tailtag.",
                style: Theme.of(context).textTheme.displayLarge,
              ),
          ),
        ),
      bottomNavigationBar: Material(
        color: Theme.of(context).colorScheme.surfaceContainerHigh,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                FilledButton(
                  onPressed: () => context.push("/register"),
                  child: const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text("Get Started")
                  )
                ),
                TextButton(
                  onPressed: () => context.push("/login"),
                  child: const Text("Already have an account? Sign in.")
                )
              ],
            ),
          )
        )
      ),
    );
  }
}

