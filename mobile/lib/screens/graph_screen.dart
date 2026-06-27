import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../resources.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/responsive.dart';
import '../shared/widgets/screen_header.dart';
import 'catalog_detail_screen.dart';

/// Relationship view for one catalog record. GETs a `/api/graph/<kind>/<id>/`
/// endpoint and renders each neighbour list as a labelled group of chips.
/// ponytail: grouped chips, not a force-directed canvas — same information,
/// no graph-layout dependency. Swap in a real viz if the edges get dense.
class GraphScreen extends StatefulWidget {
  final String title;
  final String path; // e.g. /api/graph/diseases/12/
  const GraphScreen({super.key, required this.title, required this.path});

  @override
  State<GraphScreen> createState() => _GraphScreenState();
}

class _GraphScreenState extends State<GraphScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final r = await api.get(widget.path);
    return (r as Map).cast<String, dynamic>();
  }

  /// Catalog resource a graph group's rows belong to, so chips can deep-link
  /// to the detail screen. Null for groups with no catalog screen (interactions).
  static const _groupResource = {
    'symptoms': '/api/symptoms/',
    'medications': '/api/medications/',
    'procedures': '/api/procedures/',
    'lab_tests': '/api/lab-tests/',
    'specialties': '/api/specialties/',
    'articles': '/api/articles/',
    'diseases': '/api/diseases/',
    'related_diseases': '/api/diseases/',
    'treats_diseases': '/api/diseases/',
  };

  /// Best human label for a neighbour row across catalog shapes.
  String _label(Map<String, dynamic> row) {
    if (row['medication_a_name'] != null || row['medication_b_name'] != null) {
      return '${row['medication_a_name'] ?? '?'} × ${row['medication_b_name'] ?? '?'}';
    }
    for (final k in ['name', 'generic_name', 'title']) {
      final v = row[k];
      if (v != null && '$v'.trim().isNotEmpty) return '$v';
    }
    return '#${row['id'] ?? '?'}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          SafeArea(
            child: CappedWidth(
              child: Column(
              children: [
                ScreenHeader(
                    title: widget.title, subtitle: 'Related information'),
                Expanded(
                  child: FutureBuilder<Map<String, dynamic>>(
                    future: _future,
                    builder: (context, snap) {
                      if (snap.connectionState == ConnectionState.waiting) {
                        return const Center(
                            child: CircularProgressIndicator(
                                color: EnhancedTheme.primaryTeal));
                      }
                      if (snap.hasError) {
                        return EmptyState(
                          icon: Icons.error_outline,
                          title: 'Could not load relationships',
                          message: '${snap.error}',
                          color: EnhancedTheme.errorRed,
                        );
                      }
                      // Every list-valued field is a neighbour group; the
                      // singular root key (disease/medication/…) is the node.
                      final groups = <MapEntry<String, List>>[];
                      for (final e in snap.data!.entries) {
                        if (e.value is List && (e.value as List).isNotEmpty) {
                          groups.add(MapEntry(e.key, e.value as List));
                        }
                      }
                      if (groups.isEmpty) {
                        return const EmptyState(
                          icon: Icons.hub_outlined,
                          title: 'No relationships',
                          message: 'Nothing linked to this record yet.',
                        );
                      }
                      return ListView(
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                        children: [
                          for (final g in groups)
                            _Group(
                              heading: _heading(g.key),
                              rows: g.value.cast<Map<String, dynamic>>(),
                              label: _label,
                              resource: resourceByPath(
                                  _groupResource[g.key] ?? ''),
                            ),
                        ],
                      );
                    },
                  ),
                ),
              ],
            ),
            ),
          ),
        ],
      ),
    );
  }

  String _heading(String key) {
    final words = key.replaceAll('_', ' ');
    return words[0].toUpperCase() + words.substring(1);
  }
}

class _Group extends StatelessWidget {
  final String heading;
  final List<Map<String, dynamic>> rows;
  final String Function(Map<String, dynamic>) label;
  final CatalogResource? resource; // null = chips not tappable
  const _Group({
    required this.heading,
    required this.rows,
    required this.label,
    required this.resource,
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
            Text('$heading (${rows.length})',
                style: GoogleFonts.outfit(
                  color: context.labelColor,
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                )),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final row in rows)
                  _Chip(
                    label: label(row),
                    onTap: resource == null
                        ? null
                        : () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => CatalogDetailScreen(
                                    resource: resource!, row: row),
                              ),
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

class _Chip extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;
  const _Chip({required this.label, this.onTap});

  @override
  Widget build(BuildContext context) {
    final chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: EnhancedTheme.accentCyan.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: EnhancedTheme.accentCyan.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label,
              style: const TextStyle(
                color: EnhancedTheme.accentCyan,
                fontWeight: FontWeight.w600,
                fontSize: 13,
              )),
          if (onTap != null) ...[
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right,
                size: 16, color: EnhancedTheme.accentCyan),
          ],
        ],
      ),
    );
    if (onTap == null) return chip;
    return Material(
      color: Colors.transparent,
      child: InkWell(
          borderRadius: BorderRadius.circular(12), onTap: onTap, child: chip),
    );
  }
}
