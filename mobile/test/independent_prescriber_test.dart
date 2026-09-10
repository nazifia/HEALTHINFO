import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/api.dart';

/// An independent prescriber holds a licence and staffs no facility, so the
/// menu has to wait for them to pick one: every tenant-scoped screen answers
/// 403 until they do. Mirrors tests/test_independent_prescriber.py.
void main() {
  final home = File('lib/screens/home_screen.dart').readAsStringSync();
  final picker = File('lib/screens/facility_picker_screen.dart').readAsStringSync();
  final apiSrc = File('lib/api.dart').readAsStringSync();

  test('the flag comes off the server row, never guessed from the role', () {
    expect(Api.isIndependent({'role': 'doctor', 'is_independent': true}), isTrue);
    // A doctor on a facility's staff is not one, tenant or no tenant on the
    // map the client happens to hold.
    expect(Api.isIndependent({'role': 'doctor', 'tenant': 3}), isFalse);
    expect(Api.isIndependent({'role': 'super_admin', 'tenant': null}), isFalse);
    expect(Api.isIndependent(null), isFalse);
  });

  test('an independent seat is in no module, so it holds no grants', () {
    final seat = {'role': 'doctor', 'is_independent': true, 'tenant': null};
    expect(Api.moduleOf(seat), isNull);
    expect(Api.grantsOf(seat), isEmpty);
    expect(Api.canManageUsers(seat), isFalse);
  });

  test('the drawer waits for a facility before it offers anything else', () {
    // Empty tenant: the picker is the home and Account is the only group.
    expect(home, contains('if (tenantSlug.isEmpty) {'));
    expect(home, contains('_setGroups([_accountGroup], home: _facilityHome);'));
    // Picked one: the clinical menu, with the way back to the picker in it.
    expect(home, contains('_facilityAccountGroup'));
    expect(home, contains("_Section(\n      'Change facility'"));
  });

  test('the chip that changes facility is offered to the seats that can', () {
    expect(home,
        contains("(_role == 'super_admin' || _independent) && tenantSlug.isNotEmpty"));
  });

  test('the picker reads the server list and nothing wider', () {
    // getAll, not getList: a state with more than one page of facilities
    // would otherwise hide the rest of them from the picker.
    expect(apiSrc, contains("getAll('/api/tenants/prescribing/')"));
    expect(picker, contains('api.prescribingFacilities()'));
    // Picking is a scope change: the cached seat carried the last facility's
    // tenant and idle timeout.
    expect(picker, contains('api.forgetMe()'));
  });

  test('only the platform admin\'s step out is trailed', () {
    expect(apiSrc, contains("if (_me?['role'] == 'super_admin') {"));
  });
}
