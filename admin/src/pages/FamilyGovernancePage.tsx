/** Phase 6: Family Accounts governance page (spec §23).
 *
 * PRIVACY CONTRACT: this page shows aggregate relationship/consent counts and
 * audited family actions ONLY — never relationship display names, invited
 * emails, consent purposes, or any clinical data. Admin is not a backdoor
 * into family access; every grant remains owner-controlled and revocable.
 */
import { useEffect, useState } from "react";
import { fetchFamilyOverview, FamilyOverview } from "../api";
import { BRAND } from "../brand";

const actionColor: Record<string, string> = {
  FAMILY_INVITATION_CREATED: "#1D4ED8",
  FAMILY_INVITATION_ACCEPTED: "#0B7A5C",
  FAMILY_INVITATION_DECLINED: "#92400E",
  FAMILY_RELATIONSHIP_REVOKED: "#991B1B",
  FAMILY_CONSENT_GRANTED: "#0B7A5C",
  FAMILY_CONSENT_REVOKED: "#991B1B",
  FAMILY_RECORD_ACCESS: "#1D4ED8",
  FAMILY_RECORD_ACCESS_DENIED: "#991B1B",
  FAMILY_MEDICINE_ORDERS_VIEWED: "#1D4ED8",
  DENIED: "#991B1B",
};

export function FamilyGovernancePage() {
  const [data, setData] = useState<FamilyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFamilyOverview()
      .then(setData)
      .catch(() => setError("Failed to load family overview."));
  }, []);

  if (error) return <p style={{ color: "#991B1B" }}>{error}</p>;
  if (!data) return <p style={{ padding: 24 }}>Loading…</p>;

  const stats: Array<{ label: string; value: string; hint: string }> = [
    {
      label: "Active relationships",
      value: String(data.active_relationships),
      hint: "accepted links — zero access until the owner grants consent",
    },
    {
      label: "Pending invitations",
      value: String(data.pending_invitations),
      hint: "24 h single-use, stored as SHA-256 hashes only",
    },
    {
      label: "Declined / expired",
      value: `${data.declined_invitations} / ${data.expired_invitations}`,
      hint: "invitee declined or invitation TTL elapsed",
    },
    {
      label: "Revoked relationships",
      value: String(data.revoked_relationships),
      hint: "either side can revoke — access ends immediately",
    },
    {
      label: "Access-denied events",
      value: String(data.access_denied_events),
      hint: "audited FAMILY_RECORD_ACCESS_DENIED — consent gate working",
    },
  ];

  return (
    <div>
      <h2 style={{ color: BRAND.teal }}>Family Access — Governance</h2>
      <p style={{ color: "#5A6478", maxWidth: 720 }}>
        Aggregate family-access metrics and audited actions. Relationship
        names, invited emails, consent purposes, and record data are
        deliberately not shown here — a family relationship grants zero access
        by itself; owners grant scoped, time-bounded, revocable consent.
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

      <h3>Recent family actions (audited)</h3>
      {data.recent_events.length === 0 ? (
        <p style={{ color: "#5A6478" }}>No family activity recorded yet.</p>
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
