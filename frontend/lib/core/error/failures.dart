/// Sealed hierarchy of typed failures.
/// Domain and presentation layers use these instead of raw exceptions.
sealed class Failure {
  const Failure(this.message);
  final String message;
}

/// HTTP / connectivity errors talking to API Gateway.
final class NetworkFailure extends Failure {
  const NetworkFailure([super.message = 'Network error. Check your connection.']);
}

/// Non-2xx HTTP status returned by the API (400, 401, 429, 502, 504, …).
final class ServerFailure extends Failure {
  const ServerFailure(super.message, {this.statusCode});
  final int? statusCode;
}

/// S3 presigned PUT failed.
final class UploadFailure extends Failure {
  const UploadFailure([super.message = 'File upload failed. Please try again.']);
}

/// Selected file exceeds the client-side size limit.
final class FileTooLargeFailure extends Failure {
  const FileTooLargeFailure([super.message = 'File exceeds the 10 MB limit.']);
}

/// User submitted an empty log text.
final class EmptyInputFailure extends Failure {
  const EmptyInputFailure(
      [super.message = 'Please paste a log or upload a file first.']);
}
