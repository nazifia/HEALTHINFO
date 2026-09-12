import 'package:flutter/material.dart';

/// Entrance motion for the dashboards and stat screens. Every piece honours
/// the OS "reduce motion" setting (MediaQuery.disableAnimations) by snapping
/// to its final state.
///
/// - [Reveal]: fade + lift a card in, staggered by [index].
/// - [Sweep]: uncover a chart left-to-right, so a line "draws" and bars
///   appear in order.
/// - [CountUp]: tick a formatted number up from zero, keeping its prefix,
///   suffix, grouping and decimals ("₦1,200.50", "42%", "3 / 5").
/// - [Grow]: tween 0→1 for callers that scale a value themselves (donut
///   fill, comparison bars).
///
/// [Reveal] and [CountUp] wait until they are scrolled into view: the stat
/// screens are non-lazy ListViews, so everything builds at once and a card
/// below the fold would otherwise have finished before anyone saw it.

const _reveal = Duration(milliseconds: 380);
const _stagger = Duration(milliseconds: 55);
const _count = Duration(milliseconds: 800);
const _sweep = Duration(milliseconds: 700);

bool _still(BuildContext c) => MediaQuery.disableAnimationsOf(c);

/// Flips [shown] the first time this widget's box is inside the screen.
/// Listens to every enclosing scrollable (a KPI strip scrolls sideways inside
/// a page that scrolls down) and stops listening once shown.
mixin _WhenVisible<T extends StatefulWidget> on State<T> {
  bool shown = false;
  final _positions = <ScrollPosition>[];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    for (final p in _positions) {
      p.removeListener(_afterScroll);
    }
    _positions.clear();
    for (
      var s = Scrollable.maybeOf(context);
      s != null;
      s = Scrollable.maybeOf(s.context)
    ) {
      _positions.add(s.position..addListener(_afterScroll));
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _check());
  }

  // The position notifies before the frame lays out, so measure after it.
  void _afterScroll() =>
      WidgetsBinding.instance.addPostFrameCallback((_) => _check());

  void _check() {
    if (shown || !mounted) return;
    final ro = context.findRenderObject();
    if (ro is! RenderBox || !ro.hasSize || !ro.attached) return;
    final top = ro.localToGlobal(Offset.zero).dy;
    final screen = MediaQuery.sizeOf(context).height;
    // ponytail: vertical test only; a sideways strip builds its chips lazily
    if (top < screen && top + ro.size.height > 0) {
      setState(() => shown = true);
      _dropListeners();
    }
  }

  void _dropListeners() {
    for (final p in _positions) {
      p.removeListener(_afterScroll);
    }
    _positions.clear();
  }

  @override
  void dispose() {
    _dropListeners();
    super.dispose();
  }
}

class Reveal extends StatefulWidget {
  final Widget child;

  /// Slot in a row or list; each slot starts [_stagger] later than the last.
  final int index;
  const Reveal({super.key, required this.child, this.index = 0});

  @override
  State<Reveal> createState() => _RevealState();
}

class _RevealState extends State<Reveal> with _WhenVisible {
  @override
  Widget build(BuildContext context) {
    if (_still(context)) return widget.child;
    // ponytail: stagger caps at 8 slots so a long list never waits half a second
    final delay = _stagger * widget.index.clamp(0, 8);
    final total = _reveal + delay;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: shown ? 1 : 0),
      duration: total,
      curve: Interval(
        delay.inMilliseconds / total.inMilliseconds,
        1,
        curve: Curves.easeOutCubic,
      ),
      child: widget.child,
      builder: (_, t, c) => Opacity(
        opacity: t,
        child: Transform.translate(offset: Offset(0, 14 * (1 - t)), child: c),
      ),
    );
  }
}

class Sweep extends StatelessWidget {
  final Widget child;
  const Sweep({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    if (_still(context)) return child;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: _sweep,
      curve: Curves.easeOutCubic,
      child: child,
      builder: (_, t, c) => ClipRect(clipper: _Left(t), child: c),
    );
  }
}

class _Left extends CustomClipper<Rect> {
  final double t;
  _Left(this.t);
  @override
  Rect getClip(Size s) => Rect.fromLTWH(0, 0, s.width * t, s.height);
  @override
  bool shouldReclip(_Left old) => old.t != t;
}

class Grow extends StatelessWidget {
  final Widget Function(BuildContext, double t) builder;
  const Grow({super.key, required this.builder});

  @override
  Widget build(BuildContext context) {
    if (_still(context)) return builder(context, 1);
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: _count,
      curve: Curves.easeOutCubic,
      builder: (c, t, _) => builder(c, t),
    );
  }
}

/// Drop-in for a [Text] whose string holds one number. Strings with no
/// number, or digits either side of it (dates, ranges, times), render plain.
class CountUp extends StatefulWidget {
  final String value;
  final TextStyle? style;
  final int? maxLines;
  final TextOverflow? overflow;
  final TextAlign? textAlign;
  const CountUp(
    this.value, {
    super.key,
    this.style,
    this.maxLines,
    this.overflow,
    this.textAlign,
  });

  static final _num = RegExp(r'^(\D*?)(\d[\d,]*)(\.\d+)?(\D*)$');
  static final _group = RegExp(r'\B(?=(\d{3})+(?!\d))');

  /// Renders [n] the way the source string did: same decimals, same commas.
  static String format(String src, double n) {
    final m = _num.firstMatch(src);
    if (m == null) return src;
    final decimals = (m[3]?.length ?? 1) - 1;
    var s = n.toStringAsFixed(decimals);
    if (m[2]!.contains(',')) {
      final dot = s.indexOf('.');
      final whole = dot < 0 ? s : s.substring(0, dot);
      s =
          whole.replaceAllMapped(_group, (_) => ',') +
          (dot < 0 ? '' : s.substring(dot));
    }
    return '${m[1]}$s${m[4]}';
  }

  @override
  State<CountUp> createState() => _CountUpState();
}

class _CountUpState extends State<CountUp> with _WhenVisible {
  @override
  Widget build(BuildContext context) {
    final value = widget.value;
    final m = CountUp._num.firstMatch(value);
    Widget text(String s) => Text(
      s,
      style: widget.style,
      maxLines: widget.maxLines,
      overflow: widget.overflow,
      textAlign: widget.textAlign,
    );
    if (m == null || _still(context)) return text(value);
    final target = double.parse(m[2]!.replaceAll(',', '') + (m[3] ?? ''));
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: shown ? target : 0),
      duration: _count,
      curve: Curves.easeOutCubic,
      builder: (_, n, _) => text(CountUp.format(value, n)),
    );
  }
}
