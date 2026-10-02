import '../entities/diagnosis.dart';
import '../entities/upload_url.dart';

/// Abstract interface for all diagnosis-related data operations.
/// Implementations live in `data/repositories/`.
/// Domain code must depend only on this interface — never on the impl.
abstract class DiagnosisRepository {
  /// Sends an inline log string to `POST /diagnose` and returns the result.
  Future<Diagnosis> diagnoseLog(String log);

  /// Sends a previously uploaded S3 key to `POST /diagnose` and returns the result.
  Future<Diagnosis> diagnoseFromS3(String logKey);

  /// Calls `GET /upload-url?filename=<filename>` and returns the presigned URL.
  Future<UploadUrl> getUploadUrl(String filename);

  /// PUTs [bytes] directly to the presigned S3 [uploadUrl].
  Future<void> uploadFile(String uploadUrl, List<int> bytes);
}
