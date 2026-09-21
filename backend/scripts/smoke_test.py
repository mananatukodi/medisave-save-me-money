"""Live-server smoke test: boots uvicorn on a scratch SQLite DB, exercises the
public flow over real HTTP, prints results, and always terminates the server.

Not part of the pytest suite — run manually:  python scripts/smoke_test.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta

BASE = "http://127.0.0.1:8019"
DB = "smoke.db"
LOG = "smoke-uvicorn.log"

# Windows consoles default to cp1252; force UTF-8 so Telugu/arrow output prints.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# An externally-set MEDISAVE_DATABASE_URL (e.g. Postgres) wins; default is SQLite.
os.environ.setdefault("MEDISAVE_DATABASE_URL", f"sqlite:///{DB}")
# The smoke flow makes many auth calls in a burst; rate limiting is separately
# unit-tested, so it is disabled here via its documented config switch.
os.environ.setdefault("MEDISAVE_RATE_LIMIT_ENABLED", "false")


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as err:
        payload = err.read().decode()
        try:
            return err.code, json.loads(payload)
        except json.JSONDecodeError:
            return err.code, payload


def main() -> int:
    import uuid

    run_id = uuid.uuid4().hex[:8]  # unique user per run: a persistent DB must not
    # inherit consents/data from previous runs.
    patient_email = f"smoke-{run_id}@example.com"
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8019", "--log-level", "warning"],
        stdout=open(LOG, "w"),
        stderr=subprocess.STDOUT,
    )
    results: list[tuple[str, bool, str]] = []
    try:
        # Wait for boot.
        for _ in range(60):
            try:
                status, _ = call("GET", "/health")
                if status == 200:
                    break
            except OSError:
                time.sleep(0.5)
        else:
            print("Server never became healthy")
            print("--- uvicorn log ---")
            try:
                with open(LOG) as handle:
                    print(handle.read() or "(empty)")
            except OSError as err:
                print(f"(no log: {err})")
            return 1

        status, body = call("GET", "/health")
        results.append(("health 200 + demo_mode", status == 200 and body["demo_mode"] is True, str(body)))

        status, body = call("GET", "/ready")
        results.append(("ready db ok", status == 200 and body["checks"]["database"] == "ok", str(body)))

        status, tokens = call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Test", "email": patient_email,
            "password": "Password123!", "primary_language": "te",
        })
        results.append(("register 201 → tokens", status == 201 and "access_token" in tokens, str(status)))
        token = tokens["access_token"]

        status, body = call("POST", "/api/v1/ai/chat",
                            {"message": "eye pain", "language": "te"}, token)
        results.append(("AI without consent → 403", status == 403, str(status)))

        status, body = call("POST", "/api/v1/ai/chat",
                            {"message": "severe chest pain", "language": "en"}, token)
        results.append(("emergency bypasses consent",
                        status == 200 and body["urgency"] == "EMERGENCY", str(body)[:120]))

        status, _ = call("POST", "/api/v1/consents",
                         {"consent_type": "AI_ACCESS", "purpose": "smoke"}, token)
        status, body = call("POST", "/api/v1/ai/chat",
                            {"message": "I need cataract consultation", "language": "en"}, token)
        routes = [n["route"] for n in body.get("navigation", [])]
        ok_nav = "/specialties/eye-care" in routes
        results.append(("AI eye-care intent + nav",
                        status == 200 and body["intent"] == "EYE_CARE" and ok_nav,
                        f"intent={body.get('intent')} routes={routes}"))

        status, body = call("GET", "/api/v1/specialties", token=token)
        results.append(("17 specialties seeded", status == 200 and len(body) == 17, f"count={len(body)}"))

        status, _ = call("POST", "/api/v1/emergency/sos", {"note": "smoke"}, token)
        status, body = call("GET", "/api/v1/emergency/events", token=token)
        results.append(("SOS starts REQUESTED (never CONFIRMED)", status == 200
                        and body[0]["status"] == "REQUESTED", str(body[0]["status"])))

        status, _ = call("GET", "/api/v1/admin/users", token=token)
        results.append(("RBAC: patient denied admin → 403", status == 403, str(status)))

        # ---- Phase 3: provider -> verification -> availability -> booking ----
        call("POST", "/api/v1/auth/register", {
            "full_name": "Dr Smoke", "email": "smoke-doctor@example.com",
            "password": "Password123!",
        })
        call("POST", "/api/v1/auth/register", {
            "full_name": "Admin Smoke", "email": "smoke-admin@example.com",
            "password": "Password123!",
        })
        # Promote via SUPER_ADMIN created directly in the DB seed? No: use API-level
        # demonstration with the seeded roles — register as doctor role via the API
        # is not possible by design (role grants are admin-only), so the smoke test
        # creates the doctor row via the doctor token only if the role exists.
        status, _ = call("GET", "/api/v1/doctors", token=token)
        results.append(("doctor discovery endpoint live", status == 200, str(status)))
        status, _ = call("GET", "/api/v1/providers?kind=doctor", token=token)
        results.append(("provider search endpoint live", status == 200, str(status)))
        status, _ = call("GET", "/api/v1/hospitals", token=token)
        results.append(("hospital discovery endpoint live", status == 200, str(status)))
        status, _ = call("GET", "/api/v1/appointments", token=token)
        results.append(("appointments listing live", status == 200, str(status)))
        status, _ = call("GET", "/api/v1/admin/verifications/doctors", token=token)
        results.append(("RBAC: patient denied verification queue → 403", status == 403, str(status)))

        # ---- Phase 4: medicine -> verified price -> savings -> order ----
        # Smoke fixtures only: every record below is named (TEST FIXTURE) and the
        # role grants are made directly in the disposable smoke database.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models.user import Role, User, UserRole

        s = sessionmaker(bind=create_engine(os.environ["MEDISAVE_DATABASE_URL"]))()

        def grant_role(email: str, role_id: str) -> None:
            user = s.query(User).filter(User.email == email).first()
            if user is None:
                return
            if s.get(Role, role_id) is None:
                s.add(Role(id=role_id, description="smoke"))
            if not s.query(UserRole).filter_by(user_id=user.id, role_id=role_id).first():
                s.add(UserRole(user_id=user.id, role_id=role_id))
            s.commit()

        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Super Admin", "email": f"sa-{run_id}@example.com",
            "password": "Password123!",
        })
        grant_role(f"sa-{run_id}@example.com", "SUPER_ADMIN")
        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Pharmacy", "email": f"ph-{run_id}@example.com",
            "password": "Password123!",
        })
        grant_role(f"ph-{run_id}@example.com", "PHARMACY_ADMIN")
        _, admin_tok = call("POST", "/api/v1/auth/login",
                            {"email": f"sa-{run_id}@example.com", "password": "Password123!"})
        admin_token = admin_tok["access_token"]
        _, ph_tok = call("POST", "/api/v1/auth/login",
                         {"email": f"ph-{run_id}@example.com", "password": "Password123!"})
        ph_token = ph_tok["access_token"]

        status, med = call("POST", "/api/v1/medicines", {
            "name": f"SmokeMed {run_id} (TEST FIXTURE)", "generic_name": "smokemed",
            "strength": "500 mg", "dosage_form": "TABLET", "pack_size": "10 tablets",
            "description": "smoke fixture", "data_source": "SMOKE_TEST",
        }, admin_token)
        results.append(("admin creates medicine", status == 201, str(status)))
        med_id = med["id"] if status == 201 else ""

        status, body = call("GET", f"/api/v1/medicines/{med_id}")
        results.append(("medicine detail public",
                        status == 200 and body["strength"] == "500 mg", str(status)))
        status, body = call("GET", f"/api/v1/medicines?q=SmokeMed+{run_id}")
        results.append(("medicine search finds it", status == 200 and any(
            m["id"] == med_id for m in body), str(status)))

        status, ph = call("POST", "/api/v1/pharmacies", {
            "name": f"SmokePharma A {run_id} (TEST FIXTURE)", "city": "Hyderabad",
            "pickup_supported": True, "delivery_supported": True,
        }, ph_token)
        results.append(("pharmacy registers PENDING", status == 201
                        and ph["verification_status"] == "PENDING", str(status)))
        ph_a = ph["id"] if status == 201 else ""
        status, _ = call("POST", f"/api/v1/admin/pharmacies/{ph_a}/verify",
                         {"new_status": "VERIFIED"}, admin_token)
        results.append(("admin verifies pharmacy", status == 200, str(status)))
        status, body = call("GET", "/api/v1/pharmacies")
        results.append(("verified pharmacy publicly visible", status == 200
                        and any(p["id"] == ph_a for p in body), str(status)))

        def submit_and_verify(ph_token_: str, amount: float, medicine_id_: str = "") -> str:
            _, p = call("POST", "/api/v1/pharmacies/me/prices",
                        {"medicine_id": medicine_id_ or med_id, "price": amount}, ph_token_)
            if p is None or "id" not in p:
                return ""
            call("POST", f"/api/v1/admin/prices/{p['id']}/decision",
                 {"decision": "VERIFIED"}, admin_token)
            return p["id"]

        status, body = call("POST", "/api/v1/pharmacies/me/prices",
                            {"medicine_id": med_id, "price": 120}, ph_token)
        price_a = body.get("id", "") if status == 201 else ""
        results.append(("pharmacy submits price PENDING", status == 201
                        and body["verification_status"] == "PENDING", str(status)))
        call("POST", f"/api/v1/admin/prices/{price_a}/decision",
             {"decision": "VERIFIED"}, admin_token)
        status, body = call("GET", f"/api/v1/medicines/{med_id}/prices")
        results.append(("verified price public with provenance", status == 200 and any(
            p["id"] == price_a and p["verification_status"] == "VERIFIED"
            and p["source"] and p["last_updated"] for p in body), str(status)))

        # Second pharmacy at 150 -> savings = 30 (spec §11/§12 example)
        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Pharmacy B", "email": f"phb-{run_id}@example.com",
            "password": "Password123!",
        })
        grant_role(f"phb-{run_id}@example.com", "PHARMACY_ADMIN")
        _, phb_tok = call("POST", "/api/v1/auth/login",
                          {"email": f"phb-{run_id}@example.com", "password": "Password123!"})
        phb_token = phb_tok["access_token"]
        status_b, ph = call("POST", "/api/v1/pharmacies", {
            "name": f"SmokePharma B {run_id} (TEST FIXTURE)", "city": "Warangal",
            "pickup_supported": True,
        }, phb_token)
        ph_b = ph["id"] if status_b == 201 else ""
        call("POST", f"/api/v1/admin/pharmacies/{ph_b}/verify", {"new_status": "VERIFIED"}, admin_token)
        submit_and_verify(phb_token, 150)

        status, body = call("GET", f"/api/v1/medicines/{med_id}/savings")
        results.append(("savings CALCULATED = 30", status == 200
                        and body["status"] == "CALCULATED"
                        and body["potential_savings"] == 30.0
                        and body["reference_price"] == 150.0
                        and body["selected_price"] == 120.0, str(body)[:120]))

        status, _ = call("POST", "/api/v1/pharmacies/me/inventory",
                         {"medicine_id": med_id, "stock_status": "IN_STOCK", "quantity": 50}, ph_token)
        status, order = call("POST", "/api/v1/orders", {
            "pharmacy_id": ph_a, "items": [{"medicine_id": med_id, "quantity": 2}],
            "pickup_option": True,
        }, token)
        ok = status == 201 and order["items"][0]["unit_price"] == 120.0
        results.append(("order created with price snapshot 120", ok, str(order)[:120]))
        order_id = order["id"] if status == 201 else ""

        status, body = call("GET", f"/api/v1/orders/{order_id}", token=token)
        results.append(("patient views own order", status == 200, str(status)))

        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Other", "email": f"other-{run_id}@example.com",
            "password": "Password123!",
        })
        _, other_tok = call("POST", "/api/v1/auth/login",
                            {"email": f"other-{run_id}@example.com", "password": "Password123!"})
        status, _ = call("GET", f"/api/v1/orders/{order_id}", token=other_tok["access_token"])
        results.append(("order hidden from other patients → 404", status == 404, str(status)))

        # Prescription gating: Rx-required medicine cannot be confirmed directly.
        status, med2 = call("POST", "/api/v1/medicines", {
            "name": f"SmokeRx {run_id} (TEST FIXTURE)", "strength": "10 mg",
            "dosage_form": "TABLET", "pack_size": "10 tablets",
            "prescription_required": True, "data_source": "SMOKE_TEST",
        }, admin_token)
        med2_id = med2["id"] if status == 201 else ""
        submit_and_verify(ph_token, 60, med2_id)
        call("POST", "/api/v1/pharmacies/me/inventory",
             {"medicine_id": med2_id, "stock_status": "IN_STOCK"}, ph_token)
        status, rx_order = call("POST", "/api/v1/orders", {
            "pharmacy_id": ph_a, "items": [{"medicine_id": med2_id, "quantity": 1}],
            "pickup_option": True,
        }, token)
        results.append(("Rx medicine order pauses at PRESCRIPTION_REQUIRED",
                        status == 201 and rx_order["status"] == "PRESCRIPTION_REQUIRED",
                        str(rx_order.get("status") if isinstance(rx_order, dict) else rx_order)))
        status, _ = call("GET", "/api/v1/admin/prices/verification", token=token)
        results.append(("RBAC: patient denied price queue → 403", status == 403, str(status)))

        # ---- Phase 5: vault upload -> signed URL -> share -> revoke -> audit ----
        status, rec = call("POST", "/api/v1/health-records",
                           {"category": "LAB_REPORT", "title": "Smoke Lab (SYNTHETIC)",
                            "record_date": "2026-09-01"}, token)
        results.append(("vault: create record", status == 201, str(status)))
        rec_id = rec["id"] if status == 201 else ""

        # Synthetic PNG upload via raw multipart (urllib has no multipart helper).
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
               b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
               b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
        boundary = "smokeboundary42"
        mp = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"smoke.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + png + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            BASE + f"/api/v1/health-records/{rec_id}/upload",
            data=mp, method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                up_status, up_body = response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as err:
            up_status, up_body = err.code, err.read().decode()
        results.append(("vault: upload PNG validated+stored", up_status == 201
                        and isinstance(up_body, dict)
                        and up_body.get("file", {}).get("upload_status") == "COMPLETED"
                        and len(up_body.get("file", {}).get("checksum_sha256", "")) == 64,
                        str(up_status)))

        status, meta = call("GET", f"/api/v1/health-records/{rec_id}", token=token)
        meta_json = json.dumps(meta)
        results.append(("vault: metadata exposes no object keys/paths", status == 200
                        and "object_key" not in meta_json
                        and "data/vault" not in meta_json
                        and meta["file"]["upload_status"] == "COMPLETED", str(status)))

        status, url = call("GET", f"/api/v1/health-records/{rec_id}/download-url", token=token)
        ok_url = status == 200 and url["ttl_seconds"] == 900
        if ok_url:
            request = urllib.request.Request(BASE + url["url"],
                                             headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(request, timeout=15) as response:
                dl_status = response.status
        else:
            dl_status = 0
        results.append(("vault: signed URL + patient download", ok_url and dl_status == 200,
                        f"url={status} dl={dl_status}"))

        # Doctor share flow
        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Doctor", "email": f"vdoc-{run_id}@example.com",
            "password": "Password123!",
        })
        grant_role(f"vdoc-{run_id}@example.com", "DOCTOR")
        s2 = sessionmaker(bind=create_engine(os.environ["MEDISAVE_DATABASE_URL"]))()
        doctor_row = s2.query(User).filter(User.email == f"vdoc-{run_id}@example.com").first()
        doctor_id = doctor_row.id if doctor_row else ""
        s2.close()
        _, d_tok = call("POST", "/api/v1/auth/login",
                        {"email": f"vdoc-{run_id}@example.com", "password": "Password123!"})
        doctor_token = d_tok["access_token"]

        status, share = call("POST", "/api/v1/health-records/shares",
                             {"record_id": rec_id, "grantee_user_id": doctor_id,
                              "grantee_type": "DOCTOR", "scope": "VIEW_RECORD",
                              "purpose": "smoke"}, token)
        results.append(("vault: share created", status == 201, str(status)))
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=doctor_token)
        results.append(("vault: granted doctor can view", status == 200, str(status)))

        status, _ = call("DELETE", f"/api/v1/health-records/shares/{share['id']}", token=token)
        status2, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=doctor_token)
        results.append(("vault: revoked doctor → 403", status == 200 and status2 == 403,
                        f"revoke={status} view={status2}"))

        status, audit = call("GET", f"/api/v1/health-records/{rec_id}/audit", token=token)
        actions = [e["action"] for e in audit] if status == 200 else []
        results.append(("vault: audit trail (VIEW/DENIED/SHARE_CREATED/SHARE_REVOKED)",
                        all(a in actions for a in ("VIEW", "SHARE_CREATED", "SHARE_REVOKED"))
                        and "DENIED" in actions,
                        str(actions)))

        # Another patient cannot see the record (existence hidden)
        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Stranger", "email": f"vstr-{run_id}@example.com",
            "password": "Password123!",
        })
        _, s_tok = call("POST", "/api/v1/auth/login",
                        {"email": f"vstr-{run_id}@example.com", "password": "Password123!"})
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=s_tok["access_token"])
        results.append(("vault: stranger → 404 (no IDOR)", status == 404, str(status)))

        # Expired consent: backdate a share's expiry directly, then expect 403
        status, exp_share = call("POST", "/api/v1/health-records/shares",
                                 {"record_id": rec_id, "grantee_user_id": doctor_id,
                                  "scope": "VIEW_RECORD", "expires_in_days": 1}, token)
        s3 = sessionmaker(bind=create_engine(os.environ["MEDISAVE_DATABASE_URL"]))()
        from app.models.vault import HealthRecordShare as Share
        row = s3.get(Share, exp_share["id"])
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
        s3.commit()
        s3.close()
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=doctor_token)
        results.append(("vault: expired share → 403", status == 403, str(status)))

        # ---- Phase 6: family invite -> consent -> scoped access -> revoke ----
        # Synthetic family members only; relationship alone grants NOTHING.
        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Family Member", "email": f"fam-{run_id}@example.com",
            "password": "Password123!",
        })
        _, fam_tok = call("POST", "/api/v1/auth/login",
                          {"email": f"fam-{run_id}@example.com", "password": "Password123!"})
        s3 = sessionmaker(bind=create_engine(os.environ["MEDISAVE_DATABASE_URL"]))()
        from app.models.user import User as SmokeUser
        fam_id = s3.query(SmokeUser).filter(SmokeUser.email == f"fam-{run_id}@example.com").one().id
        owner_id = s3.query(SmokeUser).filter(SmokeUser.email == patient_email).one().id
        s3.close()
        status, inv = call("POST", "/api/v1/family/invitations",
                           {"display_name": "Smoke Relative", "relationship_type": "SPOUSE",
                            "member_user_id": fam_id}, token)
        results.append(("family: invitation created (token once)", status == 201
                        and bool(inv.get("invitation_token")), str(status)))
        status, lst = call("GET", "/api/v1/family/invitations", token=token)
        results.append(("family: token never re-exposed in lists",
                        status == 200 and all("invitation_token" not in i for i in lst), str(status)))
        status, acc = call("POST", f"/api/v1/family/invitations/{inv['id']}/accept",
                           token=fam_tok["access_token"])
        results.append(("family: accept -> ACTIVE", status == 200
                        and acc["status"] == "ACTIVE", str(status)))

        # No consent yet: relationship must NOT grant record access (403).
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=fam_tok["access_token"])
        results.append(("family: no default access (relationship ≠ access)", status == 403, str(status)))

        # Grant scoped consent (VIEW_HEALTH_RECORDS, category filter) -> access.
        # The vault record rec_id is a LAB_REPORT, so the filter must include it.
        status, _ = call("PUT", f"/api/v1/family/relationships/{inv['id']}/consent",
                         {"scopes": ["VIEW_HEALTH_RECORDS"], "purpose": "smoke",
                          "category_filter": ["LAB_REPORT"]}, token)
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=fam_tok["access_token"])
        results.append(("family: consented member can view (scoped)", status == 200, str(status)))

        # Category outside the filter must be denied: create an INSURANCE record.
        status, other = call("POST", "/api/v1/health-records",
                             {"category": "INSURANCE_DOCUMENT", "title": "Smoke Insurance (SYNTHETIC)",
                              "record_date": "2026-09-01"}, token)
        status, _ = call("GET", f"/api/v1/health-records/{other['id']}", token=fam_tok["access_token"])
        results.append(("family: category out of scope → 403", status == 403, str(status)))

        # Unrelated stranger stays 404.
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=s_tok["access_token"])
        results.append(("family: unrelated stranger → 404", status == 404, str(status)))

        # Consent revocation is immediate — member loses view at once.
        status, _ = call("DELETE", f"/api/v1/family/relationships/{inv['id']}/consent", token=token)
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=fam_tok["access_token"])
        results.append(("family: revoked consent → 403", status == 403, str(status)))

        # Re-grant with expiry, then expire via backdated consent (direct DB).
        status, fcons = call("PUT", f"/api/v1/family/relationships/{inv['id']}/consent",
                             {"scopes": ["VIEW_HEALTH_RECORDS"], "purpose": "smoke",
                              "expires_in_days": 1}, token)
        s3 = sessionmaker(bind=create_engine(os.environ["MEDISAVE_DATABASE_URL"]))()
        from app.models.family import FamilyAccessConsent as FConsent
        frow = s3.get(FConsent, fcons["id"])
        frow.expires_at = datetime.now(UTC) - timedelta(hours=1)
        s3.commit()
        s3.close()
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=fam_tok["access_token"])
        results.append(("family: expired consent → 403", status == 403, str(status)))

        # Owner retains full access after all family changes.
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=token)
        results.append(("family: owner access unaffected", status == 200, str(status)))

        # ---- Phase 6: appointment on behalf of the owner (REQUEST_APPOINTMENT) ----
        call("POST", "/api/v1/auth/register", {
            "full_name": "Smoke Doctor 6", "email": f"doc6-{run_id}@example.com",
            "password": "Password123!",
        })
        grant_role(f"doc6-{run_id}@example.com", "DOCTOR")
        _, d6_tok = call("POST", "/api/v1/auth/login",
                         {"email": f"doc6-{run_id}@example.com", "password": "Password123!"})
        d6_token = d6_tok["access_token"]
        status, fam_doctor = call("POST", "/api/v1/doctors/register", {
            "full_name": f"Dr Smoke 6 {run_id} (TEST FIXTURE)", "specialty_slug": "eye-care",
            "qualifications": "MBBS, MS", "registration_number": f"TMC-{run_id}",
            "years_experience": 5, "consultation_modes": "IN_PERSON", "city": "Hyderabad",
        }, d6_token)
        fam_doctor_id = fam_doctor.get("id", "") if isinstance(fam_doctor, dict) else ""
        status, fam_service = call("POST", "/api/v1/doctors/me/services", {
            "specialty_slug": "eye-care", "name_en": f"Family smoke screening {run_id}",
            "name_te": "కంటి పరీక్ష", "name_hi": "दृष्टि जांच",
            "duration_minutes": 30, "consultation_type": "IN_PERSON", "price_amount": 300.0,
        }, d6_token)
        fam_service_id = fam_service.get("id", "") if isinstance(fam_service, dict) else ""
        call("POST", "/api/v1/doctors/me/availability", [
            {"weekday": wd, "start_time": "10:00", "end_time": "13:00", "slot_minutes": 30}
            for wd in range(5)
        ], d6_token)
        call("POST", f"/api/v1/admin/verifications/doctors/{fam_doctor_id}/decision",
             {"new_status": "VERIFIED", "decision_note": "smoke fixture"}, admin_token)
        day = date.today() + timedelta(days=1)
        while day.weekday() != 0:  # Monday always falls inside the fixture rules
            day += timedelta(days=1)
        booking = {
            "doctor_id": fam_doctor_id, "service_id": fam_service_id,
            "appointment_date": day.isoformat(), "appointment_time": "10:30",
            "on_behalf_of_patient_id": owner_id,
        }
        status, _ = call("POST", "/api/v1/appointments", booking, fam_tok["access_token"])
        results.append(("family: booking on behalf without consent → 403", status == 403, str(status)))

        status, _ = call("PUT", f"/api/v1/family/relationships/{inv['id']}/consent",
                         {"scopes": ["REQUEST_APPOINTMENT"], "purpose": "smoke"}, token)
        status, appt = call("POST", "/api/v1/appointments", booking, fam_tok["access_token"])
        ok = status == 201 and appt["patient_user_id"] == owner_id \
            and appt["requested_by_user_id"] == fam_id
        results.append(("family: on-behalf booking keeps patient=owner, requester=member",
                        ok, str(status)))
        appt_id = appt["id"] if status == 201 else ""

        # ---- Phase 6: medicine-order scope for the family member ----
        status, _ = call("PUT", f"/api/v1/family/relationships/{inv['id']}/consent",
                         {"scopes": ["VIEW_MEDICINE_ORDERS"], "purpose": "smoke"}, token)
        status, fam_orders = call("GET", f"/api/v1/orders?for_patient={owner_id}",
                                  token=fam_tok["access_token"])
        ok = status == 200 and isinstance(fam_orders, list) \
            and any(o.get("id") == order_id for o in fam_orders)
        results.append(("family: medicine-order list scoped to owner's orders", ok, str(status)))
        # Order detail (and any prescription content) stays owner-only.
        status, _ = call("GET", f"/api/v1/orders/{order_id}", token=fam_tok["access_token"])
        results.append(("family: order detail + prescription content owner-only → 404",
                        status == 404, str(status)))

        # ---- Phase 6: AI never infers family authorization from language ----
        status, body = call("POST", "/api/v1/ai/chat",
                            {"message": "I want my family member records summary", "language": "en"}, token)
        results.append(("AI family intent explains consent, never retrieves",
                        status == 200 and body["intent"] == "FAMILY_RECORD_SUMMARY"
                        and "consent" in body["message"].lower(), str(body)[:120]))

        # Re-grant view consent, then revoke the relationship — access ends at once.
        status, _ = call("PUT", f"/api/v1/family/relationships/{inv['id']}/consent",
                         {"scopes": ["VIEW_HEALTH_RECORDS"], "purpose": "smoke"}, token)
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=fam_tok["access_token"])
        assert status == 200, f"pre-revoke view failed: {status}"
        status, _ = call("POST", f"/api/v1/family/relationships/{inv['id']}/revoke", token=token)
        status, _ = call("GET", f"/api/v1/health-records/{rec_id}", token=fam_tok["access_token"])
        results.append(("family: revoked relationship → 403", status == 403, str(status)))

        # ---- Phase 6: invitation security (unauthorized acceptance / reuse) ----
        status, inv2 = call("POST", "/api/v1/family/invitations",
                            {"display_name": "Smoke Relative 2", "relationship_type": "CHILD",
                             "member_user_id": fam_id}, token)
        results.append(("family: re-invite after revoke allowed", status == 201, str(status)))
        status, _ = call("POST", f"/api/v1/family/invitations/{inv2['id']}/accept",
                         token=other_tok["access_token"])
        results.append(("family: stranger acceptance → 403", status == 403, str(status)))
        status, _ = call("POST", f"/api/v1/family/invitations/{inv2['id']}/accept",
                         token=fam_tok["access_token"])
        status2, _ = call("POST", f"/api/v1/family/invitations/{inv2['id']}/accept",
                          token=fam_tok["access_token"])
        results.append(("family: invitation single-use (reuse → 409)",
                        status == 200 and status2 == 409, f"accept={status} reuse={status2}"))

        # Audit trail: family actions visible to the owner.
        status, hist = call("GET", "/api/v1/family/access-history", token=token)
        fam_actions = {h["action"] for h in hist} if status == 200 else set()
        results.append(("family: audit trail (invite/consent/revoke)",
                        {"FAMILY_INVITATION_CREATED", "FAMILY_CONSENT_GRANTED",
                         "FAMILY_RELATIONSHIP_REVOKED"}.issubset(fam_actions), str(status)))

        # ---- Phase 7: emergency SOS — state machine, idempotency, honesty ----
        # Family alerts need RECEIVE_HEALTH_ALERTS on the still-ACTIVE inv2.
        status, _ = call("PUT", f"/api/v1/family/relationships/{inv2['id']}/consent",
                         {"scopes": ["RECEIVE_HEALTH_ALERTS"], "purpose": "smoke"}, token)

        # Close any SOS left active by the earlier Phase 1 smoke check.
        status, prev_events = call("GET", "/api/v1/emergency/events", token=token)
        for prev in (prev_events or []):
            if prev["status"] in ("REQUESTED", "ALERTING", "CONTACTING", "ACTIVE",
                                  "HANDOFF_PENDING"):
                call("POST", f"/api/v1/emergency/sos/{prev['id']}/cancel",
                     {"reason": "OTHER"}, token)

        sos_key = f"smoke-sos-{run_id}"
        status, sos = call("POST", "/api/v1/emergency/sos",
                           {"note": "phase7 smoke", "emergency_type": "MEDICAL",
                            "idempotency_key": sos_key, "device_platform": "smoke-runner",
                            "network_status": "4G"}, token)
        results.append(("emergency: SOS created REQUESTED (AI-independent)",
                        status == 201 and sos["status"] == "REQUESTED"
                        and sos["correlation_id"], str(status)))
        sos_id = sos["id"]
        status2, sos2 = call("POST", "/api/v1/emergency/sos",
                             {"idempotency_key": sos_key}, token)
        results.append(("emergency: idempotency key returns same event",
                        status2 == 200 and sos2["id"] == sos_id, str(status2)))
        status3, sos3 = call("POST", "/api/v1/emergency/sos", {"note": "retry"}, token)
        results.append(("emergency: active-dedup never rejects retries",
                        status3 == 200 and sos3["id"] == sos_id, str(status3)))

        # Emergency profile + minimum-necessary summary (UNKNOWN honesty).
        status, _ = call("PUT", "/api/v1/emergency/profile",
                         {"blood_group": "O+", "allergies": "penicillin"}, token)
        status, summary = call("GET", f"/api/v1/emergency/{sos_id}/medical-summary", token=token)
        results.append(("emergency: summary real fields + UNKNOWN honesty",
                        status == 200 and summary["blood_group"] == "O+"
                        and summary["allergies"] == "penicillin"
                        and summary["critical_conditions"] == "UNKNOWN"
                        and summary["disclaimer"].startswith("This information is user-provided"),
                        str(status)))

        # Family alerts: minimum necessary; location only with explicit consent.
        status, alerts = call("GET", "/api/v1/emergency/family-alerts", token=fam_tok["access_token"])
        has_alert = status == 200 and any(a["event_id"] == sos_id for a in alerts)
        results.append(("emergency: family member sees minimal alert",
                        has_alert and all("critical_medications" not in a for a in alerts)
                        and alerts and alerts[0]["location"] is None,
                        str(status)))
        call("POST", "/api/v1/consents",
             {"consent_type": "EMERGENCY_LOCATION", "purpose": "smoke",
              "recipient": f"family:{inv2['id']}"}, token)
        status, alerts = call("GET", "/api/v1/emergency/family-alerts", token=fam_tok["access_token"])
        results.append(("emergency: location shared only after EMERGENCY_LOCATION consent",
                        status == 200 and alerts and alerts[0]["location_shared"] is True,
                        str(status)))

        # Nearby hospitals: honest NOT_VERIFIED availability; no fabrication.
        status, nearby = call("GET",
                              "/api/v1/emergency/hospitals/nearby?lat=17.3850&lng=78.4867",
                              token=token)
        results.append(("emergency: nearby hospitals (availability NOT_VERIFIED)",
                        status == 200 and all(
                            h["availability_status"] == "NOT_VERIFIED" for h in nearby),
                        str(status)))

        # Ambulance abstraction: NOT_CONFIGURED is recorded honestly.
        status, amb = call("POST", f"/api/v1/emergency/{sos_id}/ambulance", {}, token)
        results.append(("emergency: ambulance NOT_CONFIGURED (never faked)",
                        status == 200 and amb["status"] == "NOT_CONFIGURED"
                        and "not currently available" in amb["detail"], str(status)))

        # Notifications: IN_APP real; SMS without provider honestly FAILED.
        call("POST", "/api/v1/emergency/contacts",
             {"full_name": "Smoke Contact", "phone_number": "+919999999998",
              "notification_preferences": "IN_APP,SMS"}, token)
        status, notes = call("GET", f"/api/v1/emergency/{sos_id}/notifications", token=token)
        ok = status == 200 and any(n["channel"] == "IN_APP" and n["status"] == "SENT"
                                   for n in notes)
        results.append(("emergency: IN_APP notification SENT (real)", ok, str(status)))

        # State machine: FALSE_ALARM cancel, then a fresh SOS is allowed.
        status, _ = call("POST", f"/api/v1/emergency/sos/{sos_id}/cancel",
                         {"reason": "FALSE_ALARM"}, token)
        status, cancelled = call("GET", f"/api/v1/emergency/sos/{sos_id}", token=token)
        results.append(("emergency: FALSE_ALARM terminal state",
                        status == 200 and cancelled["status"] == "FALSE_ALARM", str(status)))
        status, sos_b = call("POST", "/api/v1/emergency/sos",
                             {"note": "second emergency"}, token)
        results.append(("emergency: new SOS after terminal", status == 201, str(status)))
        if status == 201:
            call("POST", f"/api/v1/emergency/sos/{sos_b['id']}/cancel",
                 {"reason": "USER_CANCELLED"}, token)

        # Audit trail for the emergency lifecycle.
        status, audit = call("GET", f"/api/v1/emergency/{sos_id}/audit", token=token)
        audit_actions = {a["action"] for a in audit} if status == 200 else set()
        results.append(("emergency: audit trail (SOS_CREATED/AMBULANCE_REQUESTED/"
                        "SOS_FALSE_ALARM)",
                        {"SOS_CREATED", "AMBULANCE_REQUESTED", "SOS_FALSE_ALARM"}
                        .issubset(audit_actions), str(status)))

        # Cleanup: synthetic insurance record + Phase 6 fixtures for this run
        # (FK-safe order; users and audit rows are kept for the audit trail).
        call("DELETE", f"/api/v1/health-records/{other['id']}", token=token)
        s3 = sessionmaker(bind=create_engine(os.environ["MEDISAVE_DATABASE_URL"]))()
        from app.models.appointment import Appointment as SmokeAppointment
        from app.models.family import FamilyAccessConsent as FConsent
        from app.models.family import FamilyRelationship as FRel
        from app.models.providers import (
            Doctor as SmokeDoctor,
        )
        from app.models.providers import (
            DoctorVerification as SmokeDoctorVerification,
        )
        from app.models.providers import (
            ProviderService as SmokeService,
        )
        from app.models.providers import (
            ServiceAvailability as SmokeAvailability,
        )
        from app.models.providers import (
            ServicePrice as SmokePrice,
        )
        if appt_id:
            s3.query(SmokeAppointment).filter(SmokeAppointment.id == appt_id).delete()
        if fam_doctor_id:
            for svc in s3.query(SmokeService).filter(SmokeService.doctor_id == fam_doctor_id).all():
                s3.query(SmokePrice).filter(SmokePrice.service_id == svc.id).delete()
                s3.query(SmokeAvailability).filter(
                    SmokeAvailability.provider_kind == "DOCTOR",
                    SmokeAvailability.provider_id == fam_doctor_id,
                ).delete()
            s3.query(SmokeService).filter(SmokeService.doctor_id == fam_doctor_id).delete()
            s3.query(SmokeDoctorVerification).filter(
                SmokeDoctorVerification.doctor_id == fam_doctor_id
            ).delete()
            s3.query(SmokeDoctor).filter(SmokeDoctor.id == fam_doctor_id).delete()
        rel_ids = [r.id for r in s3.query(FRel).filter(
            (FRel.owner_user_id == fam_id) | (FRel.member_user_id == fam_id)).all()]
        if rel_ids:
            s3.query(FConsent).filter(FConsent.relationship_id.in_(rel_ids)).delete(
                synchronize_session=False)
            s3.query(FRel).filter(FRel.id.in_(rel_ids)).delete(synchronize_session=False)
        s3.commit()
        s3.close()

        # Cleanup: delete the synthetic record (purges stored file too)
        call("DELETE", f"/api/v1/health-records/{rec_id}", token=token)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    print("\n=== SMOKE TEST RESULTS (live server, real HTTP) ===")
    failed = 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}   [{detail}]")
        failed += 0 if ok else 1
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
