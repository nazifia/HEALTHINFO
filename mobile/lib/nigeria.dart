import 'package:flutter/material.dart';

import 'main.dart';
import 'nigeria_data.dart';
import 'shared/widgets/searchable_dropdown.dart';
import 'shared/widgets/snack.dart';

// The state -> LGA list is generated from the server's own INEC list; see
// scripts/gen_nigeria.py. Re-exported so the screens keep importing one file.
export 'nigeria_data.dart' show nigeriaStates;

/// Tappable chip showing a report's region; opens a picker sheet and PATCHes
/// the new "LGA, State" to `path`. Calls `onSaved` to let the list reload.
class RegionEditChip extends StatelessWidget {
  final String path; // e.g. /api/case-reports/12/
  final String current;
  final VoidCallback onSaved;
  const RegionEditChip({
    super.key,
    required this.path,
    required this.current,
    required this.onSaved,
  });

  Future<void> _edit(BuildContext context) async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _RegionSheet(),
    );
    if (picked == null) return;
    try {
      await api.patch(path, {'region': picked});
      onSaved();
      if (context.mounted) showSuccess(context, 'Region updated.');
    } catch (e) {
      if (context.mounted) showError(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      avatar: const Icon(Icons.edit_location_alt_outlined, size: 16),
      label: Text(current.isEmpty ? 'Set region' : current),
      onPressed: () => _edit(context),
    );
  }
}

class _RegionSheet extends StatefulWidget {
  const _RegionSheet();
  @override
  State<_RegionSheet> createState() => _RegionSheetState();
}

class _RegionSheetState extends State<_RegionSheet> {
  String _region = '';

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 16, 20, 24 + inset),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Edit region',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 16),
          RegionPicker(onChanged: (r) => _region = r),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _region.isEmpty
                  ? null
                  : () => Navigator.of(context).pop(_region),
              child: const Text('Save'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Cascading State → LGA picker. Reports `region` as "LGA, State" (or "" until
/// both are chosen). Drop into any report form.
class RegionPicker extends StatefulWidget {
  final ValueChanged<String> onChanged;
  final String? initial; // "LGA, State" to preselect (edit flow)
  const RegionPicker({super.key, required this.onChanged, this.initial});

  @override
  State<RegionPicker> createState() => _RegionPickerState();
}

class _RegionPickerState extends State<RegionPicker> {
  String? _state;
  String? _lga;

  @override
  void initState() {
    super.initState();
    // Parse "LGA, State" back into the two dropdowns; ignore if it's not a
    // known pair (e.g. legacy free-text region).
    final parts = widget.initial?.split(', ');
    if (parts != null && parts.length == 2 && nigeriaStates[parts[1]] != null) {
      _state = parts[1];
      if (nigeriaStates[_state]!.contains(parts[0])) _lga = parts[0];
    }
  }

  void _emit() {
    final ok = _state != null && _lga != null;
    widget.onChanged(ok ? '$_lga, $_state' : '');
  }

  @override
  Widget build(BuildContext context) {
    final lgas = _state == null ? const <String>[] : nigeriaStates[_state]!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SearchableDropdown<String>(
          initialValue: _state,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'State'),
          items: [
            for (final s in nigeriaStates.keys)
              DropdownMenuItem(value: s, child: Text(s)),
          ],
          onChanged: (v) => setState(() {
            _state = v;
            _lga = null;
            _emit();
          }),
        ),
        const SizedBox(height: 12),
        SearchableDropdown<String>(
          initialValue: _lga,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'LGA'),
          items: [
            for (final l in lgas) DropdownMenuItem(value: l, child: Text(l)),
          ],
          onChanged: lgas.isEmpty
              ? null
              : (v) => setState(() {
                    _lga = v;
                    _emit();
                  }),
        ),
      ],
    );
  }
}
