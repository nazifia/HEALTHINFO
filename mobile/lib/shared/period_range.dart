import 'package:flutter/material.dart';

/// "Which period?" for a dashboard: a whole month, a whole year, or any range.
///
/// Month and year come back as the same from/to range a custom pick does, so
/// the dashboard's existing ?from=&to= call needs no change. Returns null when
/// the user backs out. The end is capped at today — the API would zero-fill a
/// future that has not happened.
Future<DateTimeRange?> pickPeriodRange(
    BuildContext context, DateTimeRange? current) async {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final choice = await showModalBottomSheet<String>(
    context: context,
    builder: (_) => SafeArea(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        ListTile(
            leading: const Icon(Icons.calendar_view_month),
            title: const Text('A month'),
            onTap: () => Navigator.pop(context, 'month')),
        ListTile(
            leading: const Icon(Icons.calendar_today),
            title: const Text('A year'),
            onTap: () => Navigator.pop(context, 'year')),
        ListTile(
            leading: const Icon(Icons.date_range),
            title: const Text('Custom range'),
            onTap: () => Navigator.pop(context, 'range')),
      ]),
    ),
  );
  if (choice == null || !context.mounted) return null;
  if (choice == 'range') {
    return showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 5),
      lastDate: now,
      initialDateRange: current,
    );
  }
  final d = await showDatePicker(
    context: context,
    initialDate: today,
    firstDate: DateTime(now.year - 5),
    lastDate: today,
    initialDatePickerMode:
        choice == 'year' ? DatePickerMode.year : DatePickerMode.day,
    helpText: choice == 'year'
        ? 'Pick any day in the year'
        : 'Pick any day in the month',
  );
  if (d == null) return null;
  final start = choice == 'year' ? DateTime(d.year) : DateTime(d.year, d.month);
  final last = choice == 'year' ? DateTime(d.year, 12, 31) : DateTime(d.year, d.month + 1, 0);
  return DateTimeRange(start: start, end: last.isAfter(today) ? today : last);
}

/// Month/year/range filter for a report screen's State. Add the mixin, pass
/// [periodQuery] to the API call, and put [periodButton] atop the list; the
/// button's callback reloads the screen's future.
mixin PeriodFilter<T extends StatefulWidget> on State<T> {
  DateTimeRange? range; // null = all time

  Map<String, String>? get periodQuery => range == null
      ? null
      : {
          'from': range!.start.toIso8601String().substring(0, 10),
          'to': range!.end.toIso8601String().substring(0, 10),
        };

  Widget periodButton(VoidCallback reload) => Align(
        alignment: Alignment.centerRight,
        child: TextButton.icon(
          onPressed: () async {
            final picked = await pickPeriodRange(context, range);
            if (picked == null) return;
            setState(() => range = picked);
            reload();
          },
          icon: const Icon(Icons.date_range),
          label: Text(range == null
              ? 'All time'
              : '${periodQuery!['from']} → ${periodQuery!['to']}'),
        ),
      );
}
