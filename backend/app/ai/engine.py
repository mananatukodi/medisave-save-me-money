"""AI guidance engine implementing the spec §11 pipeline:

Authentication → Consent check → Emergency screening → Intent classification
→ Context retrieval → AI processing → Safety validation → Structured response
→ Navigation/action → Audit.

Provider note: with MEDISAVE_AI_PROVIDER=none (current default) the "AI
processing" step is the deterministic guidance renderer below — no external LLM
is called. A real LLM provider REQUIRES INTEGRATION (app/ai/providers.py).
"""

from dataclasses import dataclass

from app.ai.classifier import classify_intent
from app.ai.intents import Intent
from app.ai.safety import (
    MANDATORY_DISCLAIMER,
    Urgency,
    enforce_safe_text,
    screen_urgency,
    validate_response_text,
)

DISCLAIMER_TE = "ఇది సాధారణ ఆరోగ్య సమాచారం మాత్రమే, రోగనిర్ధారణ కాదు. అర్హమైన వైద్య నిపుణుడిని సంప్రదించండి."
DISCLAIMER_HI = "यह सामान्य स्वास्थ्य जानकारी है, निदान नहीं। कृपया योग्य स्वास्थ्य पेशेवर से परामर्श करें।"

EMERGENCY_MESSAGE = (
    "This may be a medical emergency. Please seek immediate care: "
    "call your local emergency number (India: 108) or go to the nearest hospital now. "
    "Do not wait for an online reply."
)
EMERGENCY_MESSAGE_TE = (
    "ఇది వైద్య అత్యవసర పరిస్థితి కావచ్చు. వెంటనే 108కి కాల్ చేయండి లేదా సమీప ఆసుపత్రికి వెళ్లండి."
)
EMERGENCY_MESSAGE_HI = (
    "यह एक चिकित्सा आपातकाल हो सकता है। तुरंत 108 पर कॉल करें या नज़दीकी अस्पताल जाएं।"
)

URGENT_MESSAGE = (
    "Your description may need prompt medical attention. "
    "Please consider visiting a doctor within 24 hours or using the SOS button if it worsens."
)


@dataclass
class AIAction:
    label_en: str
    label_te: str
    label_hi: str
    route: str  # in-app navigation route


@dataclass
class AIResponse:
    intent: str
    urgency: str
    message: str
    disclaimer: str
    red_flags: list[str]
    recommended_actions: list[str]
    navigation: list[AIAction]
    requires_human_review: bool
    confidence: float

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "urgency": self.urgency,
            "message": self.message,
            "disclaimer": self.disclaimer,
            "redFlags": self.red_flags,
            "recommendedActions": self.recommended_actions,
            "navigation": [
                {"label_en": a.label_en, "label_te": a.label_te, "label_hi": a.label_hi, "route": a.route}
                for a in self.navigation
            ],
            "requiresHumanReview": self.requires_human_review,
            "confidence": self.confidence,
        }


SPECIALTY_INTENTS: dict[Intent, tuple[str, str, str]] = {
    Intent.EYE_CARE: ("Eye Care", "కంటి సంరక్షణ", "आंखों की देखभाल"),
    Intent.DENTAL_CARE: ("Dental Care", "దంత సంరక్షణ", "दंत चिकित्सा"),
    Intent.CARDIOLOGY: ("Cardiology", "గుండె జబ్బుల వైద్యం", "हृदय रोग विज्ञान"),
    Intent.PEDIATRICS: ("Pediatrics", "పిల్లల వైద్యం", "बाल चिकित्सा"),
    Intent.ORTHOPEDICS: ("Orthopedics", "ఎముకల వైద్యం", "अस्थि रोग"),
    Intent.DERMATOLOGY: ("Dermatology", "చర్మ వ్యాధులు", "त्वचा रोग"),
    Intent.ENT: ("ENT", "చెవి-ముక్కు-గొంతు", "कान-नाक-गला"),
    Intent.NEUROLOGY: ("Neurology", "నాడీ వ్యవస్థ", "न्यूरोलॉजी"),
    Intent.GYNECOLOGY: ("Gynecology", "స్త్రీ జననేంద్రియ వైద్యం", "स्त्री रोग"),
}

INTENT_ROUTES: dict[str, str] = {
    Intent.DOCTOR_SEARCH.value: "/doctors",
    Intent.HOSPITAL_SEARCH.value: "/hospitals",
    Intent.SPECIALIST_SEARCH.value: "/specialties",
    Intent.PHARMACY_SEARCH.value: "/pharmacies",
    Intent.PHARMACY_AVAILABILITY.value: "/medicines",
    Intent.MEDICINE_SEARCH.value: "/medicines",
    Intent.MEDICINE_INFORMATION.value: "/medicines",
    Intent.MEDICINE_PRICE.value: "/medicines/savings",
    Intent.MEDICINE_COMPARISON.value: "/medicines/savings",
    Intent.MEDICINE_ORDER.value: "/orders",
    Intent.PRESCRIPTION_REQUIRED.value: "/prescriptions",
    Intent.SAVINGS_CHECK.value: "/medicines/savings",
    Intent.HEALTH_RECORD.value: "/records",
    Intent.PRESCRIPTION.value: "/prescriptions",
    Intent.LAB_REPORT.value: "/labs",
    Intent.RECORD_SUMMARY.value: "/records",
    Intent.FAMILY_RECORD_SUMMARY.value: "/family",
    Intent.INSURANCE.value: "/insurance",
    Intent.INSURANCE_CLAIM.value: "/claims",
    Intent.APPOINTMENT.value: "/appointments",
    Intent.PAYMENT.value: "/payments",
    Intent.FOLLOW_UP.value: "/appointments",
    Intent.FAMILY_HEALTH.value: "/family",
    Intent.SUPPORT.value: "/support",
    Intent.HEALTH_EDUCATION.value: "/education",
    Intent.EYE_CARE.value: "/specialties/eye-care",
    Intent.DENTAL_CARE.value: "/specialties/dental-care",
    Intent.CARDIOLOGY.value: "/specialties/cardiology",
    Intent.PEDIATRICS.value: "/specialties/pediatrics",
    Intent.ORTHOPEDICS.value: "/specialties/orthopedics",
    Intent.DERMATOLOGY.value: "/specialties/dermatology",
    Intent.ENT.value: "/specialties/ent",
    Intent.NEUROLOGY.value: "/specialties/neurology",
    Intent.GYNECOLOGY.value: "/specialties/gynecology",
}

# Phase 4 medicine guidance (spec §13, §21, §22): navigation-first, safety-first.
# The assistant never prescribes, never changes dosage, never invents prices,
# never claims a prescription was verified, and never recommends substitution.
MEDICINE_GUIDANCE: dict[Intent, str] = {
    Intent.MEDICINE_SEARCH: (
        "I can help you look up medicines, check availability at verified "
        "pharmacies, and compare verified prices. I cannot prescribe or "
        "recommend a specific medicine for your condition — please confirm any "
        "medicine with a qualified doctor or pharmacist."
    ),
    Intent.MEDICINE_INFORMATION: (
        "I can show basic medicine information recorded from verified sources. "
        "For dosage, interactions, or whether a medicine is right for you, "
        "please consult a doctor or pharmacist."
    ),
    Intent.MEDICINE_PRICE: (
        "I can show verified prices with their source and last-updated date, "
        "and potential savings where verified data allows it. I never invent "
        "prices — if verified data is unavailable, I will say so."
    ),
    Intent.MEDICINE_COMPARISON: (
        "I can show verified price comparisons for the exact same pack size, "
        "strength, and dosage form. I do not recommend substituting a "
        "prescribed medicine — please confirm any change with your doctor or "
        "pharmacist."
    ),
    Intent.PHARMACY_SEARCH: (
        "I can help you find verified pharmacies, including delivery and "
        "pickup options."
    ),
    Intent.PHARMACY_AVAILABILITY: (
        "I can show stock status exactly as reported by verified pharmacies. "
        "Unknown stock is never shown as available."
    ),
    Intent.MEDICINE_ORDER: (
        "I can guide you through ordering from a verified pharmacy. "
        "Prescription-required medicines need a valid prescription reviewed by "
        "the pharmacy before confirmation."
    ),
    Intent.PRESCRIPTION_REQUIRED: (
        "Some medicines legally require a prescription. MediSave AI cannot "
        "verify or approve prescriptions automatically — a verified pharmacy "
        "reviews submitted prescriptions."
    ),
    Intent.SAVINGS_CHECK: (
        "I can calculate potential savings only from verified price data. "
        "When verified data is insufficient, I will tell you instead of "
        "estimating."
    ),
}

# Phase 5 record-summary guidance (spec §14): the assistant NEVER reads or
# sends health records automatically. A real summary pipeline requires the
# patient's explicit per-request authorization, minimum-necessary scope, and
# an audited AI access event — REQUIRES PRODUCTION INTEGRATION (LLM with PHI
# controls). Until then the response is honest navigation, never fabricated
# record content.
RECORD_SUMMARY_GUIDANCE = (
    "I cannot read or summarize your health records automatically. "
    "Record summaries require your explicit authorization for each request, "
    "and that secure processing is not available yet. You can open your "
    "Health Vault to view, download, or share specific records yourself."
)
RECORD_SUMMARY_GUIDANCE_TE = (
    "మేము మీ ఆరోగ్య రికార్డులను స్వయంగా చదవము లేదా సారాంశం చేయము. "
    "ప్రతి అభ్యర్థనకు మీ స్పష్టమైన అనుమతి అవసరం, ఆ సురక్షిత ప్రాసెసింగ్ "
    "ఇంకా అందుబాటులో లేదు. నిర్దిష్ట రికార్డులను మీరే చూడవచ్చు లేదా పంచవచ్చు."
)
RECORD_SUMMARY_GUIDANCE_HI = (
    "मैं आपके स्वास्थ्य रिकॉर्ड स्वतः नहीं पढ़ सकता या सारांश नहीं बना सकता। "
    "हर अनुरोध के लिए आपकी स्पष्ट अनुमति आवश्यक है, और वह सुरक्षित प्रोसेसिंग "
    "अभी उपलब्ध नहीं है। आप अपने Health Vault में रिकॉर्ड स्वयं देख या साझा कर सकते हैं।"
)

MEDICINE_GUIDANCE_TE: dict[Intent, str] = {
    Intent.MEDICINE_SEARCH: (
        "మీకు మందులు వెతకడంలో, ధృవీకరించిన ఫార్మసీల్లో లభ్యత చూడటంలో, ధరలు పోల్చడంలో "
        "సహాయపడతాము. మేము మందులు సూచించము — దయచేసి అర్హమైన వైద్యుడిని లేదా ఫార్మసిస్ట్‌ను సంప్రదించండి."
    ),
    Intent.MEDICINE_INFORMATION: (
        "మేము ధృవీకరించిన మూలాల నుండి ప్రాథమిక మందు సమాచారం చూపిస్తాము. "
        "మోతాదు లేదా అనుబంధాల కోసం వైద్యుడిని లేదా ఫార్మసిస్ట్‌ను సంప్రదించండి."
    ),
    Intent.MEDICINE_PRICE: (
        "మేము మూలం మరియు చివరిగా నవీకరించిన తేదీతో సహా ధృవీకరించిన ధరలు చూపిస్తాము. "
        "ధృవీకరించిన సమాచారం లేకపోతే అదే చెబుతాము — ధరలు కల్పించము."
    ),
    Intent.MEDICINE_COMPARISON: (
        "అదే ప్యాక్, స్ట్రెంత్ మరియు ఫారమ్ కోసం మాత్రమే ధృవీకరించిన ధర పోలిక చూపుతాము. "
        "సూచించిన మందును మార్చమని మేము సిఫార్సు చేయము — వైద్యుడిని సంప్రదించండి."
    ),
    Intent.PHARMACY_SEARCH: "డెలివరీ మరియు పికప్ ఎంపికలతో ధృవీకరించిన ఫార్మసీలను కనుగొనడంలో సహాయపడతాము.",
    Intent.PHARMACY_AVAILABILITY: (
        "ఫార్మసీ నివేదించిన స్టాక్ స్థితిని అలాగే చూపుతాము. "
        "తెలియని స్టాక్‌ను అందుబాటులో ఉన్నట్టు చూపము."
    ),
    Intent.MEDICINE_ORDER: (
        "ధృవీకరించిన ఫార్మసీ నుండి ఆర్డర్ చేయడానికి మార్గనిర్దేశం చేస్తాము. "
        "ప్రిస్క్రిప్షన్ అవసరమైన మందులకు ఫార్మసీ సమీక్ష అవసరం."
    ),
    Intent.PRESCRIPTION_REQUIRED: (
        "కొన్ని మందులకు చట్టబద్ధంగా ప్రిస్క్రిప్షన్ అవసరం. "
        "MediSave AI ప్రిస్క్రిప్షన్‌లను ధృవీకరించదు — ధృవీకరించిన ఫార్మసీ సమీక్షిస్తుంది."
    ),
    Intent.SAVINGS_CHECK: (
        "మేము ధృవీకరించిన ధర డేటా నుండి మాత్రమే పొదుపు లెక్కిస్తాము. "
        "డేటా సరిపోకపోతే అంచనా వేయకుండా అదే చెబుతాము."
    ),
}

MEDICINE_GUIDANCE_HI: dict[Intent, str] = {
    Intent.MEDICINE_SEARCH: (
        "मैं दवाइयाँ खोजने, सत्यापित फार्मेसियों में उपलब्धता देखने और सत्यापित "
        "कीमतों की तुलना करने में मदद कर सकता हूँ। मैं दवा लिख नहीं सकता — "
        "कृपया योग्य डॉक्टर या फार्मासिस्ट से पुष्टि करें।"
    ),
    Intent.MEDICINE_INFORMATION: (
        "मैं सत्यापित स्रोतों से बुनियादी दवा जानकारी दिखा सकता हूँ। "
        "खुराक या इंटरैक्शन के लिए कृपया डॉक्टर या फार्मासिस्ट से मिलें।"
    ),
    Intent.MEDICINE_PRICE: (
        "मैं स्रोत और अंतिम अपडेट के साथ सत्यापित कीमतें दिखा सकता हूँ। "
        "सत्यापित डेटा न होने पर मैं वही कहूँगा — कीमतें नहीं गढ़ूँगा।"
    ),
    Intent.MEDICINE_COMPARISON: (
        "मैं केवल उसी पैक, स्ट्रेंथ और फॉर्म की सत्यापित कीमत तुलना दिखाता हूँ। "
        "मैं दवा बदलने की सलाह नहीं देता — कृपया डॉक्टर से मिलें।"
    ),
    Intent.PHARMACY_SEARCH: "डिलीवरी और पिकअप विकल्पों के साथ सत्यापित फार्मेसियाँ खोजने में मदद करता हूँ।",
    Intent.PHARMACY_AVAILABILITY: (
        "मैं फार्मेसी की बताई स्टॉक स्थिति जैसी है वैसी दिखाता हूँ। "
        "अज्ञात स्टॉक को उपलब्ध नहीं दिखाते।"
    ),
    Intent.MEDICINE_ORDER: (
        "मैं सत्यापित फार्मेसी से ऑर्डर करने में मार्गदर्शन करता हूँ। "
        "प्रिस्क्रिप्शन आवश्यक दवाओं को फार्मेसी समीक्षा चाहिए।"
    ),
    Intent.PRESCRIPTION_REQUIRED: (
        "कुछ दवाओं को कानूनी रूप से प्रिस्क्रिप्शन चाहिए। "
        "MediSave AI प्रिस्क्रिप्शन सत्यापित नहीं करता — सत्यापित फार्मेसी समीक्षा करती है।"
    ),
    Intent.SAVINGS_CHECK: (
        "मैं केवल सत्यापित कीमत डेटा से बचत गणना करता हूँ। "
        "डेटा अपर्याप्त होने पर अनुमान लगाने के बजाय बता दूँगा।"
    ),
}

SPECIALTY_GUIDANCE = {
    Intent.EYE_CARE: (
        "For eye concerns, start with a vision screening by an optometrist or an "
        "ophthalmologist consultation. If you are diabetic, schedule a diabetic eye "
        "screening at least once a year."
    ),
    Intent.DENTAL_CARE: (
        "For dental concerns, begin with a check-up and cleaning. Persistent tooth pain, "
        "swelling, or bleeding gums should be examined by a dentist promptly."
    ),
}


@dataclass
class PipelineContext:
    user_id: str
    language: str
    message: str
    session_id: str | None = None
    consent_active: bool = False


def _disclaimer_for(language: str) -> str:
    return {"te": DISCLAIMER_TE, "hi": DISCLAIMER_HI}.get(language, MANDATORY_DISCLAIMER)


def _emergency_response(language: str) -> AIResponse:
    message = {
        "te": EMERGENCY_MESSAGE_TE,
        "hi": EMERGENCY_MESSAGE_HI,
        "en": EMERGENCY_MESSAGE,
    }.get(language, EMERGENCY_MESSAGE)
    return AIResponse(
        intent=Intent.EMERGENCY.value,
        urgency="EMERGENCY",
        message=message,
        disclaimer=_disclaimer_for(language),
        red_flags=["possible emergency signs detected"],
        recommended_actions=[
            "Call 108 (India emergency) or reach the nearest hospital immediately",
            "Open Emergency SOS now",
            "Do not wait for online replies",
        ],
        navigation=[
            # Phase 7: the AI only ROUTES to the deterministic SOS flow — it
            # can never create, confirm, or delay an SOS itself.
            AIAction("Open SOS", "SOS తెరవండి", "SOS खोलें", "/emergency"),
            AIAction("Call 108", "108 కు కాల్ చేయండి", "108 पर कॉल करें", "tel:108"),
            AIAction("Nearby Hospitals", "సమీప ఆసుపత్రులు", "नज़दीकी अस्पताल", "/hospitals/nearby"),
        ],
        requires_human_review=True,
        confidence=1.0,
    )


def _guidance_for_intent(intent: Intent, language: str) -> AIResponse:
    route = INTENT_ROUTES.get(intent.value, "/specialties")
    if intent in SPECIALTY_INTENTS:
        en, te, hi = SPECIALTY_INTENTS[intent]
        guidance = SPECIALTY_GUIDANCE.get(intent)
        base = f"You can explore verified {en} providers and services in the {en} section."
        if guidance:
            base = guidance
        message = {
            "te": base + f" మీరు {te} విభాగంలో కొనసాగవచ్చు.",
            "hi": base + f" आप {hi} सेक्शन में आगे बढ़ सकते हैं.",
            "en": base,
        }.get(language, base)
        return AIResponse(
            intent=intent.value,
            urgency="ROUTINE",
            message=enforce_safe_text(message),
            disclaimer=_disclaimer_for(language),
            red_flags=[],
            recommended_actions=[
            "Review the listed services",
            "Book an appointment with a verified provider",
        ],
            navigation=[AIAction(en, te, hi, route)],
            requires_human_review=False,
            confidence=0.8,
        )

    if intent == Intent.RECORD_SUMMARY:
        message = {
            "te": RECORD_SUMMARY_GUIDANCE_TE,
            "hi": RECORD_SUMMARY_GUIDANCE_HI,
        }.get(language, RECORD_SUMMARY_GUIDANCE)
        return AIResponse(
            intent=intent.value,
            urgency="ROUTINE",
            message=enforce_safe_text(message),
            disclaimer=_disclaimer_for(language),
            red_flags=[],
            recommended_actions=[
                "Open the Health Vault",
                "Authorize any future AI summary explicitly per request",
            ],
            navigation=[AIAction("Health Vault", "ఆరోగ్య వాల్ట్", "हेल्थ वॉल्ट", "/records")],
            requires_human_review=False,
            confidence=0.8,
        )

    if intent == Intent.FAMILY_RECORD_SUMMARY:
        # Phase 6: AI never infers authorization from natural language. A
        # family member must hold an explicit, unexpired VIEW_HEALTH_RECORDS
        # consent; summaries of another person's records require the same
        # per-request authorization flow — not implemented, stated honestly.
        return AIResponse(
            intent=intent.value,
            urgency="ROUTINE",
            message=enforce_safe_text(
                {
                    "te": "కుటుంబ సభ్యుని ఆరోగ్య రికార్డుల సారాంశం కోసం ఆ వ్యక్తి స్పష్టమైన అనుమతి అవసరం. "
                         "కుటుంబ సంబంధం మాత్రంచే ప్రవేశం లభించదు. Family Access లో అనుమతులు చూడండి.",
                    "hi": "परिवार के सदस्य के स्वास्थ्य रिकॉर्ड का सारांश उस व्यक्ति की स्पष्ट अनुमति से ही संभव है। "
                         "केवल पारिवारिक संबंध से पहुँच नहीं मिलती। Family Access में अनुमतियाँ देखें।",
                }.get(
                    language,
                    "Access to a family member's records requires that person's explicit, "
                    "scoped consent — a family relationship alone grants nothing. I cannot "
                    "retrieve or summarize their records without it. Check permissions in "
                    "Family Access.",
                )
            ),
            disclaimer=_disclaimer_for(language),
            red_flags=[],
            recommended_actions=[
                "Ask the person to grant scoped consent in Family Access",
                "Open Family Access to review current permissions",
            ],
            navigation=[AIAction("Family Access", "కుటుంబ ప్రవేశం", "फैमिली एक्सेस", "/family")],
            requires_human_review=False,
            confidence=0.8,
        )

    if intent in MEDICINE_GUIDANCE:
        base = MEDICINE_GUIDANCE[intent]
        message = MEDICINE_GUIDANCE_TE.get(intent, base) if language == "te" else (
            MEDICINE_GUIDANCE_HI.get(intent, base) if language == "hi" else base
        )
        return AIResponse(
            intent=intent.value,
            urgency="ROUTINE",
            message=enforce_safe_text(message),
            disclaimer=_disclaimer_for(language),
            red_flags=[],
            recommended_actions=[
                "Open the suggested section",
                "Confirm any medicine decision with a doctor or pharmacist",
            ],
            navigation=[AIAction("Medicines & Savings", "మందులు & పొదుపు", "दवाइयाँ और बचत", route)],
            requires_human_review=False,
            confidence=0.75,
        )

    generic = (
        "I can help you navigate MediSave AI. Based on your message, "
        "I can point you to the right section. Remember: I provide navigation "
        "and general information — not a diagnosis."
    )
    message = {
        "te": "మేము మీకు సరైన విభాగానికి మార్గనిర్దేశం చేయగలము. ఇది రోగనిర్ధారణ కాదు.",
        "hi": "मैं आपको सही सेक्शन तक ले जा सकता हूँ। यह निदान नहीं है।",
    }.get(language, generic)
    return AIResponse(
        intent=intent.value,
        urgency="ROUTINE",
        message=message,
        disclaimer=_disclaimer_for(language),
        red_flags=[],
        recommended_actions=["Open the suggested section"],
        navigation=[AIAction(intent.value.replace("_", " ").title(), intent.value, intent.value, route)]
        if route in INTENT_ROUTES.values()
        else [],
        requires_human_review=False,
        confidence=0.6,
    )


def run_pipeline(context: PipelineContext, consent_active: bool | None = None) -> AIResponse:
    """Execute the safety pipeline. Raises PermissionError when consent is missing."""
    if consent_active is not None:
        context.consent_active = consent_active

    # Step 1: emergency screening BEFORE anything else.
    urgency: Urgency = screen_urgency(context.message)
    if urgency.level == "EMERGENCY":
        return _emergency_response(context.language)

    # Step 2: consent gate (spec §11, §30).
    if not context.consent_active:
        raise PermissionError("AI_ACCESS consent is required before using the AI Health Assistant")

    # Step 3: intent classification.
    intent, confidence, _ = classify_intent(context.message)

    # Step 4-6: guidance rendering + safety validation.
    response = _guidance_for_intent(intent, context.language)
    if urgency.level == "URGENT":
        response.urgency = "URGENT"
        response.red_flags = list({*response.red_flags, *urgency.matched})
        response.recommended_actions.insert(0, URGENT_MESSAGE)
        response.requires_human_review = True
    problems = validate_response_text(response.message)
    if problems:
        response.message = enforce_safe_text(response.message)

    return response
