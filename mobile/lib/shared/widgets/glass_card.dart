import 'dart:ui';
import 'package:flutter/material.dart';
import '../../core/theme/enhanced_theme.dart';

/// Reusable frosted-glass card (PharmApp style). Theme-aware by default.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding,
    this.margin,
    this.borderRadius = 18,
    this.blur = 20,
    this.color,
    this.borderColor,
    this.onTap,
    this.width,
    this.height,
    this.constraints,
    this.boxShadow,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final double borderRadius;
  final double blur;
  final Color? color;
  final Color? borderColor;
  final VoidCallback? onTap;
  final double? width;
  final double? height;
  final BoxConstraints? constraints;
  final List<BoxShadow>? boxShadow;

  @override
  Widget build(BuildContext context) {
    final br = BorderRadius.circular(borderRadius);
    Widget card = ClipRRect(
      borderRadius: br,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          width: width,
          height: height,
          padding: padding,
          constraints: constraints,
          decoration: BoxDecoration(
            color: color ?? context.cardColor,
            borderRadius: br,
            border: Border.all(color: borderColor ?? context.borderColor),
            boxShadow: boxShadow,
          ),
          child: child,
        ),
      ),
    );

    if (onTap != null) {
      card = Material(
        color: Colors.transparent,
        child: InkWell(borderRadius: br, onTap: onTap, child: card),
      );
    }
    if (margin != null) card = Padding(padding: margin!, child: card);
    return card;
  }
}
