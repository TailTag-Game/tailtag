/// The signed-in player's TailTag identity.
final class CurrentUser {
  /// Creates a user with the given application [id].
  const new(this.id);

  /// The TailTag-owned application user id, separate from the Clerk identity.
  final int id;
}
