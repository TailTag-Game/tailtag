import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/conventions/convention_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_profile_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The message at the top of the picker.
enum PickerBanner {
  /// The server refused the entry.
  entryFailed,

  /// The server refused the entry for a reason with no explanation.
  unknownError,

  /// The app does not know whether a write landed.
  unknownOutcome,

  /// A recovery read shows the enrollment but not the selection.
  notEntered,

  /// A recovery read shows no enrollment.
  notJoined,

  /// The API refused the token while the native session stayed active.
  apiAccess,
}

/// How the player stands with a listed convention.
enum ConventionRowKind {
  /// The player has not joined.
  fresh,

  /// The player joined, and another convention or none is selected.
  joined,

  /// The convention is the selection.
  selected,
}

/// A listed convention and how the player stands with it.
@immutable
final class ConventionRow {
  /// Creates a row.
  const new(this.convention, this.kind);

  /// The listed convention.
  final Convention convention;

  /// How the player stands with it.
  final ConventionRowKind kind;
}

/// A server result that moves the player away from the picker.
@immutable
sealed class PickerResolution {
  /// Creates a resolution for [scope].
  const new(this.scope);

  /// The player scope that produced the result.
  final PlayerScope scope;
}

/// The server selected this enrollment.
final class PickerEntered extends PickerResolution {
  /// Creates the resolution.
  const new(super.scope, this.enrollment);

  /// The selected enrollment.
  final ConventionEnrollment enrollment;
}

/// A fresh profile is no longer eligible.
final class PickerIneligible extends PickerResolution {
  /// Creates the resolution.
  const new(super.scope, this.profile);

  /// The fresh profile.
  final PlayerProfile profile;
}

/// What the picker shows. It lives in memory only.
@immutable
final class ConventionPickerState {
  /// Creates a state.
  const new({
    this.rows,
    this.reading = false,
    this.recovering = false,
    this.writingId,
    this.readFailure,
    this.banner,
    this.writesLocked = false,
    this.resolution,
  });

  /// The rows of the last successful read, or null before one.
  final List<ConventionRow>? rows;

  /// Whether a read that the player asked for is running.
  final bool reading;

  /// Whether a recovery read is running.
  final bool recovering;

  /// The convention whose write is running, or null.
  final int? writingId;

  /// The failure of the last read, or null.
  final ApiFailure? readFailure;

  /// The banner, or null. A [readFailure] replaces it on screen.
  final PickerBanner? banner;

  /// Whether writes wait for a successful read.
  final bool writesLocked;

  /// The result that moves the player away, or null.
  final PickerResolution? resolution;

  /// Whether a row action can start a write.
  bool get canWrite =>
      rows != null && writingId == null && !writesLocked && resolution == null;

  /// Whether the player can leave for another signed-in screen.
  bool get canLeave => writingId == null;
}

/// Runs the picker over the convention repository.
///
/// It sends one write at a time and only on an explicit action. It never
/// repeats a write. After a result with no definite answer, it locks writes
/// until a read succeeds. Every async step captures its [PlayerScope], so a
/// late result from a closed scope changes nothing.
final class ConventionPickerController extends Notifier<ConventionPickerState> {
  /// The ID of the latest read. A later read or a write makes an earlier ID
  /// stale, so its result is dropped.
  int _lastRead = 0;

  /// The convention of the write with no definite answer, or null.
  int? _target;

  bool _foregroundRunning = false;

  @override
  ConventionPickerState build() {
    // A new player scope rebuilds this provider and clears the picker.
    ref
      ..watch(playerScopeProvider)
      ..listen(
        foregroundSignalProvider,
        (_, _) => unawaited(_readOnForeground()),
      );
    _target = null;
    return const ConventionPickerState(reading: true);
  }

  /// Runs the first read when a screen opens. The screen starts it, so a
  /// scope change alone sends no read.
  Future<void> open() async {
    if (ref.mounted) {
      await _read(ref.read(playerScopeProvider));
    }
  }

  /// Runs "Join and enter" for a new [row], or "Enter convention" for a
  /// joined one.
  Future<void> enter(ConventionRow row) async {
    final id = row.convention.id;
    if (!state.canWrite || row.kind == ConventionRowKind.selected) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    _lastRead++;
    state = ConventionPickerState(rows: state.rows, writingId: id);
    final repository = ref.read(conventionRepositoryProvider);
    final ConventionEnrollment enrollment;
    try {
      enrollment = row.kind == ConventionRowKind.fresh
          ? await repository.enrollAndSelect(
              id,
              cancellation: scope.cancellation,
            )
          : await repository.select(id, cancellation: scope.cancellation);
    } on ApiFailure catch (failure) {
      if (scope.isActive) {
        await _afterFailedWrite(scope, failure, id);
      }
      return;
    }
    if (!scope.isActive) {
      return;
    }
    if (enrollment.isSelected && enrollment.convention.id == id) {
      _resolve(PickerEntered(scope, enrollment));
    } else {
      _lockAfterUnknown(id);
    }
  }

  /// Reads again. After a write with no definite answer, this is the
  /// recovery read.
  Future<void> tryAgain() async {
    if (state.writingId != null || state.recovering || state.reading) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final target = _target;
    if (target != null) {
      await _recover(scope, target);
      return;
    }
    state = ConventionPickerState(
      rows: state.rows,
      reading: true,
      readFailure: state.readFailure,
      banner: state.banner,
      writesLocked: state.writesLocked,
    );
    await _read(scope);
  }

  /// Reads again after a pull. It never runs the recovery read: only Try
  /// again does.
  Future<void> pullToRefresh() async {
    if (_target == null) {
      await tryAgain();
    }
  }

  Future<void> _afterFailedWrite(
    PlayerScope scope,
    ApiFailure failure,
    int id,
  ) async {
    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiValidationFailure() || ApiNotFoundFailure():
        state = ConventionPickerState(
          rows: state.rows,
          banner: PickerBanner.entryFailed,
        );
        await _read(scope, banner: PickerBanner.entryFailed);
      case ApiPermissionFailure():
        state = ConventionPickerState(
          rows: state.rows,
          banner: PickerBanner.unknownError,
        );
        await _read(
          scope,
          banner: PickerBanner.unknownError,
          withProfile: true,
        );
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope)) {
          _target = id;
          state = ConventionPickerState(
            rows: state.rows,
            banner: PickerBanner.apiAccess,
            writesLocked: true,
          );
        }
      case ApiFailure():
        _lockAfterUnknown(id);
    }
  }

  void _lockAfterUnknown(int id) {
    _target = id;
    state = ConventionPickerState(
      rows: state.rows,
      banner: PickerBanner.unknownOutcome,
      writesLocked: true,
    );
  }

  /// Reads the lists. A failure keeps the rows and locks writes, because a
  /// failed read leaves rows that can be stale.
  Future<void> _read(
    PlayerScope scope, {
    PickerBanner? banner,
    bool withProfile = false,
  }) async {
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    try {
      if (withProfile) {
        final profile = await ref
            .read(playerProfileRepositoryProvider)
            .fetch(cancellation: scope.cancellation);
        if (!live()) {
          return;
        }
        if (!profile.isEnabled || !profile.onboardingComplete) {
          _resolve(PickerIneligible(scope, profile));
          return;
        }
      }
      final lists = await _fetchLists(scope);
      if (live()) {
        state = ConventionPickerState(rows: lists.rows, banner: banner);
      }
    } on ApiCancelledFailure {
      return;
    } on ApiUnauthenticatedFailure {
      if (live() && await _sessionStaysActive(scope) && live()) {
        state = ConventionPickerState(
          rows: state.rows,
          banner: PickerBanner.apiAccess,
          writesLocked: true,
        );
      }
    } on ApiFailure catch (failure) {
      if (live()) {
        state = ConventionPickerState(
          rows: state.rows,
          readFailure: failure,
          writesLocked: state.rows != null,
        );
      }
    }
  }

  /// Resolves a write with no definite answer from the server lists. It
  /// sends no write.
  Future<void> _recover(PlayerScope scope, int target) async {
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    state = ConventionPickerState(
      rows: state.rows,
      recovering: true,
      banner: state.banner,
      writesLocked: true,
    );
    final _Lists lists;
    try {
      lists = await _fetchLists(scope);
    } on ApiCancelledFailure {
      return;
    } on ApiUnauthenticatedFailure {
      if (live() && await _sessionStaysActive(scope) && live()) {
        _stayUnknown();
      }
      return;
    } on ApiFailure {
      if (live()) {
        _stayUnknown();
      }
      return;
    }
    if (!live()) {
      return;
    }
    final enrollment = lists.enrollments
        .where((item) => item.convention.id == target)
        .firstOrNull;
    if (enrollment != null && enrollment.isSelected) {
      _target = null;
      _resolve(PickerEntered(scope, enrollment));
      return;
    }
    _target = null;
    final listed = lists.rows.any((row) => row.convention.id == target);
    state = ConventionPickerState(
      rows: lists.rows,
      banner: !listed
          ? PickerBanner.entryFailed
          : enrollment != null
          ? PickerBanner.notEntered
          : PickerBanner.notJoined,
    );
  }

  void _stayUnknown() {
    state = ConventionPickerState(
      rows: state.rows,
      banner: state.banner ?? PickerBanner.unknownOutcome,
      writesLocked: true,
    );
  }

  /// Reads the profile and the lists after the app returns to the
  /// foreground. The rows stay on screen during the read.
  Future<void> _readOnForeground() async {
    final current = state;
    if (_foregroundRunning ||
        current.rows == null ||
        current.writingId != null ||
        current.recovering ||
        current.writesLocked ||
        current.resolution != null) {
      return;
    }
    _foregroundRunning = true;
    try {
      await _read(
        ref.read(playerScopeProvider),
        banner: current.banner,
        withProfile: true,
      );
    } finally {
      _foregroundRunning = false;
    }
  }

  Future<_Lists> _fetchLists(PlayerScope scope) async {
    final repository = ref.read(conventionRepositoryProvider);
    final conventionsRead = repository.listConventions(
      cancellation: scope.cancellation,
    );
    final enrollmentsRead = repository.listEnrollments(
      cancellation: scope.cancellation,
    );
    // All or nothing: the first failure throws.
    await Future.wait<Object>([conventionsRead, enrollmentsRead]);
    final enrollments = await enrollmentsRead;
    final conventions = await conventionsRead;
    return _Lists(_rows(conventions, enrollments), enrollments);
  }

  static List<ConventionRow> _rows(
    List<Convention> conventions,
    List<ConventionEnrollment> enrollments,
  ) {
    final joined = {
      for (final item in enrollments) item.convention.id: item.isSelected,
    };
    return [
      for (final convention in conventions)
        ConventionRow(convention, switch (joined[convention.id]) {
          null => ConventionRowKind.fresh,
          true => ConventionRowKind.selected,
          false => ConventionRowKind.joined,
        }),
    ];
  }

  /// Checks the native session once. If it ended, the state events move the
  /// stage and close [scope].
  Future<bool> _sessionStaysActive(PlayerScope scope) async {
    final session = ref.read(authSessionProvider);
    await session.recheckSession();
    return scope.isActive && session.state is AuthSignedIn;
  }

  /// The picker stays busy, so no tap lands before the route changes.
  void _resolve(PickerResolution resolution) {
    state = ConventionPickerState(
      rows: state.rows,
      writingId: state.writingId,
      recovering: state.recovering,
      banner: state.banner,
      writesLocked: state.writesLocked,
      resolution: resolution,
    );
  }
}

final class _Lists {
  const new(this.rows, this.enrollments);

  final List<ConventionRow> rows;
  final List<ConventionEnrollment> enrollments;
}

/// The picker state. It ends when the screen leaves or the player scope
/// changes.
final NotifierProvider<ConventionPickerController, ConventionPickerState>
conventionPickerControllerProvider =
    NotifierProvider.autoDispose<
      ConventionPickerController,
      ConventionPickerState
    >(ConventionPickerController.new);
