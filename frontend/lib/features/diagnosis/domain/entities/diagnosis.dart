/// Pure Dart domain entity representing a completed AI diagnosis.
/// No Flutter, http, Riverpod, or JSON imports allowed here.
class Diagnosis {
  const Diagnosis({
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
}
