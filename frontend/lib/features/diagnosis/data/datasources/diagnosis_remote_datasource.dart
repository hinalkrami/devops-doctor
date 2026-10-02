import '../../../../core/constants/api_constants.dart';
import '../../../../core/network/api_client.dart';
import '../models/diagnosis_model.dart';
import '../models/upload_url_model.dart';

/// Remote data source for all diagnosis-related API calls.
/// Knows the exact URL paths, HTTP verbs, and JSON shapes.
/// Returns data models — never domain entities.
class DiagnosisRemoteDatasource {
  const DiagnosisRemoteDatasource(this._client);

  final ApiClient _client;

  /// POST /diagnose with inline log text.
  Future<DiagnosisModel> postDiagnoseInline(String log) async {
    final json = await _client.post(
      ApiConstants.diagnose,
      body: {'log': log},
    );
    return DiagnosisModel.fromJson(json);
  }

  /// POST /diagnose with an S3 log key.
  Future<DiagnosisModel> postDiagnoseFromS3(String logKey) async {
    final json = await _client.post(
      ApiConstants.diagnose,
      body: {'log_key': logKey},
    );
    return DiagnosisModel.fromJson(json);
  }

  /// GET /upload-url?filename=<filename>
  Future<UploadUrlModel> getUploadUrl(String filename) async {
    final json = await _client.get(
      ApiConstants.uploadUrl,
      queryParams: {'filename': filename},
    );
    return UploadUrlModel.fromJson(json);
  }

  /// PUT raw bytes directly to the presigned S3 URL.
  Future<void> uploadFile(String uploadUrl, List<int> bytes) =>
      _client.putRaw(uploadUrl, bytes);
}
