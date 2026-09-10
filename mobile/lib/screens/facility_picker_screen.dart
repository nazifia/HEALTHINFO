import 'package:flutter/material.dart';

import '../main.dart';
import '../config.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/skeleton_cards.dart';
import '../shared/widgets/snack.dart';

/// Where an independent prescriber is writing.
///
/// Their licence covers a state; a prescription belongs to one facility inside
/// it. The list comes from /api/tenants/prescribing/ and so does the fence:
/// picking here only sets the X-Tenant-ID header every later call carries, and
/// the server checks the state on their row again on every write.
class FacilityPickerScreen extends StatefulWidget {
  const FacilityPickerScreen({super.key});

  @override
  State<FacilityPickerScreen> createState() => _FacilityPickerScreenState();
}

class _FacilityPickerScreenState extends State<FacilityPickerScreen> {
  late Future<List<dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = api.prescribingFacilities();
    // The list is one state's facilities: re-read it when the seat changes
    // what it is working as, the same way every other scoped screen does.
    tenantChanged.addListener(_onTenantChanged);
  }

  @override
  void dispose() {
    tenantChanged.removeListener(_onTenantChanged);
    super.dispose();
  }

  void _onTenantChanged() {
    if (mounted) setState(() {});
  }

  void _reload() =>
      setState(() => _future = api.prescribingFacilities());

  Future<void> _pick(Map<String, dynamic> t) async {
    await setTenant('${t['slug']}', name: '${t['name']}');
    // The cached row carries the seat's tenant and its idle timeout; both are
    // the facility's now.
    api.forgetMe();
    if (!mounted) return;
    showSuccess(context, 'Prescribing under ${t['name']}.');
  }

  Future<void> _clear() async {
    await setTenant('');
    api.forgetMe();
    if (!mounted) return;
    showSuccess(context, 'Pick a facility before writing.');
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        _reload();
        await _future;
      },
      child: FutureBuilder<List<dynamic>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const SkeletonCards(cards: 4);
          }
          if (snap.hasError) {
            return ListView(children: [
              const SizedBox(height: 80),
              EmptyState(
                icon: Icons.error_outline,
                title: 'Could not load your facilities',
                message: '${snap.error}',
                color: EnhancedTheme.errorRed,
              ),
            ]);
          }
          final rows = snap.data!.cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
            children: [
              const _Explainer(),
              if (tenantSlug.isNotEmpty)
                GlassCard(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(16),
                  child: Row(children: [
                    const Icon(Icons.check_circle_outline, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                        child: Text('Writing under $tenantLabel',
                            style: const TextStyle(fontWeight: FontWeight.w600))),
                    TextButton(onPressed: _clear, child: const Text('Clear')),
                  ]),
                ),
              if (rows.isEmpty)
                const EmptyState(
                  icon: Icons.apartment_outlined,
                  title: 'No facility open to you yet',
                  message: 'Ask the platform admin to check the state on your '
                      'account, and that the facility you work with has been '
                      'approved.',
                  boxed: true,
                )
              else
                for (final t in rows)
                  GlassCard(
                    margin: const EdgeInsets.only(bottom: 10),
                    padding: const EdgeInsets.all(4),
                    onTap: () => _pick(t),
                    child: ListTile(
                      leading: Icon(t['kind'] == 'pharmacy'
                          ? Icons.local_pharmacy_outlined
                          : Icons.local_hospital_outlined),
                      title: Text('${t['name']}'),
                      subtitle: Text('${t['kind']}'),
                      trailing: '${t['slug']}' == tenantSlug
                          ? const Icon(Icons.check, size: 20)
                          : const Icon(Icons.chevron_right, size: 20),
                      onTap: () => _pick(t),
                    ),
                  ),
            ],
          );
        },
      ),
    );
  }
}

class _Explainer extends StatelessWidget {
  const _Explainer();

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Text(
          'Your licence covers the whole state, but a prescription belongs to '
          'one facility. Pick the one you are working in — you can change it '
          'at any time.',
          style: TextStyle(color: context.subLabelColor),
        ),
      );
}
