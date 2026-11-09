import "package:flutter/material.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/conventions/convention_strings.dart";

/// The minimal home of the selected convention.
///
/// It shows only real server values. Gameplay controls join it when they
/// work.
class ConventionHomeScreen extends StatelessWidget {
  /// Creates the screen for [enrollment].
  const new({
    required this.enrollment,
    required this.refreshing,
    required this.refreshFailure,
    required this.apiAccess,
    required this.onChangeConvention,
    required this.onRefresh,
    required this.onManagePasskeys,
    required this.onSignOut,
    required this.onOpenAuthProof,
    super.key,
  });

  /// The selected enrollment.
  final ConventionEnrollment enrollment;

  /// Whether a silent reload is running.
  final bool refreshing;

  /// The failure of the last silent reload, or null.
  final ApiFailure? refreshFailure;

  /// Whether the API refused the token during the last silent reload.
  final bool apiAccess;

  /// Opens the picker.
  final VoidCallback onChangeConvention;

  /// Reads the server state again.
  final VoidCallback onRefresh;

  /// Opens the passkey screen.
  final VoidCallback onManagePasskeys;

  /// Signs out.
  final VoidCallback onSignOut;

  /// Opens the debug proof screen, or null outside debug builds.
  final VoidCallback? onOpenAuthProof;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final convention = enrollment.convention;
    return Scaffold(
      appBar: AppBar(title: const Text(ConventionStrings.appName)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(TokenSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.lg,
            children: [
              ?_banner(convention),
              Card(
                key: const Key("convention-home"),
                margin: EdgeInsets.zero,
                child: Padding(
                  padding: const EdgeInsets.all(TokenSpacing.lg),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    spacing: TokenSpacing.md,
                    children: [
                      Text(
                        convention.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.titleLarge,
                      ),
                      Text(
                        ConventionStrings.dates(context, convention),
                        style: textTheme.bodyMedium,
                      ),
                      Align(
                        alignment: AlignmentDirectional.centerStart,
                        child: StatusBadge(
                          tone: ConventionStrings.statusTone(convention.status),
                          label: ConventionStrings.statusLabel(
                            convention.status,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              TailTagButton(
                key: const Key("convention-change"),
                label: ConventionStrings.changeConvention,
                onPressed: onChangeConvention,
              ),
              TailTagButton(
                key: const Key("convention-refresh"),
                label: ConventionStrings.refresh,
                variant: TailTagButtonVariant.secondary,
                loading: refreshing,
                onPressed: onRefresh,
              ),
              TailTagButton(
                key: const Key("entry-manage-passkeys"),
                label: ConventionStrings.managePasskeys,
                variant: TailTagButtonVariant.secondary,
                onPressed: onManagePasskeys,
              ),
              TailTagButton(
                key: const Key("entry-sign-out"),
                label: ConventionStrings.signOut,
                variant: TailTagButtonVariant.secondary,
                onPressed: onSignOut,
              ),
              if (onOpenAuthProof != null)
                TailTagButton(
                  key: const Key("entry-auth-proof"),
                  label: ConventionStrings.authProof,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: onOpenAuthProof,
                ),
            ],
          ),
        ),
      ),
    );
  }

  /// One banner at a time. A reload problem replaces the inactive notice.
  /// The status badge still shows the real status.
  Widget? _banner(Convention convention) {
    final failure = refreshFailure;
    if (failure != null || apiAccess) {
      return StatusBanner(
        key: const Key("convention-home-banner"),
        tone: StatusTone.error,
        message: failure == null
            ? ConventionStrings.apiAccess
            : (genericErrorFor(failure) ?? GenericError.unknown).message,
        actionLabel: UiStrings.tryAgain,
        actionLoading: refreshing,
        onAction: onRefresh,
      );
    }
    if (convention.isOpen) {
      return null;
    }
    return const StatusBanner(
      key: Key("convention-home-banner"),
      tone: StatusTone.warning,
      message: ConventionStrings.inactive,
    );
  }
}
