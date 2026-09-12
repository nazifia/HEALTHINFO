import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../config.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/hero_banner.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/snack.dart';
import '../shared/widgets/stats_kit.dart';
import 'cases_screen.dart';
import 'chw_reports_screen.dart';
import 'consultations_screen.dart';
import 'drug_orders_screen.dart';
import 'report_scaffold.dart';
import 'vital_events_screen.dart';

/// The ward: a clinical cadre's own landing screen. How much of each register
/// they file exists, and the latest few of the one they file most.
///
/// Counts come from each list endpoint's own pagination — there is no ward
/// dashboard endpoint to keep in step with this list. Mirrors viewClinical()
/// in web/app.js, including which registers each cadre gets.

/// One register a cadre files into: the drawer label it also carries (so a
/// tile can jump the drawer there), its list endpoint, and its icon.
class _Register {
  final String label;
  final String path;
  final IconData icon;
  const _Register(this.label, this.path, this.icon);
}

const _consultations = _Register(
    'Consultations', '/api/consultations/', Icons.medical_information_outlined);
const _drugOrders =
    _Register('Drug orders', '/api/prescriptions/', Icons.medication_outlined);
const _cases =
    _Register('Case reports', '/api/case-reports/', Icons.assignment_outlined);
const _labs =
    _Register('Lab results', '/api/lab-results/', Icons.science_outlined);
const _appointments =
    _Register('Appointments', '/api/appointments/', Icons.event_outlined);
const _immunizations =
    _Register('Immunizations', '/api/immunizations/', Icons.vaccines_outlined);
const _vitalEvents = _Register(
    'Vital events', '/api/vital-events/', Icons.child_friendly_outlined);
const _chwReports =
    _Register('CHW reports', '/api/chw-reports/', Icons.groups_outlined);
const _adr = _Register('Adverse reactions', '/api/adverse-reactions/',
    Icons.medication_liquid_outlined);

/// What each cadre files, most-filed first — the first one is the register the
/// "latest" panel reads. Mirrors CLINICAL_WORK in web/app.js.
const _work = <String, List<_Register>>{
  'doctor': [_consultations, _drugOrders, _cases, _labs, _appointments],
  'nurse': [_cases, _drugOrders, _immunizations, _labs, _appointments],
  'midwife': [_vitalEvents, _drugOrders, _immunizations, _cases, _appointments],
  'chew': [_chwReports, _drugOrders, _immunizations, _cases, _adr],
};

/// Fields worth reading in a one-line summary, best first. The registers do not
/// share a shape, so the first key a row actually carries wins.
const _titleKeys = [
  'patient_name',
  'diagnosis',
  'disease_name',
  'medication_name',
  'vaccine',
  'test_name',
  'event_type',
  'reference',
  'notes',
];

/// The new-record sheet for a register, by the label its tile carries. Only
/// the four a cadre lands on are here — the FAB files what that cadre files
/// most, and every other register is one tap away with its own FAB.
final _forms = <String, Widget Function()>{
  _consultations.label: consultationForm,
  _cases.label: caseReportForm,
  _vitalEvents.label: vitalEventForm,
  _chwReports.label: chwReportForm,
};

class _WardData {
  final Map<String, dynamic> me;
  final List<_Register> registers;
  final List<int?> counts;
  final List<dynamic> latest;
  final int? openVisits;
  final int? visitsToday;
  const _WardData(this.me, this.registers, this.counts, this.latest,
      this.openVisits, this.visitsToday);
}

class WardScreen extends StatefulWidget {
  /// Jumps the drawer to a section by its label. Null in a standalone route,
  /// where the tiles are counts and nothing more.
  final void Function(String label)? onOpen;

  const WardScreen({super.key, this.onOpen});

  @override
  State<WardScreen> createState() => _WardScreenState();
}

class _WardScreenState extends State<WardScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<_WardData> _future;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_WardData> _load() async {
    final me = await api.me() ?? const <String, dynamic>{};
    final registers = _work['${me['role']}'] ?? _work['nurse']!;
    // One row asked for per register: the page is thrown away, the count is
    // the answer. A register that refuses shows a dash rather than taking the
    // whole screen down with it.
    final counts = await Future.wait(registers.map((r) async {
      try {
        final data = await api.get(r.path, {'page_size': '1'});
        return data is Map ? data['count'] as int? : null;
      } catch (_) {
        return null;
      }
    }));
    List<dynamic> latest = const [];
    try {
      latest = await api.getList(
          registers.first.path, {'ordering': '-created_at', 'page_size': '5'});
    } catch (_) {}
    int? open;
    int? today;
    try {
      final r = await api
          .get(_consultations.path, {'status': 'open', 'page_size': '1'});
      open = r is Map ? r['count'] as int? : null;
      // The API has no date filter, so today's visits are counted off the
      // newest page. ponytail: 100 rows caps it; add a created_after filter
      // past that.
      final rows = await api.getList(
          _consultations.path, {'ordering': '-created_at', 'page_size': '100'});
      final now = DateTime.now();
      today = rows.where((r) {
        final at = DateTime.tryParse('${r['created_at'] ?? ''}')?.toLocal();
        return at != null &&
            at.year == now.year &&
            at.month == now.month &&
            at.day == now.day;
      }).length;
    } catch (_) {}
    return _WardData(me, registers, counts, latest, open, today);
  }

  /// Find a patient by phone, name or hospital number, then start a visit or
  /// write an order for them without going through the register.
  Future<void> _findPatient() async {
    final picked = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => SearchSheet(
        path: '/api/patients/',
        title: 'Find a patient',
        hint: 'Phone, name or hospital number',
        errorTitle: 'Could not load patients',
        emptyIcon: Icons.person_search_outlined,
        emptyTitle: 'No patients found',
        emptyMessage: 'Register the patient first, or search again.',
        label: (r) => '${r['full_name']}',
        sub: (r) => [
          '${r['hospital_number'] ?? ''}',
          if ('${r['sex'] ?? ''}'.isNotEmpty) '${r['sex']}',
          if (r['age'] != null) '${r['age']}y',
          if ('${r['phone'] ?? ''}'.isNotEmpty) '${r['phone']}',
          if ('${r['allergies'] ?? ''}'.trim().isNotEmpty)
            'Allergies: ${r['allergies']}',
        ].join(' · '),
      ),
    );
    if (picked == null || !mounted) return;
    final what = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            title: Text('${picked['full_name']}',
                style: const TextStyle(fontWeight: FontWeight.w800)),
            subtitle: Text('${picked['hospital_number'] ?? ''}'),
          ),
          ListTile(
            leading: const Icon(Icons.medical_information_outlined),
            title: const Text('Start visit'),
            onTap: () => Navigator.of(context).pop('visit'),
          ),
          ListTile(
            leading: const Icon(Icons.medication_outlined),
            title: const Text('Prescribe'),
            onTap: () => Navigator.of(context).pop('prescribe'),
          ),
        ]),
      ),
    );
    if (what == null || !mounted) return;
    if (what == 'prescribe') {
      final written = await prescribeFor(context, picked);
      if (written && mounted) showSuccess(context, 'Order written.');
      return;
    }
    final saved = await showModalBottomSheet<Object?>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => consultationForm(patient: picked),
    );
    if (saved == null || saved == false) return;
    _reload();
    // Most visits end with something to take home, so the next step rides on
    // the toast rather than a second search for the same patient.
    if (mounted) {
      showSuccess(context, 'Visit filed.',
          action: SnackBarAction(
            label: 'Prescribe',
            textColor: Colors.white,
            onPressed: () => prescribeFor(context, picked),
          ));
    }
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  Future<void> _file(_Register register) async {
    final form = _forms[register.label];
    if (form == null) return;
    final saved = await showModalBottomSheet<Object?>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => form(),
    );
    if (saved == null || saved == false) return;
    _reload();
    if (mounted) showSuccess(context, '${register.label} filed.');
  }

  String _rowTitle(Map row) {
    for (final k in _titleKeys) {
      final v = row[k];
      if (v != null && '$v'.trim().isNotEmpty) return '$v';
    }
    return 'Record #${row['id']}';
  }

  String _rowSubtitle(Map row) {
    final at = '${row['created_at'] ?? ''}';
    final when =
        at.length >= 16 ? at.substring(0, 16).replaceFirst('T', ' ') : at;
    final status = '${row['status'] ?? row['severity'] ?? ''}';
    return [status, when].where((s) => s.isNotEmpty).join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
        setState(() {
          _future = f;
        });
        await f;
      },
      child: FutureBuilder<_WardData>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const SkeletonCards(cards: 3, statRow: true);
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Could not load the ward',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
                action:
                    TextButton(onPressed: _reload, child: const Text('Retry')),
              ),
            ]);
          }
          final data = snap.data!;
          final primary = data.registers.first;
          final list = ListView(
            padding: const EdgeInsets.all(16),
            children: [
              HeroBanner(
                name: '${data.me['username'] ?? 'there'}',
                subtitle: [
                  _roleLabel('${data.me['role'] ?? ''}'),
                  tenantLabel,
                ].where((s) => s.isNotEmpty).join(' · '),
                stats: [
                  MapEntry('Open visits', data.openVisits),
                  MapEntry('Visits today', data.visitsToday),
                ],
                action: OutlinedButton.icon(
                  onPressed: _findPatient,
                  style: HeroBanner.actionStyle,
                  icon: const Icon(Icons.person_search_outlined, size: 18),
                  label: const Text('Find a patient'),
                ),
              ),
              const SizedBox(height: 16),
              _tiles(data),
              const SizedBox(height: 16),
              StatSection(
                icon: primary.icon,
                heading: 'Latest ${primary.label.toLowerCase()}',
                child: data.latest.isEmpty
                    ? const Text('Nothing filed yet.')
                    : Column(
                        children: [
                          for (final row in data.latest.cast<Map>())
                            ListTile(
                              dense: true,
                              contentPadding: EdgeInsets.zero,
                              title: Text(_rowTitle(row),
                                  overflow: TextOverflow.ellipsis),
                              subtitle: Text(_rowSubtitle(row)),
                              onTap: widget.onOpen == null
                                  ? null
                                  : () => widget.onOpen!(primary.label),
                            ),
                        ],
                      ),
              ),
            ],
          );
          if (!_forms.containsKey(primary.label)) return list;
          return Scaffold(
            backgroundColor: Colors.transparent,
            body: list,
            floatingActionButton: FloatingActionButton.extended(
              onPressed: () => _file(primary),
              icon: const Icon(Icons.add),
              label: Text('New ${_singular(primary.label).toLowerCase()}'),
            ),
          );
        },
      ),
    );
  }

  static String _roleLabel(String role) => role.isEmpty
      ? ''
      : role[0].toUpperCase() + role.substring(1).replaceAll('_', ' ');

  /// "Case reports" is what the register is called; one of them is a case
  /// report. Every label here is a plain plural.
  static String _singular(String label) =>
      label.endsWith('s') ? label.substring(0, label.length - 1) : label;

  // KpiRow takes bare tiles, and these ones open their register, so the same
  // two-up wrap is built here with each tile inside its own tap target.
  Widget _tiles(_WardData data) {
    const gap = 12.0;
    return LayoutBuilder(builder: (context, c) {
      final w = (c.maxWidth - gap) / 2;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (var i = 0; i < data.registers.length; i++)
            SizedBox(
              width: w,
              child: GestureDetector(
                onTap: widget.onOpen == null
                    ? null
                    : () => widget.onOpen!(data.registers[i].label),
                child: KpiTile(
                  icon: data.registers[i].icon,
                  value: '${data.counts[i] ?? '—'}',
                  label: data.registers[i].label,
                ),
              ),
            ),
        ],
      );
    });
  }
}
