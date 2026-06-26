import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

import 'config.dart';

/// Wraps the app and fires [onTimeout] after [timeout] of no pointer activity.
/// Also resets when the app returns to the foreground so a backgrounded app
/// can't sit logged-in past the window.
class InactivityWatcher extends StatefulWidget {
  const InactivityWatcher({
    super.key,
    required this.child,
    required this.onTimeout,
    this.timeout = idleTimeout,
  });

  final Widget child;
  final VoidCallback onTimeout;
  final Duration timeout;

  @override
  State<InactivityWatcher> createState() => _InactivityWatcherState();
}

class _InactivityWatcherState extends State<InactivityWatcher>
    with WidgetsBindingObserver {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _reset();
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _reset() {
    _timer?.cancel();
    _timer = Timer(widget.timeout, widget.onTimeout);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _reset();
  }

  @override
  Widget build(BuildContext context) {
    // Listener sees pointer events before child widgets consume them.
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (_) => _reset(),
      onPointerMove: (_) => _reset(),
      child: widget.child,
    );
  }
}
