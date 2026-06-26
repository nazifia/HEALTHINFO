import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/snack.dart';

/// Shared list+FAB shell for a staff-filed report type (lab results, vaccines,
/// births/deaths, stock). Each screen supplies the list path, a card builder and
/// a bottom-sheet form builder — the load/refresh/empty/error plumbing lives
/// here so the report screens stay tiny. Mirrors the AdrScreen pattern.
class ReportListScreen extends StatefulWidget {
  final String path; // API list path, e.g. /api/lab-results/
  final String fabLabel;
  final IconData emptyIcon;
  final String emptyTitle;
  final String emptyMessage;
  final String savedMessage;
  final Widget Function(Map<String, dynamic> row, VoidCallback reload, VoidCallback edit) card;
  // Form sheet for a new (existing == null) or edited record. Pops `true` on save.
  final Widget Function(Map<String, dynamic>? existing) form;
  // Optional summary widget rendered above the list, fed the loaded rows
  // (e.g. a KPI header). Hidden when the list is empty.
  final Widget Function(List<Map<String, dynamic>> items)? header;

  const ReportListScreen({
    super.key,
    required this.path,
    required this.fabLabel,
    required this.emptyIcon,
    required this.emptyTitle,
    required this.emptyMessage,
    required this.savedMessage,
    required this.card,
    required this.form,
    this.header,
  });

  @override
  State<ReportListScreen> createState() => _ReportListScreenState();
}

class _ReportListScreenState extends State<ReportListScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = api.getList(widget.path);
  }

  void _reload() => setState(() => _future = api.getList(widget.path));

  Future<void> _openForm([Map<String, dynamic>? existing]) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => widget.form(existing),
    );
    if (saved == true) {
      _reload();
      if (mounted) showSuccess(context, widget.savedMessage);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openForm,
        backgroundColor: EnhancedTheme.primaryTeal,
        icon: const Icon(Icons.add, color: Colors.white),
        label: Text(widget.fabLabel,
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          _reload();
          await _future;
        },
        child: FutureBuilder<List<dynamic>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(
                  child: CircularProgressIndicator(color: EnhancedTheme.primaryTeal));
            }
            if (snap.hasError) {
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: Icons.error_outline,
                  title: 'Could not load',
                  message: '${snap.error}',
                  color: EnhancedTheme.errorRed,
                ),
              ]);
            }
            final items = (snap.data ?? []).cast<Map<String, dynamic>>();
            if (items.isEmpty) {
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: widget.emptyIcon,
                  title: widget.emptyTitle,
                  message: widget.emptyMessage,
                ),
              ]);
            }
            final hasHeader = widget.header != null;
            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
              itemCount: items.length + (hasHeader ? 1 : 0),
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                if (hasHeader && i == 0) return widget.header!(items);
                final row = items[i - (hasHeader ? 1 : 0)];
                return widget.card(row, _reload, () => _openForm(row));
              },
            );
          },
        ),
      ),
    );
  }
}

/// Bottom-sheet shell for a report form: the grabber handle, title, scroll,
/// inline error and submit button. Children are the form fields. Keeps each
/// form focused on its own fields. Mirrors the _AdrForm chrome.
class ReportFormSheet extends StatelessWidget {
  final String title;
  final bool saving;
  final String? error;
  final String submitLabel;
  final VoidCallback? onSubmit;
  final List<Widget> children;

  const ReportFormSheet({
    super.key,
    required this.title,
    required this.saving,
    required this.error,
    required this.submitLabel,
    required this.onSubmit,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: inset),
      child: Container(
        decoration: BoxDecoration(
          color: context.scaffoldBg,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: context.hintColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Text(title,
                  style: TextStyle(
                      color: context.labelColor,
                      fontSize: 18,
                      fontWeight: FontWeight.w800)),
              const SizedBox(height: 16),
              ...children,
              if (error != null) ...[
                const SizedBox(height: 12),
                Text(error!,
                    style: const TextStyle(
                        color: EnhancedTheme.errorRed, fontSize: 13)),
              ],
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: saving ? null : onSubmit,
                  style: FilledButton.styleFrom(
                      backgroundColor: EnhancedTheme.primaryTeal),
                  child: saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : Text(submitLabel),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Small pill badge — reused by the report cards. Mirrors AdrScreen's _Badge.
class ReportBadge extends StatelessWidget {
  final String text;
  final Color color;
  const ReportBadge({super.key, required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        text.isEmpty ? '—' : text.replaceAll('_', ' ').toUpperCase(),
        style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 11),
      ),
    );
  }
}
