import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/widgets/motion.dart';

void main() {
  test('CountUp keeps prefix, suffix, grouping and decimals', () {
    expect(CountUp.format('₦1,200.50', 987.654), '₦987.65');
    expect(CountUp.format('₦12,345', 12345), '₦12,345');
    expect(CountUp.format('42%', 21), '21%');
    expect(CountUp.format('7', 3.2), '3');
    expect(CountUp.format('2024-01-05', 0), '2024-01-05');
    expect(CountUp.format('—', 0), '—');
  });

  testWidgets('Reveal waits for the scroll that brings it on screen', (
    tester,
  ) async {
    final ctrl = ScrollController();
    await tester.pumpWidget(
      MaterialApp(
        home: ListView(
          controller: ctrl,
          children: const [
            Reveal(child: SizedBox(height: 100, child: Text('top'))),
            // Past the 600px test viewport, inside the 250px cache extent: built, unseen.
            SizedBox(height: 700),
            Reveal(child: SizedBox(height: 100, child: Text('bottom'))),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    double opacity(String s) => tester
        .widget<Opacity>(
          find
              .ancestor(
                of: find.text(s, skipOffstage: false),
                matching: find.byType(Opacity, skipOffstage: false),
              )
              .first,
        )
        .opacity;
    expect(opacity('top'), 1);
    expect(opacity('bottom'), 0);
    ctrl.jumpTo(ctrl.position.maxScrollExtent);
    await tester.pumpAndSettle();
    expect(opacity('bottom'), 1);
  });
}
