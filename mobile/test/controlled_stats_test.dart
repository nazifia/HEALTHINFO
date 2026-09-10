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
}
