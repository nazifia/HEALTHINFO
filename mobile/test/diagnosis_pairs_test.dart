import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/stats_rows.dart';

void main() {
  test('each pair becomes one labelled row', () {
    final rows = diagnosisPairRows([
      {
        'diagnosis': 'Malaria',
        'icd10_code': 'B54',
        'medication': 'Artemether',
        'count': 2,
        'dispensed': 1,
      },
    ]);
    expect(rows, [
      {'pair': 'Malaria · Artemether (1 of 2 filled)', 'count': 2}
    ]);
  });

  test('an order with no diagnosis is kept, not dropped', () {
    final rows = diagnosisPairRows([
      {'diagnosis': '—', 'medication': 'Paracetamol', 'count': 1, 'dispensed': 0}
    ]);
    expect(rows.single['pair'], '— · Paracetamol (0 of 1 filled)');
  });

  test('a missing or empty field leaves the section empty', () {
    expect(diagnosisPairRows(null), isEmpty);
    expect(diagnosisPairRows([]), isEmpty);
    expect(prescribedRows(null), isEmpty);
  });

  test('a single-drug row carries the filled count too', () {
    expect(
      prescribedRows([
        {'medication': 'Artemether', 'count': 2, 'dispensed': 1}
      ]),
      [
        {'medication': 'Artemether (1 of 2 filled)', 'count': 2}
      ],
    );
  });

  test('a row from an older API with no dispensed field keeps a bare label', () {
    expect(
      prescribedRows([
        {'medication': 'Artemether', 'count': 2}
      ]).single['medication'],
      'Artemether',
    );
  });
}
