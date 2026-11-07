/// A thin bridge to the native Clerk SDKs (email code access, Google access,
/// Apple access on iOS, passkeys, session reload, and tokens).
///
/// The native side only forwards calls and maps errors. No token, email
/// address, or Clerk identifier crosses the bridge except the values the
/// caller asks for ([TailTagClerk.getToken] returns a token).
library;

import "dart:async";

import "package:flutter/services.dart";

/// The name of the method channel that carries the calls.
const String clerkMethodChannelName = "app.tailtag/clerk";

/// The name of the event channel that carries the state changes.
const String clerkStateChannelName = "app.tailtag/clerk/state";

/// What the native Clerk SDK reports about the session.
enum ClerkBridgeState {
  /// The native SDK has not finished loading.
  loading,

  /// The SDK has loaded and there is no active session.
  signedOut,

  /// The SDK has loaded and a session is active.
  signedIn,
}

/// Why a bridge call failed.
enum ClerkBridgeErrorCategory {
  /// The network could not be reached.
  connectivity,

  /// The verification code was wrong or has expired.
  invalidCode,

  /// There is no session, or the session was ended or revoked.
  sessionEnded,

  /// The native Clerk plugin is not available on this platform.
  unsupported,

  /// Clerk refused the request because of its rate limits.
  rateLimited,

  /// Email account creation found an existing account.
  accountExists,

  /// Email sign-in found no account.
  accountNotFound,

  /// The provider sign-in cannot run on this device.
  providerUnavailable,

  /// The device or OS cannot use a passkey now.
  passkeyUnavailable,

  /// Clerk needs a fresh sign-in before a passkey change.
  reverificationRequired,

  /// Anything else.
  unexpected,
}

/// One verified passkey, as the native side reports it.
///
/// [id] exists only to remove the passkey. Never log it.
final class ClerkPasskey {
  /// Creates the item.
  const new({
    required this.id,
    required this.name,
    required this.createdAt,
    this.lastUsedAt,
  });

  /// The opaque Clerk passkey identifier.
  final String id;

  /// The name that Clerk gave the passkey.
  final String name;

  /// When the passkey was added.
  final DateTime createdAt;

  /// When the passkey was last used, or null if never.
  final DateTime? lastUsedAt;

  @override
  String toString() => "ClerkPasskey($name)";
}

/// What remains for signing in if one passkey goes away. The native side
/// reads these values from fresh Clerk state. They carry no identifier.
final class ClerkRemovalFacts {
  /// Creates the facts.
  const new({
    required this.otherVerifiedPasskey,
    required this.verifiedEmail,
    required this.emailCodeEnabled,
    required this.verifiedGoogle,
    required this.googleEnabled,
    required this.verifiedApple,
    required this.appleEnabled,
  });

  /// Another verified passkey stays.
  final bool otherVerifiedPasskey;

  /// The account has a verified email address.
  final bool verifiedEmail;

  /// The instance allows email codes as a first factor.
  final bool emailCodeEnabled;

  /// The account has a verified Google external account.
  final bool verifiedGoogle;

  /// The instance allows Google sign-in.
  final bool googleEnabled;

  /// The account has a verified Apple external account. Always false on
  /// Android.
  final bool verifiedApple;

  /// The instance allows Apple sign-in. Always false on Android.
  final bool appleEnabled;
}

/// A failed bridge call.
///
/// It carries only a [category]. The native message and details are never
/// read, so no failure can leak a token, an email address, or Clerk text.
final class ClerkBridgeException implements Exception {
  /// Creates an exception for [category].
  const new(this.category);

  /// The loggable category of this failure.
  final ClerkBridgeErrorCategory category;

  @override
  String toString() => "ClerkBridgeException(${category.name})";
}

/// The Dart side of the native Clerk bridge.
final class TailTagClerk {
  /// Creates a bridge over the default channels.
  new();

  static const MethodChannel _methods = MethodChannel(clerkMethodChannelName);
  static const EventChannel _stateEvents = EventChannel(clerkStateChannelName);

  /// Starts the native Clerk SDK with the publishable key.
  Future<void> configure({required String publishableKey}) =>
      _invoke<void>("configure", {"publishableKey": publishableKey});

  /// Starts an email code sign-in for [emailAddress] and sends the code.
  ///
  /// The native side binds to this attempt. Any earlier binding ends.
  Future<void> startEmailSignIn(String emailAddress) =>
      _invoke<void>("startEmailSignIn", {"emailAddress": emailAddress});

  /// Starts an email account creation for [emailAddress] and sends the
  /// code.
  ///
  /// The native side binds to this attempt. Any earlier binding ends.
  Future<void> startEmailSignUp(String emailAddress) =>
      _invoke<void>("startEmailSignUp", {"emailAddress": emailAddress});

  /// Sends a new code for the bound attempt.
  Future<void> resendEmailCode() => _invoke<void>("resendEmailCode");

  /// Verifies [code] against the bound attempt.
  ///
  /// Returns the native result name, for example `completed`. The native
  /// side returns `completed` only when the session is active.
  Future<String?> verifyEmailCode(String code) =>
      _invoke<String>("verifyEmailCode", {"code": code});

  /// Signs in or creates an account through Google.
  ///
  /// Returns the native result name: `completed`, `cancelled`, or
  /// `needsEmailCode`. The native side returns `completed` only when the
  /// session is active. For `needsEmailCode`, the native side binds to the
  /// attempt and has already sent the code. Any earlier binding ends.
  Future<String?> continueWithGoogle() => _invoke<String>("continueWithGoogle");

  /// Signs in or creates an account through Apple, on iOS only.
  ///
  /// The results are the same as for [continueWithGoogle]. Android has no
  /// Apple method, so the call fails with
  /// [ClerkBridgeErrorCategory.unsupported] there.
  Future<String?> continueWithApple() => _invoke<String>("continueWithApple");

  /// Whether the device and the Clerk instance allow passkeys now.
  ///
  /// Anything other than a native `true` is false.
  Future<bool> passkeyAvailability() async =>
      await _invoke<bool>("passkeyAvailability") ?? false;

  /// Signs in with a passkey from the system sheet.
  ///
  /// Returns the native result name: `completed` or `cancelled`. The native
  /// side returns `completed` only when the session is active.
  Future<String?> signInWithPasskey() => _invoke<String>("signInWithPasskey");

  /// Adds a passkey for the signed-in user.
  ///
  /// Returns `completed` only after Clerk verified the passkey, or
  /// `cancelled` when the player dismissed the sheet.
  Future<String?> createPasskey() => _invoke<String>("createPasskey");

  /// The signed-in user's verified passkeys, after a fresh client read.
  ///
  /// A malformed item fails the whole call as
  /// [ClerkBridgeErrorCategory.unexpected].
  Future<List<ClerkPasskey>> listPasskeys() async {
    final raw = await _invoke<List<Object?>>("listPasskeys");
    if (raw == null) {
      throw const ClerkBridgeException(ClerkBridgeErrorCategory.unexpected);
    }
    return [for (final item in raw) _passkeyFrom(item)];
  }

  /// What remains for signing in if [passkeyId] goes away, after a fresh
  /// client read. An unknown [passkeyId] fails as
  /// [ClerkBridgeErrorCategory.unexpected].
  Future<ClerkRemovalFacts> passkeyRemovalFacts(String passkeyId) async {
    final raw = await _invoke<Map<Object?, Object?>>("passkeyRemovalFacts", {
      "passkeyId": passkeyId,
    });
    bool fact(String key) => switch (raw?[key]) {
      final bool value => value,
      _ => throw const ClerkBridgeException(
        ClerkBridgeErrorCategory.unexpected,
      ),
    };
    return ClerkRemovalFacts(
      otherVerifiedPasskey: fact("otherVerifiedPasskey"),
      verifiedEmail: fact("verifiedEmail"),
      emailCodeEnabled: fact("emailCodeEnabled"),
      verifiedGoogle: fact("verifiedGoogle"),
      googleEnabled: fact("googleEnabled"),
      verifiedApple: fact("verifiedApple"),
      appleEnabled: fact("appleEnabled"),
    );
  }

  /// Deletes the verified passkey [passkeyId] of the signed-in user. An
  /// unknown [passkeyId] fails as [ClerkBridgeErrorCategory.unexpected]
  /// and deletes nothing.
  Future<void> removePasskey(String passkeyId) =>
      _invoke<void>("removePasskey", {"passkeyId": passkeyId});

  /// Loads the native session state again without clearing storage.
  Future<void> reload() => _invoke<void>("reload");

  /// The current session token, or null when no session is active.
  ///
  /// With [skipCache] set, the SDK fetches a fresh token from the server.
  Future<String?> getToken({bool skipCache = false}) =>
      _invoke<String>("getToken", {"skipCache": skipCache});

  /// Ends the current session.
  Future<void> signOut() => _invoke<void>("signOut");

  /// The state changes, one event per change.
  ///
  /// Values other than the three known states are ignored. A failure on the
  /// channel, such as a native SDK that could not start, arrives as a
  /// [ClerkBridgeException].
  Stream<ClerkBridgeState> get states =>
      _stateEvents.receiveBroadcastStream().transform(
        StreamTransformer<Object?, ClerkBridgeState>.fromHandlers(
          handleData: (event, sink) {
            final state = switch (event) {
              "loading" => ClerkBridgeState.loading,
              "signedOut" => ClerkBridgeState.signedOut,
              "signedIn" => ClerkBridgeState.signedIn,
              _ => null,
            };
            if (state != null) sink.add(state);
          },
          handleError: (error, stackTrace, sink) =>
              sink.addError(_exceptionFor(error), stackTrace),
        ),
      );

  Future<T?> _invoke<T>(
    String method, [
    Map<String, Object?>? arguments,
  ]) async {
    try {
      return await _methods.invokeMethod<T>(method, arguments);
    } on Object catch (error, stackTrace) {
      Error.throwWithStackTrace(_exceptionFor(error), stackTrace);
    }
  }

  /// Reads one passkey map: `id` and `name` strings, `createdAt` and an
  /// optional `lastUsedAt` in epoch milliseconds.
  static ClerkPasskey _passkeyFrom(Object? item) {
    if (item case final Map<Object?, Object?> map) {
      final lastUsedAt = map["lastUsedAt"];
      if (map
          case {
            "id": final String id,
            "name": final String name,
            "createdAt": final int createdAt,
          }
          when id.isNotEmpty && (lastUsedAt == null || lastUsedAt is int)) {
        return ClerkPasskey(
          id: id,
          name: name,
          createdAt: DateTime.fromMillisecondsSinceEpoch(createdAt),
          lastUsedAt: lastUsedAt is int
              ? DateTime.fromMillisecondsSinceEpoch(lastUsedAt)
              : null,
        );
      }
    }
    throw const ClerkBridgeException(ClerkBridgeErrorCategory.unexpected);
  }

  static ClerkBridgeException _exceptionFor(Object error) {
    final category = switch (error) {
      MissingPluginException() => ClerkBridgeErrorCategory.unsupported,
      PlatformException(:final code) => switch (code) {
        "connectivity" => ClerkBridgeErrorCategory.connectivity,
        "invalidCode" => ClerkBridgeErrorCategory.invalidCode,
        "sessionEnded" => ClerkBridgeErrorCategory.sessionEnded,
        "unsupported" => ClerkBridgeErrorCategory.unsupported,
        "rateLimited" => ClerkBridgeErrorCategory.rateLimited,
        "accountExists" => ClerkBridgeErrorCategory.accountExists,
        "accountNotFound" => ClerkBridgeErrorCategory.accountNotFound,
        "providerUnavailable" => ClerkBridgeErrorCategory.providerUnavailable,
        "passkeyUnavailable" => ClerkBridgeErrorCategory.passkeyUnavailable,
        "reverificationRequired" =>
          ClerkBridgeErrorCategory.reverificationRequired,
        _ => ClerkBridgeErrorCategory.unexpected,
      },
      _ => ClerkBridgeErrorCategory.unexpected,
    };
    return ClerkBridgeException(category);
  }
}
