import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";

/// The passkey change that is running.
enum PasskeyChange {
  /// Adding a passkey.
  add,

  /// Removing a passkey.
  remove,
}

/// A confirmed outcome that the screen reports.
enum PasskeyNotice {
  /// The fresh list shows the new passkey.
  added,

  /// The fresh list no longer shows the removed passkey.
  removed,

  /// The outcome of a change is not known. The fresh list is the truth.
  unconfirmed,
}

/// What the passkey screen shows. It lives in memory only.
@immutable
final class PasskeyScreenState {
  /// Creates a state.
  const new({
    this.availability,
    this.passkeys,
    this.reading = false,
    this.readFailure,
    this.change,
    this.changeFailure,
    this.notice,
    this.writesLocked = false,
  });

  /// Whether passkeys work here, or null while it is unknown.
  final PasskeyAvailability? availability;

  /// The last list that Clerk confirmed, or null before the first read.
  final List<PasskeyInfo>? passkeys;

  /// Whether a list read is running.
  final bool reading;

  /// The failure of the last list read, or null.
  final AuthFailure? readFailure;

  /// The running change, or null.
  final PasskeyChange? change;

  /// The failure of the last change, or null. An ambiguous failure is not
  /// kept here: [notice] reports it after a fresh read.
  final AuthFailure? changeFailure;

  /// The confirmed outcome of the last change, or null.
  final PasskeyNotice? notice;

  /// Whether changes wait for a successful read after an ambiguous change.
  final bool writesLocked;

  /// Whether passkeys can be added on this device.
  bool get canAdd => availability == PasskeyAvailability.available;

  /// Whether a change can start now. A failed read leaves a list that can
  /// be stale, so changes wait for a successful read.
  bool get canChange =>
      change == null &&
      !reading &&
      !writesLocked &&
      readFailure == null &&
      passkeys != null;

  /// Whether the screen can close now. A change and the read after it
  /// block closing. A failed read does not: closing runs a fresh bootstrap,
  /// and the screen reads the list again when it opens.
  bool get canClose => change == null;

  PasskeyScreenState _copy({
    PasskeyAvailability? availability,
    List<PasskeyInfo>? passkeys,
    bool? reading,
    AuthFailure? readFailure,
    PasskeyChange? change,
    AuthFailure? changeFailure,
    PasskeyNotice? notice,
    bool? writesLocked,
  }) => PasskeyScreenState(
    availability: availability ?? this.availability,
    passkeys: passkeys ?? this.passkeys,
    reading: reading ?? this.reading,
    readFailure: readFailure,
    change: change,
    changeFailure: changeFailure,
    notice: notice,
    writesLocked: writesLocked ?? this.writesLocked,
  );
}

/// Runs the passkey screen over the auth session.
///
/// It starts one call at a time and only on an explicit action, except the
/// first read. It never repeats a change. After a change that ends in a
/// connectivity or unexpected failure, it reads the list again and allows
/// no other change until a read succeeds.
final class PasskeyController extends Notifier<PasskeyScreenState> {
  @override
  PasskeyScreenState build() {
    scheduleMicrotask(() => unawaited(_open()));
    return const PasskeyScreenState(reading: true);
  }

  Future<void> _open() async {
    if (!ref.mounted) {
      return;
    }
    final availability = await ref
        .read(authSessionProvider)
        .passkeyAvailability();
    if (!ref.mounted) {
      return;
    }
    state = state._copy(availability: availability, reading: true);
    await _read();
  }

  /// Reads the list again after a failed read.
  Future<void> retryRead() async {
    if (state.reading || state.change != null || state.readFailure == null) {
      return;
    }
    // After an ambiguous change, the first good read still reports that the
    // outcome is not known.
    final afterAmbiguousChange = state.writesLocked;
    state = state._copy(reading: true);
    await _read(
      notice: afterAmbiguousChange ? (_) => PasskeyNotice.unconfirmed : null,
    );
  }

  /// Adds a passkey. Success shows only after a fresh read lists it.
  Future<void> add() async {
    if (!state.canChange || !state.canAdd) {
      return;
    }
    final before = {for (final passkey in state.passkeys!) passkey.id};
    state = state._copy(change: PasskeyChange.add);
    final AuthAttemptResult result;
    try {
      result = await ref.read(authSessionProvider).createPasskey();
    } on AuthFailure catch (failure) {
      await _afterFailedChange(failure);
      return;
    }
    if (!ref.mounted) {
      return;
    }
    switch (result) {
      case AuthAttemptCancelled():
        // The list is unchanged. Clerk keeps no verified passkey.
        state = state._copy();
      case AuthAttemptCompleted() || AuthAttemptNeedsEmailCode():
        await _read(
          change: PasskeyChange.add,
          notice: (passkeys) =>
              passkeys.any((passkey) => !before.contains(passkey.id))
              ? PasskeyNotice.added
              : PasskeyNotice.unconfirmed,
        );
    }
  }

  /// Removes [passkey] after the player confirmed it. Success shows only
  /// after a fresh read no longer lists it.
  Future<void> remove(PasskeyInfo passkey) async {
    if (!state.canChange) {
      return;
    }
    state = state._copy(change: PasskeyChange.remove);
    try {
      await ref.read(authSessionProvider).removePasskey(passkey.id);
    } on AuthFailure catch (failure) {
      await _afterFailedChange(failure);
      return;
    }
    if (!ref.mounted) {
      return;
    }
    await _read(
      change: PasskeyChange.remove,
      notice: (passkeys) => passkeys.any((item) => item.id == passkey.id)
          ? PasskeyNotice.unconfirmed
          : PasskeyNotice.removed,
    );
  }

  /// A connectivity or unexpected failure leaves the outcome unknown, so
  /// the screen locks changes and reads the list. Every other failure is a
  /// clear refusal with nothing changed.
  Future<void> _afterFailedChange(AuthFailure failure) async {
    if (!ref.mounted) {
      return;
    }
    final change = state.change;
    switch (failure) {
      case AuthConnectivityFailure() || AuthUnexpectedFailure():
        state = state._copy(change: change, writesLocked: true);
        await _read(change: change, notice: (_) => PasskeyNotice.unconfirmed);
      default:
        state = state._copy(changeFailure: failure);
    }
  }

  /// Reads the list. On success it unlocks changes and shows [notice] for
  /// the fresh list. On failure it keeps the lock and the last list.
  Future<void> _read({
    PasskeyChange? change,
    PasskeyNotice Function(List<PasskeyInfo> passkeys)? notice,
  }) async {
    state = state._copy(change: change, reading: true);
    final List<PasskeyInfo> passkeys;
    try {
      passkeys = await ref.read(authSessionProvider).listPasskeys();
    } on AuthFailure catch (failure) {
      if (ref.mounted) {
        state = state._copy(reading: false, readFailure: failure);
      }
      return;
    }
    if (ref.mounted) {
      state = state._copy(
        passkeys: passkeys,
        reading: false,
        notice: notice?.call(passkeys),
        writesLocked: false,
      );
    }
  }
}

/// The passkey screen state. It ends when the screen leaves.
final NotifierProvider<PasskeyController, PasskeyScreenState>
passkeyControllerProvider =
    NotifierProvider.autoDispose<PasskeyController, PasskeyScreenState>(
      PasskeyController.new,
    );
