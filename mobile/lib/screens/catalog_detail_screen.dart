import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../resources.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/responsive.dart';
import 'catalog_edit_screen.dart';
import 'graph_screen.dart';

class CatalogDetailScreen extends StatefulWidget {
  final CatalogResource resource;
  final Map<String, dynamic> row;
  const CatalogDetailScreen({
    super.key,
    required this.resource,
    required this.row,
  });

  @override
  State<CatalogDetailScreen> createState() => _CatalogDetailScreenState();
}

class _CatalogDetailScreenState extends State<CatalogDetailScreen> {
  late Map<String, dynamic> row = widget.row;

  Future<void> _edit() async {
    final updated = await Navigator.of(context).push<Map<String, dynamic>>(
      MaterialPageRoute(
        builder: (_) => CatalogEditScreen(resource: widget.resource, row: row),
      ),
    );
    if (updated != null && mounted) setState(() => row = updated);
  }

  @override
  Widget build(BuildContext context) {
    final resource = widget.resource;
    final title = row[resource.titleField]?.toString() ?? resource.label;
    final sub = resource.subtitleField == null
        ? ''
        : (row[resource.subtitleField]?.toString() ?? '');
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      // Edit FAB only for write-role users; backend still enforces this.
      floatingActionButton: FutureBuilder<String?>(
        future: api.myRole(),
        builder: (context, snap) {
          if (!api.roleCanWrite(snap.data)) return const SizedBox.shrink();
          return FloatingActionButton.extended(
            onPressed: _edit,
            backgroundColor: EnhancedTheme.primaryTeal,
            foregroundColor: Colors.white,
            icon: const Icon(Icons.edit_outlined),
            label: const Text('Edit'),
          );
        },
      ),
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          CappedWidth(
            child: CustomScrollView(
            slivers: [
              SliverAppBar.large(
                pinned: true,
                expandedHeight: 200,
                backgroundColor: Colors.transparent,
                foregroundColor: Colors.white,
                flexibleSpace: FlexibleSpaceBar(
                  titlePadding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  title: Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  background: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          EnhancedTheme.primaryTeal,
                          EnhancedTheme.accentCyan,
                        ],
                      ),
                      borderRadius: const BorderRadius.vertical(
                          bottom: Radius.circular(28)),
                    ),
                    child: Align(
                      alignment: const Alignment(0.85, -0.35),
                      child: Icon(resource.icon,
                          size: 120,
                          color: Colors.white.withValues(alpha: 0.18)),
                    ),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.all(16),
                sliver: SliverList.list(
                  children: [
                    if (sub.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 14, vertical: 8),
                            decoration: BoxDecoration(
                              color: EnhancedTheme.primaryTeal
                                  .withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(
                                  color: EnhancedTheme.primaryTeal
                                      .withValues(alpha: 0.3)),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(resource.icon,
                                    size: 16,
                                    color: EnhancedTheme.primaryTeal),
                                const SizedBox(width: 6),
                                Flexible(
                                  child: Text('${resource.subtitleLabel}: $sub',
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                        color: EnhancedTheme.primaryTeal,
                                        fontWeight: FontWeight.w600,
                                        fontSize: 13,
                                      )),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    if (graphPath(resource.path, row['id']) != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: OutlinedButton.icon(
                          icon: const Icon(Icons.hub_outlined),
                          label: const Text('View relationships'),
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => GraphScreen(
                                title: title,
                                path: graphPath(resource.path, row['id'])!,
                              ),
                            ),
                          ),
                        ),
                      ),
                    for (final s in resource.sections)
                      if ((row[s.key]?.toString().trim().isNotEmpty) ?? false)
                        _Section(title: s.heading, body: row[s.key].toString()),
                    for (final link in resource.links)
                      if (resourceByPath(link.path) != null &&
                          (row[link.key] is List) &&
                          (row[link.key] as List).isNotEmpty)
                        _LinkSection(
                          heading: link.heading,
                          ids: (row[link.key] as List).cast(),
                          target: resourceByPath(link.path)!,
                        ),
                  ],
                ),
              ),
            ],
          ),
          ),
        ],
      ),
    );
  }
}

/// Fetches the linked rows by id and lists them as tappable chips.
class _LinkSection extends StatefulWidget {
  final String heading;
  final List<dynamic> ids;
  final CatalogResource target;
  const _LinkSection({
    required this.heading,
    required this.ids,
    required this.target,
  });

  @override
  State<_LinkSection> createState() => _LinkSectionState();
}

class _LinkSectionState extends State<_LinkSection> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    // ponytail: N parallel GETs by id — fine for a handful of links.
    // Add a ?ids= bulk endpoint server-side if a record links to many rows.
    _future = Future.wait(widget.ids.map((id) async {
      final r = await api.get('${widget.target.path}$id/');
      return (r as Map).cast<String, dynamic>();
    }));
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.heading,
                style: GoogleFonts.outfit(
                  color: context.labelColor,
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                )),
            const SizedBox(height: 10),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: _future,
              builder: (context, snap) {
                if (snap.connectionState == ConnectionState.waiting) {
                  return const Padding(
                    padding: EdgeInsets.all(8),
                    child: SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: EnhancedTheme.primaryTeal),
                    ),
                  );
                }
                if (snap.hasError) {
                  return Text('Could not load (${snap.error})',
                      style: const TextStyle(color: EnhancedTheme.errorRed));
                }
                final rows = snap.data ?? [];
                return Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final r in rows)
                      _LinkChip(
                        label: r[widget.target.titleField]?.toString() ?? '—',
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => CatalogDetailScreen(
                              resource: widget.target,
                              row: r,
                            ),
                          ),
                        ),
                      ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _LinkChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _LinkChip({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: EnhancedTheme.accentCyan.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
                color: EnhancedTheme.accentCyan.withValues(alpha: 0.3)),
          ),
          child: Text(label,
              style: const TextStyle(
                color: EnhancedTheme.accentCyan,
                fontWeight: FontWeight.w600,
                fontSize: 13,
              )),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final String body;
  const _Section({required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: GoogleFonts.outfit(
                  color: context.labelColor,
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                )),
            const SizedBox(height: 8),
            Text(body,
                style: TextStyle(
                  color: context.subLabelColor,
                  height: 1.5,
                  fontSize: 14,
                )),
          ],
        ),
      ),
    );
  }
}
