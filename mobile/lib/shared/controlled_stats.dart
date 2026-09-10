// Row shaping for the state controlled-drug rollup
// (/api/analytics/platform/controlled/), kept out of the screen so the
// arithmetic is testable. Sibling of sales_headline.dart.

/// One column of the rollup, summed over every area in it.
///
/// Rows are one per area, so the patch's total is the sum of its rows.
num controlledTotal(Map? data, String key) =>
    ((data?['by_area'] as List?) ?? []).fold<num>(
        0, (t, r) => t + ((r as Map)[key] as num? ?? 0));

/// The same column left per area, for the bar chart.
///
/// Rows are keyed by the tier the payload was folded to — 'state', or 'local'
/// for a seat that answers for one — so the level names the label column.
List<Map<String, dynamic>> controlledByArea(Map? data, String key) {
  final level = '${data?['level'] ?? 'state'}';
  return [
    for (final r in ((data?['by_area'] as List?) ?? []).cast<Map>())
      {'area': '${r[level] ?? '—'}', 'value': r[key] ?? 0}
  ];
}

/// The drug rows ranked by one column, biggest first, zeros dropped.
///
/// The payload orders by lines written plus lines sold, so a card that names
/// one column has to rank by that column — otherwise the tallest bar is not
/// the top row. A drug with nothing in the column is not on the card at all.
List<Map<String, dynamic>> controlledByDrug(Map? data, String key) {
  final rows = [
    for (final r in ((data?['by_drug'] as List?) ?? []).cast<Map>())
      if ((r[key] as num? ?? 0) > 0)
        {'drug': '${r['drug'] ?? '—'}', 'value': r[key] as num}
  ];
  rows.sort((a, b) => (b['value'] as num).compareTo(a['value'] as num));
  return rows;
}
