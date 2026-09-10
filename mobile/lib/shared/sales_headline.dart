// Row shaping for the state-sales rollup (/api/analytics/platform/sales/),
// kept out of the screen so the arithmetic is testable. Mirrors
// salesHeadline() in web/app.js.

/// One headline figure: what every pharmacy in the patch sold in one period.
typedef SalesPeriod = ({String bucket, String period, num revenue, num sales});

const _buckets = ['daily', 'monthly', 'yearly'];

/// Money arrives as a DRF decimal string ("250.50"), not a JSON number.
num _money(dynamic v) => v is num ? v : num.tryParse('$v') ?? 0;

/// The latest day, month and year the payload carries, each summed across every
/// area in it.
///
/// Rows are one per (area, period), so a period's total is the sum of its rows.
/// With a ?from/to window the latest period in range is not today, so the
/// period travels with the figure rather than being assumed.
List<SalesPeriod> salesHeadline(Map? data) {
  final out = <SalesPeriod>[];
  for (final bucket in _buckets) {
    final rows = _rowsFor(data, bucket);
    if (rows.isEmpty) continue;
    out.add((
      bucket: bucket,
      period: rows.first['period'] as String,
      revenue: rows.fold<num>(0, (t, r) => t + _money(r['revenue'])),
      sales: rows.fold<num>(0, (t, r) => t + _money(r['sales'])),
    ));
  }
  return out;
}

/// The same latest period, left per area, for the bar chart: one row per state
/// (or per local government, for a seat that answers for one).
List<Map<String, dynamic>> salesByArea(Map? data, String bucket) {
  final level = '${data?['level'] ?? 'state'}';
  return [
    for (final r in _rowsFor(data, bucket))
      {'area': '${r[level] ?? '—'}', 'revenue': _money(r['revenue'])}
  ];
}

/// The rows of one bucket that fall in its latest period. ISO periods sort as
/// strings, so the largest label is the latest one.
List<Map<String, dynamic>> _rowsFor(Map? data, String bucket) {
  final rows = (data?[bucket] as List?)?.cast<Map<String, dynamic>>() ?? [];
  if (rows.isEmpty) return [];
  final latest = rows.fold<String>('', (a, r) {
    final p = '${r['period']}';
    return p.compareTo(a) > 0 ? p : a;
  });
  return [
    for (final r in rows)
      if ('${r['period']}' == latest) {...r, 'period': latest}
  ];
}
