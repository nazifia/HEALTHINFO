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

  test('a diagnosis row carries the filled count too', () {
    expect(
      diagnosisRows([
        {'diagnosis': 'Malaria', 'count': 3, 'dispensed': 2}
      ]),
      [
        {'diagnosis': 'Malaria (2 of 3 filled)', 'count': 3}
      ],
    );
    expect(diagnosisRows(null), isEmpty);
  });

  test('a drilldown keeps only the pairs for the tapped diagnosis', () {
    final pairs = [
      {'diagnosis': 'Malaria', 'medication': 'Artemether', 'count': 2},
      {'diagnosis': 'Cholera', 'medication': 'ORS', 'count': 1},
    ];
    expect(pairsFor(pairs, 'Malaria'), [pairs.first]);
    expect(pairsFor(pairs, 'Typhoid'), isEmpty);
  });

  test('no selection caps the pairs the panel draws', () {
    final pairs = [
      for (var i = 0; i < 30; i++)
        {'diagnosis': 'D$i', 'medication': 'M$i', 'count': 1}
    ];
    expect(pairsFor(pairs, null).length, 10);
    expect(pairsFor(pairs, null, limit: 3).length, 3);
    expect(pairsFor(null, null), isEmpty);
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
