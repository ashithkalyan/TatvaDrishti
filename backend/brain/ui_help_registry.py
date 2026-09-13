"""
KAVACH Brain — UI Knowledge Registry Resolver
=================================================
Backend half of the Hovering Assistant's "what's next to the send
button" natural-language path (see frontend/src/hoverAssistant/ and
KAVACH_vs_DRISHTI_Analysis.md's write-up of the feature).

Point-and-click inspector mode and "left of / next to" spatial phrases
never reach this file — those are answered entirely client-side, by
construction, using document.elementFromPoint() and
getBoundingClientRect() against the live UI Knowledge Registry (a React
context of every <HelpTarget> currently mounted). There is no ambiguity
to resolve there, so there is nothing for the backend to do.

This module exists for the remaining case: an officer TYPES or SPEAKS a
question without pointing — "what's the paperclip for", "what does
attach file do". That's genuinely the same shape of problem
alias_resolver.py already solves for Indian name/nickname matching
("Manja" should still find "Manjunath Gowda") — an officer's short,
informal phrase needs to be matched against a set of known
formal/informal labels. Rather than write a second fuzzy matcher, this
module reuses alias_resolver.resolve_name() verbatim: every registered
element's label + keywords become the "known_names" list, and each
meaningful word in the officer's question is matched against it the
same way a name would be.

Zero external calls, zero ML — same guarantee as the rest of KAVACH's
brain. The frontend sends the CURRENT screen's registered elements on
every call (never the backend's own idea of what's on screen, since
only the browser knows what's actually rendered right now), so a
match can only ever point at something genuinely visible.
"""
from . import alias_resolver

# Words that carry no signal about WHICH element the officer means —
# stripped before matching so they never crowd out the words that
# actually do (a label/keyword itself is never one of these; if a team
# member ever names an element "Tab" or "Menu" literally, add it as a
# multi-word label instead so the whole-label substring pass below
# still catches it).
_STOPWORDS = {
    "what", "is", "this", "that", "the", "a", "an", "does", "do", "for",
    "of", "on", "in", "to", "how", "i", "can", "find", "where", "it",
    "thing", "used", "use", "mean", "means", "about", "here", "there",
    "click", "clicked", "clicking", "tap", "tapped", "tapping", "app",
    "kavach", "and", "or", "me", "my", "you", "your", "please", "just",
}

_METHOD_LABELS = {
    "exact": "exact match",
    "alias_dictionary": "known alias",
    "transliteration_variant": "spelling variant",
    "phonetic": "sounds-like match",
    "fuzzy": "close spelling match",
}


def _content_tokens(text: str) -> list:
    import re
    words = re.findall(r"[a-zA-Z]+", (text or "").lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def resolve_ui_query(query: str, candidates: list, min_fuzzy: float = 0.72) -> list:
    """
    query: the officer's typed/spoken question, e.g. "what's the paperclip for"
    candidates: [{"id": str, "label": str, "keywords": [str, ...]}, ...] —
        every <HelpTarget> currently registered on the officer's screen,
        as sent by the frontend (frontend/src/hoverAssistant/uiIntentRouter.js).

    Returns ranked, explainable matches:
        [{"id", "label", "confidence", "reason"}, ...] sorted descending,
        one entry per candidate element (best score kept).
    """
    if not query or not candidates:
        return []

    q_lower = query.lower()
    best = {}  # id -> {"id","label","confidence","reason"}
    labels_by_id = {c["id"]: (c.get("label") or c["id"]) for c in candidates if c.get("id")}

    def _consider(cid, confidence, reason):
        if cid not in labels_by_id:
            return
        confidence = round(min(confidence, 1.0), 2)
        cur = best.get(cid)
        if cur is None or confidence > cur["confidence"]:
            best[cid] = {"id": cid, "label": labels_by_id[cid], "confidence": confidence, "reason": reason}

    # 1. Whole-label substring — the officer typed the label itself, or
    #    most of it ("what does attach file do"). Checked before the
    #    token-level pass because a direct label mention is the
    #    strongest possible signal, stronger than any single-word match.
    for c in candidates:
        label = (c.get("label") or "").strip()
        if label and len(label) > 2 and label.lower() in q_lower:
            _consider(c["id"], 0.97, f'You mentioned "{label}" directly')

    # 2. Token-level reuse of alias_resolver.resolve_name() — every
    #    element's label + keywords flattened into one "known_names"
    #    list, matched the same way a spoken nickname would be.
    flat_names = []
    owner = {}  # lowercased flat name -> [element ids]
    for c in candidates:
        if not c.get("id"):
            continue
        for n in [c.get("label") or ""] + list(c.get("keywords") or []):
            n = (n or "").strip()
            if not n:
                continue
            flat_names.append(n)
            owner.setdefault(n.lower(), []).append(c["id"])

    for token in _content_tokens(query):
        matches = alias_resolver.resolve_name(token, flat_names, min_fuzzy=min_fuzzy)
        for m in matches[:5]:
            method_label = _METHOD_LABELS.get(m["method"], m["method"])
            # Slightly de-weight a phonetic/fuzzy guess relative to an
            # exact or dictionary hit, so a strong keyword match always
            # outranks a loose one for the same element.
            conf = m["confidence"] if m["method"] in ("exact", "alias_dictionary") else m["confidence"] * 0.9
            for cid in owner.get(m["name"].lower(), []):
                _consider(cid, conf,
                          f'"{token}" matched "{m["name"]}" ({method_label}, {int(round(conf * 100))}% confidence)')

    return sorted(best.values(), key=lambda r: -r["confidence"])
