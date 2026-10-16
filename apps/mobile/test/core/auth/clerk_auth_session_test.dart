import "package:flutter/services.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_clerk/tailtag_clerk.dart";
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
      onCall: (call) => call.method == "getToken" ? "placeholder-token" : null,
    );
    await native.emit("signedIn");

    await session.startEmailCode("player+clerk_test@example.invalid");
    await session.verifyEmailCode("000000");
    final token = await session.token();
    await session.signOut();

    expect(token, "placeholder-token");
    expect(native.calls.map((call) => call.method), [
      "configure",
      "startEmailCode",
      "verifyCode",
      "getToken",
      "signOut",
    ]);
    expect(native.calls.take(4).map((call) => call.arguments), [
      {"publishableKey": "pk_test_placeholder"},
      {"emailAddress": "player+clerk_test@example.invalid"},
      {"code": "000000"},
      {"skipCache": false},
    ]);
    expect(native.calls.last.arguments, anyOf(isNull, isEmpty));
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
        for (final action in <Future<void> Function()>[
          () => session.startEmailCode("player@example.invalid"),
          () => session.verifyEmailCode("000000"),
        ]) {
          try {
            await action();
          } on Object catch (error) {
            failures.add(error);
          }
        }

        expect(failures, hasLength(2), reason: "both calls must throw");
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
}
