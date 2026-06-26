import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'config.dart';
import 'core/theme/enhanced_theme.dart';
import 'core/theme/theme_provider.dart';
import 'inactivity_watcher.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';

final api = Api();

// Lets the inactivity watcher route to login from outside the widget tree.
final navigatorKey = GlobalKey<NavigatorState>();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await loadTenant();
  await api.loadTokens();
  final prefs = await SharedPreferences.getInstance();
  final saved = prefs.getString('theme_mode');
  final mode = saved == 'dark' ? ThemeMode.dark : ThemeMode.light;
  runApp(
    ProviderScope(
      overrides: [
        themeModeProvider.overrideWith((ref) => ThemeModeNotifier(mode)),
      ],
      child: const HealthInfoApp(),
    ),
  );
}

class HealthInfoApp extends ConsumerWidget {
  const HealthInfoApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Health Info',
      navigatorKey: navigatorKey,
      theme: EnhancedTheme.enhancedLightTheme,
      darkTheme: EnhancedTheme.enhancedDarkTheme,
      themeMode: themeMode,
      builder: (context, child) => InactivityWatcher(
        onTimeout: _logoutOnIdle,
        child: child ?? const SizedBox.shrink(),
      ),
      home: api.isLoggedIn ? const HomeScreen() : const LoginScreen(),
    );
  }

  Future<void> _logoutOnIdle() async {
    if (!api.isLoggedIn) return; // already logged out, nothing to do
    await api.logout();
    navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }
}
