import 'package:flutter/material.dart';

/// Small tinted rounded square holding a card-header icon. Gives analytics
/// cards a consistent, accented header treatment.
class IconChip extends StatelessWidget {
  final IconData icon;
  final Color color;
  final double size;
  const IconChip({super.key, required this.icon, required this.color, this.size = 18});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(size * 0.4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Icon(icon, color: color, size: size),
    );
  }
}
