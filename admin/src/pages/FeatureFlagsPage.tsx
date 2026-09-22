import { useEffect, useState } from "react";
import { fetchFeatureFlags, updateFeatureFlag, type FeatureFlagRow } from "../api";
import { BRAND } from "../brand";

export function FeatureFlagsPage() {
  const [flags, setFlags] = useState<FeatureFlagRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFeatureFlags()
      .then(setFlags)
      .catch(() => setError("Could not load feature flags."));
  }, []);

  const toggle = async (row: FeatureFlagRow) => {
    try {
      const updated = await updateFeatureFlag(row.key, !row.is_enabled);
      setFlags((rows) => rows?.map((r) => (r.key === updated.key ? updated : r)) ?? null);
    } catch {
      setError("Update failed — toggling flags requires SUPER_ADMIN (server-side RBAC).");
    }
  };

  return (
    <div>
      <h1 style={{ color: BRAND.darkText }}>Feature Flags</h1>
      {error && <p role="alert" style={{ color: "#DC2626" }}>{error}</p>}
      {flags === null && !error && <p>Loading…</p>}
      {flags?.map((flag) => (
        <div
          key={flag.key}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "#fff",
            padding: "12px 16px",
            borderRadius: 8,
            marginBottom: 8,
            maxWidth: 640,
          }}
        >
          <div>
            <strong style={{ fontSize: 14 }}>{flag.key}</strong>
            <div style={{ fontSize: 12, color: "#5A6478" }}>{flag.description}</div>
          </div>
          <button
            onClick={() => void toggle(flag)}
            aria-pressed={flag.is_enabled}
            aria-label={`Toggle ${flag.key}`}
            style={{
              padding: "8px 16px",
              border: 0,
              borderRadius: 999,
              background: flag.is_enabled ? BRAND.teal : "#D5DCE8",
              color: flag.is_enabled ? "#fff" : BRAND.darkText,
              cursor: "pointer",
              minWidth: 88,
            }}
          >
            {flag.is_enabled ? "Enabled" : "Disabled"}
          </button>
        </div>
      ))}
    </div>
  );
}
