/// A suit that the signed-in player owns, as the server reports it.
final class Fursuit {
  /// Creates a suit.
  const new({
    required this.id,
    required this.name,
    required this.photoUrl,
    required this.isEnabled,
  });

  /// The server ID.
  final int id;

  /// The name, as the server normalized it.
  final String name;

  /// A short-lived read URL for the photo. A new read gives a new URL.
  final Uri photoUrl;

  /// False when TailTag staff disabled the suit.
  final bool isEnabled;
}

/// Why a catch session ended, as the server reports it.
enum CatchSessionEndReason {
  /// The owner stopped it.
  owner,

  /// TailTag staff stopped it.
  operator,

  /// The suit stopped participating, or lost eligibility.
  eligibilityLost,

  /// It reached its 12-hour lifetime.
  expired,
}

/// The newest catch session of a suit at one convention.
final class CatchSession {
  /// Creates a session.
  const new({
    required this.isActive,
    required this.startedAt,
    required this.expiresAt,
    required this.endedAt,
    required this.endReason,
  });

  /// Whether the suit is catchable now. The server computes it.
  final bool isActive;

  /// When the session started.
  final DateTime startedAt;

  /// When the session ends by itself.
  final DateTime expiresAt;

  /// When the session ended, or null while it has not ended.
  final DateTime? endedAt;

  /// Why the session ended, or null while it has not ended.
  final CatchSessionEndReason? endReason;
}

/// The participation of one suit at one convention.
final class FursuitActivation {
  /// Creates an activation.
  const new({
    required this.fursuitId,
    required this.isActive,
    required this.isEligible,
    required this.session,
  });

  /// The suit's server ID.
  final int fursuitId;

  /// The owner's stored choice to participate.
  final bool isActive;

  /// Whether the server allows participation now.
  final bool isEligible;

  /// The newest catch session, or null when the suit never had one.
  final CatchSession? session;

  /// Whether the suit participates now: chosen and allowed.
  bool get isParticipating => isActive && isEligible;

  /// Whether the suit is catchable now.
  bool get isCatchable => isParticipating && (session?.isActive ?? false);

  /// A copy with [session] in place of the current session.
  FursuitActivation withSession(CatchSession session) => FursuitActivation(
    fursuitId: fursuitId,
    isActive: isActive,
    isEligible: isEligible,
    session: session,
  );
}

/// A photo that the owner picked, ready to upload.
final class PickedPhoto {
  /// Creates a photo from its [bytes] and file [name].
  const new({required this.bytes, required this.name});

  /// The encoded image.
  final List<int> bytes;

  /// The file name that the picker gave.
  final String name;
}
