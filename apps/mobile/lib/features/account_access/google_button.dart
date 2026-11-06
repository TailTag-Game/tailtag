import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";

/// The colors of the Google button in one theme.
///
/// The values come from Google's sign-in branding guidelines
/// (https://developers.google.com/identity/branding-guidelines). They are
/// Google's brand colors, so they are not TailTag tokens.
enum GoogleButtonColors {
  /// The light theme.
  light(
    fill: Color(0xFFFFFFFF),
    stroke: Color(0xFF747775),
    text: Color(0xFF1F1F1F),
    logoAsset: "assets/images/google/google_g_light.png",
  ),

  /// The dark theme.
  dark(
    fill: Color(0xFF131314),
    stroke: Color(0xFF8E918F),
    text: Color(0xFFE3E3E3),
    logoAsset: "assets/images/google/google_g_dark.png",
  );

  new({
    required this.fill,
    required this.stroke,
    required this.text,
    required this.logoAsset,
  });

  /// The colors for [brightness].
  static GoogleButtonColors of(Brightness brightness) =>
      brightness == Brightness.dark ? dark : light;

  /// The button fill.
  final Color fill;

  /// The 1 px border.
  final Color stroke;

  /// The label color.
  final Color text;

  /// The standard color "G", cut from Google's own button on [fill].
  final String logoAsset;
}

/// The padding around the "G" and the label, by platform, from Google's
/// branding guidelines: (before the logo, between logo and label, after the
/// label).
({double start, double gap, double end}) googleButtonPadding(
  TargetPlatform platform,
) => switch (platform) {
  TargetPlatform.iOS || TargetPlatform.macOS => (start: 16, gap: 12, end: 16),
  _ => (start: 12, gap: 10, end: 12),
};

/// The side of the Google "G" logo.
const double googleLogoSize = 20;

/// The "Continue with Google" button.
///
/// It follows Google's branding guidelines: the standard color "G", the
/// approved text, Google's fill, border, and label colors, and Google's
/// padding. It keeps the TailTag pill shape and the `size.minTarget`
/// height. While [loading] is true, it is disabled. After
/// [loadingIndicatorDelay], a spinner replaces the logo and the label keeps
/// its place.
class GoogleButton extends StatelessWidget {
  /// Creates the button.
  const new({
    required this.label,
    required this.onPressed,
    this.loading = false,
    super.key,
  });

  /// The approved text, "Continue with Google".
  final String label;

  /// Called on tap. When null, the button is disabled.
  final VoidCallback? onPressed;

  /// Whether the Google attempt is running.
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = GoogleButtonColors.of(theme.brightness);
    final padding = googleButtonPadding(theme.platform);
    final logo = Image.asset(
      colors.logoAsset,
      width: googleLogoSize,
      height: googleLogoSize,
      excludeFromSemantics: true,
    );
    return Semantics(
      value: loading ? UiStrings.loading : null,
      child: OutlinedButton(
        onPressed: loading ? null : onPressed,
        style: OutlinedButton.styleFrom(
          backgroundColor: colors.fill,
          foregroundColor: colors.text,
          // While loading, the disabled colors stay the normal colors.
          disabledBackgroundColor: loading ? colors.fill : null,
          disabledForegroundColor: loading ? colors.text : null,
          side: BorderSide(color: colors.stroke),
          minimumSize: const Size(TokenSize.minTarget, TokenSize.minTarget),
          padding: EdgeInsetsDirectional.only(
            start: padding.start,
            end: padding.end,
          ),
          shape: const StadiumBorder(),
          textStyle: TokenTypography.titleMedium,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (loading)
              DelayedVisibility(
                replacement: logo,
                child: SizedBox.square(
                  dimension: googleLogoSize,
                  // Stroke widths have no token. 2 suits a 20 px spinner.
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: colors.text,
                  ),
                ),
              )
            else
              logo,
            SizedBox(width: padding.gap),
            Flexible(child: Text(label, textAlign: TextAlign.center)),
          ],
        ),
      ),
    );
  }
}
