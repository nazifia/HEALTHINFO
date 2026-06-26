import 'package:flutter/material.dart';

import '../api.dart';
import '../main.dart';
import '../resources.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/snack.dart';

/// One editable text field derived from a [CatalogResource].
class _Field {
  final String key;
  final String label;
  final bool multiline;
  final TextEditingController ctrl;
  _Field(this.key, this.label, this.multiline, String? initial)
      : ctrl = TextEditingController(text: initial ?? '');
}

String _pretty(String key) => key
    .split('_')
    .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
    .join(' ');

/// Generic edit form for any catalog resource. Edits the plain text fields
/// (title, subtitle, section bodies); PATCHes only what changed.
/// ponytail: skips M2M links and workflow `status` — those have their own flows
/// (relationship view + transition action). Add them here only if asked.
class CatalogEditScreen extends StatefulWidget {
  final CatalogResource resource;
  final Map<String, dynamic> row;
  const CatalogEditScreen({
    super.key,
    required this.resource,
    required this.row,
  });

  @override
  State<CatalogEditScreen> createState() => _CatalogEditScreenState();
}

class _CatalogEditScreenState extends State<CatalogEditScreen> {
  late final List<_Field> _fields;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final r = widget.resource;
    final seen = <String>{};
    String? init(String k) => widget.row[k]?.toString();
    _fields = [
      _Field(r.titleField, _pretty(r.titleField), false, init(r.titleField)),
    ];
    seen.add(r.titleField);
    if (r.subtitleField != null && seen.add(r.subtitleField!)) {
      _fields.add(_Field(r.subtitleField!, r.subtitleLabel ?? _pretty(r.subtitleField!),
          false, init(r.subtitleField!)));
    }
    for (final s in r.sections) {
      if (seen.add(s.key)) {
        _fields.add(_Field(s.key, s.heading, true, init(s.key)));
      }
    }
  }

  @override
  void dispose() {
    for (final f in _fields) {
      f.ctrl.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    // Send only changed fields so we never overwrite something we don't show.
    final body = <String, dynamic>{};
    for (final f in _fields) {
      final v = f.ctrl.text;
      if (v != (widget.row[f.key]?.toString() ?? '')) body[f.key] = v;
    }
    if (body.isEmpty) {
      Navigator.of(context).pop();
      return;
    }
    setState(() => _saving = true);
    try {
      final id = widget.row['id'];
      final updated =
          await api.patch('${widget.resource.path}$id/', body) as Map;
      if (!mounted) return;
      Navigator.of(context).pop(updated.cast<String, dynamic>());
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showError(context, e.friendly);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.scaffoldBg,
      appBar: AppBar(
        title: Text('Edit ${widget.resource.label}'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 18),
              child: Center(
                child: SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.white),
                ),
              ),
            )
          else
            IconButton(
              icon: const Icon(Icons.check),
              tooltip: 'Save',
              onPressed: _save,
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          for (final f in _fields)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextField(
                controller: f.ctrl,
                minLines: f.multiline ? 3 : 1,
                maxLines: f.multiline ? 12 : 1,
                textInputAction:
                    f.multiline ? TextInputAction.newline : TextInputAction.next,
                decoration: InputDecoration(
                  labelText: f.label,
                  border: const OutlineInputBorder(),
                  focusedBorder: const OutlineInputBorder(
                    borderSide: BorderSide(color: EnhancedTheme.primaryTeal),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
