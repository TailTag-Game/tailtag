// Widget keys the proof screen must expose (the tests find widgets by them):
//
//   auth-proof-email      the email TextField
//   auth-proof-send-code  the button that calls startEmailCode
//   auth-proof-code       the code TextField
//   auth-proof-verify     the button that calls verifyEmailCode
//   auth-proof-call-me    the "Call /api/me/" button, in every auth state
//   auth-proof-sign-out   the sign-out button, whenever the state is signed in
//   auth-proof-state      Text of the auth state; contains "restoring",
//                         "signedOut", "signedIn", or "failed" (any case)
//   auth-proof-result     Text of the last call; contains the failure category
//                         name or the HTTP status, and for a 200 contains
//                         "id present: yes" (any case), never the id value
//   auth-proof-azp        Text containing "azp claim present: yes" or
//                         "azp claim present: no" (any case), set when the
//                         call finishes, from the token the session hands out
//
// The Text widgets are plain `Text(data)`, not rich text.
// The key widgets are the TextFields and buttons themselves, not wrappers.
// The call-me button always exists so that a signed-out call can be proved
// to send no header and map to unauthenticated.

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/debug/auth_proof_screen.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";
import "package:tailtag_mobile/core/session/current_user_repository.dart";

import "../support/api_test_support.dart";
import "../support/auth_test_support.dart";

const _userId = 987654;
const _email = "player+clerk_test@example.invalid";

Finder _key(String name) => find.byKey(Key("auth-proof-$name"));

String _text(WidgetTester tester, String name) =>
    tester.widget<Text>(_key(name)).data!.toLowerCase();

/// Pumps the screen over a real transport whose only substitute is the
/// network. The fake session is also the transport's token provider, the
/// way `authTokenOverride` wires the real one.
Future<void> _pump(
  WidgetTester tester,
  FakeAuthSession session,
  FakeHttpClient network,
) async {
  tester.view
    ..physicalSize = const Size(800, 2400)
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionProvider.overrideWithValue(session),
        currentUserRepositoryProvider.overrideWithValue(
          CurrentUserRepository(
            createTestTransport(network, tokenProvider: session),
          ),
        ),
      ],
      child: const MaterialApp(home: AuthProofScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _callMe(WidgetTester tester) async {
  await tester.tap(_key("call-me"));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets("sign-in reaches the session and the screen follows its state", (
    tester,
  ) async {
    final session = FakeAuthSession();
    await _pump(tester, session, FakeHttpClient.respond(200));
    expect(_text(tester, "state"), contains("signedout"));

    await tester.enterText(_key("email"), _email);
    await tester.tap(_key("send-code"));
    await tester.pumpAndSettle();
    await tester.enterText(_key("code"), "000000");
    await tester.tap(_key("verify"));
    await tester.pumpAndSettle();

    expect(session.startEmailCodeCalls, [_email]);
    expect(session.verifyCodeCalls, ["000000"]);
    expect(_text(tester, "state"), contains("signedin"));
  });

  for (final hasAzp in [true, false]) {
    testWidgets("a signed-in call sends one bearer header and reports azp "
        "${hasAzp ? "present" : "absent"} without showing secrets", (
      tester,
    ) async {
      final token = fakeJwt({
        "sub": "user_test",
        if (hasAzp) "azp": "https://example.invalid",
      });
      final network = FakeHttpClient.respond(200, body: '{"id": $_userId}');
      await _pump(
        tester,
        FakeAuthSession(initial: const AuthSignedIn(), tokenValue: token),
        network,
      );

      await _callMe(tester);

      expect(network.requests, hasLength(1));
      expect(network.requests.single.authorization, "Bearer $token");
      expect(_text(tester, "result"), contains("200"));
      expect(_text(tester, "result"), contains("id present: yes"));
      expect(
        _text(tester, "azp"),
        contains("azp claim present: ${hasAzp ? "yes" : "no"}"),
      );
      // Neither the id nor any token text may reach the screen.
      for (final secret in ["$_userId", token, "user_test"]) {
        expect(
          find.textContaining(secret, findRichText: true),
          findsNothing,
          reason: "screen must not render $secret",
        );
      }
    });
  }

  testWidgets(
    "a 401 while signed in rechecks the session once, without retrying",
    (tester) async {
      final network = FakeHttpClient.respond(401, body: '{"detail": "no"}');
      final session = FakeAuthSession(
        initial: const AuthSignedIn(),
        tokenValue: fakeJwt({"sub": "user_test"}),
      );
      await _pump(tester, session, network);

      await _callMe(tester);

      expect(network.requests, hasLength(1));
      expect(session.recheckCalls, 1);
      expect(_text(tester, "result"), contains("unauthenticated"));
      expect(_text(tester, "state"), contains("signedout"));
    },
  );

  testWidgets("a signed-out call sends no header and does not recheck", (
    tester,
  ) async {
    final network = FakeHttpClient.respond(401, body: '{"detail": "no"}');
    final session = FakeAuthSession(tokenValue: fakeJwt({"sub": "user_test"}));
    await _pump(tester, session, network);

    await _callMe(tester);

    expect(network.requests.single.authorization, isNull);
    expect(_text(tester, "result"), contains("unauthenticated"));
    expect(session.recheckCalls, 0);
  });

  testWidgets("sign-out reaches the session", (tester) async {
    final session = FakeAuthSession(initial: const AuthSignedIn());
    await _pump(tester, session, FakeHttpClient.respond(200));

    await tester.tap(_key("sign-out"));
    await tester.pumpAndSettle();

    expect(session.signOutCalls, 1);
    expect(_text(tester, "state"), contains("signedout"));
  });
}
