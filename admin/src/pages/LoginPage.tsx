import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { BRAND } from "../brand";

export function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch {
      setError("Login failed. Check your credentials.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: BRAND.background }}>
      <form
        onSubmit={onSubmit}
        style={{
          background: "#fff",
          padding: 32,
          borderRadius: 12,
          width: 360,
          boxShadow: "0 8px 24px rgba(23,32,51,0.08)",
        }}
      >
        <h1 style={{ margin: 0, fontSize: 22, color: BRAND.darkText }}>MediSave AI — Admin</h1>
        <p style={{ color: "#5A6478", fontSize: 14 }}>
          Sign in with a SUPER_ADMIN account. Role checks are enforced server-side.
        </p>
        <label style={labelStyle}>Email</label>
        <input
          style={inputStyle}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          aria-label="Email"
        />
        <label style={labelStyle}>Password</label>
        <input
          style={inputStyle}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          aria-label="Password"
        />
        {error && <p role="alert" style={{ color: "#DC2626", fontSize: 14 }}>{error}</p>}
        <button
          type="submit"
          disabled={busy}
          style={{
            marginTop: 16,
            width: "100%",
            padding: 12,
            border: 0,
            borderRadius: 8,
            background: BRAND.teal,
            color: "#fff",
            fontWeight: 600,
            fontSize: 15,
            cursor: busy ? "wait" : "pointer",
          }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: "block", fontSize: 13, margin: "12px 0 4px" };
const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: 10,
  border: "1px solid #D5DCE8",
  borderRadius: 8,
  fontSize: 14,
  boxSizing: "border-box",
};
