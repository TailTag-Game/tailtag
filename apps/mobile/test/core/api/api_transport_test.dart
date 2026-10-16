import "package:flutter_test/flutter_test.dart";
import "package:tailtag_api/tailtag_api.dart";
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_diagnostic.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tonik_util/tonik_util.dart";

import "../../support/api_test_support.dart";

const _secret = "SECRET-DETAIL";
const _avatarBytes = [0x89, 0x50, 0x4e, 0x47];
const _shortDeadline = Duration(milliseconds: 50);
const _neverDeadline = Duration(minutes: 10);

/// `GET /api/me/`: a JSON operation that documents only 200 and 401.
Future<Object> _me(ApiTransport transport, {ApiCancellation? cancellation}) {
  return transport.execute(
    operationId: "meRetrieve",
    cancellation: cancellation,
    call: (token) => transport.me.meRetrieve(cancellation: token),
  );
}

/// `PUT /api/profile/avatar/`: the multipart operation. It documents 400,
/// 401, and 403 without bodies.
Future<Object> _avatar(ApiTransport transport) {
  return transport.execute(
    operationId: "profileAvatarUpdate",
    multipart: true,
    call: (token) => transport.profile.profileAvatarUpdate(
      body: const AvatarPut(
        avatar: TonikFileBytes(_avatarBytes, fileName: "me.png"),
      ),
      cancellation: token,
    ),
  );
}

typedef _StatusCase = ({
  String label,
  Future<Object> Function(ApiTransport) operation,
  int status,
  String body,
  Matcher failure,
  String? code,
  Map<String, List<String>>? fieldErrors,
});

void main() {
  group("status to ApiFailure", () {
    final cases = <_StatusCase>[
      (
        label: "400 documented without a body model keeps code and fieldErrors",
        operation: _avatar,
        status: 400,
        body:
            '{"code": "validation_error", "detail": "$_secret", '
            '"avatar": ["too large", "wrong type"], "display_name": ["blank"]}',
        failure: isA<ApiValidationFailure>(),
        code: "validation_error",
        fieldErrors: {
          "avatar": ["too large", "wrong type"],
          "display_name": ["blank"],
        },
      ),
      (
        label: "401",
        operation: _me,
        status: 401,
        body: '{"detail": "$_secret"}',
        failure: isA<ApiUnauthenticatedFailure>(),
        code: null,
        fieldErrors: null,
      ),
      (
        label: "403 undocumented for the operation keeps code",
        operation: _me,
        status: 403,
        body: '{"code": "profile_disabled", "detail": "$_secret"}',
        failure: isA<ApiPermissionFailure>(),
        code: "profile_disabled",
        fieldErrors: null,
      ),
      (
        label: "404",
        operation: _me,
        status: 404,
        body: '{"code": "not_found", "detail": "$_secret"}',
        failure: isA<ApiNotFoundFailure>(),
        code: "not_found",
        fieldErrors: null,
      ),
      (
        label: "409 keeps code",
        operation: _me,
        status: 409,
        body: '{"code": "already_caught", "detail": "$_secret"}',
        failure: isA<ApiConflictFailure>(),
        code: "already_caught",
        fieldErrors: null,
      ),
      (
        label: "500 with a non-JSON body is still a server failure",
        operation: _me,
        status: 500,
        body: "<html>$_secret</html>",
        failure: isA<ApiServerFailure>(),
        code: null,
        fieldErrors: null,
      ),
      (
        label: "undocumented status",
        operation: _me,
        status: 418,
        body: '{"detail": "$_secret"}',
        failure: isA<ApiUnexpectedFailure>(),
        code: null,
        fieldErrors: null,
      ),
    ];

    for (final c in cases) {
      test(c.label, () async {
        final inner = FakeHttpClient.respond(c.status, body: c.body);

        final Object thrown;
        try {
          await c.operation(createTestTransport(inner));
          fail("expected an ApiFailure");
        } on ApiFailure catch (failure) {
          thrown = failure;
        }

        expect(thrown, c.failure);
        final failure = thrown as ApiFailure;
        expect(failure.statusCode, c.status);
        expect(failure.code, c.code);
        if (c.fieldErrors != null) {
          expect((failure as ApiValidationFailure).fieldErrors, c.fieldErrors);
        }
        expect(failure.toString(), isNot(contains(_secret)));
      });
    }

    test(
      "302 is unexpected and the redirect target is never requested",
      () async {
        final inner = FakeHttpClient.respond(
          302,
          headers: {"location": "https://elsewhere.example/steal"},
        );

        await expectLater(
          _me(createTestTransport(inner)),
          throwsA(
            isA<ApiUnexpectedFailure>().having(
              (failure) => failure.statusCode,
              "statusCode",
              302,
            ),
          ),
        );

        expect(inner.requests, hasLength(1));
        expect(inner.requests.single.followRedirects, isFalse);
      },
    );
  });

  test("multipart sends multipart/form-data with a boundary and the field "
      "name", () async {
    final inner = FakeHttpClient.respond(
      200,
      body:
          '{"handle": null, "display_name": null, "avatar_url": null, '
          '"onboarding_complete": false, "is_enabled": true}',
    );

    final result = await _avatar(createTestTransport(inner));

    expect(result, isA<ProfileAvatarUpdateResponse200>());
    final request = inner.requests.single;
    expect(request.method, "PUT");
    expect(
      request.url,
      Uri.parse("https://dev.tailtag.app/api/profile/avatar/"),
    );
    final contentType = request.headers["content-type"]!;
    expect(contentType, startsWith("multipart/form-data; boundary="));
    final boundary = contentType.split("boundary=").last;
    expect(boundary, isNotEmpty);
    expect(request.bodyText, contains("--$boundary"));
    expect(request.bodyText, contains('name="avatar"'));
    expect(request.bodyText, contains('filename="me.png"'));
  });

  group("deadline", () {
    // Each row makes the *other* deadline unreachable, so only the right
    // selection can produce a timeout.
    final cases =
        <
          ({
            String label,
            Future<Object> Function(ApiTransport) operation,
            Duration json,
            Duration multipart,
          })
        >[
          (
            label: "JSON uses the JSON deadline",
            operation: _me,
            json: _shortDeadline,
            multipart: _neverDeadline,
          ),
          (
            label: "multipart uses the multipart deadline",
            operation: _avatar,
            json: _neverDeadline,
            multipart: _shortDeadline,
          ),
        ];

    for (final c in cases) {
      test(c.label, () async {
        final inner = FakeHttpClient.hang();
        final transport = createTestTransport(
          inner,
          jsonTimeout: c.json,
          multipartTimeout: c.multipart,
        );

        await expectLater(
          c.operation(transport),
          throwsA(isA<ApiTimeoutFailure>()),
        );

        expect(inner.aborted, isTrue);
      }, timeout: const Timeout(Duration(seconds: 5)));
    }
  });

  // The deadline and cancel() must not depend on something below the
  // transport already listening for the abort.
  group("a stall that never sees the abort", () {
    final stalls =
        <({String label, ApiTransport Function(Duration json) transport})>[
          (
            label: "token provider never returns",
            transport: (json) => createTestTransport(
              FakeHttpClient.respond(200, body: '{"id": 1}'),
              jsonTimeout: json,
              tokenProvider: HangingApiTokenProvider(),
            ),
          ),
          (
            label: "inner client not yet listening for the abort",
            transport: (json) => createTestTransport(
              FakeHttpClient.hang(listenForAbort: false),
              jsonTimeout: json,
            ),
          ),
        ];

    for (final stall in stalls) {
      test("${stall.label}: the deadline resolves as timeout", () async {
        await expectLater(
          _me(stall.transport(_shortDeadline)),
          throwsA(isA<ApiTimeoutFailure>()),
        );
      }, timeout: const Timeout(Duration(seconds: 3)));

      test("${stall.label}: cancel resolves as cancelled", () async {
        final cancellation = ApiCancellation();

        final outcome = expectLater(
          _me(stall.transport(_neverDeadline), cancellation: cancellation),
          throwsA(isA<ApiCancelledFailure>()),
        );
        await Future<void>.delayed(const Duration(milliseconds: 20));
        cancellation.cancel();
        await outcome;
      }, timeout: const Timeout(Duration(seconds: 3)));
    }
  });

  group("diagnostics", () {
    final cases =
        <
          ({
            String label,
            FakeHttpClient Function() client,
            int? status,
            bool failed,
          })
        >[
          (
            label: "success",
            client: () => FakeHttpClient.respond(200, body: '{"id": 1}'),
            status: 200,
            failed: false,
          ),
          (
            label: "server failure",
            client: () =>
                FakeHttpClient.respond(401, body: '{"detail": "$_secret"}'),
            status: 401,
            failed: true,
          ),
        ];

    for (final c in cases) {
      test("${c.label} emits one allow-listed diagnostic", () async {
        final diagnostics = <ApiDiagnostic>[];
        final transport = createTestTransport(
          c.client(),
          token: "SECRET-TOKEN",
          diagnostics: diagnostics.add,
        );

        try {
          await _me(transport);
        } on ApiFailure {
          // The thrown failure is covered by the status table.
        }

        expect(diagnostics, hasLength(1));
        final diagnostic = diagnostics.single;
        expect(diagnostic.method, "GET");
        expect(diagnostic.operationId, "meRetrieve");
        expect(diagnostic.statusCode, c.status);
        expect(diagnostic.duration, greaterThanOrEqualTo(Duration.zero));
        expect(diagnostic.failure != null, c.failed);
        expect(diagnostic.toString(), isNot(contains("SECRET")));
      });
    }
  });
}
