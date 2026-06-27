// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Health Info';

  @override
  String get signIn => 'Sign in';

  @override
  String get register => 'Register';

  @override
  String get signOut => 'Sign out';

  @override
  String get phoneLabel => 'Phone';

  @override
  String get passwordLabel => 'Password';

  @override
  String get usernameLabel => 'Username';

  @override
  String get search => 'Search';

  @override
  String get retry => 'Retry';

  @override
  String get cancel => 'Cancel';

  @override
  String get save => 'Save';

  @override
  String get settings => 'Settings';

  @override
  String get somethingWentWrong => 'Something went wrong';

  @override
  String get noMatches => 'No matches';

  @override
  String get language => 'Language';

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
