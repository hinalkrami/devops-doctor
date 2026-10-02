import 'package:flutter/material.dart';

/// DevOps dashboard colour palette.
/// Dark theme inspired by AWS Console / terminal tooling.
abstract final class AppColors {
  // Backgrounds
  static const Color background = Color(0xFF0D1117);
  static const Color surface = Color(0xFF161B22);
  static const Color surfaceElevated = Color(0xFF1C2128);
  static const Color border = Color(0xFF30363D);

  // AWS brand
  static const Color awsOrange = Color(0xFFFF9900);
  static const Color awsOrangeDim = Color(0xFFB36B00);

  // Status
  static const Color success = Color(0xFF3FB950);
  static const Color error = Color(0xFFF85149);
  static const Color warning = Color(0xFFD29922);
  static const Color info = Color(0xFF58A6FF);

  // Text
  static const Color textPrimary = Color(0xFFE6EDF3);
  static const Color textSecondary = Color(0xFF8B949E);
  static const Color textMuted = Color(0xFF484F58);

  // Monospace / terminal
  static const Color codeBackground = Color(0xFF010409);
  static const Color codeText = Color(0xFF79C0FF);
}
