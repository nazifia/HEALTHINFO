import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../main.dart';
import '../api.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/hero_banner.dart';
import '../shared/widgets/snack.dart';

/// A patient's home — GET /api/portal/*.
///
/// A welcome banner with the facts a nurse asks for first, the drugs the
/// pharmacy has actually handed over, and where to go and get more. The full
/// record lives on Profile ([PatientDetailsCard]). Nothing else: the clinical
/// timeline is the facility's working record and the portal API does not
/// serve it.
///
/// No patient id is sent anywhere: the API reads it off the signed-in account
/// (apps.patients.portal), so this screen cannot show anyone else's record. An
/// account nobody has linked to a patient row gets 403, and the message says
/// who can fix that.
class MyHealthScreen extends StatefulWidget {
  /// Opens the Profile drawer section — the banner's "View full profile".
  final VoidCallback? onOpenProfile;
  const MyHealthScreen({super.key, this.onOpenProfile});

  @override
  State<MyHealthScreen> createState() => _MyHealthScreenState();
}

/// The device's position, or null when the patient refuses it, location is
/// switched off, or no fix arrives in time. Never throws: the pharmacy list
/// still answers without one, it just isn't sorted by distance.
Future<Position?> myPosition() async {
  try {
    if (!await Geolocator.isLocationServiceEnabled()) return null;
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return null;
    }
    return await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(timeLimit: Duration(seconds: 8)),
    );
  } catch (_) {
    return null;
  }
}

// What a patient is shown about themselves, in the order they read it. Not
// the whole row: the staff notes and the registry bookkeeping are the
// facility's working record, not the card the patient came for.
const _details = <String, String>{
  'hospital_number': 'Hospital number',
  'full_name': 'Name',
  'sex': 'Sex',
  'age': 'Age',
  'date_of_birth': 'Date of birth',
  'phone': 'Phone',
  'address': 'Address',
  'blood_group': 'Blood group',
  'genotype': 'Genotype',
  'allergies': 'Allergies',
  'patient_type_display': 'Payment route',
  'nhis_number': 'NHIS number',
  'next_of_kin_name': 'Next of kin',
  'next_of_kin_phone': 'Next of kin phone',
};

String _text(Object? v) {
  if (v == null) return '—';
  if (v is List) return v.isEmpty ? '—' : v.join(', ');
  final s = '$v'.trim();
  return s.isEmpty ? '—' : s;
}

class _MyHealthScreenState extends State<MyHealthScreen>
    with AutomaticKeepAliveClientMixin {
  late Future<List<dynamic>> _future;

  // The pharmacy list is loaded on demand, not with the page: it asks for the
  // device's location, and a patient reading their prescriptions has not
  // asked to be located yet.
  List<Map<String, dynamic>>? _pharmacies;
  bool _findingPharmacies = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  // The scheme calls fail soft: a patient on no scheme still has a record
  // and a drug list, and the dependents card says why it is empty.
  Future<List<dynamic>> _load() => Future.wait([
        api.portalMe(),
        api.portalMedications(),
        api.portalEnrollments().catchError((_) => <dynamic>[]),
        api.portalDependents().catchError((_) => <dynamic>[]),
      ]);

  void _reload() => setState(() {
        _pharmacies = null;
        _future = _load();
      });

  /// Load the nearby pharmacies, optionally only those holding one drug.
  Future<void> _findPharmacies({Object? medication}) async {
    setState(() => _findingPharmacies = true);
    final position = await myPosition();
    if (!mounted) return;
    if (position == null) {
      showError(context, 'Location is off — pharmacies are listed unsorted.');
    }
    try {
      final rows = await api.portalPharmacies(
        lat: position?.latitude,
        lng: position?.longitude,
        medication: medication,
      );
      if (!mounted) return;
      setState(() => _pharmacies = rows.cast<Map<String, dynamic>>());
    } on ApiException catch (e) {
      if (mounted) showError(context, e.friendly);
    } finally {
      if (mounted) setState(() => _findingPharmacies = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
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
                  child: CircularProgressIndicator(
                      color: EnhancedTheme.primaryTeal));
            }
            if (snap.hasError) {
              final error = snap.error;
              return ListView(children: [
                const SizedBox(height: 80),
                EmptyState(
                  icon: Icons.badge_outlined,
                  title: 'Your record is not linked yet',
                  message: error is ApiException ? error.friendly : '$error',
                  color: EnhancedTheme.errorRed,
                ),
              ]);
            }
            final me = (snap.data![0] as Map).cast<String, dynamic>();
            final meds = (snap.data![1] as List).cast<Map<String, dynamic>>();
            final cards = (snap.data![2] as List).cast<Map<String, dynamic>>();
            final deps = (snap.data![3] as List).cast<Map<String, dynamic>>();
            return ListView(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
              children: [
                _HeroCard(me: me, meds: meds, onOpenProfile: widget.onOpenProfile),
                const SizedBox(height: 12),
                _MedicationsCard(
                  meds: meds,
                  onFind: (medication) => _findPharmacies(medication: medication),
                ),
                const SizedBox(height: 12),
                _DependentsCard(cards: cards, rows: deps, onAdded: _reload),
                const SizedBox(height: 12),
                _PharmaciesCard(
                  rows: _pharmacies,
                  busy: _findingPharmacies,
                  onFind: _findPharmacies,
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// The patient's banner: the handful of facts a nurse asks for first. The
/// full record lives on Profile.
class _HeroCard extends StatelessWidget {
  final Map<String, dynamic> me;
  final List<Map<String, dynamic>> meds;
  final VoidCallback? onOpenProfile;
  const _HeroCard({required this.me, required this.meds, this.onOpenProfile});

  @override
  Widget build(BuildContext context) {
    final name = _text(me['full_name']) == '—' ? 'there' : _text(me['full_name']);
    final sex = me['sex'] == 'M'
        ? 'Male'
        : me['sex'] == 'F'
            ? 'Female'
            : _text(me['sex']);
    final who = [
      sex,
      if (me['age'] != null) '${me['age']} yrs',
      if (_text(me['hospital_number']) != '—')
        'Hospital No. ${me['hospital_number']}',
    ].where((s) => s != '—').join(' · ');
    return HeroBanner(
      name: name,
      subtitle: who,
      stats: [
        MapEntry('Blood group', me['blood_group']),
        MapEntry('Genotype', me['genotype']),
        MapEntry('Scheme', me['patient_type_display']),
        MapEntry('NHIS number', me['nhis_number']),
        MapEntry('Medications collected', meds.length),
        MapEntry('Allergies', me['allergies']),
      ],
      action: onOpenProfile == null
          ? null
          : OutlinedButton.icon(
              onPressed: onOpenProfile,
              style: HeroBanner.actionStyle,
              icon: const Icon(Icons.person_outline, size: 18),
              label: const Text('View full profile'),
            ),
    );
  }
}

/// A patient's full record, as the portal serves it. Shown on Profile above
/// the account row; the home banner keeps only the headline facts.
class PatientDetailsCard extends StatelessWidget {
  final Map<String, dynamic> me;
  const PatientDetailsCard({super.key, required this.me});

  @override
  Widget build(BuildContext context) {
    final conditions = me['chronic_condition_names'];
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('My details', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final entry in _details.entries)
            if (me.containsKey(entry.key))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                        width: 140,
                        child: Text(entry.value,
                            style: const TextStyle(color: Colors.grey))),
                    Expanded(child: Text(_text(me[entry.key]))),
                  ],
                ),
              ),
          if (conditions is List && conditions.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              children: [
                for (final c in conditions) Chip(label: Text('$c')),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _MedicationsCard extends StatelessWidget {
  final List<Map<String, dynamic>> meds;
  final ValueChanged<Object?> onFind;
  const _MedicationsCard({required this.meds, required this.onFind});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('My medications', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          // Dispensed drugs only reach this list, so empty means nothing has
          // been collected, not that nothing was written.
          if (meds.isEmpty)
            const Text('You have not collected any medication yet.',
                style: TextStyle(color: Colors.grey))
          else
            for (final m in meds)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.medication_outlined,
                    color: EnhancedTheme.primaryTeal),
                title: Text(_text(m['medication_name'])),
                subtitle: Text([
                  _text(m['dose']),
                  _text(m['frequency']),
                  if (m['duration_days'] != null) '${m['duration_days']} days',
                  _text(m['status']).replaceAll('_', ' '),
                ].where((s) => s != '—').join(' · ')),
                trailing: TextButton(
                  onPressed: () => onFind(m['medication']),
                  child: const Text('Where to get it'),
                ),
              ),
        ],
      ),
    );
  }
}

/// The people on the principal's card. A dependent is named here and waits
/// on the scheme; its answer shows as the status, and can change later. A
/// patient on no scheme has nobody to ask, so the button stays hidden.
class _DependentsCard extends StatelessWidget {
  final List<Map<String, dynamic>> cards;
  final List<Map<String, dynamic>> rows;
  final VoidCallback onAdded;
  const _DependentsCard(
      {required this.cards, required this.rows, required this.onAdded});

  Color _statusColor(String status) => switch (status) {
        'approved' => EnhancedTheme.successGreen,
        'declined' => EnhancedTheme.errorRed,
        _ => EnhancedTheme.warningAmber,
      };

  Future<void> _add(BuildContext context) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _DependentForm(cards: cards),
    );
    if (saved == true) onAdded();
  }

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('My dependents', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          if (rows.isEmpty)
            const Text('Nobody added yet.',
                style: TextStyle(color: Colors.grey))
          else
            for (final r in rows)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.family_restroom_outlined,
                    color: EnhancedTheme.primaryTeal),
                title: Text(_text(r['full_name'])),
                subtitle: Text([
                  _text(r['relationship']),
                  _text(r['hmo_name']),
                  if (r['status'] == 'approved' && _text(r['member_number']) != '—')
                    'No. ${r['member_number']}',
                  if (r['status'] == 'declined' && _text(r['reason']) != '—')
                    '${r['reason']}',
                ].where((s) => s != '—').join(' · ')),
                trailing: Chip(
                  label: Text('${r['status']}',
                      style: const TextStyle(color: Colors.white, fontSize: 12)),
                  backgroundColor: _statusColor('${r['status']}'),
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                ),
              ),
          const SizedBox(height: 8),
          if (cards.isEmpty)
            const Text('You are not on a scheme yet, so there is nobody to ask.',
                style: TextStyle(color: Colors.grey))
          else
            FilledButton.icon(
              onPressed: () => _add(context),
              icon: const Icon(Icons.person_add_alt_outlined),
              label: const Text('Add a dependent'),
            ),
        ],
      ),
    );
  }
}

/// Names one dependent. Pops `true` once the scheme has it.
class _DependentForm extends StatefulWidget {
  final List<Map<String, dynamic>> cards;
  const _DependentForm({required this.cards});

  @override
  State<_DependentForm> createState() => _DependentFormState();
}

class _DependentFormState extends State<_DependentForm> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  String _relationship = 'child';
  String? _sex;
  DateTime? _dob;
  int? _enrollment;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    if (widget.cards.length == 1) _enrollment = widget.cards.first['id'] as int?;
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) return showError(context, 'Give their full name.');
    if (_enrollment == null) {
      return showError(context, 'Pick which membership this goes under.');
    }
    setState(() => _saving = true);
    try {
      await api.addDependent({
        'enrollment': _enrollment,
        'full_name': name,
        'relationship': _relationship,
        if (_sex != null) 'sex': _sex,
        if (_dob != null) 'date_of_birth': _dob!.toIso8601String().substring(0, 10),
        if (_phone.text.trim().isNotEmpty) 'phone': _phone.text.trim(),
      });
      if (!mounted) return;
      showSuccess(context, 'Sent to the scheme for approval.');
      Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) showError(context, e.friendly);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
          16, 16, 16, MediaQuery.of(context).viewInsets.bottom + 16),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Add a dependent',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            if (widget.cards.length > 1)
              DropdownButtonFormField<int>(
                initialValue: _enrollment,
                decoration:
                    const InputDecoration(labelText: 'Under which membership'),
                items: [
                  for (final c in widget.cards)
                    DropdownMenuItem(
                        value: c['id'] as int,
                        child: Text('${c['hmo_name']} · ${c['member_number']}')),
                ],
                onChanged: (v) => setState(() => _enrollment = v),
              ),
            TextField(
              controller: _name,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(labelText: 'Full name'),
            ),
            DropdownButtonFormField<String>(
              initialValue: _relationship,
              decoration: const InputDecoration(labelText: 'Relationship'),
              items: const [
                DropdownMenuItem(value: 'child', child: Text('Child')),
                DropdownMenuItem(value: 'spouse', child: Text('Spouse')),
                DropdownMenuItem(value: 'parent', child: Text('Parent')),
                DropdownMenuItem(value: 'other', child: Text('Other')),
              ],
              onChanged: (v) => setState(() => _relationship = v ?? 'child'),
            ),
            DropdownButtonFormField<String?>(
              initialValue: _sex,
              decoration: const InputDecoration(labelText: 'Sex'),
              items: const [
                DropdownMenuItem(value: null, child: Text('—')),
                DropdownMenuItem(value: 'M', child: Text('Male')),
                DropdownMenuItem(value: 'F', child: Text('Female')),
              ],
              onChanged: (v) => setState(() => _sex = v),
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.cake_outlined),
              title: Text(_dob == null
                  ? 'Date of birth'
                  : _dob!.toIso8601String().substring(0, 10)),
              onTap: () async {
                final now = DateTime.now();
                final picked = await showDatePicker(
                  context: context,
                  initialDate: _dob ?? now,
                  firstDate: DateTime(now.year - 120),
                  lastDate: now,
                );
                if (picked != null) setState(() => _dob = picked);
              },
            ),
            TextField(
              controller: _phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Phone (optional)'),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? 'Sending…' : 'Send for approval'),
            ),
          ],
        ),
      ),
    );
  }
}

class _PharmaciesCard extends StatelessWidget {
  final List<Map<String, dynamic>>? rows;
  final bool busy;
  final VoidCallback onFind;
  const _PharmaciesCard(
      {required this.rows, required this.busy, required this.onFind});

  @override
  Widget build(BuildContext context) {
    final found = rows;
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Where to get them',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: busy ? null : onFind,
            icon: const Icon(Icons.my_location),
            label: Text(busy ? 'Looking…' : 'Find pharmacies near me'),
          ),
          if (found != null) ...[
            const SizedBox(height: 8),
            if (found.isEmpty)
              const Text('No pharmacy listed for that. Try the full list.',
                  style: TextStyle(color: Colors.grey))
            else
              for (final p in found)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.local_pharmacy_outlined,
                      color: EnhancedTheme.accentCyan),
                  title: Text(_text(p['pharmacy'])),
                  subtitle: Text([
                    _text(p['name']),
                    _text(p['address']),
                    _text(p['phone']),
                  ].where((s) => s != '—').join(' · ')),
                  // ponytail: distance only. Opening a maps app needs a
                  // url_launcher dependency — add it when someone asks to
                  // navigate rather than to phone ahead.
                  trailing: Text(p['distance_km'] == null
                      ? '—'
                      : '${p['distance_km']} km'),
                ),
          ],
        ],
      ),
    );
  }
}
