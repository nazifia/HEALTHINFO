import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Locales the app ships translations for. `null` state = follow the device.
const supportedLocales = [
  Locale('en'),
  Locale('ha'),
  Locale('yo'),
  Locale('ig'),
];

class LocaleNotifier extends StateNotifier<Locale?> {
  LocaleNotifier(super.initial);

  static const _key = 'locale';

  Future<void> setLocale(Locale? locale) async {
    state = locale;
    final prefs = await SharedPreferences.getInstance();
    if (locale == null) {
      await prefs.remove(_key);
    } else {
      await prefs.setString(_key, locale.languageCode);
    }
  }

  /// Read the saved code at startup; unknown/missing → device default (null).
  static Locale? fromPrefs(SharedPreferences prefs) {
    final code = prefs.getString(_key);
    if (code == null) return null;
    return supportedLocales.firstWhere(
      (l) => l.languageCode == code,
      orElse: () => const Locale('en'),
    );
  }
}

final localeProvider =
    StateNotifierProvider<LocaleNotifier, Locale?>((ref) => LocaleNotifier(null));
