import "dart:async";
import "dart:ui";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_riverpod/misc.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/fursuits/tag_share.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The message at the top of the tag screen.
enum TagBanner {
  /// The server has no tag operations, for example with the catch request
  /// gate off.
  unavailable,

  /// TailTag staff disabled the suit.
  suitDisabled,

  /// The API refused the token while the native session stayed active.
  apiAccess,

  /// A read failed, in [TagScreenState.failure].
  readFailed,

  /// After a lost response, the tag has a new version.
  changed,

  /// After a lost response, the tag has the version that was sent.
  notReplaced,

  /// The server refused the replacement because the tag changed.
  conflict,

  /// The read after a lost response or a conflict failed.
  checkFailed,

  /// The server refused the replacement, in [TagScreenState.failure].
  replaceFailed,

  /// The tag image could not be made or shared.
  shareFailed,
}

/// What the tag screen shows. It lives in memory only.
@immutable
final class TagScreenState {
  /// Creates a state.
  const new({
    this.tag,
    this.reading = false,
    this.replacing = false,
    this.sharing = false,
    this.banner,
    this.failure,
  });

  /// The tag, or null before the first successful read. It is also null
  /// while an unconfirmed replacement is checked, because the shown QR code
  /// can already be dead.
  final FursuitTag? tag;

  /// Whether a read runs.
  final bool reading;

  /// Whether a replacement runs.
  final bool replacing;

  /// Whether the tag image is being made or shared.
  final bool sharing;

  /// The message, or null.
  final TagBanner? banner;

  /// The failure for [TagBanner.readFailed] and [TagBanner.replaceFailed].
  final ApiFailure? failure;

  TagScreenState _copy({
    FursuitTag? tag,
    bool? reading,
    bool? replacing,
    bool? sharing,
    TagBanner? banner,
    ApiFailure? failure,
    bool clearBanner = false,
    bool clearTag = false,
  }) => TagScreenState(
    tag: clearTag ? null : tag ?? this.tag,
    reading: reading ?? this.reading,
    replacing: replacing ?? this.replacing,
    sharing: sharing ?? this.sharing,
    banner: clearBanner ? null : banner ?? this.banner,
    failure: clearBanner ? null : failure ?? this.failure,
  );
}

/// The result of a replacement that the screen waits for.
enum TagReplaceResult {
  /// The server confirmed the new tag.
  done,

  /// The app does not know the result, or the tag changed. It was not sent
  /// again, and the tag is being read.
  checking,

  /// The server refused it, or the screen closed. The banner says why.
  failed,
}

/// The banners that a successful plain read makes stale.
const Set<TagBanner> _readBanners = {
  TagBanner.unavailable,
  TagBanner.suitDisabled,
  TagBanner.apiAccess,
  TagBanner.readFailed,
  TagBanner.checkFailed,
};

/// Owns the tag of one suit while its tag screen shows.
///
/// A new player scope rebuilds it, which drops the payload. A replacement
/// with no definite answer is never sent again. The controller reads the
/// tag instead, and the first successful read compares the version.
final class TagController extends Notifier<TagScreenState> {
  /// Creates the controller for suit [fursuitId].
  new(this.fursuitId);

  /// The suit's server ID.
  final int fursuitId;

  /// The ID of the latest read. A later read or a replacement makes an
  /// earlier read stale.
  int _lastRead = 0;

  /// The version that an unconfirmed replacement sent, and whether the
  /// server answered with a conflict. The next successful read resolves it.
  ({int sent, bool conflict})? _check;

  @override
  TagScreenState build() {
    ref
      ..watch(playerScopeProvider)
      ..listen(foregroundSignalProvider, (_, _) => unawaited(read()));
    _lastRead++;
    _check = null;
    // The screen just opened, so a tag image from an earlier share goes.
    unawaited(ref.read(tagShareProvider).clear());
    return const TagScreenState(reading: true);
  }

  /// Reads the tag. The screen calls it when it opens, on pull to refresh,
  /// and from "Try again". It also resolves an unconfirmed replacement.
  Future<void> read() async {
    if (!ref.mounted || state.replacing) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    state = state._copy(reading: true);
    try {
      final tag = await ref
          .read(fursuitRepositoryProvider)
          .readTag(fursuitId, cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      state = TagScreenState(
        tag: tag,
        sharing: state.sharing,
        banner: _bannerAfterRead(tag),
      );
    } on ApiFailure catch (failure) {
      if (live()) {
        await _afterFailedRead(scope, failure, live);
      }
    }
  }

  /// Replaces the tag, or gets a new one after a revocation. It sends the
  /// version that the screen shows.
  Future<TagReplaceResult> replace() async {
    final tag = state.tag;
    if (tag == null || state.replacing) {
      return TagReplaceResult.failed;
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive;
    // A read that runs now can carry the tag from before the replacement,
    // so its result is dropped.
    _lastRead++;
    _check = null;
    state = state._copy(reading: false, replacing: true, clearBanner: true);
    try {
      final next = await ref
          .read(fursuitRepositoryProvider)
          .replaceTag(
            fursuitId,
            expectedVersion: tag.version,
            cancellation: scope.cancellation,
          );
      if (!live()) {
        return TagReplaceResult.failed;
      }
      state = TagScreenState(tag: next);
      return TagReplaceResult.done;
    } on ApiFailure catch (failure) {
      if (!live()) {
        return TagReplaceResult.failed;
      }
      state = state._copy(replacing: false);
      return await _afterFailedReplace(scope, failure, tag.version);
    }
  }

  /// Makes the tag image with [render] and opens the share sheet at
  /// [origin].
  Future<void> share(Future<TagImage> Function() render, {Rect? origin}) async {
    final tag = state.tag;
    if (tag?.state != TagState.current || state.sharing) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive;
    // The image shows the tag from before the render. A read that changed
    // the tag meanwhile makes it outdated.
    bool current() =>
        live() &&
        state.tag?.state == TagState.current &&
        state.tag?.version == tag?.version;
    state = state._copy(sharing: true, clearBanner: true);
    try {
      final image = await render();
      // A player who signed out, or a tag that changed while the image
      // rendered, shares nothing.
      if (!current()) {
        if (live()) {
          state = state._copy(sharing: false);
        }
        return;
      }
      await ref
          .read(tagShareProvider)
          .share(image, origin: origin, isCurrent: current);
      if (live()) {
        state = state._copy(sharing: false);
      }
    } on Object {
      // The image holds the QR code, so the error is never logged.
      if (live()) {
        state = state._copy(sharing: false, banner: TagBanner.shareFailed);
      }
    }
  }

  TagBanner? _bannerAfterRead(FursuitTag tag) {
    final check = _check;
    _check = null;
    if (check == null) {
      final banner = state.banner;
      return _readBanners.contains(banner) ? null : banner;
    }
    if (tag.state == TagState.revoked) {
      return null;
    }
    if (check.conflict) {
      return TagBanner.conflict;
    }
    return tag.version > check.sent ? TagBanner.changed : TagBanner.notReplaced;
  }

  Future<TagReplaceResult> _afterFailedReplace(
    PlayerScope scope,
    ApiFailure failure,
    int sent,
  ) async {
    void refused(TagBanner banner, [ApiFailure? cause]) {
      state = state._copy(banner: banner, failure: cause);
    }

    switch (failure) {
      case ApiCancelledFailure():
        return TagReplaceResult.failed;
      // A 5xx can come from a proxy after the server committed the
      // replacement, so it is an unknown outcome too (AC19, amended).
      case ApiConnectivityFailure() ||
          ApiTimeoutFailure() ||
          ApiServerFailure():
        _check = (sent: sent, conflict: false);
        state = state._copy(clearTag: true);
        unawaited(read());
        return TagReplaceResult.checking;
      case ApiConflictFailure(code: "tag_version_conflict"):
        _check = (sent: sent, conflict: true);
        state = state._copy(clearTag: true);
        unawaited(read());
        return TagReplaceResult.checking;
      case ApiConflictFailure(code: "fursuit_disabled"):
        refused(TagBanner.suitDisabled);
      case ApiPermissionFailure():
        refused(TagBanner.replaceFailed, failure);
      case ApiNotFoundFailure():
        refused(TagBanner.unavailable);
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && ref.mounted) {
          refused(TagBanner.apiAccess);
        }
      case ApiFailure():
        refused(TagBanner.replaceFailed, failure);
    }
    return TagReplaceResult.failed;
  }

  Future<void> _afterFailedRead(
    PlayerScope scope,
    ApiFailure failure,
    bool Function() live,
  ) async {
    void show(TagBanner banner, [ApiFailure? cause]) {
      state = state._copy(reading: false, banner: banner, failure: cause);
    }

    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope) && live()) {
          show(TagBanner.apiAccess);
        } else if (live()) {
          state = state._copy(reading: false);
        }
      // Any other failure of the read after an unconfirmed replacement
      // offers the read-only retry (AC19).
      case ApiFailure() when _check != null:
        show(TagBanner.checkFailed);
      case ApiNotFoundFailure():
        show(TagBanner.unavailable);
      case ApiConflictFailure(code: "fursuit_disabled"):
        show(TagBanner.suitDisabled);
      case ApiFailure():
        show(TagBanner.readFailed, failure);
    }
  }

  Future<bool> _sessionStaysActive(PlayerScope scope) async {
    final session = ref.read(authSessionProvider);
    await session.recheckSession();
    return scope.isActive && session.state is AuthSignedIn;
  }
}

/// The tag of one suit. It ends when the tag screen closes or the player
/// scope changes.
final NotifierProviderFamily<TagController, TagScreenState, int>
tagControllerProvider = NotifierProvider.autoDispose
    .family<TagController, TagScreenState, int>(TagController.new);
