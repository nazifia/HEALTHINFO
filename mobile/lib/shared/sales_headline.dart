// Row shaping for the state-sales rollup (/api/analytics/platform/sales/),
// kept out of the screen so the arithmetic is testable. Mirrors
// salesHeadline() in web/app.js.

/// One headline figure: what every pharmacy in the patch sold in one period.
typedef SalesPeriod = ({String bucket, String period, num revenue, num sales});

// Each bucket with how many characters of the ISO date it keeps:
// 2026-09-09 / 2026-09 / 2026 (the server's _SALES_PERIODS).
const _buckets = {'daily': 10, 'monthly': 7, 'yearly': 4};

/// Money arrives as a DRF decimal string ("250.50"), not a JSON number.
num _money(dynamic v) => v is num ? v : num.tryParse('$v') ?? 0;

/// Today, this month and this year (`now`; the server buckets in UTC), each
/// summed across every area — zero until the first sale lands, never the last
/// day that had one. With no `now` (a ?from/to window, where the latest
/// period in range is not today) the latest period the payload carries.
///
/// Rows are one per (area, period), so a period's total is the sum of its rows.
List<SalesPeriod> salesHeadline(Map? data, {DateTime? now}) {
  final out = <SalesPeriod>[];
  final iso = now?.toUtc().toIso8601String();
  for (final MapEntry(key: bucket, value: width) in _buckets.entries) {
    final period = iso?.substring(0, width);
    final rows = _rowsFor(data, bucket, period: period);
    if (rows.isEmpty && (period == null || data?[bucket] is! List)) continue;
    out.add((
      bucket: bucket,
      period: period ?? rows.first['period'] as String,
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

/// The rows of one bucket that fall in `period`, or in its latest period when
/// none is asked for. ISO periods sort as strings, so the largest label is
/// the latest one.
List<Map<String, dynamic>> _rowsFor(Map? data, String bucket, {String? period}) {
  final rows = (data?[bucket] as List?)?.cast<Map<String, dynamic>>() ?? [];
  if (rows.isEmpty) return [];
  final latest = period ?? rows.fold<String>('', (a, r) {
    final p = '${r['period']}';
    return p.compareTo(a) > 0 ? p : a;
  });
  return [
    for (final r in rows)
      if ('${r['period']}' == latest) {...r, 'period': latest}
  ];
}
