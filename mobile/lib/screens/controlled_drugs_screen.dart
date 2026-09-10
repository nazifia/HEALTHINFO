import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart' show units;
import '../core/theme/enhanced_theme.dart';
import '../shared/controlled_stats.dart';
import '../shared/widgets/breakdown_card.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/stats_kit.dart';

/// The state's controlled-drug register: what was written for, what was handed
/// over, and what left the counter with no script behind it. Aggregate-only —
/// the rollup names areas and drugs, never a patient or a prescriber.
///
/// Its own screen so a regulator can open it directly; the same cards also run
/// as a section of PublicHealthScreen.
class ControlledDrugsScreen extends StatefulWidget {
  const ControlledDrugsScreen({super.key});

  @override
  State<ControlledDrugsScreen> createState() => _ControlledDrugsScreenState();
}

class _ControlledDrugsScreenState extends State<ControlledDrugsScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  /// Platform rollup only — a pharmacy reads its own register, not the
  /// state's, so there is no tenant-scoped twin to fall back to.
  Future<Map<String, dynamic>> _load() async {
    final r = await api.get('/api/analytics/platform/controlled/');
    return (r as Map).cast<String, dynamic>();
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        final f = _load();
        setState(() { _future = f; });
        await f;
      },
      child: FutureBuilder<Map<String, dynamic>>(
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
                title: 'Could not load the controlled register',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: controlledCards(snap.data),
          );
        },
      ),
    );
  }
}

/// The cards for one controlled-drug rollup payload, in reading order.
List<Widget> controlledCards(Map? poison) => [
      MetricCard(
        value: units(controlledTotal(poison, 'prescribed_units')),
        label: 'Controlled units prescribed',
        sub: '${units(controlledTotal(poison, 'prescribed'))} script line(s) '
            'across the patch',
      ),
      MetricCard(
        value: units(controlledTotal(poison, 'dispensed_units')),
        label: 'Controlled units dispensed',
        sub: '${units(controlledTotal(poison, 'dispensed'))} line(s) handed '
            'over — the rest was written for and never collected',
      ),
      MetricCard(
        value: units(controlledTotal(poison, 'otc_units')),
        label: 'Controlled units sold with no script',
        sub: '${units(controlledTotal(poison, 'otc'))} till line(s) — '
            'net of returns, cancelled sales left out',
      ),
      BreakdownCard(
        heading: 'Dispensed by area',
        icon: Icons.map_outlined,
        rows: controlledByArea(poison, 'dispensed_units'),
        labelKey: 'area',
        valueKey: 'value',
      ),
      BreakdownCard(
        heading: 'Sold with no script, by area',
        icon: Icons.point_of_sale_outlined,
        rows: controlledByArea(poison, 'otc_units'),
        labelKey: 'area',
        valueKey: 'value',
      ),
      BreakdownCard(
        heading: 'Most dispensed controlled drugs',
        icon: Icons.medication_outlined,
        rows: controlledByDrug(poison, 'dispensed_units'),
        labelKey: 'drug',
        valueKey: 'value',
      ),
      BreakdownCard(
        heading: 'Most sold over the counter',
        icon: Icons.medication_liquid_outlined,
        rows: controlledByDrug(poison, 'otc_units'),
        labelKey: 'drug',
        valueKey: 'value',
      ),
    ];
