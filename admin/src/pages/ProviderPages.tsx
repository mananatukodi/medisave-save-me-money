import { useEffect, useState } from "react";
import { fetchAdminAppointments, fetchDoctorQueue, fetchSpecialties, type AppointmentRow, type DoctorRow, type SpecialtyRow } from "../api";
import { BRAND } from "../brand";

/** Read-only admin lists (spec §16). Providers appear here only via real registrations. */
export function DoctorsPage() {
  const [doctors, setDoctors] = useState<DoctorRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDoctorQueue()
      .then(setDoctors)
      .catch(() => setError("Could not load doctors (requires SUPER_ADMIN)."));
  }, []);

  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Doctors</h1>
      {error && <p role="alert" style={{ color: "#DC2626" }}>{error}</p>}
      {doctors?.length === 0 && <p>No registered doctors yet. Nothing is fabricated (spec §20).</p>}
      {doctors?.map((d) => (
        <div key={d.id} style={{ background: "#fff", padding: "10px 16px", borderRadius: 8, marginBottom: 8, maxWidth: 720 }}>
          <strong>{d.full_name}</strong>
          <div style={{ fontSize: 12, color: "#5A6478" }}>
            {d.specialty_slug} · {d.city ?? "—"} · {d.verification_status}
          </div>
        </div>
      ))}
    </div>
  );
}

export function HospitalsPage() {
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchDoctorQueue().catch(() => setError("Requires SUPER_ADMIN."));
  }, []);
  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Hospitals</h1>
      <p style={{ color: "#5A6478" }}>
        Registered hospitals are managed in the Verification Queue (statuses: Pending, Under Review,
        Verified, Rejected, Suspended). {error}
      </p>
    </div>
  );
}

export function SpecialtiesPage() {
  const [items, setItems] = useState<SpecialtyRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSpecialties()
      .then(setItems)
      .catch(() => setError("Could not load specialties."));
  }, []);

  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Specialties</h1>
      {error && <p role="alert" style={{ color: "#DC2626" }}>{error}</p>}
      {items?.map((s) => (
        <div key={s.slug} style={{ background: "#fff", padding: "10px 16px", borderRadius: 8, marginBottom: 8, maxWidth: 720 }}>
          <strong>{s.icon} {s.name_en}</strong>
          <div style={{ fontSize: 13 }}>{s.name_te} · {s.name_hi}</div>
          <div style={{ fontSize: 11, color: "#5A6478" }}>{s.slug}</div>
        </div>
      ))}
    </div>
  );
}

export function AppointmentsPage() {
  const [items, setItems] = useState<AppointmentRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminAppointments()
      .then(setItems)
      .catch(() => setError("Could not load appointments (requires SUPER_ADMIN)."));
  }, []);

  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Appointments</h1>
      {error && <p role="alert" style={{ color: "#DC2626" }}>{error}</p>}
      {items?.length === 0 && <p>No appointments yet.</p>}
      {items && items.length > 0 && (
        <table style={{ borderCollapse: "collapse", width: "100%", background: "#fff" }}>
          <thead>
            <tr>
              {["Date", "Time", "Specialty", "Consultation", "Price", "Status"].map((h) => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td style={tdStyle}>{a.appointment_date}</td>
                <td style={tdStyle}>{a.appointment_time}</td>
                <td style={tdStyle}>{a.specialty_slug}</td>
                <td style={tdStyle}>{a.consultation_type}</td>
                <td style={tdStyle}>
                  {a.price_amount !== null ? `${a.price_amount} ${a.price_verified ? "(verified)" : "(declared)"}` : "—"}
                </td>
                <td style={tdStyle}>{a.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = { textAlign: "left", padding: 10, borderBottom: "2px solid #E3E8F0", fontSize: 13 };
const tdStyle: React.CSSProperties = { padding: 10, borderBottom: "1px solid #EEF1F6", fontSize: 13 };
