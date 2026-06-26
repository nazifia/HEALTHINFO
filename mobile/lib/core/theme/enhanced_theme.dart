import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shimmer/shimmer.dart';

class EnhancedTheme {
  // ── Premium Colour Palette ──────────────────────────────────────────────────
  static const Color primaryDark      = Color(0xFF0F172A); // Slate 900
  static const Color primaryTeal      = Color(0xFF0D9488); // Teal 600
  static const Color accentCyan       = Color(0xFF06B6D4);
  static const Color accentOrange     = Color(0xFFF59E0B);
  static const Color accentPurple     = Color(0xFF8B5CF6);
  static const Color surfaceColor     = Color(0xFF1E293B);
  static const Color backgroundLight  = Color(0xFFF8FAFC);
  static const Color surfaceGlass     = Color(0x14FFFFFF);
  static const Color glassLight       = Color(0x33FFFFFF);
  static const Color glassMedium      = Color(0x66FFFFFF);
  static const Color glassDark        = Color(0x99FFFFFF);
  static const Color successGreen     = Color(0xFF10B981);
  static const Color warningAmber     = Color(0xFFF59E0B);
  static const Color errorRed         = Color(0xFFEF4444);
  static const Color infoBlue         = Color(0xFF3B82F6);

  // ── ThemeData ────────────────────────────────────────────────────────────────

  static ThemeData get enhancedDarkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primaryTeal,
        brightness: Brightness.dark,
        surface: surfaceColor,
        surfaceTint: Colors.transparent,
      ),
      scaffoldBackgroundColor: primaryDark,
      textTheme: TextTheme(
        displayLarge: GoogleFonts.outfit(fontWeight: FontWeight.bold, color: Colors.white),
        titleLarge:   GoogleFonts.outfit(fontWeight: FontWeight.w600, color: Colors.white),
        bodyLarge:    GoogleFonts.inter(color: Colors.white),
        bodyMedium:   GoogleFonts.inter(color: Colors.white70),
        labelLarge:   GoogleFonts.inter(color: Colors.white70, fontWeight: FontWeight.w500),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.06),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(16)),
          borderSide: BorderSide(color: primaryTeal, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
        hintStyle: TextStyle(color: Colors.white.withValues(alpha: 0.50)),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryTeal,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 32),
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 16),
        ),
      ),
      cardTheme: CardThemeData(
        color: surfaceColor,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        margin: const EdgeInsets.all(8),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: Colors.black.withValues(alpha: 0.85),
        actionTextColor: accentCyan,
        contentTextStyle: GoogleFonts.inter(color: Colors.black, fontSize: 14),
      ),
      dividerTheme: DividerThemeData(
        color: Colors.white.withValues(alpha: 0.08),
        thickness: 1,
        space: 1,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: GoogleFonts.outfit(
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: surfaceColor,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: GoogleFonts.inter(color: Colors.white70, fontSize: 13),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.transparent,
        modalBackgroundColor: Colors.transparent,
      ),
    );
  }

  static ThemeData get enhancedLightTheme {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primaryTeal,
        brightness: Brightness.light,
        surface: backgroundLight,
        surfaceTint: Colors.transparent,
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.outfit(fontWeight: FontWeight.bold, color: primaryDark),
        titleLarge:   GoogleFonts.outfit(fontWeight: FontWeight.w600, color: primaryDark),
        bodyLarge:    GoogleFonts.inter(color: Colors.black87),
        bodyMedium:   GoogleFonts.inter(color: Colors.black54),
        labelLarge:   GoogleFonts.inter(color: Colors.black54, fontWeight: FontWeight.w500),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: Colors.grey.shade200),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(16)),
          borderSide: BorderSide(color: primaryTeal, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryTeal,
          foregroundColor: Colors.black,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 32),
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 16),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryTeal,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 14),
        ),
      ),
      cardTheme: CardThemeData(
        color: Colors.black,
        elevation: 0,
        shadowColor: Colors.black.withValues(alpha:0.1),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        margin: const EdgeInsets.all(8),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: Colors.black.withValues(alpha: 0.85),
        actionTextColor: accentCyan,
        contentTextStyle: GoogleFonts.inter(color: Colors.black, fontSize: 14),
      ),
      dividerTheme: DividerThemeData(
        color: Colors.black.withValues(alpha: 0.08),
        thickness: 1,
        space: 1,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: GoogleFonts.outfit(
          color: primaryDark,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
        iconTheme: const IconThemeData(color: Color(0xFF0F172A)),
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: Colors.black,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: GoogleFonts.inter(color: Colors.black87, fontSize: 13),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: Colors.white,
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.white,
        modalBackgroundColor: Colors.white,
      ),
    );
  }

  // ── Glassmorphic container (BackdropFilter – no fixed dimensions needed) ─────
  static Widget glassContainer(
    BuildContext context, {
    required Widget child,
    double blur = 20,
    double? opacity,
    Color? color,
    BorderRadius? borderRadius,
    EdgeInsetsGeometry? padding,
    BoxConstraints? constraints,
  }) {
    final br = borderRadius ?? BorderRadius.circular(20);
    return ClipRRect(
      borderRadius: br,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          constraints: constraints,
          padding: padding,
          decoration: BoxDecoration(
            color: (color ?? Colors.white).withValues(alpha:opacity ?? 0.08),
            borderRadius: br,
            border: Border.all(
              color: Colors.white.withValues(alpha:0.15),
              width: 1.5,
            ),
          ),
          child: child,
        ),
      ),
    );
  }

  // ── Shimmer loading placeholder ──────────────────────────────────────────────
  static Widget loadingShimmer({
    double width = double.infinity,
    double height = 16,
    double radius = 8,
  }) {
    return Shimmer.fromColors(
      baseColor: Colors.white.withValues(alpha:0.05),
      highlightColor: Colors.white.withValues(alpha:0.15),
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha:0.1),
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    );
  }

  // ── Badge helpers ────────────────────────────────────────────────────────────
  static Widget successBadge(String text) => _badge(
        text: text,
        icon: Icons.check_circle,
        color: successGreen,
      );

  static Widget errorBadge(String text) => _badge(
        text: text,
        icon: Icons.error,
        color: errorRed,
      );

  static Widget warningBadge(String text) => _badge(
        text: text,
        icon: Icons.warning_amber_rounded,
        color: warningAmber,
      );

  static Widget infoBadge(String text) => _badge(
        text: text,
        icon: Icons.info_outline,
        color: infoBlue,
      );

  static Widget _badge({
    required String text,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha:0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha:0.3), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 14),
          const SizedBox(width: 4),
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

/// Placeholder provider kept for backwards compatibility.
final enhancedThemeProvider = Provider<bool>((ref) => true);

// ── Theme-aware BuildContext extension ────────────────────────────────────────

extension PharmContext on BuildContext {
  bool get isDark => Theme.of(this).brightness == Brightness.dark;

  /// Scaffold / page background colour.
  Color get scaffoldBg =>
      isDark ? const Color(0xFF0F172A) : const Color(0xFFF1F5F9);

  /// Full-page gradient decoration used inside the background Stack.
  BoxDecoration get bgGradient => BoxDecoration(
        gradient: LinearGradient(
          colors: isDark
              ? [const Color(0xFF0A0F1E), const Color(0xFF0F172A), const Color(0xFF1E293B)]
              : [const Color(0xFFF8FAFC), const Color(0xFFEFF6FF), const Color(0xFFE0F2FE)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      );

  /// Glass-card background fill.
  Color get cardColor => isDark
      ? Colors.white.withValues(alpha: 0.10)
      : Colors.white.withValues(alpha: 0.90);

  /// Glass-card border colour.
  Color get borderColor => isDark
      ? Colors.white.withValues(alpha: 0.16)
      : Colors.black.withValues(alpha: 0.09);

  /// Primary label text colour.
  Color get labelColor => isDark ? Colors.white : Colors.black87;

  /// Secondary / sub-label text colour.
  Color get subLabelColor => isDark
      ? Colors.white.withValues(alpha: 0.80)
      : Colors.black.withValues(alpha: 0.65);

  /// Hint / tertiary text colour.
  Color get hintColor => isDark
      ? Colors.white.withValues(alpha: 0.62)
      : Colors.black.withValues(alpha: 0.42);

  /// Divider line colour.
  Color get dividerColor => isDark
      ? Colors.white.withValues(alpha: 0.07)
      : Colors.black.withValues(alpha: 0.06);

  /// Icon colour on background (not on accent).
  Color get iconOnBg => isDark ? Colors.white : Colors.black87;
}
