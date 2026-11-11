import "dart:async";

import "package:flutter/widgets.dart";

/// How long a wait lasts before a loading indicator shows.
///
/// A shorter wait shows no indicator, so a fast response does not flash.
/// See "Loading" in docs/design/components.md.
const Duration loadingIndicatorDelay = Duration(milliseconds: 500);

/// Shows [replacement] for [delay] after it is added to the tree, then
/// [child].
///
/// Add it only while a wait runs, for example `if (loading)`. Removing it
/// cancels the timer, so the next wait starts again from zero. Use it for a
/// screen loading indicator, the "Updating" subtitle of a switch row, or a
/// choice sheet that loads its list. `TailTagButton` uses it for its loading
/// state.
class DelayedVisibility extends StatefulWidget {
  /// Creates a delayed view of [child].
  const new({
    required this.child,
    this.replacement = const SizedBox.shrink(),
    this.delay = loadingIndicatorDelay,
    super.key,
  });

  /// What shows after [delay], for example a spinner.
  final Widget child;

  /// What shows until [delay] ends. It is empty by default.
  final Widget replacement;

  /// How long [replacement] shows.
  final Duration delay;

  @override
  State<DelayedVisibility> createState() => _DelayedVisibilityState();
}

class _DelayedVisibilityState extends State<DelayedVisibility> {
  late final Timer _timer;
  bool _elapsed = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer(widget.delay, () => setState(() => _elapsed = true));
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return _elapsed ? widget.child : widget.replacement;
  }
}
