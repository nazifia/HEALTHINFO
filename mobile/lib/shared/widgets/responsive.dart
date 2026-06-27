import 'package:flutter/material.dart';

/// Single breakpoint for the whole app. Above it = tablet/desktop layout.
const double kWideBreakpoint = 900;

bool isWide(BuildContext context) =>
    MediaQuery.of(context).size.width >= kWideBreakpoint;

/// Centers and width-caps its child. Use to stop pushed full-screen routes
/// (detail/edit/search) stretching across a wide monitor.
class CappedWidth extends StatelessWidget {
  final Widget child;
  final double maxWidth;
  const CappedWidth({super.key, required this.child, this.maxWidth = 1100});

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: child,
        ),
      );
}

/// A scrollable collection of equal-width cards: one column on phones, two on
/// wide screens. Drop-in for the report/catalog ListViews so the extra width
/// holds more cards instead of stretching one. Works under RefreshIndicator.
class CardGrid extends StatelessWidget {
  final int itemCount;
  final IndexedWidgetBuilder itemBuilder;

  /// Optional full-width widget pinned above the cards (e.g. a KPI header).
  final Widget? header;
  final EdgeInsets padding;
  const CardGrid({
    super.key,
    required this.itemCount,
    required this.itemBuilder,
    this.header,
    this.padding = const EdgeInsets.fromLTRB(16, 12, 16, 96),
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      // 1 col phone, 2 col tablet/desktop, 3 col ultrawide.
      final cols = c.maxWidth >= 1400
          ? 3
          : c.maxWidth >= kWideBreakpoint
              ? 2
              : 1;
      if (cols == 1) {
        final hasHeader = header != null;
        return ListView.separated(
          padding: padding,
          physics: const AlwaysScrollableScrollPhysics(),
          itemCount: itemCount + (hasHeader ? 1 : 0),
          separatorBuilder: (_, _) => const SizedBox(height: 10),
          itemBuilder: (ctx, i) {
            if (hasHeader && i == 0) return header!;
            return itemBuilder(ctx, i - (hasHeader ? 1 : 0));
          },
        );
      }
      const gap = 12.0;
      final tileW = (c.maxWidth - padding.horizontal - gap * (cols - 1)) / cols;
      return SingleChildScrollView(
        padding: padding,
        physics: const AlwaysScrollableScrollPhysics(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (header != null)
              Padding(padding: const EdgeInsets.only(bottom: 12), child: header!),
            Wrap(
              spacing: gap,
              runSpacing: gap,
              children: [
                for (var i = 0; i < itemCount; i++)
                  SizedBox(width: tileW, child: itemBuilder(context, i)),
              ],
            ),
          ],
        ),
      );
    });
  }
}
