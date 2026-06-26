import 'package:flutter/material.dart';

import '../../core/theme/enhanced_theme.dart';

/// One place for success/failure toasts so every screen reports the same way.
/// Pass the backend envelope's message (ApiException.friendly already extracts
/// it on failures).
void showSuccess(BuildContext context, String message) =>
    _snack(context, message, EnhancedTheme.primaryTeal, Icons.check_circle_outline);

void showError(BuildContext context, String message) =>
    _snack(context, message, EnhancedTheme.errorRed, Icons.error_outline);

void _snack(BuildContext context, String message, Color color, IconData icon) {
  final messenger = ScaffoldMessenger.of(context);
  messenger.clearSnackBars(); // never stack toasts
  messenger.showSnackBar(
    SnackBar(
      behavior: SnackBarBehavior.floating,
      backgroundColor: color,
      content: Row(
        children: [
          Icon(icon, color: Colors.white, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    ),
  );
}
