"""AI intent definitions (spec §10) and trilingual keyword signals."""

from enum import StrEnum


class Intent(StrEnum):
    SYMPTOM_INFORMATION = "SYMPTOM_INFORMATION"
    EMERGENCY = "EMERGENCY"
    DOCTOR_SEARCH = "DOCTOR_SEARCH"
    HOSPITAL_SEARCH = "HOSPITAL_SEARCH"
    SPECIALIST_SEARCH = "SPECIALIST_SEARCH"
    EYE_CARE = "EYE_CARE"
    DENTAL_CARE = "DENTAL_CARE"
    CARDIOLOGY = "CARDIOLOGY"
    PEDIATRICS = "PEDIATRICS"
    ORTHOPEDICS = "ORTHOPEDICS"
    DERMATOLOGY = "DERMATOLOGY"
    ENT = "ENT"
    NEUROLOGY = "NEUROLOGY"
    GYNECOLOGY = "GYNECOLOGY"
    PHARMACY_SEARCH = "PHARMACY_SEARCH"
    PHARMACY_AVAILABILITY = "PHARMACY_AVAILABILITY"
    MEDICINE_SEARCH = "MEDICINE_SEARCH"
    MEDICINE_INFORMATION = "MEDICINE_INFORMATION"
    MEDICINE_PRICE = "MEDICINE_PRICE"
    MEDICINE_COMPARISON = "MEDICINE_COMPARISON"
    MEDICINE_ORDER = "MEDICINE_ORDER"
    PRESCRIPTION_REQUIRED = "PRESCRIPTION_REQUIRED"
    SAVINGS_CHECK = "SAVINGS_CHECK"
    HEALTH_RECORD = "HEALTH_RECORD"
    PRESCRIPTION = "PRESCRIPTION"
    LAB_REPORT = "LAB_REPORT"
    RECORD_SUMMARY = "RECORD_SUMMARY"
    FAMILY_RECORD_SUMMARY = "FAMILY_RECORD_SUMMARY"
    INSURANCE = "INSURANCE"
    INSURANCE_CLAIM = "INSURANCE_CLAIM"
    APPOINTMENT = "APPOINTMENT"
    PAYMENT = "PAYMENT"
    FOLLOW_UP = "FOLLOW_UP"
    FAMILY_HEALTH = "FAMILY_HEALTH"
    SUPPORT = "SUPPORT"
    HEALTH_EDUCATION = "HEALTH_EDUCATION"


# Keyword signals per intent (English + Telugu + Hindi). Matching is case-insensitive
# substring based. This is a first-line rule engine; an LLM classifier can replace it
# behind the same interface without changing the safety pipeline.
INTENT_KEYWORDS: dict[Intent, tuple[str, ...]] = {
    Intent.EMERGENCY: (),  # handled by the emergency screener, not keyword scoring
    Intent.EYE_CARE: (
        "eye", "vision", "eyes", "cataract", "glaucoma", "retina", "spectacles", "glasses",
        "contact lens", "kanna", "kallu", "chupu", "కంటి", "కళ్ళు", "చూపు", "తెల్లకంటి",
        "గ్లౌకోమా", "आंख", "नेत्र", "दृष्टि", "मोतियाबिंद",
    ),
    Intent.DENTAL_CARE: (
        "tooth", "teeth", "dental", "dentist", "gum", "cavity", "root canal", "braces",
        "pandu", "pallu", "dantam", "దంత", "పన్ను", "దవడ", "दांत", "दंत", "मसूड़",
    ),
    Intent.CARDIOLOGY: (
        "heart", "cardiac", "bp", "blood pressure", "cholesterol", "ecg", "palpitation",
        "గుండె", "రక్తపోటు", "हृदय", "दिल", "बीपी",
    ),
    Intent.PEDIATRICS: (
        "child", "baby", "infant", "kid", "newborn", "vaccination", "పిల్ల", "బిడ్డ",
        "శిశు", "టీకా", "बच्चा", "बच्चे", "शिशु", "टीका",
    ),
    Intent.ORTHOPEDICS: (
        "bone", "joint", "knee", "back pain", "fracture", "shoulder", "sprain",
        "ఎముక", "మోకాలు", "భుజం", "नली", "हड्डी", "घुटना", "जोड़",
    ),
    Intent.DERMATOLOGY: (
        "skin", "rash", "itching", "acne", "hair fall", "eczema", "చర్మ", "దద్దుర్లు",
        "తాము", "జుట్టు", "त्वचा", "खाज", "रैश", "बाल झड़",
    ),
    Intent.ENT: (
        "ear", "nose", "throat", "hearing", "tonsil", "sinus", "snoring",
        "చెవి", "ముక్కు", "గొంతు", "कान", "नाक", "गला",
    ),
    Intent.NEUROLOGY: (
        "headache", "migraine", "seizure", "epilepsy", "numbness", "dizziness", "brain",
        "తలనొప్పి", "మైగ్రేన్", "మూర్ఛ", "తడిమె", "सिरदर्द", "माइग्रेन", "दौरा", "मस्तिष्क",
    ),
    Intent.GYNECOLOGY: (
        "pregnan", "menstrual", "period", "gynec", "women health", "pcod", "pcos",
        "గర్భ", "ఋతు", "స్త్రీ", "गर्भ", "माहवारी", "स्त्री",
    ),
    Intent.DOCTOR_SEARCH: (
        "find doctor", "doctor near", "best doctor", "which doctor", "suggest a doctor",
        "doctor search", "వైద్యుడు", "డాక్టర్ కావాలి", "डॉक्टर", "डॉक्टर चाहिए",
    ),
    Intent.HOSPITAL_SEARCH: (
        "hospital near", "find hospital", "best hospital", "which hospital", "clinic near",
        "ఆసుపత్రి", "హాస్పిటల్", "క్లినిక్", "अस्पताल", "हॉस्पिटल", "क्लिनिक",
    ),
    Intent.SPECIALIST_SEARCH: (
        "specialist", "expert", "super specialist", "నిపుణుడు", "స్పెషలిస్ట్", "विशेषज्ञ",
    ),
    Intent.PHARMACY_SEARCH: (
        "pharmacy near", "medical store", "chemist", "pharmacy open", "ఫార్మసీ", "మెడికల్ షాప్",
        "दवा की दुकान", "मेडिकल स्टोर",
    ),
    Intent.MEDICINE_SEARCH: (
        "medicine for", "tablet for", "which medicine", "where to buy", "buy medicine",
        "మందు", "టాబ్లెట్", "మందులు", "మందు దొరుకుతుందా", "మందు ఎక్కడ",
        "दवा", "दवाइयां", "गोली", "दवा कहाँ", "दवा मिलेगी",
    ),
    Intent.MEDICINE_INFORMATION: (
        "side effects", "medicine information", "drug information", "how to take",
        "మందు వివరాలు", "మందు గురించి", "दवा की जानकारी", "साइड इफ़ेक्ट",
    ),
    Intent.MEDICINE_PRICE: (
        "medicine price", "price of", "cost of", "cheaper", "price entha",
        "generic", "ధర", "వెల", "తక్కువ ధర", "జెనెరిక్", "ఎంత",
        "कीमत", "सस्ता", "कितना",
    ),
    Intent.MEDICINE_COMPARISON: (
        "price comparison", "compare prices", "instead of", "can i use this instead",
        "substitute", "ధరల పోలిక", "कीमत तुलना", "विकल्प",
    ),
    Intent.MEDICINE_ORDER: (
        "order medicine", "place an order", "order tablet", "buy online",
        "home delivery of medicine", "ఆర్డర్", "ఆర్డర్ చేయాలి", "ऑर्डर",
    ),
    Intent.PRESCRIPTION_REQUIRED: (
        "prescription required", "do i need a prescription", "need prescription",
        "ప్రిస్క్రిప్షన్ కావాలా", "పర్చా కావాలా", "पर्चा ज़रूरी",
    ),
    Intent.SAVINGS_CHECK: (
        "savings", "how much can i save", "save money",
        "పొదుపు", "ఎంత పొదుపు", "बचत", "कितनी बचत",
    ),
    Intent.PHARMACY_AVAILABILITY: (
        "in stock", "stock available", "is it available", "out of stock",
        "స్టాక్", "అందుబాటులో", "स्टॉक", "उपलब्ध",
    ),
    Intent.RECORD_SUMMARY: (
        "summarize my", "summary of my records", "my reports summary",
        "summarize my lab reports", "medical history summary",
        "నా రిపోర్ట్ల సారాంశం", "सारांश", "मेरी रिपोर्ट का सारांश",
    ),
    Intent.FAMILY_RECORD_SUMMARY: (
        "summarize my father", "summarize my mother", "summarize my husband",
        "summarize my wife", "summarize my son", "summarize my daughter",
        "family member records", "caregiver access",
        "నా తండ్రి రిపోర్ట్ల", "నా తల్లి రిపోర్ట్ల", "కుటుంబ సభ్యుల రికార్డులు",
        "मेरे पिता की रिपोर्ट", "मेरी माता की रिपोर्ट", "परिवार के रिकॉर्ड",
    ),
    Intent.HEALTH_RECORD: (
        "record", "report upload", "my documents", "health vault", "రికార్డ్", "నా ఫైల్",
        "रिकॉर्ड", "दस्तावेज़",
    ),
    Intent.PRESCRIPTION: (
        "prescription", "rx", "ప్రిస్క్రిప్షన్", "సైకిల్ ఆఫ్ మందు", "पर्चा", "प्रेस्क्रिप्शन",
    ),
    Intent.LAB_REPORT: (
        "lab report", "blood test", "lab test", "x ray", "x-ray", "scan", "mri", "ct scan",
        "ల్యాబ్", "రక్త పరీక్ష", "స్కాన్", "लैब", "ब्लड टेस्ट", "जांच",
    ),
    Intent.INSURANCE: (
        "insurance", "policy", "premium", "coverage", "renewal", "భీమా", "పాలసీ", "बीमा", "पॉलिसी",
    ),
    Intent.INSURANCE_CLAIM: (
        "claim", "reimburse", "cashless", "denied claim", "క్లెయిమ్", "दावा", "क्लेम",
    ),
    Intent.APPOINTMENT: (
        "appointment", "book", "slot", "schedule", "reschedule", "cancel appointment",
        "అపాయింట్‌మెంట్", "బుక్", "अपॉइंटमेंट", "बुक",
    ),
    Intent.PAYMENT: (
        "payment", "pay", "refund", "transaction", "bill", "చెల్లింపు", "డబ్బు", "भुगतान", "रिफंड",
    ),
    Intent.FOLLOW_UP: (
        "follow up", "followup", "next visit", "review visit", "తర్వాత భేటీ", "फॉलो अप", "अगली विजिट",
    ),
    Intent.FAMILY_HEALTH: (
        "my mother", "my father", "my wife", "my husband", "my son", "my daughter", "family",
        "కుటుంబ", "నా అమ్మ", "నా నాన్న", "परिवार", "मेरी मां", "मेरे पिता",
    ),
    Intent.SUPPORT: (
        "complaint", "help me", "support", "customer care", "problem with app", "refund issue",
        "సపోర్ట్", "ఫిర్యాదు", "సహాయం", "सहायता", "शिकायत",
    ),
    Intent.HEALTH_EDUCATION: (
        "what is", "how to prevent", "symptoms of", "information about", "explain", "diet for",
        "what are", "అంటే ఏమిటి", "ఎలా", "क्या है", "कैसे",
    ),
    Intent.SYMPTOM_INFORMATION: (
        "pain", "fever", "cough", "cold", "symptom", "hurt", "swelling", "tired", "vomit",
        "diarrhea", "నొప్పి", "జ్వరం", "దగ్గు", "జలుబు", "వాంతులు", "बुखार", "खांसी", "दर्द", "उल्टी",
    ),
}
