/** Axios API client with JWT header injection and 401 handling. */
import axios from "axios";

export const api = axios.create({ baseURL: "/api/v1" });

const TOKEN_KEY = "medisave_admin_token";

export function setToken(token: string | null) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
  api.defaults.headers.common["Authorization"] = token ? `Bearer ${token}` : "";
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      setToken(null);
    }
    return Promise.reject(error);
  }
);

export interface Me {
  id: string;
  full_name: string;
  email: string;
  roles: string[];
}

export interface AuditLogRow {
  id: string;
  actor_user_id: string | null;
  actor_role: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  created_at: string;
}

export interface FeatureFlagRow {
  key: string;
  description: string;
  is_enabled: boolean;
}

export async function login(email: string, password: string): Promise<Me> {
  const resp = await api.post<{ access_token: string }>("/auth/login", { email, password });
  setToken(resp.data.access_token);
  const me = await api.get<Me>("/auth/me");
  return me.data;
}

export async function fetchMe(): Promise<Me | null> {
  try {
    const resp = await api.get<Me>("/auth/me");
    return resp.data;
  } catch {
    return null;
  }
}

export async function fetchAuditLogs(): Promise<AuditLogRow[]> {
  const resp = await api.get<AuditLogRow[]>("/admin/audit-logs");
  return resp.data;
}

export async function fetchFeatureFlags(): Promise<FeatureFlagRow[]> {
  const resp = await api.get<FeatureFlagRow[]>("/feature-flags");
  return resp.data;
}

export async function updateFeatureFlag(key: string, is_enabled: boolean): Promise<FeatureFlagRow> {
  const resp = await api.patch<FeatureFlagRow>(`/feature-flags/${key}`, { is_enabled });
  return resp.data;
}

export async function fetchUsers(): Promise<Me[]> {
  const resp = await api.get<Me[]>("/admin/users");
  return resp.data;
}

// ---- Phase 3: providers, verification, appointments ----

export interface DoctorRow {
  id: string;
  full_name: string;
  specialty_slug: string;
  qualifications: string;
  registration_number?: string;
  registration_council?: string;
  city: string | null;
  verification_status: string;
}

export interface HospitalRow {
  id: string;
  name: string;
  hospital_type: string;
  city: string | null;
  emergency_available: boolean;
  emergency_verified: boolean;
  verification_status: string;
}

export interface VerificationHistoryRow {
  previous_status: string;
  new_status: string;
  decided_by_user_id: string | null;
  decision_note: string;
  created_at: string;
}

export interface SpecialtyRow {
  slug: string;
  name_en: string;
  name_te: string;
  name_hi: string;
  icon: string;
}

export interface AppointmentRow {
  id: string;
  patient_user_id: string;
  doctor_id: string;
  specialty_slug: string;
  appointment_date: string;
  appointment_time: string;
  consultation_type: string;
  price_amount: number | null;
  price_verified: boolean;
  status: string;
}

export async function fetchDoctorQueue(status?: string): Promise<DoctorRow[]> {
  const resp = await api.get<DoctorRow[]>("/admin/verifications/doctors", {
    params: status ? { status } : undefined,
  });
  return resp.data;
}

export async function fetchHospitalQueue(status?: string): Promise<HospitalRow[]> {
  const resp = await api.get<HospitalRow[]>("/admin/verifications/hospitals", {
    params: status ? { status } : undefined,
  });
  return resp.data;
}

export async function decideDoctor(doctorId: string, newStatus: string, note: string): Promise<DoctorRow> {
  const resp = await api.post<DoctorRow>(`/admin/verifications/doctors/${doctorId}/decision`, {
    new_status: newStatus,
    decision_note: note,
  });
  return resp.data;
}

export async function decideHospital(hospitalId: string, newStatus: string, note: string): Promise<HospitalRow> {
  const resp = await api.post<HospitalRow>(`/admin/verifications/hospitals/${hospitalId}/decision`, {
    new_status: newStatus,
    decision_note: note,
  });
  return resp.data;
}

export async function fetchDoctorHistory(doctorId: string): Promise<VerificationHistoryRow[]> {
  const resp = await api.get<VerificationHistoryRow[]>(
    `/admin/verifications/doctors/${doctorId}/history`
  );
  return resp.data;
}

export async function fetchSpecialties(): Promise<SpecialtyRow[]> {
  const resp = await api.get<SpecialtyRow[]>("/specialties");
  return resp.data;
}

export async function fetchAdminAppointments(): Promise<AppointmentRow[]> {
  const resp = await api.get<AppointmentRow[]>("/admin/appointments");
  return resp.data;
}

// ---- Phase 4: medicines, pharmacies, prices, orders ----

export interface MedicineRow {
  id: string;
  name: string;
  generic_name: string;
  brand_name: string;
  manufacturer: string;
  strength: string;
  dosage_form: string;
  pack_size: string;
  prescription_required: boolean;
  status: string;
  data_source: string;
}

export interface PharmacyRow {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  address_line: string;
  phone: string | null;
  operating_hours: string;
  delivery_supported: boolean;
  pickup_supported: boolean;
  verification_status: string;
  is_active: boolean;
}

export interface PriceQueueRow {
  id: string;
  medicine_id: string;
  medicine_name: string;
  pharmacy_id: string;
  pharmacy_name: string;
  price: number;
  currency: string;
  source: string;
  submitted_at: string;
  verification_status: string;
}

export interface OrderRow {
  id: string;
  patient_id: string;
  pharmacy_id: string;
  status: string;
  subtotal: number;
  delivery_fee: number;
  total: number;
  currency: string;
  pickup_option: boolean;
  items: {
    id: string;
    medicine_id: string;
    medicine_name: string;
    quantity: number;
    unit_price: number;
    price_source: string;
    snapshot_verification_status: string;
  }[];
  created_at: string;
}

export async function fetchMedicines(q?: string): Promise<MedicineRow[]> {
  const resp = await api.get<MedicineRow[]>("/medicines", { params: q ? { q } : undefined });
  return resp.data;
}

export async function createMedicine(payload: Partial<MedicineRow>): Promise<MedicineRow> {
  const resp = await api.post<MedicineRow>("/medicines", payload);
  return resp.data;
}

export async function fetchAdminPharmacies(status?: string): Promise<PharmacyRow[]> {
  const resp = await api.get<PharmacyRow[]>("/admin/pharmacies/verification", {
    params: status ? { status } : undefined,
  });
  return resp.data;
}

export async function verifyPharmacy(pharmacyId: string): Promise<PharmacyRow> {
  const resp = await api.post<PharmacyRow>(`/admin/pharmacies/${pharmacyId}/verify`, {});
  return resp.data;
}

export async function decidePharmacy(
  pharmacyId: string,
  newStatus: string,
  note: string
): Promise<PharmacyRow> {
  const resp = await api.post<PharmacyRow>(`/admin/pharmacies/${pharmacyId}/reject`, {
    new_status: newStatus,
    decision_note: note,
  });
  return resp.data;
}

export async function suspendPharmacy(pharmacyId: string, note: string): Promise<PharmacyRow> {
  const resp = await api.post<PharmacyRow>(`/admin/pharmacies/${pharmacyId}/suspend`, {
    new_status: "SUSPENDED",
    decision_note: note,
  });
  return resp.data;
}

export async function fetchPriceQueue(status?: string): Promise<PriceQueueRow[]> {
  const resp = await api.get<PriceQueueRow[]>("/admin/prices/verification", {
    params: status ? { status } : undefined,
  });
  return resp.data;
}

export async function decidePrice(priceId: string, decision: "VERIFIED" | "REJECTED", note: string) {
  const resp = await api.post(`/admin/prices/${priceId}/decision`, { decision, note });
  return resp.data;
}

export async function fetchAdminOrders(status?: string): Promise<OrderRow[]> {
  const resp = await api.get<OrderRow[]>("/admin/orders", {
    params: status ? { status } : undefined,
  });
  return resp.data;
}

export async function expireStalePrices(): Promise<{ expired: number }> {
  const resp = await api.post<{ expired: number }>("/admin/prices/expire-stale", {});
  return resp.data;
}

// ---- Phase 5: Health Vault governance (aggregate metrics only — no content) ----

export interface VaultEventRow {
  id: string;
  action: string;
  result: string;
  created_at: string;
}

export interface VaultOverview {
  records: number;
  stored_files: number;
  storage_bytes: number;
  active_shares: number;
  recent_events: VaultEventRow[];
}

export async function fetchVaultOverview(): Promise<VaultOverview> {
  const resp = await api.get<VaultOverview>("/admin/vault/overview");
  return resp.data;
}

// ---- Phase 6: Family Access governance (aggregate metrics only — no names, no content) ----

export interface FamilyEventRow {
  id: string;
  action: string;
  outcome: string;
  created_at: string;
}

export interface FamilyOverview {
  active_relationships: number;
  pending_invitations: number;
  declined_invitations: number;
  expired_invitations: number;
  revoked_relationships: number;
  access_denied_events: number;
  recent_events: FamilyEventRow[];
}

export async function fetchFamilyOverview(): Promise<FamilyOverview> {
  const resp = await api.get<FamilyOverview>("/admin/family/overview");
  return resp.data;
}

// ---- Phase 7: Emergency governance (operational aggregates only — no notes/coords/content) ----

export interface EmergencyEventRow {
  id: string;
  action: string;
  outcome: string;
  created_at: string;
}

export interface EmergencyOverview {
  active_emergencies: number;
  status_counts: Record<string, number>;
  notification_delivery: { QUEUED: number; SENT: number; DELIVERED: number; FAILED: number };
  handoff_status: {
    REQUESTED: number;
    ACCEPTED: number;
    REJECTED: number;
    EXPIRED: number;
    COMPLETED: number;
  };
  ambulance_provider: {
    configured: boolean;
    dispatch_requests: number;
    not_configured_attempts: number;
  };
  security_denied_events: number;
  recent_events: EmergencyEventRow[];
}

export async function fetchEmergencyOverview(): Promise<EmergencyOverview> {
  const resp = await api.get<EmergencyOverview>("/admin/emergency/overview");
  return resp.data;
}
