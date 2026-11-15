import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/features/fursuits/suit_status.dart";

final _start = DateTime.utc(2026, 11, 14, 8);
final _expires = DateTime.utc(2026, 11, 14, 20);
final _ended = DateTime.utc(2026, 11, 14, 9);

FursuitActivation _activation({
  bool active = true,
  bool eligible = true,
  CatchSessionEndReason? reason,
  DateTime? ended,
}) => FursuitActivation(
  fursuitId: 5,
  isActive: active,
  isEligible: eligible,
  session: CatchSession(
    isActive: false,
    startedAt: _start,
    expiresAt: _expires,
    endedAt: ended,
    endReason: reason,
  ),
);

void main() {
  final cases =
      <({String label, FursuitActivation activation, SessionNote? note})>[
        (
          label: "a timeout that no operation finalized uses expires_at",
          activation: _activation(reason: CatchSessionEndReason.expired),
          note: (kind: SessionNoteKind.timedOut, at: _expires),
        ),
        (
          label: "a staff end uses ended_at",
          activation: _activation(
            reason: CatchSessionEndReason.operator,
            ended: _ended,
          ),
          note: (kind: SessionNoteKind.staffEnded, at: _ended),
        ),
        (
          label: "an owner end shows no note",
          activation: _activation(
            reason: CatchSessionEndReason.owner,
            ended: _ended,
          ),
          note: null,
        ),
        (
          label: "a suit that does not participate shows no note",
          activation: _activation(
            active: false,
            reason: CatchSessionEndReason.expired,
          ),
          note: null,
        ),
        (
          label: "a suit the server does not allow shows no note",
          activation: _activation(
            eligible: false,
            reason: CatchSessionEndReason.operator,
            ended: _ended,
          ),
          note: null,
        ),
      ];
  for (final c in cases) {
    test("session note: ${c.label}", () {
      expect(sessionNoteFor(c.activation), c.note);
    });
  }
}
