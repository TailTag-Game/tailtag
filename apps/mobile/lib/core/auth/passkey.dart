import "package:flutter/foundation.dart";

/// Whether this device and the Clerk instance allow passkeys now.
enum PasskeyAvailability {
  /// The device supports passkeys, and Clerk has passkey sign-in on.
  available,

  /// The device cannot use passkeys, or Clerk has passkey sign-in off.
  unavailable,
}

/// One verified passkey of the signed-in player.
///
/// [id] exists only to remove the passkey. It never enters a log, an error,
/// analytics, or screen text.
@immutable
final class PasskeyInfo {
  /// Creates the item.
  const new({
    required this.id,
    required this.name,
    required this.createdAt,
    this.lastUsedAt,
  });

  /// The opaque identifier that `removePasskey` takes.
  final String id;

  /// The name that Clerk gave the passkey.
  final String name;

  /// When the player added the passkey.
  final DateTime createdAt;

  /// When the player last signed in with it, or null if never.
  final DateTime? lastUsedAt;

  @override
  bool operator ==(Object other) =>
      other is PasskeyInfo &&
      other.id == id &&
      other.name == name &&
      other.createdAt == createdAt &&
      other.lastUsedAt == lastUsedAt;

  @override
  int get hashCode => Object.hash(id, name, createdAt, lastUsedAt);

  /// Leaves out [id], so a printed item cannot leak it.
  @override
  String toString() => "PasskeyInfo($name)";
}
