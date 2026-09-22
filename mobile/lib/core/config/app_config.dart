/// Environment config. Real values come from --dart-define at build time
/// (e.g. --dart-define=MEDISAVE_API_BASE_URL=https://api.medisave.example).
/// Never hardcode production credentials (spec §2.26-27).
class AppConfig {
  static const apiBaseUrl = String.fromEnvironment(
    "MEDISAVE_API_BASE_URL",
    defaultValue: "http://10.0.2.2:8000", // Android emulator -> host loopback
  );
  static const demoMode = bool.fromEnvironment("MEDISAVE_DEMO_MODE", defaultValue: true);
}
