import 'package:intl/intl.dart';

/// Formats ISO 8601 timestamps for display in the history list.
abstract final class DateFormatter {
  static final DateFormat _fmt = DateFormat('MMM d, yyyy · HH:mm');

  /// Returns a human-readable string from an ISO 8601 [timestamp].
  /// Falls back to the raw string if parsing fails.
  static String format(String timestamp) {
    try {
      final dt = DateTime.parse(timestamp).toLocal();
      return _fmt.format(dt);
    } catch (_) {
      return timestamp;
    }
  }
}
