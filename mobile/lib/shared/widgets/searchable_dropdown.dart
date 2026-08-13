import 'package:flutter/material.dart';

/// Search-first pickers for every dropdown in the app.
///
/// [SearchableDropdown] is a drop-in replacement for [DropdownButtonFormField]:
/// same `items` / `initialValue` / `onChanged` / `decoration` arguments, but
/// tapping it opens a bottom sheet with a filter box instead of an inline menu.
/// Long option lists (medications, diseases, the 774 LGAs) stop being a scroll
/// hunt, and short ones behave the same as before.
///
/// [showSearchablePicker] is the same sheet on its own, for the places that
/// render a custom control (the report filter pills) rather than a form field.

/// Text used to match a typed query. Reads the item's [Text] child when there
/// is one, otherwise falls back to the value.
String _labelOf(DropdownMenuItem<dynamic> item) {
  final child = item.child;
  if (child is Text) return child.data ?? child.textSpan?.toPlainText() ?? '';
  return item.value?.toString() ?? '';
}

/// How well `label` answers query `q`, lower being better; null means no match.
///
/// Ranks exact hits over prefixes over word starts over mid-word substrings,
/// and only then falls back to a fuzzy subsequence ("amx" finding
/// "Amoxicillin"), so a typo-tolerant match never outranks a literal one.
int? _matchScore(String label, String q) {
  final l = label.toLowerCase();
  if (l == q) return 0;
  if (l.startsWith(q)) return 1;
  final at = l.indexOf(q);
  if (at > 0) return _isWordBoundary(l.codeUnitAt(at - 1)) ? 2 : 3;
  return _isSubsequence(l, q) ? 4 : null;
}

/// True for anything that is not a letter or a digit, i.e. the character before
/// a new word: spaces, hyphens, slashes, commas, parentheses.
bool _isWordBoundary(int code) {
  final isDigit = code >= 0x30 && code <= 0x39;
  final isLetter = code >= 0x61 && code <= 0x7a;
  return !isDigit && !isLetter;
}

/// True when every character of `q` appears in `text` in order (gaps allowed).
bool _isSubsequence(String text, String q) {
  var i = 0;
  for (final c in text.codeUnits) {
    if (i == q.length) break;
    if (c == q.codeUnitAt(i)) i++;
  }
  return i == q.length;
}

/// Items matching `query`, best first; ties keep the caller's original order.
/// Public so the ranking can be tested without driving the sheet.
List<DropdownMenuItem<T>> rankDropdownMatches<T>(
  List<DropdownMenuItem<T>> items,
  String query,
) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return items;
  final scored = <(int, int, DropdownMenuItem<T>)>[];
  for (var i = 0; i < items.length; i++) {
    final score = _matchScore(_labelOf(items[i]), q);
    if (score != null) scored.add((score, i, items[i]));
  }
  scored.sort((a, b) => a.$1 == b.$1 ? a.$2 - b.$2 : a.$1 - b.$1);
  return [for (final s in scored) s.$3];
}

/// Opens the picker sheet. Resolves to the chosen item, or null if the sheet
/// was dismissed — an item whose `value` is null (an "— any —" row) is a real
/// choice and comes back as the item itself.
///
/// [searchable] hides the filter box when false, for the odd list where a
/// search line is pure noise.
Future<DropdownMenuItem<T>?> showSearchablePicker<T>({
  required BuildContext context,
  required List<DropdownMenuItem<T>> items,
  T? selected,
  String? title,
  String searchHint = 'Search',
  bool searchable = true,
}) {
  return showModalBottomSheet<DropdownMenuItem<T>>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => _PickerSheet<T>(
      items: items,
      selected: selected,
      title: title,
      searchHint: searchHint,
      searchable: searchable,
    ),
  );
}

class _PickerSheet<T> extends StatefulWidget {
  final List<DropdownMenuItem<T>> items;
  final T? selected;
  final String? title;
  final String searchHint;
  final bool searchable;

  const _PickerSheet({
    required this.items,
    required this.selected,
    required this.title,
    required this.searchHint,
    required this.searchable,
  });

  @override
  State<_PickerSheet<T>> createState() => _PickerSheetState<T>();
}

class _PickerSheetState<T> extends State<_PickerSheet<T>> {
  final _query = TextEditingController();

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  List<DropdownMenuItem<T>> get _matches =>
      rankDropdownMatches(widget.items, _query.text);

  @override
  Widget build(BuildContext context) {
    final matches = _matches;
    final maxHeight = MediaQuery.sizeOf(context).height * 0.75;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: maxHeight),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.title != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text(
                  widget.title!,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            if (widget.searchable)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: TextField(
                  controller: _query,
                  // ponytail: only steal the keyboard when the list is long
                  // enough that scrolling it would be the slower path.
                  autofocus: widget.items.length >= 10,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: widget.searchHint,
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    border: const OutlineInputBorder(),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              ),
            Flexible(
              child: matches.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.fromLTRB(20, 8, 20, 24),
                      child: Text('No match'),
                    )
                  : ListView.builder(
                      shrinkWrap: true,
                      padding: const EdgeInsets.only(bottom: 12),
                      itemCount: matches.length,
                      itemBuilder: (_, i) {
                        final item = matches[i];
                        final picked = item.value == widget.selected;
                        return ListTile(
                          dense: true,
                          selected: picked,
                          title: DefaultTextStyle.merge(
                            style: Theme.of(context).textTheme.bodyMedium,
                            child: item.child,
                          ),
                          trailing: picked ? const Icon(Icons.check) : null,
                          onTap: () => Navigator.pop(context, item),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Drop-in searchable replacement for [DropdownButtonFormField].
class SearchableDropdown<T> extends FormField<T> {
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?>? onChanged;
  final T? currentValue;

  SearchableDropdown({
    super.key,
    required this.items,
    required this.onChanged,
    T? initialValue,
    T? value,
    InputDecoration decoration = const InputDecoration(),
    Widget? hint,
    String searchHint = 'Search',
    // Per-dropdown opt-out: pass false to drop the filter box from this one
    // field's sheet.
    bool searchable = true,
    // Accepted so call sites can be swapped verbatim; the sheet is always
    // full width, so there is nothing to expand.
    bool isExpanded = true,
    bool isDense = false,
    super.validator,
    super.autovalidateMode,
  })  : currentValue = value ?? initialValue,
        super(
          initialValue: value ?? initialValue,
          enabled: onChanged != null,
          builder: (field) {
            final context = field.context;
            final enabled = onChanged != null;
            final selected = items.where((i) => i.value == field.value);
            final label = selected.isEmpty
                ? (hint ??
                    Text(
                      decoration.hintText ?? '',
                      style: TextStyle(color: Theme.of(context).hintColor),
                    ))
                : selected.first.child;
            return InkWell(
              onTap: enabled
                  ? () async {
                      final picked = await showSearchablePicker<T>(
                        context: context,
                        items: items,
                        selected: field.value,
                        title: decoration.labelText,
                        searchHint: searchHint,
                        searchable: searchable,
                      );
                      if (picked != null) field.didChange(picked.value);
                    }
                  : null,
              borderRadius: BorderRadius.circular(8),
              child: InputDecorator(
                decoration: decoration.copyWith(
                  errorText: field.errorText,
                  enabled: enabled,
                  suffixIcon: decoration.suffixIcon ??
                      const Icon(Icons.arrow_drop_down),
                ),
                isEmpty: selected.isEmpty,
                isFocused: false,
                child: DefaultTextStyle.merge(
                  style: Theme.of(context).textTheme.bodyLarge,
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                  child: label,
                ),
              ),
            );
          },
        );

  @override
  FormFieldState<T> createState() => _SearchableDropdownState<T>();
}

class _SearchableDropdownState<T> extends FormFieldState<T> {
  SearchableDropdown<T> get _field => widget as SearchableDropdown<T>;

  @override
  void didUpdateWidget(SearchableDropdown<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Owners drive the value with setState, the way DropdownButtonFormField
    // is used everywhere in this app; keep the field in step with them.
    if (oldWidget.currentValue != _field.currentValue) {
      setValue(_field.currentValue);
    }
  }

  @override
  void didChange(T? value) {
    super.didChange(value);
    _field.onChanged?.call(value);
  }
}
