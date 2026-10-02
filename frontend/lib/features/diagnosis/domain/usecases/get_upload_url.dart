import '../entities/upload_url.dart';
import '../repositories/diagnosis_repository.dart';

/// Use case: obtain a presigned S3 PUT URL for a given filename.
///
/// Calls `GET /upload-url?filename=<filename>`.
class GetUploadUrl {
  const GetUploadUrl(this._repository);

  final DiagnosisRepository _repository;

  Future<UploadUrl> call(String filename) =>
      _repository.getUploadUrl(filename);
}
