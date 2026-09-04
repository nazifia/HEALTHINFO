import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/stock_ledger_screen.dart';

List<Map<String, dynamic>> rows(List<num?> quantities) =>
    [for (final q in quantities) {'quantity': q}];

void main() {
  test('in and out come out of one signed column', () {
    final t = ledgerTotals(rows([100, -30, -20, 5]));
    expect(t.into, 105);
    expect(t.out, 50);
    expect(t.net, 55);
  });

  test('a page that only dispensed nets negative', () {
    final t = ledgerTotals(rows([-10, -1]));
    expect(t.into, 0);
    expect(t.out, 11);
    expect(t.net, -11);
  });

  test('a missing quantity counts as nothing, not as an incoming unit', () {
    expect(ledgerTotals(rows([null, 0])), (into: 0, out: 0, net: 0));
    expect(ledgerTotals(const []), (into: 0, out: 0, net: 0));
  });
}
