import "dart:async";

import "package:flutter/services.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_clerk/tailtag_clerk.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/clerk_auth_session.dart";

const _methodChannel = MethodChannel(clerkMethodChannelName);
const _stateChannel = EventChannel(clerkStateChannelName);

/// Text a failure must never carry: native `message` and `details` can hold
/// an email address or a Clerk identifier.
const _leakedMessage = "leak-message user@example.invalid";
const _leakedDetails = "leak-details sess_placeholder";

/// The native side of both channels, as the Swift and Kotlin code behaves.
final class _NativeBridge {
  /// Answers a call; throwing makes the channel return that error.
  Object? Function(MethodCall call)? onCall;

  final List<MethodCall> calls = [];
  MockStreamHandlerEventSink? _sink;

  List<MethodCall> callsTo(String method) =>
      calls.where((call) => call.method == method).toList();

  void install() {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          ..setMockMethodCallHandler(_methodChannel, (call) async {
            calls.add(call);
            return onCall?.call(call);
          })
          ..setMockStreamHandler(
            _stateChannel,
            MockStreamHandler.inline(
              onListen: (arguments, sink) => _sink = sink,
              onCancel: (arguments) => _sink = null,
            ),
          );
    addTearDown(() {
      messenger
        ..setMockMethodCallHandler(_methodChannel, null)
        ..setMockStreamHandler(_stateChannel, null);
    });
  }

  /// Sends a state event and lets it reach Dart.
  Future<void> emit(Object? event) async {
    _sink!.success(event);
    await pumpEventQueue();
  }

  /// Sends a state error, as a native SDK that could not start does.
  Future<void> emitError(String code) async {
    _sink!.error(code: code, message: _leakedMessage, details: _leakedDetails);
    await pumpEventQueue();
  }
}

/// A started session over the mocked channels.
Future<(ClerkAuthSession, _NativeBridge)> _startSession({
  Object? Function(MethodCall call)? onCall,
}) async {
  final native = _NativeBridge()
    ..onCall = onCall
    ..install();
  final session = ClerkAuthSession(
    bridge: TailTagClerk(),
    publishableKey: "pk_test_placeholder",
  );
  addTearDown(session.dispose);
  await session.start();
  await pumpEventQueue();
  return (session, native);
}

PlatformException _nativeError(String code) => PlatformException(
  code: code,
  message: _leakedMessage,
  details: _leakedDetails,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test("every call crosses the channel with its documented name and "
      "arguments", () async {
    final (session, native) = await _startSession(
      onCall: (call) => switch (call.method) {
        "getToken" => "placeholder-token",
        "verifyEmailCode" => "completed",
        _ => null,
      },
    );

    await session.startEmailSignUp("player+clerk_test@example.invalid");
    await session.startEmailSignIn("player+clerk_test@example.invalid");
    await session.resendEmailCode();
    final result = await session.verifyEmailCode("000000");
    await native.emit("signedIn");
    final token = await session.token();
    await session.signOut();

    expect(result, isA<AuthAttemptCompleted>());
    expect(token, "placeholder-token");
    expect(native.calls.map((call) => call.method), [
      "configure",
      "startEmailSignUp",
      "startEmailSignIn",
      "resendEmailCode",
      "verifyEmailCode",
      "getToken",
      "signOut",
    ]);
    expect(native.calls.take(6).map((call) => call.arguments), [
      {"publishableKey": "pk_test_placeholder"},
      {"emailAddress": "player+clerk_test@example.invalid"},
      {"emailAddress": "player+clerk_test@example.invalid"},
      anyOf(isNull, isEmpty),
      {"code": "000000"},
      {"skipCache": false},
    ]);
    expect(native.calls.last.arguments, anyOf(isNull, isEmpty));
  });

  group("verifyEmailCode()", () {
    test("never sets signed in itself: only native state events do", () async {
      final (session, native) = await _startSession(
        onCall: (call) => "completed",
      );
      await native.emit("signedOut");

      await session.verifyEmailCode("000000");
      expect(session.state, isA<AuthSignedOut>());

      await native.emit("signedIn");
      expect(session.state, isA<AuthSignedIn>());
    });

    test("an unknown native result is an unexpected failure", () async {
      final (session, _) = await _startSession(onCall: (call) => "partial");

      expect(
        () => session.verifyEmailCode("000000"),
        throwsA(isA<AuthUnexpectedFailure>()),
      );
    });
  });

  // Google and Apple share one provider contract. Apple also allows
  // unsupported, because Android has no Apple flow.
  final providers =
      <
        ({
          String method,
          Future<AuthAttemptResult> Function(ClerkAuthSession) call,
          List<String> results,
          List<({String label, Exception error, Matcher failure})> failures,
        })
      >[
        (
          method: "continueWithGoogle",
          call: (session) => session.continueWithGoogle(),
          results: ["completed", "cancelled", "needsEmailCode"],
          failures: [
            (
              label: "providerUnavailable",
              error: _nativeError("providerUnavailable"),
              failure: isA<AuthProviderUnavailableFailure>(),
            ),
            (
              label: "connectivity",
              error: _nativeError("connectivity"),
              failure: isA<AuthConnectivityFailure>(),
            ),
            (
              label: "rateLimited",
              error: _nativeError("rateLimited"),
              failure: isA<AuthUnexpectedFailure>(),
            ),
            (
              label: "unsupported",
              error: _nativeError("unsupported"),
              failure: isA<AuthUnexpectedFailure>(),
            ),
          ],
        ),
        (
          method: "continueWithApple",
          call: (session) => session.continueWithApple(),
          // Both providers share the result mapping, so Apple checks its
          // routing once and then only its own failure rules.
          results: ["completed"],
          failures: [
            (
              label: "providerUnavailable",
              error: _nativeError("providerUnavailable"),
              failure: isA<AuthProviderUnavailableFailure>(),
            ),
            (
              label: "rateLimited",
              error: _nativeError("rateLimited"),
              failure: isA<AuthUnexpectedFailure>(),
            ),
            (
              label: "unsupported",
              error: _nativeError("unsupported"),
              failure: isA<AuthUnsupportedFailure>(),
            ),
            // Android has no Apple method, so its plugin answers "not
            // implemented".
            (
              label: "no Apple method on the platform",
              error: MissingPluginException(_leakedMessage),
              failure: isA<AuthUnsupportedFailure>(),
            ),
          ],
        ),
      ];

  for (final provider in providers) {
    group("${provider.method}()", () {
      const matchers = <String, Matcher>{
        "completed": TypeMatcher<AuthAttemptCompleted>(),
        "cancelled": TypeMatcher<AuthAttemptCancelled>(),
        "needsEmailCode": TypeMatcher<AuthAttemptNeedsEmailCode>(),
      };
      for (final name in provider.results) {
        test("maps $name and never sets signed in itself", () async {
          final (session, native) = await _startSession(onCall: (call) => name);
          await native.emit("signedOut");

          expect(await provider.call(session), matchers[name]);
          expect(session.state, isA<AuthSignedOut>());
          final call = native.callsTo(provider.method).single;
          expect(call.arguments, anyOf(isNull, isEmpty));
        });
      }

      // Each provider keeps only the categories that its contract allows.
      // Every other category becomes unexpected.
      for (final f in provider.failures) {
        test("${f.label} keeps only an allowed category", () async {
          final (session, _) = await _startSession(
            onCall: (call) => throw f.error,
          );
          Object? thrown;
          try {
            await provider.call(session);
          } on Object catch (error) {
            thrown = error;
          }
          expect(thrown, f.failure);
          expect(thrown.toString(), isNot(contains("leak-")));
        });
      }
    });
  }

  test(
    "an unknown or missing native provider result is an unexpected failure",
    () async {
      for (final unknown in ["partial", null]) {
        final (session, _) = await _startSession(onCall: (call) => unknown);
        await expectLater(
          session.continueWithGoogle(),
          throwsA(isA<AuthUnexpectedFailure>()),
        );
      }
    },
  );

  test("a second access call while one is pending throws unexpected and "
      "never reaches native", () async {
    final pending = Completer<Object?>();
    final (session, native) = await _startSession(
      onCall: (call) => call.method == "configure" ? null : pending.future,
    );

    final first = session.startEmailSignIn("player@example.invalid");
    await pumpEventQueue();
    await expectLater(
      session.verifyEmailCode("000000"),
      throwsA(isA<AuthUnexpectedFailure>()),
    );
    pending.complete(null);
    await first;

    expect(native.callsTo("startEmailSignIn"), hasLength(1));
    expect(native.callsTo("verifyEmailCode"), isEmpty);
    await session.resendEmailCode();
    expect(native.callsTo("resendEmailCode"), hasLength(1));
  });

  group("bridge errors become AuthFailure without native text", () {
    // The wire codes of the Test Surface Contract, an unknown code, and a
    // missing plugin, each with the failure the app must see.
    final cases = <({String label, Exception error, Matcher failure})>[
      (
        label: "connectivity",
        error: _nativeError("connectivity"),
        failure: isA<AuthConnectivityFailure>(),
      ),
      (
        label: "invalidCode",
        error: _nativeError("invalidCode"),
        failure: isA<AuthInvalidCodeFailure>(),
      ),
      (
        label: "sessionEnded",
        error: _nativeError("sessionEnded"),
        failure: isA<AuthSessionEndedFailure>(),
      ),
      (
        label: "unsupported",
        error: _nativeError("unsupported"),
        failure: isA<AuthUnsupportedFailure>(),
      ),
      (
        label: "rateLimited",
        error: _nativeError("rateLimited"),
        failure: isA<AuthRateLimitedFailure>(),
      ),
      (
        label: "accountExists",
        error: _nativeError("accountExists"),
        failure: isA<AuthAccountExistsFailure>(),
      ),
      (
        label: "accountNotFound",
        error: _nativeError("accountNotFound"),
        failure: isA<AuthAccountNotFoundFailure>(),
      ),
      (
        label: "unexpected",
        error: _nativeError("unexpected"),
        failure: isA<AuthUnexpectedFailure>(),
      ),
      (
        label: "an unknown code",
        error: _nativeError("brand_new_native_code"),
        failure: isA<AuthUnexpectedFailure>(),
      ),
      (
        label: "no plugin on the platform",
        error: MissingPluginException(_leakedMessage),
        failure: isA<AuthUnsupportedFailure>(),
      ),
    ];

    for (final c in cases) {
      test(c.label, () async {
        final (session, native) = await _startSession();
        native.onCall = (call) => throw c.error;

        final failures = <Object>[];
        for (final action in <Future<Object?> Function()>[
          () => session.startEmailSignIn("player@example.invalid"),
          () => session.startEmailSignUp("player@example.invalid"),
          session.resendEmailCode,
          () => session.verifyEmailCode("000000"),
        ]) {
          try {
            await action();
          } on Object catch (error) {
            failures.add(error);
          }
        }

        expect(failures, hasLength(4), reason: "every call must throw");
        expect(session.state, isNot(isA<AuthSignedIn>()));
        for (final failure in failures) {
          expect(failure, c.failure);
          expect(failure.toString(), isNot(contains("leak-")));
          expect(failure.toString(), isNot(contains("example.invalid")));
        }
      });
    }
  });

  test(
    "a failing configure leaves a failed state and does not throw",
    () async {
      final cases = <({Exception error, Matcher failure})>[
        (
          error: _nativeError("connectivity"),
          failure: isA<AuthConnectivityFailure>(),
        ),
        (
          error: MissingPluginException(),
          failure: isA<AuthUnsupportedFailure>(),
        ),
      ];

      for (final c in cases) {
        final native = _NativeBridge()
          ..onCall = ((call) => throw c.error)
          ..install();
        final session = ClerkAuthSession(
          bridge: TailTagClerk(),
          publishableKey: "pk_test_placeholder",
        );
        addTearDown(session.dispose);

        await session.start();

        expect(
          session.state,
          isA<AuthFailed>().having((s) => s.failure, "failure", c.failure),
        );
        expect(native.callsTo("configure"), hasLength(1));
      }
    },
  );

  test("native state events drive AuthState and unknown values are "
      "ignored", () async {
    final (session, native) = await _startSession();
    final seen = <AuthState>[];
    final subscription = session.states.listen(seen.add);
    addTearDown(subscription.cancel);

    expect(session.state, isA<AuthRestoring>());

    await native.emit("signedOut");
    expect(session.state, isA<AuthSignedOut>());
    await native.emit("signedIn");
    expect(session.state, isA<AuthSignedIn>());
    await native.emit("loading");
    expect(session.state, isA<AuthRestoring>());
    await native.emit("signedIn");
    await native.emit("not-a-state");
    expect(session.state, isA<AuthSignedIn>());

    expect(seen.map((state) => state.runtimeType).toList(), [
      AuthSignedOut,
      AuthSignedIn,
      AuthRestoring,
      AuthSignedIn,
    ]);
  });

  group("token()", () {
    test("is null without asking native unless signed in", () async {
      final (session, native) = await _startSession(
        onCall: (call) => "placeholder-token",
      );

      expect(await session.token(), isNull, reason: "restoring");
      await native.emit("signedOut");
      expect(await session.token(), isNull, reason: "signed out");

      expect(native.callsTo("getToken"), isEmpty);
    });

    test("is null, not an error, when native fails", () async {
      final (session, native) = await _startSession();
      await native.emit("signedIn");
      native.onCall = (call) => throw _nativeError("connectivity");

      expect(await session.token(), isNull);
      expect(native.callsTo("getToken"), hasLength(1));
    });
  });

  group("recheckSession() asks native once, bypassing the cache", () {
    final cases =
        <({String label, Object? Function(MethodCall) native, Matcher state})>[
          (
            label: "no active session ends the session",
            native: (call) => null,
            state: isA<AuthSignedOut>(),
          ),
          (
            label: "a sessionEnded error ends the session",
            native: (call) => throw _nativeError("sessionEnded"),
            state: isA<AuthSignedOut>(),
          ),
          (
            label: "a returned token keeps the session",
            native: (call) => "placeholder-token",
            state: isA<AuthSignedIn>(),
          ),
          (
            label: "any other error keeps the session",
            native: (call) => throw _nativeError("connectivity"),
            state: isA<AuthSignedIn>(),
          ),
        ];

    for (final c in cases) {
      test(c.label, () async {
        final (session, native) = await _startSession();
        await native.emit("signedIn");
        native.onCall = c.native;

        await session.recheckSession();

        expect(session.state, c.state);
        expect(native.callsTo("getToken").map((call) => call.arguments), [
          {"skipCache": true},
        ]);
      });
    }
  });

  group("startup failure and reloadSession()", () {
    test("a native state error is a failed state, and later events "
        "recover", () async {
      final (session, native) = await _startSession();

      await native.emitError("connectivity");
      expect(
        session.state,
        isA<AuthFailed>().having(
          (s) => s.failure,
          "failure",
          isA<AuthConnectivityFailure>(),
        ),
      );
      expect(session.state.toString(), isNot(contains("leak-")));

      await native.emit("signedIn");
      expect(session.state, isA<AuthSignedIn>());
    });

    test("reload asks native to reload and never reports signed out "
        "itself", () async {
      final (session, native) = await _startSession();
      await native.emitError("unexpected");
      final seen = <AuthState>[];
      final subscription = session.states.listen(seen.add);
      addTearDown(subscription.cancel);

      await session.reloadSession();
      await pumpEventQueue();

      expect(native.callsTo("reload"), hasLength(1));
      expect(native.callsTo("signOut"), isEmpty);
      expect(seen, [isA<AuthRestoring>()]);

      await native.emit("signedIn");
      expect(session.state, isA<AuthSignedIn>());
    });

    test("a failed reload is a failed state again and does not "
        "throw", () async {
      final (session, native) = await _startSession();
      await native.emitError("unexpected");
      native.onCall = (call) => throw _nativeError("connectivity");

      await session.reloadSession();

      expect(
        session.state,
        isA<AuthFailed>().having(
          (s) => s.failure,
          "failure",
          isA<AuthConnectivityFailure>(),
        ),
      );
    });

    test("after a failed configure, reload configures again", () async {
      final native = _NativeBridge()
        ..onCall = ((call) => throw _nativeError("connectivity"))
        ..install();
      final session = ClerkAuthSession(
        bridge: TailTagClerk(),
        publishableKey: "pk_test_placeholder",
      );
      addTearDown(session.dispose);
      await session.start();
      expect(session.state, isA<AuthFailed>());

      native.onCall = (call) => null;
      await session.reloadSession();
      await native.emit("signedOut");

      expect(native.callsTo("configure"), hasLength(2));
      expect(native.callsTo("reload"), isEmpty);
      expect(session.state, isA<AuthSignedOut>());
    });
  });
}
