import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./auth";
import { BRAND } from "./brand";
import { DemoBanner } from "./components/DemoBanner";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FeatureFlagsPage } from "./pages/FeatureFlagsPage";
import { VerificationQueuePage } from "./pages/VerificationQueuePage";
import {
  AppointmentsPage,
  DoctorsPage,
  HospitalsPage,
  SpecialtiesPage,
} from "./pages/ProviderPages";
import {
  MedicinesPage,
  MedicineOrdersPage,
  PharmaciesPage,
  PriceVerificationPage,
} from "./pages/PharmacyPages";
import { VaultGovernancePage } from "./pages/VaultGovernancePage";
import { FamilyGovernancePage } from "./pages/FamilyGovernancePage";
import { EmergencyGovernancePage } from "./pages/EmergencyGovernancePage";

function RequireSuperAdmin({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <p style={{ padding: 24 }}>Loading…</p>;
  if (!me) return <Navigate to="/login" replace />;
  // Cosmetic client check only — the API enforces SUPER_ADMIN server-side (spec §4).
  if (!me.roles.includes("SUPER_ADMIN")) {
    return (
      <div style={{ padding: 24 }}>
        <h2>Access denied</h2>
        <p>Your account does not have the SUPER_ADMIN role.</p>
      </div>
    );
  }
  return <>{children}</>;
}

function Shell({ children }: { children: ReactNode }) {
  const { me, signOut } = useAuth();
  return (
    <div style={{ minHeight: "100vh" }}>
      <DemoBanner />
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 24,
          padding: "12px 24px",
          background: "#fff",
          borderBottom: `3px solid ${BRAND.teal}`,
        }}
      >
        <strong style={{ color: BRAND.teal, fontSize: 18 }}>MediSave AI</strong>
        <nav style={{ display: "flex", gap: 16, flexWrap: "wrap" }} aria-label="Admin navigation">
          <Link to="/" style={navLink}>Dashboard</Link>
          <Link to="/verifications" style={navLink}>Verification Queue</Link>
          <Link to="/doctors" style={navLink}>Doctors</Link>
          <Link to="/hospitals" style={navLink}>Hospitals</Link>
          <Link to="/specialties" style={navLink}>Specialties</Link>
          <Link to="/appointments" style={navLink}>Appointments</Link>
          <Link to="/medicines" style={navLink}>Medicines</Link>
          <Link to="/pharmacies" style={navLink}>Pharmacies</Link>
          <Link to="/price-verification" style={navLink}>Price Verification</Link>
          <Link to="/medicine-orders" style={navLink}>Medicine Orders</Link>
          <Link to="/vault-governance" style={navLink}>Health Vault</Link>
          <Link to="/family-governance" style={navLink}>Family Access</Link>
          <Link to="/emergency-governance" style={navLink}>Emergency</Link>
          <Link to="/feature-flags" style={navLink}>Feature Flags</Link>
        </nav>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "#5A6478" }}>
          {me?.email} ({me?.roles.join(", ")})
        </span>
        <button onClick={signOut} style={signOutStyle}>Sign out</button>
      </header>
      <main style={{ padding: 24 }}>{children}</main>
    </div>
  );
}

const navLink: React.CSSProperties = { color: BRAND.darkText, textDecoration: "none", fontSize: 14 };
const signOutStyle: React.CSSProperties = {
  padding: "6px 12px",
  border: "1px solid #D5DCE8",
  borderRadius: 8,
  background: "#fff",
  cursor: "pointer",
  fontSize: 13,
};

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="*"
            element={
              <RequireSuperAdmin>
                <Shell>
                  <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/verifications" element={<VerificationQueuePage />} />
                    <Route path="/doctors" element={<DoctorsPage />} />
                    <Route path="/hospitals" element={<HospitalsPage />} />
                    <Route path="/specialties" element={<SpecialtiesPage />} />
                    <Route path="/appointments" element={<AppointmentsPage />} />
                    <Route path="/medicines" element={<MedicinesPage />} />
                    <Route path="/pharmacies" element={<PharmaciesPage />} />
                    <Route path="/price-verification" element={<PriceVerificationPage />} />
                    <Route path="/medicine-orders" element={<MedicineOrdersPage />} />
                    <Route path="/vault-governance" element={<VaultGovernancePage />} />
                    <Route path="/family-governance" element={<FamilyGovernancePage />} />
                    <Route path="/emergency-governance" element={<EmergencyGovernancePage />} />
                    <Route path="/feature-flags" element={<FeatureFlagsPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Shell>
              </RequireSuperAdmin>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
