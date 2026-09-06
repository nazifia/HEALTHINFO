import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/inactivity_watcher.dart';

void main() {
  testWidgets('signs out after the tenant\'s window, and a tap restarts it',
      (tester) async {
    var out = 0;
    Widget watcher(Duration timeout) => MaterialApp(
          home: InactivityWatcher(
            onTimeout: () => out++,
            timeout: timeout,
            child: const SizedBox.expand(child: Text('screen')),
          ),
        );

    await tester.pumpWidget(watcher(const Duration(minutes: 5)));
    await tester.pump(const Duration(minutes: 4));
    expect(out, 0);

    // A tap starts the window over: four more minutes is still not five.
    await tester.tap(find.text('screen'));
    await tester.pump(const Duration(minutes: 4));
    expect(out, 0);
    await tester.pump(const Duration(minutes: 2));
    expect(out, 1);
  });

  testWidgets('a shorter window from the server applies without a restart',
      (tester) async {
    var out = 0;
    Widget watcher(Duration timeout) => MaterialApp(
          home: InactivityWatcher(
            onTimeout: () => out++,
            timeout: timeout,
            child: const SizedBox.expand(child: Text('screen')),
          ),
        );

    await tester.pumpWidget(watcher(const Duration(minutes: 30)));
    await tester.pumpWidget(watcher(const Duration(minutes: 2)));
    await tester.pump(const Duration(minutes: 3));
    expect(out, 1);
  });
}
