import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_riverpod/misc.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The message at the top of the suit screens.
enum SuitsBanner {
  /// The app does not know whether a write reached the server.
  unknownOutcome,

  /// The API refused the token while the native session stayed active.
  apiAccess,

  /// The server refused a write because of the player profile.
  notEligible,

  /// The server refused a write with a field message, in
  /// [SuitsState.serverMessage].
  refused,

  /// A write failed for another reason, in [SuitsState.writeFailure].
  writeFailed,
}

/// The write that runs for one suit.
enum SuitWrite {
  /// Participation on or off.
  participation,

  /// Catch session start or stop.
  session,

  /// A new name.
  name,

  /// A new photo.
  photo,

  /// A new approval mode (#512).
  approval,
}

/// What the suit list and the suit screen show. It lives in memory only.
@immutable
final class SuitsState {
  /// Creates a state.
  const new({
    this.fursuits,
    this.activations = const {},
    this.reading = false,
    this.readFailure,
    this.banner,
    this.serverMessage,
    this.writeFailure,
    this.writes = const {},
  });

  /// The player's suits, or null before the first successful read.
  final List<Fursuit>? fursuits;

  /// The participation rows at the selected convention, by suit ID.
  final Map<int, FursuitActivation> activations;

  /// Whether a read runs.
  final bool reading;

  /// The failure of the last read, or null.
  final ApiFailure? readFailure;

  /// The write message, or null.
  final SuitsBanner? banner;

  /// The server's field message for [SuitsBanner.refused].
  final String? serverMessage;

  /// The failure for [SuitsBanner.writeFailed].
  final ApiFailure? writeFailure;

  /// The running write of each suit, by suit ID.
  final Map<int, SuitWrite> writes;

  /// The suit with [id], or null.
  Fursuit? fursuit(int id) {
    for (final item in fursuits ?? const <Fursuit>[]) {
      if (item.id == id) {
        return item;
      }
    }
    return null;
  }

  SuitsState _copy({
    List<Fursuit>? fursuits,
    Map<int, FursuitActivation>? activations,
    bool? reading,
    ApiFailure? readFailure,
    bool clearReadFailure = false,
    SuitsBanner? banner,
    String? serverMessage,
    ApiFailure? writeFailure,
    bool clearBanner = false,
    Map<int, SuitWrite>? writes,
  }) => SuitsState(
    fursuits: fursuits ?? this.fursuits,
    activations: activations ?? this.activations,
    reading: reading ?? this.reading,
    readFailure: clearReadFailure ? null : readFailure ?? this.readFailure,
    banner: clearBanner ? null : banner ?? this.banner,
    serverMessage: clearBanner ? null : serverMessage ?? this.serverMessage,
    writeFailure: clearBanner ? null : writeFailure ?? this.writeFailure,
    writes: writes ?? this.writes,
  );
}

/// The result of a write that a sheet or form waits for.
sealed class SuitWriteResult {
  const new();
}

/// The server accepted the write.
final class SuitWriteDone extends SuitWriteResult {
  /// Creates the result.
  const new();
}

/// The server refused the value with a field [message].
final class SuitWriteFieldError extends SuitWriteResult {
  /// Creates the result.
  const new(this.message);

  /// The server's message for the field.
  final String message;
}

/// The write failed, and the screen banner says why.
final class SuitWriteFailed extends SuitWriteResult {
  /// Creates the result.
  const new();
}

/// The app does not know whether the write reached the server. It was not
/// sent again, and the state is being read again.
final class SuitWriteUnknown extends SuitWriteResult {
  /// Creates the result.
  const new();
}

/// Owns the suit list and the participation at one convention.
///
/// The provider is per convention, so a new selected convention reads its
/// own rows. A new player scope rebuilds it and clears all data. It reads on
/// open, on foreground return, on demand, after a participation write, and
/// when a shown live session reaches its end.
final class SuitsController extends Notifier<SuitsState> {
  /// Creates the controller for [conventionId].
  new(this.conventionId);

  /// The selected convention.
  final int conventionId;

  /// The ID of the latest read. A later read makes an earlier one stale.
  int _lastRead = 0;

  Timer? _expiry;

  /// The wait before the next read when the server still reports a session
  /// live after its end on the device clock.
  static const Duration _expiryRetry = Duration(seconds: 30);

  @override
  SuitsState build() {
    ref
      ..watch(playerScopeProvider)
      ..listen(foregroundSignalProvider, (_, _) => unawaited(read()))
      ..onDispose(() => _expiry?.cancel());
    _lastRead++;
    _expiry?.cancel();
    return const SuitsState(reading: true);
  }

  /// Reads the suits and their participation. A screen calls it when it
  /// opens, on pull to refresh, and from "Try again".
  Future<void> read() async {
    if (!ref.mounted) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    state = state._copy(reading: true);
    final repository = ref.read(fursuitRepositoryProvider);
    // Both reads run at once. The second is marked as handled, so its
    // failure is not reported as unhandled while the first one fails.
    final fursuitsRead = repository.listFursuits(
      cancellation: scope.cancellation,
    );
    final activationsRead = repository.listActivations(
      conventionId,
      cancellation: scope.cancellation,
    )..ignore();
    try {
      final fursuits = await fursuitsRead;
      final activations = await activationsRead;
      if (!live()) {
        return;
      }
      state = state._copy(
        fursuits: fursuits,
        activations: {for (final row in activations) row.fursuitId: row},
        reading: false,
        clearReadFailure: true,
      );
      _scheduleExpiry();
    } on ApiFailure catch (failure) {
      if (live()) {
        await _afterFailedRead(scope, failure, live);
      }
    }
  }

  /// Turns participation of suit [fursuitId] on or off. The screen asks for
  /// confirmation before it turns participation off.
  Future<void> setParticipation(int fursuitId, {required bool active}) async {
    await _write(fursuitId, SuitWrite.participation, (scope) async {
      await ref
          .read(fursuitRepositoryProvider)
          .setParticipation(
            conventionId,
            fursuitId,
            active: active,
            cancellation: scope.cancellation,
          );
      return () => unawaited(read());
    });
  }

  /// Starts or stops the catch session of suit [fursuitId]. It returns true
  /// when the server confirmed the change.
  Future<bool> setCatchSession(int fursuitId, {required bool active}) async {
    final result = await _write(fursuitId, SuitWrite.session, (scope) async {
      final session = await ref
          .read(fursuitRepositoryProvider)
          .setCatchSession(
            conventionId,
            fursuitId,
            active: active,
            cancellation: scope.cancellation,
          );
      return () {
        final row = state.activations[fursuitId];
        if (row != null && session != null) {
          state = state._copy(
            activations: {
              ...state.activations,
              fursuitId: row.withSession(session),
            },
          );
          _scheduleExpiry();
        }
      };
    });
    return result is SuitWriteDone;
  }

  /// Changes the name of suit [fursuitId].
  Future<SuitWriteResult> rename(int fursuitId, String name) =>
      _write(fursuitId, SuitWrite.name, (scope) async {
        final fursuit = await ref
            .read(fursuitRepositoryProvider)
            .renameFursuit(
              fursuitId,
              name: name,
              cancellation: scope.cancellation,
            );
        return () => _replace(fursuit);
      }, field: "name");

  /// Sets the approval mode of suit [fursuitId]. A change applies only to
  /// new requests, so pending requests stay pending.
  Future<SuitWriteResult> setApprovalMode(
    int fursuitId,
    CatchApprovalMode mode,
  ) => _write(fursuitId, SuitWrite.approval, (scope) async {
    final fursuit = await ref
        .read(fursuitRepositoryProvider)
        .setApprovalMode(
          fursuitId,
          mode: mode,
          cancellation: scope.cancellation,
        );
    return () => _replace(fursuit);
  });

  /// Replaces the photo of suit [fursuitId].
  Future<SuitWriteResult> replacePhoto(int fursuitId, PickedPhoto photo) =>
      _write(fursuitId, SuitWrite.photo, (scope) async {
        final fursuit = await ref
            .read(fursuitRepositoryProvider)
            .replacePhoto(
              fursuitId,
              photo: photo,
              cancellation: scope.cancellation,
            );
        return () => _replace(fursuit);
      }, field: "photo");

  /// Adds a suit that the server just created, so its screen can show it
  /// at once. The suit screen reads the server state when it opens.
  void created(Fursuit fursuit) {
    final others = (state.fursuits ?? const <Fursuit>[]).where(
      (item) => item.id != fursuit.id,
    );
    state = state._copy(fursuits: [...others, fursuit]);
  }

  /// Shows that a create elsewhere had no definite answer, and reads again.
  void createOutcomeUnknown() {
    state = state._copy(banner: SuitsBanner.unknownOutcome);
    unawaited(read());
  }

  void _replace(Fursuit fursuit) {
    state = state._copy(
      fursuits: (state.fursuits ?? const <Fursuit>[])
          .map((item) => item.id == fursuit.id ? fursuit : item)
          .toList(growable: false),
    );
  }

  /// Runs one write for a suit. [send] calls the server and returns how to
  /// apply the confirmed result. A write with no definite answer is never
  /// sent again: the controller reads the server state instead.
  Future<SuitWriteResult> _write(
    int fursuitId,
    SuitWrite kind,
    Future<void Function()> Function(PlayerScope scope) send, {
    String? field,
  }) async {
    if (state.writes.containsKey(fursuitId)) {
      return const SuitWriteFailed();
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive;
    // A read that runs now can carry a state from before this write, so
    // its result is dropped.
    final readWasRunning = state.reading;
    final mark = ++_lastRead;
    state = state._copy(
      reading: false,
      clearBanner: true,
      writes: {...state.writes, fursuitId: kind},
    );
    void finish() {
      state = state._copy(writes: {...state.writes}..remove(fursuitId));
    }

    try {
      final apply = await send(scope);
      if (!live()) {
        return const SuitWriteFailed();
      }
      // A read that overlapped the write can carry the state from before
      // it, so its result is dropped. The write's own response applies,
      // and a new read brings back what the dropped read would have
      // shown, including the expiry timer.
      final overlapped = readWasRunning || _lastRead != mark;
      if (overlapped) {
        _lastRead++;
        state = state._copy(reading: false);
      }
      finish();
      apply();
      if (overlapped && kind != SuitWrite.participation) {
        unawaited(read());
      }
      return const SuitWriteDone();
    } on ApiFailure catch (failure) {
      if (!live()) {
        return const SuitWriteFailed();
      }
      finish();
      return await _afterFailedWrite(scope, failure, field);
    }
  }

  Future<SuitWriteResult> _afterFailedWrite(
    PlayerScope scope,
    ApiFailure failure,
    String? field,
  ) async {
    switch (failure) {
      case ApiCancelledFailure():
        return const SuitWriteFailed();
      case ApiConnectivityFailure() || ApiTimeoutFailure():
        state = state._copy(banner: SuitsBanner.unknownOutcome);
        unawaited(read());
        return const SuitWriteUnknown();
      case ApiValidationFailure(:final fieldErrors):
        final fieldMessage = field == null ? null : _first(fieldErrors[field]);
        if (fieldMessage != null) {
          return SuitWriteFieldError(fieldMessage);
        }
        final message = fieldErrors.values.map(_first).nonNulls.firstOrNull;
        state = message == null
            ? state._copy(
                banner: SuitsBanner.writeFailed,
                writeFailure: failure,
              )
            : state._copy(banner: SuitsBanner.refused, serverMessage: message);
        unawaited(read());
        return const SuitWriteFailed();
      case ApiPermissionFailure():
        state = state._copy(banner: SuitsBanner.notEligible);
        return const SuitWriteFailed();
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && ref.mounted) {
          state = state._copy(banner: SuitsBanner.apiAccess);
        }
        return const SuitWriteFailed();
      case ApiFailure():
        state = state._copy(
          banner: SuitsBanner.writeFailed,
          writeFailure: failure,
        );
        unawaited(read());
        return const SuitWriteFailed();
    }
  }

  Future<void> _afterFailedRead(
    PlayerScope scope,
    ApiFailure failure,
    bool Function() live,
  ) async {
    if (failure is ApiCancelledFailure) {
      return;
    }
    if (failure is ApiUnauthenticatedFailure) {
      if (await _sessionStaysActive(scope) && live()) {
        state = state._copy(reading: false, banner: SuitsBanner.apiAccess);
      }
      return;
    }
    state = state._copy(reading: false, readFailure: failure);
  }

  /// Reads again when the soonest shown live session reaches its end, so
  /// the screen does not keep showing "Catchable" after the server ended it.
  void _scheduleExpiry() {
    _expiry?.cancel();
    DateTime? soonest;
    for (final row in state.activations.values) {
      final session = row.session;
      if (row.isCatchable && session != null) {
        if (soonest == null || session.expiresAt.isBefore(soonest)) {
          soonest = session.expiresAt;
        }
      }
    }
    if (soonest == null) {
      return;
    }
    final wait =
        soonest.difference(DateTime.now()) + const Duration(seconds: 1);
    // A live session past its end means that the device clock runs ahead
    // of the server. Reading again at once would loop, so it waits.
    _expiry = Timer(wait.isNegative ? _expiryRetry : wait, () {
      unawaited(read());
    });
  }

  Future<bool> _sessionStaysActive(PlayerScope scope) async {
    final session = ref.read(authSessionProvider);
    await session.recheckSession();
    return scope.isActive && session.state is AuthSignedIn;
  }

  static String? _first(List<String>? messages) =>
      messages == null || messages.isEmpty ? null : messages.first;
}

/// The suit data of one convention. It ends when no suit screen shows it or
/// the player scope changes.
final NotifierProviderFamily<SuitsController, SuitsState, int>
suitsControllerProvider = NotifierProvider.autoDispose
    .family<SuitsController, SuitsState, int>(SuitsController.new);
