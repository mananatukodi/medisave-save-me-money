import { useCallback, useEffect, useState } from "react";
import {
  decideDoctor,
  decideHospital,
  fetchDoctorHistory,
  fetchDoctorQueue,
  fetchHospitalQueue,
  type DoctorRow,
  type HospitalRow,
} from "../api";
import { BRAND } from "../brand";

const STATUS_TABS = ["PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "SUSPENDED"] as const;

const statusColor: Record<string, string> = {
  PENDING: "#B45309",
  UNDER_REVIEW: BRAND.blue,
  VERIFIED: "#047857",
  REJECTED: "#DC2626",
  SUSPENDED: "#DC2626",
};

/** Admin verification workflow (spec §2, §16). Every action is audited server-side. */
export function VerificationQueuePage() {
  const [tab, setTab] = useState<(typeof STATUS_TABS)[number]>("PENDING");
  const [doctors, setDoctors] = useState<DoctorRow[]>([]);
  const [hospitals, setHospitals] = useState<HospitalRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (status: string) => {
    setError(null);
    try {
      const [d, h] = await Promise.all([fetchDoctorQueue(status), fetchHospitalQueue(status)]);
      setDoctors(d);
      setHospitals(h);
    } catch {
      setError("Could not load the queue (requires SUPER_ADMIN).");
    }
  }, []);

  useEffect(() => {
    void load(tab);
  }, [tab, load]);

  const act = async (kind: "doctor" | "hospital", id: string, newStatus: string) => {
    setBusyId(id);
    setError(null);
    try {
      if (kind === "doctor") {
        await decideDoctor(id, newStatus, note);
      } else {
        await decideHospital(id, newStatus, note);
      }
      setNote("");
      await load(tab);
    } catch {
      setError("Action failed (server-side RBAC or state rule rejected it).");
    } finally {
      setBusyId(null);
    }
  };

  const showHistory = async (doctorId: string) => {
    try {
      const history = await fetchDoctorHistory(doctorId);
      alert(
        history
          .map((h) => `${h.previous_status || "—"} → ${h.new_status} (${new Date(h.created_at).toLocaleString()})`)
          .join("\n") || "No history yet."
      );
    } catch {
      setError("Could not load history.");
    }
  };

  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Verification Queue</h1>
      <p style={{ color: "#5A6478", maxWidth: 720 }}>
        Providers reach patients only through this workflow. Decisions write an immutable history row
        and an audit entry; a provider is shown as VERIFIED only after a real decision exists.
      </p>
      <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
        {STATUS_TABS.map((status) => (
          <button
            key={status}
            onClick={() => setTab(status)}
            aria-pressed={tab === status}
            style={{
              padding: "8px 14px",
              borderRadius: 999,
              border: `1px solid ${tab === status ? BRAND.teal : "#D5DCE8"}`,
              background: tab === status ? BRAND.teal : "#fff",
              color: tab === status ? "#fff" : BRAND.darkText,
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            {status}
          </button>
        ))}
      </div>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Decision note (recorded in history + audit log)"
        style={{ width: 420, maxWidth: "100%", padding: 8, border: "1px solid #D5DCE8", borderRadius: 8 }}
      />
      {error && <p role="alert" style={{ color: "#DC2626" }}>{error}</p>}

      <h2 style={{ color: BRAND.darkText }}>Doctors ({doctors.length})</h2>
      {doctors.length === 0 && <p>No doctors in {tab}.</p>}
      {doctors.map((doc) => (
        <div key={doc.id} style={cardStyle}>
          <div>
            <strong>{doc.full_name}</strong>
            <div style={{ fontSize: 12, color: "#5A6478" }}>
              {doc.specialty_slug} · {doc.qualifications || "qualifications not provided"} ·{" "}
              {doc.city ?? "city not set"} · reg {doc.registration_number || "not provided"}
            </div>
            <span style={{ color: statusColor[doc.verification_status], fontWeight: 600, fontSize: 12 }}>
              {doc.verification_status}
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={approveStyle} disabled={busyId === doc.id}
              onClick={() => void act("doctor", doc.id, "VERIFIED")}>Approve</button>
            <button style={rejectStyle} disabled={busyId === doc.id}
              onClick={() => void act("doctor", doc.id, "REJECTED")}>Reject</button>
            <button style={neutralStyle} disabled={busyId === doc.id}
              onClick={() => void act("doctor", doc.id, "UNDER_REVIEW")}>Review</button>
            <button style={neutralStyle} disabled={busyId === doc.id}
              onClick={() => void act("doctor", doc.id, "SUSPENDED")}>Suspend</button>
            <button style={neutralStyle} onClick={() => void showHistory(doc.id)}>History</button>
          </div>
        </div>
      ))}

      <h2 style={{ color: BRAND.darkText }}>Hospitals ({hospitals.length})</h2>
      {hospitals.length === 0 && <p>No hospitals in {tab}.</p>}
      {hospitals.map((hosp) => (
        <div key={hosp.id} style={cardStyle}>
          <div>
            <strong>{hosp.name}</strong>
            <div style={{ fontSize: 12, color: "#5A6478" }}>
              {hosp.hospital_type} · {hosp.city ?? "city not set"} ·{" "}
              emergency flagged: {hosp.emergency_available ? "yes" : "no"} · emergency verified:{" "}
              {hosp.emergency_verified ? "yes" : "NO"}
            </div>
            <span style={{ color: statusColor[hosp.verification_status], fontWeight: 600, fontSize: 12 }}>
              {hosp.verification_status}
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={approveStyle} disabled={busyId === hosp.id}
              onClick={() => void act("hospital", hosp.id, "VERIFIED")}>Approve</button>
            <button style={rejectStyle} disabled={busyId === hosp.id}
              onClick={() => void act("hospital", hosp.id, "REJECTED")}>Reject</button>
            <button style={neutralStyle} disabled={busyId === hosp.id}
              onClick={() => void act("hospital", hosp.id, "UNDER_REVIEW")}>Review</button>
            <button style={neutralStyle} disabled={busyId === hosp.id}
              onClick={() => void act("hospital", hosp.id, "SUSPENDED")}>Suspend</button>
          </div>
        </div>
      ))}
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 16,
  background: "#fff",
  padding: "12px 16px",
  borderRadius: 8,
  marginBottom: 8,
  maxWidth: 860,
};
const approveStyle: React.CSSProperties = {
  padding: "6px 12px", border: 0, borderRadius: 6, background: "#047857", color: "#fff", cursor: "pointer",
};
const rejectStyle: React.CSSProperties = {
  padding: "6px 12px", border: 0, borderRadius: 6, background: "#DC2626", color: "#fff", cursor: "pointer",
};
const neutralStyle: React.CSSProperties = {
  padding: "6px 12px", border: "1px solid #D5DCE8", borderRadius: 6, background: "#fff", cursor: "pointer",
};
