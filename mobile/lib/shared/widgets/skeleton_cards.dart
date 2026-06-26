import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

import '../../core/theme/enhanced_theme.dart';
import 'glass_card.dart';

/// Shimmering placeholder cards shown while a dashboard/analytics screen loads.
/// Mirrors the real card layout so the page doesn't jump when data arrives.
class SkeletonCards extends StatelessWidget {
  /// Number of tall (chart-height) cards after the optional stat row.
  final int cards;

  /// Show a two-up stat-tile row at the top (dashboard header).
  final bool statRow;

  const SkeletonCards({super.key, this.cards = 3, this.statRow = true});

  @override
  Widget build(BuildContext context) {
    final base = context.isDark
        ? Colors.white.withValues(alpha: 0.06)
        : Colors.black.withValues(alpha: 0.05);
    final highlight = context.isDark
        ? Colors.white.withValues(alpha: 0.14)
        : Colors.black.withValues(alpha: 0.10);

    Widget block(double h, {double w = double.infinity}) => Container(
          width: w,
          height: h,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(8),
          ),
        );

    return Shimmer.fromColors(
      baseColor: base,
      highlightColor: highlight,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          if (statRow) ...[
            Row(children: [
              Expanded(child: _tile(block)),
              const SizedBox(width: 12),
              Expanded(child: _tile(block)),
            ]),
            const SizedBox(height: 12),
          ],
          for (var i = 0; i < cards; i++) ...[
            GlassCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  block(14, w: 160),
                  const SizedBox(height: 16),
                  block(150),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],
        ],
      ),
    );
  }

  Widget _tile(Widget Function(double, {double w}) block) => GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            block(28, w: 28),
            const SizedBox(height: 14),
            block(26, w: 60),
            const SizedBox(height: 8),
            block(11, w: 90),
          ],
        ),
      );
}
