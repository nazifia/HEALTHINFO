// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Yoruba (`yo`).
class AppLocalizationsYo extends AppLocalizations {
  AppLocalizationsYo([String locale = 'yo']) : super(locale);

  @override
  String get appTitle => 'Ìfitónilétí Ìlera';

  @override
  String get signIn => 'Wọlé';

  @override
  String get register => 'Forúkọsílẹ̀';

  @override
  String get signOut => 'Jáde';

  @override
  String get phoneLabel => 'Fóònù';

  @override
  String get passwordLabel => 'Ọ̀rọ̀ aṣínà';

  @override
  String get usernameLabel => 'Orúkọ olùmúlò';

  @override
  String get search => 'Wá';

  @override
  String get retry => 'Túndánwò';

  @override
  String get cancel => 'Fagilé';

  @override
  String get save => 'Fipamọ́';

  @override
  String get settings => 'Ètò';

  @override
  String get somethingWentWrong => 'Nǹkan kan ṣàṣìṣe';

  @override
  String get noMatches => 'Kò sí àbájáde';

  @override
  String get language => 'Èdè';

  @override
  String get systemDefault => 'System default';

  @override
  String get langEnglish => 'English';

  @override
  String get langHausa => 'Hausa';

  @override
  String get langYoruba => 'Yorùbá';

  @override
  String get langIgbo => 'Igbo';

  @override
  String get askHint => 'Ask a health question…';

  @override
  String get semanticSearchHint => 'Search by meaning…';

  @override
  String get selectSymptoms => 'Select symptoms';

  @override
  String get selectSymptomsHint => 'Diseases are ranked by how many you pick.';

  @override
  String findDiseases(int count) {
    return 'Find diseases ($count selected)';
  }

  @override
  String get possibleConditions => 'Possible conditions';

  @override
  String get selectMedications => 'Select medications';

  @override
  String get selectMedicationsHint =>
      'Pick at least two to check for conflicts.';

  @override
  String checkInteractions(int count) {
    return 'Check ($count selected)';
  }

  @override
  String interactionsFound(int count) {
    return 'Interactions found ($count)';
  }

  @override
  String get noKnownInteractions => 'No known interactions';

  @override
  String get medicalDisclaimer =>
      'For information only. Not a substitute for professional medical advice.';
}
