import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/controlled_stats.dart';

const _payload = {
  'level': 'state',
  'by_area': [
    {'state': 'Lagos', 'prescribed': 3, 'prescribed_units': 15,
     'dispensed': 2, 'dispensed_units': 12},
    {'state': 'Kano', 'prescribed': 1, 'prescribed_units': 4,
     'dispensed': 1, 'dispensed_units': 4},
  ],
  'by_drug': [
    // Ordered by lines written plus lines sold, the way the API sends them.
    {'drug': 'Codeine syrup', 'dispensed_units': 6, 'otc_units': 1},
    {'drug': 'Tramadol 100mg', 'dispensed_units': 10, 'otc_units': 0},
    {'drug': 'Pethidine 50mg', 'dispensed_units': 0, 'otc_units': 8},
  ],
};

void main() {
  test('a column is summed across every area', () {
    expect(controlledTotal(_payload, 'prescribed_units'), 19);
    expect(controlledTotal(_payload, 'dispensed_units'), 16);
    expect(controlledTotal(_payload, 'prescribed'), 4);
  });

  test('nothing to show sums to zero rather than throwing', () {
    expect(controlledTotal(null, 'dispensed'), 0);
    expect(controlledTotal(const {}, 'dispensed'), 0);
    expect(controlledByArea(null, 'dispensed'), isEmpty);
  });

  test('rows are labelled by the tier the payload was folded to', () {
    expect(controlledByArea(_payload, 'dispensed_units'), [
      {'area': 'Lagos', 'value': 12},
      {'area': 'Kano', 'value': 4},
    ]);
    // A local seat's rows carry 'local', not 'state'.
    expect(
      controlledByArea(const {
        'level': 'local',
        'by_area': [{'local': 'Ikeja', 'dispensed_units': 12}],
      }, 'dispensed_units'),
      [{'area': 'Ikeja', 'value': 12}],
    );
  });

  test('drug rows are ranked by the column the card names', () {
    expect(controlledByDrug(_payload, 'dispensed_units'), [
      {'drug': 'Tramadol 100mg', 'value': 10},
      {'drug': 'Codeine syrup', 'value': 6},
    ]);
    // A drug that only ever goes over the counter tops the till card.
    expect(controlledByDrug(_payload, 'otc_units'), [
      {'drug': 'Pethidine 50mg', 'value': 8},
      {'drug': 'Codeine syrup', 'value': 1},
    ]);
    expect(controlledByDrug(null, 'otc_units'), isEmpty);
  });
}
