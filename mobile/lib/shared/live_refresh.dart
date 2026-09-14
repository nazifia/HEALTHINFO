import 'dart:async';

import 'package:flutter/widgets.dart';

/// Re-pulls a screen's numbers every 10s while it is mounted AND on screen,
/// so rows other staff (or `simulate`) write show up without a pull-to-refresh.
///
/// The screen implements [refresh] as its usual reload (a new future into
/// setState). FutureBuilder keeps the last snapshot's data while the new
/// future is waiting, so the builder shows its skeleton only when
/// `!snap.hasData` — the numbers stay on screen and just change.
///
/// Every register lives in the home IndexedStack at once, so without the
/// visibility gate ~20 screens each fired a request and a rebuild every 10s
/// and the UI stuttered. Hidden tabs (Visibility.of) and screens under a
/// pushed route (ModalRoute.isCurrent) now skip the tick; a tab catches up
/// the moment it is shown again.
///
/// ponytail: 10s poll on the visible screen; swap for SSE only if the poll
/// load ever shows on the server.
mixin LiveRefresh<T extends StatefulWidget> on State<T> {
  static const period = Duration(seconds: 10);
  Timer? _liveTimer;
  bool _wasVisible = true;

  /// Start the next load the way pull-to-refresh does.
  void refresh();

  bool get _onScreen =>
      Visibility.of(context) && (ModalRoute.of(context)?.isCurrent ?? true);

  @override
  void initState() {
    super.initState();
    _liveTimer = Timer.periodic(period, (_) {
      if (mounted && _onScreen) refresh();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Visibility.of registers a dependency, so this runs when a tab is shown
    // or hidden. Refresh once on the way back so it is not up to 10s stale.
    final visible = _onScreen;
    if (visible && !_wasVisible) refresh();
    _wasVisible = visible;
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    super.dispose();
  }
}
