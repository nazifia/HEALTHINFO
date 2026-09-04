import 'dart:async';

import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/empty_state.dart';
import '../shared/widgets/snack.dart';
import 'report_scaffold.dart';

/// Shared pieces the pharmacy screens all need: firing a state transition,
/// drawing the buttons that fire one, and pointing at a row the API already
/// lists. Kept beside [ReportListScreen] rather than inside it — a list screen
/// is about loading rows, and these are about acting on one.

/// POST a row action, show whatever the API said, then refresh.
///
/// Every pharmacy action endpoint answers with the same `{message, data}`
/// envelope (config/responses.py), so the button that fires one never has to
/// invent its own wording — and a refused transition shows the server's own
/// reason instead of a generic failure.
Future<bool> runAction(
  BuildContext context,
  String path, {
  Object? body,
  Future<void> Function()? after,
}) async {
  try {
    final r = await api.post(path, body);
    if (!context.mounted) return true;
    showSuccess(context, '${(r as Map?)?['message'] ?? 'Done.'}');
    if (after != null) await after();
    return true;
  } catch (e) {
    if (context.mounted) showError(context, '$e');
    return false;
  }
}

/// The row of buttons a card offers for its state transitions.
///
/// Labels are the API's own action names, so the list a screen shows and the
/// URL it posts to can never drift apart.
class ActionRow extends StatelessWidget {
  final List<String> actions;
  final void Function(String action) onAction;
  const ActionRow({super.key, required this.actions, required this.onAction});

  static const _icons = {
    'submit': Icons.send_outlined,
    'approve': Icons.check_circle_outline,
    'reject': Icons.cancel_outlined,
    'cancel': Icons.close,
    'pay': Icons.payments_outlined,
    'pay-all': Icons.account_balance_wallet_outlined,
    'receive': Icons.inventory_outlined,
    'dispense': Icons.medication_outlined,
    'count': Icons.checklist_outlined,
    'complete': Icons.done_all,
    'accept': Icons.how_to_reg_outlined,
    'top-up': Icons.add_card_outlined,
    'deduct': Icons.remove_circle_outline,
  };

  static const _destructive = {'reject', 'cancel', 'deduct'};

  static String label(String action) {
    final words = action.replaceAll('-', ' ');
    return words[0].toUpperCase() + words.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    if (actions.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Wrap(
        spacing: 4,
        runSpacing: 0,
        children: [
          for (final a in actions)
            TextButton.icon(
              onPressed: () => onAction(a),
              style: TextButton.styleFrom(
                visualDensity: VisualDensity.compact,
                padding: const EdgeInsets.symmetric(horizontal: 10),
                foregroundColor: _destructive.contains(a)
                    ? EnhancedTheme.errorRed
                    : EnhancedTheme.primaryTeal,
              ),
              icon: Icon(_icons[a] ?? Icons.play_arrow, size: 16),
              label: Text(label(a), style: const TextStyle(fontSize: 13)),
            ),
        ],
      ),
    );
  }
}

/// Two labelled figures side by side inside a card.
class FactRow extends StatelessWidget {
  final String label;
  final String value;
  final bool bold;
  const FactRow(this.label, this.value, {super.key, this.bold = false});

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
        color: bold ? context.labelColor : context.hintColor,
        fontSize: bold ? 15 : 13,
        fontWeight: bold ? FontWeight.w700 : FontWeight.w500);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: style),
        Flexible(
            child: Text(value,
                style: style,
                textAlign: TextAlign.right,
                overflow: TextOverflow.ellipsis)),
      ]),
    );
  }
}

/// Colour for a status pill. One mapping for every workflow in the module, so
/// "approved" is the same green whether it is a claim, a transfer or a count.
Color statusColor(Object? status) {
  switch ('$status') {
    case 'paid':
    case 'approved':
    case 'received':
    case 'completed':
    case 'dispensed':
    case 'accepted':
      return EnhancedTheme.successGreen;
    case 'rejected':
    case 'cancelled':
    case 'out_of_stock':
    case 'critical':
      return EnhancedTheme.errorRed;
    case 'pending':
    case 'partial':
    case 'in_progress':
    case 'submitted':
      return EnhancedTheme.accentOrange;
    default:
      return EnhancedTheme.accentCyan;
  }
}

/// Pick one row from any searchable list endpoint.
///
/// Generalises the patient picker: the pharmacy screens all need to point at
/// something the API already lists — an item, a prescriber, a customer, an
/// expense category — and none of them needs its own search sheet.
/// Returns the chosen row, or null if the sheet was dismissed.
Future<Map<String, dynamic>?> pickRow(
  BuildContext context, {
  required String path,
  required String title,
  required String Function(Map<String, dynamic> row) label,
  String Function(Map<String, dynamic> row)? subtitle,
  Map<String, String>? query,
  String hint = 'Search…',
}) {
  return showModalBottomSheet<Map<String, dynamic>>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _RemotePickerSheet(
      path: path,
      title: title,
      label: label,
      subtitle: subtitle,
      query: query,
      hint: hint,
    ),
  );
}

class _RemotePickerSheet extends StatefulWidget {
  final String path;
  final String title;
  final String hint;
  final Map<String, String>? query;
  final String Function(Map<String, dynamic> row) label;
  final String Function(Map<String, dynamic> row)? subtitle;

  const _RemotePickerSheet({
    required this.path,
    required this.title,
    required this.label,
    required this.hint,
    this.subtitle,
    this.query,
  });

  @override
  State<_RemotePickerSheet> createState() => _RemotePickerSheetState();
}

class _RemotePickerSheetState extends State<_RemotePickerSheet> {
  late Future<List<dynamic>> _future = api.getList(widget.path, widget.query);
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  // ponytail: same 350ms debounce as the report lists, same caveat — a slow
  // earlier response can still land last.
  void _search(String value) {
    final q = value.trim();
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      setState(() =>
          _future = api.getList(widget.path, listQuery(q, {...?widget.query})));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        height: MediaQuery.of(context).size.height * 0.7,
        decoration: BoxDecoration(
          color: context.scaffoldBg,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(children: [
          Text(widget.title,
              style: TextStyle(
                  color: context.labelColor,
                  fontSize: 18,
                  fontWeight: FontWeight.w800)),
          const SizedBox(height: 12),
          TextField(
            autofocus: true,
            onChanged: _search,
            decoration: InputDecoration(
              hintText: widget.hint,
              prefixIcon: const Icon(Icons.search, size: 20),
              isDense: true,
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: FutureBuilder<List<dynamic>>(
              future: _future,
              builder: (context, snap) {
                if (snap.connectionState == ConnectionState.waiting) {
                  return const Center(
                      child: CircularProgressIndicator(
                          color: EnhancedTheme.primaryTeal));
                }
                if (snap.hasError) {
                  return EmptyState(
                    icon: Icons.error_outline,
                    title: 'Could not load',
                    message: '${snap.error}',
                    color: EnhancedTheme.errorRed,
                  );
                }
                final rows = (snap.data ?? []).cast<Map<String, dynamic>>();
                if (rows.isEmpty) {
                  return const EmptyState(
                    icon: Icons.search_off,
                    title: 'Nothing found',
                    message: 'Try another search.',
                  );
                }
                return ListView.builder(
                  itemCount: rows.length,
                  itemBuilder: (context, i) {
                    final r = rows[i];
                    final sub = widget.subtitle?.call(r) ?? '';
                    return ListTile(
                      dense: true,
                      title: Text(widget.label(r),
                          style: TextStyle(color: context.labelColor)),
                      subtitle: sub.isEmpty
                          ? null
                          : Text(sub,
                              style: TextStyle(
                                  color: context.hintColor, fontSize: 12)),
                      onTap: () => Navigator.of(context).pop(r),
                    );
                  },
                );
              },
            ),
          ),
        ]),
      ),
    );
  }
}
