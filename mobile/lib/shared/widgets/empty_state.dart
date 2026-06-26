import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme/enhanced_theme.dart';

/// Reusable empty / no-data placeholder (PharmApp style). Set [boxed] true
/// for the bordered glass-panel style; false for centered full-screen.
// ponytail: dropped flutter_animate entrance — not a dep here, static is fine.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.color = EnhancedTheme.primaryTeal,
    this.boxed = false,
    this.action,
  });

  final IconData icon;
  final String title;
  final String? message;
  final Color color;
  final bool boxed;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final column = Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: EdgeInsets.all(boxed ? 18 : 28),
          decoration: BoxDecoration(
            gradient: RadialGradient(colors: [
              color.withValues(alpha: 0.12),
              color.withValues(alpha: 0.03),
            ]),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, color: color, size: boxed ? 32 : 56),
        ),
        SizedBox(height: boxed ? 12 : 20),
        Text(
          title,
          textAlign: TextAlign.center,
          style: GoogleFonts.outfit(
            color: context.labelColor,
            fontSize: boxed ? 15 : 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        if (message != null) ...[
          const SizedBox(height: 6),
          Text(
            message!,
            textAlign: TextAlign.center,
            style: TextStyle(color: context.subLabelColor, fontSize: 13),
          ),
        ],
        if (action != null) ...[
          const SizedBox(height: 16),
          action!,
        ],
      ],
    );

    if (!boxed) return Center(child: column);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 20),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: color.withValues(alpha: 0.15)),
      ),
      child: column,
    );
  }
}
