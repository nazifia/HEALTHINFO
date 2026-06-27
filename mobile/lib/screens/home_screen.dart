import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../resources.dart';
import '../l10n/app_localizations.dart';
import '../core/locale_provider.dart';
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
import 'interaction_check_screen.dart';
import 'differential_screen.dart';
import 'semantic_search_screen.dart';
import 'ask_screen.dart';
import 'global_search_screen.dart';
import 'dashboard_screen.dart';
import 'super_admin_dashboard_screen.dart';
import 'tenant_management_screen.dart';
import 'user_management_screen.dart';
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
/// The super-admin platform dashboard is prepended at runtime for super_admins
/// only (see [_HomeScreenState._sections]).
final List<_Section> _baseSections = [
  const _Section('Dashboard', Icons.insights_outlined, DashboardScreen()),
  for (final r in catalogResources)
    _Section(r.label, r.icon, CatalogListScreen(resource: r)),
  const _Section('Interactions', Icons.warning_amber_outlined, InteractionsScreen()),
  const _Section('Interaction checker', Icons.rule, InteractionCheckScreen()),
  const _Section('Differential', Icons.healing_outlined, DifferentialScreen()),
  const _Section('Semantic search', Icons.travel_explore, SemanticSearchScreen()),
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

  // Super-admins get the cross-tenant platform dashboard prepended; everyone
  // else sees just the base sections.
  List<_Section> _sections = _baseSections;

  @override
  void initState() {
    super.initState();
    _loadRole();
  }

  Future<void> _loadRole() async {
    final role = await api.myRole();
    if (!mounted || role != 'super_admin') return;
    setState(() {
      _sections = [
        const _Section('Platform', Icons.admin_panel_settings_outlined,
            SuperAdminDashboardScreen()),
        const _Section('Tenants', Icons.apartment_outlined,
            TenantManagementScreen()),
        const _Section('Users', Icons.manage_accounts_outlined,
            UserManagementScreen()),
        // Central-only cross-tenant collation views. Hidden from non-super-admins.
        const _Section('Collated reports', Icons.bar_chart_outlined,
            CollatedReportsScreen()),
        const _Section('ADR collation', Icons.vaccines_outlined,
            PlatformAdrScreen()),
        const _Section('Public health', Icons.public_outlined,
            PublicHealthScreen()),
        const _Section('Report sources', Icons.inventory_2_outlined,
            ReportSourcesScreen()),
        const _Section('Surveillance', Icons.notifications_active_outlined,
            SurveillanceScreen()),
        ..._baseSections,
      ];
    });
  }

  Future<void> _logout() async {
    await api.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  // Drawer/rail nav, reused for both the slide-out (narrow) and the always-on
  // pane (wide). `embedded` drops the brand header gap so it sits under the bar.
  Widget _nav(int catalogCount, {required bool embedded}) {
    return NavigationDrawer(
      backgroundColor: context.scaffoldBg,
      selectedIndex: _index,
      onDestinationSelected: (i) {
        setState(() => _index = i);
        if (!embedded) Navigator.of(context).pop(); // close slide-out drawer
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
              Flexible(
                child: Text('Health Info',
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    )),
              ),
            ],
          ),
        ),
        for (var i = 0; i < _sections.length; i++) ...[
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
    );
  }

  @override
  Widget build(BuildContext context) {
    final section = _sections[_index];
    final isDark = context.isDark;
    // Divider sits after the catalog block; shift it by however many super-admin
    // sections got prepended ahead of the base list.
    final catalogCount =
        catalogResources.length + (_sections.length - _baseSections.length);
    // ponytail: single breakpoint. Tablet/desktop get an always-on nav pane +
    // width-capped content; phones keep the slide-out drawer. Tune 900 if needed.
    final wide = MediaQuery.of(context).size.width >= 900;
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        automaticallyImplyLeading: !wide,
        title: Text(section.label),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const GlobalSearchScreen()),
            ),
            tooltip: 'Search catalog',
          ),
          _LanguageMenu(ref: ref),
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
      drawer: wide ? null : SizedBox(width: 280, child: _nav(catalogCount, embedded: false)),
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          SafeArea(
            child: Row(
              children: [
                if (wide) ...[
                  SizedBox(width: 300, child: _nav(catalogCount, embedded: true)),
                  const VerticalDivider(width: 1),
                ],
                Expanded(
                  child: _content(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── kept below build() to stay near the appBar that uses it ──
  // Width-capped page area so lists/forms don't stretch across a wide monitor.
  Widget _content() {
    final body = IndexedStack(
      index: _index,
      children: [for (final s in _sections) s.page],
    );
    return Center(
      child: ConstrainedBox(
        // Wide enough for the 3-col CardGrid (>=1400) to engage on big monitors.
        constraints: const BoxConstraints(maxWidth: 1500),
        child: body,
      ),
    );
  }
}

/// App-bar language switcher. Writes through [localeProvider], which persists
/// the choice; "System default" clears it back to the device locale.
class _LanguageMenu extends StatelessWidget {
  final WidgetRef ref;
  const _LanguageMenu({required this.ref});

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final current = ref.watch(localeProvider)?.languageCode;
    final names = {
      'en': t.langEnglish,
      'ha': t.langHausa,
      'yo': t.langYoruba,
      'ig': t.langIgbo,
    };
    return PopupMenuButton<String>(
      icon: const Icon(Icons.translate),
      tooltip: t.language,
      onSelected: (code) => ref.read(localeProvider.notifier).setLocale(
            code == 'system' ? null : Locale(code),
          ),
      itemBuilder: (context) => [
        CheckedPopupMenuItem(
          value: 'system',
          checked: current == null,
          child: Text(t.systemDefault),
        ),
        const PopupMenuDivider(),
        for (final l in supportedLocales)
          CheckedPopupMenuItem(
            value: l.languageCode,
            checked: current == l.languageCode,
            child: Text(names[l.languageCode] ?? l.languageCode),
          ),
      ],
    );
  }
}
