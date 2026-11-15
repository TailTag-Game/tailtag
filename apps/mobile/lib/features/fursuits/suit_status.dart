import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";

/// The one badge of a suit at the selected convention.
enum SuitBadge {
  /// No activation, or the owner turned participation off.
  notParticipating,

  /// The owner chose to participate, and the server does not allow it now.
  cantParticipate,

  /// The suit participates and has no live session.
  participating,

  /// The suit has a live session.
  catchable,
}

/// The badge of a suit with [activation] at the selected convention.
SuitBadge badgeFor(FursuitActivation? activation) {
  if (activation == null || !activation.isActive) {
    return SuitBadge.notParticipating;
  }
  if (!activation.isEligible) {
    return SuitBadge.cantParticipate;
  }
  return activation.isCatchable ? SuitBadge.catchable : SuitBadge.participating;
}

/// Why a "turn on" control is disabled. The text of each reason lives in
/// the strings file.
enum DisabledReason {
  /// TailTag staff disabled the suit.
  suitDisabled,

  /// The convention is not open for play.
  conventionClosed,

  /// The suit does not participate.
  participateFirst,

  /// The server does not allow participation, for a reason the app does
  /// not know.
  cannotParticipate,
}

/// Why turning participation on is disabled, or null when it can turn on.
///
/// The app disables it only when a server value that it holds proves that
/// the server refuses. Turning it off is never disabled.
DisabledReason? participationBlock(
  Fursuit fursuit,
  Convention convention,
  FursuitActivation? activation,
) {
  if (activation?.isActive ?? false) {
    return null;
  }
  if (!fursuit.isEnabled) {
    return DisabledReason.suitDisabled;
  }
  if (!convention.isOpen) {
    return DisabledReason.conventionClosed;
  }
  return null;
}

/// Why starting a session is disabled, or null when it can start. A live
/// session can always stop.
DisabledReason? sessionBlock(
  Fursuit fursuit,
  Convention convention,
  FursuitActivation? activation,
) {
  if (activation?.isCatchable ?? false) {
    return null;
  }
  if (activation == null || !activation.isActive) {
    return DisabledReason.participateFirst;
  }
  if (activation.isEligible) {
    return null;
  }
  if (!fursuit.isEnabled) {
    return DisabledReason.suitDisabled;
  }
  if (!convention.isOpen) {
    return DisabledReason.conventionClosed;
  }
  return DisabledReason.cannotParticipate;
}

/// Why the newest session ended without the owner, for the session note.
enum SessionNoteKind {
  /// It reached its 12-hour lifetime.
  timedOut,

  /// TailTag staff ended it.
  staffEnded,
}

/// The session note: what ended the newest session and when.
typedef SessionNote = ({SessionNoteKind kind, DateTime at});

/// The note for a participating suit whose newest session ended by timeout
/// or by staff, or null.
///
/// An expired session that no operation finalized has no `endedAt`, so a
/// timeout uses `expiresAt`. An owner or eligibility end shows no note.
SessionNote? sessionNoteFor(FursuitActivation? activation) {
  final session = activation?.session;
  if (activation == null ||
      !activation.isParticipating ||
      session == null ||
      session.isActive) {
    return null;
  }
  return switch (session.endReason) {
    CatchSessionEndReason.expired => (
      kind: SessionNoteKind.timedOut,
      at: session.expiresAt,
    ),
    CatchSessionEndReason.operator => (
      kind: SessionNoteKind.staffEnded,
      at: session.endedAt ?? session.expiresAt,
    ),
    _ => null,
  };
}
