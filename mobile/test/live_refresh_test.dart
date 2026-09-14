import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/live_refresh.dart';

class _Poller extends StatefulWidget {
  final List<int> hits;
  const _Poller(this.hits);
  @override
  State<_Poller> createState() => _PollerState();
}

class _PollerState extends State<_Poller> with LiveRefresh {
  @override
  void refresh() => widget.hits.add(1);
  @override
  Widget build(BuildContext context) => const SizedBox();
}

void main() {
  testWidgets('hidden IndexedStack tab does not poll; shown tab does', (tester) async {
    final hits = <int>[];
    Widget app(int index) => MaterialApp(
          home: IndexedStack(index: index, children: [const SizedBox(), _Poller(hits)]),
        );
    await tester.pumpWidget(app(0));
    await tester.pump(LiveRefresh.period * 2);
    expect(hits, isEmpty);

    await tester.pumpWidget(app(1));
    expect(hits.length, 1); // catch-up refresh on becoming visible
    await tester.pump(LiveRefresh.period);
    expect(hits.length, 2);
  });
}
