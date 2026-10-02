/// Application-wide non-API constants.
class AppConstants {
  AppConstants._();

  /// Maximum log file size the client will accept before upload (10 MB).
  static const int maxFileSizeBytes = 10 * 1024 * 1024;

  /// Default number of history records to fetch.
  static const int historyDefaultLimit = 20;
}
