import 'package:flutter/material.dart';

/// One catalog type (disease, medication, …) described by data, not code.
/// Adding a new tab = add a CatalogResource below, no new screen class.
class CatalogResource {
  final String label;
  final IconData icon;
  final String path; // API list path, e.g. /api/diseases/
  final String titleField; // row -> list/detail title
  final String? subtitleLabel; // prefix for the list subtitle
  final String? subtitleField; // row -> list subtitle value
  final List<({String key, String heading})> sections; // detail body
  // M2M id-list fields to render as tappable links to another resource.
  final List<({String key, String heading, String path})> links;

  const CatalogResource({
    required this.label,
    required this.icon,
    required this.path,
    required this.titleField,
    this.subtitleLabel,
    this.subtitleField,
    required this.sections,
    this.links = const [],
  });
}

CatalogResource? resourceByPath(String path) {
  for (final r in catalogResources) {
    if (r.path == path) return r;
  }
  return null;
}

/// Catalog list paths that have a `/api/graph/<kind>/<id>/` relationship view.
const _graphKinds = {
  '/api/diseases/': 'diseases',
  '/api/medications/': 'medications',
  '/api/procedures/': 'procedures',
  '/api/specialties/': 'specialties',
};

/// Graph endpoint for a record, or null if this resource has no graph view.
String? graphPath(String resourcePath, Object? id) {
  final kind = _graphKinds[resourcePath];
  if (kind == null || id == null) return null;
  return '/api/graph/$kind/$id/';
}

const catalogResources = <CatalogResource>[
  CatalogResource(
    label: 'Diseases',
    icon: Icons.coronavirus_outlined,
    path: '/api/diseases/',
    titleField: 'name',
    subtitleLabel: 'ICD-10',
    subtitleField: 'icd10_code',
    sections: [
      (key: 'description', heading: 'Description'),
      (key: 'causes', heading: 'Causes'),
      (key: 'risk_factors', heading: 'Risk factors'),
      (key: 'diagnosis', heading: 'Diagnosis'),
      (key: 'treatment', heading: 'Treatment'),
      (key: 'prevention', heading: 'Prevention'),
      (key: 'complications', heading: 'Complications'),
      (key: 'references', heading: 'References'),
    ],
    links: [
      (key: 'symptoms', heading: 'Symptoms', path: '/api/symptoms/'),
      (key: 'medications', heading: 'Medications', path: '/api/medications/'),
    ],
  ),
  CatalogResource(
    label: 'Medications',
    icon: Icons.medication_outlined,
    path: '/api/medications/',
    titleField: 'generic_name',
    subtitleLabel: 'Brand',
    subtitleField: 'brand_name',
    sections: [
      (key: 'drug_class', heading: 'Drug class'),
      (key: 'description', heading: 'Description'),
      (key: 'indications', heading: 'Indications'),
      (key: 'dosage', heading: 'Dosage'),
      (key: 'side_effects', heading: 'Side effects'),
      (key: 'warnings', heading: 'Warnings'),
      (key: 'contraindications', heading: 'Contraindications'),
      (key: 'storage_information', heading: 'Storage'),
    ],
  ),
  CatalogResource(
    label: 'Symptoms',
    icon: Icons.sick_outlined,
    path: '/api/symptoms/',
    titleField: 'name',
    subtitleLabel: 'Severity',
    subtitleField: 'severity_level',
    sections: [
      (key: 'description', heading: 'Description'),
      (key: 'severity_level', heading: 'Severity (1=mild .. 5=severe)'),
    ],
  ),
  CatalogResource(
    label: 'Procedures',
    icon: Icons.healing_outlined,
    path: '/api/procedures/',
    titleField: 'name',
    sections: [
      (key: 'description', heading: 'Description'),
      (key: 'indications', heading: 'Indications'),
      (key: 'preparation', heading: 'Preparation'),
      (key: 'risks', heading: 'Risks'),
      (key: 'recovery', heading: 'Recovery'),
      (key: 'references', heading: 'References'),
    ],
  ),
  CatalogResource(
    label: 'Lab tests',
    icon: Icons.science_outlined,
    path: '/api/lab-tests/',
    titleField: 'name',
    subtitleLabel: 'Normal range',
    subtitleField: 'normal_range',
    sections: [
      (key: 'description', heading: 'Description'),
      (key: 'purpose', heading: 'Purpose'),
      (key: 'preparation', heading: 'Preparation'),
      (key: 'normal_range', heading: 'Normal range'),
      (key: 'units', heading: 'Units'),
      (key: 'references', heading: 'References'),
    ],
  ),
  CatalogResource(
    label: 'Articles',
    icon: Icons.article_outlined,
    path: '/api/articles/',
    titleField: 'title',
    sections: [
      (key: 'summary', heading: 'Summary'),
      (key: 'body', heading: 'Body'),
      (key: 'references', heading: 'References'),
    ],
  ),
  CatalogResource(
    label: 'Specialties',
    icon: Icons.local_hospital_outlined,
    path: '/api/specialties/',
    titleField: 'name',
    sections: [
      (key: 'description', heading: 'Description'),
    ],
  ),
];
