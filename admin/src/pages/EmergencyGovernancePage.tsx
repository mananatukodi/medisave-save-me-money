/** Phase 7: Emergency governance page.
 *
 * PRIVACY CONTRACT: operational aggregates and audit actions ONLY —
 * no event notes, no coordinates, no clinical content. An emergency is
 * never a reason for admin to read a patient's health data.
 */
import { useEffect, useState } from "react";
import { fetchEmergencyOverview, EmergencyOverview } from "../api";
import { BRAND } from "../brand";

const actionColor: Record<string, string> = {
  SOS_CREATED: "#1D4ED8",
  SOS_CANCELLED: "#92400E",
  SOS_FALSE_ALARM: "#92400E",
  EMERGENCY_RESOLVED: "#0B7A5C",
  LOCATION_CAPTURED: "#1D4ED8",
  EMERGENCY_PROFILE_ACCESSED: "#7C3AED",
  EMERGENCY_CONTACT_NOTIFIED: "#0B7A5C",
  AMBULANCE_REQUESTED: "#B45309",
  HOSPITAL_SEARCHED: "#1D4ED8",
  HOSPITAL_HANDOFF_REQUESTED: "#1D4ED8",
  HOSPITAL_HANDOFF_ACCEPTED: "#0B7A5C",
  HOSPITAL_HANDOFF_REJECTED: "#991B1B",
};

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #D5DCE8",
        borderRadius: 12,
        padding: "16px 20px",
        minWidth: 200,
      }}
    >
      <div style={{ fontSize: 13, color: "#5A6478" }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: BRAND.teal }}>{value}</div>
      <div style={{ fontSize: 11, color: "#8A93A6", marginTop: 4 }}>{hint}</div>
    </div>
  );
}

export function EmergencyGovernancePage() {
  const [data, setData] = useState<EmergencyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEmergencyOverview()
      .then(setData)
      .catch(() => setError("Failed to load emergency overview."));
  }, []);

  if (error) return <p style={{ color: "#991B1B" }}>{error}</p>;
  if (!data) return <p style={{ padding: 24 }}>Loading…</p>;

  return (
    <div>
      <h2 style={{ color: BRAND.teal }}>Emergency &amp; SOS — Governance</h2>
      <p style={{ color: "#5A6478", maxWidth: 720 }}>
        Operational aggregates and audited actions. Event notes, locations,
        and any clinical content are deliberately not shown here — emergency
        oversight does not open patient health data.
      </p>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "16px 0 24px" }}>
        <Stat
          label="Active emergencies"
          value={String(data.active_emergencies)}
          hint="non-terminal SOS events right now"
        />
        <Stat
          label="Resolved"
          value={String(data.status_counts.RESOLVED ?? 0)}
          hint="closed through the state machine"
        />
        <Stat
          label="Cancelled / false alarm"
          value={`${data.status_counts.CANCELLED ?? 0} / ${data.status_counts.FALSE_ALARM ?? 0}`}
          hint="patient-initiated early exits"
        />
        <Stat
          label="Notifications FAILED"
          value={String(data.notification_delivery.FAILED)}
          hint="honest failures (e.g. provider not configured)"
        />
        <Stat
          label="Handoff accepted"
          value={String(data.handoff_status.ACCEPTED)}
          hint="real hospital-side confirmations only"
        />
        <Stat
          label="Ambulance provider"
          value={data.ambulance_provider.configured ? "CONFIGURED" : "NOT_CONFIGURED"}
          hint={`${data.ambulance_provider.not_configured_attempts} honest NOT_CONFIGURED attempts`}
        />
        <Stat
          label="Security denials"
          value={String(data.security_denied_events)}
          hint="audited unauthorized emergency access attempts"
        />
      </div>

      <h3>Recent emergency audit actions</h3>
      {data.recent_events.length === 0 ? (
        <p style={{ color: "#5A6478" }}>No emergency activity recorded yet.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", minWidth: 640 }}>
          <thead>
            <tr>
              {["Time", "Action", "Result"].map((h) => (
                <th
                  key={h}
                  style={{ textAlign: "left", borderBottom: `2px solid ${BRAND.teal}`, padding: "6px 16px" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.recent_events.map((ev) => (
              <tr key={ev.id}>
                <td style={{ padding: "6px 16px", borderBottom: "1px solid #E7EBF2", fontSize: 13 }}>
                  {new Date(ev.created_at).toLocaleString()}
                </td>
                <td style={{ padding: "6px 16px", borderBottom: "1px solid #E7EBF2" }}>
                  <span
                    style={{
                      padding: "2px 8px",
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 600,
                      color: actionColor[ev.action] ?? "#5A6478",
                      background: "#F1F4F9",
                    }}
                  >
                    {ev.action}
                  </span>
                </td>
                <td style={{ padding: "6px 16px", borderBottom: "1px solid #E7EBF2", fontSize: 13 }}>
                  {ev.outcome}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
