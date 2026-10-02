import '../repositories/diagnosis_repository.dart';

/// Use case: PUT raw bytes to a presigned S3 URL.
///
/// This is a direct S3 PUT — it does not go through API Gateway or Lambda.
class UploadFile {
  const UploadFile(this._repository);

  final DiagnosisRepository _repository;

  Future<void> call(String uploadUrl, List<int> bytes) =>
      _repository.uploadFile(uploadUrl, bytes);
}
