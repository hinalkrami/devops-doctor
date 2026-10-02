/// Pure Dart domain entity representing a presigned S3 upload URL.
class UploadUrl {
  const UploadUrl({
    required this.uploadUrl,
    required this.logKey,
    required this.expiresIn,
  });

  /// The full presigned S3 PUT URL.
  final String uploadUrl;

  /// The S3 object key (e.g. `logs/2026-10-02/uuid-filename.log`).
  /// Pass this to `POST /diagnose` as `log_key`.
  final String logKey;

  /// Seconds until the presigned URL expires.
  final int expiresIn;
}
