/// The signed-in player's TailTag profile, as the server reports it.
///
/// Every value comes from the server. The app derives no completion or
/// eligibility state of its own.
final class PlayerProfile {
  /// Creates a profile from server values.
  const new({
    required this.onboardingComplete,
    required this.isEnabled,
    this.handle,
    this.displayName,
    this.avatarUrl,
  });

  /// The unique handle, or null before onboarding.
  final String? handle;

  /// The display name, or null before onboarding.
  final String? displayName;

  /// The avatar address, or null when the player has no avatar.
  final Uri? avatarUrl;

  /// Whether the server reports that onboarding is complete.
  final bool onboardingComplete;

  /// Whether the server allows this player to take part.
  final bool isEnabled;
}
