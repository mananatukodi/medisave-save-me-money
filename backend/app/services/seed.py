"""Idempotent startup seed: RBAC roles, specialty catalog, feature flags.

IMPORTANT (spec §54): we seed ONLY structural catalog data — roles, the 17
specialties from spec §6, and feature flags. We do NOT seed doctors, hospitals,
pharmacies, medicines, prices, or insurance data, because that would be
fabricated healthcare information. Provider/price data enters the system only
through the verification workflow (Phase 3+).
"""

from sqlalchemy.orm import Session

from app.models.healthcare import Specialty, SpecialtyService
from app.models.ops import FeatureFlag
from app.models.user import Role

ROLES = (
    "PATIENT",
    "FAMILY_MEMBER",
    "DOCTOR",
    "HOSPITAL_ADMIN",
    "PHARMACY_ADMIN",
    "LAB_ADMIN",
    "INSURANCE_PARTNER",
    "SUPPORT_AGENT",
    "FIELD_AGENT",
    "SUPER_ADMIN",
)

# (slug, en, te, hi, icon, sort, description_en)
SPECIALTIES = (
    ("eye-care", "Eye Care", "కంటి సంరక్షణ", "आंखों की देखभाल", "👁️", 10,
     "Ophthalmologists, optometrists, vision screening, cataract & glaucoma care."),
    ("dental-care", "Dental Care", "దంత సంరక్షణ", "दंत चिकित्सा", "🦷", 20,
     "Dentists, cleanings, fillings, root canal consultation, orthodontics."),
    ("cardiology", "Cardiology", "గుండె జబ్బుల వైద్యం", "हृदय रोग विज्ञान", "❤️", 30,
     "Heart health consultation, ECG, cardiology specialists."),
    ("pediatrics", "Pediatrics", "పిల్లల వైద్యం", "बाल चिकित्सा", "👶", 40,
     "Child health, vaccinations guidance, pediatric specialists."),
    ("general-medicine", "General Medicine", "సాధారణ వైద్యం", "सामान्य चिकित्सा", "🩺", 50,
     "Primary care and general physicians."),
    ("neurology", "Neurology", "నాడీ వ్యవస్థ", "न्यूरोलॉजी", "🧠", 60,
     "Brain, spine and nervous system specialists."),
    ("orthopedics", "Orthopedics", "ఎముకల వైద్యం", "अस्थि रोग", "🦴", 70,
     "Bones, joints and muscle care."),
    ("gynecology", "Gynecology", "స్త్రీ జననేంద్రియ వైద్యం", "स्त्री रोग", "👩‍⚕️", 80,
     "Women's health and gynecology specialists."),
    ("dermatology", "Dermatology", "చర్మ వ్యాధులు", "त्वचा रोग", "🧴", 90,
     "Skin, hair and nail care."),
    ("ent", "ENT", "చెవి-ముక్కు-గొంతు", "कान-नाक-गला", "👂", 100,
     "Ear, nose and throat specialists."),
    ("pulmonology", "Pulmonology", "ఊపిరితిత్తుల వ్యాధులు", "फुफ्फुस विज्ञान", "🫁", 110,
     "Lung and respiratory care."),
    ("nephrology", "Nephrology", "వృక్క వైద్యం", "नेफ्रोलॉजी", "🫘", 120,
     "Kidney care and dialysis guidance."),
    ("oncology", "Oncology", "క్యాన్సర్ చికిత్స", "कैंसर विज्ञान", "🧬", 130,
     "Cancer care navigation and oncology specialists."),
    ("mental-health", "Mental Health", "మానసిక ఆరోగ్యం", "मानसिक स्वास्थ्य", "🧠", 140,
     "Mental health support and counseling navigation."),
    ("physiotherapy", "Physiotherapy", "ఫిజియోథెరపీ", "फिजियोथेरेपी", "🧑‍⚕️", 150,
     "Rehabilitation and physiotherapy."),
    ("diagnostics-lab", "Diagnostics & Lab", "పరీక్షలు & ల్యాబ్", "जांच & लैब", "🧪", 160,
     "Lab tests, imaging and diagnostics navigation."),
    ("other", "Other Specialties", "ఇతర విశేషాలు", "अन्य विशेषज्ञताएं", "➕", 170,
     "Additional specialties as the network grows."),
)

EYE_CARE_SERVICES = (
    ("vision-screening", "Vision screening", "కంటి పరీక్ష", "दृष्टि जांच"),
    ("cataract-consultation", "Cataract consultation", "తెల్లకంటి సలహా", "मोतियाबिंद परामर्श"),
    ("glaucoma-screening", "Glaucoma screening", "గ్లౌకోమా పరీక్ష", "ग्लूकोमा जांच"),
    ("retina-consultation", "Retina consultation", "రెటినా సలహా", "रेटिना परामर्श"),
    ("diabetic-eye-screening", "Diabetic eye screening", "డయాబెటిక్ కంటి పరీక్ష", "डायबिटिक आई जांच"),
    ("pediatric-eye-care", "Pediatric eye care", "పిల్లల కంటి సంరక్షణ", "बाल नेत्र देखभाल"),
    ("eye-surgery-consultation", "Eye surgery consultation", "కంటి శస్త్రచికిత్స సలహా", "आई सर्जरी परामर्श"),
)

DENTAL_CARE_SERVICES = (
    ("dental-checkup", "Dental check-up", "దంత పరీక్ష", "दंत जांच"),
    ("cleaning-scaling", "Cleaning & scaling", "క్లీనింగ్ & స్కేలింగ్", "क्लीनिंग और स्केलिंग"),
    ("fillings", "Fillings", "ఫిల్లింగ్స్", "फिलिंग"),
    ("root-canal-consultation", "Root canal consultation", "రూట్ కెనాల్ సలహా", "रूट कैनाल परामर्श"),
    ("extraction", "Tooth extraction", "పన్ను తీయడం", "दांत निकालना"),
    ("crowns-bridges", "Crowns & bridges", "క్రౌన్స్ & బ్రిడ్జెస్", "क्राउन और ब्रिज"),
    ("orthodontics-braces", "Orthodontics & braces", "బ్రేస్‌లు", "ऑर्थोडॉन्टिक्स और ब्रेसेस"),
    ("pediatric-dentistry", "Pediatric dentistry", "పిల్లల దంత వైద్యం", "बाल दंत चिकित్सा"),
    ("gum-care", "Gum care", "చిగుళ్ళ సంరక్షణ", "मसूड़ों की देखभाल"),
)

FEATURE_FLAGS = (
    ("AI_ENABLED", "AI Health Assistant available", True),
    ("SOS_ENABLED", "Emergency SOS feature", True),
    # Phase 7 emergency flags: core SOS needs none of the optional ones.
    ("EMERGENCY_HOSPITAL_SEARCH", "Nearby emergency hospital discovery", True),
    ("EMERGENCY_NOTIFICATIONS", "Emergency notification dispatch", True),
    ("EMERGENCY_LOCATION", "Emergency location capture/sharing", True),
    ("AMBULANCE_INTEGRATION", "Ambulance dispatch provider integration", False),
    ("HOSPITAL_HANDOFF", "Emergency hospital handoff workflow", True),
    ("EMERGENCY_SMS", "Emergency SMS channel", False),
    ("EMERGENCY_VOICE", "Emergency voice call integration", False),
    ("ONLINE_CONSULTATION_ENABLED", "Online consultation booking", False),
    ("MEDICINE_SAVINGS_ENABLED", "Medicine savings engine", False),
    ("EYE_CARE_ENABLED", "Eye care module", True),
    ("DENTAL_CARE_ENABLED", "Dental care module", True),
    ("INSURANCE_ENABLED", "Insurance module", False),
    ("LAB_ENABLED", "Diagnostics & lab module", False),
    # Phase 8 partner ecosystem flags: OFF until configured (external
    # integrations must never silently activate).
    ("partner_ecosystem", "Partner ecosystem core (organizations + members)", False),
    ("partner_onboarding", "Partner registration/onboarding workflow", False),
    ("partner_verification", "Partner verification/admin review workflow", False),
    ("partner_services", "Partner service catalog management", False),
    ("partner_claims", "Partner claims architecture", False),
    ("partner_settlement", "Partner settlement records (finance-recorded)", False),
    ("partner_webhooks", "Partner webhook event ledger + endpoints", False),
    ("partner_api", "Partner API key credentials", False),
    ("partner_lab", "Diagnostics lab partner module", False),
    ("partner_insurance", "Insurance partner module", False),
    ("partner_emergency", "Emergency provider (ambulance) partner module", False),
)


def seed(db: Session) -> None:
    # Roles (idempotent)
    for role_id in ROLES:
        if db.get(Role, role_id) is None:
            db.add(Role(id=role_id, description=f"System role {role_id}"))

    # Specialties (idempotent)
    for slug, en, te, hi, icon, sort, desc in SPECIALTIES:
        existing = db.query(Specialty).filter(Specialty.slug == slug).first()
        if existing is None:
            db.add(
                Specialty(
                    slug=slug, name_en=en, name_te=te, name_hi=hi,
                    icon=icon, sort_order=sort, description_en=desc,
                )
            )

    # Eye-care and dental-care service catalogs (idempotent)
    db.flush()  # make pending Specialty rows visible to the queries below
    eye = db.query(Specialty).filter(Specialty.slug == "eye-care").first()
    if eye is not None and not eye.services:
        for code, en, te, hi in EYE_CARE_SERVICES:
            db.add(SpecialtyService(specialty_id=eye.id, code=code, name_en=en, name_te=te, name_hi=hi))
    dental = db.query(Specialty).filter(Specialty.slug == "dental-care").first()
    if dental is not None and not dental.services:
        for code, en, te, hi in DENTAL_CARE_SERVICES:
            db.add(SpecialtyService(specialty_id=dental.id, code=code, name_en=en, name_te=te, name_hi=hi))

    # Feature flags (idempotent)
    for key, description, enabled in FEATURE_FLAGS:
        if db.get(FeatureFlag, key) is None:
            db.add(FeatureFlag(key=key, description=description, is_enabled=enabled))

    db.commit()
