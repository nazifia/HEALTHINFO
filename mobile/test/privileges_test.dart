import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/api.dart';
import 'package:health_info_app/pharmacy.dart';

/// The grant helpers the screens gate on, mirrored from
/// apps/accounts/permissions.py. What a seat may hand out is read off its own
/// row, so a form never offers what the API would refuse.
void main() {
  tearDown(() => myGrants = const {});

  test('a module admin holds its whole catalog, a granted seat only its row', () {
    final admin = {'role': 'tenant_admin', 'tenant': 3};
    expect(Api.grantsOf(admin), {'manage_users', 'pharmacy_admin'});

    final clerk = {'role': 'pharmacist', 'tenant': 3, 'privileges': ['manage_users']};
    expect(Api.grantsOf(clerk), {'manage_users'});
    expect(Api.canManageUsers(clerk), isTrue);

    final plain = {'role': 'pharmacist', 'tenant': 3};
    expect(Api.grantsOf(plain), isEmpty);
    expect(Api.canManageUsers(plain), isFalse);
  });

  test('a grant outside the seat\'s own module counts for nothing', () {
    // The claims desk has no money screens of its own to be trusted with.
    final insurer = {
      'role': 'hmo', 'tenant': 3, 'hmo': 7, 'privileges': ['pharmacy_admin'],
    };
    expect(Api.moduleOf(insurer), 'scheme');
    expect(Api.grantsOf(insurer), isEmpty);

    final authority = {'role': 'government', 'jurisdiction': 2, 'is_admin': true};
    expect(Api.moduleOf(authority), 'oversight');
    expect(Api.grantsOf(authority), {'manage_users'});
  });

  test('a grant is not the role', () {
    // The facility's admin staffs the facility, the tenant_admin seat included.
    expect(Api.manageableRoles({'role': 'tenant_admin', 'tenant': 3}),
        contains('tenant_admin'));
    // Someone trusted with the user list cannot mint the admin who could take
    // that trust back.
    expect(
        Api.manageableRoles(
            {'role': 'pharmacist', 'tenant': 3, 'privileges': ['manage_users']}),
        isNot(contains('tenant_admin')));
    // Each portal staffs its own seats and nobody else's.
    expect(Api.manageableRoles({'role': 'hmo', 'tenant': 3, 'hmo': 7}), ['hmo']);
    expect(Api.manageableRoles({'role': 'government', 'jurisdiction': 2}),
        ['government']);
    // The platform admin is narrowed by nothing.
    expect(Api.manageableRoles({'role': 'super_admin', 'tenant': null}), isNull);
  });

  test('the pharmacy grant opens the money screens', () {
    expect(isPharmacyAdmin('pharmacist'), isFalse);
    myGrants = {'pharmacy_admin'};
    expect(isPharmacyAdmin('pharmacist'), isTrue);
    // Reading a price list is still the admin's; the grant is what says so.
    expect(canEditPriceList('pharmacist'), isTrue);
  });
}
