/// The lifecycle status of a convention, as the server reports it.
enum ConventionStatus {
  /// Not open yet.
  draft,

  /// Open for play.
  active,

  /// Stopped for now.
  paused,

  /// Finished.
  completed,

  /// Called off.
  cancelled,
}

/// A convention that the server reports.
final class Convention {
  /// Creates a convention.
  const new({
    required this.id,
    required this.name,
    required this.status,
    required this.startDate,
    required this.endDate,
    this.timeZone,
    this.reviewDeadlineAt,
    this.reviewDeadlineLocalDate,
    this.reviewOpen = false,
  });

  /// The server ID.
  final int id;

  /// The official name.
  final String name;

  /// The current lifecycle status.
  final ConventionStatus status;

  /// The first day. It is a calendar date at local midnight, so it never
  /// needs a timezone conversion.
  final DateTime startDate;

  /// The last day, as a calendar date at local midnight.
  final DateTime endDate;

  /// The IANA time zone that operators set, or null before one is set.
  final String? timeZone;

  /// The UTC instant when the catch request review window closes, or null
  /// while the convention has no time zone.
  final DateTime? reviewDeadlineAt;

  /// The convention-local calendar day that starts at [reviewDeadlineAt],
  /// as a date at local midnight. Owners can review until the end of the
  /// day before it.
  final DateTime? reviewDeadlineLocalDate;

  /// Whether the review window is open now, as the server computed it.
  final bool reviewOpen;

  /// Whether the convention is open for play.
  bool get isOpen => status == ConventionStatus.active;

  /// Whether a player can scan to catch here: the convention is open and
  /// its review window is open. The server still decides each scan.
  bool get catchingOpen => isOpen && reviewOpen;
}

/// The durable relationship between the player and a convention.
final class ConventionEnrollment {
  /// Creates an enrollment.
  const new({
    required this.id,
    required this.convention,
    required this.isSelected,
  });

  /// The server ID.
  final int id;

  /// The convention, with its current status.
  final Convention convention;

  /// Whether this enrollment is the player's selected convention.
  final bool isSelected;
}
