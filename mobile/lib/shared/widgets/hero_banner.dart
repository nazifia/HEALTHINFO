import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/theme/enhanced_theme.dart';
import 'motion.dart';

/// The welcome banner a user lands on: a greeting for the time of day, their
/// name, one line of who they are, and a handful of facts. The patient and the
/// clinician land on the same shape; only the facts differ. Same content as
/// the web hero (web/app.js heroHtml).
class HeroBanner extends StatelessWidget {
  final String name;
  final String subtitle;
  final List<MapEntry<String, Object?>> stats;

  /// Labels of the facts that need acting on: their tiles flash red.
  final Set<String> alerts;
  final Widget? action;
  const HeroBanner({
    super.key,
    required this.name,
    required this.subtitle,
    required this.stats,
    this.alerts = const {},
    this.action,
  });

  static String text(Object? v) {
    if (v == null) return '—';
    if (v is List) return v.isEmpty ? '—' : v.join(', ');
    final s = '$v'.trim();
    return s.isEmpty ? '—' : s;
  }

  /// The button style that reads on the gradient.
  static ButtonStyle get actionStyle => OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        side: const BorderSide(color: Color(0x99FFFFFF)),
      );

  @override
  Widget build(BuildContext context) {
    final h = DateTime.now().hour;
    final greet = h < 12
        ? 'Good morning'
        : h < 17
            ? 'Good afternoon'
            : 'Good evening';
    final initials = name
        .split(RegExp(r'\s+'))
        .take(2)
        .map((w) => w.isEmpty ? '' : w[0])
        .join()
        .toUpperCase();
    const white70 = Color(0xB3FFFFFF);
    return Reveal(
        child: Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [EnhancedTheme.primaryTeal, EnhancedTheme.accentCyan],
        ),
        boxShadow: [
          BoxShadow(
            color: EnhancedTheme.primaryTeal.withValues(alpha: 0.35),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 60,
                height: 60,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: const Color(0x38FFFFFF),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0x66FFFFFF)),
                ),
                child: Text(initials,
                    style: GoogleFonts.outfit(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('$greet,',
                        style: const TextStyle(color: white70, fontSize: 14)),
                    Text(name,
                        style: GoogleFonts.outfit(
                            color: Colors.white,
                            fontSize: 24,
                            fontWeight: FontWeight.w800,
                            height: 1.15)),
                    if (subtitle.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(subtitle,
                            style: const TextStyle(
                                color: white70, fontSize: 13)),
                      ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final (i, s) in stats.indexed)
                Reveal(
                    index: i + 1,
                    child: _HeroStat(s.key, s.value,
                        alert: alerts.contains(s.key))),
            ],
          ),
          if (action != null) ...[
            const SizedBox(height: 16),
            action!,
          ],
        ],
      ),
    ));
  }
}

class _HeroStat extends StatefulWidget {
  final String label;
  final Object? value;
  final bool alert;
  const _HeroStat(this.label, this.value, {this.alert = false});

  @override
  State<_HeroStat> createState() => _HeroStatState();
}

class _HeroStatState extends State<_HeroStat>
    with SingleTickerProviderStateMixin {
  static const _quiet = Color(0x2EFFFFFF);
  static const _red = Color(0xFFE53935);

  // Same 1.2s on/off as the web tile; solid red under "reduce motion".
  late final _blink = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1200));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.alert && !MediaQuery.disableAnimationsOf(context)) {
      _blink.repeat();
    } else {
      _blink.stop();
      _blink.value = 0;
    }
  }

  @override
  void didUpdateWidget(_HeroStat old) {
    super.didUpdateWidget(old);
    if (old.alert != widget.alert) didChangeDependencies();
  }

  @override
  void dispose() {
    _blink.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final label = widget.label;
    final value = widget.value;
    return AnimatedBuilder(
      animation: _blink,
      builder: (context, child) => Container(
        constraints: const BoxConstraints(minWidth: 96),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: widget.alert && _blink.value < .5 ? _red : _quiet,
          borderRadius: BorderRadius.circular(12),
        ),
        child: child,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label,
              style: const TextStyle(color: Color(0xB3FFFFFF), fontSize: 11)),
          CountUp(HeroBanner.text(value),
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}
