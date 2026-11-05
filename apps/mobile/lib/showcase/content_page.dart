import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/empty_state.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/showcase/showcase_images.dart";
import "package:tailtag_mobile/showcase/showcase_parts.dart";

/// Showcase tab for cards, list rows, avatars, badges, and the empty state.
class ContentPage extends StatelessWidget {
  /// Creates the tab.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return const ShowcasePage(
      children: [
        _CardSection(),
        _ListRowSection(),
        _AvatarSection(),
        _BadgeSection(),
        _EmptyStateSection(),
      ],
    );
  }
}

/// A note for the parts whose pressed and focused look is a Material state
/// layer. Flutter draws that layer only during a real press or focus.
const String _stateLayerNote =
    "Live: press and hold for the pressed layer. "
    "Use Tab on a keyboard for the focus layer.";

class _CardSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final supporting = textTheme.bodyMedium?.copyWith(
      color: scheme.onSurfaceVariant,
    );
    return ShowcaseSection(
      title: "Card",
      children: [
        ShowcaseExample(
          label: "With buttons: the catch preview (F8)",
          // A trading card: the photo sits spacing.sm from the card edge, and
          // the name and action sit below it.
          child: Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                    TokenSpacing.sm,
                    TokenSpacing.sm,
                    TokenSpacing.sm,
                    0,
                  ),
                  child: TailTagAvatar(
                    name: "Blaze",
                    kind: AvatarKind.fursuit,
                    imageUrl: ShowcaseImages.of(context).sample,
                    size: AvatarSize.photo,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(TokenSpacing.lg),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        "Blaze",
                        style: textTheme.titleLarge,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: TokenSpacing.xs),
                      Text(
                        "Red fox. Owned by @ember_sky.",
                        style: supporting,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: TokenSpacing.lg),
                      const TailTagButton(
                        label: "Confirm catch",
                        icon: Icons.check_circle_outlined,
                        onPressed: noop,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        ShowcaseExample(
          label: "Tappable: the active convention (F3). $_stateLayerNote",
          child: Card(
            child: InkWell(
              onTap: noop,
              child: Padding(
                padding: const EdgeInsets.all(TokenSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            "Northwind Fur Meet 2026",
                            style: textTheme.titleLarge,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: TokenSpacing.sm),
                        const StatusBadge(
                          tone: StatusTone.success,
                          label: "Active",
                        ),
                      ],
                    ),
                    const SizedBox(height: TokenSpacing.xs),
                    Text(
                      "Your fursuits and catches count here.",
                      style: supporting,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        ShowcaseExample(
          label: "Long text: a two-line title and three lines of text",
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(TokenSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    longFursuitName,
                    style: textTheme.titleLarge,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: TokenSpacing.xs),
                  Text(
                    "A tall wolf with silver paws and a long blue scarf. "
                    "Look for the scarf near the main stage in the "
                    "afternoon. Ask before a hug, and mind the tail. "
                    "This text ends after three lines.",
                    style: supporting,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ListRowSection extends StatefulWidget {
  const new();

  @override
  State<_ListRowSection> createState() => _ListRowSectionState();
}

class _ListRowSectionState extends State<_ListRowSection> {
  String _choice = "Northwind Fur Meet";

  @override
  Widget build(BuildContext context) {
    const outNow = StatusBadge(tone: StatusTone.success, label: "Out now");
    return ShowcaseSection(
      title: "List row",
      children: [
        ShowcaseExample(
          label:
              "Navigation rows: fursuits (F4) and catches (F9). "
              "$_stateLayerNote",
          bleed: true,
          child: Column(
            children: [
              ListTile(
                leading: const TailTagAvatar(
                  name: "Blaze",
                  kind: AvatarKind.fursuit,
                ),
                title: const Text("Blaze"),
                subtitle: StatusBadge.rowSubtitle(
                  context,
                  outNow,
                  subtitle: const Text("Red fox"),
                ),
                trailing: StatusBadge.rowTrailing(context, outNow),
                onTap: noop,
              ),
              ListTile(
                leading: TailTagAvatar(
                  name: longFursuitName,
                  kind: AvatarKind.fursuit,
                  imageUrl: ShowcaseImages.of(context).sample,
                ),
                title: const Text(
                  longFursuitName,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: const Text(
                  "Caught at Lakeside Pawcon on 12 March. "
                  "This subtitle wraps to two lines and then ends.",
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                onTap: noop,
              ),
              const ListTile(
                leading: TailTagAvatar(name: "", kind: AvatarKind.fursuit),
                title: Text("Unnamed fursuit"),
                subtitle: Text("Disabled row: activate it first"),
                enabled: false,
              ),
            ],
          ),
        ),
        const ShowcaseExample(
          label: "Info row: a value the player cannot change here (F2)",
          bleed: true,
          child: ListTile(
            leading: Icon(Icons.alternate_email_outlined),
            title: Text("Handle"),
            subtitle: Text("ember_sky"),
          ),
        ),
        ShowcaseExample(
          label: "Live: choice rows, as in a bottom sheet (F3)",
          child: Column(
            children: [
              for (final name in const [
                "Northwind Fur Meet",
                "Lakeside Pawcon",
              ])
                ListTile(
                  title: Text(name),
                  selected: _choice == name,
                  trailing: _choice == name ? const Icon(Icons.check) : null,
                  onTap: () => setState(() => _choice = name),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _AvatarSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    final images = ShowcaseImages.of(context);
    return ShowcaseSection(
      title: "Avatar",
      children: [
        ShowcaseExample(
          label:
              "Small: image, initials, one word, empty player, empty fursuit",
          child: Wrap(
            spacing: TokenSpacing.md,
            runSpacing: TokenSpacing.md,
            children: [
              TailTagAvatar(
                name: "Blaze",
                kind: AvatarKind.fursuit,
                imageUrl: images.sample,
              ),
              const TailTagAvatar(name: "Ember Sky", kind: AvatarKind.player),
              const TailTagAvatar(name: "blaze", kind: AvatarKind.fursuit),
              const TailTagAvatar(name: "", kind: AvatarKind.player),
              const TailTagAvatar(name: "", kind: AvatarKind.fursuit),
            ],
          ),
        ),
        ShowcaseExample(
          label: "Large: image and placeholder",
          child: Wrap(
            spacing: TokenSpacing.md,
            children: [
              TailTagAvatar(
                name: "Blaze",
                kind: AvatarKind.fursuit,
                imageUrl: images.sample,
                size: AvatarSize.large,
              ),
              const TailTagAvatar(
                name: "Ember Sky",
                kind: AvatarKind.player,
                size: AvatarSize.large,
              ),
            ],
          ),
        ),
        const ShowcaseExample(
          label: "Photo: placeholder (the catch preview card shows an image)",
          child: SizedBox(
            width: 160,
            child: TailTagAvatar(
              name: "Midnight Velvet",
              kind: AvatarKind.fursuit,
              size: AvatarSize.photo,
            ),
          ),
        ),
        ShowcaseExample(
          label: "Error: a missing image keeps the placeholder",
          child: TailTagAvatar(
            name: "Missing Image",
            kind: AvatarKind.fursuit,
            imageUrl: images.missing,
          ),
        ),
      ],
    );
  }
}

class _BadgeSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return const ShowcaseSection(
      title: "Badge",
      children: [
        ShowcaseExample(
          label: "Neutral with an icon, neutral, success, warning, error",
          child: Wrap(
            spacing: TokenSpacing.sm,
            runSpacing: TokenSpacing.sm,
            children: [
              StatusBadge(
                tone: StatusTone.neutral,
                label: "Inactive",
                icon: Icons.schedule_outlined,
              ),
              StatusBadge(tone: StatusTone.neutral, label: "Caught"),
              StatusBadge(tone: StatusTone.success, label: "Out now"),
              StatusBadge(tone: StatusTone.warning, label: "Not live"),
              StatusBadge(tone: StatusTone.error, label: "Revoked"),
            ],
          ),
        ),
      ],
    );
  }
}

class _EmptyStateSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return const ShowcaseSection(
      title: "Empty state",
      children: [
        ShowcaseExample(
          label: "With an action (F4)",
          child: EmptyState(
            icon: Icons.pets_outlined,
            title: "No fursuits yet",
            body: "Add a fursuit to start playing.",
            action: TailTagButton(label: "Add fursuit", onPressed: noop),
          ),
        ),
        ShowcaseExample(
          label: "Without an action (F9)",
          child: EmptyState(
            icon: Icons.qr_code_scanner_outlined,
            title: "No catches yet",
            body: "Scan a fursuit QR code to make your first catch.",
          ),
        ),
      ],
    );
  }
}
