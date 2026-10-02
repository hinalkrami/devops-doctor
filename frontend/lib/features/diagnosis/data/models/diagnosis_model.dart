import '../../domain/entities/diagnosis.dart';

/// JSON data model for the `POST /diagnose` response.
///
/// Live API shape (confirmed):
/// ```json
/// {
///   "status": "success",
///   "model": "qwen.qwen3-32b",
///   "diagnosis_id": "f0d0a7bd-...",
///   "diagnosis": {
///     "problem": "...",
///     "root_cause": "...",
///     "evidence": "...",
///     "explanation": "...",
///     "recommended_fix": "...",
///     "kubectl_commands": ["...", "..."],
///     "prevention": "..."
///   }
/// }
/// ```
class DiagnosisModel {
  const DiagnosisModel({
    required this.diagnosisId,
    required this.model,
    required this.problem,
    required this.rootCause,
    required this.evidence,
    required this.explanation,
    required this.recommendedFix,
    required this.kubectlCommands,
    required this.prevention,
  });

  final String diagnosisId;
  final String model;
  final String problem;
  final String rootCause;
  final String evidence;
  final String explanation;
  final String recommendedFix;
  final List<String> kubectlCommands;
  final String prevention;

  /// Parses the top-level API response map.
  /// The 7 diagnosis fields are nested under the `"diagnosis"` key.
  factory DiagnosisModel.fromJson(Map<String, dynamic> json) {
    final d = json['diagnosis'] as Map<String, dynamic>;

    final rawCommands = d['kubectl_commands'];
    final List<String> commands;
    if (rawCommands is List) {
      commands = rawCommands.map((e) => e.toString()).toList();
    } else if (rawCommands is String) {
      // Fallback: model returned a newline-separated string.
      commands = rawCommands
          .split('\n')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList();
    } else {
      commands = const [];
    }

    return DiagnosisModel(
      diagnosisId: json['diagnosis_id'] as String? ?? '',
      model: json['model'] as String? ?? '',
      problem: d['problem'] as String? ?? '',
      rootCause: d['root_cause'] as String? ?? '',
      evidence: d['evidence'] as String? ?? '',
      explanation: d['explanation'] as String? ?? '',
      recommendedFix: d['recommended_fix'] as String? ?? '',
      kubectlCommands: commands,
      prevention: d['prevention'] as String? ?? '',
    );
  }

  /// Converts this data model to the domain entity.
  Diagnosis toEntity() => Diagnosis(
        diagnosisId: diagnosisId,
        model: model,
        problem: problem,
        rootCause: rootCause,
        evidence: evidence,
        explanation: explanation,
        recommendedFix: recommendedFix,
        kubectlCommands: kubectlCommands,
        prevention: prevention,
      );
}
