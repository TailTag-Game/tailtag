import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";
import "package:tailtag_mobile/features/fursuits/suit_status.dart";
import "package:tailtag_mobile/features/fursuits/suits_controller.dart";

/// The badge of [badge].
StatusBadge suitBadge(SuitBadge badge, {Key? key}) => switch (badge) {
  SuitBadge.notParticipating => StatusBadge(
    key: key,
    tone: StatusTone.neutral,
    label: FursuitStrings.badgeNotParticipating,
  ),
  SuitBadge.cantParticipate => StatusBadge(
    key: key,
    tone: StatusTone.warning,
    label: FursuitStrings.badgeCantParticipate,
  ),
  SuitBadge.participating => StatusBadge(
    key: key,
    tone: StatusTone.neutral,
    label: FursuitStrings.badgeParticipating,
  ),
  SuitBadge.catchable => StatusBadge(
    key: key,
    tone: StatusTone.success,
    label: FursuitStrings.badgeCatchable,
  ),
};

/// The text of [reason].
String disabledReasonText(DisabledReason reason) => switch (reason) {
  DisabledReason.suitDisabled => FursuitStrings.suitDisabled,
  DisabledReason.conventionClosed => FursuitStrings.conventionClosed,
  DisabledReason.participateFirst => FursuitStrings.participateFirst,
  DisabledReason.cannotParticipate => FursuitStrings.cannotParticipate,
};

/// The one banner of a suit screen, or null. A read failure replaces any
/// other banner.
Widget? suitsBanner(SuitsState state, VoidCallback onTryAgain) {
  final failure = state.readFailure;
  if (failure != null) {
    return StatusBanner(
      key: const Key("suits-banner"),
      tone: StatusTone.error,
      message: (genericErrorFor(failure) ?? GenericError.unknown).message,
      actionLabel: UiStrings.tryAgain,
      actionLoading: state.reading,
      onAction: onTryAgain,
    );
  }
  final banner = state.banner;
  if (banner == null) {
    return null;
  }
  final (tone, message) = switch (banner) {
    SuitsBanner.unknownOutcome => (
      StatusTone.warning,
      FursuitStrings.writeUnknownOutcome,
    ),
    SuitsBanner.apiAccess => (StatusTone.error, FursuitStrings.apiAccess),
    SuitsBanner.notEligible => (StatusTone.error, FursuitStrings.notEligible),
    SuitsBanner.refused => (
      StatusTone.error,
      state.serverMessage ?? GenericError.unknown.message,
    ),
    SuitsBanner.writeFailed => (
      StatusTone.error,
      (switch (state.writeFailure) {
                null => null,
                final failure => genericErrorFor(failure),
              } ??
              GenericError.unknown)
          .message,
    ),
  };
  return StatusBanner(
    key: const Key("suits-banner"),
    tone: tone,
    message: message,
    actionLabel: UiStrings.tryAgain,
    actionLoading: state.reading,
    onAction: onTryAgain,
  );
}

/// The screen loading indicator, after the loading delay.
class SuitsLoading extends StatelessWidget {
  /// Creates the indicator.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return const DelayedVisibility(
      child: Padding(
        padding: EdgeInsets.all(TokenSpacing.xl),
        child: Center(
          child: CircularProgressIndicator(semanticsLabel: UiStrings.loading),
        ),
      ),
    );
  }
}

/// The subtitle of a switch row: "Updating" with a spinner after the
/// loading delay while [pending], else [text].
Widget switchSubtitle({required bool pending, required String text}) {
  final subtitle = Text(text);
  if (!pending) {
    return subtitle;
  }
  return DelayedVisibility(
    replacement: subtitle,
    child: const Row(
      children: [
        SizedBox.square(
          dimension: TokenSize.iconSmall,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        SizedBox(width: TokenSpacing.sm),
        Flexible(child: Text(UiStrings.updating)),
      ],
    ),
  );
}
