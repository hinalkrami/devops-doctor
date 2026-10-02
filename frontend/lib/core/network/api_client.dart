import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../constants/api_constants.dart';
import '../error/failures.dart';

/// Thin HTTP wrapper.
/// All calls to API Gateway and S3 go through here.
/// Never import `http` directly from feature code.
class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  // ---------------------------------------------------------------------------
  // GET
  // ---------------------------------------------------------------------------

  /// Performs a GET against [path] (relative to [ApiConstants.baseUrl]).
  /// Returns the decoded JSON body on success.
  /// Throws [ServerFailure] for non-2xx, [NetworkFailure] on connectivity issues.
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? queryParams,
  }) async {
    final uri = Uri.parse(ApiConstants.baseUrl + path).replace(
      queryParameters: queryParams,
    );
    try {
      final response = await _client.get(
        uri,
        headers: {'Content-Type': 'application/json'},
      );
      return _handleResponse(response);
    } on SocketException {
      throw const NetworkFailure();
    } on http.ClientException {
      throw const NetworkFailure();
    }
  }

  // ---------------------------------------------------------------------------
  // POST
  // ---------------------------------------------------------------------------

  /// Performs a POST against [path] (relative to [ApiConstants.baseUrl]).
  Future<Map<String, dynamic>> post(
    String path, {
    required Map<String, dynamic> body,
  }) async {
    final uri = Uri.parse(ApiConstants.baseUrl + path);
    try {
      final response = await _client.post(
        uri,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
      return _handleResponse(response);
    } on SocketException {
      throw const NetworkFailure();
    } on http.ClientException {
      throw const NetworkFailure();
    }
  }

  // ---------------------------------------------------------------------------
  // PUT (raw bytes – for S3 presigned URLs)
  // ---------------------------------------------------------------------------

  /// PUTs raw [bytes] to a full [url] (not relative — used for S3 presigned URLs).
  /// Throws [UploadFailure] on non-2xx, [NetworkFailure] on connectivity issues.
  Future<void> putRaw(String url, List<int> bytes) async {
    final uri = Uri.parse(url);
    try {
      final response = await _client.put(
        uri,
        headers: {'Content-Type': 'text/plain'},
        body: bytes,
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw UploadFailure(
          'S3 upload failed with status ${response.statusCode}.',
        );
      }
    } on SocketException {
      throw const NetworkFailure();
    } on http.ClientException {
      throw const NetworkFailure();
    } on UploadFailure {
      rethrow;
    }
  }

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  Map<String, dynamic> _handleResponse(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }
    // Try to extract the `message` field from the error body.
    String message = 'Server error (${response.statusCode}).';
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      if (body['message'] != null) {
        message = body['message'] as String;
      }
    } catch (_) {}
    throw ServerFailure(message, statusCode: response.statusCode);
  }
}
