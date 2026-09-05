// Row shaping for the prescribing breakdowns, kept out of the screens so the
// formatting is testable and the two screens phrase "filled" the same way.

/// Appends how many of the orders behind a bar were actually dispensed.
///
/// A bar is a count of orders *written*. Written and handed over are different
/// numbers, and a bar alone cannot say which it is showing — so the label
/// carries the filled count next to it. Rows from an older API with no
/// ``dispensed`` field keep their bare label rather than reading "0 filled".
String withFilled(String label, dynamic count, dynamic dispensed) =>
    dispensed is num ? '$label ($dispensed of $count filled)' : label;

/// Flattens the API's diagnosis-and-medication pairs into label/count rows.
///
/// One row per "what was prescribed for what". The diagnosis arrives as "—"
/// when the order was written with no case linked to it, and those rows are
/// kept: a drug with no recorded reason is a gap worth seeing.
List<Map<String, dynamic>> diagnosisPairRows(dynamic pairs) => [
      for (final p in (pairs as List?) ?? [])
        {
          'pair': withFilled(
              '${p['diagnosis']} · ${p['medication']}', p['count'], p['dispensed']),
          'count': p['count'],
        }
    ];

/// The same treatment for a single-drug breakdown ("prescribed for these
/// cases"), which carries a medication name instead of a pair.
List<Map<String, dynamic>> prescribedRows(dynamic rows) => [
      for (final r in (rows as List?) ?? [])
        {
          'medication':
              withFilled('${r['medication']}', r['count'], r['dispensed']),
          'count': r['count'],
        }
    ];

/// The same treatment for a diagnosis breakdown ("top diagnoses"), which
/// carries a diagnosis name and the prescribing written against it.
List<Map<String, dynamic>> diagnosisRows(dynamic rows) => [
      for (final r in (rows as List?) ?? [])
        {
          'diagnosis':
              withFilled('${r['diagnosis']}', r['count'], r['dispensed']),
          'count': r['count'],
        }
    ];

/// The pair rows behind one diagnosis — the drilldown for a tapped bar.
///
/// With nothing selected the list is capped, because the panel is a chart and
/// thirty bars is not readable. A selection shows every pair it has, which is
/// why the API sends more pairs than the panel draws.
List<dynamic> pairsFor(dynamic pairs, String? diagnosis, {int limit = 10}) {
  final all = (pairs as List?) ?? [];
  if (diagnosis == null) return all.take(limit).toList();
  return [
    for (final p in all)
      if ('${p['diagnosis']}' == diagnosis) p
  ];
}
