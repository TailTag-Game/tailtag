import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/conventions/convention_repository.dart";

import "../../support/api_test_support.dart";

String _convention({
  int id = 10,
  String name = "Test Con",
  String status = "active",
}) =>
    '{"id": $id, "name": "$name", "status": "$status", '
    '"start_date": "2026-11-08", "end_date": "2026-11-10"}';

ConventionRepository _repository(FakeHttpClient client) =>
    ConventionRepository(createTestTransport(client));

ConventionRepository _answering(int status, String body) =>
    _repository(FakeHttpClient.respond(status, body: body));

void main() {
  group("reads map the server response", () {
    test("conventions keep the server order and calendar dates", () async {
      final conventions = await _answering(
        200,
        "[${_convention(id: 2, name: "B Con")}, "
        "${_convention(id: 1, name: "A Con")}]",
      ).listConventions();

      expect(conventions.map((c) => c.id), [2, 1]);
      expect(conventions.first.name, "B Con");
      // A calendar date stays the same day in every timezone.
      expect(conventions.first.startDate, DateTime(2026, 11, 8));
      expect(conventions.first.endDate, DateTime(2026, 11, 10));
    });
  });

  group("a response with a missing field fails closed", () {
    final cases = <({String label, Future<Object?> Function() read})>[
      (
        label: "a convention with no status",
        read: () => _answering(
          200,
          '[{"id": 1, "name": "A", "start_date": "2026-11-08", '
          '"end_date": "2026-11-10"}]',
        ).listConventions(),
      ),
      (
        label: "an enrollment with no is_active",
        read: () => _answering(
          200,
          '[{"id": 7, "convention": ${_convention()}, '
          '"created_at": "2026-10-01T12:00:00Z"}]',
        ).listEnrollments(),
      ),
      (
        label: "a selection write with a null enrollment",
        read: () => _answering(200, '{"enrollment": null}').select(10),
      ),
      (
        label: "a selection read with no enrollment key",
        read: () => _answering(200, "{}").readSelection(),
      ),
    ];
    for (final c in cases) {
      test(c.label, () async {
        await expectLater(c.read(), throwsA(isA<ApiUnexpectedFailure>()));
      });
    }
  });
}
