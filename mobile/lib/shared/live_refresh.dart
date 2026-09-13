import 'dart:async';

import 'package:flutter/widgets.dart';

/// Re-pulls a screen's numbers every 10s while it is mounted, so rows other
/// staff (or `simulate`) write show up without a pull-to-refresh.
///
/// The screen implements [refresh] as its usual reload (a new future into
/// setState). FutureBuilder keeps the last snapshot's data while the new
/// future is waiting, so the builder shows its skeleton only when
/// `!snap.hasData` — the numbers stay on screen and just change.
///
/// ponytail: 10s poll on every mounted screen (a kept-alive tab polls while
/// hidden); swap for SSE only if the poll load ever shows on the server.
mixin LiveRefresh<T extends StatefulWidget> on State<T> {
  static const period = Duration(seconds: 10);
  Timer? _liveTimer;

  /// Start the next load the way pull-to-refresh does.
  void refresh();

  @override
  void initState() {
    super.initState();
    _liveTimer = Timer.periodic(period, (_) {
      if (mounted) refresh();
    });
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    super.dispose();
  }
}
