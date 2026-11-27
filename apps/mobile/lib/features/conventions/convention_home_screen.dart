import "dart:async";

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
import "package:tailtag_mobile/features/catches/catch_strings.dart";
import "package:tailtag_mobile/features/conventions/convention_strings.dart";

/// The gameplay home of the selected convention.
class ConventionHomeScreen extends StatelessWidget {
  /// Creates the screen for [enrollment].
  const new({
    required this.enrollment,
    required this.refreshing,
    required this.refreshFailure,
    required this.apiAccess,
    required this.onChangeConvention,
    required this.onRefresh,
    required this.onScan,
    required this.onShowMyTag,
    required this.reviewEntry,
    required this.accountMenu,
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
  final Future<void> Function() onRefresh;

  /// Opens the scanner.
  final VoidCallback onScan;

  /// Opens the suit selector sheet to show a TailTag.
  final VoidCallback onShowMyTag;

  /// The card that opens owner catch review. It shows only while requests
  /// wait (#512 AC3).
  final Widget reviewEntry;

  /// The account menu action in the top app bar.
  final Widget accountMenu;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final convention = enrollment.convention;
    return Scaffold(
      appBar: AppBar(
        title: const Text(ConventionStrings.appName),
        actions: [accountMenu],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: onRefresh,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
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
                    padding: const EdgeInsets.fromLTRB(
                      TokenSpacing.lg,
                      TokenSpacing.lg,
                      TokenSpacing.lg,
                      TokenSpacing.sm,
                    ),
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
                            tone: ConventionStrings.statusTone(
                              convention.status,
                            ),
                            label: ConventionStrings.statusLabel(
                              convention.status,
                            ),
                          ),
                        ),
                        const Divider(height: 1),
                        Row(
                          children: [
                            Expanded(
                              child: Align(
                                alignment: AlignmentDirectional.centerStart,
                                child: TailTagButton(
                                  key: const Key("convention-change"),
                                  label: ConventionStrings.changeConvention,
                                  variant: TailTagButtonVariant.secondaryText,
                                  onPressed: onChangeConvention,
                                ),
                              ),
                            ),
                            IconButton(
                              key: const Key("convention-refresh"),
                              tooltip: ConventionStrings.refresh,
                              onPressed: refreshing
                                  ? null
                                  : () => unawaited(onRefresh()),
                              icon: refreshing
                                  ? const SizedBox.square(
                                      dimension: TokenSize.iconSmall,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.refresh_outlined),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                // Gameplay actions stay together with zero empty gap when the
                // review card is hidden.
                Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TailTagButton(
                      key: const Key("convention-scan"),
                      label: CatchStrings.scanTag,
                      icon: Icons.qr_code_scanner,
                      onPressed: convention.catchingOpen ? onScan : null,
                    ),
                    if (!convention.catchingOpen)
                      Padding(
                        padding: const EdgeInsets.only(top: TokenSpacing.sm),
                        child: Text(
                          CatchStrings.scanClosed(convention.name),
                          key: const Key("convention-scan-closed"),
                          style: textTheme.bodyMedium,
                        ),
                      ),
                    const SizedBox(height: TokenSpacing.md),
                    TailTagButton(
                      key: const Key("convention-show-tag"),
                      label: ConventionStrings.showMyTag,
                      icon: Icons.qr_code_2,
                      variant: TailTagButtonVariant.secondary,
                      onPressed: onShowMyTag,
                    ),
                    reviewEntry,
                  ],
                ),
              ],
            ),
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
        onAction: () => unawaited(onRefresh()),
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
