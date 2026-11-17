import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/catches/catch_providers.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/conventions/convention_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The message at the top of the request list.
enum RequestsBanner {
  /// The server has no catch flow.
  serviceOff,

  /// The player cannot use catches at the selected convention.
  ineligible,

  /// The API refused the token while the native session stayed active.
  apiAccess,

  /// Another action changed the request before the withdrawal.
  changed,

  /// The request is gone: the window closed or cleanup deleted it.
  gone,

  /// A withdrawal ended with no definite answer.
  withdrawUnknown,

  /// A withdrawal failed, in [RequestsState.failure].
  withdrawFailed,
}

/// What the request list shows. It lives in memory only.
@immutable
final class RequestsState {
  /// Creates a state.
  const new({
    this.requests,
    this.conventions = const {},
    this.reading = false,
    this.readFailure,
    this.banner,
    this.failure,
    this.withdrawing,
  });

  /// The requests in server order, or null before the first read.
  final List<PlayerCatchRequest>? requests;

  /// The known conventions by ID, for the group headers.
  final Map<int, Convention> conventions;

  /// Whether a read runs.
  final bool reading;

  /// The failure of the last read, or null.
  final ApiFailure? readFailure;

  /// The message, or null.
  final RequestsBanner? banner;

  /// The failure for [RequestsBanner.withdrawFailed].
  final ApiFailure? failure;

  /// The request whose withdrawal runs, or null.
  final int? withdrawing;

  RequestsState _copy({
    List<PlayerCatchRequest>? requests,
    Map<int, Convention>? conventions,
    bool? reading,
    RequestsBanner? banner,
    ApiFailure? failure,
    bool clearReadFailure = false,
    bool clearBanner = false,
    bool clearWithdrawing = false,
    int? withdrawing,
    ApiFailure? readFailure,
  }) => RequestsState(
    requests: requests ?? this.requests,
    conventions: conventions ?? this.conventions,
    reading: reading ?? this.reading,
    readFailure: clearReadFailure ? null : readFailure ?? this.readFailure,
    banner: clearBanner ? null : banner ?? this.banner,
    failure: clearBanner ? null : failure ?? this.failure,
    withdrawing: clearWithdrawing ? null : withdrawing ?? this.withdrawing,
  );
}

/// The banners that a successful read makes stale.
const Set<RequestsBanner> _readBanners = {
  RequestsBanner.serviceOff,
  RequestsBanner.ineligible,
  RequestsBanner.apiAccess,
};

/// Owns the player's request list while the Requests section is alive.
///
/// It reads on open, on foreground return, on pull to refresh, after a
/// withdrawal, and once at the earliest review deadline on screen. It
/// never polls. A withdrawal with no definite answer is never repeated by
/// itself: the list is read again instead.
final class RequestsController extends Notifier<RequestsState> {
  int _lastRead = 0;
  Timer? _deadline;

  @override
  RequestsState build() {
    ref
      ..watch(playerScopeProvider)
      ..listen(foregroundSignalProvider, (_, _) => unawaited(read()))
      ..onDispose(() => _deadline?.cancel());
    _lastRead++;
    _deadline?.cancel();
    return const RequestsState(reading: true);
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
    try {
      final conventionsRepository = ref.read(conventionRepositoryProvider);
      final requests = await ref
          .read(catchRepositoryProvider)
          .listRequests(cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      final enrollments = await conventionsRepository.listEnrollments(
        cancellation: scope.cancellation,
      );
      if (!live()) {
        return;
      }
      final conventions = <int, Convention>{
        for (final enrollment in enrollments)
          enrollment.convention.id: enrollment.convention,
      };
      // A request can belong to a convention that the player left. Its
      // header reads that convention, and a failed read keeps the generic
      // header (#511 AC22).
      final missing = {
        for (final request in requests)
          if (!conventions.containsKey(request.conventionId))
            request.conventionId,
      };
      for (final conventionId in missing) {
        try {
          conventions[conventionId] = await conventionsRepository
              .readConvention(conventionId, cancellation: scope.cancellation);
        } on ApiFailure {
          // The header falls back to "Another convention".
        }
        if (!live()) {
          return;
        }
      }
      state = RequestsState(
        requests: requests,
        conventions: conventions,
        banner: _readBanners.contains(state.banner) ? null : state.banner,
        failure: state.failure,
      );
      _armDeadline(requests);
    } on ApiFailure catch (failure) {
      if (live()) {
        await _afterFailedRead(scope, failure, live);
      }
    }
  }

  /// Withdraws [request]. It returns true when the server confirmed it.
  Future<bool> withdraw(PlayerCatchRequest request) async {
    if (state.withdrawing != null) {
      return false;
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive;
    // A read that runs now can carry the state from before the withdrawal.
    _lastRead++;
    state = state._copy(
      reading: false,
      withdrawing: request.id,
      clearBanner: true,
    );
    try {
      final updated = await ref
          .read(catchRepositoryProvider)
          .withdraw(request.id, cancellation: scope.cancellation);
      if (!live()) {
        return false;
      }
      state = state._copy(
        clearWithdrawing: true,
        requests: [
          for (final item in state.requests ?? const <PlayerCatchRequest>[])
            if (item.id == updated.id) updated else item,
        ],
      );
      // The list is read again after each withdrawal (#511 AC25).
      unawaited(read());
      return true;
    } on ApiFailure catch (failure) {
      if (!live()) {
        return false;
      }
      state = state._copy(clearWithdrawing: true);
      await _afterFailedWithdraw(scope, failure, live);
      return false;
    }
  }

  Future<void> _afterFailedWithdraw(
    PlayerScope scope,
    ApiFailure failure,
    bool Function() live,
  ) async {
    void showAndRead(RequestsBanner banner) {
      state = state._copy(banner: banner);
      unawaited(read());
    }

    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiConflictFailure(code: "request_state_changed"):
        showAndRead(RequestsBanner.changed);
      case ApiConflictFailure(code: "review_window_closed") ||
          ApiNotFoundFailure(code: "request_not_found"):
        showAndRead(RequestsBanner.gone);
      // A 5xx can come from a proxy after the server committed the
      // withdrawal, so it is an unknown outcome too.
      case ApiConnectivityFailure() ||
          ApiTimeoutFailure() ||
          ApiServerFailure():
        showAndRead(RequestsBanner.withdrawUnknown);
      case ApiNotFoundFailure(code: null):
        state = state._copy(banner: RequestsBanner.serviceOff);
      case ApiPermissionFailure():
        state = state._copy(banner: RequestsBanner.ineligible);
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && live()) {
          state = state._copy(banner: RequestsBanner.apiAccess);
        }
      case ApiFailure():
        state = state._copy(
          banner: RequestsBanner.withdrawFailed,
          failure: failure,
        );
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
          banner: RequestsBanner.serviceOff,
          clearReadFailure: true,
        );
      case ApiPermissionFailure():
        state = state._copy(
          reading: false,
          banner: RequestsBanner.ineligible,
          clearReadFailure: true,
        );
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && live()) {
          state = state._copy(
            reading: false,
            banner: RequestsBanner.apiAccess,
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
  /// requests leave the list.
  void _armDeadline(List<PlayerCatchRequest> requests) {
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

/// The player's request list. It ends when the Requests section closes or
/// the player scope changes.
final NotifierProvider<RequestsController, RequestsState>
requestsControllerProvider =
    NotifierProvider.autoDispose<RequestsController, RequestsState>(
      RequestsController.new,
    );
