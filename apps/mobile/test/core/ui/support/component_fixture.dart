import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/empty_state.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";

/// A long screen title that must end in an ellipsis on a small phone.
const fixtureTitle = "Sable the Arctic Fox at FurCon 2026 Main Hall";

/// The navigation bar labels: one short word each.
const fixtureNavLabels = ["Home", "Catches", "Profile"];

/// Every pressable control in the fixture, by the id it reports when tapped.
const fixtureControls = {
  "banner": "Try again",
  "primary": "Save",
  "secondary": "Enroll",
  "secondaryText": "Cancel",
  "destructive": "Rotate code",
  "card": "Sable the Arctic Fox",
  "row": "Sable",
  "choice": "FurCon 2026",
  "chip": "FurCon",
  "switch": "Out for catching",
  "empty": "Add fursuit",
  "nav1": "Catches",
};

/// Every V0 inventory component from components.md in its normal state,
/// with no backend, Clerk session, or app config. The dialog, the bottom
/// sheet, and the snackbar open on top of it in the tests.
class ComponentFixture extends StatelessWidget {
  /// Creates the fixture. [onTap] gets the id of each tapped control.
  const new({required this.onTap, this.textScale = 1, super.key});

  /// Called with a [fixtureControls] id when a control is tapped.
  final ValueChanged<String> onTap;

  /// The text scale for the whole fixture.
  final double textScale;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: buildTailTagTheme(),
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: _Page(onTap: onTap),
        ),
      ),
    );
  }
}

const _outNow = StatusBadge(tone: StatusTone.success, label: "Out now");

class _Page extends StatelessWidget {
  const new({required this.onTap});

  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) {
    const gap = SizedBox(height: TokenSpacing.lg);
    return Scaffold(
      appBar: AppBar(
        title: const Text(fixtureTitle),
        actions: [
          IconButton(
            tooltip: "Share QR code",
            icon: Icon(Icons.adaptive.share),
            onPressed: () => onTap("share"),
          ),
          PopupMenuButton<String>(
            icon: Icon(Icons.adaptive.more),
            itemBuilder: (_) => const [
              PopupMenuItem(value: "help", child: Text("Help")),
            ],
          ),
        ],
      ),
      // A Column, not a lazy list, so every part lays out at once.
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(TokenSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            StatusBanner(
              tone: StatusTone.error,
              message: GenericError.unknown.message,
              actionLabel: GenericError.unknown.actionLabel,
              onAction: () => onTap("banner"),
            ),
            gap,
            for (final (id, variant) in [
              ("primary", TailTagButtonVariant.primary),
              ("secondary", TailTagButtonVariant.secondary),
              ("secondaryText", TailTagButtonVariant.secondaryText),
              ("destructive", TailTagButtonVariant.destructive),
            ]) ...[
              TailTagButton(
                label: fixtureControls[id]!,
                variant: variant,
                onPressed: () => onTap(id),
              ),
              const SizedBox(height: TokenSpacing.sm),
            ],
            gap,
            TextFormField(
              maxLength: 50,
              decoration: const InputDecoration(
                labelText: "Display name",
                helperText: "Other players see this name.",
              ),
            ),
            gap,
            Card(
              child: InkWell(
                onTap: () => onTap("card"),
                child: Padding(
                  padding: const EdgeInsets.all(TokenSpacing.lg),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        fixtureControls["card"]!,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: TokenSpacing.md),
                      const Text(
                        "Out now in the main hall.",
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            gap,
            ListTile(
              leading: const TailTagAvatar(
                name: "Sable",
                kind: AvatarKind.fursuit,
              ),
              title: Text(fixtureControls["row"]!),
              subtitle: StatusBadge.rowSubtitle(
                context,
                _outNow,
                subtitle: const Text("Arctic fox"),
              ),
              trailing: StatusBadge.rowTrailing(context, _outNow),
              onTap: () => onTap("row"),
            ),
            const ListTile(title: Text("Handle"), subtitle: Text("@sable")),
            ListTile(
              title: Text(fixtureControls["choice"]!),
              trailing: const Icon(Icons.check),
              selected: true,
              onTap: () => onTap("choice"),
            ),
            gap,
            Wrap(
              spacing: TokenSpacing.sm,
              runSpacing: TokenSpacing.sm,
              children: [
                FilterChip(
                  label: const Text("All"),
                  selected: true,
                  onSelected: (_) => onTap("all"),
                ),
                FilterChip(
                  label: Text(fixtureControls["chip"]!),
                  onSelected: (_) => onTap("chip"),
                ),
              ],
            ),
            gap,
            const Wrap(
              spacing: TokenSpacing.sm,
              runSpacing: TokenSpacing.sm,
              children: [
                StatusBadge(tone: StatusTone.neutral, label: "Caught"),
                StatusBadge(tone: StatusTone.warning, label: "Not out"),
                StatusBadge(tone: StatusTone.error, label: "Revoked"),
              ],
            ),
            gap,
            SwitchListTile(
              title: Text(fixtureControls["switch"]!),
              subtitle: const Text("Other players can catch this fursuit."),
              value: true,
              onChanged: (_) => onTap("switch"),
            ),
            gap,
            const Center(
              child: CircularProgressIndicator(
                semanticsLabel: "Loading fursuits",
              ),
            ),
            gap,
            EmptyState(
              icon: Icons.pets_outlined,
              title: "No fursuits yet",
              body: "Add a fursuit to start playing.",
              action: TailTagButton(
                label: fixtureControls["empty"]!,
                variant: TailTagButtonVariant.secondary,
                onPressed: () => onTap("empty"),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        onDestinationSelected: (index) => onTap("nav$index"),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: "Home",
          ),
          NavigationDestination(
            icon: Icon(Icons.pets_outlined),
            selectedIcon: Icon(Icons.pets),
            label: "Catches",
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outlined),
            selectedIcon: Icon(Icons.person),
            label: "Profile",
          ),
        ],
      ),
    );
  }
}
