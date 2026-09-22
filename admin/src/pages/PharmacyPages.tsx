/** Phase 4 admin pages: medicines, pharmacies + verification, price
 * verification, orders, savings status (spec §26). All decisions hit
 * server-side SUPER_ADMIN endpoints; the UI performs no local authorization. */
import { useEffect, useState } from "react";
import {
  createMedicine,
  decidePharmacy,
  decidePrice,
  expireStalePrices,
  fetchAdminOrders,
  fetchAdminPharmacies,
  fetchMedicines,
  fetchPriceQueue,
  MedicineRow,
  OrderRow,
  PharmacyRow,
  PriceQueueRow,
  suspendPharmacy,
  verifyPharmacy,
} from "../api";
import { BRAND } from "../brand";

const statusColor: Record<string, string> = {
  VERIFIED: "#0B7A5C",
  PENDING: "#92400E",
  UNDER_REVIEW: "#1D4ED8",
  REJECTED: "#991B1B",
  SUSPENDED: "#991B1B",
  EXPIRED: "#6B7280",
  UNVERIFIED: "#6B7280",
  DELIVERED: "#0B7A5C",
  CONFIRMED: "#1D4ED8",
  CANCELLED: "#991B1B",
};

function Badge({ value }: { value: string }) {
  return (
    <span
      style={{
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        color: "#fff",
        background: statusColor[value] ?? "#5A6478",
      }}
    >
      {value}
    </span>
  );
}

const th: React.CSSProperties = { textAlign: "left", padding: "8px 12px", borderBottom: `2px solid ${BRAND.teal}` };
const td: React.CSSProperties = { padding: "8px 12px", borderBottom: "1px solid #EDF1F7", fontSize: 13 };
const btn: React.CSSProperties = {
  padding: "5px 10px",
  borderRadius: 6,
  border: "1px solid #D5DCE8",
  background: "#fff",
  cursor: "pointer",
  fontSize: 12,
  marginRight: 6,
};

function Table({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", borderRadius: 8 }}>
      <thead>
        <tr>
          {headers.map((h) => (
            <th key={h} style={th}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

function StatusFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const options = ["", "PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "SUSPENDED", "EXPIRED"];
  return (
    <label style={{ fontSize: 13, marginRight: 12 }}>
      Status:{" "}
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ padding: "4px 8px" }}>
        {options.map((o) => (
          <option key={o} value={o}>{o || "ALL"}</option>
        ))}
      </select>
    </label>
  );
}

// ------------------------------------------------------------- medicines

export function MedicinesPage() {
  const [medicines, setMedicines] = useState<MedicineRow[]>([]);
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const [strength, setStrength] = useState("");
  const [form, setForm] = useState("TABLET");
  const [pack, setPack] = useState("");
  const [rx, setRx] = useState(false);
  const [error, setError] = useState("");

  const load = () => fetchMedicines(q || undefined).then(setMedicines).catch(() => setMedicines([]));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const submit = async () => {
    setError("");
    if (!name.trim() || !strength.trim()) {
      setError("Name and strength are required.");
      return;
    }
    try {
      await createMedicine({
        name: name.trim(),
        strength: strength.trim(),
        dosage_form: form,
        pack_size: pack.trim(),
        prescription_required: rx,
        data_source: "ADMIN_MANUAL_ENTRY",
      });
      setName("");
      setStrength("");
      setPack("");
      setRx(false);
      await load();
    } catch (err) {
      setError("Creation failed — check the values (real data source required).");
    }
  };

  return (
    <section>
      <h2>Medicine Catalog</h2>
      <p style={{ color: "#5A6478", fontSize: 13 }}>
        Master data only — records must come from a real source. No medicine is created by this
        dashboard automatically.
      </p>
      <input placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} style={{ padding: 8, width: 260, marginRight: 8 }} />
      <Table headers={["Name", "Generic", "Strength", "Form", "Pack", "Rx", "Status", "Source"]}>
        {medicines.map((m) => (
          <tr key={m.id}>
            <td style={td}>{m.name}</td>
            <td style={td}>{m.generic_name}</td>
            <td style={td}>{m.strength}</td>
            <td style={td}>{m.dosage_form}</td>
            <td style={td}>{m.pack_size}</td>
            <td style={td}>{m.prescription_required ? "✔ required" : "—"}</td>
            <td style={td}><Badge value={m.status} /></td>
            <td style={td}>{m.data_source}</td>
          </tr>
        ))}
      </Table>
      <h3 style={{ marginTop: 24 }}>Add medicine</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} style={{ padding: 8, width: 220 }} />
        <input placeholder="Strength (e.g. 500 mg)" value={strength} onChange={(e) => setStrength(e.target.value)} style={{ padding: 8, width: 140 }} />
        <select value={form} onChange={(e) => setForm(e.target.value)} style={{ padding: 8 }}>
          {["TABLET", "CAPSULE", "SYRUP", "INJECTION", "CREAM", "OINTMENT", "DROPS", "INHALER", "POWDER", "SOLUTION", "OTHER"].map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <input placeholder="Pack size" value={pack} onChange={(e) => setPack(e.target.value)} style={{ padding: 8, width: 120 }} />
        <label style={{ fontSize: 13 }}>
          <input type="checkbox" checked={rx} onChange={(e) => setRx(e.target.checked)} /> Prescription required
        </label>
        <button onClick={submit} style={{ ...btn, background: BRAND.teal, color: "#fff", border: "none" }}>Create</button>
        {error && <span style={{ color: "#991B1B", fontSize: 13 }}>{error}</span>}
      </div>
    </section>
  );
}

// ------------------------------------------------------------- pharmacies

export function PharmaciesPage() {
  const [rows, setRows] = useState<PharmacyRow[]>([]);
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");

  const load = () => fetchAdminPharmacies(status || undefined).then(setRows).catch(() => setRows([]));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const act = async (fn: () => Promise<unknown>, okMessage: string) => {
    setMessage("");
    try {
      await fn();
      setMessage(okMessage);
      await load();
    } catch {
      setMessage("Action failed — the API rejected it (check current status).");
    }
  };

  return (
    <section>
      <h2>Pharmacies & Verification</h2>
      <StatusFilter value={status} onChange={setStatus} />
      {message && <p style={{ fontSize: 13, color: BRAND.teal }}>{message}</p>}
      <Table headers={["Pharmacy", "City", "Delivery", "Pickup", "Status", "Actions"]}>
        {rows.map((p) => (
          <tr key={p.id}>
            <td style={td}>{p.name}<br /><span style={{ color: "#5A6478", fontSize: 12 }}>{p.address_line}</span></td>
            <td style={td}>{p.city}</td>
            <td style={td}>{p.delivery_supported ? "yes" : "no"}</td>
            <td style={td}>{p.pickup_supported ? "yes" : "no"}</td>
            <td style={td}><Badge value={p.verification_status} /></td>
            <td style={td}>
              {p.verification_status !== "VERIFIED" && (
                <button style={btn} onClick={() => act(() => verifyPharmacy(p.id), "Pharmacy verified (audited)")}>Verify</button>
              )}
              {p.verification_status === "VERIFIED" && (
                <button style={btn} onClick={() => act(() => suspendPharmacy(p.id, note), "Pharmacy suspended (audited)")}>Suspend</button>
              )}
              <button style={btn} onClick={() => act(() => decidePharmacy(p.id, "REJECTED", note), "Pharmacy rejected (audited)")}>Reject</button>
            </td>
          </tr>
        ))}
      </Table>
      <label style={{ display: "block", marginTop: 12, fontSize: 13 }}>
        Decision note (stored in the immutable history):
        <input value={note} onChange={(e) => setNote(e.target.value)} style={{ padding: 8, width: 320, marginLeft: 8 }} />
      </label>
    </section>
  );
}

// -------------------------------------------------------- price verification

export function PriceVerificationPage() {
  const [rows, setRows] = useState<PriceQueueRow[]>([]);
  const [status, setStatus] = useState("PENDING");
  const [message, setMessage] = useState("");

  const load = () => fetchPriceQueue(status || undefined).then(setRows).catch(() => setRows([]));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const decide = async (id: string, decision: "VERIFIED" | "REJECTED") => {
    setMessage("");
    try {
      await decidePrice(id, decision, "dashboard decision");
      await load();
    } catch {
      setMessage("Decision failed — price may already be decided.");
    }
  };

  return (
    <section>
      <h2>Price Verification</h2>
      <StatusFilter value={status} onChange={setStatus} />
      <button style={btn} onClick={async () => setMessage(`Expired ${(await expireStalePrices()).expired} price record(s).`)}>
        Run expiration sweep
      </button>
      {message && <p style={{ fontSize: 13, color: BRAND.teal }}>{message}</p>}
      <p style={{ color: "#5A6478", fontSize: 13 }}>
        Only VERIFIED prices are patient-visible. Expired prices never remain visible as current.
      </p>
      <Table headers={["Medicine", "Pharmacy", "Price", "Source", "Submitted", "Status", "Actions"]}>
        {rows.map((p) => (
          <tr key={p.id}>
            <td style={td}>{p.medicine_name}</td>
            <td style={td}>{p.pharmacy_name}</td>
            <td style={td}>{p.currency} {p.price}</td>
            <td style={td}>{p.source}</td>
            <td style={td}>{new Date(p.submitted_at).toLocaleString()}</td>
            <td style={td}><Badge value={p.verification_status} /></td>
            <td style={td}>
              {p.verification_status === "PENDING" && (
                <>
                  <button style={btn} onClick={() => decide(p.id, "VERIFIED")}>Verify</button>
                  <button style={btn} onClick={() => decide(p.id, "REJECTED")}>Reject</button>
                </>
              )}
            </td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

// ------------------------------------------------------------- orders

export function MedicineOrdersPage() {
  const [rows, setRows] = useState<OrderRow[]>([]);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetchAdminOrders(status || undefined).then(setRows).catch(() => setRows([]));
  }, [status]);

  return (
    <section>
      <h2>Medicine Orders</h2>
      <StatusFilter value={status} onChange={setStatus} />
      <Table headers={["Order", "Status", "Pharmacy", "Items", "Total", "Created"]}>
        {rows.map((o) => (
          <tr key={o.id}>
            <td style={td} className="mono">{o.id.slice(0, 8)}…</td>
            <td style={td}><Badge value={o.status} /></td>
            <td style={td} className="mono">{o.pharmacy_id.slice(0, 8)}…</td>
            <td style={td}>
              {o.items.map((i) => (
                <div key={i.id} style={{ fontSize: 12 }}>
                  {i.medicine_name} × {i.quantity} @ INR {i.unit_price}
                  {" "}
                  <span style={{ color: "#5A6478" }}>(snapshot: {i.snapshot_verification_status})</span>
                </div>
              ))}
            </td>
            <td style={td}>{o.currency} {o.total}</td>
            <td style={td}>{new Date(o.created_at).toLocaleString()}</td>
          </tr>
        ))}
      </Table>
    </section>
  );
}
