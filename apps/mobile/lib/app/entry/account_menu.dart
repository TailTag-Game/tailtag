import "dart:async";

import "package:flutter/material.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/features/conventions/convention_strings.dart";

/// The top app bar trigger that opens the account actions sheet.
///
/// Shows the player's avatar when [profile] carries identity details, or a
/// neutral account icon before onboarding or during recovery.
class AccountMenuButton extends StatelessWidget {
  /// Creates the button.
  const new({
    required this.onManagePasskeys,
    required this.onSignOut,
    this.profile,
    this.onOpenAuthProof,
    super.key,
  });

  /// The player's loaded profile, or null when unavailable.
  final PlayerProfile? profile;

  /// Opens passkey management, or null when leaving the screen is disabled.
  final VoidCallback? onManagePasskeys;

  /// Signs out.
  final VoidCallback onSignOut;

  /// Opens the debug proof screen in debug builds, or null.
  final VoidCallback? onOpenAuthProof;

  bool get _hasIdentity {
    final current = profile;
    if (current == null) {
      return false;
    }
    return (current.displayName?.trim().isNotEmpty ?? false) ||
        (current.handle?.trim().isNotEmpty ?? false) ||
        current.avatarUrl != null;
  }

  Future<void> _openSheet(BuildContext context) async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (sheetContext) => _AccountSheet(
        profile: _hasIdentity ? profile : null,
        onManagePasskeys: onManagePasskeys == null
            ? null
            : () {
                Navigator.of(sheetContext).pop();
                onManagePasskeys!();
              },
        onSignOut: () {
          Navigator.of(sheetContext).pop();
          onSignOut();
        },
        onOpenAuthProof: onOpenAuthProof == null
            ? null
            : () {
                Navigator.of(sheetContext).pop();
                onOpenAuthProof!();
              },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final current = profile;
    if (_hasIdentity && current != null) {
      return IconButton(
        key: const Key("account-menu"),
        tooltip: EntryStrings.account,
        padding: const EdgeInsets.all(TokenSpacing.xs),
        constraints: const BoxConstraints.tightFor(
          width: TokenSize.minTarget,
          height: TokenSize.minTarget,
        ),
        onPressed: () => unawaited(_openSheet(context)),
        icon: TailTagAvatar(
          name: current.displayName ?? current.handle ?? "",
          kind: AvatarKind.player,
          imageUrl: current.avatarUrl?.toString(),
        ),
      );
    }
    return IconButton(
      key: const Key("account-menu"),
      tooltip: EntryStrings.account,
      icon: const Icon(Icons.account_circle_outlined),
      onPressed: () => unawaited(_openSheet(context)),
    );
  }
}

class _AccountSheet extends StatelessWidget {
  const new({
    required this.profile,
    required this.onManagePasskeys,
    required this.onSignOut,
    required this.onOpenAuthProof,
  });

  final PlayerProfile? profile;
  final VoidCallback? onManagePasskeys;
  final VoidCallback onSignOut;
  final VoidCallback? onOpenAuthProof;

  @override
  Widget build(BuildContext context) {
    final current = profile;
    final displayName = current?.displayName?.trim();
    final handle = current?.handle?.trim();
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(
          TokenSpacing.sm,
          0,
          TokenSpacing.sm,
          TokenSpacing.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (current != null) ...[
              ListTile(
                key: const Key("account-sheet-identity"),
                leading: TailTagAvatar(
                  name: displayName ?? handle ?? "",
                  kind: AvatarKind.player,
                  imageUrl: current.avatarUrl?.toString(),
                ),
                title: Text(
                  displayName != null && displayName.isNotEmpty
                      ? displayName
                      : "@${handle ?? ""}",
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle:
                    displayName != null &&
                        displayName.isNotEmpty &&
                        handle != null &&
                        handle.isNotEmpty
                    ? Text("@$handle")
                    : null,
              ),
              const Divider(height: TokenSpacing.md),
            ],
            ListTile(
              key: const Key("entry-manage-passkeys"),
              leading: const Icon(Icons.key_outlined),
              title: const Text(EntryStrings.managePasskeys),
              enabled: onManagePasskeys != null,
              onTap: onManagePasskeys,
            ),
            ListTile(
              key: const Key("entry-sign-out"),
              leading: const Icon(Icons.logout_outlined),
              title: const Text(EntryStrings.signOut),
              onTap: onSignOut,
            ),
            if (onOpenAuthProof != null) ...[
              const Divider(height: TokenSpacing.md),
              ListTile(
                key: const Key("entry-auth-proof"),
                leading: const Icon(Icons.bug_report_outlined),
                title: const Text(ConventionStrings.authProof),
                onTap: onOpenAuthProof,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
