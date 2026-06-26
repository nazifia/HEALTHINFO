import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/theme/enhanced_theme.dart';
import 'glass_card.dart';
import 'icon_chip.dart';

/// Shared design kit for the stats screens (analytics, dashboard, facility
/// metrics). One header treatment, one KPI tile, one section card, plus the
/// richer charts (donut, sparkline, comparison bars) so all three screens read
/// as one product. Keep new chart widgets here; bar/line charts live in
/// bar_chart.dart.

/// Hero header: big title, optional subtitle, optional trailing action
/// (e.g. a date-range button). Sits at the top of every stats screen.
class StatsHeader extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? subtitle;
  final Color color;
  final Widget? trailing;
  const StatsHeader({
    super.key,
    required this.icon,
    required this.title,
    this.subtitle,
    this.color = EnhancedTheme.primaryTeal,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [color, color.withValues(alpha: 0.55)],
              ),
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: color.withValues(alpha: 0.35),
                  blurRadius: 16,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Icon(icon, color: Colors.white, size: 24),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w800,
                      fontSize: 24,
                      height: 1.05,
                    )),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(subtitle!,
                      style: TextStyle(color: context.hintColor, fontSize: 13)),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// Big-number KPI tile: tinted icon, value, label, optional sparkline trend
/// and optional delta badge. Designed to sit inside a [KpiRow].
class KpiTile extends StatelessWidget {
  final IconData icon;
  final String value;
  final String label;
  final Color color;

  /// Optional inline trend drawn under the value.
  final List<num>? spark;

  /// Optional signed delta, e.g. "+12%". Green if it starts with '+', red '-'.
  final String? delta;

  const KpiTile({
    super.key,
    required this.icon,
    required this.value,
    required this.label,
    this.color = EnhancedTheme.primaryTeal,
    this.spark,
    this.delta,
  });

  @override
  Widget build(BuildContext context) {
    final deltaColor = delta == null
        ? null
        : delta!.startsWith('-')
            ? EnhancedTheme.errorRed
            : EnhancedTheme.successGreen;
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              IconChip(icon: icon, color: color, size: 18),
              const Spacer(),
              if (delta != null)
                Text(delta!,
                    style: TextStyle(
                        color: deltaColor,
                        fontSize: 12,
                        fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 12),
          Text(value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.outfit(
                color: context.labelColor,
                fontWeight: FontWeight.w800,
                fontSize: 28,
                height: 1.0,
              )),
          const SizedBox(height: 4),
          Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  color: context.hintColor,
                  fontSize: 12,
                  fontWeight: FontWeight.w500)),
          if (spark != null && spark!.length > 1) ...[
            const SizedBox(height: 10),
            SizedBox(height: 28, child: Sparkline(values: spark!, color: color)),
          ],
        ],
      ),
    );
  }
}

/// Lays KPI tiles out two-per-row, wrapping to new rows as needed. Equal-width
/// tiles, consistent gaps.
class KpiRow extends StatelessWidget {
  final List<KpiTile> tiles;
  const KpiRow({super.key, required this.tiles});

  @override
  Widget build(BuildContext context) {
    const gap = 12.0;
    return LayoutBuilder(builder: (context, c) {
      final w = (c.maxWidth - gap) / 2;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final t in tiles) SizedBox(width: w, child: t),
        ],
      );
    });
  }
}

/// Unified card scaffold for a titled section: icon chip + heading, optional
/// trailing widget, then the child. Replaces the per-screen header rows.
class StatSection extends StatelessWidget {
  final IconData icon;
  final String heading;
  final Widget child;
  final Color color;
  final Widget? trailing;
  const StatSection({
    super.key,
    required this.icon,
    required this.heading,
    required this.child,
    this.color = EnhancedTheme.primaryTeal,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              IconChip(icon: icon, color: color),
              const SizedBox(width: 10),
              Expanded(
                child: Text(heading,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    )),
              ),
              ?trailing,
            ]),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

/// One label/value stat used inside metric rows (smaller than a [KpiTile]).
class StatMetric extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  const StatMetric(this.label, this.value, {super.key, this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(value,
            style: GoogleFonts.outfit(
              color: color ?? context.labelColor,
              fontWeight: FontWeight.w800,
              fontSize: 22,
            )),
        Text(label,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: context.hintColor, fontSize: 11)),
      ],
    );
  }
}

/// Ratio donut with a centered percentage/label. [value] of [total] is filled
/// in [color]; the remainder is a faint track.
class DonutChart extends StatelessWidget {
  final num value;
  final num total;
  final Color color;
  final String centerLabel;
  final String centerSub;
  final double size;
  const DonutChart({
    super.key,
    required this.value,
    required this.total,
    required this.centerLabel,
    this.centerSub = '',
    this.color = EnhancedTheme.primaryTeal,
    this.size = 120,
  });

  @override
  Widget build(BuildContext context) {
    final rest = (total - value).clamp(0, double.infinity).toDouble();
    final track = context.isDark
        ? Colors.white.withValues(alpha: 0.07)
        : Colors.black.withValues(alpha: 0.06);
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          PieChart(PieChartData(
            startDegreeOffset: -90,
            sectionsSpace: 0,
            centerSpaceRadius: size * 0.32,
            sections: [
              PieChartSectionData(
                value: value.toDouble(),
                color: color,
                radius: size * 0.18,
                showTitle: false,
              ),
              PieChartSectionData(
                // Avoid a zero-sum chart rendering nothing.
                value: total <= 0 ? 1 : rest,
                color: track,
                radius: size * 0.18,
                showTitle: false,
              ),
            ],
          )),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(centerLabel,
                  style: GoogleFonts.outfit(
                    color: context.labelColor,
                    fontWeight: FontWeight.w800,
                    fontSize: 22,
                  )),
              if (centerSub.isNotEmpty)
                Text(centerSub,
                    style: TextStyle(color: context.hintColor, fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}

/// Tiny axis-less trend line for inside KPI tiles.
class Sparkline extends StatelessWidget {
  final List<num> values;
  final Color color;
  const Sparkline({super.key, required this.values, this.color = EnhancedTheme.primaryTeal});

  @override
  Widget build(BuildContext context) {
    final spots = [
      for (var i = 0; i < values.length; i++)
        FlSpot(i.toDouble(), values[i].toDouble()),
    ];
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    return LineChart(LineChartData(
      minY: 0,
      maxY: (maxY <= 0 ? 1 : maxY) * 1.15,
      gridData: const FlGridData(show: false),
      borderData: FlBorderData(show: false),
      titlesData: const FlTitlesData(show: false),
      lineTouchData: const LineTouchData(enabled: false),
      lineBarsData: [
        LineChartBarData(
          spots: spots,
          isCurved: true,
          curveSmoothness: 0.3,
          color: color,
          barWidth: 2,
          dotData: FlDotData(show: spots.length == 1),
          belowBarData: BarAreaData(
            show: true,
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [color.withValues(alpha: 0.25), color.withValues(alpha: 0.0)],
            ),
          ),
        ),
      ],
    ));
  }
}

/// Horizontal you-vs-peers comparison bars. Each row is drawn as a fractional
/// fill of the largest value, with the value printed at the end.
class ComparisonBars extends StatelessWidget {
  final List<({String label, num value, Color color})> rows;
  const ComparisonBars({super.key, required this.rows});

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return Text('No data yet.',
          style: TextStyle(color: context.hintColor, fontSize: 13));
    }
    final max = rows.map((r) => r.value).reduce((a, b) => a > b ? a : b);
    final denom = max <= 0 ? 1.0 : max.toDouble();
    final track = context.isDark
        ? Colors.white.withValues(alpha: 0.06)
        : Colors.black.withValues(alpha: 0.05);
    return Column(
      children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(r.label,
                        style: TextStyle(
                            color: context.subLabelColor, fontSize: 12)),
                    Text('${r.value}',
                        style: TextStyle(
                            color: r.color,
                            fontSize: 13,
                            fontWeight: FontWeight.w800)),
                  ],
                ),
                const SizedBox(height: 4),
                ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: Stack(
                    children: [
                      Container(height: 8, color: track),
                      FractionallySizedBox(
                        widthFactor: (r.value / denom).clamp(0.0, 1.0),
                        child: Container(
                          height: 8,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(colors: [
                              r.color.withValues(alpha: 0.6),
                              r.color,
                            ]),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

String pctOf(num? ratio) => ratio == null ? '—' : '${(ratio * 100).round()}%';
