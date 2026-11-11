import "dart:math" as math;

import "package:flutter/material.dart";
import "package:flutter/services.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";

/// The platform-view type of the native Apple button. The `tailtag_clerk`
/// iOS plugin registers it.
const String appleButtonViewType = "app.tailtag/apple-button";

/// The opacity of the native button while another attempt is pending.
const double _disabledOpacity = 0.38;

/// The "Continue with Apple" button, on iOS only.
///
/// The system `ASAuthorizationAppleIDButton` draws the logo and the text, so
/// the button always meets Apple's Human Interface Guidelines and needs no
/// Apple artwork in the app. It is black in the light theme and white in
/// the dark theme. A Flutter button around it owns the tap, the focus, the
/// disabled state, and the semantics, so it behaves like the other access
/// buttons. The native view gets no touches and no accessibility element.
///
/// It keeps the TailTag pill shape. Its height is `size.minTarget`, scaled
/// by the text scale, because the native button sizes its text to its
/// height. While [loading] is true, it is disabled. After
/// [loadingIndicatorDelay], a spinner shows at its end.
class AppleButton extends StatelessWidget {
  /// Creates the button.
  const new({required this.onPressed, this.loading = false, super.key});

  /// Called on tap. When null, the button is disabled.
  final VoidCallback? onPressed;

  /// Whether the Apple attempt is running.
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final height = math.max(
      TokenSize.minTarget,
      MediaQuery.textScalerOf(context).scale(TokenSize.minTarget),
    );
    final enabled = onPressed != null && !loading;
    return Semantics(
      value: loading ? UiStrings.loading : null,
      child: TextButton(
        onPressed: loading ? null : onPressed,
        style: TextButton.styleFrom(
          padding: EdgeInsets.zero,
          minimumSize: Size(TokenSize.minTarget, height),
          shape: const StadiumBorder(),
          splashFactory: NoSplash.splashFactory,
        ),
        child: Semantics(
          label: AccountAccessStrings.continueWithApple,
          child: SizedBox(
            height: height,
            width: double.infinity,
            child: Stack(
              alignment: AlignmentDirectional.centerEnd,
              children: [
                Positioned.fill(
                  child: Opacity(
                    opacity: enabled || loading ? 1 : _disabledOpacity,
                    child: IgnorePointer(
                      child: ExcludeSemantics(
                        child: UiKitView(
                          // The native view reads its style only when it is
                          // created, so a theme change creates a new one.
                          key: ValueKey(dark),
                          viewType: appleButtonViewType,
                          creationParams: {"style": dark ? "white" : "black"},
                          creationParamsCodec: const StandardMessageCodec(),
                        ),
                      ),
                    ),
                  ),
                ),
                if (loading)
                  Padding(
                    padding: EdgeInsetsDirectional.only(
                      end: height / 2 - TokenSpacing.sm,
                    ),
                    child: DelayedVisibility(
                      child: SizedBox.square(
                        dimension: 20,
                        // Stroke widths have no token. 2 suits a 20 px
                        // spinner.
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: dark ? Colors.black : Colors.white,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
