import "dart:io";

import "package:flutter_test/flutter_test.dart";
import "package:http/http.dart" as http;
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/session/current_user_repository.dart";

import "../../support/api_test_support.dart";

const _shortDeadline = Duration(milliseconds: 50);

CurrentUserRepository _repository(
  FakeHttpClient client, {
  Duration jsonTimeout = apiJsonTimeout,
}) {
  return CurrentUserRepository(
    createTestTransport(client, jsonTimeout: jsonTimeout),
  );
}

void main() {
  group("CurrentUserRepository.fetch", () {
    test(
      "200 returns the TailTag-owned CurrentUser over the real wire",
      () async {
        final client = FakeHttpClient.respond(200, body: '{"id": 42}');

        final user = await _repository(client).fetch();

        expect(user.id, 42);
        // Wire-level proof that the whole chain is assembled: generated path
        // (with its trailing slash), bearer seam, and no redirect following.
        expect(client.requests, hasLength(1));
        final request = client.requests.single;
        expect(request.method, "GET");
        expect(request.url, Uri.parse("https://dev.tailtag.app/api/me/"));
        expect(request.authorization, "Bearer test-token");
        expect(request.followRedirects, isFalse);
      },
    );

    test("401 is unauthenticated", () async {
      final client = FakeHttpClient.respond(
        401,
        body: '{"detail": "Authentication credentials were not provided."}',
      );

      await expectLater(
        _repository(client).fetch(),
        throwsA(
          isA<ApiUnauthenticatedFailure>().having(
            (failure) => failure.statusCode,
            "statusCode",
            401,
          ),
        ),
      );
    });

    group("malformed 200 is unexpected", () {
      const cases = <({String label, String body, String contentType})>[
        (
          label: "not JSON",
          body: "<html>oops</html>",
          contentType: "text/html",
        ),
        (
          label: "JSON syntax error",
          body: '{"id": ',
          contentType: "application/json",
        ),
        (
          label: "wrong shape",
          body: '{"id": "forty-two"}',
          contentType: "application/json",
        ),
      ];

      for (final c in cases) {
        test(c.label, () async {
          final client = FakeHttpClient.respond(
            200,
            body: c.body,
            contentType: c.contentType,
          );

          await expectLater(
            _repository(client).fetch(),
            throwsA(isA<ApiUnexpectedFailure>()),
          );
        });
      }
    });

    group("connectivity", () {
      final cases = <String, Object>{
        "ClientException": http.ClientException("connection reset"),
        "SocketException": const SocketException("no route to host"),
      };

      for (final MapEntry(key: label, value: error) in cases.entries) {
        test(label, () async {
          final client = FakeHttpClient.fail(error);

          await expectLater(
            _repository(client).fetch(),
            throwsA(isA<ApiConnectivityFailure>()),
          );
        });
      }
    });

    test(
      "a stalled response past the deadline aborts the request as timeout",
      () async {
        final client = FakeHttpClient.hang();

        await expectLater(
          _repository(client, jsonTimeout: _shortDeadline).fetch(),
          throwsA(isA<ApiTimeoutFailure>()),
        );

        expect(client.aborted, isTrue);
      },
      timeout: const Timeout(Duration(seconds: 5)),
    );

    test(
      "cancel aborts the in-flight request and resolves as cancelled",
      () async {
        final client = FakeHttpClient.hang();
        final cancellation = ApiCancellation();

        final outcome = expectLater(
          _repository(client).fetch(cancellation: cancellation),
          throwsA(isA<ApiCancelledFailure>()),
        );
        await client.requestSent;
        cancellation.cancel();
        await outcome;

        expect(client.aborted, isTrue);
      },
      timeout: const Timeout(Duration(seconds: 5)),
    );
  });
}
