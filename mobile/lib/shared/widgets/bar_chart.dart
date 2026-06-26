import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../../core/theme/enhanced_theme.dart';

/// Vertical bar chart (fl_chart) with tap tooltips.
/// One bar per row; full label + value shown in the tooltip since x-axis
/// labels are truncated to fit. Each bar cycles through [palette] so rows
/// are visually distinct.
class MiniBarChart extends StatelessWidget {
  final List<({String label, num value})> rows;
  const MiniBarChart({
    super.key,
    required this.rows,
  });

  static const List<Color> palette = [
    EnhancedTheme.primaryTeal,
    EnhancedTheme.accentPurple,
    EnhancedTheme.accentOrange,
    EnhancedTheme.accentCyan,
    EnhancedTheme.infoBlue,
    EnhancedTheme.successGreen,
    EnhancedTheme.errorRed,
  ];

  Color _barColor(int i) => palette[i % palette.length];

  /// Show whole numbers plain, trim trailing zeros otherwise (e.g. 12, 3.5).
  static String fmt(num v) =>
      v == v.roundToDouble() ? v.toInt().toString() : '$v';

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return Text('No data yet.',
          style: TextStyle(color: context.hintColor, fontSize: 13));
    }
    final maxValue = rows.map((r) => r.value).reduce((a, b) => a > b ? a : b);
    final maxY = (maxValue <= 0 ? 1 : maxValue) * 1.25;
    final track = context.isDark
        ? Colors.white.withValues(alpha: 0.04)
        : Colors.black.withValues(alpha: 0.03);

    return SizedBox(
      height: 190,
      child: BarChart(
        BarChartData(
          maxY: maxY.toDouble(),
          alignment: BarChartAlignment.spaceAround,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            horizontalInterval: maxY / 4,
            getDrawingHorizontalLine: (_) =>
                FlLine(color: context.dividerColor, strokeWidth: 1),
          ),
          borderData: FlBorderData(show: false),
          barTouchData: BarTouchData(
            touchTooltipData: BarTouchTooltipData(
              getTooltipColor: (_) => EnhancedTheme.primaryDark,
              getTooltipItem: (group, _, rod, _) => BarTooltipItem(
                '${rows[group.x].label}\n',
                const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    fontSize: 12),
                children: [
                  TextSpan(
                    text: fmt(rows[group.x].value),
                    style: TextStyle(
                        color: _barColor(group.x),
                        fontWeight: FontWeight.w800,
                        fontSize: 13),
                  ),
                ],
              ),
            ),
          ),
          titlesData: FlTitlesData(
            topTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 44,
                getTitlesWidget: (value, meta) {
                  final i = value.toInt();
                  if (i < 0 || i >= rows.length) return const SizedBox.shrink();
                  final label = rows[i].label;
                  final short =
                      label.length > 8 ? '${label.substring(0, 7)}…' : label;
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(fmt(rows[i].value),
                            style: TextStyle(
                                color: _barColor(i),
                                fontSize: 11,
                                fontWeight: FontWeight.w800)),
                        const SizedBox(height: 2),
                        Text(short,
                            style: TextStyle(
                                color: context.hintColor, fontSize: 10)),
                      ],
                    ),
                  );
                },
              ),
            ),
          ),
          barGroups: [
            for (var i = 0; i < rows.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: rows[i].value.toDouble(),
                    width: 18,
                    borderRadius:
                        const BorderRadius.vertical(top: Radius.circular(6)),
                    backDrawRodData: BackgroundBarChartRodData(
                      show: true,
                      toY: maxY.toDouble(),
                      color: track,
                    ),
                    gradient: LinearGradient(
                      begin: Alignment.bottomCenter,
                      end: Alignment.topCenter,
                      colors: [
                        _barColor(i).withValues(alpha: 0.65),
                        _barColor(i),
                      ],
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

/// Time-series line chart. rows are ordered oldest→newest; x is the index,
/// y is the value. Used for any trailing-window trend (search volume, case
/// volume, …). Axis labels are omitted to match the compact card style.
class TrendLineChart extends StatelessWidget {
  final List<({String period, num value})> rows;
  final Color color;
  const TrendLineChart({
    super.key,
    required this.rows,
    this.color = EnhancedTheme.primaryTeal,
  });

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return Text('No data yet.',
          style: TextStyle(color: context.hintColor, fontSize: 13));
    }
    final spots = [
      for (var i = 0; i < rows.length; i++)
        FlSpot(i.toDouble(), rows[i].value.toDouble()),
    ];
    final maxRaw = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    final maxY = (maxRaw <= 0 ? 1 : maxRaw) * 1.2;
    return SizedBox(
      height: 170,
      child: LineChart(LineChartData(
        minY: 0,
        maxY: maxY,
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: maxY / 4,
          getDrawingHorizontalLine: (_) =>
              FlLine(color: context.dividerColor, strokeWidth: 1),
        ),
        borderData: FlBorderData(show: false),
        titlesData: const FlTitlesData(show: false),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => EnhancedTheme.primaryDark,
            getTooltipItems: (spots) => [
              for (final s in spots)
                LineTooltipItem(
                  rows[s.x.toInt()].period,
                  const TextStyle(
                      color: Colors.white70,
                      fontSize: 11,
                      fontWeight: FontWeight.w500),
                  children: [
                    TextSpan(
                      text: '\n${MiniBarChart.fmt(rows[s.x.toInt()].value)}',
                      style: TextStyle(
                          color: color,
                          fontSize: 14,
                          fontWeight: FontWeight.w800),
                    ),
                  ],
                ),
            ],
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            curveSmoothness: 0.3,
            color: color,
            barWidth: 3,
            // A single point draws no line segment; show the dot so it's visible.
            dotData: FlDotData(show: spots.length == 1),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  color.withValues(alpha: 0.28),
                  color.withValues(alpha: 0.0),
                ],
              ),
            ),
          ),
        ],
      )),
    );
  }
}
