// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hausa (`ha`).
class AppLocalizationsHa extends AppLocalizations {
  AppLocalizationsHa([String locale = 'ha']) : super(locale);

  @override
  String get appTitle => 'Bayanin Lafiya';

  @override
  String get signIn => 'Shiga';

  @override
  String get register => 'Yi rajista';

  @override
  String get signOut => 'Fita';

  @override
  String get phoneLabel => 'Lambar waya';

  @override
  String get passwordLabel => 'Kalmar sirri';

  @override
  String get usernameLabel => 'Sunan mai amfani';

  @override
  String get search => 'Bincika';

  @override
  String get retry => 'Sake gwadawa';

  @override
  String get cancel => 'Soke';

  @override
  String get save => 'Ajiye';

  @override
  String get settings => 'Saiti';

  @override
  String get somethingWentWrong => 'Wani abu ya faskara';

  @override
  String get noMatches => 'Babu sakamako';

  @override
  String get language => 'Harshe';

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
