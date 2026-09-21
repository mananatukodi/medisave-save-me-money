/** Phase 5: Health Vault governance page (spec §13).
 *
 * PRIVACY CONTRACT: this page shows aggregate metrics and security/consent
 * events ONLY — never record titles, filenames, or document contents.
 * Admin is not a backdoor into patient data; clinical access stays with the
 * record owner and explicitly granted sharees. */
import { useEffect, useState } from "react";
import { fetchVaultOverview, VaultOverview } from "../api";
import { BRAND } from "../brand";

const actionColor: Record<string, string> = {
  DENIED: "#991B1B",
  SHARE_CREATED: "#1D4ED8",
  SHARE_REVOKED: "#92400E",
  VIEW: "#1D4ED8",
  DOWNLOAD_URL: "#0B7A5C",
  FILE_UPLOADED: "#0B7A5C",
  RECORD_CREATED: "#0B7A5C",
  RECORD_DELETED: "#991B1B",
};

export function VaultGovernancePage() {
  const [data, setData] = useState<VaultOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVaultOverview()
      .then(setData)
      .catch(() => setError("Failed to load vault overview."));
  }, []);

  if (error) return <p style={{ color: "#991B1B" }}>{error}</p>;
  if (!data) return <p style={{ padding: 24 }}>Loading…</p>;

  const stats: Array<{ label: string; value: string; hint: string }> = [
    { label: "Health records", value: String(data.records), hint: "metadata only — contents stay with the patient" },
    { label: "Stored files", value: String(data.stored_files), hint: "encrypted at rest (dev storage provider)" },
    {
      label: "Storage used",
      value: `${(data.storage_bytes / 1024).toFixed(1)} KB`,
      hint: "aggregate size; no file contents exposed",
    },
    { label: "Active shares", value: String(data.active_shares), hint: "consent-controlled grants, revocable" },
  ];

  return (
    <div>
      <h2 style={{ color: BRAND.teal }}>Health Vault — Governance</h2>
      <p style={{ color: "#5A6478", maxWidth: 720 }}>
        Aggregate system health and security events. Document contents, titles,
        and filenames are deliberately not shown here — there is no ordinary
        admin path to patient clinical data.
      </p>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "16px 0 24px" }}>
        {stats.map((s) => (
          <div
            key={s.label}
            style={{
              background: "#fff",
              border: "1px solid #D5DCE8",
              borderRadius: 12,
              padding: "16px 20px",
              minWidth: 200,
            }}
          >
            <div style={{ fontSize: 13, color: "#5A6478" }}>{s.label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: BRAND.teal }}>{s.value}</div>
            <div style={{ fontSize: 11, color: "#8A93A6", marginTop: 4 }}>{s.hint}</div>
          </div>
        ))}
      </div>

      <h3>Recent security & consent events</h3>
      {data.recent_events.length === 0 ? (
        <p style={{ color: "#5A6478" }}>No vault activity recorded yet.</p>
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
                  {ev.result}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
