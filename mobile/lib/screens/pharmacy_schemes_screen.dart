import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/searchable_dropdown.dart';
import '../shared/widgets/snack.dart';
import 'pharmacy_kit.dart';
import 'pharmacy_sales_screen.dart' show askText;
import 'report_scaffold.dart';

/// The insurers the pharmacy bills, who is a member of which, and what each
/// scheme pays for a particular drug.
///
/// The counter reads all three every time it prices an insured sale, but only
/// the pharmacy admin sets the first two — the same split the API enforces, so
/// a hidden button here is convenience rather than the control itself.
///
/// The price list is the exception: an insurer signed in on its own seat keeps
/// its own (IsSchemePriceListEditor), so the whole user is read here rather
/// than the role alone — the scheme a seat answers for decides what it writes.
class PharmacySchemesScreen extends StatelessWidget {
  const PharmacySchemesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>?>(
      future: api.me(),
      builder: (context, snap) {
        final role = snap.data?['role']?.toString();
        final admin = isPharmacyAdmin(role);
        final myHmo = snap.data?['hmo'];
        return DefaultTabController(
          length: 4,
          child: Column(children: [
            const TabBar(
              labelColor: EnhancedTheme.primaryTeal,
              indicatorColor: EnhancedTheme.primaryTeal,
              isScrollable: true,
              tabs: [
                Tab(text: 'Insurers'),
                Tab(text: 'Members'),
                Tab(text: 'Dependents'),
                Tab(text: 'Price list'),
              ],
            ),
            Expanded(
              child: TabBarView(children: [
                _HmosTab(admin: admin, platform: role == 'super_admin'),
                _MembersTab(admin: admin),
                _DependentsTab(answers: answersForInsurer(role)),
                _RulesTab(
                  canEdit: canEditPriceList(role, hmoId: myHmo),
                  insurer: role == 'hmo',
                  myHmoId: myHmo is int ? myHmo : null,
                ),
              ]),
            ),
          ]),
        );
      },
    );
  }
}

/* ------------------------------------------------------------- insurers */

class _HmosTab extends StatelessWidget {
  final bool admin;

  /// The platform admin signs an insurer up rather than typing a row for it:
  /// the scheme and the seat that runs its desk are one decision, so their
  /// button opens the sign-up sheet instead of the plain insurer form. Editing
  /// an existing scheme is the same form for everyone.
  final bool platform;
  const _HmosTab({required this.admin, this.platform = false});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/hmos/',
      searchHint: 'Insurer name or code…',
      fabLabel: platform ? 'Register scheme' : 'Add insurer',
      showFab: admin,
      emptyIcon: Icons.health_and_safety_outlined,
      emptyTitle: 'No insurers yet',
      emptyMessage: admin
          ? 'Add the HMOs and NHIA schemes this pharmacy bills.'
          : 'The pharmacy admin keeps the list of insurers.',
      savedMessage: platform ? 'Scheme saved.' : 'Insurer saved.',
      filters: const [
        ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
          'true': 'Active',
          'false': 'Retired',
        }),
      ],
      card: (row, reload, edit) => _HmoCard(row: row, admin: admin, edit: edit),
      form: (existing) => platform && existing == null
          ? const _SchemeSignUpForm()
          : _HmoForm(existing: existing),
    );
  }
}

class _HmoCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool admin;
  final VoidCallback edit;
  const _HmoCard({required this.row, required this.admin, required this.edit});

  @override
  Widget build(BuildContext context) {
    // A threshold of 0 is not "no cover" — it is "never ask first", which is a
    // different thing and worth saying in words.
    final threshold = num.tryParse('${row['preauth_threshold'] ?? 0}') ?? 0;
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Row(children: [
        Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${row['name']}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
            Text(
                '${row['code']?.toString().isNotEmpty == true ? '${row['code']} · ' : ''}'
                'pays ${row['coverage_percent']}% by default',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
            Text(
                threshold > 0
                    ? 'Clears an insured sale above ${money(threshold)} first'
                    : 'No authorisation asked for',
                style: TextStyle(color: context.hintColor, fontSize: 12)),
          ]),
        ),
        if (row['is_active'] != true)
          const ReportBadge(text: 'retired', color: EnhancedTheme.errorRed),
        if (admin)
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
      ]),
    );
  }
}

class _HmoForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _HmoForm({this.existing});

  @override
  State<_HmoForm> createState() => _HmoFormState();
}

class _HmoFormState extends State<_HmoForm> {
  final _name = TextEditingController();
  final _code = TextEditingController();
  final _contact = TextEditingController();
  final _email = TextEditingController();
  final _coverage = TextEditingController(text: '100');
  final _threshold = TextEditingController(text: '0');
  bool _autoSubmit = false;
  bool _active = true;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _name.text = '${e['name'] ?? ''}';
      _code.text = '${e['code'] ?? ''}';
      _contact.text = '${e['contact'] ?? ''}';
      _email.text = '${e['email'] ?? ''}';
      _coverage.text = '${e['coverage_percent'] ?? '100'}';
      _threshold.text = '${e['preauth_threshold'] ?? '0'}';
      _autoSubmit = e['auto_submit_claims'] == true;
      _active = e['is_active'] == true;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _code.dispose();
    _contact.dispose();
    _email.dispose();
    _coverage.dispose();
    _threshold.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Name the insurer.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'name': _name.text.trim(),
        'code': _code.text.trim(),
        'contact': _contact.text.trim(),
        'email': _email.text.trim(),
        'coverage_percent': _coverage.text.trim(),
        'preauth_threshold': _threshold.text.trim().isEmpty
            ? '0'
            : _threshold.text.trim(),
        'auto_submit_claims': _autoSubmit,
        'is_active': _active,
      };
      if (_isEdit) {
        await api.patch('/api/pharmacy/hmos/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pharmacy/hmos/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _isEdit ? 'Edit insurer' : 'New insurer',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add insurer',
      onSubmit: _submit,
      children: [
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Insurer'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _code,
          decoration: const InputDecoration(labelText: 'Code (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _contact,
          decoration: const InputDecoration(labelText: 'Contact (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: 'Email (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _coverage,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Default cover %',
            helperText: 'What the insurer pays where no drug rule says otherwise',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _threshold,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Pre-authorisation threshold',
            helperText: 'Insured amount above which a sale is cleared first. '
                '0 asks for no authorisation.',
          ),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Send each claim as it happens'),
          subtitle: const Text('Off means a claim waits for the monthly batch'),
          value: _autoSubmit,
          onChanged: (v) => setState(() => _autoSubmit = v),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Active'),
          subtitle: const Text('A retired insurer takes no new members'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
      ],
    );
  }
}

/// Sign an insurer up: the scheme, and the seat that will run its desk.
///
/// Platform admin only (the API refuses anyone else) — an insurer joining is
/// not the pharmacy's decision. One post writes both, so a rejected password
/// leaves no scheme behind with nobody able to sign in to it, and from here
/// the scheme staffs itself: the seat minted carries the portal-admin flag.
///
/// The seat is a switch rather than the only way through: an insurer that
/// sends no one to the platform is still a scheme the pharmacy bills, and
/// turning it off files that row the plain way (POST /api/pharmacy/hmos/).
class _SchemeSignUpForm extends StatefulWidget {
  const _SchemeSignUpForm();

  @override
  State<_SchemeSignUpForm> createState() => _SchemeSignUpFormState();
}

class _SchemeSignUpFormState extends State<_SchemeSignUpForm> {
  final _name = TextEditingController();
  final _code = TextEditingController();
  final _contact = TextEditingController();
  final _email = TextEditingController();
  final _coverage = TextEditingController(text: '100');
  final _threshold = TextEditingController(text: '0');
  final _adminPhone = TextEditingController();
  final _adminName = TextEditingController();
  final _adminEmail = TextEditingController();
  final _adminPassword = TextEditingController();
  bool _autoSubmit = false;
  bool _withAdmin = true;
  bool _saving = false;
  String? _error;
  int? _tenantId;
  List<Map<String, dynamic>> _tenants = const [];

  @override
  void initState() {
    super.initState();
    _loadTenants();
  }

  Future<void> _loadTenants() async {
    try {
      final rows = await api.getList('/api/tenants/', {'page_size': '100'});
      if (mounted) setState(() => _tenants = rows.cast<Map<String, dynamic>>());
    } catch (e) {
      // Without the list there is no organization to pin the scheme to, so say
      // so here rather than letting the save fail on a field left empty.
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _code.dispose();
    _contact.dispose();
    _email.dispose();
    _coverage.dispose();
    _threshold.dispose();
    _adminPhone.dispose();
    _adminName.dispose();
    _adminEmail.dispose();
    _adminPassword.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final body = schemeSignUpBody(
      tenantId: _tenantId,
      name: _name.text,
      code: _code.text,
      contact: _contact.text,
      email: _email.text,
      coveragePercent: _coverage.text,
      preauthThreshold: _threshold.text,
      autoSubmitClaims: _autoSubmit,
      adminPhone: _adminPhone.text,
      adminName: _adminName.text,
      adminEmail: _adminEmail.text,
      adminPassword: _adminPassword.text,
    );
    final missing = schemeSignUpProblem(body, withAdmin: _withAdmin);
    if (missing != null) {
      setState(() => _error = missing);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      // No seat to mint: the scheme is a row the pharmacy keeps itself, and
      // the plain insurer endpoint is what files one. The tenant rides in the
      // header there, so the pick has to be the organization already open.
      if (_withAdmin) {
        await api.post('/api/pharmacy/hmos/register/', body);
      } else {
        await api.post('/api/pharmacy/hmos/', body['scheme']);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _withAdmin ? 'Register a scheme' : 'Add an insurer',
      saving: _saving,
      error: _error,
      submitLabel: _withAdmin ? 'Register scheme' : 'Add insurer',
      onSubmit: _submit,
      children: [
        SearchableDropdown<int>(
          initialValue: _tenantId,
          decoration: const InputDecoration(
            labelText: 'Organization',
            helperText: 'Whose claims this scheme answers for',
          ),
          items: [
            for (final t in _tenants)
              DropdownMenuItem(
                value: t['id'] as int,
                child: Text('${t['name']}'),
              ),
          ],
          onChanged: (v) => setState(() => _tenantId = v),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _name,
          decoration: const InputDecoration(labelText: 'Scheme'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _code,
          decoration: const InputDecoration(labelText: 'Code (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _contact,
          decoration: const InputDecoration(labelText: 'Contact (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: 'Email (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _coverage,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Default cover %',
            helperText:
                'What the insurer pays where no drug rule says otherwise',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _threshold,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Pre-authorisation threshold',
            helperText:
                'Insured amount above which a sale is cleared first. '
                '0 asks for no authorisation.',
          ),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Send each claim as it happens'),
          subtitle: const Text('Off means a claim waits for the monthly batch'),
          value: _autoSubmit,
          onChanged: (v) => setState(() => _autoSubmit = v),
        ),
        const Divider(height: 24),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Give the scheme its own admin'),
          subtitle: const Text(
            'Off files the insurer as a row the pharmacy keeps itself',
          ),
          value: _withAdmin,
          onChanged: (v) => setState(() => _withAdmin = v),
        ),
        if (_withAdmin) ...[
          Text(
            'Scheme admin',
            style: TextStyle(
              color: context.labelColor,
              fontWeight: FontWeight.w700,
            ),
          ),
          Text(
            "Runs the scheme's desk and adds the rest of its staff itself.",
            style: TextStyle(color: context.hintColor, fontSize: 12),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _adminPhone,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              labelText: 'Phone',
              helperText: 'They sign in with it',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _adminName,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(labelText: 'Name (optional)'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _adminEmail,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(labelText: 'Email (optional)'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _adminPassword,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Password'),
          ),
        ],
      ],
    );
  }
}

/* -------------------------------------------------------------- members */

class _MembersTab extends StatelessWidget {
  final bool admin;
  const _MembersTab({required this.admin});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/enrollments/',
      searchHint: 'Member number or patient…',
      fabLabel: 'Enrol a patient',
      // Any pharmacy staffer enrols a patient — a card presented at the
      // counter is registered there, not in a back office.
      emptyIcon: Icons.badge_outlined,
      emptyTitle: 'Nobody enrolled yet',
      emptyMessage: 'Register the card a patient presents at the counter.',
      savedMessage: 'Membership saved.',
      filters: const [
        ReportFilter(param: 'is_active', anyLabel: 'Any state', options: {
          'true': 'Active',
          'false': 'Lapsed',
        }),
      ],
      card: (row, reload, edit) => _MemberCard(row: row, edit: edit),
      form: (existing) => _MemberForm(existing: existing),
    );
  }
}

class _MemberCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback edit;
  const _MemberCard({required this.row, required this.edit});

  @override
  Widget build(BuildContext context) {
    final remaining = row['remaining_benefit'];
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Row(children: [
        Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${row['patient_name'] ?? 'Patient'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
            Text('${row['hmo_name']} · ${row['member_number']}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
            Text(
                'Covered at ${row['effective_coverage']}%'
                // Null is an uncapped plan, which is not the same as nothing
                // left — say which.
                '${remaining == null ? ' · uncapped' : ' · ${money(remaining)} left this year'}',
                style: TextStyle(color: context.hintColor, fontSize: 12)),
          ]),
        ),
        if (row['is_valid'] != true)
          const ReportBadge(text: 'not valid', color: EnhancedTheme.errorRed),
        IconButton(
            icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
      ]),
    );
  }
}

/* ----------------------------------------------------------- dependents */

/// People principals asked to have covered under their card, raised from the
/// patient portal. The scheme's own seat (or the pharmacy admin for it)
/// answers — at any time, in either direction — so both buttons show
/// whichever way it stands. Mirrors the web's pharmacy-dependents resource.
class _DependentsTab extends StatelessWidget {
  final bool answers;
  const _DependentsTab({required this.answers});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/dependents/',
      searchHint: 'Dependent, principal or number…',
      fabLabel: '',
      showFab: false,
      emptyIcon: Icons.family_restroom_outlined,
      emptyTitle: 'No dependents asked for',
      emptyMessage: 'Members add them from their own portal.',
      savedMessage: '',
      filters: const [
        ReportFilter(param: 'status', anyLabel: 'Any state', options: {
          'pending': 'Awaiting approval',
          'approved': 'Approved',
          'declined': 'Declined',
        }),
      ],
      card: (row, reload, _) =>
          _DependentCard(row: row, reload: reload, answers: answers),
      form: (_) => const SizedBox.shrink(),
    );
  }
}

class _DependentCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  final bool answers;
  const _DependentCard(
      {required this.row, required this.reload, required this.answers});

  Future<void> _answer(BuildContext context, String action) async {
    final typed = await askText(
        context,
        action == 'approve' ? 'Approve dependent' : 'Decline dependent',
        action == 'approve' ? 'Member number (optional)' : 'Reason');
    if (typed == null || !context.mounted) return;
    final body = {action == 'approve' ? 'member_number' : 'reason': typed};
    try {
      final r = await api.post(
          '/api/pharmacy/dependents/${row['id']}/$action/', body);
      if (context.mounted) {
        showSuccess(context, '${(r as Map?)?['message'] ?? 'Done.'}');
      }
      reload();
    } catch (e) {
      if (context.mounted) showError(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = '${row['status']}';
    final (badge, color) = switch (status) {
      'approved' => ('approved', EnhancedTheme.successGreen),
      'declined' => ('declined', EnhancedTheme.errorRed),
      _ => ('pending', EnhancedTheme.warningAmber),
    };
    final note = status == 'approved'
        ? '${row['member_number'] ?? ''}'
        : '${row['reason'] ?? ''}';
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${row['full_name'] ?? 'Dependent'}',
                      style: TextStyle(
                          color: context.labelColor,
                          fontWeight: FontWeight.w700,
                          fontSize: 15)),
                  Text(
                      '${row['relationship']} of ${row['principal_name']}'
                      ' · ${row['hmo_name']} ${row['principal_number']}',
                      style:
                          TextStyle(color: context.hintColor, fontSize: 13)),
                  if (note.isNotEmpty)
                    Text(note,
                        style:
                            TextStyle(color: context.hintColor, fontSize: 12)),
                ]),
          ),
          ReportBadge(text: badge, color: color),
        ]),
        if (answers)
          Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            if (status != 'approved')
              TextButton(
                  onPressed: () => _answer(context, 'approve'),
                  child: const Text('Approve')),
            if (status != 'declined')
              TextButton(
                  onPressed: () => _answer(context, 'decline'),
                  style: TextButton.styleFrom(
                      foregroundColor: EnhancedTheme.errorRed),
                  child: const Text('Decline')),
          ]),
      ]),
    );
  }
}

class _MemberForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _MemberForm({this.existing});

  @override
  State<_MemberForm> createState() => _MemberFormState();
}

class _MemberFormState extends State<_MemberForm> {
  final _number = TextEditingController();
  final _plan = TextEditingController();
  final _coverage = TextEditingController();
  final _limit = TextEditingController();
  int? _patientId;
  String? _patientName;
  int? _hmoId;
  String? _hmoName;
  DateTime? _from;
  DateTime? _to;
  bool _active = true;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _number.text = '${e['member_number'] ?? ''}';
      _plan.text = '${e['plan'] ?? ''}';
      _coverage.text = e['coverage_percent'] == null
          ? ''
          : '${e['coverage_percent']}';
      _limit.text = e['annual_limit'] == null ? '' : '${e['annual_limit']}';
      _patientId = e['patient'] as int?;
      _patientName = e['patient_name'] as String?;
      _hmoId = e['hmo'] as int?;
      _hmoName = e['hmo_name'] as String?;
      _from = DateTime.tryParse('${e['valid_from'] ?? ''}');
      _to = DateTime.tryParse('${e['valid_to'] ?? ''}');
      _active = e['is_active'] == true;
    }
  }

  @override
  void dispose() {
    _number.dispose();
    _plan.dispose();
    _coverage.dispose();
    _limit.dispose();
    super.dispose();
  }

  Future<void> _pickPatient() async {
    final row = await pickRow(
      context,
      path: '/api/patients/',
      title: 'Which patient?',
      hint: 'Name, hospital number or phone…',
      label: (r) => '${r['full_name']}',
      subtitle: (r) => '${r['hospital_number'] ?? ''} · ${r['phone'] ?? ''}',
    );
    if (row != null) {
      setState(() {
        _patientId = row['id'] as int?;
        _patientName = '${row['full_name']}';
      });
    }
  }

  Future<void> _pickHmo() async {
    final row = await pickRow(
      context,
      path: '/api/pharmacy/hmos/',
      title: 'Which insurer?',
      hint: 'Insurer name…',
      query: const {'is_active': 'true'},
      label: (r) => '${r['name']}',
      subtitle: (r) => 'pays ${r['coverage_percent']}% by default',
    );
    if (row != null) {
      setState(() {
        _hmoId = row['id'] as int?;
        _hmoName = '${row['name']}';
      });
    }
  }

  Future<void> _pickDate(bool isFrom) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: (isFrom ? _from : _to) ?? now,
      firstDate: DateTime(now.year - 5),
      lastDate: DateTime(now.year + 10),
    );
    if (picked != null) {
      setState(() => isFrom ? _from = picked : _to = picked);
    }
  }

  Future<void> _submit() async {
    if (_patientId == null || _hmoId == null) {
      setState(() => _error = 'Pick the patient and the insurer.');
      return;
    }
    if (_number.text.trim().isEmpty) {
      setState(() => _error = 'Enter the number on the card.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'patient': _patientId,
        'hmo': _hmoId,
        'member_number': _number.text.trim(),
        'plan': _plan.text.trim(),
        // Blank means "the scheme default applies" and "no cap" — null, not 0,
        // which would mean covered at nothing and capped at nothing.
        'coverage_percent':
            _coverage.text.trim().isEmpty ? null : _coverage.text.trim(),
        'annual_limit': _limit.text.trim().isEmpty ? null : _limit.text.trim(),
        'valid_from': _from?.toIso8601String().split('T').first,
        'valid_to': _to?.toIso8601String().split('T').first,
        'is_active': _active,
      };
      if (_isEdit) {
        await api.patch(
            '/api/pharmacy/enrollments/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pharmacy/enrollments/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _picker(String label, String? value, VoidCallback onTap) {
    return InputDecorator(
      decoration: InputDecoration(labelText: label),
      child: Row(children: [
        Expanded(
          child: Text(value ?? 'Not picked',
              style: TextStyle(
                  color: value == null ? context.hintColor : context.labelColor),
              overflow: TextOverflow.ellipsis),
        ),
        TextButton(
            onPressed: onTap, child: Text(value == null ? 'Pick' : 'Change')),
      ]),
    );
  }

  String _dateLabel(DateTime? d) =>
      d == null ? 'Any date' : d.toIso8601String().split('T').first;

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _isEdit ? 'Edit membership' : 'Enrol a patient',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Enrol',
      onSubmit: _submit,
      children: [
        _picker('Patient', _patientName, _pickPatient),
        const SizedBox(height: 12),
        _picker('Insurer', _hmoName, _pickHmo),
        const SizedBox(height: 12),
        TextField(
          controller: _number,
          decoration: const InputDecoration(labelText: 'Member number'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _plan,
          decoration: const InputDecoration(labelText: 'Plan (optional)'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _coverage,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Cover % for this member',
            helperText: "Blank uses the insurer's default",
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _limit,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Annual limit',
            helperText: 'Most this plan pays out in a calendar year. '
                'Blank is uncapped.',
          ),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: _picker('Valid from', _dateLabel(_from), () => _pickDate(true)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _picker('Valid to', _dateLabel(_to), () => _pickDate(false)),
          ),
        ]),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Active'),
          subtitle: const Text('A lapsed card cannot be billed'),
          value: _active,
          onChanged: (v) => setState(() => _active = v),
        ),
      ],
    );
  }
}

/* ------------------------------------------------------------ price list */

class _RulesTab extends StatelessWidget {
  final bool canEdit;
  final bool insurer;
  final int? myHmoId;
  const _RulesTab({required this.canEdit, required this.insurer, this.myHmoId});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pharmacy/item-rules/',
      searchHint: 'Drug or insurer…',
      fabLabel: 'Price a drug',
      showFab: canEdit,
      emptyIcon: Icons.rule_outlined,
      emptyTitle: 'Nothing priced yet',
      emptyMessage: canEdit
          ? "Every drug is covered at the scheme's default until a row says otherwise."
          : 'The scheme and the pharmacy admin keep what it pays per drug.',
      savedMessage: 'Price list saved.',
      card: (row, reload, edit) =>
          _RuleCard(row: row, canEdit: canEdit, edit: edit, reload: reload),
      form: (existing) =>
          _RuleForm(existing: existing, insurer: insurer, myHmoId: myHmoId),
    );
  }
}

class _RuleCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool canEdit;
  final VoidCallback edit;
  final VoidCallback reload;
  const _RuleCard(
      {required this.row,
      required this.canEdit,
      required this.edit,
      required this.reload});

  /// Dropping a row is not editing it: the drug goes back to the scheme's own
  /// default, which is a different cover from the one on screen. The
  /// confirmation says what it will be covered at afterwards rather than only
  /// that the row goes.
  Future<void> _drop(BuildContext context) async {
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Stop pricing ${row['item_name'] ?? 'this drug'}?'),
        content: Text(
            "It goes back to ${row['hmo_name']}'s scheme default. Sales "
            'already made keep what they were covered at.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Keep it')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Take it off')),
        ],
      ),
    );
    if (go != true || !context.mounted) return;
    try {
      await api.delete('/api/pharmacy/item-rules/${row['id']}/');
      if (!context.mounted) return;
      showSuccess(context, 'Off the price list.');
      reload();
    } catch (e) {
      if (context.mounted) showError(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final cover = num.tryParse('${row['coverage_percent'] ?? 0}') ?? 0;
    final tariff = num.tryParse('${row['tariff'] ?? ''}');
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Row(children: [
        Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${row['item_name'] ?? 'Drug'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
            Text('${row['hmo_name']} pays $cover%',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
            // The tariff is the other half of the row, and it only reads
            // against the shelf price: a pharmacy charging above it keeps the
            // sale, the excess simply stays with the patient.
            if (tariff != null)
              Text(
                  'up to ${money(tariff)} a unit'
                  '${row['item_price'] == null ? '' : ' · shelf ${money(row['item_price'])}'}',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
            if ('${row['note'] ?? ''}'.isNotEmpty)
              Text('${row['note']}',
                  style: TextStyle(color: context.hintColor, fontSize: 12)),
          ]),
        ),
        // 0% is the exclusion, and the one rule worth spotting from across the
        // list: the drug falls entirely to the patient even on a covered sale.
        if (cover == 0)
          const ReportBadge(text: 'excluded', color: EnhancedTheme.errorRed),
        if (canEdit) ...[
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
          IconButton(
              icon: const Icon(Icons.delete_outline, size: 18),
              onPressed: () => _drop(context)),
        ],
      ]),
    );
  }
}

class _RuleForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  // An insurer seat prices its own scheme and nobody else's, so the scheme is
  // not a question it is asked — and the drugs come from a catalogue it may
  // actually read.
  final bool insurer;
  final int? myHmoId;
  const _RuleForm({this.existing, this.insurer = false, this.myHmoId});

  @override
  State<_RuleForm> createState() => _RuleFormState();
}

class _RuleFormState extends State<_RuleForm> {
  final _coverage = TextEditingController(text: '0');
  final _tariff = TextEditingController();
  final _note = TextEditingController();
  int? _hmoId;
  String? _hmoName;
  int? _itemId;
  String? _itemName;
  // What the pharmacy charges for the picked drug, so a tariff is set against
  // a real price rather than from memory.
  Object? _shelfPrice;
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _coverage.text = '${e['coverage_percent'] ?? '0'}';
      _tariff.text = '${e['tariff'] ?? ''}';
      _note.text = '${e['note'] ?? ''}';
      _hmoId = e['hmo'] as int?;
      _hmoName = e['hmo_name'] as String?;
      _itemId = e['item'] as int?;
      _itemName = e['item_name'] as String?;
      _shelfPrice = e['item_price'];
    } else if (widget.insurer) {
      // The only scheme this seat may file under; the API refuses the rest.
      _hmoId = widget.myHmoId;
      _hmoName = 'My scheme';
    }
  }

  @override
  void dispose() {
    _coverage.dispose();
    _tariff.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _pickHmo() async {
    final row = await pickRow(
      context,
      path: '/api/pharmacy/hmos/',
      title: 'Which insurer?',
      hint: 'Insurer name…',
      query: const {'is_active': 'true'},
      label: (r) => '${r['name']}',
      subtitle: (r) => 'pays ${r['coverage_percent']}% by default',
    );
    if (row != null) {
      setState(() {
        _hmoId = row['id'] as int?;
        _hmoName = '${row['name']}';
      });
    }
  }

  /// The drugs a list can be written against.
  ///
  /// An insurer is not pharmacy staff and is refused /pharmacy/items/ — cost
  /// prices and margins are the pharmacy's own business — so it reads names
  /// and shelf prices off the price list's own catalogue instead.
  Future<void> _pickItem() async {
    final row = await pickRow(
      context,
      path: widget.insurer
          ? '/api/pharmacy/item-rules/items/'
          : '/api/pharmacy/items/',
      title: 'Which drug?',
      hint: 'Drug name…',
      label: (r) => '${r['name']}',
      subtitle: (r) => money(r['unit_price']),
    );
    if (row != null) {
      setState(() {
        _itemId = row['id'] as int?;
        _itemName = '${row['name']}';
        _shelfPrice = row['unit_price'];
      });
    }
  }

  Future<void> _submit() async {
    if (_hmoId == null || _itemId == null) {
      setState(() => _error = 'Pick the insurer and the drug.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final tariff = _tariff.text.trim();
      final body = {
        'hmo': _hmoId,
        'item': _itemId,
        'coverage_percent': _coverage.text.trim(),
        // Blank is no ceiling, and clears one that was set — so it travels as
        // null rather than being left out of an edit.
        'tariff': tariff.isEmpty ? null : tariff,
        'note': _note.text.trim(),
      };
      if (_isEdit) {
        await api.patch(
            '/api/pharmacy/item-rules/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pharmacy/item-rules/', body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _picker(String label, String? value, VoidCallback onTap) {
    return InputDecorator(
      decoration: InputDecoration(labelText: label),
      child: Row(children: [
        Expanded(
          child: Text(value ?? 'Not picked',
              style: TextStyle(
                  color: value == null ? context.hintColor : context.labelColor),
              overflow: TextOverflow.ellipsis),
        ),
        TextButton(
            onPressed: onTap, child: Text(value == null ? 'Pick' : 'Change')),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ReportFormSheet(
      title: _isEdit ? 'Edit what this pays' : 'Price a drug',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Add to the list',
      onSubmit: _submit,
      children: [
        // An insurer has one scheme to price, so it is told which rather than
        // asked — the picker would offer a list of one.
        if (!widget.insurer) ...[
          _picker('Insurer', _hmoName, _pickHmo),
          const SizedBox(height: 12),
        ],
        _picker('Drug', _itemName, _pickItem),
        const SizedBox(height: 12),
        TextField(
          controller: _coverage,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Cover %',
            helperText: '0 excludes the drug — the patient pays all of it',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _tariff,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: 'Tariff (optional)',
            helperText: 'Most the scheme pays for one unit, whatever the '
                'pharmacy charges. Blank covers the shelf price.'
                '${_shelfPrice == null ? '' : ' Charged today: ${money(_shelfPrice)}.'}',
            helperMaxLines: 3,
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _note,
          decoration: const InputDecoration(labelText: 'Note (optional)'),
        ),
      ],
    );
  }
}
