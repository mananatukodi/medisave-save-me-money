import { BRAND, DEMO_BANNER_TEXT } from "../brand";

/** Persistent, unmissable DEMO banner (spec §46). */
export function DemoBanner() {
  return (
    <div
      style={{
        background: BRAND.aiPurple,
        color: "#fff",
        padding: "6px 16px",
        fontSize: 13,
        fontWeight: 600,
        textAlign: "center",
      }}
    >
      {DEMO_BANNER_TEXT}
    </div>
  );
}
