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

  test('a script offers nothing once it is dispensed or void', () {
    expect(rxActions('pending', 'pharmacist'), ['dispense', 'cancel']);
    expect(rxActions('partial', 'pharmacist'), ['dispense', 'cancel']);
    expect(rxActions('dispensed', 'tenant_admin'), isEmpty);
    expect(rxActions('cancelled', 'tenant_admin'), isEmpty);
    // Non-pharmacy roles get no buttons at all.
    expect(rxActions('pending', 'nurse'), isEmpty);
  });

  test('a script never sends the consultation fee it was quoted', () {
    final body = prescriptionBody(
      customerName: '  ',
      lines: [
        const RxLineDraft(
            name: 'Amoxicillin', quantity: 15, itemId: 3, dosage: '1 tds'),
      ],
      prescriberId: 8,
      consultationCategory: 'b',
    );
    // A blank name is a walk-in, not an empty string on the record.
    expect(body['customer_name'], 'Walk-in');
    // The band travels; the money it implies is the server's to snapshot.
    expect(body['consultation_category'], 'B');
    expect(body.containsKey('consultation_fee'), isFalse);
    expect((body['medications'] as List).first, {
      'name': 'Amoxicillin',
      'quantity': 15,
      'item': 3,
      'dosage': '1 tds',
    });
  });

  test('a consultation band prices off the prescriber row', () {
    final doctor = {
      'consultation_fees': {'A': '1500.00', 'B': '2500.00'},
    };
    expect(consultationFee(doctor, 'b'), 2500);
    // Anything outside A-E costs nothing, same as the server.
    expect(consultationFee(doctor, 'Z'), 0);
    expect(consultationFee(doctor, ''), 0);
  });

  test('a wallet movement only carries a method when money arrived', () {
    final topUp = walletBody('500', method: 'transfer', note: ' ');
    expect(topUp['method'], 'transfer');
    // Blank notes are dropped rather than stored as whitespace.
    expect(topUp.containsKey('note'), isFalse);
    // Nothing crossed the counter on a deduction, so no method does either.
    expect(walletBody('500', topUp: false).containsKey('method'), isFalse);
  });

  test('a wallet short of the bill pays what it can and owes the rest', () {
    expect(walletSplit('1000', '250'), (paid: 250.0, credit: 0.0));
    expect(walletSplit('100', '250'), (paid: 100.0, credit: 150.0));
    // An empty wallet funds nothing; the whole bill becomes debt.
    expect(walletSplit(null, '250'), (paid: 0.0, credit: 250.0));
  });

  test('applying a stocktake is the admin\'s, counting is not', () {
    expect(stockCheckActions('pending', 'pharmacist'), ['count', 'cancel']);
    expect(stockCheckActions('in_progress', 'pharmacist'),
        ['count', 'cancel']);
    expect(stockCheckActions('in_progress', 'tenant_admin'),
        ['count', 'complete', 'cancel']);
    expect(stockCheckActions('completed', 'tenant_admin'), isEmpty);
  });

  test('only the admin moves stock between stores; anyone receives it', () {
    expect(transferActions('pending', 'pharmacist'), isEmpty);
    expect(transferActions('pending', 'tenant_admin'), ['approve', 'reject']);
    expect(transferActions('approved', 'pharmacist'), ['receive']);
    expect(transferActions('received', 'tenant_admin'), isEmpty);
  });

  test('only the dispenser withdraws a basket, only a cashier takes one', () {
    expect(
        paymentRequestActions('pending', 'pharmacist',
            mine: true, cashier: false),
        ['complete', 'cancel']);
    expect(
        paymentRequestActions('pending', 'pharmacist',
            mine: false, cashier: true),
        ['accept', 'reject', 'complete']);
    expect(
        paymentRequestActions('completed', 'tenant_admin',
            mine: true, cashier: true),
        isEmpty);
  });
}
