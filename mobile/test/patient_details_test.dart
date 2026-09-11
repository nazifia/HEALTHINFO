import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/screens/my_health_screen.dart';

void main() {
  testWidgets('the full record shows every served field, blanks as a dash',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: PatientDetailsCard(me: const {
      'hospital_number': '4877634883',
      'full_name': 'Demo Patient',
      'blood_group': 'AB+',
      'allergies': [],
      'next_of_kin_name': null,
      'chronic_condition_names': ['Asthma'],
    }))));
    expect(find.text('Hospital number'), findsOneWidget);
    expect(find.text('4877634883'), findsOneWidget);
    expect(find.text('AB+'), findsOneWidget);
    expect(find.text('—'), findsNWidgets(2)); // allergies, next of kin
    expect(find.text('Asthma'), findsOneWidget);
    // A field the API did not send gets no row at all.
    expect(find.text('Genotype'), findsNothing);
  });
}
