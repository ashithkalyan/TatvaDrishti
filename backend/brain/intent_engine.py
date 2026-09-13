"""
KAVACH Brain — Intent Classification
=======================================
Pattern + entity based intent classifier. Deterministic and
extensible: each intent maps to a specific SQL template in
sql_builder.py, so the mapping from "what the officer meant" to "what
query ran" is always inspectable — no black box in between.
"""
import re

from . import entity_extractor

INTENT_PATTERNS = [
    ("hotspot_ops_query", [r'hotspot operation', r'patrol logbook', r'operations logbook', r'patrol activity',
                            r'patrol team', r'hotspot action', r'pending hotspot', r'hotspot recommendation',
                            r'\blogbook\b', r'patrol log', r'operations? (completed|started|assigned)']),
    ("repeat_offender_search", [r'repeat offend', r'habitual', r'multiple (fir|conviction|case)',
                                 r'appears? in (multiple|several|\d+) fir']),
    ("gang_query", [r'\bgang\b', r'syndicate', r'organi[sz]ed crime']),
    ("network_query", [r'network', r'connect(ed|ion)', r'associat', r'linked to',
                        r'who.*(he|she|they).*(know|linked)', r'phone', r'vehicle.*linked', r'hidden.*link']),
    ("risk_query", [r'risk score', r'high.?risk', r'extreme risk', r'dangerous', r'most wanted']),
    ("prediction_query", [r'forecast', r'predict', r'next month', r'likely to', r'expect.*increase', r'trend.*next']),
    ("similarity_query", [r'similar case', r'linked case', r'same (mo|pattern|method)', r'case linkage']),
    ("statistics_query", [r'how many', r'total (number|count)', r'trend', r'increas', r'decreas',
                           r'compare', r'which (district|station|area).*(highest|most|lowest)']),
    ("case_status_query", [r'status of', r'pending', r'under investigation', r'charge.?sheet', r'closed case']),
    ("timeline_query", [r'timeline', r'investigation (history|progress)', r'what happened (in|to)']),
    ("recommendation_query", [r'what should', r'next steps?', r'leads?', r'recommend']),
    ("person_lookup", [r'\bwho is\b', r'history of', r'profile of', r'tell me about', r'show.*history']),
    ("crime_type_search", [r'\b(murder|theft|robbery|burglary|assault|kidnap|rape|fraud|cyber|drug|dacoity|chain snatching)\b']),
    ("location_search", [r'\bin (bengaluru|bangalore|mysuru|mysore|hubballi|mangaluru|mangalore|belagavi|'
                          r'kalaburagi|davanagere|shivamogga|tumakuru|vijayapura|ballari)\b']),
]

FOLLOW_UP_PREFIXES = re.compile(r'^(only|just|filter|now show|among|from (these|those)|what about)')

# ── UI-help detection ────────────────────────────────────────────────
# KAVACH's floating "Hovering Assistant" (frontend: HoveringAssistant.jsx)
# is the PRIMARY route for questions about the app's own interface —
# "what does this button do", point-and-click inspector mode, etc. It
# resolves those entirely client-side against the live UI Knowledge
# Registry (frontend/src/hoverAssistant/) plus a small reuse of
# alias_resolver.resolve_name() via /api/ui-help/resolve, and never
# touches this case-data pipeline at all.
#
# This pattern set is the SAFETY NET for the other door into KAVACH: an
# officer typing a UI question straight into the ordinary case-chat box
# (CrimeChat.jsx) instead of using the assistant. Before this existed,
# "what does the paperclip icon do" fell through to the generic
# case-query pipeline, searched for zero matching records, and answered
# with a confusing "no records found" — a real UX dead end for a
# question that has a perfectly good answer, just not a database one.
#
# Deliberately narrow: fires ONLY when the message carries BOTH a
# question shape (what is/does this, how do i, where can i find) AND an
# explicit UI-chrome noun (button, icon, tab, menu, panel...). Requiring
# both keeps real case questions safe — "where is Manjunath now" or
# "what is his risk score" match the question shape alone, but never a
# UI noun, so they fall through to the normal pipeline exactly as
# before. Checked in brain.py alongside general_knowledge, gated the
# same way (only when the message carries no case-query entities).
UI_HELP_QUESTION_PATTERNS = [
    r'\bwhat is this\b', r'\bwhat does this\b', r"\bwhat'?s this\b",
    r'\bwhat is that\b', r'\bwhat does that\b', r"\bwhat'?s that\b",
    r'\bhow do i\b', r'\bhow does .* work\b', r'\bhow can i\b',
    r'\bwhere (is|can i find|do i)\b',
    r'\bwhat (is|does|are) (the|this|that)\b',
]
UI_HELP_TARGET_PATTERNS = [
    r'\bbutton\b', r'\bicon\b', r'\btab\b', r'\bmenu\b', r'\bdropdown\b',
    r'\bpanel\b', r'\bscreen\b', r'\bpage\b', r'\btoolbar\b', r'\bsidebar\b',
    r'\bsymbol\b', r'\bwidget\b', r'\btoggle\b', r'\bchip\b', r'\btooltip\b',
    r'\bfeature\b', r'\boption\b', r'\bclick(ed|ing)?\b', r'\btap(ped|ping)?\b',
    r'\bthis (thing|do[ck]hickey)\b', r'\bapp\b',
]


def is_ui_help_query(text: str) -> bool:
    """True only when the message reads as a question about the KAVACH
    interface itself, never about case data — see module note above."""
    t = text.lower().strip()
    has_question = any(re.search(p, t) for p in UI_HELP_QUESTION_PATTERNS)
    has_target = any(re.search(p, t) for p in UI_HELP_TARGET_PATTERNS)
    return has_question and has_target


# Small, fixed bilingual redirect — same honesty-note convention as
# response_generator.py's TEMPLATES: best-effort Kannada, not yet
# reviewed by a native speaker.
UI_HELP_REDIRECT = {
    "en": (
        "That sounds like a question about the KAVACH screen itself, not the case data — "
        "I can only search records here. Tap the assistant badge in the bottom-right corner "
        "and either point at the exact button/icon you mean, or type the same question there — "
        "it reads the live screen and answers instantly, no database search needed."
    ),
    "kn": (
        "ಇದು ಪ್ರಕರಣದ ಡೇಟಾದ ಬಗ್ಗೆ ಅಲ್ಲ, KAVACH ಪರದೆಯ ಬಗ್ಗೆ ಪ್ರಶ್ನೆಯಂತೆ ಕಾಣುತ್ತದೆ — ಇಲ್ಲಿ ನಾನು ಕೇವಲ "
        "ದಾಖಲೆಗಳನ್ನು ಹುಡುಕಬಲ್ಲೆ. ಬಲ ಕೆಳಭಾಗದಲ್ಲಿರುವ ಸಹಾಯಕ ಬ್ಯಾಡ್ಜ್ ಒತ್ತಿ, ನೀವು ಕೇಳುತ್ತಿರುವ ಬಟನ್/ಐಕಾನ್ "
        "ಅನ್ನು ತೋರಿಸಿ ಅಥವಾ ಅದೇ ಪ್ರಶ್ನೆಯನ್ನು ಅಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ — ಅದು ಪರದೆಯನ್ನು ನೇರವಾಗಿ ಓದಿ ತಕ್ಷಣ "
        "ಉತ್ತರಿಸುತ್ತದೆ, ಡೇಟಾಬೇಸ್ ಹುಡುಕಾಟ ಬೇಕಿಲ್ಲ."
    ),
}


def classify(text: str, entities: dict, has_prior_context: bool = False) -> dict:
    t = text.lower().strip()

    if has_prior_context and FOLLOW_UP_PREFIXES.match(t):
        return {"intent": "follow_up_filter", "confidence": 0.85,
                "matched_pattern": "follow-up refinement phrase"}

    for intent, patterns in INTENT_PATTERNS:
        for p in patterns:
            if re.search(p, t):
                return {"intent": intent, "confidence": 0.8, "matched_pattern": p}

    if entity_extractor.has_reliable_name_signal(text, entities.get("person_name_candidates")):
        return {"intent": "person_lookup", "confidence": 0.5, "matched_pattern": "name detected, no explicit verb"}
    if entities.get("crime_types"):
        return {"intent": "crime_type_search", "confidence": 0.6, "matched_pattern": "crime type detected"}
    return {"intent": "general_search", "confidence": 0.3, "matched_pattern": "no strong signal — recent records"}
