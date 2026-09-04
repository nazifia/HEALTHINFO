import 'package:flutter/material.dart';

import '../main.dart';
import '../core/theme/enhanced_theme.dart';
import '../shared/widgets/glass_card.dart';
import '../shared/widgets/snack.dart';
import 'pharmacy_kit.dart';
import 'report_scaffold.dart';

/// Notifications — GET /api/pos/notifications/.
///
/// What the app is telling this user: stock running out, a batch about to
/// expire, a basket waiting at the till. Scoped to the caller by the API — a
/// notification is addressed to one person, and listing everyone's would leak
/// who is being chased about what.
///
/// Only the read flag is writable, so tapping a row marks it read and there is
/// nothing else to edit.
class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ReportListScreen(
      path: '/api/pos/notifications/',
      fabLabel: '',
      showFab: false,
      emptyIcon: Icons.notifications_none_outlined,
      emptyTitle: 'Nothing to report',
      emptyMessage: 'Low stock and expiry alerts land here.',
      savedMessage: '',
      filters: const [
        ReportFilter(param: 'is_read', anyLabel: 'All', options: {
          'false': 'Unread',
          'true': 'Read',
        }),
        ReportFilter(param: 'kind', anyLabel: 'Any kind', options: {
          'low_stock': 'Low stock',
          'out_of_stock': 'Out of stock',
          'expiry': 'Expiring',
          'payment_request': 'Payment request',
          'system': 'System',
        }),
      ],
      header: (items) => _Header(items: items),
      card: (row, reload, edit) => _NotificationCard(row: row, reload: reload),
      form: (_) => const SizedBox.shrink(),
    );
  }
}

class _Header extends StatefulWidget {
  final List<Map<String, dynamic>> items;
  const _Header({required this.items});

  @override
  State<_Header> createState() => _HeaderState();
}

class _HeaderState extends State<_Header> {
  bool _busy = false;

  Future<void> _readAll() async {
    setState(() => _busy = true);
    // ponytail: the list below does not refresh itself — pull down to reload.
    // A router-level refresh hook is the fix if that ever grates.
    await runAction(context, '/api/pos/notifications/read-all/');
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final unread = widget.items.where((r) => r['is_read'] != true).length;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(children: [
        Expanded(
          child: Text(
              unread == 0 ? 'Nothing unread' : '$unread unread',
              style: TextStyle(
                  color: context.labelColor,
                  fontSize: 15,
                  fontWeight: FontWeight.w700)),
        ),
        if (unread > 0)
          TextButton.icon(
            onPressed: _busy ? null : _readAll,
            icon: const Icon(Icons.done_all, size: 18),
            label: const Text('Mark all read'),
          ),
      ]),
    );
  }
}

class _NotificationCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final VoidCallback reload;
  const _NotificationCard({required this.row, required this.reload});

  Future<void> _markRead(BuildContext context) async {
    if (row['is_read'] == true) return;
    try {
      await api.patch('/api/pos/notifications/${row['id']}/', {'is_read': true});
      reload();
    } catch (e) {
      if (context.mounted) showError(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final unread = row['is_read'] != true;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => _markRead(context),
      child: GlassCard(
        borderRadius: 16,
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            if (unread)
              Container(
                width: 8,
                height: 8,
                margin: const EdgeInsets.only(right: 8),
                decoration: const BoxDecoration(
                    color: EnhancedTheme.primaryTeal, shape: BoxShape.circle),
              ),
            Expanded(
              child: Text('${row['title']}',
                  style: TextStyle(
                      color: context.labelColor,
                      fontWeight: unread ? FontWeight.w800 : FontWeight.w600,
                      fontSize: 15)),
            ),
            ReportBadge(
                text: '${row['priority']}',
                color: statusColor(row['priority'])),
          ]),
          if ('${row['message'] ?? ''}'.trim().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('${row['message']}',
                style: TextStyle(color: context.hintColor, fontSize: 13)),
          ],
          const SizedBox(height: 4),
          Text(
              '${'${row['kind']}'.replaceAll('_', ' ')} · '
              '${'${row['created_at']}'.split('T').first}',
              style: TextStyle(color: context.hintColor, fontSize: 12)),
        ]),
      ),
    );
  }
}
