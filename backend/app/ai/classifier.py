"""Rule-based intent classifier over the spec §10 intent set.

Deliberately deterministic and explainable; an LLM classifier can replace it
behind the same `classify_intent` interface without touching the safety pipeline.
"""

from app.ai.intents import INTENT_KEYWORDS, Intent


def classify_intent(text: str) -> tuple[Intent, float, dict[str, int]]:
    """Return (intent, confidence, per-intent match counts).

    Falls back to SYMPTOM_INFORMATION when nothing matches confidently.
    """
    lowered = (text or "").lower()
    scores: dict[str, int] = {}

    best_intent: Intent | None = None
    best_score = 0
    for intent, keywords in INTENT_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in lowered)
        if count > 0:
            scores[intent.value] = count
            if count > best_score:
                best_intent, best_score = intent, count

    if best_intent is None:
        return Intent.SYMPTOM_INFORMATION, 0.0, scores
    # Simple normalisation: proportion of the top intent's hits vs total hits.
    total = sum(scores.values())
    confidence = round(best_score / max(total, 1), 2)
    return best_intent, confidence, scores
