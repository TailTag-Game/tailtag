import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";

/// Where the player stands on the way into TailTag.
///
/// The entry coordinator derives the stage from the auth state, the identity
/// bootstrap, and sign-out. Each stage has its own route. Only [EntryReady]
/// shows protected content.
sealed class EntryStage {
  /// Creates a stage.
  const new();
}

/// The native SDK is loading the session.
final class EntryRestoring extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntryRestoring";
}

/// The native SDK failed to start or lost its state stream.
final class EntryAuthRecovery extends EntryStage {
  /// Creates the stage for [failure].
  const new(this.failure) : super();

  /// Why authentication failed.
  final AuthFailure failure;

  /// Whether a retry can help. An unsupported platform cannot recover.
  bool get canRetry => failure is! AuthUnsupportedFailure;

  @override
  String toString() => "EntryAuthRecovery(${failure.name})";
}

/// No session is active.
final class EntrySignedOut extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntrySignedOut";
}

/// Sign-out is running. Protected content is already hidden.
final class EntrySigningOut extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntrySigningOut";
}

/// Sign-out failed, and the native session is still active.
final class EntrySignOutFailed extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntrySignOutFailed";
}

/// A session is active, and the app is reading the TailTag identity and
/// profile.
final class EntryIdentityLoading extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntryIdentityLoading";
}

/// The identity read or the profile read failed.
final class EntryIdentityFailed extends EntryStage {
  /// Creates the stage. A null [failure] means that the API refused the
  /// token while the native session stayed active.
  const new({this.failure}) : super();

  /// The read failure, or null for an API-access failure.
  final ApiFailure? failure;

  /// Whether the API refused the token of an active native session.
  bool get isApiAccess => failure == null;

  @override
  String toString() =>
      "EntryIdentityFailed(${failure?.category.name ?? "apiAccess"})";
}

/// The signed-in player is on the passkey screen.
///
/// It needs an active session but no profile and no convention. It shows no
/// protected product content, and no bootstrap result changes it. Only
/// closing it, sign-out, or a session end leaves it.
final class EntryPasskeys extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntryPasskeys";
}

/// The profile of an enabled player is incomplete.
final class EntryOnboarding extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntryOnboarding";
}

/// The server reports that the profile is disabled. It offers no onboarding
/// or participation write.
final class EntryAccountUnavailable extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntryAccountUnavailable";
}

/// The profile of an enabled player is complete. The neutral landing shows
/// until conventions (#482) add their stages.
final class EntryReady extends EntryStage {
  /// Creates the stage.
  const new() : super();

  @override
  String toString() => "EntryReady";
}
