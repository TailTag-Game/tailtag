import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_riverpod/misc.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/catches/catch_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// Where a scan stands.
enum ScanPhase {
  /// The camera looks for a TailTag.
  scanning,

  /// The preview read runs.
  previewing,

  /// The preview shows, and the player can confirm.
  preview,

  /// The submission runs.
  submitting,

  /// One outcome shows.
  result,
}

/// The outcome that the result screen shows (#511 AC15).
enum ScanResult {
  /// A new request waits for the owner.
  pending,

  /// Automatic approval made a catch.
  approved,

  /// A request already waits.
  alreadyPending,

  /// The suit is already in the collection.
  alreadyCaught,

  /// The neutral refusal, which also covers a block.
  unavailable,

  /// The player scanned their own suit.
  ownSuit,

  /// The player cannot catch at the convention.
  ineligible,

  /// The review window is closed, or the convention has no time zone.
  closed,

  /// A cooldown or the per-player limit applies.
  wait,

  /// A submission ended with no definite answer.
  unknown,

  /// The server has no catch flow.
  serviceOff,

  /// The server's selected convention differs from the home.
  conventionChanged,

  /// Any other failure, in [ScanState.failure].
  failed,
}

/// The results after which the home state must be read again.
const Set<ScanResult> reloadHomeResults = {
  ScanResult.ineligible,
  ScanResult.conventionChanged,
};

/// What the scanner screen shows. It never holds the payload.
@immutable
final class ScanState {
  /// Creates a state.
  const new({
    this.phase = ScanPhase.scanning,
    this.notATag = false,
    this.preview,
    this.result,
    this.request,
    this.waitSeconds = 0,
    this.failure,
  });

  /// Where the scan stands.
  final ScanPhase phase;

  /// Whether the last code was not a TailTag.
  final bool notATag;

  /// The previewed suit, kept for the result text.
  final CatchPreview? preview;

  /// The outcome, while [phase] is [ScanPhase.result].
  final ScanResult? result;

  /// The request that the submission returned, for the deadline text.
  final PlayerCatchRequest? request;

  /// The seconds left before "Try again" works after a 429.
  final int waitSeconds;

  /// The failure for [ScanResult.failed].
  final ApiFailure? failure;

  ScanState _copy({int? waitSeconds}) => ScanState(
    phase: phase,
    notATag: notATag,
    preview: preview,
    result: result,
    request: request,
    waitSeconds: waitSeconds ?? this.waitSeconds,
    failure: failure,
  );
}

/// The two server calls of a scan.
enum _Call { preview, submit }

/// Owns one scan for the selected convention [conventionId].
///
/// The payload lives in a private field only. "Scan again", closing the
/// scanner, and a new player scope drop it. A submission with no definite
/// answer is sent again only when the player asks, and the server returns
/// the existing request or catch for a repeat.
final class ScanController extends Notifier<ScanState> {
  /// Creates the controller for [conventionId].
  new(this.conventionId);

  /// The selected convention of the home.
  final int conventionId;

  TagPayload? _payload;
  String? _lastNotATag;
  _Call? _lastCall;
  Timer? _countdown;

  @override
  ScanState build() {
    ref
      ..watch(playerScopeProvider)
      ..onDispose(() {
        _countdown?.cancel();
        _payload = null;
      });
    _payload = null;
    _lastNotATag = null;
    _lastCall = null;
    _countdown?.cancel();
    return const ScanState();
  }

  /// Handles the raw text of a QR code that the camera read. It returns
  /// true when the text is a TailTag and the preview starts.
  bool read(String raw) {
    if (state.phase != ScanPhase.scanning) {
      return false;
    }
    final payload = TagPayload.parse(raw);
    if (payload == null) {
      // The same wrong code stays quiet until another code is read.
      if (raw != _lastNotATag) {
        _lastNotATag = raw;
        state = const ScanState(notATag: true);
      }
      return false;
    }
    _payload = payload;
    unawaited(_preview());
    return true;
  }

  /// Drops the payload and the outcome, and scans again.
  void scanAgain() {
    _countdown?.cancel();
    _payload = null;
    _lastNotATag = null;
    _lastCall = null;
    state = const ScanState();
  }

  /// Submits the previewed attempt.
  Future<void> confirm() async {
    if (state.phase != ScanPhase.preview) {
      return;
    }
    await _submit();
  }

  /// Repeats the call that failed, with the same payload. The player starts
  /// it, after an unknown outcome, a failure, or the end of a wait.
  Future<void> retry() async {
    if (state.phase != ScanPhase.result || state.waitSeconds > 0) {
      return;
    }
    switch (_lastCall) {
      case _Call.preview:
        await _preview();
      case _Call.submit:
        await _submit();
      case null:
        return;
    }
  }

  Future<void> _preview() async {
    final payload = _payload;
    if (payload == null) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive && _payload == payload;
    _lastCall = _Call.preview;
    state = const ScanState(phase: ScanPhase.previewing);
    try {
      final preview = await ref
          .read(catchRepositoryProvider)
          .preview(payload, cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      if (preview.conventionId != conventionId) {
        _payload = null;
        _show(ScanResult.conventionChanged);
        return;
      }
      state = ScanState(phase: ScanPhase.preview, preview: preview);
    } on ApiFailure catch (failure) {
      if (live()) {
        await _afterFailure(scope, failure, _Call.preview, live);
      }
    }
  }

  Future<void> _submit() async {
    final payload = _payload;
    if (payload == null) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive && _payload == payload;
    final preview = state.preview;
    _lastCall = _Call.submit;
    state = ScanState(phase: ScanPhase.submitting, preview: preview);
    try {
      final submission = await ref
          .read(catchRepositoryProvider)
          .submit(payload, cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      _show(switch (submission.outcome) {
        CatchSubmitOutcome.pending => ScanResult.pending,
        CatchSubmitOutcome.approved => ScanResult.approved,
        CatchSubmitOutcome.alreadyPending => ScanResult.alreadyPending,
        CatchSubmitOutcome.alreadyCaught => ScanResult.alreadyCaught,
      }, request: submission.request);
    } on ApiFailure catch (failure) {
      if (live()) {
        await _afterFailure(scope, failure, _Call.submit, live);
      }
    }
  }

  Future<void> _afterFailure(
    PlayerScope scope,
    ApiFailure failure,
    _Call call,
    bool Function() live,
  ) async {
    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiNotFoundFailure(code: null):
        _show(ScanResult.serviceOff);
      case ApiNotFoundFailure():
        _show(ScanResult.unavailable);
      case ApiConflictFailure(code: "self_catch_not_allowed"):
        _show(ScanResult.ownSuit);
      case ApiConflictFailure(code: "catch_requests_unavailable"):
        _show(ScanResult.closed);
      case ApiPermissionFailure():
        _show(ScanResult.ineligible);
      case ApiRateLimitedFailure(:final retryAfterSeconds):
        _startWait(retryAfterSeconds ?? _defaultWait);
      // A 5xx can come from a proxy after the server committed the
      // submission, so it is an unknown outcome too.
      case ApiConnectivityFailure() || ApiTimeoutFailure() || ApiServerFailure()
          when call == _Call.submit:
        _show(ScanResult.unknown);
      case ApiUnauthenticatedFailure():
        final session = ref.read(authSessionProvider);
        await session.recheckSession();
        // If the session ended, the entry stage moves and this scope closes.
        if (live()) {
          _show(ScanResult.failed, failure: failure);
        }
      case ApiFailure():
        _show(ScanResult.failed, failure: failure);
    }
  }

  void _show(
    ScanResult result, {
    PlayerCatchRequest? request,
    ApiFailure? failure,
  }) {
    state = ScanState(
      phase: ScanPhase.result,
      preview: state.preview,
      result: result,
      request: request,
      failure: failure,
    );
  }

  void _startWait(int seconds) {
    _countdown?.cancel();
    state = ScanState(
      phase: ScanPhase.result,
      preview: state.preview,
      result: ScanResult.wait,
      waitSeconds: seconds,
    );
    _countdown = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!ref.mounted) {
        timer.cancel();
        return;
      }
      final left = state.waitSeconds - 1;
      state = state._copy(waitSeconds: left < 0 ? 0 : left);
      if (left <= 0) {
        timer.cancel();
      }
    });
  }

  /// The wait when a 429 carried no usable wait.
  static const int _defaultWait = 10;
}

/// The scan of the selected convention. It ends when the scanner closes or
/// the player scope changes, which drops the payload.
final NotifierProviderFamily<ScanController, ScanState, int>
scanControllerProvider = NotifierProvider.autoDispose
    .family<ScanController, ScanState, int>(ScanController.new);
