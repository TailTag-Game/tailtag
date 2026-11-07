import "dart:async";

import "package:flutter/services.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_clerk/tailtag_clerk.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/clerk_auth_session.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";

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

  group("passkeys", () {
    // Wire maps as both plugins send them: epoch milliseconds, no extra
    // fields.
    final firstCreated = DateTime(2026, 11, 1, 9).millisecondsSinceEpoch;
    final firstUsed = DateTime(2026, 11, 5, 18).millisecondsSinceEpoch;
    final secondCreated = DateTime(2026, 11, 6, 7).millisecondsSinceEpoch;
    const allowingFacts = {
      "otherVerifiedPasskey": false,
      "verifiedEmail": true,
      "emailCodeEnabled": true,
      "verifiedGoogle": false,
      "googleEnabled": true,
      "verifiedApple": false,
      "appleEnabled": false,
    };

    test("every passkey call crosses the channel with its documented name "
        "and arguments", () async {
      final (session, native) = await _startSession(
        onCall: (call) => switch (call.method) {
          "passkeyAvailability" => true,
          "signInWithPasskey" || "createPasskey" => "completed",
          "listPasskeys" => [
            {
              "id": "pk_placeholder_1",
              "name": "iCloud Keychain",
              "createdAt": firstCreated,
              "lastUsedAt": firstUsed,
            },
            {
              "id": "pk_placeholder_2",
              "name": "Google Password Manager",
              "createdAt": secondCreated,
            },
          ],
          "passkeyRemovalFacts" => allowingFacts,
          _ => null,
        },
      );

      expect(
        await session.passkeyAvailability(),
        PasskeyAvailability.available,
      );
      expect(await session.signInWithPasskey(), isA<AuthAttemptCompleted>());
      expect(await session.createPasskey(), isA<AuthAttemptCompleted>());
      expect(await session.listPasskeys(), [
        PasskeyInfo(
          id: "pk_placeholder_1",
          name: "iCloud Keychain",
          createdAt: DateTime.fromMillisecondsSinceEpoch(firstCreated),
          lastUsedAt: DateTime.fromMillisecondsSinceEpoch(firstUsed),
        ),
        PasskeyInfo(
          id: "pk_placeholder_2",
          name: "Google Password Manager",
          createdAt: DateTime.fromMillisecondsSinceEpoch(secondCreated),
        ),
      ]);
      await session.removePasskey("pk_placeholder_1");

      final passkeyCalls = native.calls.skip(1).toList();
      expect(passkeyCalls.map((call) => call.method), [
        "passkeyAvailability",
        "signInWithPasskey",
        "createPasskey",
        "listPasskeys",
        "passkeyRemovalFacts",
        "removePasskey",
      ]);
      expect(passkeyCalls.take(4).map((call) => call.arguments), [
        anyOf(isNull, isEmpty),
        anyOf(isNull, isEmpty),
        anyOf(isNull, isEmpty),
        anyOf(isNull, isEmpty),
      ]);
      expect(passkeyCalls.skip(4).map((call) => call.arguments), [
        {"passkeyId": "pk_placeholder_1"},
        {"passkeyId": "pk_placeholder_1"},
      ]);
      // A passkey sign-in or creation never sets signed in itself.
      expect(session.state, isNot(isA<AuthSignedIn>()));
    });

    test("availability is unavailable unless native says true, and never "
        "throws", () async {
      for (final answer in <Object? Function()>[
        () => false,
        () => null,
        () => "true",
        () => throw _nativeError("unexpected"),
      ]) {
        final (session, _) = await _startSession(
          onCall: (call) => call.method == "configure" ? null : answer(),
        );
        expect(
          await session.passkeyAvailability(),
          PasskeyAvailability.unavailable,
        );
      }
    });

    test("sign-in and creation map only completed and cancelled", () async {
      final operations = <Future<AuthAttemptResult> Function(ClerkAuthSession)>[
        (session) => session.signInWithPasskey(),
        (session) => session.createPasskey(),
      ];
      for (final operation in operations) {
        final (cancelled, _) = await _startSession(
          onCall: (call) => "cancelled",
        );
        expect(await operation(cancelled), isA<AuthAttemptCancelled>());
        for (final unknown in ["needsEmailCode", "partial", null]) {
          final (session, _) = await _startSession(
            onCall: (call) => call.method == "configure" ? null : unknown,
          );
          await expectLater(
            operation(session),
            throwsA(isA<AuthUnexpectedFailure>()),
          );
        }
      }
    });

    // Each operation keeps only the categories that the #476 contract
    // allows. Every other wire code becomes unexpected.
    const wireCodes = {
      "connectivity": TypeMatcher<AuthConnectivityFailure>(),
      "invalidCode": TypeMatcher<AuthInvalidCodeFailure>(),
      "sessionEnded": TypeMatcher<AuthSessionEndedFailure>(),
      "unsupported": TypeMatcher<AuthUnsupportedFailure>(),
      "rateLimited": TypeMatcher<AuthRateLimitedFailure>(),
      "accountExists": TypeMatcher<AuthAccountExistsFailure>(),
      "accountNotFound": TypeMatcher<AuthAccountNotFoundFailure>(),
      "providerUnavailable": TypeMatcher<AuthProviderUnavailableFailure>(),
      "passkeyUnavailable": TypeMatcher<AuthPasskeyUnavailableFailure>(),
      "reverificationRequired":
          TypeMatcher<AuthReverificationRequiredFailure>(),
      "unexpected": TypeMatcher<AuthUnexpectedFailure>(),
    };
    final operations =
        <
          ({
            String label,
            Future<Object?> Function(ClerkAuthSession) call,
            Set<String> allowed,
          })
        >[
          (
            label: "signInWithPasskey",
            call: (session) => session.signInWithPasskey(),
            allowed: {"passkeyUnavailable", "accountNotFound", "connectivity"},
          ),
          (
            label: "createPasskey",
            call: (session) => session.createPasskey(),
            allowed: {
              "passkeyUnavailable",
              "reverificationRequired",
              "sessionEnded",
              "connectivity",
            },
          ),
          (
            label: "listPasskeys",
            call: (session) => session.listPasskeys(),
            allowed: {"sessionEnded", "connectivity"},
          ),
          (
            label: "removePasskey",
            call: (session) => session.removePasskey("pk_placeholder_1"),
            allowed: {"reverificationRequired", "sessionEnded", "connectivity"},
          ),
        ];
    for (final operation in operations) {
      test("${operation.label}() keeps only its allowed categories, without "
          "native text", () async {
        for (final MapEntry(key: code, value: matcher) in wireCodes.entries) {
          final (session, _) = await _startSession(
            onCall: (call) =>
                call.method == "configure" ? null : throw _nativeError(code),
          );
          Object? thrown;
          try {
            await operation.call(session);
          } on Object catch (error) {
            thrown = error;
          }
          expect(
            thrown,
            operation.allowed.contains(code)
                ? matcher
                : isA<AuthUnexpectedFailure>(),
            reason: code,
          );
          expect(thrown.toString(), isNot(contains("leak-")));
        }
      });
    }

    test(
      "a malformed passkey item fails the whole list as unexpected",
      () async {
        final malformed = <Object?>[
          "pk_placeholder_1",
          {"name": "No id", "createdAt": firstCreated},
          {"id": "", "name": "Empty id", "createdAt": firstCreated},
          {"id": "pk_placeholder_1", "createdAt": firstCreated},
          {"id": "pk_placeholder_1", "name": "Text date", "createdAt": "today"},
          {
            "id": "pk_placeholder_1",
            "name": "Text last use",
            "createdAt": firstCreated,
            "lastUsedAt": "today",
          },
        ];
        for (final item in malformed) {
          final (session, _) = await _startSession(
            onCall: (call) => call.method == "listPasskeys" ? [item] : null,
          );
          await expectLater(
            session.listPasskeys(),
            throwsA(isA<AuthUnexpectedFailure>()),
            reason: "$item",
          );
        }
        final (session, _) = await _startSession(onCall: (call) => null);
        await expectLater(
          session.listPasskeys(),
          throwsA(isA<AuthUnexpectedFailure>()),
        );
      },
    );

    // The last-method rule. Each row names the one fact pair that keeps
    // another way to sign in, or none.
    final ruleCases = <({String label, Map<String, bool> facts, bool allowed})>[
      (label: "nothing remains", facts: {}, allowed: false),
      (
        label: "another verified passkey",
        facts: {"otherVerifiedPasskey": true},
        allowed: true,
      ),
      (
        label: "verified email with email codes on",
        facts: {"verifiedEmail": true, "emailCodeEnabled": true},
        allowed: true,
      ),
      (
        label: "verified email with email codes off",
        facts: {"verifiedEmail": true},
        allowed: false,
      ),
      (
        label: "email codes on without a verified email",
        facts: {"emailCodeEnabled": true},
        allowed: false,
      ),
      (
        label: "verified Google with Google on",
        facts: {"verifiedGoogle": true, "googleEnabled": true},
        allowed: true,
      ),
      (
        label: "verified Google with Google off",
        facts: {"verifiedGoogle": true},
        allowed: false,
      ),
      (
        label: "verified Apple with Apple on",
        facts: {"verifiedApple": true, "appleEnabled": true},
        allowed: true,
      ),
      (
        label: "verified Apple with Apple off",
        facts: {"verifiedApple": true},
        allowed: false,
      ),
    ];
    for (final c in ruleCases) {
      test(
        "removal with ${c.label} is ${c.allowed ? "allowed" : "refused"}",
        () async {
          final facts = {
            for (final key in allowingFacts.keys) key: c.facts[key] ?? false,
          };
          final (session, native) = await _startSession(
            onCall: (call) =>
                call.method == "passkeyRemovalFacts" ? facts : null,
          );
          if (c.allowed) {
            await session.removePasskey("pk_placeholder_1");
            expect(native.callsTo("removePasskey"), hasLength(1));
          } else {
            await expectLater(
              session.removePasskey("pk_placeholder_1"),
              throwsA(isA<AuthLastMethodRequiredFailure>()),
            );
            expect(native.callsTo("removePasskey"), isEmpty);
          }
        },
      );
    }

    test("missing or malformed removal facts delete nothing", () async {
      for (final facts in <Object?>[
        null,
        {...allowingFacts}..remove("verifiedGoogle"),
        {...allowingFacts, "verifiedEmail": "true"},
      ]) {
        final (session, native) = await _startSession(
          onCall: (call) => call.method == "passkeyRemovalFacts" ? facts : null,
        );
        await expectLater(
          session.removePasskey("pk_placeholder_1"),
          throwsA(isA<AuthUnexpectedFailure>()),
        );
        expect(native.callsTo("removePasskey"), isEmpty);
      }
    });

    test("passkey calls share the one-attempt rule", () async {
      final pending = Completer<Object?>();
      final (session, native) = await _startSession(
        onCall: (call) =>
            call.method == "createPasskey" ? pending.future : null,
      );

      final creation = session.createPasskey();
      await pumpEventQueue();
      await expectLater(
        session.listPasskeys(),
        throwsA(isA<AuthUnexpectedFailure>()),
      );
      await expectLater(
        session.removePasskey("pk_placeholder_1"),
        throwsA(isA<AuthUnexpectedFailure>()),
      );
      pending.complete("cancelled");
      expect(await creation, isA<AuthAttemptCancelled>());

      expect(native.callsTo("listPasskeys"), isEmpty);
      expect(native.callsTo("passkeyRemovalFacts"), isEmpty);
    });
  });
}
