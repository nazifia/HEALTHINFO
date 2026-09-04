import 'dart:async';

import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/responsive.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';

/// One server-side choice filter offered above a report list.
///
/// [param] is the DRF filterset field, so the values must be the ones the API
/// stores, not their labels. Selecting nothing drops the param entirely.
class ReportFilter {
  final String param; // query param, e.g. 'patient_type'
  final String anyLabel; // shown when no value is picked, e.g. 'Any type'
  final Map<String, String> options; // wire value -> label

  const ReportFilter({
    required this.param,
    required this.anyLabel,
    required this.options,
  });
}

/// Query params for a list request: the picked filters plus the search box.
///
/// Null when nothing is set, so an unfiltered list asks for a bare URL. A blank
/// search is dropped rather than sent as `?search=`, which DRF would treat as a
/// match-nothing term on some backends.
Map<String, String>? listQuery(String search, Map<String, String> picked) {
  final params = {
    ...picked,
    if (search.trim().isNotEmpty) 'search': search.trim(),
  };
  return params.isEmpty ? null : params;
}

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
  // Set to show a search box that re-queries the endpoint with ?search=...
  // (DRF SearchFilter). Null = no search box.
  final String? searchHint;
  // Server-side choice filters shown as dropdowns above the list. Empty = none.
  final List<ReportFilter> filters;
  // Optional tap handler on a card (e.g. open a detail page).
  final void Function(Map<String, dynamic> row)? onTap;
  // Hide the FAB for a list the current user may read but not add to.
  final bool showFab;

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
    this.searchHint,
    this.filters = const [],
    this.onTap,
    this.showFab = true,
  });

  @override
  State<ReportListScreen> createState() => _ReportListScreenState();
}

class _ReportListScreenState extends State<ReportListScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;
  String _query = '';
  // Picked filter values, keyed by query param. A param is absent when the
  // user has it on "any", so the request just doesn't carry it.
  final Map<String, String> _picked = {};
  Timer? _debounce;

  bool get _narrowed => _query.isNotEmpty || _picked.isNotEmpty;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = api.getList(widget.path);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _reload() => setState(
      () => _future = api.getList(widget.path, listQuery(_query, _picked)));

  // ponytail: 350ms debounce, no in-flight cancellation — a slow earlier
  // response can still land last. Add a request token if that ever shows up.
  void _onSearchChanged(String value) {
    _query = value.trim();
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (mounted) _reload();
    });
  }

  Future<void> _openForm([Map<String, dynamic>? existing]) async {
    // Anything but null counts as saved: most sheets pop `true`, but one that
    // creates a record (the dispensing counter) pops the record itself.
    final saved = await showModalBottomSheet<Object?>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => widget.form(existing),
    );
    if (saved != null && saved != false) {
      _reload();
      if (mounted) showSuccess(context, widget.savedMessage);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: !widget.showFab
          ? null
          : FloatingActionButton.extended(
              heroTag: 'fab_${widget.fabLabel}',
              onPressed: _openForm,
              backgroundColor: EnhancedTheme.primaryTeal,
              icon: const Icon(Icons.add, color: Colors.white),
              label: Text(widget.fabLabel,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700)),
            ),
      body: Column(children: [
        if (widget.searchHint != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: TextField(
              onChanged: _onSearchChanged,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: widget.searchHint,
                prefixIcon: const Icon(Icons.search, size: 20),
                isDense: true,
              ),
            ),
          ),
        if (widget.filters.isNotEmpty)
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: Row(children: [
              for (final f in widget.filters) ...[
                _FilterDropdown(
                  filter: f,
                  value: _picked[f.param],
                  onChanged: (v) {
                    if (v == null) {
                      _picked.remove(f.param);
                    } else {
                      _picked[f.param] = v;
                    }
                    _reload();
                  },
                ),
                const SizedBox(width: 8),
              ],
            ]),
          ),
        Expanded(child: _list()),
      ]),
    );
  }

  Widget _list() {
    return RefreshIndicator(
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
              // "Nothing here" and "nothing matched" are different problems —
              // only the second one is fixed by clearing the search or filters.
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: _narrowed ? Icons.search_off : widget.emptyIcon,
                  title: _narrowed ? 'No matches' : widget.emptyTitle,
                  message: !_narrowed
                      ? widget.emptyMessage
                      : _query.isEmpty
                          ? 'Nothing matched the selected filters.'
                          : 'Nothing found for "$_query".',
                ),
              ]);
            }
            return CardGrid(
              itemCount: items.length,
              header: widget.header == null ? null : widget.header!(items),
              itemBuilder: (context, i) {
                final card =
                    widget.card(items[i], _reload, () => _openForm(items[i]));
                if (widget.onTap == null) return card;
                return InkWell(
                  borderRadius: BorderRadius.circular(16),
                  onTap: () => widget.onTap!(items[i]),
                  child: card,
                );
              },
            );
          },
        ));
  }
}

/// Compact pill dropdown for one [ReportFilter]. A null value means "any", and
/// it stays in the list so a picked filter can be cleared without a second
/// control.
class _FilterDropdown extends StatelessWidget {
  final ReportFilter filter;
  final String? value;
  final ValueChanged<String?> onChanged;

  const _FilterDropdown({
    required this.filter,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final active = value != null;
    final accent = active ? EnhancedTheme.primaryTeal : context.hintColor;
    final items = <DropdownMenuItem<String?>>[
      DropdownMenuItem(value: null, child: Text(filter.anyLabel)),
      for (final o in filter.options.entries)
        DropdownMenuItem(value: o.key, child: Text(o.value)),
    ];
    final label = active ? filter.options[value] ?? value! : filter.anyLabel;
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: () async {
        final picked = await showSearchablePicker<String?>(
          context: context,
          items: items,
          selected: value,
          title: filter.anyLabel,
        );
        if (picked != null) onChanged(picked.value);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: accent.withValues(alpha: active ? 1 : 0.4)),
          color: active
              ? EnhancedTheme.primaryTeal.withValues(alpha: 0.12)
              : Colors.transparent,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                  color: context.labelColor,
                  fontSize: 13,
                  fontWeight: FontWeight.w600),
            ),
            Icon(Icons.arrow_drop_down, size: 20, color: accent),
          ],
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

/// Form field that links a report to a registered patient (GET /api/patients/).
/// Optional everywhere: reports stay valid — and de-identified — without one,
/// so this never blocks a submit. When a patient is linked the backend fills in
/// the age band and sex the rollups read.
class PatientPicker extends StatefulWidget {
  final int? initialId;
  final String? initialLabel;
  final ValueChanged<int?> onChanged;

  const PatientPicker({
    super.key,
    required this.onChanged,
    this.initialId,
    this.initialLabel,
  });

  @override
  State<PatientPicker> createState() => _PatientPickerState();
}

class _PatientPickerState extends State<PatientPicker> {
  int? _id;
  String? _label;

  @override
  void initState() {
    super.initState();
    _id = widget.initialId;
    _label = widget.initialLabel;
  }

  Future<void> _pick() async {
    final picked = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const _PatientSearchSheet(),
    );
    if (picked == null) return;
    setState(() {
      _id = picked['id'] as int?;
      _label = '${picked['full_name']} · ${picked['hospital_number']}';
    });
    widget.onChanged(_id);
  }

  void _clear() {
    setState(() {
      _id = null;
      _label = null;
    });
    widget.onChanged(null);
  }

  @override
  Widget build(BuildContext context) {
    return InputDecorator(
      decoration: const InputDecoration(labelText: 'Patient (optional)'),
      child: Row(children: [
        Expanded(
          child: Text(
            _label ?? (_id == null ? 'Not linked' : 'Patient #$_id'),
            style: TextStyle(
                color: _id == null ? context.hintColor : context.labelColor),
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (_id != null)
          IconButton(
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.clear, size: 18),
            onPressed: _clear,
          ),
        TextButton(onPressed: _pick, child: Text(_id == null ? 'Link' : 'Change')),
      ]),
    );
  }
}

/// Search sheet behind [PatientPicker]. Pops the chosen patient row.
class _PatientSearchSheet extends StatefulWidget {
  const _PatientSearchSheet();

  @override
  State<_PatientSearchSheet> createState() => _PatientSearchSheetState();
}

class _PatientSearchSheetState extends State<_PatientSearchSheet> {
  Future<List<dynamic>> _future = api.getList('/api/patients/');
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _search(String value) {
    final q = value.trim();
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      setState(() {
        _future =
            api.getList('/api/patients/', q.isEmpty ? null : {'search': q});
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        height: MediaQuery.of(context).size.height * 0.7,
        decoration: BoxDecoration(
          color: context.scaffoldBg,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(children: [
          Text('Link a patient',
              style: TextStyle(
                  color: context.labelColor,
                  fontSize: 18,
                  fontWeight: FontWeight.w800)),
          const SizedBox(height: 12),
          TextField(
            autofocus: true,
            onChanged: _search,
            decoration: const InputDecoration(
              hintText: 'Name, hospital number or phone',
              prefixIcon: Icon(Icons.search, size: 20),
              isDense: true,
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: FutureBuilder<List<dynamic>>(
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
                    title: 'Could not load patients',
                    message: '${snap.error}',
                    color: EnhancedTheme.errorRed,
                  );
                }
                final rows = (snap.data ?? []).cast<Map<String, dynamic>>();
                if (rows.isEmpty) {
                  return const EmptyState(
                    icon: Icons.person_search_outlined,
                    title: 'No patients found',
                    message: 'Register the patient first, or search again.',
                  );
                }
                return ListView.builder(
                  itemCount: rows.length,
                  itemBuilder: (context, i) {
                    final r = rows[i];
                    return ListTile(
                      dense: true,
                      title: Text('${r['full_name']}',
                          style: TextStyle(color: context.labelColor)),
                      subtitle: Text(
                        [
                          '${r['hospital_number'] ?? ''}',
                          if ('${r['sex'] ?? ''}'.isNotEmpty) '${r['sex']}',
                          if (r['age'] != null) '${r['age']}y',
                        ].join(' · '),
                        style: TextStyle(color: context.hintColor, fontSize: 12),
                      ),
                      onTap: () => Navigator.of(context).pop(r),
                    );
                  },
                );
              },
            ),
          ),
        ]),
      ),
    );
  }
}
