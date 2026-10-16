import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/app/debug/azp_probe.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";

/// The debug-only screen that proves Clerk sign-in against the TailTag API.
///
/// It shows the auth state, the category and HTTP status of `GET /api/me/`,
/// whether a TailTag id came back, and whether the session token has an
/// `azp` claim. It never shows or logs a token, the id value, an email
/// address, or a Clerk identifier.
class AuthProofScreen extends ConsumerStatefulWidget {
  /// Creates the screen.
  const new({super.key});

  @override
  ConsumerState<AuthProofScreen> createState() => _AuthProofScreenState();
}

class _AuthProofScreenState extends ConsumerState<AuthProofScreen> {
  final _email = TextEditingController();
  final _code = TextEditingController();
  String _result = "No call yet";
  String _azp = "azp claim present: not checked yet";

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _run(String action, Future<void> Function() call) async {
    try {
      await call();
    } on AuthFailure catch (failure) {
      if (mounted) {
        setState(() => _result = "$action failed: ${failure.name}");
      }
    }
  }

  Future<void> _callMe() async {
    final session = ref.read(authSessionProvider);
    String result;
    ApiFailure? failure;
    try {
      final user = await ref.read(currentUserRepositoryProvider).fetch();
      result = "HTTP 200, TailTag id present: ${user.id > 0 ? "yes" : "no"}";
    } on ApiFailure catch (error) {
      failure = error;
      final status = error.statusCode;
      result = status == null
          ? error.category.name
          : "${error.category.name} (HTTP $status)";
    }
    final token = await session.token();
    final hasAzp = token != null && tokenHasAzpClaim(token);
    if (failure is ApiUnauthenticatedFailure && session.state is AuthSignedIn) {
      await session.recheckSession();
    }
    if (mounted) {
      setState(() {
        _result = result;
        _azp = "azp claim present: ${hasAzp ? "yes" : "no"}";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(authSessionProvider);
    final state = ref.watch(authStateProvider).value ?? session.state;
    return Scaffold(
      appBar: AppBar(title: const Text("Auth proof (debug)")),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: 12,
            children: [
              Text(_describe(state), key: const Key("auth-proof-state")),
              TextField(
                key: const Key("auth-proof-email"),
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                decoration: const InputDecoration(labelText: "Email"),
              ),
              FilledButton(
                key: const Key("auth-proof-send-code"),
                onPressed: () => _run(
                  "Send code",
                  () => session.startEmailCode(_email.text.trim()),
                ),
                child: const Text("Send code"),
              ),
              TextField(
                key: const Key("auth-proof-code"),
                controller: _code,
                keyboardType: TextInputType.number,
                autocorrect: false,
                decoration: const InputDecoration(labelText: "Code"),
              ),
              FilledButton(
                key: const Key("auth-proof-verify"),
                onPressed: () => _run(
                  "Verify code",
                  () => session.verifyEmailCode(_code.text.trim()),
                ),
                child: const Text("Verify code"),
              ),
              FilledButton(
                key: const Key("auth-proof-call-me"),
                onPressed: _callMe,
                child: const Text("Call /api/me/"),
              ),
              Text(_result, key: const Key("auth-proof-result")),
              Text(_azp, key: const Key("auth-proof-azp")),
              if (state is AuthSignedIn)
                OutlinedButton(
                  key: const Key("auth-proof-sign-out"),
                  onPressed: () => _run("Sign out", session.signOut),
                  child: const Text("Sign out"),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

String _describe(AuthState state) => switch (state) {
  AuthRestoring() => "Auth state: restoring",
  AuthSignedOut() => "Auth state: signedOut",
  AuthSignedIn() => "Auth state: signedIn",
  AuthFailed(:final failure) => "Auth state: failed (${failure.name})",
};
