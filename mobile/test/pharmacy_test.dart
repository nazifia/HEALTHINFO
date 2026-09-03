import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/pharmacy.dart';

void main() {
  test('a discount never turns a line negative', () {
    const line = BasketLine(
        itemId: 1, name: 'Paracetamol', unitPrice: 12.5, quantity: 2, discount: 100);
    expect(line.lineTotal, 0);
  });

  test('the basket adds its lines up', () {
    final lines = [
      const BasketLine(
          itemId: 1, name: 'Paracetamol', unitPrice: 12.5, quantity: 20),
      const BasketLine(
          itemId: 2, name: 'Syrup', unitPrice: 950, quantity: 1, discount: 50),
    ];
    expect(basketTotal(lines), 250 + 900);
  });

  test('a cash sale sends no scheme card, an HMO sale does', () {
    final lines = [
      const BasketLine(itemId: 7, name: 'ORS', unitPrice: 150, quantity: 3),
    ];
    final cash = saleBody(
        lines: lines, paymentMethod: 'cash', patientId: 4, enrollmentId: 9);
    // The API rejects a membership on a non-HMO sale, so it must not travel.
    expect(cash.containsKey('enrollment'), isFalse);
    expect(cash['patient'], 4);
    expect(cash['items'], [
      {'item': 7, 'quantity': 3}
    ]);

    final insured = saleBody(
        lines: lines, paymentMethod: 'hmo', patientId: 4, enrollmentId: 9);
    expect(insured['enrollment'], 9);
  });

  test('a walk-in carries no patient, and totals stay server-side', () {
    final body = saleBody(
      lines: [
        const BasketLine(
            itemId: 1, name: 'Paracetamol', unitPrice: 12.5, quantity: 2,
            discount: 5),
      ],
      paymentMethod: 'cash',
    );
    expect(body.containsKey('patient'), isFalse);
    expect(body.containsKey('total'), isFalse);
    expect((body['items'] as List).first, {
      'item': 1,
      'quantity': 2,
      'discount': '5.00',
    });
  });

  test('only the admin decides or banks a claim', () {
    expect(claimActions('draft', 'pharmacist'), ['submit']);
    expect(claimActions('submitted', 'pharmacist'), isEmpty);
    expect(claimActions('submitted', 'tenant_admin'), ['approve', 'reject']);
    expect(claimActions('approved', 'tenant_admin'), ['pay']);
    // A rejected claim can be corrected and sent again.
    expect(claimActions('rejected', 'pharmacist'), ['submit']);
    // Settled or withdrawn: nothing left to do.
    expect(claimActions('paid', 'super_admin'), isEmpty);
    expect(claimActions('cancelled', 'super_admin'), isEmpty);
    // Nobody outside the pharmacy gets a button at all.
    expect(claimActions('draft', 'nurse'), isEmpty);
  });

  test('batch actions follow the same split', () {
    expect(batchActions('draft', 'pharmacist'),
        ['add-claims', 'submit', 'cancel']);
    expect(batchActions('submitted', 'pharmacist'), ['cancel']);
    expect(batchActions('submitted', 'tenant_admin'),
        ['approve', 'pay', 'cancel']);
    expect(batchActions('paid', 'tenant_admin'), isEmpty);
    expect(batchActions('draft', 'doctor'), isEmpty);
  });

  test('money and units read blanks without crashing', () {
    expect(money('4575.00'), '₦4,575.00');
    expect(money(1650), '₦1,650.00');
    expect(money(null), '—');
    expect(units('80'), '80');
    expect(units(null), '—');
  });

  test('an order can only be sent while it is a draft', () {
    expect(orderActions('draft', 'pharmacist'), ['submit', 'cancel']);
    // Sent or part-delivered: the only thing left is abandoning the rest.
    expect(orderActions('submitted', 'pharmacist'), ['cancel']);
    expect(orderActions('partial', 'tenant_admin'), ['cancel']);
    // Fully received, or already cancelled: nothing to do.
    expect(orderActions('received', 'tenant_admin'), isEmpty);
    expect(orderActions('cancelled', 'pharmacist'), isEmpty);
    expect(orderActions('draft', 'nurse'), isEmpty);
  });

  test('an order posts its lines and lets the API count deliveries', () {
    final lines = [
      const OrderLineDraft(
          itemId: 5, name: 'ORS sachet', quantity: 200, unitCost: 95),
      const OrderLineDraft(
          itemId: 6, name: 'Ceftriaxone', quantity: 50, unitCost: 1750),
    ];
    expect(orderTotal(lines), 200 * 95 + 50 * 1750);

    final body = purchaseOrderBody(
        supplierId: 2, lines: lines, expectedDate: '2026-09-10', notes: ' ');
    expect(body['supplier'], 2);
    expect(body['expected_date'], '2026-09-10');
    // Blank notes are dropped rather than sent as whitespace.
    expect(body.containsKey('notes'), isFalse);
    // What has arrived is a fact about deliveries — an order never asserts it.
    expect((body['items'] as List).first, {
      'item': 5,
      'quantity_ordered': 200,
      'unit_cost': '95.00',
    });
    expect(body.toString().contains('quantity_received'), isFalse);
  });

  test('an order with no expected date omits it', () {
    final body = purchaseOrderBody(supplierId: 1, lines: [
      const OrderLineDraft(itemId: 1, name: 'Paracetamol', quantity: 10, unitCost: 5),
    ]);
    expect(body.containsKey('expected_date'), isFalse);
  });
}
