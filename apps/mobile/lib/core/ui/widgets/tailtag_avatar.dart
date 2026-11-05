import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";

/// Whose image an avatar shows.
enum AvatarKind {
  /// A player. The empty-name icon is a person.
  player,

  /// A fursuit. The empty-name icon is a paw.
  fursuit,
}

/// The size and shape of an avatar.
enum AvatarSize {
  /// A `size.avatar.small` circle, for list rows.
  small,

  /// A `size.avatar.large` circle, for headers.
  large,

  /// A rounded square at the full width of its parent, for previews.
  ///
  /// It has `radius.small` corners. Inside a card it sits `spacing.sm` from
  /// the card edge, so its corners follow the `radius.large` card corners.
  photo,
}

/// The image of a player or a fursuit, with the image placeholder.
///
/// The avatar is excluded from semantics, because the name always shows
/// next to it.
class TailTagAvatar extends StatelessWidget {
  /// Creates an avatar.
  const new({
    required this.name,
    required this.kind,
    this.imageUrl,
    this.size = AvatarSize.small,
    super.key,
  });

  /// The display name or fursuit name. It gives the placeholder initials.
  final String name;

  /// Whether this is a player or a fursuit.
  final AvatarKind kind;

  /// The image URL from the API.
  ///
  /// The placeholder shows while the image loads, and when the URL is null
  /// or the image fails. API image URLs are presigned and expire, so a
  /// failed image shows the placeholder until the screen reloads with a new
  /// URL.
  final String? imageUrl;

  /// The size and shape.
  final AvatarSize size;

  /// Up to two initials: the first character of the first two words.
  static String initialsOf(String name) {
    final words = name.trim().split(RegExp(r"\s+")).where((w) => w.isNotEmpty);
    return words.take(2).map((w) => w.characters.first.toUpperCase()).join();
  }

  @override
  Widget build(BuildContext context) {
    final placeholder = _Placeholder(name: name, kind: kind, size: size);
    final url = imageUrl;
    final content = url == null
        ? placeholder
        : Image.network(
            url,
            fit: BoxFit.cover,
            frameBuilder: (context, child, frame, wasSynchronouslyLoaded) {
              final loaded = wasSynchronouslyLoaded || frame != null;
              return loaded ? child : placeholder;
            },
            errorBuilder: (context, error, stackTrace) => placeholder,
          );
    final shaped = switch (size) {
      AvatarSize.small => _circle(content, TokenSize.avatarSmall),
      AvatarSize.large => _circle(content, TokenSize.avatarLarge),
      AvatarSize.photo => AspectRatio(
        aspectRatio: 1,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(TokenRadius.small),
          child: content,
        ),
      ),
    };
    return ExcludeSemantics(child: shaped);
  }

  Widget _circle(Widget child, double diameter) {
    return SizedBox.square(
      dimension: diameter,
      child: ClipOval(child: child),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const new({required this.name, required this.kind, required this.size});

  final String name;
  final AvatarKind kind;
  final AvatarSize size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final initials = TailTagAvatar.initialsOf(name);
    final style = size == AvatarSize.small
        ? textTheme.titleMedium
        : textTheme.headlineMedium;
    // Players are violet and fursuits are pink, so a list of placeholders
    // reads as a sheet of stickers. The icon and the name, not the color,
    // tell the kinds apart.
    final (Color background, Color foreground) = switch (kind) {
      AvatarKind.player => (scheme.primaryContainer, scheme.onPrimaryContainer),
      AvatarKind.fursuit => (
        scheme.tertiaryContainer,
        scheme.onTertiaryContainer,
      ),
    };
    return ColoredBox(
      color: background,
      child: Center(
        child: initials.isEmpty
            ? Icon(
                kind == AvatarKind.player
                    ? Icons.person_outlined
                    : Icons.pets_outlined,
                color: foreground,
                size: TokenSize.iconMedium,
              )
            : Text(
                initials,
                style: style?.copyWith(color: foreground),
                textScaler: TextScaler.noScaling,
              ),
      ),
    );
  }
}
