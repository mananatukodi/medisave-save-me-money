import { useEffect, useState } from "react";
import { fetchAuditLogs, type AuditLogRow } from "../api";
import { BRAND } from "../brand";

export function DashboardPage() {
  const [logs, setLogs] = useState<AuditLogRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuditLogs()
      .then(setLogs)
      .catch(() => setError("Could not load audit logs (requires SUPER_ADMIN role)."));
  }, []);

  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Dashboard</h1>
      <p style={{ color: "#5A6478" }}>
        Recent audit events (spec §37). Additional admin modules (users, medicines, claims, AI
        sessions, …) are specified in docs/MEDISAVE_AI_IMPLEMENTATION_PLAN.md and land in later phases.
      </p>
      {error && <p role="alert" style={{ color: "#DC2626" }}>{error}</p>}
      {logs === null && !error && <p>Loading…</p>}
      {logs !== null && logs.length === 0 && <p>No audit events yet.</p>}
      {logs !== null && logs.length > 0 && (
        <table style={{ borderCollapse: "collapse", width: "100%", background: "#fff" }}>
          <thead>
            <tr>
              {["Time", "Action", "Actor", "Outcome", "Resource"].map((h) => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td style={tdStyle}>{new Date(log.created_at).toLocaleString()}</td>
                <td style={tdStyle}>{log.action}</td>
                <td style={tdStyle}>{log.actor_role ?? "—"}</td>
                <td style={tdStyle}>{log.outcome}</td>
                <td style={tdStyle}>{log.resource_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: 10,
  borderBottom: "2px solid #E3E8F0",
  fontSize: 13,
};
const tdStyle: React.CSSProperties = { padding: 10, borderBottom: "1px solid #EEF1F6", fontSize: 13 };
