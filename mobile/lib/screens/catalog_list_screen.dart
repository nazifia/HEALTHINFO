import 'dart:async';
import 'package:flutter/material.dart';

import '../main.dart';
import '../resources.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/responsive.dart';
import 'catalog_detail_screen.dart';

/// Searchable list for any [CatalogResource]. Used inside the home tabs.
class CatalogListScreen extends StatefulWidget {
  final CatalogResource resource;
  const CatalogListScreen({super.key, required this.resource});

  @override
  State<CatalogListScreen> createState() => _CatalogListScreenState();
}

class _CatalogListScreenState extends State<CatalogListScreen>
    with AutomaticKeepAliveClientMixin {
  final _search = TextEditingController();
  Timer? _debounce;
  late Future<List<dynamic>> _future;

  @override
  bool get wantKeepAlive => true; // keep tab state when switching

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<List<dynamic>> _load([String query = '']) {
    final q = query.trim();
    // PharmApp-style: ignore 1-char noise — show the full list until 2+ chars.
    return api.getList(
      widget.resource.path,
      q.length < 2 ? null : {'search': q},
    );
  }

  void _onSearch(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 200), () {
      final f = _load(value);
      setState(() {
        _future = f;
      });
    });
  }

  String _str(Map<String, dynamic> row, String? field) {
    if (field == null) return '';
    final v = row[field];
    return v == null ? '' : v.toString();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final r = widget.resource;
    return Column(
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
                    color: EnhancedTheme.primaryTeal.withValues(alpha: 0.8),
                    size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _search,
                    onChanged: _onSearch,
                    decoration: InputDecoration(
                      hintText: 'Search ${r.label.toLowerCase()}…',
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      filled: false,
                      contentPadding:
                          const EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () async {
              final f = _load(_search.text);
              setState(() {
                _future = f;
              });
              await f;
            },
            child: FutureBuilder<List<dynamic>>(
              future: _future,
              builder: (context, snap) {
                if (snap.connectionState == ConnectionState.waiting) {
                  return const Center(
                    child: CircularProgressIndicator(
                        color: EnhancedTheme.primaryTeal),
                  );
                }
                if (snap.hasError) {
                  return _wrap(EmptyState(
                    icon: Icons.error_outline,
                    title: 'Something went wrong',
                    message: '${snap.error}',
                    color: EnhancedTheme.errorRed,
                  ));
                }
                final items = snap.data ?? [];
                if (items.isEmpty) {
                  return _wrap(EmptyState(
                    icon: r.icon,
                    title: 'No ${r.label.toLowerCase()} found',
                    message: 'Try a different search.',
                  ));
                }
                return CardGrid(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  itemCount: items.length,
                  itemBuilder: (context, i) {
                    final row = items[i] as Map<String, dynamic>;
                    final sub = _str(row, r.subtitleField);
                    final title = _str(row, r.titleField);
                    return GlassCard(
                      borderRadius: 16,
                      padding: const EdgeInsets.all(14),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) =>
                              CatalogDetailScreen(resource: r, row: row),
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: EnhancedTheme.primaryTeal
                                  .withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(r.icon,
                                color: EnhancedTheme.primaryTeal, size: 22),
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
                                    style: TextStyle(
                                        color: context.hintColor,
                                        fontSize: 12),
                                  ),
                                ],
                              ],
                            ),
                          ),
                          Icon(Icons.chevron_right, color: context.hintColor),
                        ],
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ),
      ],
    );
  }

  // EmptyState needs to live inside a scrollable for pull-to-refresh to work.
  Widget _wrap(Widget child) => ListView(
        children: [
          Padding(padding: const EdgeInsets.only(top: 80), child: child),
        ],
      );
}
