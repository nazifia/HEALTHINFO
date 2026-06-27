// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Igbo (`ig`).
class AppLocalizationsIg extends AppLocalizations {
  AppLocalizationsIg([String locale = 'ig']) : super(locale);

  @override
  String get appTitle => 'Ozi Ahụike';

  @override
  String get signIn => 'Banye';

  @override
  String get register => 'Debanye aha';

  @override
  String get signOut => 'Pụọ';

  @override
  String get phoneLabel => 'Ekwentị';

  @override
  String get passwordLabel => 'Okwuntughe';

  @override
  String get usernameLabel => 'Aha onye ọrụ';

  @override
  String get search => 'Chọọ';

  @override
  String get retry => 'Nwaa ọzọ';

  @override
  String get cancel => 'Kagbuo';

  @override
  String get save => 'Chekwaa';

  @override
  String get settings => 'Ntọala';

  @override
  String get somethingWentWrong => 'Ihe adịghị mma mere';

  @override
  String get noMatches => 'Enweghị nsonaazụ';

  @override
  String get language => 'Asụsụ';

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
