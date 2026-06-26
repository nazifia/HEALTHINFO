import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/bar_chart.dart';

/// Public-health analytics: the analysis side of the four collection feeds —
/// AMR, immunization coverage, vital-stats mortality and pharmacy shortages.
/// Each section tries the super-admin platform rollup, falling back to the
/// tenant's own. Mirrors CollatedReportsScreen.
class PublicHealthScreen extends StatefulWidget {
  const PublicHealthScreen({super.key});

  @override
  State<PublicHealthScreen> createState() => _PublicHealthScreenState();
}

class _PublicHealthScreenState extends State<PublicHealthScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _loadAll();
  }

  /// Platform rollup first; on any non-200 (e.g. 403 for non-super-admins) fall
  /// back to the tenant endpoint. Returns {} if both fail so one dead feed
  /// doesn't blank the whole screen.
  Future<Map<String, dynamic>> _load(String platformPath, String tenantPath) async {
    for (final p in [platformPath, tenantPath]) {
      try {
        final r = await api.get(p);
        return (r as Map).cast<String, dynamic>();
      } catch (_) {}
    }
    return {};
  }

  Future<List<Map<String, dynamic>>> _loadAll() => Future.wait([
        _load('/api/analytics/platform/labs/', '/api/analytics/labs/'),
        _load('/api/analytics/platform/immunizations/', '/api/analytics/immunizations/'),
        _load('/api/analytics/platform/vitals/', '/api/analytics/vitals/'),
        _load('/api/analytics/platform/stock/', '/api/analytics/stock/'),
        _load('/api/analytics/platform/chw/', '/api/analytics/chw/'),
        _load('/api/analytics/platform/facility/', '/api/analytics/facility/'),
        _load('/api/analytics/platform/insurance/', '/api/analytics/insurance/'),
        _load('/api/analytics/platform/appointments/', '/api/analytics/appointments/'),
      ]);

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        final f = _loadAll();
        setState(() => _future = f);
        await f;
      },
      child: FutureBuilder<List<Map<String, dynamic>>>(
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
                title: 'Could not load analytics',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final [lab, imm, vital, stock, chw, facility, insurance, appt] = snap.data!;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              // ── Antimicrobial resistance ──
              _SectionTitle('Antimicrobial resistance', Icons.biotech_outlined),
              _Metric(
                value: _pct(lab['amr_rate']),
                label: 'Overall resistance rate',
                sub: '${lab['resistant'] ?? 0} of ${lab['isolates_tested'] ?? 0} isolates resistant',
              ),
              _Breakdown(
                heading: 'Resistance by organism',
                icon: Icons.coronavirus_outlined,
                rows: (lab['amr_by_organism'] as List?) ?? [],
                labelKey: 'organism',
                valueKey: 'resistance_rate',
                asPercent: true,
              ),
              _Breakdown(
                heading: 'Resistance by antibiotic',
                icon: Icons.medication_outlined,
                rows: (lab['amr_by_antibiotic'] as List?) ?? [],
                labelKey: 'antibiotic',
                valueKey: 'resistance_rate',
                asPercent: true,
              ),

              // ── Immunization coverage ──
              _SectionTitle('Immunization coverage', Icons.vaccines_outlined),
              _Metric(value: '${imm['total_doses'] ?? 0}', label: 'Doses administered'),
              _Breakdown(
                heading: 'By vaccine',
                icon: Icons.medical_services_outlined,
                rows: (imm['by_vaccine'] as List?) ?? [],
                labelKey: 'vaccine',
              ),
              _Breakdown(
                heading: 'By state',
                icon: Icons.map_outlined,
                rows: (imm['by_region_state'] as List?) ?? [],
                labelKey: 'state',
              ),

              // ── Mortality ──
              _SectionTitle('Vital statistics & mortality', Icons.monitor_heart_outlined),
              _Metric(
                value: '${vital['births'] ?? 0} / ${vital['deaths'] ?? 0}',
                label: 'Births / deaths',
                sub: 'MMR ${_num(vital['maternal_mortality_ratio'])} per 100k · '
                    'IMR ${_num(vital['infant_mortality_rate'])} per 1k',
              ),
              _Breakdown(
                heading: 'Deaths by cause',
                icon: Icons.dangerous_outlined,
                rows: (vital['deaths_by_cause'] as List?) ?? [],
                labelKey: 'cause__name',
              ),

              // ── Pharmacy shortages ──
              _SectionTitle('Pharmacy stock', Icons.inventory_2_outlined),
              _Metric(
                value: '${stock['shortage_count'] ?? 0}',
                label: 'Active shortages',
                sub: '${stock['total_reports'] ?? 0} stock reports',
                danger: ((stock['shortage_count'] ?? 0) as num) > 0,
              ),
              _Breakdown(
                heading: 'Most consumed',
                icon: Icons.local_pharmacy_outlined,
                rows: (stock['top_consumed'] as List?) ?? [],
                labelKey: 'medication__generic_name',
                valueKey: 'consumed',
              ),

              // ── Community health workers ──
              _SectionTitle('Community health workers', Icons.groups_outlined),
              _Metric(
                value: '${chw['total'] ?? 0}',
                label: 'Field reports',
                sub: '${chw['danger_signs'] ?? 0} danger signs · '
                    'referral rate ${_pct(chw['referral_rate'])}',
              ),
              _Breakdown(
                heading: 'By report type',
                icon: Icons.assignment_ind_outlined,
                rows: (chw['by_type'] as List?) ?? [],
                labelKey: 'report_type',
              ),

              // ── Health-service KPIs ──
              _SectionTitle('Health-service performance', Icons.local_hospital_outlined),
              _Metric(
                value: _pct(facility['occupancy_rate']),
                label: 'Bed occupancy',
                sub: 'avg wait ${_num(facility['avg_wait_minutes'])} min · '
                    '${facility['patients_treated'] ?? 0} patients treated',
              ),

              // ── Insurance ──
              _SectionTitle('Insurance claims', Icons.receipt_long_outlined),
              _Metric(
                value: '${insurance['total'] ?? 0}',
                label: 'Claims',
                sub: '₦${_num(insurance['total_amount'])} total · '
                    'approval rate ${_pct(insurance['approval_rate'])}',
              ),
              _Breakdown(
                heading: 'By status',
                icon: Icons.fact_check_outlined,
                rows: (insurance['by_status'] as List?) ?? [],
                labelKey: 'status',
              ),
              _Breakdown(
                heading: 'Top diagnoses',
                icon: Icons.coronavirus_outlined,
                rows: (insurance['top_diagnoses'] as List?) ?? [],
                labelKey: 'diagnosis__name',
              ),

              // ── Appointments / telemedicine ──
              _SectionTitle('Appointments & telemedicine', Icons.event_outlined),
              _Metric(
                value: '${appt['total'] ?? 0}',
                label: 'Appointments',
                sub: '${appt['telemedicine'] ?? 0} telemedicine · '
                    'no-show rate ${_pct(appt['no_show_rate'])}',
              ),
              _Breakdown(
                heading: 'By mode',
                icon: Icons.devices_outlined,
                rows: (appt['by_mode'] as List?) ?? [],
                labelKey: 'mode',
              ),
              _Breakdown(
                heading: 'By status',
                icon: Icons.event_available_outlined,
                rows: (appt['by_status'] as List?) ?? [],
                labelKey: 'status',
              ),
            ],
          );
        },
      ),
    );
  }
}

String _pct(dynamic rate) =>
    rate is num ? '${(rate * 100).toStringAsFixed(1)}%' : '—';
String _num(dynamic v) => v is num ? '$v' : '—';

class _SectionTitle extends StatelessWidget {
  final String text;
  final IconData icon;
  const _SectionTitle(this.text, this.icon);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 20, 4, 4),
      child: Row(children: [
        Icon(icon, color: EnhancedTheme.primaryTeal, size: 20),
        const SizedBox(width: 8),
        Text(text,
            style: GoogleFonts.outfit(
              color: context.labelColor,
              fontWeight: FontWeight.w800,
              fontSize: 18,
            )),
      ]),
    );
  }
}

class _Metric extends StatelessWidget {
  final String value;
  final String label;
  final String? sub;
  final bool danger;
  const _Metric({required this.value, required this.label, this.sub, this.danger = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value,
                style: GoogleFonts.outfit(
                  color: danger ? EnhancedTheme.errorRed : context.labelColor,
                  fontWeight: FontWeight.w800,
                  fontSize: 28,
                )),
            Text(label, style: TextStyle(color: context.hintColor, fontSize: 12)),
            if (sub != null) ...[
              const SizedBox(height: 4),
              Text(sub!, style: TextStyle(color: context.hintColor, fontSize: 12)),
            ],
          ],
        ),
      ),
    );
  }
}

class _Breakdown extends StatelessWidget {
  final String heading;
  final IconData icon;
  final List<dynamic> rows;
  final String labelKey;
  final String valueKey;
  final bool asPercent;
  const _Breakdown({
    required this.heading,
    required this.icon,
    required this.rows,
    required this.labelKey,
    this.valueKey = 'count',
    this.asPercent = false,
  });

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, color: EnhancedTheme.primaryTeal, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(heading,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.outfit(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    )),
              ),
            ]),
            const SizedBox(height: 10),
            MiniBarChart(
              rows: [
                for (final row in rows.cast<Map<String, dynamic>>())
                  (
                    label: '${row[labelKey] ?? ''}',
                    // Show resistance rates as 0-100 so a 0..1 fraction reads sensibly.
                    value: asPercent
                        ? ((row[valueKey] as num?) ?? 0) * 100
                        : (row[valueKey] as num?) ?? 0,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
