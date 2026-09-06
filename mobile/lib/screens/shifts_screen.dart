import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Staff roster — GET/POST /api/shifts/.
///
/// The roster is what makes "on duty" a fact instead of a number somebody
/// typed: a facility KPI snapshot filed with staffing left blank takes its
/// count from here. Every tenant member reads it — a nurse needs to know who
/// else is on — but only the tenant admin sets it.
class ShiftsScreen extends StatefulWidget {
  const ShiftsScreen({super.key});

  @override
  State<ShiftsScreen> createState() => _ShiftsScreenState();
}

class _ShiftsScreenState extends State<ShiftsScreen> {
  bool _calendar = false;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final admin = isPharmacyAdmin(snap.data);
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Row(children: [
              for (final week in [false, true]) ...[
                ChoiceChip(
                  label: Text(week ? 'Week' : 'List'),
                  selected: _calendar == week,
                  onSelected: (_) => setState(() => _calendar = week),
                ),
                const SizedBox(width: 8),
              ],
            ]),
          ),
          Expanded(
            child: _calendar
                ? _WeekView(admin: admin)
                : ReportListScreen(
                    path: '/api/shifts/',
                    fabLabel: 'Add shift',
                    showFab: admin,
                    emptyIcon: Icons.schedule_outlined,
                    emptyTitle: 'Nobody rostered yet',
                    emptyMessage: admin
                        ? 'Tap "Add shift" to put someone on.'
                        : 'The tenant admin keeps the roster.',
                    savedMessage: 'Shift saved.',
                    header: (items) => const _OnDutyHeader(),
                    card: (row, reload, edit) =>
                        _ShiftCard(row: row, admin: admin, edit: edit),
                    form: (existing) => _ShiftForm(existing: existing),
                  ),
          ),
        ]);
      },
    );
  }
}

/// Open the shift sheet over any screen; true when something was saved.
Future<bool> _editShift(BuildContext context,
    [Map<String, dynamic>? existing]) async {
  final saved = await showModalBottomSheet<Object?>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _ShiftForm(existing: existing),
  );
  return saved != null && saved != false;
}

/// One week of the roster, a day at a time.
///
/// Asks the server for the window (?starts_at__gte=&starts_at__lt=) rather
/// than paging the whole roster and grouping locally — one request either way,
/// and this one comes back with only the week in it.
class _WeekView extends StatefulWidget {
  final bool admin;
  const _WeekView({required this.admin});

  @override
  State<_WeekView> createState() => _WeekViewState();
}

class _WeekViewState extends State<_WeekView> {
  late DateTime _monday = _weekOf(DateTime.now());
  late Future<List<dynamic>> _future = _load();

  static DateTime _weekOf(DateTime d) =>
      DateTime(d.year, d.month, d.day).subtract(Duration(days: d.weekday - 1));

  Future<List<dynamic>> _load() {
    final end = _monday.add(const Duration(days: 7));
    // ponytail: one page of 100 shifts a week. A roster past that needs paging,
    // not a bigger number.
    return api.getList('/api/shifts/', {
      'starts_at__gte': _monday.toUtc().toIso8601String(),
      'starts_at__lt': end.toUtc().toIso8601String(),
      'ordering': 'starts_at',
      'page_size': '100',
    });
  }

  void _reload() => setState(() => _future = _load());

  void _jump(DateTime monday) {
    _monday = monday;
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    final heading = DateFormat('d MMM');
    final end = _monday.add(const Duration(days: 6));
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: !widget.admin
          ? null
          : FloatingActionButton.extended(
              heroTag: 'fab_week_shift',
              onPressed: () async {
                if (await _editShift(context)) _reload();
              },
              backgroundColor: EnhancedTheme.primaryTeal,
              icon: const Icon(Icons.add, color: Colors.white),
              label: const Text('Add shift',
                  style: TextStyle(color: Colors.white)),
            ),
      body: FutureBuilder<List<dynamic>>(
        future: _future,
        builder: (context, snap) {
          final rows = (snap.data ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 90),
            children: [
              Row(children: [
                IconButton(
                  icon: const Icon(Icons.chevron_left),
                  onPressed: () =>
                      _jump(_monday.subtract(const Duration(days: 7))),
                ),
                Expanded(
                  child: Text(
                    '${heading.format(_monday)} – ${heading.format(end)}',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: context.labelColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 15),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.chevron_right),
                  onPressed: () => _jump(_monday.add(const Duration(days: 7))),
                ),
              ]),
              if (_monday != _weekOf(DateTime.now()))
                Center(
                  child: TextButton(
                    onPressed: () => _jump(_weekOf(DateTime.now())),
                    child: const Text('This week'),
                  ),
                ),
              if (snap.connectionState == ConnectionState.waiting)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 32),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (snap.hasError)
                Text('${snap.error}',
                    style: const TextStyle(color: EnhancedTheme.errorRed))
              else
                for (var i = 0; i < 7; i++) ..._day(context, rows, i),
            ],
          );
        },
      ),
    );
  }

  List<Widget> _day(
      BuildContext context, List<Map<String, dynamic>> rows, int offset) {
    final day = _monday.add(Duration(days: offset));
    final onDay = rows.where((r) {
      final start = _at(r['starts_at']);
      return start != null && DateUtils.isSameDay(start, day);
    }).toList();
    final today = DateUtils.isSameDay(day, DateTime.now());
    return [
      Padding(
        padding: EdgeInsets.only(top: offset == 0 ? 8 : 16, bottom: 6),
        child: Text(
          '${DateFormat('EEEE d MMM').format(day)}${today ? '  ·  today' : ''}',
          style: TextStyle(
              color: today ? EnhancedTheme.primaryTeal : context.hintColor,
              fontWeight: FontWeight.w700,
              fontSize: 13),
        ),
      ),
      if (onDay.isEmpty)
        Text('Nobody on',
            style: TextStyle(color: context.hintColor, fontSize: 12))
      else
        for (final row in onDay)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _ShiftCard(
              row: row,
              admin: widget.admin,
              edit: () async {
                if (await _editShift(context, row)) _reload();
              },
            ),
          ),
    ];
  }
}

final _stamp = DateFormat('EEE d MMM, HH:mm');

DateTime? _at(dynamic iso) =>
    iso == null ? null : DateTime.tryParse('$iso')?.toLocal();

/// Half-open, the same way the server counts: a shift ending at 14:00 and the
/// next starting at 14:00 hand over without both counting at 14:00.
bool _onNow(Map<String, dynamic> row) {
  final start = _at(row['starts_at']);
  final end = _at(row['ends_at']);
  if (start == null || end == null) return false;
  final now = DateTime.now();
  return !start.isAfter(now) && end.isAfter(now);
}

/// Who is on right now, straight from /api/shifts/on_duty/ rather than counted
/// off the page of rows on screen — the list is paginated, that count is not.
class _OnDutyHeader extends StatelessWidget {
  const _OnDutyHeader();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<dynamic>(
      future: api.get('/api/shifts/on_duty/'),
      builder: (context, snap) {
        final data = (snap.data as Map?)?.cast<String, dynamic>() ?? const {};
        final count = (data['count'] as num?)?.toInt();
        final names = ((data['results'] as List?) ?? [])
            .cast<Map<String, dynamic>>()
            .map((r) => '${r['username'] ?? ''}')
            .where((n) => n.isNotEmpty)
            .toSet()
            .join(', ');
        return Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Column(children: [
            StatsHeader(
              icon: Icons.schedule_outlined,
              title: 'Staff roster',
              subtitle: names.isEmpty ? 'Nobody on duty right now' : names,
              color: EnhancedTheme.primaryTeal,
            ),
            KpiRow(tiles: [
              KpiTile(
                icon: Icons.how_to_reg_outlined,
                label: 'On duty now',
                value: count == null ? '—' : '$count',
                color: EnhancedTheme.successGreen,
              ),
            ]),
          ]),
        );
      },
    );
  }
}

class _ShiftCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _ShiftCard({required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    final start = _at(row['starts_at']);
    final end = _at(row['ends_at']);
    final branch = '${row['branch_name'] ?? ''}'.trim();
    final notes = '${row['notes'] ?? ''}'.trim();
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['username'] ?? 'User #${row['user']}'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          if (_onNow(row))
            const ReportBadge(text: 'on now', color: EnhancedTheme.successGreen),
          if (admin)
            IconButton(
                icon: const Icon(Icons.edit_outlined, size: 18),
                onPressed: edit),
        ]),
        const SizedBox(height: 6),
        Text(
          start == null || end == null
              ? '—'
              : '${_stamp.format(start)}  →  ${_stamp.format(end)}',
          style: TextStyle(color: context.hintColor, fontSize: 13),
        ),
        if (branch.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(branch, style: TextStyle(color: context.hintColor, fontSize: 13)),
        ],
        if (notes.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(notes, style: TextStyle(color: context.hintColor, fontSize: 12)),
        ],
      ]),
    );
  }
}

class _ShiftForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _ShiftForm({this.existing});

  @override
  State<_ShiftForm> createState() => _ShiftFormState();
}

class _ShiftFormState extends State<_ShiftForm> {
  final _notes = TextEditingController();
  int? _userId;
  String? _userLabel;
  int? _branchId;
  String? _branchLabel;
  DateTime? _starts;
  DateTime? _ends;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _userId = e['user'] as int?;
      _userLabel = '${e['username'] ?? ''}';
      _branchId = e['branch'] as int?;
      _branchLabel = '${e['branch_name'] ?? ''}';
      _starts = _at(e['starts_at']);
      _ends = _at(e['ends_at']);
      _notes.text = '${e['notes'] ?? ''}';
    }
  }

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickUser() async {
    final picked = await pickRow(
      context,
      path: '/api/users/',
      title: 'Staff member',
      label: (r) => '${r['username'] ?? 'User #${r['id']}'}',
      subtitle: (r) => '${r['role'] ?? ''}'.replaceAll('_', ' '),
    );
    if (picked == null) return;
    setState(() {
      _userId = picked['id'] as int?;
      _userLabel = '${picked['username'] ?? ''}';
    });
  }

  Future<void> _pickBranch() async {
    final picked = await pickRow(
      context,
      path: '/api/branches/',
      title: 'Branch',
      label: (r) => '${r['name'] ?? 'Branch #${r['id']}'}',
    );
    if (picked == null) return;
    setState(() {
      _branchId = picked['id'] as int?;
      _branchLabel = '${picked['name'] ?? ''}';
    });
  }

  Future<void> _pickWhen({required bool start}) async {
    final now = DateTime.now();
    final current = start ? _starts : _ends;
    final day = await showDatePicker(
      context: context,
      initialDate: current ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 2),
    );
    if (day == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current ?? now),
    );
    if (time == null) return;
    final picked =
        DateTime(day.year, day.month, day.day, time.hour, time.minute);
    setState(() {
      if (start) {
        _starts = picked;
        // A shift that now ends before it starts is a half-filled form, not an
        // answer — drop the end so the admin picks it again.
        if (_ends != null && !_ends!.isAfter(picked)) _ends = null;
      } else {
        _ends = picked;
      }
    });
  }

  Future<void> _submit() async {
    if (_userId == null) {
      setState(() => _error = 'Pick the staff member.');
      return;
    }
    if (_starts == null || _ends == null) {
      setState(() => _error = 'Set when the shift starts and ends.');
      return;
    }
    if (!_ends!.isAfter(_starts!)) {
      setState(() => _error = 'A shift must end after it starts.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'user': _userId,
        'branch': _branchId,
        'starts_at': _starts!.toUtc().toIso8601String(),
        'ends_at': _ends!.toUtc().toIso8601String(),
        'notes': _notes.text.trim(),
      };
      if (_isEdit) {
        await api.patch('/api/shifts/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/shifts/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _pickField(String label, String? value, String empty, VoidCallback tap,
          {VoidCallback? clear}) =>
      InputDecorator(
        decoration: InputDecoration(labelText: label),
        child: Row(children: [
          Expanded(
            child: Text(
              value == null || value.isEmpty ? empty : value,
              style: TextStyle(
                  color: value == null || value.isEmpty
                      ? context.hintColor
                      : context.labelColor),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (clear != null && value != null && value.isNotEmpty)
            IconButton(
                icon: const Icon(Icons.clear, size: 18), onPressed: clear),
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: tap),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _isEdit ? 'Edit shift' : 'New shift',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add shift',
      onSubmit: _submit,
      children: [
        _pickField('Staff member', _userLabel, 'Nobody picked', _pickUser),
        const SizedBox(height: 12),
        _pickField('Branch (optional)', _branchLabel, 'Whole facility',
            _pickBranch, clear: () {
          setState(() {
            _branchId = null;
            _branchLabel = null;
          });
        }),
        const SizedBox(height: 12),
        _pickField('Starts', _starts == null ? null : _stamp.format(_starts!),
            'Not set', () => _pickWhen(start: true)),
        const SizedBox(height: 12),
        _pickField('Ends', _ends == null ? null : _stamp.format(_ends!),
            'Not set', () => _pickWhen(start: false)),
        const SizedBox(height: 12),
        TextField(
          controller: _notes,
          decoration: const InputDecoration(labelText: 'Notes'),
        ),
      ],
    );
  }
}
