import '../entities/diagnosis.dart';
import '../repositories/diagnosis_repository.dart';

/// Use case: diagnose an inline log string.
///
/// Calls `POST /diagnose` with `{ "log": "..." }`.
class DiagnoseLog {
  const DiagnoseLog(this._repository);

  final DiagnosisRepository _repository;

  Future<Diagnosis> call(String log) => _repository.diagnoseLog(log);
}
