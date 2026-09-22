"""Specialty catalog tests (spec §6): 17 specialties, Eye Care + Dental Care services."""

EXPECTED_COUNT = 17


def test_requires_auth(client):
    assert client.get("/api/v1/specialties").status_code == 401


def test_list_has_17_specialties(client, patient_headers):
    items = client.get("/api/v1/specialties", headers=patient_headers).json()
    assert len(items) == EXPECTED_COUNT
    slugs = [s["slug"] for s in items]
    assert slugs[0] == "eye-care"  # Eye Care first (sort order 10)
    assert "dental-care" in slugs
    for slug in ("cardiology", "pediatrics", "orthopedics", "dermatology", "ent",
                 "neurology", "gynecology", "pulmonology", "nephrology", "oncology",
                 "mental-health", "physiotherapy", "diagnostics-lab", "other"):
        assert slug in slugs


def test_specialties_have_trilingual_names(client, patient_headers):
    items = client.get("/api/v1/specialties", headers=patient_headers).json()
    for item in items:
        assert item["name_te"], f"Telugu name missing for {item['slug']}"
        assert item["name_en"] and item["name_hi"]


def test_eye_care_services_seeded(client, patient_headers):
    eye = client.get("/api/v1/specialties/eye-care", headers=patient_headers).json()
    codes = {s["code"] for s in eye["services"]}
    assert {"vision-screening", "cataract-consultation", "glaucoma-screening",
            "diabetic-eye-screening", "pediatric-eye-care"} <= codes


def test_dental_care_services_seeded(client, patient_headers):
    dental = client.get("/api/v1/specialties/dental-care", headers=patient_headers).json()
    codes = {s["code"] for s in dental["services"]}
    assert {"dental-checkup", "cleaning-scaling", "root-canal-consultation",
            "orthodontics-braces", "pediatric-dentistry"} <= codes


def test_unknown_specialty_404(client, patient_headers):
    assert client.get("/api/v1/specialties/does-not-exist", headers=patient_headers).status_code == 404
