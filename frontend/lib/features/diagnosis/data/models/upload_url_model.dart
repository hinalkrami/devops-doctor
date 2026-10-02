import '../../domain/entities/upload_url.dart';

/// JSON data model for the `GET /upload-url` response.
///
/// Live API shape:
/// ```json
/// {
///   "status": "success",
///   "upload_url": "https://s3.eu-central-1.amazonaws.com/...",
///   "log_key": "logs/2026-10-02/uuid-filename.log",
///   "expires_in": 300
/// }
/// ```
class UploadUrlModel {
  const UploadUrlModel({
    required this.uploadUrl,
    required this.logKey,
    required this.expiresIn,
  });

  final String uploadUrl;
  final String logKey;
  final int expiresIn;

  factory UploadUrlModel.fromJson(Map<String, dynamic> json) =>
      UploadUrlModel(
        uploadUrl: json['upload_url'] as String,
        logKey: json['log_key'] as String,
        expiresIn: (json['expires_in'] as num).toInt(),
      );

  UploadUrl toEntity() => UploadUrl(
        uploadUrl: uploadUrl,
        logKey: logKey,
        expiresIn: expiresIn,
      );
}
