import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_repository.dart";

import "../../support/api_test_support.dart";

FursuitRepository _answering(int status, String body) => FursuitRepository(
  createTestTransport(FakeHttpClient.respond(status, body: body)),
);

const _row =
    '"fursuit_id": 5, "convention_id": 10, "is_active": true, '
    '"is_eligible": true, "activated_at": "2026-11-14T10:00:00Z", '
    '"deactivated_at": null';

void main() {
  test("an activation row maps its newest session and end reason", () async {
    final rows = await _answering(
      200,
      '[{$_row, "catch_session": {"fursuit_id": 5, "convention_id": 10, '
      '"is_active": false, "started_at": "2026-11-14T08:00:00Z", '
      '"expires_at": "2026-11-14T20:00:00Z", '
      '"ended_at": "2026-11-14T09:00:00Z", "end_reason": "operator"}}]',
    ).listActivations(10);

    final session = rows.single.session!;
    expect(session.endReason, CatchSessionEndReason.operator);
    expect(session.endedAt, DateTime.utc(2026, 11, 14, 9));
    expect(rows.single.isCatchable, isFalse);
  });

  group("a response with a missing field fails closed", () {
    final cases = <({String label, Future<Object?> Function() read})>[
      (
        // An older server without the field cannot say "never started".
        label: "an activation row with no catch_session key",
        read: () => _answering(200, "[{$_row}]").listActivations(10),
      ),
      (
        label: "a suit with no photo URL",
        read: () => _answering(
          200,
          '[{"id": 5, "name": "Alpha", "is_enabled": true, '
          '"catch_approval_mode": "manual"}]',
        ).listFursuits(),
      ),
    ];
    for (final c in cases) {
      test(c.label, () async {
        await expectLater(c.read(), throwsA(isA<ApiUnexpectedFailure>()));
      });
    }
  });
}
