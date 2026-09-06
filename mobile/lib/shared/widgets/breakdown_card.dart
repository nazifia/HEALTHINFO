import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/theme/enhanced_theme.dart';
import 'bar_chart.dart';
import 'glass_card.dart';

/// A headed card holding one grouped-count bar chart — "by region", "by
/// reporter", "by tenant". Every rollup screen draws the same card, so it
/// lives here instead of once per screen.
class BreakdownCard extends StatelessWidget {
  final String heading;
  final IconData icon;
  final List<dynamic> rows;
  final String labelKey;
  final String valueKey;
  final bool asPercent;
  const BreakdownCard({
    super.key,
    required this.heading,
    required this.icon,
    required this.rows,
    required this.labelKey,
    this.valueKey = 'count',
    this.asPercent = false,
  });

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, color: EnhancedTheme.primaryTeal, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(heading,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    )),
              ),
            ]),
            const SizedBox(height: 10),
            MiniBarChart(
              rows: [
                for (final row in rows.cast<Map<String, dynamic>>())
                  (
                    label: '${row[labelKey] ?? ''}',
                    // Show resistance rates as 0-100 so a 0..1 fraction reads sensibly.
                    value: asPercent
                        ? ((row[valueKey] as num?) ?? 0) * 100
                        : (row[valueKey] as num?) ?? 0,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
