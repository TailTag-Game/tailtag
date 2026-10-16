/// A thin bridge to the native Clerk SDKs (email code sign-in and tokens).
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

  /// Anything else.
  unexpected,
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

  /// Starts an email code sign-in for [emailAddress].
  Future<void> startEmailCode(String emailAddress) =>
      _invoke<void>("startEmailCode", {"emailAddress": emailAddress});

  /// Completes the email code sign-in with [code].
  Future<void> verifyCode(String code) =>
      _invoke<void>("verifyCode", {"code": code});

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
  /// channel arrives as a [ClerkBridgeException].
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

  static ClerkBridgeException _exceptionFor(Object error) {
    final category = switch (error) {
      MissingPluginException() => ClerkBridgeErrorCategory.unsupported,
      PlatformException(:final code) => switch (code) {
        "connectivity" => ClerkBridgeErrorCategory.connectivity,
        "invalidCode" => ClerkBridgeErrorCategory.invalidCode,
        "sessionEnded" => ClerkBridgeErrorCategory.sessionEnded,
        "unsupported" => ClerkBridgeErrorCategory.unsupported,
        _ => ClerkBridgeErrorCategory.unexpected,
      },
      _ => ClerkBridgeErrorCategory.unexpected,
    };
    return ClerkBridgeException(category);
  }
}
