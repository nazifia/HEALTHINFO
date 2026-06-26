import 'dart:async';
import 'package:flutter/material.dart';

import '../main.dart';
import '../resources.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import 'catalog_detail_screen.dart';

/// Cross-catalog search wired to GET /api/search/?q=. One box searches diseases,
/// medications, procedures, lab tests and articles at once; results are grouped
/// by type and tap through to the same detail screen as the per-tab lists.
class GlobalSearchScreen extends StatefulWidget {
  const GlobalSearchScreen({super.key});

  @override
  State<GlobalSearchScreen> createState() => _GlobalSearchScreenState();
}

// SearchView response key -> catalog list path (resolved to a CatalogResource
// for icon/title/subtitle rendering and detail navigation).
const _groups = <({String key, String path})>[
  (key: 'diseases', path: '/api/diseases/'),
  (key: 'medications', path: '/api/medications/'),
  (key: 'procedures', path: '/api/procedures/'),
  (key: 'lab_tests', path: '/api/lab-tests/'),
  (key: 'articles', path: '/api/articles/'),
];

class _GlobalSearchScreenState extends State<GlobalSearchScreen> {
  final _search = TextEditingController();
  Timer? _debounce;
  Future<Map<String, dynamic>>? _future;
  Map<String, dynamic>? _last; // keep showing prior hits while the next loads

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onSearch(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 200), () {
      final q = value.trim();
      // Mirror the backend min-length guard — no request below 2 chars.
      setState(() {
        if (q.length < 2) {
          _future = null;
          _last = null;
        } else {
          _future = _run(q);
        }
      });
    });
  }

  Future<Map<String, dynamic>> _run(String q) async {
    final data = await api.get('/api/search/', {'q': q});
    return data as Map<String, dynamic>;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      appBar: AppBar(title: const Text('Search')),
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                  child: GlassCard(
                    borderRadius: 16,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Row(
                      children: [
                        const SizedBox(width: 8),
                        Icon(Icons.search,
                            color: EnhancedTheme.primaryTeal
                                .withValues(alpha: 0.8),
                            size: 20),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TextField(
                            controller: _search,
                            autofocus: true,
                            onChanged: _onSearch,
                            decoration: const InputDecoration(
                              hintText: 'Search all catalog…',
                              border: InputBorder.none,
                              enabledBorder: InputBorder.none,
                              focusedBorder: InputBorder.none,
                              filled: false,
                              contentPadding:
                                  EdgeInsets.symmetric(vertical: 14),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Expanded(child: _body(context)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context) {
    if (_future == null) {
      return const EmptyState(
        icon: Icons.search,
        title: 'Search the catalog',
        message: 'Type at least 2 characters.',
      );
    }
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.hasData) _last = snap.data;
        // While a new query loads, keep the previous results on screen (no blank
        // flash) and show a thin progress bar instead of a full-screen spinner.
        final loading = snap.connectionState == ConnectionState.waiting;
        if (loading && _last == null) {
          return const Center(
            child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal),
          );
        }
        if (snap.hasError && _last == null) {
          return EmptyState(
            icon: Icons.error_outline,
            title: 'Something went wrong',
            message: '${snap.error}',
            color: EnhancedTheme.errorRed,
          );
        }
        final data = snap.data ?? _last ?? const {};
        final total = (data['total'] as int?) ?? 0;
        if (total == 0) {
          return const EmptyState(
            icon: Icons.search_off,
            title: 'No results',
            message: 'Try a different search.',
          );
        }

        final children = <Widget>[];
        if (data['disclaimer'] != null) {
          children.add(Padding(
            padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
            child: Text(
              '${data['disclaimer']}',
              style: TextStyle(
                  color: context.hintColor,
                  fontSize: 11,
                  fontStyle: FontStyle.italic),
            ),
          ));
        }
        for (final g in _groups) {
          final rows = (data[g.key] as List?) ?? const [];
          final r = resourceByPath(g.path);
          if (rows.isEmpty || r == null) continue;
          children.add(Padding(
            padding: const EdgeInsets.fromLTRB(4, 14, 4, 6),
            child: Text(
              '${r.label} (${rows.length})',
              style: TextStyle(
                color: EnhancedTheme.primaryTeal,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ));
          for (final row in rows) {
            children.add(_tile(context, r, row as Map<String, dynamic>));
          }
        }
        return Column(
          children: [
            SizedBox(
              height: 2,
              child: loading
                  ? const LinearProgressIndicator(
                      color: EnhancedTheme.primaryTeal, minHeight: 2)
                  : null,
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                children: children,
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _tile(BuildContext context, CatalogResource r, Map<String, dynamic> row) {
    final title = (row[r.titleField] ?? '').toString();
    final sub = r.subtitleField == null
        ? ''
        : (row[r.subtitleField] ?? '').toString();
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        borderRadius: 16,
        padding: const EdgeInsets.all(14),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => CatalogDetailScreen(resource: r, row: row),
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: EnhancedTheme.primaryTeal.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(r.icon, color: EnhancedTheme.primaryTeal, size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title.isEmpty ? '—' : title,
                    style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                    ),
                  ),
                  if (sub.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      '${r.subtitleLabel}: $sub',
                      style:
                          TextStyle(color: context.hintColor, fontSize: 12),
                    ),
                  ],
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: context.hintColor),
          ],
        ),
      ),
    );
  }
}
