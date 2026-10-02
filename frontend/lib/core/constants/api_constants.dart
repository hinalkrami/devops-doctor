/// All API Gateway endpoint constants.
/// No URL strings should appear anywhere else in the codebase.
class ApiConstants {
  ApiConstants._();

  static const String baseUrl =
      'https://j2lmkn9he0.execute-api.eu-central-1.amazonaws.com';

  static const String diagnose = '/diagnose';
  static const String history = '/history';
  static const String uploadUrl = '/upload-url';
}
