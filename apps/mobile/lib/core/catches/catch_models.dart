import "package:flutter/foundation.dart";

/// A scanned value that has the exact printed TailTag format.
///
/// The value is secret to the suit owner. It lives only in memory, and
/// [toString] never shows it, so no log or error report can carry it.
@immutable
final class TagPayload {
  const new _(this.value);

  /// The only format that the V0 scanner accepts:
  /// `https://tailtag.app/t#` and a 43-character URL-safe base64 token.
  static final RegExp _format = RegExp(
    r"^https://tailtag\.app/t#[A-Za-z0-9_-]{43}$",
  );

  /// [raw] as a payload, or null when it is not a TailTag. A value that
  /// fails the check never goes to the server.
  static TagPayload? parse(String raw) =>
      _format.hasMatch(raw) ? TagPayload._(raw) : null;

  /// The scanned string, sent to the server as is.
  final String value;

  @override
  bool operator ==(Object other) => other is TagPayload && other.value == value;

  @override
  int get hashCode => value.hashCode;

  @override
  String toString() => "TagPayload(<redacted>)";
}

/// A suit as a catch read shows it.
@immutable
final class CatchFursuit {
  /// Creates a suit summary.
  const new({required this.id, required this.name, required this.photoUrl});

  /// The server ID.
  final int id;

  /// The suit name.
  final String name;

  /// The signed photo URL.
  final Uri photoUrl;
}

/// The suit that a scanned tag resolves to at the player's convention.
@immutable
final class CatchPreview {
  /// Creates a preview.
  const new({required this.fursuit, required this.conventionId});

  /// The suit.
  final CatchFursuit fursuit;

  /// The convention that the server resolved the tag against.
  final int conventionId;
}

/// The state of a request, as the player sees it.
enum CatchRequestState {
  /// The owner has not decided.
  pending,

  /// A catch exists for this request.
  approved,

  /// The owner declined.
  declined,

  /// The player withdrew it, or left the convention.
  withdrawn,

  /// It ended for a reason that the player does not see.
  unavailable,
}

/// One of the player's own catch requests.
@immutable
final class PlayerCatchRequest {
  /// Creates a request.
  const new({
    required this.id,
    required this.fursuit,
    required this.conventionId,
    required this.state,
    required this.requestedAt,
    required this.reviewDeadlineAt,
  });

  /// The server ID.
  final int id;

  /// The suit.
  final CatchFursuit fursuit;

  /// The convention of the request.
  final int conventionId;

  /// The current state.
  final CatchRequestState state;

  /// The server time of the submission.
  final DateTime requestedAt;

  /// When the convention's review window closes.
  final DateTime reviewDeadlineAt;

  /// A copy with [state].
  PlayerCatchRequest withState(CatchRequestState state) => PlayerCatchRequest(
    id: id,
    fursuit: fursuit,
    conventionId: conventionId,
    state: state,
    requestedAt: requestedAt,
    reviewDeadlineAt: reviewDeadlineAt,
  );
}

/// What a submission did.
enum CatchSubmitOutcome {
  /// A new request waits for the owner.
  pending,

  /// Automatic approval made a catch.
  approved,

  /// A request for this suit already waits.
  alreadyPending,

  /// The player already caught this suit at this convention.
  alreadyCaught,
}

/// The server answer to a submission.
@immutable
final class CatchSubmission {
  /// Creates an answer.
  const new({required this.outcome, this.request});

  /// What the submission did.
  final CatchSubmitOutcome outcome;

  /// The request, when the answer carries one.
  final PlayerCatchRequest? request;
}

/// One completed catch in the private collection.
@immutable
final class CaughtFursuit {
  /// Creates a catch.
  const new({
    required this.id,
    required this.fursuit,
    required this.conventionId,
    required this.conventionName,
    required this.caughtAt,
  });

  /// The server ID.
  final int id;

  /// The suit.
  final CatchFursuit fursuit;

  /// The convention of the catch.
  final int conventionId;

  /// The convention name.
  final String conventionName;

  /// The server time of the request that made the catch.
  final DateTime caughtAt;
}

/// One page of the collection.
@immutable
final class CatchHistoryPage {
  /// Creates a page.
  const new({required this.items, required this.hasNext});

  /// The catches, newest first.
  final List<CaughtFursuit> items;

  /// Whether a later page exists.
  final bool hasNext;
}
