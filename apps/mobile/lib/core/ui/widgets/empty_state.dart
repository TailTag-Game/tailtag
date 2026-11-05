import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";

/// The view of a list that loaded with no items.
///
/// It shows an icon, a title that says what is empty, one line that says how
/// to fill the list, and an optional action. Features write the text.
///
/// A dashed outline frames the content, like an empty slot in a card binder
/// that waits for its first card.
class EmptyState extends StatelessWidget {
  /// Creates an empty state.
  const new({
    required this.icon,
    required this.title,
    required this.body,
    this.action,
    super.key,
  });

  /// One Outlined icon. It is excluded from semantics.
  final IconData icon;

  /// What is empty, for example "No fursuits yet".
  final String title;

  /// How to fill the list, for example "Add a fursuit to start playing."
  final String body;

  /// An optional primary or secondary `TailTagButton`.
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    // At a large text scale in a short space, the framed content scrolls.
    return SingleChildScrollView(
      child: CustomPaint(
        painter: _DashedSlotPainter(color: scheme.outline),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(
            horizontal: TokenSpacing.xl,
            vertical: TokenSpacing.xxl,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ExcludeSemantics(
                child: Icon(
                  icon,
                  size: TokenSize.iconLarge,
                  color: scheme.primary,
                ),
              ),
              const SizedBox(height: TokenSpacing.md),
              Semantics(
                header: true,
                child: Text(
                  title,
                  textAlign: TextAlign.center,
                  style: textTheme.titleLarge?.copyWith(
                    color: scheme.onSurface,
                  ),
                ),
              ),
              const SizedBox(height: TokenSpacing.sm),
              Text(
                body,
                textAlign: TextAlign.center,
                style: textTheme.bodyMedium?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
              ),
              if (action != null) ...[
                const SizedBox(height: TokenSpacing.xl),
                action!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Paints a dashed `radius.large` outline around the empty state.
class _DashedSlotPainter extends CustomPainter {
  const new({required this.color});

  final Color color;

  // Stroke widths have no token. 2 matches the focused text field border.
  static const double _strokeWidth = 2;

  @override
  void paint(Canvas canvas, Size size) {
    const inset = _strokeWidth / 2;
    final outline = Path()
      ..addRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            inset,
            inset,
            size.width - _strokeWidth,
            size.height - _strokeWidth,
          ),
          const Radius.circular(TokenRadius.large),
        ),
      );
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = _strokeWidth
      ..strokeCap = StrokeCap.round;
    for (final metric in outline.computeMetrics()) {
      var distance = 0.0;
      while (distance < metric.length) {
        final end = distance + TokenSpacing.sm;
        canvas.drawPath(metric.extractPath(distance, end), paint);
        distance = end + TokenSpacing.sm;
      }
    }
  }

  @override
  bool shouldRepaint(_DashedSlotPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}
