import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../api.dart';
import '../main.dart';
import 'widgets/snack.dart';

/// Pull one of the API's CSV endpoints and hand the file to the platform's
/// share sheet — the phone's own "save to Files / send to someone" dialog.
///
/// The server renders the CSV (`?format=csv`), so the client never builds a
/// row: what is shared is byte-for-byte what the web client downloads.
///
/// ponytail: share sheet rather than a chosen save path — no file-picker
/// dependency, and on a phone "share" is how a file leaves the app anyway.
/// share_plus cannot share files on Linux; desktop Linux gets the error toast.
Future<void> exportCsv(
  BuildContext context, {
  required String path,
  required String filename,
  Map<String, String>? query,
}) async {
  try {
    final bytes = await api.getBytes(path, {...?query, 'format': 'csv'});
    if (!context.mounted) return;
    await SharePlus.instance.share(ShareParams(
      title: filename,
      files: [
        XFile.fromData(
          Uint8List.fromList(bytes),
          name: filename,
          mimeType: 'text/csv',
        ),
      ],
      // Byte-backed files land in a temp file named for the platform, so name
      // the download explicitly or the share sheet offers "file.csv".
      fileNameOverrides: [filename],
    ));
  } on ApiException catch (e) {
    if (context.mounted) showError(context, e.friendly);
  } catch (e) {
    if (context.mounted) showError(context, 'Could not export: $e');
  }
}

/// Toolbar button that runs [exportCsv]. Disabled while a pull is in flight so
/// a slow export is not fired twice.
class CsvExportButton extends StatefulWidget {
  final String path;
  final String filename;
  final Map<String, String>? query;
  final String tooltip;

  const CsvExportButton({
    super.key,
    required this.path,
    required this.filename,
    this.query,
    this.tooltip = 'Export CSV',
  });

  @override
  State<CsvExportButton> createState() => _CsvExportButtonState();
}

class _CsvExportButtonState extends State<CsvExportButton> {
  bool _busy = false;

  Future<void> _run() async {
    setState(() => _busy = true);
    await exportCsv(context,
        path: widget.path, filename: widget.filename, query: widget.query);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: widget.tooltip,
      onPressed: _busy ? null : _run,
      icon: _busy
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2))
          : const Icon(Icons.file_download_outlined),
    );
  }
}
