import "package:flutter/material.dart";

/// Official MediSave AI brand colors (spec §27).
class Brand {
  static const teal = Color(0xFF2BC0A4);
  static const aiPurple = Color(0xFF6B5CFF);
  static const blue = Color(0xFF2563EB);
  static const background = Color(0xFFF7FAFC);
  static const darkText = Color(0xFF172033);
}

ThemeData buildMedisaveTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Brand.teal,
      primary: Brand.teal,
      secondary: Brand.aiPurple,
      surface: Colors.white,
      error: const Color(0xFFDC2626),
    ),
    scaffoldBackgroundColor: Brand.background,
    fontFamily: "Poppins",
  );

  return base.copyWith(
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.white,
      foregroundColor: Brand.darkText,
      elevation: 0,
      centerTitle: false,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: Brand.teal,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(52), // large touch target (spec §44)
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(0xFFD5DCE8)),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
  );
}
