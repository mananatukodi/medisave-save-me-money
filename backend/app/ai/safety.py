"""AI safety layer (spec §11, §38): emergency screening + response validation.

Every AI response passes through validate_response before returning to a user.
Emergency screening runs FIRST — before any intent scoring.
"""

from dataclasses import dataclass, field

# Red-flag phrases per urgency tier. English + Telugu + Hindi.
EMERGENCY_PHRASES = (
    "chest pain", "crushing chest", "heart attack", "can't breathe", "cannot breathe",
    "not breathing", "severe bleeding", "bleeding heavily", "unconscious", "collapsed",
    "stroke", "slurred speech", "face drooping", "seizure now", "fits now", "poison",
    "overdose", "suicid", "kill myself", "end my life", "severe burn", "drowned",
    "snake bite", "snakebite", "severe allergic", "anaphyla",
    "గుండె నొప్పి", "ఊపిరి", "రక్తం", "స్పృహ", "కుప్పకూల", "వణుకు", "విషం", "ఆత్మహత్య",
    "పాము", "కాటు", "छाती में दर्द", "सांस नहीं", "खून", "बेहोश", "स्ट्रोक", "दौरा",
    "जहर", "आत्महत्या", "सांप",
)

URGENT_PHRASES = (
    "high fever", "fever for", "vomiting blood", "blood in stool", "severe pain",
    "severe headache", "worst headache", "broken bone", "can't walk", "cannot walk",
    "dehydrated", "baby fever", "infant fever", "fainted",
    "ఎక్కువ జ్వరం", "తీవ్ర నొప్పి", "రక్తంతో వాంతులు", "తీవ్ర తలనొప్పి",
    "तेज बुखार", "तेज दर्द", "बच्चे को बुखार",
)


@dataclass
class Urgency:
    level: str  # EMERGENCY | URGENT | ROUTINE
    matched: list[str] = field(default_factory=list)
    requires_human_review: bool = False


def screen_urgency(text: str) -> Urgency:
    """Scan free text for emergency/urgent red flags (spec §11, §38)."""
    lowered = (text or "").lower()
    for phrase in EMERGENCY_PHRASES:
        if phrase in lowered:
            return Urgency(level="EMERGENCY", matched=[phrase], requires_human_review=True)
    for phrase in URGENT_PHRASES:
        if phrase in lowered:
            return Urgency(
                level="URGENT",
                matched=[phrase],
                requires_human_review=True,
            )
    return Urgency(level="ROUTINE")


DISALLOWED_CLAIM_PATTERNS = (
    "you have", "you definitely have", "you are diagnosed", "i diagnose",
    "certain cure", "guaranteed cure", "100% cure", "guaranteed result",
    "guaranteed claim approval", "guaranteed insurance approval",
    "guaranteed treatment outcome", "guaranteed outcome",
    "stop taking your medicine", "stop your medication",
)

MANDATORY_DISCLAIMER = (
    "This is general health information, not a diagnosis. "
    "Please consult a qualified healthcare professional."
)


def validate_response_text(text: str) -> list[str]:
    """Return a list of safety problems found in the drafted text (empty = safe)."""
    lowered = (text or "").lower()
    return [pattern for pattern in DISALLOWED_CLAIM_PATTERNS if pattern in lowered]


def enforce_safe_text(text: str) -> str:
    """Replace disallowed claims with neutral wording before returning to users."""
    safe = text or ""
    for pattern in DISALLOWED_CLAIM_PATTERNS:
        if pattern in safe.lower():
            safe = safe.replace(pattern, "this may be related to")
            safe = safe.replace(pattern.capitalize(), "This may be related to")
    return safe
