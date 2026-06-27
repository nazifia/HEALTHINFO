import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

// ponytail: Flutter's flutter_localizations ships no Material/Cupertino data for
// ha/ig/yo, so those locales throw "No MaterialLocalizations found". These
// delegates serve English data for any locale, as a last-resort fallback.
// Append AFTER AppLocalizations.localizationsDelegates so real translations win.

const _en = Locale('en');

class FallbackMaterialDelegate
    extends LocalizationsDelegate<MaterialLocalizations> {
  const FallbackMaterialDelegate();
  @override
  bool isSupported(Locale locale) => true;
  @override
  Future<MaterialLocalizations> load(Locale locale) =>
      GlobalMaterialLocalizations.delegate.load(_en);
  @override
  bool shouldReload(FallbackMaterialDelegate old) => false;
}

class FallbackCupertinoDelegate
    extends LocalizationsDelegate<CupertinoLocalizations> {
  const FallbackCupertinoDelegate();
  @override
  bool isSupported(Locale locale) => true;
  @override
  Future<CupertinoLocalizations> load(Locale locale) =>
      GlobalCupertinoLocalizations.delegate.load(_en);
  @override
  bool shouldReload(FallbackCupertinoDelegate old) => false;
}
