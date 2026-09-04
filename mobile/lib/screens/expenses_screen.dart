import 'package:flutter/material.dart';

import '../main.dart';
import '../pharmacy.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/stats_kit.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Expenses — GET /api/pos/expenses/.
///
/// Money out that bought no stock. A cash expense is booked against whatever
/// drawer is open, so the till still counts correctly at close — which is why
/// the source matters more here than the amount does.
class ExpensesScreen extends StatelessWidget {
  const ExpensesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<String?>(
      future: api.myRole(),
      builder: (context, snap) {
        final role = snap.data;
        return ReportListScreen(
          path: '/api/pos/expenses/',
          searchHint: 'Search expenses…',
          fabLabel: 'Record expense',
          showFab: isPharmacyStaff(role),
          emptyIcon: Icons.receipt_outlined,
          emptyTitle: 'Nothing spent yet',
          emptyMessage: 'Record what the shop pays out that is not stock.',
          savedMessage: 'Expense recorded.',
          filters: const [
            ReportFilter(
                param: 'payment_source',
                anyLabel: 'Any source',
                options: {
                  'cash': 'Out of the drawer',
                  'other': 'Bank / card / transfer',
                }),
          ],
          header: (items) => _Header(items: items),
          card: (row, reload, edit) => _ExpenseCard(row: row, edit: edit),
          form: (existing) => _ExpenseForm(existing: existing),
        );
      },
    );
  }
}

class _Header extends StatelessWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  Widget build(BuildContext context) {
    num sum(bool cash) => items
        .where((r) => (r['payment_source'] == 'cash') == cash)
        .fold<num>(0, (t, r) => t + (num.tryParse('${r['amount']}') ?? 0));
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(children: [
        StatsHeader(
          icon: Icons.receipt_outlined,
          title: 'Expenses',
          subtitle: '${items.length} recorded',
          color: EnhancedTheme.accentOrange,
        ),
        KpiRow(tiles: [
          KpiTile(
              icon: Icons.payments_outlined,
              label: 'Out of the drawer',
              value: money(sum(true)),
              color: EnhancedTheme.accentOrange),
          KpiTile(
              icon: Icons.account_balance_outlined,
              label: 'Bank / card',
              value: money(sum(false)),
              color: EnhancedTheme.accentCyan),
          KpiTile(
              icon: Icons.summarize_outlined,
              label: 'Total',
              value: money(sum(true) + sum(false)),
              color: EnhancedTheme.primaryTeal),
        ]),
      ]),
    );
  }
}

class _ExpenseCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback edit;
  const _ExpenseCard({required this.row, required this.edit});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      borderRadius: 16,
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('${row['category_name'] ?? 'Uncategorised'}',
                style: TextStyle(
                    color: context.labelColor,
                    fontWeight: FontWeight.w700,
                    fontSize: 15)),
          ),
          Text(money(row['amount']),
              style: const TextStyle(
                  color: EnhancedTheme.accentOrange,
                  fontWeight: FontWeight.w800,
                  fontSize: 15)),
          IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18), onPressed: edit),
        ]),
        Text(
            '${row['date']} · '
            '${row['payment_source'] == 'cash' ? 'drawer' : 'bank / card'}',
            style: TextStyle(color: context.hintColor, fontSize: 13)),
        if ('${row['description'] ?? ''}'.trim().isNotEmpty)
          Text('${row['description']}',
              style: TextStyle(color: context.hintColor, fontSize: 13)),
      ]),
    );
  }
}

class _ExpenseForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _ExpenseForm({this.existing});

  @override
  State<_ExpenseForm> createState() => _ExpenseFormState();
}

class _ExpenseFormState extends State<_ExpenseForm> {
  final _amount = TextEditingController();
  final _description = TextEditingController();
  int? _categoryId;
  String? _categoryName;
  String _source = 'cash';
  bool _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _amount.text = '${e['amount'] ?? ''}';
      _description.text = '${e['description'] ?? ''}';
      _categoryId = e['category'] as int?;
      _categoryName = e['category_name'] as String?;
      _source = '${e['payment_source'] ?? 'cash'}';
    }
  }

  @override
  void dispose() {
    _amount.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _pickCategory() async {
    final row = await pickRow(
      context,
      path: '/api/pos/expense-categories/',
      title: 'What kind of expense?',
      hint: 'Category name…',
      label: (r) => '${r['name']}',
    );
    if (row != null) {
      setState(() {
        _categoryId = row['id'] as int?;
        _categoryName = '${row['name']}';
      });
    }
  }

  Future<void> _newCategory() async {
    final name = TextEditingController();
    final made = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('New category'),
        content: TextField(
            controller: name,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Name')),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Add')),
        ],
      ),
    );
    if (made != true || name.text.trim().isEmpty) return;
    try {
      // Only the admin keeps the category list; a 403 lands in the form's
      // error line rather than silently doing nothing.
      final r = await api
          .post('/api/pos/expense-categories/', {'name': name.text.trim()});
      if (!mounted) return;
      setState(() {
        _categoryId = (r as Map)['id'] as int?;
        _categoryName = '${r['name']}';
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _submit() async {
    if (_amount.text.trim().isEmpty || _categoryId == null) {
      setState(() => _error = 'An expense needs a category and an amount.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final body = {
        'category': _categoryId,
        'amount': _amount.text.trim(),
        'description': _description.text.trim(),
        'payment_source': _source,
      };
      if (_isEdit) {
        await api.patch('/api/pos/expenses/${widget.existing!['id']}/', body);
      } else {
        await api.post('/api/pos/expenses/', body);
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
      title: _isEdit ? 'Edit expense' : 'Record expense',
      saving: _saving,
      error: _error,
      submitLabel: _isEdit ? 'Save changes' : 'Record',
      onSubmit: _submit,
      children: [
        InputDecorator(
          decoration: const InputDecoration(labelText: 'Category'),
          child: Row(children: [
            Expanded(
              child: Text(_categoryName ?? 'Not picked',
                  style: TextStyle(
                      color: _categoryId == null
                          ? context.hintColor
                          : context.labelColor),
                  overflow: TextOverflow.ellipsis),
            ),
            TextButton(onPressed: _pickCategory, child: const Text('Pick')),
            TextButton(onPressed: _newCategory, child: const Text('New')),
          ]),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _amount,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Amount (₦)'),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _source,
          decoration: const InputDecoration(
            labelText: 'Paid from',
            // Cash comes out of whatever drawer is open, so the till's
            // expected figure drops by it.
            helperText: 'Cash is taken off the open drawer',
          ),
          items: const [
            DropdownMenuItem(value: 'cash', child: Text('Cash drawer')),
            DropdownMenuItem(value: 'other', child: Text('Bank / card / transfer')),
          ],
          onChanged: (v) => setState(() => _source = v ?? 'cash'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _description,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'What for'),
        ),
      ],
    );
  }
}
