import "package:go_router/go_router.dart";

import "../features/ai/ai_assistant_screen.dart";
import "../features/appointments/booking_screen.dart";
import "../features/appointments/my_appointments_screen.dart";
import "../features/auth/login_screen.dart";
import "../features/auth/language_screen.dart";
import "../features/doctors/doctor_profile_screen.dart";
import "../features/doctors/doctor_search_screen.dart";
import "../features/emergency/emergency_screens.dart";
import "../features/emergency/sos_screen.dart";
import "../features/family/family_screens.dart";
import "../features/home/home_screen.dart";
import "../features/hospitals/hospital_search_screen.dart";
import "../features/medicines/medicine_detail_screen.dart";
import "../features/medicines/medicine_search_screen.dart";
import "../features/medicines/order_screen.dart";
import "../features/pharmacies/pharmacy_search_screen.dart";
import "../features/profile/settings_screen.dart";
import "../features/specialties/specialty_list_screen.dart";
import "../features/specialties/specialty_placeholder_screen.dart";
import "../features/vault/vault_home_screen.dart";
import "../features/vault/vault_record_detail_screen.dart";

/// Route names/paths mirror the backend AI navigation routes (spec §11).
class AppRoutes {
  static const login = "/login";
  static const language = "/language";
  static const home = "/";
  static const ai = "/ai";
  static const emergency = "/emergency";
  static const specialties = "/specialties";
  static String specialty(String slug) => "/specialties/$slug";
  static const doctors = "/doctors";
  static String doctorProfile(String id) => "/doctors/$id";
  static const hospitals = "/hospitals";
  static String booking(String doctorId, String serviceId) =>
      "/book?doctorId=$doctorId&serviceId=$serviceId";
  static const myAppointments = "/appointments";
  static const medicines = "/medicines";
  static String medicineDetail(String id) => "/medicines/$id";
  static String order(String medicineId) => "/order?medicineId=$medicineId";
  static const myOrders = "/orders";
  static const pharmacies = "/pharmacies";
  static const family = "/family";
  static const familyAccess = "/family/access";
  static const emergency = "/emergency";
  static const emergencyActive = "/emergency/active";
  static const emergencyContacts = "/emergency/contacts";
  static const emergencyProfile = "/emergency/profile";
  static const emergencyHospitals = "/emergency/hospitals";
  static const emergencyHistory = "/emergency/history";
  static const emergencyHandoff = "/emergency/handoff";
  static const vault = "/vault";
  static String vaultRecord(String id) => "/vault/$id";
  static const settings = "/settings";
}

final appRouter = GoRouter(
  initialLocation: AppRoutes.language,
  routes: [
    GoRoute(path: AppRoutes.language, builder: (c, s) => const LanguageScreen()),
    GoRoute(path: AppRoutes.login, builder: (c, s) => const LoginScreen()),
    GoRoute(path: AppRoutes.home, builder: (c, s) => const HomeScreen()),
    GoRoute(path: AppRoutes.ai, builder: (c, s) => const AiAssistantScreen()),
    GoRoute(path: AppRoutes.emergency, builder: (c, s) => const EmergencyHomeScreen()),
    GoRoute(path: AppRoutes.emergencyActive, builder: (c, s) => const SOSActiveScreen()),
    GoRoute(path: AppRoutes.emergencyContacts, builder: (c, s) => const EmergencyContactsScreen()),
    GoRoute(path: AppRoutes.emergencyProfile, builder: (c, s) => const EmergencyProfileScreen()),
    GoRoute(
      path: AppRoutes.emergencyHospitals,
      builder: (c, s) => const NearbyEmergencyHospitalsScreen(),
    ),
    GoRoute(path: AppRoutes.emergencyHistory, builder: (c, s) => const EmergencyHistoryScreen()),
    GoRoute(
      path: AppRoutes.emergencyHandoff,
      builder: (c, s) =>
          EmergencyHandoffScreen(eventId: s.uri.queryParameters["id"] ?? ""),
    ),
    GoRoute(path: AppRoutes.specialties, builder: (c, s) => const SpecialtyListScreen()),
    GoRoute(
      path: "/specialties/:slug",
      builder: (c, s) => SpecialtyPlaceholderScreen(slug: s.pathParameters["slug"] ?? ""),
    ),
    GoRoute(
      path: AppRoutes.doctors,
      builder: (c, s) => DoctorSearchScreen(specialty: s.uri.queryParameters["specialty"]),
    ),
    GoRoute(
      path: "/doctors/:id",
      builder: (c, s) => DoctorProfileScreen(doctorId: s.pathParameters["id"] ?? ""),
    ),
    GoRoute(
      path: AppRoutes.hospitals,
      builder: (c, s) => HospitalSearchScreen(specialty: s.uri.queryParameters["specialty"]),
    ),
    GoRoute(
      path: "/book",
      builder: (c, s) => BookingScreen(
        doctorId: s.uri.queryParameters["doctorId"] ?? "",
        serviceId: s.uri.queryParameters["serviceId"] ?? "",
      ),
    ),
    GoRoute(path: AppRoutes.myAppointments, builder: (c, s) => const MyAppointmentsScreen()),
    GoRoute(path: AppRoutes.medicines, builder: (c, s) => const MedicineSearchScreen()),
    GoRoute(
      path: "/medicines/:id",
      builder: (c, s) => MedicineDetailScreen(medicineId: s.pathParameters["id"] ?? ""),
    ),
    GoRoute(
      path: "/order",
      builder: (c, s) => OrderScreen(medicineId: s.uri.queryParameters["medicineId"] ?? ""),
    ),
    GoRoute(path: AppRoutes.myOrders, builder: (c, s) => const MyOrdersScreen()),
    GoRoute(path: AppRoutes.pharmacies, builder: (c, s) => const PharmacySearchScreen()),
    GoRoute(path: AppRoutes.family, builder: (c, s) => const MyFamilyScreen()),
    GoRoute(path: AppRoutes.familyAccess, builder: (c, s) => const FamilyAccessScreen()),
    GoRoute(path: AppRoutes.vault, builder: (c, s) => const VaultHomeScreen()),
    GoRoute(
      path: "/vault/:id",
      builder: (c, s) =>
          VaultRecordDetailScreen(recordId: s.pathParameters["id"] ?? ""),
    ),
    GoRoute(path: AppRoutes.settings, builder: (c, s) => const SettingsScreen()),
  ],
);
