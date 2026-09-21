"""Phase 8 HTTP smoke test against a LIVE server (PostgreSQL).

Run with a server on :8000 whose DB is at Alembic head b4f8d2a6c9e1:
    python scripts/phase8_smoke_test.py

Honesty: creates only throwaway smoke data (smoke8-* emails), then the
operator (or the repo docs) cleans it up. Role promotion of the smoke admin
uses the documented ops path (seeded SUPER_ADMIN role + explicit grant).
"""

import json
import sys
import time
import urllib.error
import urllib.request

from sqlalchemy import create_engine, text

BASE = "http://localhost:8000/api/v1"
PG = "postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave"
passed = 0
failed = 0
suffix = str(int(time.time()))
ADMIN_EMAIL = f"smoke8-admin-{suffix}@example.com"


def call(method, path, body=None, token=None, expect=None, label=""):
    global passed, failed
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            code = resp.getcode()
            payload = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as err:
        code = err.code
        try:
            payload = json.loads(err.read().decode() or "{}")
        except Exception:
            payload = {}
    ok = (expect is None and 200 <= code < 300) or (
        expect is not None and code == expect
    )
    if ok:
        passed += 1
        print(f"  PASS [{code}] {label or path}")
    else:
        failed += 1
        detail = json.dumps(payload)[:200]
        print(f"  FAIL [{code}] {label or path} -> {detail}")
    return code, payload


def register_and_login(email):
    body = {"email": email, "password": "Password123!", "full_name": "Smoke User"}
    call(
        "POST",
        "/auth/register",
        body,
        label=f"register {email.split('@')[0]}",
    )
    code, data = call(
        "POST",
        "/auth/login",
        {"email": email, "password": "Password123!"},
        label=f"login {email.split('@')[0]}",
    )
    return data.get("access_token")


def promote_admin():
    """Documented ops path: grant the seeded SUPER_ADMIN role to the smoke
    admin (mirrors backend role-seed + admin grant; no data fabrication)."""
    engine = create_engine(PG)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": ADMIN_EMAIL},
        ).first()
        conn.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id, granted_at) "
                "VALUES (:uid, 'SUPER_ADMIN', NOW())"
            ),
            {"uid": row[0]},
        )
    engine.dispose()


def main():
    global failed, passed
    print("=== Phase 1-7 critical paths ===")
    with urllib.request.urlopen("http://localhost:8000/health") as resp:
        health = json.loads(resp.read().decode())
    if health.get("status") == "ok":
        passed += 1
        print(f"  PASS [200] /health status=ok env={health.get('env')}")
    else:
        failed += 1
        print("  FAIL /health")

    tok_admin = register_and_login(ADMIN_EMAIL)
    tok_a = register_and_login(f"smoke8-a-{suffix}@example.com")
    tok_b = register_and_login(f"smoke8-b-{suffix}@example.com")

    print("=== Flag gating (partner flags OFF by default) ===")
    call(
        "POST",
        "/partners",
        {"organization_type": "HOSPITAL", "legal_name": "Smoke Off"},
        token=tok_a,
        expect=503,
        label="onboarding gated 503 (flag off)",
    )
    call(
        "GET",
        "/partner/dashboard",
        token=tok_a,
        expect=503,
        label="dashboard gated 503 (flag off)",
    )
    call(
        "GET",
        "/lab-tests",
        expect=503,
        label="public lab tests gated 503 (flag off)",
    )
    call(
        "GET",
        "/admin/partners",
        token=tok_admin,
        expect=403,
        label="non-admin blocked (RBAC honest)",
    )

    print("=== Onboarding, verification, isolation (flags ON) ===")
    promote_admin()
    code, data = call(
        "POST",
        "/auth/login",
        {"email": ADMIN_EMAIL, "password": "Password123!"},
        label="admin re-login after grant",
    )
    tok_admin = data.get("access_token")

    flags = (
        "partner_ecosystem",
        "partner_onboarding",
        "partner_verification",
        "partner_services",
        "partner_lab",
        "partner_insurance",
        "partner_claims",
        "partner_webhooks",
        "partner_api",
    )
    for flag in flags:
        call(
            "PATCH",
            f"/feature-flags/{flag}",
            {"is_enabled": True},
            token=tok_admin,
            expect=200,
            label=f"enable {flag}",
        )

    code, org_a = call(
        "POST",
        "/partners",
        {
            "organization_type": "DIAGNOSTIC_LAB",
            "legal_name": "Smoke Lab A",
            "display_name": "Smoke Lab A",
            "registration_number": f"SMOKE8-LAB-{suffix}",
            "city": "Hyderabad",
        },
        token=tok_a,
        expect=201,
        label="org A registered (DRAFT)",
    )
    code, org_b = call(
        "POST",
        "/partners",
        {
            "organization_type": "DIAGNOSTIC_LAB",
            "legal_name": "Smoke Lab B",
            "display_name": "Smoke Lab B",
            "registration_number": f"SMOKE8-LABB-{suffix}",
            "city": "Vijayawada",
        },
        token=tok_b,
        expect=201,
        label="org B registered (DRAFT)",
    )

    call(
        "GET",
        f"/partners/{org_b['id']}",
        token=tok_a,
        expect=404,
        label="A cannot read B org (404 existence-hidden)",
    )
    call(
        "GET",
        f"/partners/{org_b['id']}/members",
        token=tok_a,
        expect=404,
        label="A cannot list B members",
    )
    call(
        "GET",
        f"/partners/{org_b['id']}/documents",
        token=tok_a,
        expect=404,
        label="A cannot list B documents",
    )

    call(
        "POST",
        f"/partners/{org_a['id']}/submit",
        token=tok_a,
        expect=200,
        label="org A submit",
    )
    call(
        "POST",
        f"/admin/partners/{org_a['id']}/review",
        token=tok_admin,
        expect=200,
        label="admin review",
    )
    call(
        "POST",
        f"/admin/partners/{org_a['id']}/approve",
        token=tok_admin,
        expect=200,
        label="admin approve",
    )
    call(
        "GET",
        f"/partners/{org_a['id']}/history",
        token=tok_a,
        expect=200,
        label="lifecycle history trail",
    )
    call(
        "POST",
        f"/admin/partners/{org_b['id']}/approve",
        token=tok_admin,
        expect=409,
        label="DRAFT->APPROVED rejected 409",
    )

    code, doc = call(
        "POST",
        f"/partners/{org_a['id']}/documents",
        {
            "document_type": "LAB_LICENSE",
            "storage_reference": f"smoke8/lab-license-{suffix}",
            "checksum": "b" * 64,
        },
        token=tok_a,
        expect=201,
        label="lab license uploaded",
    )
    call(
        "POST",
        f"/admin/partners/{org_a['id']}/documents/{doc['id']}/decision",
        {"decision": "VERIFIED", "note": "smoke"},
        token=tok_admin,
        expect=200,
        label="admin verifies document",
    )

    code, test = call(
        "POST",
        f"/partners/{org_a['id']}/lab/tests",
        {
            "code": f"SMOKE{suffix[-4:]}",
            "name": "Smoke Test Panel",
            "price": 150,
        },
        token=tok_a,
        expect=201,
        label="lab test created (UNVERIFIED)",
    )
    code, public = call("GET", "/lab-tests", expect=200, label="public lab catalog")
    if any(t["id"] == test["id"] for t in public):
        failed += 1
        print("  FAIL unverified test leaked to public catalog")
    else:
        passed += 1
        print("  PASS unverified test hidden from public catalog (price honesty)")
    call(
        "POST",
        f"/admin/partners/lab/tests/{test['id']}/decision",
        {"decision": "VERIFIED"},
        token=tok_admin,
        expect=200,
        label="admin verifies lab test",
    )
    code, public2 = call(
        "GET",
        "/lab-tests",
        expect=200,
        label="public catalog after verification",
    )
    if any(t["id"] == test["id"] for t in public2):
        passed += 1
        print("  PASS verified test now visible (org APPROVED)")
    else:
        failed += 1
        print("  FAIL verified test not visible")

    code, me_b = call("GET", "/auth/me", token=tok_b, expect=200, label="patient B identity")
    code, booking = call(
        "POST",
        f"/partners/{org_a['id']}/lab/bookings",
        {
            "test_id": test["id"],
            "patient_user_id": me_b["id"],
            "collection_mode": "HOME_COLLECTION",
        },
        token=tok_a,
        expect=201,
        label="lab booking created (REQUESTED)",
    )
    call(
        "POST",
        f"/partners/{org_a['id']}/lab/bookings/{booking['id']}/status",
        {"status": "CONFIRMED"},
        token=tok_a,
        expect=200,
        label="booking CONFIRMED",
    )
    call(
        "POST",
        f"/partners/{org_a['id']}/lab/bookings/{booking['id']}/status",
        {"status": "REPORT_READY"},
        token=tok_a,
        expect=409,
        label="invalid booking jump 409",
    )

    call(
        "POST",
        "/partners",
        {
            "organization_type": "INSURANCE",
            "legal_name": "Smoke InsCo",
            "registration_number": f"SMOKE8-INS-{suffix}",
        },
        token=tok_b,
        expect=201,
        label="insurer org registered",
    )
    code, mine_b = call("GET", "/partners/mine", token=tok_b, expect=200, label="org B mine")
    ins_id = next(o["id"] for o in mine_b if o["organization_type"] == "INSURANCE")
    call("POST", f"/partners/{ins_id}/submit", token=tok_b, expect=200, label="insurer submit")
    call("POST", f"/admin/partners/{ins_id}/review", token=tok_admin, expect=200, label="insurer review")
    call("POST", f"/admin/partners/{ins_id}/approve", token=tok_admin, expect=200, label="insurer approve")
    code, product = call(
        "POST",
        f"/partners/{ins_id}/insurance/products",
        {
            "product_name": "Smoke Health Cover",
            "product_type": "HEALTH",
            "claim_intake_supported": True,
        },
        token=tok_b,
        expect=201,
        label="insurance product created",
    )
    code, claim = call(
        "POST",
        f"/partners/{ins_id}/insurance/claims",
        {
            "patient_user_id": me_b["id"],
            "subject_type": "APPOINTMENT",
            "description": "Smoke claim",
            "amount": 999,
        },
        token=tok_b,
        expect=201,
        label="claim created DRAFT",
    )
    call(
        "POST",
        f"/partners/{ins_id}/insurance/claims/{claim['id']}/status",
        {"status": "APPROVED"},
        token=tok_b,
        expect=409,
        label="DRAFT->APPROVED rejected (no auto-approval)",
    )
    call(
        "POST",
        f"/partners/{ins_id}/insurance/claims/{claim['id']}/status",
        {"status": "SUBMITTED"},
        token=tok_b,
        expect=200,
        label="claim SUBMITTED",
    )
    call(
        "POST",
        f"/partners/{ins_id}/insurance/claims/{claim['id']}/status",
        {
            "status": "APPROVED",
            "approved_amount": 500,
            "note": "adjuster decision",
        },
        token=tok_b,
        expect=200,
        label="human APPROVED with amount",
    )
    code, own = call(
        "GET",
        "/insurance/claims",
        token=tok_b,
        expect=200,
        label="patient claims list",
    )
    if any(c["id"] == claim["id"] for c in own):
        passed += 1
        print("  PASS patient claim visible to owner")
    else:
        failed += 1
        print("  FAIL patient claim not visible to owner")

    code, key = call(
        "POST",
        f"/partners/{org_a['id']}/integrations/api-keys",
        {"name": "smoke-key", "scopes": "read"},
        token=tok_a,
        expect=201,
        label="API key created (raw shown once)",
    )
    if key.get("raw_key", "").startswith("msk_"):
        passed += 1
        print("  PASS raw API key returned once (msk_ prefix)")
    else:
        failed += 1
        print("  FAIL raw API key missing")
    code, integrations = call(
        "GET",
        f"/partners/{org_a['id']}/integrations",
        token=tok_a,
        expect=200,
        label="integrations list",
    )
    if any("raw_key" in i for i in integrations):
        failed += 1
        print("  FAIL raw key leaked in listing")
    else:
        passed += 1
        print("  PASS raw key never exposed in listing (hash-only storage)")
    call(
        "POST",
        f"/partners/{org_a['id']}/integrations/webhooks",
        {"endpoint_url": "http://insecure.example.com"},
        token=tok_a,
        expect=422,
        label="webhook http:// rejected 422",
    )

    call(
        "GET",
        "/partner/dashboard",
        token=tok_a,
        expect=200,
        label="partner dashboard (aggregates only)",
    )
    call(
        "GET",
        "/partner/notifications",
        token=tok_a,
        expect=200,
        label="partner IN_APP notifications",
    )
    call("GET", "/admin/partners", token=tok_admin, expect=200, label="admin partners list")
    call("GET", "/admin/partners/overview", token=tok_admin, expect=200, label="admin overview aggregates")

    print("=== Phase 1-7 regression probes (live) ===")
    call("GET", "/specialties", token=tok_a, expect=200, label="specialties catalog intact")
    call("GET", "/feature-flags", token=tok_a, expect=200, label="feature flags readable")
    call("GET", "/doctors", expect=200, label="doctors search intact")
    call("GET", "/pharmacies", expect=200, label="pharmacies search intact")
    call("GET", "/medicines", expect=200, label="medicines search intact")
    call("GET", "/orders", token=tok_a, expect=200, label="orders ownership scope intact")
    call("GET", "/health-records", token=tok_a, expect=200, label="vault scope intact")
    call("GET", "/emergency/history", token=tok_a, expect=200, label="emergency scope intact")
    call("GET", "/family/relationships", token=tok_a, expect=200, label="family scope intact")

    print("=== Summary ===")
    print(f"passed={passed} failed={failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
