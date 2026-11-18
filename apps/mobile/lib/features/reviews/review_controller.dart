import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_riverpod/misc.dart";
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/catches/catch_providers.dart";
import "package:tailtag_mobile/core/catches/catch_repository.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/features/catches/convention_headers.dart";
import "package:tailtag_mobile/features/reviews/pending_summary_controller.dart";

/// An owner action on one request.
enum ReviewAction {
  /// Approve a pending request.
  approve,

  /// Decline a pending request, with or without a block.
  decline,

  /// Undo an ordinary decline.
  undo,

  /// Return a declined request to pending.
  restore,

  /// Remove the block of the request's player, suit, and convention.
  unblock,
}

/// The message at the top of the review screen.
enum ReviewBanner {
  /// The server has no catch review.
  serviceOff,

  /// The server refused the owner with 403.
  ineligible,

  /// The API refused the token while the native session stayed active.
  apiAccess,

  /// Another action changed the request first.
  changed,

  /// The server refuses approval for now.
  paused,

  /// A catch already exists for the player, suit, and convention.
  alreadyCaught,

  /// A newer request, a catch, or an operator action stops a restore.
  cannotRestore,

  /// The undo time passed.
  tooLateToUndo,

  /// The request is gone: the window closed or cleanup deleted it.
  gone,

  /// An action ended with no definite answer.
  unknown,

  /// An action failed for another reason, in [ReviewState.failure].
  failed,
}

/// What the review screen shows. It lives in memory only.
@immutable
final class ReviewState {
  /// Creates a state.
  const new({
    this.requests,
    this.conventions = const {},
    this.reading = false,
    this.readFailure,
    this.banner,
    this.failure,
    this.acting,
  });

  /// The requests in server order, or null before the first read.
  final List<OwnerCatchRequest>? requests;

  /// The known conventions by ID, for the group headers.
  final Map<int, Convention> conventions;

  /// Whether a read runs.
  final bool reading;

  /// The failure of the last read, or null.
  final ApiFailure? readFailure;

  /// The message, or null.
  final ReviewBanner? banner;

  /// The failure for [ReviewBanner.failed].
  final ApiFailure? failure;

  /// The request and the action that runs, or null.
  final ({int id, ReviewAction action})? acting;

  ReviewState _copy({
    List<OwnerCatchRequest>? requests,
    bool? reading,
    ReviewBanner? banner,
    ApiFailure? failure,
    ApiFailure? readFailure,
    bool clearReadFailure = false,
    bool clearBanner = false,
    ({int id, ReviewAction action})? acting,
    bool clearActing = false,
  }) => ReviewState(
    requests: requests ?? this.requests,
    conventions: conventions,
    reading: reading ?? this.reading,
    readFailure: clearReadFailure ? null : readFailure ?? this.readFailure,
    banner: clearBanner ? null : banner ?? this.banner,
    failure: clearBanner ? null : failure ?? this.failure,
    acting: clearActing ? null : acting ?? this.acting,
  );
}

/// The banners that a successful read makes stale.
const Set<ReviewBanner> _readBanners = {
  ReviewBanner.serviceOff,
  ReviewBanner.ineligible,
  ReviewBanner.apiAccess,
};

/// How long undo stays possible after the app sends a decline (#512 G4).
const Duration undoLimit = Duration(seconds: 10);

/// Owns the requests on the owner's suits while the review screen shows
/// them (#512 AC9, AC29).
///
/// It reads on open, on foreground return, on pull to refresh, after each
/// action, and once at the earliest review deadline on screen. It never
/// polls. An action with no definite answer is never repeated by itself:
/// the list is read again instead. The provider is per suit filter, and a
/// null filter shows every suit.
final class ReviewController extends Notifier<ReviewState> {
  /// Creates the controller for suit [fursuitId], or every suit for null.
  new(this.fursuitId);

  /// The suit filter, or null.
  final int? fursuitId;

  int _lastRead = 0;
  Timer? _deadline;

  @override
  ReviewState build() {
    ref
      ..watch(playerScopeProvider)
      ..listen(foregroundSignalProvider, (_, _) => unawaited(read()))
      ..onDispose(() => _deadline?.cancel());
    _lastRead++;
    _deadline?.cancel();
    return const ReviewState(reading: true);
  }

  /// Reads the requests and the conventions that their headers need.
  Future<void> read() async {
    if (!ref.mounted) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    state = state._copy(reading: true);
    refreshPendingSummary(ref);
    try {
      final requests = await ref
          .read(catchRepositoryProvider)
          .listIncoming(fursuitId: fursuitId, cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      final conventions = await readHeaderConventions(
        ref,
        scope,
        requests.map((request) => request.conventionId),
        live: live,
      );
      if (conventions == null) {
        return;
      }
      state = ReviewState(
        requests: requests,
        conventions: conventions,
        banner: _readBanners.contains(state.banner) ? null : state.banner,
        failure: state.failure,
        acting: state.acting,
      );
      _armDeadline(requests);
    } on ApiFailure catch (failure) {
      if (live()) {
        await _afterFailedRead(scope, failure, live);
      }
    }
  }

  /// Approves [request]. It returns true when the server confirmed it.
  Future<bool> approve(OwnerCatchRequest request) =>
      _act(request.id, ReviewAction.approve, (repository, cancellation) {
        return repository.approve(request.id, cancellation: cancellation);
      });

  /// Declines [request], with a block when [block] is true. It returns true
  /// when the server confirmed it.
  ///
  /// After an ordinary decline, the controller stays alive for [undoLimit],
  /// so the undo snackbar still works after the owner leaves the screen.
  Future<bool> decline(OwnerCatchRequest request, {required bool block}) async {
    final done = await _act(request.id, ReviewAction.decline, (
      repository,
      cancellation,
    ) {
      return repository.decline(
        request.id,
        block: block,
        cancellation: cancellation,
      );
    });
    if (done && !block && ref.mounted) {
      final link = ref.keepAlive();
      Timer(undoLimit, link.close);
    }
    return done;
  }

  /// Undoes the ordinary decline of request [id].
  Future<bool> undo(int id) =>
      _act(id, ReviewAction.undo, (repository, cancellation) {
        return repository.undoDecline(id, cancellation: cancellation);
      });

  /// Returns declined [request] to pending.
  Future<bool> restore(OwnerCatchRequest request) =>
      _act(request.id, ReviewAction.restore, (repository, cancellation) {
        return repository.restore(request.id, cancellation: cancellation);
      });

  /// Removes the block of [request]'s player, suit, and convention.
  Future<bool> unblock(OwnerCatchRequest request) =>
      _act(request.id, ReviewAction.unblock, (repository, cancellation) async {
        await repository.unblock(request.id, cancellation: cancellation);
        return null;
      });

  /// Runs one action. [send] returns the updated request, or null when the
  /// response has none. Every action reads the list again afterward.
  Future<bool> _act(
    int id,
    ReviewAction action,
    Future<OwnerCatchRequest?> Function(
      CatchRepository repository,
      ApiCancellation cancellation,
    )
    send,
  ) async {
    if (!ref.mounted || state.acting != null) {
      return false;
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive;
    // A read that runs now can carry the state from before the action.
    _lastRead++;
    state = state._copy(
      reading: false,
      acting: (id: id, action: action),
      clearBanner: true,
    );
    // The owner can leave the screen while the action runs. The controller
    // stays alive until the answer arrives and, after a success, until the
    // read that follows ends. That read also refreshes the pending counts.
    final link = ref.keepAlive();
    var closeNow = true;
    try {
      final updated = await send(
        ref.read(catchRepositoryProvider),
        scope.cancellation,
      );
      if (!live()) {
        return false;
      }
      state = state._copy(
        clearActing: true,
        requests: updated == null
            ? null
            : [
                for (final item
                    in state.requests ?? const <OwnerCatchRequest>[])
                  if (item.id == updated.id) updated else item,
              ],
      );
      closeNow = false;
      unawaited(read().whenComplete(link.close));
      return true;
    } on ApiFailure catch (failure) {
      if (!live()) {
        return false;
      }
      state = state._copy(clearActing: true);
      await _afterFailedAction(scope, action, failure);
      return false;
    } finally {
      if (closeNow) {
        link.close();
      }
    }
  }

  Future<void> _afterFailedAction(
    PlayerScope scope,
    ReviewAction action,
    ApiFailure failure,
  ) async {
    void showAndRead(ReviewBanner banner) {
      state = state._copy(banner: banner);
      unawaited(read());
    }

    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiConflictFailure(code: "request_state_changed"):
        showAndRead(ReviewBanner.changed);
      case ApiConflictFailure(code: "approval_paused"):
        showAndRead(ReviewBanner.paused);
      case ApiConflictFailure(code: "request_superseded"):
        showAndRead(
          action == ReviewAction.approve
              ? ReviewBanner.alreadyCaught
              : ReviewBanner.cannotRestore,
        );
      case ApiConflictFailure(code: "undo_expired"):
        showAndRead(ReviewBanner.tooLateToUndo);
      case ApiConflictFailure(code: "review_window_closed") ||
          ApiNotFoundFailure(code: "request_not_found"):
        showAndRead(ReviewBanner.gone);
      // A 5xx can come from a proxy after the server committed the action,
      // so it is an unknown outcome too.
      case ApiConnectivityFailure() ||
          ApiTimeoutFailure() ||
          ApiServerFailure():
        showAndRead(ReviewBanner.unknown);
      case ApiNotFoundFailure(code: null):
        state = state._copy(banner: ReviewBanner.serviceOff);
      case ApiPermissionFailure():
        state = state._copy(banner: ReviewBanner.ineligible);
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && ref.mounted) {
          state = state._copy(banner: ReviewBanner.apiAccess);
        }
      case ApiFailure():
        state = state._copy(banner: ReviewBanner.failed, failure: failure);
        unawaited(read());
    }
  }

  Future<void> _afterFailedRead(
    PlayerScope scope,
    ApiFailure failure,
    bool Function() live,
  ) async {
    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiNotFoundFailure(code: null):
        state = state._copy(
          reading: false,
          banner: ReviewBanner.serviceOff,
          clearReadFailure: true,
        );
      case ApiPermissionFailure():
        state = state._copy(
          reading: false,
          banner: ReviewBanner.ineligible,
          clearReadFailure: true,
        );
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && live()) {
          state = state._copy(
            reading: false,
            banner: ReviewBanner.apiAccess,
            clearReadFailure: true,
          );
        } else if (live()) {
          state = state._copy(reading: false);
        }
      case ApiFailure():
        state = state._copy(reading: false, readFailure: failure);
    }
  }

  /// Reads again at the earliest deadline on screen, when that window's
  /// requests leave the list (#512 AC29).
  void _armDeadline(List<OwnerCatchRequest> requests) {
    _deadline?.cancel();
    final now = DateTime.now();
    DateTime? earliest;
    for (final request in requests) {
      final at = request.reviewDeadlineAt;
      if (at.isAfter(now) && (earliest == null || at.isBefore(earliest))) {
        earliest = at;
      }
    }
    if (earliest == null) {
      return;
    }
    // One extra second, so the server time is past the deadline too.
    _deadline = Timer(
      earliest.difference(now) + const Duration(seconds: 1),
      () => unawaited(read()),
    );
  }

  Future<bool> _sessionStaysActive(PlayerScope scope) async {
    final session = ref.read(authSessionProvider);
    await session.recheckSession();
    return scope.isActive && session.state is AuthSignedIn;
  }
}

/// The owner's requests for one suit filter. It ends when the review
/// screen closes or the player scope changes. After an ordinary decline it
/// stays for [undoLimit], so the undo snackbar still works.
final NotifierProviderFamily<ReviewController, ReviewState, int?>
reviewControllerProvider = NotifierProvider.autoDispose
    .family<ReviewController, ReviewState, int?>(ReviewController.new);
