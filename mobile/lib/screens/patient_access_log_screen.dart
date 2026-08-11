import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/responsive.dart';
import '../shared/widgets/stats_kit.dart';
import '../shared/widgets/bar_chart.dart';

/// Who read patient data — GET /api/patients/access-log/.
/// Tenant admins (and super admins) only; the backend 403s everyone else,
/// including the clinical staff whose reads fill this log.
class PatientAccessLogScreen extends StatefulWidget {
  // Set to scope the log to one patient's trail (?patient=<id>).
  final int? patientId;
  const PatientAccessLogScreen({super.key, this.patientId});

  @override
  State<PatientAccessLogScreen> createState() => _PatientAccessLogScreenState();
}

class _PatientAccessLogScreenState extends State<PatientAccessLogScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;
  String _action = 'all';

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<dynamic>> _load() => api.getList('/api/patients/access-log/', {
        if (widget.patientId != null) 'patient': '${widget.patientId}',
        if (_action != 'all') 'action': _action,
      });

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      // Scoped to one patient means we were pushed as a route and need our own
      // bar; the nav section (no patientId) sits inside the home chrome.
      appBar: widget.patientId == null
          ? null
          : AppBar(title: const Text('Who accessed this record')),
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
                  icon: Icons.lock_outline,
                  title: 'Could not load the access log',
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
                  icon: Icons.history_toggle_off,
                  title: 'Nothing recorded yet',
                  message: 'Every read of a patient record shows up here.',
                ),
              ]);
            }
            return CardGrid(
              itemCount: items.length,
              header: _Header(
                items: items,
                action: _action,
                onAction: (a) {
                  _action = a;
                  _reload();
                },
              ),
              itemBuilder: (context, i) => _Row(row: items[i]),
            );
          },
        ),
      ),
    );
  }
}

const _actions = ['all', 'list', 'retrieve', 'history'];

const _actionColor = {
  'list': EnhancedTheme.infoBlue,
  'retrieve': EnhancedTheme.accentPurple,
  'history': EnhancedTheme.accentCyan,
};

const _actionIcon = {
  'list': Icons.list_alt_outlined,
  'retrieve': Icons.person_search_outlined,
  'history': Icons.history,
};

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  final String action;
  final ValueChanged<String> onAction;
  const _Header(
      {required this.items, required this.action, required this.onAction});

  @override
  Widget build(BuildContext context) {
    final byUser = countBy(items, 'user_name');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        children: [
          StatsHeader(
            icon: Icons.privacy_tip_outlined,
            title: 'Patient access log',
            subtitle: '${items.length} read${items.length == 1 ? '' : 's'} recorded',
            color: EnhancedTheme.accentPurple,
          ),
          KpiRow(tiles: [
            KpiTile(
                icon: _actionIcon['list']!,
                label: 'Lists',
                value: '${countEq(items, 'action', 'list')}',
                color: _actionColor['list']!),
            KpiTile(
                icon: _actionIcon['retrieve']!,
                label: 'Records',
                value: '${countEq(items, 'action', 'retrieve')}',
                color: _actionColor['retrieve']!),
            KpiTile(
                icon: _actionIcon['history']!,
                label: 'Histories',
                value: '${countEq(items, 'action', 'history')}',
                color: _actionColor['history']!),
          ]),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            children: [
              for (final a in _actions)
                ChoiceChip(
                  label: Text(a),
                  selected: action == a,
                  onSelected: (_) => onAction(a),
                ),
            ],
          ),
          const SizedBox(height: 10),
          if (byUser.isNotEmpty)
            StatSection(
              icon: Icons.people_alt_outlined,
              heading: 'By user',
              color: EnhancedTheme.accentPurple,
              child: MiniBarChart(rows: byUser),
            ),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final Map<String, dynamic> row;
  const _Row({required this.row});

  @override
  Widget build(BuildContext context) {
    final action = '${row['action'] ?? ''}';
    final color = _actionColor[action] ?? EnhancedTheme.primaryTeal;
    final who = '${row['user_name'] ?? ''}'.trim().isEmpty
        ? '${row['user_phone'] ?? 'Unknown user'}'
        : '${row['user_name']}';
    final target = '${row['patient_name'] ?? ''}'.trim();
    final query = '${row['query'] ?? ''}'.trim();
    final at = '${row['created_at'] ?? ''}'.replaceFirst('T', ' ');
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(_actionIcon[action] ?? Icons.visibility_outlined,
                size: 16, color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(who,
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 15)),
            ),
            Text('${row['result_count'] ?? 0} row(s)',
                style: TextStyle(color: context.hintColor, fontSize: 11)),
          ]),
          const SizedBox(height: 6),
          Text(
            target.isEmpty
                ? 'Searched the register'
                : 'Opened $target${action == 'history' ? "'s history" : ''}',
            style: TextStyle(color: context.labelColor, fontSize: 13),
          ),
          if (query.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text('search: "$query"',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            ),
          const SizedBox(height: 6),
          Text(at.split('.').first,
              style: TextStyle(color: context.hintColor, fontSize: 11)),
        ],
      ),
    );
  }
}
