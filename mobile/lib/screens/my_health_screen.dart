import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../main.dart';
import '../api.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';

/// A patient's own record — GET /api/portal/*.
///
/// Their details, the drugs the pharmacy has actually handed over, and where
/// to go and get more. Nothing else: the clinical timeline is the facility's
/// working record and the portal API does not serve it.
///
/// No patient id is sent anywhere: the API reads it off the signed-in account
/// (apps.patients.portal), so this screen cannot show anyone else's record. An
/// account nobody has linked to a patient row gets 403, and the message says
/// who can fix that.
class MyHealthScreen extends StatefulWidget {
  const MyHealthScreen({super.key});

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

  Future<List<dynamic>> _load() =>
      Future.wait([api.portalMe(), api.portalMedications()]);

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
            return ListView(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
              children: [
                _DetailsCard(me: me),
                const SizedBox(height: 12),
                _MedicationsCard(
                  meds: meds,
                  onFind: (medication) => _findPharmacies(medication: medication),
                ),
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

class _DetailsCard extends StatelessWidget {
  final Map<String, dynamic> me;
  const _DetailsCard({required this.me});

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
