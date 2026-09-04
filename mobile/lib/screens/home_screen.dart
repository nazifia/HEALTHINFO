import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../resources.dart';
import '../l10n/app_localizations.dart';
import '../core/locale_provider.dart';
import '../core/theme/enhanced_theme.dart';
import '../core/theme/theme_provider.dart';
import 'catalog_list_screen.dart';
import 'patients_screen.dart';
import 'patient_access_log_screen.dart';
import 'cases_screen.dart';
import 'adr_screen.dart';
import 'lab_results_screen.dart';
import 'immunizations_screen.dart';
import 'vital_events_screen.dart';
import 'stock_reports_screen.dart';
import 'pharmacy_counter_screen.dart';
import 'pharmacy_stock_screen.dart';
import 'pharmacy_sales_screen.dart';
import 'pharmacy_till_screen.dart';
import 'pharmacy_claims_screen.dart';
import 'pharmacy_suppliers_screen.dart';
import 'pharmacy_orders_screen.dart';
import 'pharmacy_reports_screen.dart';
import 'branches_screen.dart';
import 'customers_screen.dart';
import 'drug_orders_screen.dart';
import 'prescriptions_screen.dart';
import 'prescribers_screen.dart';
import 'hospitals_screen.dart';
import 'stock_checks_screen.dart';
import 'stock_ledger_screen.dart';
import 'transfers_screen.dart';
import 'expenses_screen.dart';
import 'payment_requests_screen.dart';
import 'cashiers_screen.dart';
import 'commissions_screen.dart';
import 'notifications_screen.dart';
import 'dispensing_log_screen.dart';
import 'chw_reports_screen.dart';
import 'facility_metrics_screen.dart';
import 'insurance_claims_screen.dart';
import 'appointments_screen.dart';
import 'consultations_screen.dart';
import 'public_health_screen.dart';
import 'collated_reports_screen.dart';
import 'report_sources_screen.dart';
import 'platform_adr_screen.dart';
import 'surveillance_screen.dart';
import 'idsr_screen.dart';
import 'notifiable_screen.dart';
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

/// A collapsible block of sections in the drawer. `label` is the stable key —
/// it names the stored collapse state and picks the translation — so it must
/// stay unique and stay in English even when the drawer is not.
class _Group {
  final String label;
  final List<_Section> sections;
  const _Group(this.label, this.sections);
}

/// Group headers are the only nav text that is translated; the section labels
/// below them are still English everywhere.
String _groupLabel(AppLocalizations t, String key) => switch (key) {
      'Catalog' => t.navCatalog,
      'Clinical records' => t.navClinicalRecords,
      'Tools' => t.navTools,
      'Reports' => t.navReports,
      'Pharmacy' => t.navPharmacy,
      'Administration' => t.navAdministration,
      'Account' => t.navAccount,
      _ => key,
    };

/// Always visible above the groups — the drawer's "home".
const _dashboard = _Section('Dashboard', Icons.insights_outlined, DashboardScreen());

final _catalogGroup = _Group('Catalog', [
  for (final r in catalogResources) _Section(r.label, r.icon, CatalogListScreen(resource: r)),
]);

const _recordsGroup = _Group('Clinical records', [
  _Section('Patients', Icons.people_outline, PatientsScreen()),
  _Section('Consultations', Icons.medical_information_outlined, ConsultationsScreen()),
  _Section('Drug orders', Icons.medication_outlined, DrugOrdersScreen()),
  _Section('Case reports', Icons.assignment_outlined, CasesScreen()),
  _Section('Adverse reactions', Icons.medication_liquid_outlined, AdrScreen()),
  _Section('Lab results', Icons.science_outlined, LabResultsScreen()),
  _Section('Immunizations', Icons.vaccines_outlined, ImmunizationsScreen()),
  _Section('Vital events', Icons.child_friendly_outlined, VitalEventsScreen()),
  _Section('Appointments', Icons.event_outlined, AppointmentsScreen()),
]);

const _toolsGroup = _Group('Tools', [
  _Section('Interactions', Icons.warning_amber_outlined, InteractionsScreen()),
  _Section('Interaction checker', Icons.rule, InteractionCheckScreen()),
  _Section('Differential', Icons.healing_outlined, DifferentialScreen()),
  _Section('Semantic search', Icons.travel_explore, SemanticSearchScreen()),
  _Section('Ask AI', Icons.auto_awesome, AskScreen()),
]);

const _reportsGroup = _Group('Reports', [
  _Section('Pharmacy stock', Icons.inventory_2_outlined, StockReportsScreen()),
  _Section('CHW reports', Icons.groups_outlined, ChwReportsScreen()),
  _Section('Facility KPIs', Icons.local_hospital_outlined, FacilityMetricsScreen()),
  _Section('Insurance claims', Icons.receipt_long_outlined, InsuranceClaimsScreen()),
  _Section('IDSR report', Icons.assignment_outlined, IdsrScreen()),
  _Section('Notifiable cases', Icons.flag_outlined, NotifiableScreen()),
  _Section('Analytics', Icons.query_stats_outlined, AnalyticsScreen()),
]);

const _accountGroup = _Group('Account', [
  _Section('Profile', Icons.person_outline, ProfileScreen()),
]);

/// The groups every signed-in user sees, in drawer order.
List<_Group> get _baseGroups =>
    [_catalogGroup, _recordsGroup, _toolsGroup, _reportsGroup, _accountGroup];

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  static const _closedKey = 'navClosedGroups';

  int _index = 0;

  // Super-admins get the cross-tenant platform block, tenant admins the patient
  // access log, pharmacy staff the pharmacy block; everyone gets the base groups.
  List<_Group> _groups = _baseGroups;

  // Flattened view of [_groups] plus the dashboard at index 0. The drawer, the
  // app bar title and the IndexedStack all index into this.
  List<_Section> _flat = _flatten(_baseGroups);

  // Group labels the user collapsed, restored from disk on start.
  final Set<String> _closed = {};

  // Bumped by expand/collapse-all. It is part of every ExpansionTile key, so a
  // bump gives them fresh state that honours _closed again.
  int _navEpoch = 0;

  static List<_Section> _flatten(List<_Group> gs) =>
      [_dashboard, for (final g in gs) ...g.sections];

  // Governance view: who read patient data. Admin-only both here and in the API.
  static const _accessLogSection = _Section(
      'Patient access log', Icons.privacy_tip_outlined, PatientAccessLogScreen());

  // The pharmacy module. Shown to pharmacy staff only — the API gates it the
  // same way, so hiding the sections is convenience, not the control.
  // "Stock items" is this pharmacy's own shelf; "Pharmacy stock" in Reports
  // is the de-identified snapshot central surveillance reads.
  static const _pharmacyGroup = _Group('Pharmacy', [
    _Section('Pharmacy counter', Icons.local_pharmacy_outlined,
        PharmacyCounterScreen()),
    _Section('Prescriptions', Icons.description_outlined,
        PrescriptionsScreen()),
    _Section('Payment requests', Icons.pending_actions_outlined,
        PaymentRequestsScreen()),
    _Section('Stock items', Icons.inventory_outlined, PharmacyStockScreen()),
    _Section('Stock checks', Icons.fact_check_outlined, StockChecksScreen()),
    _Section('Stock ledger', Icons.receipt_long_outlined, StockLedgerScreen()),
    _Section('Transfers', Icons.swap_horiz_outlined, TransfersScreen()),
    _Section('Sales', Icons.point_of_sale_outlined, PharmacySalesScreen()),
    _Section('Returns', Icons.undo_outlined, ReturnsScreen()),
    _Section('Dispensing log', Icons.medication_outlined,
        DispensingLogScreen()),
    _Section('Cash drawer', Icons.point_of_sale_outlined, PharmacyTillScreen()),
    _Section('Expenses', Icons.receipt_outlined, ExpensesScreen()),
    _Section('Customers', Icons.people_alt_outlined, CustomersScreen()),
    _Section('Prescribers', Icons.badge_outlined, PrescribersScreen()),
    _Section('Hospitals', Icons.local_hospital_outlined, HospitalsScreen()),
    _Section('HMO claims', Icons.request_quote_outlined, PharmacyClaimsScreen()),
    _Section('Suppliers', Icons.local_shipping_outlined,
        PharmacySuppliersScreen()),
    _Section('Purchase orders', Icons.receipt_long_outlined,
        PharmacyOrdersScreen()),
    _Section('Pharmacy reports', Icons.assessment_outlined,
        PharmacyReportsScreen()),
    _Section('Alerts', Icons.notifications_none_outlined,
        NotificationsScreen()),
    _Section('Branches', Icons.storefront_outlined, BranchesScreen()),
    _Section('Cashiers', Icons.badge_outlined, CashiersScreen()),
    _Section('Staff commissions', Icons.percent_outlined, CommissionsScreen()),
  ]);

  // Central-only cross-tenant views. Hidden from non-super-admins.
  static const _platformGroup = _Group('Administration', [
    _Section('Platform', Icons.admin_panel_settings_outlined,
        SuperAdminDashboardScreen()),
    _Section('Tenants', Icons.apartment_outlined, TenantManagementScreen()),
    _Section('Users', Icons.manage_accounts_outlined, UserManagementScreen()),
    _accessLogSection,
    _Section('Collated reports', Icons.bar_chart_outlined,
        CollatedReportsScreen()),
    _Section('ADR collation', Icons.vaccines_outlined, PlatformAdrScreen()),
    _Section('Public health', Icons.public_outlined, PublicHealthScreen()),
    _Section('Report sources', Icons.inventory_2_outlined,
        ReportSourcesScreen()),
    _Section('Surveillance', Icons.notifications_active_outlined,
        SurveillanceScreen()),
  ]);

  @override
  void initState() {
    super.initState();
    _loadClosed();
    _loadRole();
  }

  Future<void> _loadClosed() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getStringList(_closedKey);
    if (!mounted || saved == null) return;
    setState(() => _closed
      ..clear()
      ..addAll(saved));
  }

  Future<void> _saveClosed() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_closedKey, _closed.toList());
  }

  void _toggleAll() {
    final anyOpen = _groups.any((g) => !_closed.contains(g.label));
    setState(() {
      _closed
        ..clear()
        ..addAll(anyOpen ? _groups.map((g) => g.label) : const <String>[]);
      _navEpoch++;
    });
    _saveClosed();
  }

  void _setGroups(List<_Group> gs) {
    setState(() {
      _groups = gs;
      _flat = _flatten(gs);
    });
  }

  Future<void> _loadRole() async {
    final role = await api.myRole();
    if (!mounted) return;
    final pharmacy = isPharmacyStaff(role) ? [_pharmacyGroup] : <_Group>[];
    if (role == 'super_admin') {
      _setGroups([_platformGroup, ...pharmacy, ..._baseGroups]);
      return;
    }
    if (role == 'tenant_admin') {
      _setGroups([
        const _Group('Administration', [_accessLogSection]),
        ...pharmacy,
        ..._baseGroups,
      ]);
      return;
    }
    if (pharmacy.isNotEmpty) _setGroups([...pharmacy, ..._baseGroups]);
  }

  Future<void> _logout() async {
    await api.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
    );
  }

  // Drawer/rail nav, reused for both the slide-out (narrow) and the always-on
  // pane (wide). `embedded` keeps the slide-out from popping the route twice.
  Widget _nav({required bool embedded}) {
    // Index 0 is the dashboard; each group's tiles follow in flattened order.
    var i = 1;
    final tiles = <Widget>[];
    for (final g in _groups) {
      final first = i;
      final children = [
        for (final s in g.sections) _navTile(s, i++, embedded: embedded),
      ];
      tiles.add(_navGroupTile(g, children, first, i, embedded: embedded));
    }
    return Material(
      color: context.scaffoldBg,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          _brandHeader(),
          _navTile(_dashboard, 0, embedded: embedded),
          _toggleAllButton(),
          ...tiles,
        ],
      ),
    );
  }

  Widget _toggleAllButton() {
    final t = AppLocalizations.of(context);
    final anyOpen = _groups.any((g) => !_closed.contains(g.label));
    return Align(
      alignment: Alignment.centerRight,
      child: Padding(
        padding: const EdgeInsets.only(right: 14, top: 2),
        child: TextButton.icon(
          onPressed: _toggleAll,
          icon: Icon(anyOpen ? Icons.unfold_less : Icons.unfold_more, size: 16),
          label: Text(anyOpen ? t.navCollapseAll : t.navExpandAll,
              style: const TextStyle(fontSize: 12)),
          style: TextButton.styleFrom(
            foregroundColor: context.subLabelColor,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            minimumSize: const Size(0, 28),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
        ),
      ),
    );
  }

  Widget _brandHeader() => Container(
        margin: const EdgeInsets.fromLTRB(12, 16, 12, 12),
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
      );

  // One collapsible block. Opens on its own if it holds the current section, so
  // a restored collapse never hides where the user is.
  Widget _navGroupTile(_Group g, List<Widget> children, int first, int endExclusive,
      {required bool embedded}) {
    // After an explicit collapse-all, honour it — even for the group the user
    // is standing in. Before that, never hide the current section.
    final holdsSelection =
        _navEpoch == 0 && _index >= first && _index < endExclusive;
    return ExpansionTile(
      key: ValueKey('${g.label}:$_navEpoch'),
      initiallyExpanded: holdsSelection || !_closed.contains(g.label),
      onExpansionChanged: (open) {
        open ? _closed.remove(g.label) : _closed.add(g.label);
        _saveClosed();
      },
      tilePadding: const EdgeInsets.symmetric(horizontal: 20),
      childrenPadding: const EdgeInsets.only(bottom: 4),
      shape: const Border(),
      collapsedShape: const Border(),
      dense: true,
      title: Text(
        _groupLabel(AppLocalizations.of(context), g.label).toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.1,
          color: context.subLabelColor,
        ),
      ),
      children: children,
    );
  }

  // One destination. Rounded, inset, tinted when selected — matches the web nav.
  Widget _navTile(_Section s, int i, {required bool embedded}) {
    // The drawer numbers its tiles by hand; _flat must agree or taps open the
    // wrong page. Debug-only check, fires the moment the two orders drift.
    assert(identical(_flat[i], s), 'nav index $i does not match _flat');
    final selected = _index == i;
    final accent = Theme.of(context).colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 1),
      child: ListTile(
        dense: true,
        visualDensity: VisualDensity.compact,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        selected: selected,
        selectedTileColor: accent.withValues(alpha: 0.12),
        selectedColor: accent,
        leading: Icon(s.icon, size: 20),
        minLeadingWidth: 20,
        title: Text(
          s.label,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: 14,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
        onTap: () {
          setState(() => _index = i);
          if (!embedded) Navigator.of(context).pop(); // close slide-out drawer
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final section = _flat[_index];
    final isDark = context.isDark;
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
      drawer: wide ? null : Drawer(width: 288, child: _nav(embedded: false)),
      body: Stack(
        children: [
          Positioned.fill(child: DecoratedBox(decoration: context.bgGradient)),
          SafeArea(
            child: Row(
              children: [
                if (wide) ...[
                  SizedBox(width: 300, child: _nav(embedded: true)),
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
      children: [for (final s in _flat) s.page],
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
      color: Theme.of(context).colorScheme.surface,
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
