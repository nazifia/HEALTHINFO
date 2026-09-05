import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/drug_orders_screen.dart';

/// The drug orders list shows one card per prescription, not per drug.
void main() {
  test('drugs written together collapse into one prescription', () {
    final rows = collapseByGroup([
      {'id': 1, 'group': 'g1', 'medication_name': 'Artemether'},
      {'id': 2, 'group': 'g1', 'medication_name': 'Paracetamol'},
      {'id': 3, 'group': null, 'medication_name': 'Zinc'},
      {'id': 4, 'group': 'g2', 'medication_name': 'Metformin'},
    ]);

    expect(rows.map((r) => r['id']), [1, 3, 4]);
    expect((rows[0]['drugs'] as List).length, 2);
    // An order on no prescription stands alone rather than joining the last.
    expect((rows[1]['drugs'] as List).single['medication_name'], 'Zinc');
    expect((rows[2]['drugs'] as List).length, 1);
  });
}
