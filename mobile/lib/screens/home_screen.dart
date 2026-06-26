import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../resources.dart';
import '../core/theme/enhanced_theme.dart';
import '../core/theme/theme_provider.dart';
import 'catalog_list_screen.dart';
import 'cases_screen.dart';
import 'adr_screen.dart';
import 'lab_results_screen.dart';
import 'immunizations_screen.dart';
import 'vital_events_screen.dart';
import 'stock_reports_screen.dart';
import 'chw_reports_screen.dart';
import 'facility_metrics_screen.dart';
import 'insurance_claims_screen.dart';
import 'appointments_screen.dart';
import 'public_health_screen.dart';
import 'collated_reports_screen.dart';
import 'report_sources_screen.dart';
import 'platform_adr_screen.dart';
import 'surveillance_screen.dart';
import 'analytics_screen.dart';
import 'interactions_screen.dart';
import 'ask_screen.dart';
import 'global_search_screen.dart';
import 'dashboard_screen.dart';
import 'profile_screen.dart';
import 'login_screen.dart';

/// One navigable section: a label + icon for the drawer and the page widget.
class _Section {
  final String label;
  final IconData icon;
  final Widget page;
  const _Section(this.label, this.icon, this.page);
}

/// Catalog tabs (data-driven) followed by the standalone feature screens.
final List<_Section> _sections = [
  const _Section('Dashboard', Icons.insights_outlined, DashboardScreen()),
  for (final r in catalogResources)
    _Section(r.label, r.icon, CatalogListScreen(resource: r)),
  const _Section('Interactions', Icons.warning_amber_outlined, InteractionsScreen()),
  const _Section('Case reports', Icons.assignment_outlined, CasesScreen()),
  const _Section('Adverse reactions', Icons.medication_liquid_outlined, AdrScreen()),
  const _Section('Lab results', Icons.science_outlined, LabResultsScreen()),
  const _Section('Immunizations', Icons.vaccines_outlined, ImmunizationsScreen()),
  const _Section('Vital events', Icons.child_friendly_outlined, VitalEventsScreen()),
  const _Section('Pharmacy stock', Icons.inventory_2_outlined, StockReportsScreen()),
  const _Section('CHW reports', Icons.groups_outlined, ChwReportsScreen()),
  const _Section('Facility KPIs', Icons.local_hospital_outlined, FacilityMetricsScreen()),
  const _Section('Insurance claims', Icons.receipt_long_outlined, InsuranceClaimsScreen()),
  const _Section('Appointments', Icons.event_outlined, AppointmentsScreen()),
  const _Section('Public health', Icons.public_outlined, PublicHealthScreen()),
  const _Section('Collated reports', Icons.bar_chart_outlined, CollatedReportsScreen()),
  const _Section('Report sources', Icons.inventory_2_outlined, ReportSourcesScreen()),
  const _Section('ADR collation', Icons.vaccines_outlined, PlatformAdrScreen()),
  const _Section('Surveillance', Icons.notifications_active_outlined, SurveillanceScreen()),
  const _Section('Analytics', Icons.query_stats_outlined, AnalyticsScreen()),
  const _Section('Ask AI', Icons.auto_awesome, AskScreen()),
  const _Section('Profile', Icons.person_outline, ProfileScreen()),
];

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  int _index = 0;

  Future<void> _logout() async {
    await api.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final section = _sections[_index];
    final isDark = context.isDark;
    final catalogCount = catalogResources.length;
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(section.label),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const GlobalSearchScreen()),
            ),
            tooltip: 'Search catalog',
          ),
          IconButton(
            icon: Icon(isDark ? Icons.light_mode : Icons.dark_mode),
            onPressed: () => ref.read(themeModeProvider.notifier).toggle(),
            tooltip: 'Toggle theme',
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _logout,
            tooltip: 'Sign out',
          ),
          const SizedBox(width: 4),
        ],
      ),
      drawer: SizedBox(
        width: 280,
        child: NavigationDrawer(
        backgroundColor: context.scaffoldBg,
        selectedIndex: _index,
        onDestinationSelected: (i) {
          setState(() => _index = i);
          Navigator.of(context).pop(); // close drawer
        },
        children: [
          Container(
            margin: const EdgeInsets.fromLTRB(12, 16, 12, 8),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [EnhancedTheme.primaryTeal, EnhancedTheme.accentCyan],
              ),
              borderRadius: BorderRadius.circular(24),
              boxShadow: [
                BoxShadow(
                  color: EnhancedTheme.primaryTeal.withValues(alpha: 0.3),
                  blurRadius: 18,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: const Row(
              children: [
                Icon(Icons.health_and_safety, color: Colors.white, size: 36),
                SizedBox(width: 12),
                Text('Health Info',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    )),
              ],
            ),
          ),
          for (var i = 0; i < _sections.length; i++) ...[
            // Separate the catalog tabs from the feature screens.
            if (i == catalogCount)
              const Padding(
                padding: EdgeInsets.fromLTRB(28, 12, 28, 4),
                child: Divider(),
              ),
            NavigationDrawerDestination(
              icon: Icon(_sections[i].icon),
              label: Text(_sections[i].label),
            ),
          ],
        ],
      ),
      ),
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          SafeArea(
            child: IndexedStack(
              index: _index,
              children: [for (final s in _sections) s.page],
            ),
          ),
        ],
      ),
    );
  }
}
