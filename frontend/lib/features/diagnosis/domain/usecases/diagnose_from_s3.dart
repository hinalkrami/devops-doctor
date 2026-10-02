import '../entities/diagnosis.dart';
import '../repositories/diagnosis_repository.dart';

/// Use case: diagnose a log file already uploaded to S3.
///
/// Calls `POST /diagnose` with `{ "log_key": "..." }`.
class DiagnoseFromS3 {
  const DiagnoseFromS3(this._repository);

  final DiagnosisRepository _repository;

  Future<Diagnosis> call(String logKey) =>
      _repository.diagnoseFromS3(logKey);
}
