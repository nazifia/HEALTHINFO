import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The ward's tiles open a drawer section by its label, so a renamed section
/// would leave a tile that does nothing — silently, at runtime. Both lists are
/// private consts in their own files, so this reads the source.
void main() {
  final ward = File('lib/screens/ward_screen.dart').readAsStringSync();
  final home = File('lib/screens/home_screen.dart').readAsStringSync();

  test('every ward register names a section the drawer has', () {
    final labels = RegExp(r"_Register\(\s*'([^']+)'")
        .allMatches(ward)
        .map((m) => m.group(1)!)
        .toSet();
    expect(labels, isNotEmpty);
    final sections = RegExp(r"_Section\(\s*'([^']+)'")
        .allMatches(home)
        .map((m) => m.group(1)!)
        .toSet();
    for (final label in labels) {
      expect(sections, contains(label),
          reason: 'ward tile "$label" opens a section the drawer has not got');
    }
  });

  test('every cadre the drawer sends to the ward has registers there', () {
    final roles = RegExp(r"_wardRoles = \{([^}]*)\}").firstMatch(home)!.group(1)!;
    final listed = RegExp(r"'([a-z_]+)'")
        .allMatches(roles)
        .map((m) => m.group(1)!)
        .toSet();
    expect(listed, {'doctor', 'nurse', 'midwife', 'chew'});
    for (final role in listed) {
      expect(ward, contains("'$role': ["), reason: '$role files nothing');
    }
  });

  test('every cadre lands on a register the FAB can file into', () {
    // The FAB files the first register in a cadre's list, so each of those
    // needs a form here; a renamed form would otherwise just stop appearing.
    final primaries = RegExp(r"'[a-z]+': \[_([A-Za-z]+),")
        .allMatches(ward)
        .map((m) => m.group(1)!)
        .toSet();
    expect(primaries, isNotEmpty);
    final withForms = RegExp(r"_([A-Za-z]+)\.label: (\w+),")
        .allMatches(ward)
        .map((m) => m.group(1)!)
        .toSet();
    expect(withForms, containsAll(primaries));
  });
}
