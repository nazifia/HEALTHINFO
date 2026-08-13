import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_info_app/shared/widgets/searchable_dropdown.dart';

List<String> _labels(List<DropdownMenuItem<String>> items) =>
    [for (final i in items) (i.child as Text).data!];

void main() {
  test('ranks literal matches over fuzzy ones', () {
    const items = [
      DropdownMenuItem(value: 'a', child: Text('Amoxicillin/Clavulanate')),
      DropdownMenuItem(value: 'b', child: Text('Co-amoxiclav')),
      DropdownMenuItem(value: 'c', child: Text('Amoxicillin')),
      DropdownMenuItem(value: 'd', child: Text('Metronidazole')),
    ];

    // exact first, then prefix
    expect(_labels(rankDropdownMatches(items, 'amoxicillin')),
        ['Amoxicillin', 'Amoxicillin/Clavulanate']);
    // word-start match ('Co-amoxiclav') outranks the mid-word one
    expect(_labels(rankDropdownMatches(items, 'amoxic')), [
      'Amoxicillin/Clavulanate',
      'Amoxicillin',
      'Co-amoxiclav',
    ]);
    // subsequence only, and only when nothing literal matches
    expect(_labels(rankDropdownMatches(items, 'amx')),
        ['Amoxicillin/Clavulanate', 'Co-amoxiclav', 'Amoxicillin']);
    expect(rankDropdownMatches(items, 'zzz'), isEmpty);
    expect(rankDropdownMatches(items, '  '), items);
  });

  testWidgets('searchable: false drops the filter box', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SearchableDropdown<String>(
          initialValue: 'M',
          searchable: false,
          items: const [
            DropdownMenuItem(value: 'M', child: Text('Male')),
            DropdownMenuItem(value: 'F', child: Text('Female')),
          ],
          onChanged: (_) {},
        ),
      ),
    ));
    await tester.tap(find.text('Male'));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Female'), findsOneWidget);
  });

  testWidgets('filters options and reports the pick', (tester) async {
    String? picked;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SearchableDropdown<String>(
          initialValue: 'Abia',
          decoration: const InputDecoration(labelText: 'State'),
          items: const [
            DropdownMenuItem(value: 'Abia', child: Text('Abia')),
            DropdownMenuItem(value: 'Kano', child: Text('Kano')),
            DropdownMenuItem(value: 'Lagos', child: Text('Lagos')),
          ],
          onChanged: (v) => picked = v,
        ),
      ),
    ));

    await tester.tap(find.text('Abia'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'lag');
    await tester.pumpAndSettle();
    expect(find.text('Kano'), findsNothing);

    await tester.tap(find.text('Lagos'));
    await tester.pumpAndSettle();
    expect(picked, 'Lagos');
    expect(find.text('Lagos'), findsOneWidget); // now the closed field's label
  });
}
