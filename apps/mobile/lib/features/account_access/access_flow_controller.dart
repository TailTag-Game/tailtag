import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/features/account_access/email_address.dart";

/// Which email choice the player made.
enum AccessMode {
  /// Sign in to an existing account.
  signIn,

  /// Create a new account.
  createAccount,
}

/// The access request that is running.
enum AccessAction {
  /// Sending the first code.
  send,

  /// Sending another code.
  resend,

  /// Verifying a code.
  verify,

  /// Signing in through Google.
  google,

  /// Signing in through Apple, on iOS only.
  apple,

  /// Signing in with a passkey.
  passkey;

  /// Whether this is a provider action, which the account screen runs.
  bool get isProvider => this == google || this == apple || this == passkey;
}

/// The account access flow. It lives in memory only.
@immutable
final class AccessFlowState {
  /// Creates a state.
  const new({
    this.mode = AccessMode.signIn,
    this.email = "",
    this.codeSent = false,
    this.viaProvider = false,
    this.pending,
    this.failure,
    this.failedAction,
    this.codeResent = false,
  });

  /// The player's choice.
  final AccessMode mode;

  /// The trimmed email address of the current attempt.
  final String email;

  /// Whether Clerk sent a code for the current attempt.
  final bool codeSent;

  /// Whether the code belongs to a provider attempt, such as Apple. The
  /// app then knows no email address, so [email] is empty.
  final bool viaProvider;

  /// The running request, or null.
  final AccessAction? pending;

  /// The failure of the last request, or null.
  final AuthFailure? failure;

  /// The request that produced [failure], when the account screen shows it.
  /// Only provider actions set it.
  final AccessAction? failedAction;

  /// Whether the last request sent another code.
  final bool codeResent;

  /// Whether a request is running.
  bool get isPending => pending != null;
}

/// Runs the account access flow over the auth session.
///
/// It sends one request at a time, and only on an explicit call. It never
/// retries. It watches [playerScopeProvider], so a new session or a
/// sign-out clears it. A result that arrives after its scope closed is
/// dropped.
final class AccessFlowController extends Notifier<AccessFlowState> {
  @override
  AccessFlowState build() {
    ref.watch(playerScopeProvider);
    return const AccessFlowState();
  }

  /// Starts a flow for [mode] with an empty email.
  void begin(AccessMode mode) {
    if (!state.isPending) {
      state = AccessFlowState(mode: mode);
    }
  }

  /// Ends the current attempt and forgets the email.
  void reset() {
    if (!state.isPending) {
      state = AccessFlowState(mode: state.mode);
    }
  }

  /// Switches between sign-in and account creation. The email stays, and
  /// nothing is sent.
  void switchMode() {
    if (state.isPending) {
      return;
    }
    state = AccessFlowState(
      mode: state.mode == AccessMode.signIn
          ? AccessMode.createAccount
          : AccessMode.signIn,
      email: state.email,
    );
  }

  /// Returns to email entry. The email stays.
  void changeEmail() {
    if (!state.isPending) {
      state = AccessFlowState(mode: state.mode, email: state.email);
    }
  }

  /// Sends the first code to [emailAddress].
  ///
  /// Returns true when Clerk sent the code.
  Future<bool> sendCode(String emailAddress) async {
    final email = emailAddress.trim();
    if (state.isPending || !isPlausibleEmailAddress(email)) {
      return false;
    }
    final mode = state.mode;
    final scope = ref.read(playerScopeProvider);
    state = AccessFlowState(
      mode: mode,
      email: email,
      pending: AccessAction.send,
    );
    final session = ref.read(authSessionProvider);
    try {
      await switch (mode) {
        AccessMode.signIn => session.startEmailSignIn(email),
        AccessMode.createAccount => session.startEmailSignUp(email),
      };
    } on AuthFailure catch (failure) {
      if (_isCurrent(scope)) {
        state = AccessFlowState(mode: mode, email: email, failure: failure);
      }
      return false;
    }
    if (!_isCurrent(scope)) {
      return false;
    }
    state = AccessFlowState(mode: mode, email: email, codeSent: true);
    return true;
  }

  /// Sends another code for the current attempt.
  Future<void> resend() async {
    if (state.isPending || !state.codeSent) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final mode = state.mode;
    final email = state.email;
    final viaProvider = state.viaProvider;
    state = AccessFlowState(
      mode: mode,
      email: email,
      codeSent: true,
      viaProvider: viaProvider,
      pending: AccessAction.resend,
    );
    try {
      await ref.read(authSessionProvider).resendEmailCode();
    } on AuthFailure catch (failure) {
      if (_isCurrent(scope)) {
        state = AccessFlowState(
          mode: mode,
          email: email,
          codeSent: true,
          viaProvider: viaProvider,
          failure: failure,
        );
      }
      return;
    }
    if (_isCurrent(scope)) {
      state = AccessFlowState(
        mode: mode,
        email: email,
        codeSent: true,
        viaProvider: viaProvider,
        codeResent: true,
      );
    }
  }

  /// Verifies a six-digit [code] for the current attempt.
  ///
  /// On success, the controls stay disabled until the new session clears
  /// this flow.
  Future<void> verify(String code) async {
    if (state.isPending || !state.codeSent || code.length != 6) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final mode = state.mode;
    final email = state.email;
    final viaProvider = state.viaProvider;
    final pending = AccessFlowState(
      mode: mode,
      email: email,
      codeSent: true,
      viaProvider: viaProvider,
      pending: AccessAction.verify,
    );
    state = pending;
    AuthFailure? failure;
    try {
      final result = await ref.read(authSessionProvider).verifyEmailCode(code);
      switch (result) {
        case AuthAttemptCompleted():
          // The native state events start the session and clear this flow.
          return;
        case AuthAttemptCancelled():
          failure = null;
        case AuthAttemptNeedsEmailCode():
          failure = const AuthUnexpectedFailure();
      }
    } on AuthFailure catch (error) {
      failure = error;
    }
    if (_isCurrent(scope)) {
      state = AccessFlowState(
        mode: mode,
        email: email,
        codeSent: true,
        viaProvider: viaProvider,
        failure: failure,
      );
    }
  }

  /// Signs in or creates an account through Google.
  ///
  /// Returns true when Clerk sent an email code that the player must enter.
  /// A cancellation returns to the account choices with no failure. On
  /// success, the controls stay disabled until the new session clears this
  /// flow.
  Future<bool> continueWithGoogle() => _continueWithProvider(
    AccessAction.google,
    (session) => session.continueWithGoogle(),
  );

  /// Signs in or creates an account through Apple, with the same rules as
  /// [continueWithGoogle].
  Future<bool> continueWithApple() => _continueWithProvider(
    AccessAction.apple,
    (session) => session.continueWithApple(),
  );

  /// Signs in with a passkey, with the same rules as [continueWithGoogle].
  /// A passkey never needs an email code.
  Future<bool> continueWithPasskey() => _continueWithProvider(
    AccessAction.passkey,
    (session) => session.signInWithPasskey(),
  );

  Future<bool> _continueWithProvider(
    AccessAction action,
    Future<AuthAttemptResult> Function(AuthSession session) call,
  ) async {
    if (state.isPending) {
      return false;
    }
    final scope = ref.read(playerScopeProvider);
    final mode = state.mode;
    state = AccessFlowState(mode: mode, pending: action);
    AuthFailure? failure;
    try {
      final result = await call(ref.read(authSessionProvider));
      switch (result) {
        case AuthAttemptCompleted():
          // The native state events start the session and clear this flow.
          return false;
        case AuthAttemptCancelled():
          failure = null;
        case AuthAttemptNeedsEmailCode():
          if (!_isCurrent(scope)) {
            return false;
          }
          state = AccessFlowState(
            mode: mode,
            codeSent: true,
            viaProvider: true,
          );
          return true;
      }
    } on AuthFailure catch (error) {
      failure = error;
    }
    if (_isCurrent(scope)) {
      state = AccessFlowState(
        mode: mode,
        failure: failure,
        failedAction: failure == null ? null : action,
      );
    }
    return false;
  }

  bool _isCurrent(PlayerScope scope) => ref.mounted && scope.isActive;
}

/// The email access flow.
final accessFlowProvider =
    NotifierProvider<AccessFlowController, AccessFlowState>(
      AccessFlowController.new,
    );
