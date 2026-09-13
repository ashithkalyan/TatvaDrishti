"""
KAVACH Brain — Deterministic Response Generation
====================================================
Every fact in a response is grounded directly in query results —
nothing is generated freely by a language model. In a law-enforcement
context, a hallucinated fact (a fabricated conviction count, an
invented address) is not an acceptable failure mode, so KAVACH's
default path never lets a model invent the substance of an answer.

This module produces two things:
  1. `text` — a complete, correct, human-readable sentence or two.
     This is what ships when Ollama isn't running, and it is ALSO
     what ships for the zero-results case even when Ollama IS
     running (see the module docstring in ollama_client.py for why
     "no records found" is never handed to free generation).
  2. `facts` — a small, bounded, JSON-safe summary of the same
     answer (intent, result_count, a short sample of the actual
     rows). This is the ONLY input ollama_client.compose_conversational()
     is allowed to read from — the LLM polishes/rewrites `text` using
     `facts` as its ceiling, it cannot add anything `facts` doesn't
     already contain.

HONESTY NOTE ON THE KANNADA TEMPLATES: these are reasonable best-effort
translations of a small set of FIXED template strings — not machine
translation of arbitrary text, which is a very different (and far
riskier) problem. Have a native Kannada speaker on the team review
these before a real deployment, same as any language glossary
regardless of who wrote it.
"""
import random

from . import abbreviation_glossary

# Multiple phrasings per key so the deterministic fallback doesn't read
# like the same form letter on every single query — randomised choice is
# safe here because ONLY the wording varies, never the substance (n,
# names, and every other value are still interpolated from real data).
TEMPLATES = {
    "en": {
        "result_count": [
            "Found {n} record{plural} matching your query.",
            "Turned up {n} matching record{plural}.",
            "{n} record{plural} match what you're looking for.",
        ],
        "no_results": [
            "No records found matching your query. Try broadening the search — check spelling, or widen the date range or district.",
            "I couldn't find anything matching that. Double-check the spelling, or try a wider date range or a different district.",
            "No matching records in the database for that one. Try rephrasing, or broaden the district/date range.",
        ],
        "no_results_named": [
            "No records found for \"{name}\" — double-check the spelling, or it may not be in the database at all.",
            "I searched for \"{name}\" and came up empty. Try an alternate spelling or a known alias, or it simply isn't on file.",
        ],
        "repeat_offender_summary": [
            "{n} repeat offender{plural} identified, ranked by linked case count and risk score.",
            "Found {n} repeat offender{plural} — ranked below by case count and risk.",
        ],
        "risk_summary": [
            "{n} high or extreme risk identit{plural} found.",
            "{n} identit{plural} flagged as high or extreme risk.",
        ],
        "gang_summary": [
            "{n} gang-affiliated identit{plural} found.",
            "{n} gang-affiliated profile{plural2} on record.",
        ],
        "person_summary": [
            "Profile match found for {name}.",
            "Here's what's on file for {name}.",
        ],
        "fir_found": [
            "FIR {fir_number} is on file — here are the details.",
            "Found it — here's what's on record for FIR {fir_number}.",
        ],
        "alias_note": 'Also searched under "{resolved}" — {reason}.',
        "memory_recall": "This relates to a query from your session on {date}: you asked about \"{snippet}\".",
        "clarify_person": [
            "I want to give you the right answer rather than guess — which person did you mean? A full name or nickname works, and I'll also check known aliases.",
            "Could you tell me who you're asking about? A name or alias is enough — I'll take it from there.",
        ],
        "clarify_general": [
            "I'm not confident I understood that precisely enough to answer accurately. Could you add a bit more — a name, crime type, district, or FIR number?",
            "To avoid guessing, could you narrow that down a little? For example, a district, a crime type, a name, or an FIR number.",
        ],
        "clarify_network": [
            "Whose network would you like me to show? Give me a name and I'll pull their known connections.",
        ],
        "path_found": [
            "Found a {hops}-hop connection between {source} and {target}.",
            "{source} and {target} are connected through a {hops}-hop chain.",
        ],
        "path_not_found": [
            "No connection found between {source} and {target} within {max_hops} hops of phone, vehicle, "
            "network, or case links currently on file. They may not be linked at all, or the link exists "
            "through something not yet captured in the data.",
        ],
        "ambiguous_name_note": [
            '{count} people named "{term}" are on file — showing {chosen} ({connections} known connection{plural}), the most connected match.',
        ],
    },
    "kn": {
        "result_count": [
            "ನಿಮ್ಮ ಪ್ರಶ್ನೆಗೆ ಸಂಬಂಧಿಸಿದ {n} ದಾಖಲೆಗಳು ಕಂಡುಬಂದಿವೆ.",
            "{n} ದಾಖಲೆಗಳು ಹೊಂದಾಣಿಕೆಯಾಗಿವೆ.",
        ],
        "no_results": [
            "ಯಾವುದೇ ದಾಖಲೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ. ದಯವಿಟ್ಟು ಬೇರೆ ಪದಗಳಲ್ಲಿ ಹುಡುಕಿ ಅಥವಾ ಜಿಲ್ಲೆ/ದಿನಾಂಕವನ್ನು ಬದಲಾಯಿಸಿ.",
            "ಆ ಹುಡುಕಾಟಕ್ಕೆ ಯಾವುದೇ ದಾಖಲೆ ಸಿಗಲಿಲ್ಲ. ಕಾಗುಣಿತ ಪರಿಶೀಲಿಸಿ ಅಥವಾ ಜಿಲ್ಲೆ/ದಿನಾಂಕದ ವ್ಯಾಪ್ತಿ ವಿಸ್ತರಿಸಿ.",
        ],
        "no_results_named": [
            "\"{name}\" ಗಾಗಿ ಯಾವುದೇ ದಾಖಲೆ ಸಿಗಲಿಲ್ಲ. ಕಾಗುಣಿತ ಪರಿಶೀಲಿಸಿ ಅಥವಾ ಅದು ದಾಖಲೆಯಲ್ಲಿ ಇಲ್ಲದಿರಬಹುದು.",
        ],
        "repeat_offender_summary": [
            "ಪೂರ್ವ ಪ್ರಕರಣಗಳ ಸಂಖ್ಯೆ ಮತ್ತು ಅಪಾಯದ ಅಂಕದ ಆಧಾರದ ಮೇಲೆ {n} ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳು ಪತ್ತೆಯಾಗಿದ್ದಾರೆ.",
        ],
        "risk_summary": [
            "{n} ಹೆಚ್ಚಿನ ಅಥವಾ ತೀವ್ರ ಅಪಾಯದ ವ್ಯಕ್ತಿಗಳು ಕಂಡುಬಂದಿದ್ದಾರೆ.",
        ],
        "gang_summary": [
            "{n} ಗ್ಯಾಂಗ್ ಸಂಬಂಧಿತ ವ್ಯಕ್ತಿಗಳು ಕಂಡುಬಂದಿದ್ದಾರೆ.",
        ],
        "person_summary": [
            "{name} ಗಾಗಿ ಪ್ರೊಫೈಲ್ ಹೊಂದಾಣಿಕೆ ಕಂಡುಬಂದಿದೆ.",
        ],
        "fir_found": [
            "FIR {fir_number} ದಾಖಲೆಯಲ್ಲಿದೆ — ವಿವರಗಳು ಇಲ್ಲಿವೆ.",
        ],
        "alias_note": '"{resolved}" ಎಂಬ ಹೆಸರಿನಡಿಯೂ ಹುಡುಕಲಾಗಿದೆ — {reason}.',
        "memory_recall": "ಇದು {date} ರಂದು ನಿಮ್ಮ ಸೆಷನ್‌ನಲ್ಲಿ ಕೇಳಿದ ಪ್ರಶ್ನೆಗೆ ಸಂಬಂಧಿಸಿದೆ: \"{snippet}\".",
        "clarify_person": [
            "ದಯವಿಟ್ಟು ನಿಖರವಾದ ಉತ್ತರ ನೀಡಲು ಬಯಸುತ್ತೇನೆ — ನೀವು ಯಾರ ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಿ? ಹೆಸರು ಅಥವಾ ಅಡ್ಡಹೆಸರು ಸಾಕು.",
        ],
        "clarify_general": [
            "ಊಹಿಸುವ ಬದಲು, ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಹೆಚ್ಚು ವಿವರ ನೀಡಿ — ಹೆಸರು, ಅಪರಾಧದ ಪ್ರಕಾರ, ಜಿಲ್ಲೆ ಅಥವಾ FIR ಸಂಖ್ಯೆ.",
        ],
        "clarify_network": [
            "ಯಾರ ನೆಟ್‌ವರ್ಕ್ ತೋರಿಸಬೇಕು? ಹೆಸರು ನೀಡಿ, ನಾನು ಅವರ ಸಂಪರ್ಕಗಳನ್ನು ತೋರಿಸುತ್ತೇನೆ.",
        ],
        "path_found": [
            "{source} ಮತ್ತು {target} ನಡುವೆ {hops}-ಹಂತದ ಸಂಪರ್ಕ ಕಂಡುಬಂದಿದೆ.",
        ],
        "path_not_found": [
            "{source} ಮತ್ತು {target} ನಡುವೆ {max_hops} ಹಂತಗಳೊಳಗೆ ಯಾವುದೇ ಸಂಪರ್ಕ ಕಂಡುಬಂದಿಲ್ಲ.",
        ],
        "ambiguous_name_note": [
            '"{term}" ಎಂಬ ಹೆಸರಿನ {count} ಜನರು ದಾಖಲೆಯಲ್ಲಿದ್ದಾರೆ — ಹೆಚ್ಚು ಸಂಪರ್ಕ ಹೊಂದಿರುವ {chosen} ಅನ್ನು ತೋರಿಸಲಾಗುತ್ತಿದೆ.',
        ],
    },
}


def _pick(t: dict, key: str) -> str:
    variants = t.get(key) or TEMPLATES["en"][key]
    if isinstance(variants, list):
        return random.choice(variants)
    return variants


def generate(intent: str, results: list, entities: dict, alias_matches: list = None,
             memory_recall: dict = None, language: str = "en", engine_payload: dict = None) -> dict:
    """
    Returns {"text": str, "insights": str|None, "facts": dict} — text is
    the deterministic, always-correct officer-facing message; facts is
    the bounded grounding payload for optional LLM polishing (see
    ollama_client.compose_conversational).

    engine_payload is only populated by the graph_engine route (see
    brain.py's _dispatch_specialist) — carries the multi-hop path search
    result and any name-disambiguation notes, neither of which fit the
    generic result-row shape everything else here works from.
    """
    t = TEMPLATES.get(language, TEMPLATES["en"])
    n = len(results)
    lines = []

    if memory_recall:
        lines.append(_pick(t, "memory_recall").format(
            date=memory_recall.get("date", ""), snippet=memory_recall.get("text", "")[:80]
        ))

    # ── Multi-hop path narrative (network_query, two people named) ──────
    # See KAVACH_vs_DRISHTI_Analysis.md §2.1 — graph_engine.find_hidden_paths()
    # now actually gets called (brain.py); this is where its result becomes
    # officer-facing text instead of just structured data nobody reads.
    # ── Hotspot Operations Logbook narrative ─────────────────────────────
    # See services/hotspot_ops.py / brain.py's _hotspot_ops_dispatch().
    # Real per-operation and aggregate data either way — this only
    # decides how to phrase it. English-forward for now (this module's
    # bilingual TEMPLATES dict covers the core case-query intents; a
    # Kannada narrative for the logbook is a reasonable, contained
    # follow-up rather than something to rush here).
    if intent == "hotspot_ops_query" and engine_payload:
        shape = engine_payload.get("shape", "list")
        if shape == "summary":
            s = engine_payload["summary"]
            period_label = {"day": "Today", "week": "This week", "month": "This month",
                             "year": "This year", None: "All time"}.get(s.get("period"), "This period")
            text = (f"{period_label}: {s['total_operations']} hotspot operation(s) logged — "
                    f"{s['completed']} completed, {s['started']} in progress, {s['assigned']} assigned, "
                    f"{s['recommended']} awaiting review. "
                    f"Districts covered: {', '.join(s['districts_covered']) or 'none'}.")
            if s.get("top_crime_types"):
                text += " Top crime types: " + ", ".join(f"{c['crime_type']} ({c['count']})" for c in s["top_crime_types"]) + "."
            facts = build_facts(intent, results, entities, n)
            return {"text": text, "insights": None, "facts": facts}
        if shape == "top_districts":
            if not results:
                text = "No hotspot operations logged for that period yet."
            else:
                text = "Most patrol activity: " + ", ".join(f"{d['district']} ({d['count']} operation(s))" for d in results) + "."
            facts = build_facts(intent, results, entities, n)
            return {"text": text, "insights": None, "facts": facts}
        if shape == "top_crime_types":
            if not results:
                text = "No hotspot operations logged for that period yet."
            else:
                text = "Most recurring crime patterns in the logbook: " + ", ".join(
                    f"{c['crime_type']} ({c['count']})" for c in results) + "."
            facts = build_facts(intent, results, entities, n)
            return {"text": text, "insights": None, "facts": facts}
        # shape == "list"
        if not results:
            text = "No hotspot operations match that — nothing logged yet for this filter."
        else:
            lines_list = [
                f'{o["district"]}{" — " + o["police_station"] if o.get("police_station") else ""} '
                f'— {o["crime_type"]} — {o["status"]}'
                f'{" (" + o["assigned_team"] + ")" if o.get("assigned_team") else ""}'
                for o in results[:8]
            ]
            text = f"{len(results)} hotspot operation(s) on file:\n" + "\n".join(f"- {l}" for l in lines_list)
            if len(results) > 8:
                text += f"\n…and {len(results) - 8} more."
        facts = build_facts(intent, results, entities, n)
        return {"text": text, "insights": None, "facts": facts}

    if intent == "network_query" and engine_payload and "paths" in engine_payload:
        paths = engine_payload["paths"]
        source_label = engine_payload.get("source_label", "the first person")
        target_label = engine_payload.get("target_label", "the second person")
        if paths:
            best = paths[0]
            lines.append(_pick(t, "path_found").format(
                hops=len(best["steps"]), source=source_label, target=target_label))
            hop_desc = "; ".join(
                f'{s["from_label"]} --{s["relationship"]}--> {s["to_label"]}' for s in best["steps"]
            )
            lines.append(hop_desc)
        else:
            lines.append(_pick(t, "path_not_found").format(
                source=source_label, target=target_label, max_hops=6))
        for note in (engine_payload.get("ambiguous_matches") or []):
            lines.append(_pick(t, "ambiguous_name_note").format(
                count=note["count"], term=note["term"], chosen=note["chosen_label"],
                connections=note["chosen_connections"], plural="" if note["chosen_connections"] == 1 else "s"))
        facts = build_facts(intent, results, entities, n)
        return {"text": " ".join(lines), "insights": None, "facts": facts}

    if n == 0:
        name_candidate = None
        if intent in ("person_lookup", "repeat_offender_search", "risk_query", "gang_query", "network_query") \
                and entities.get("person_name_candidates"):
            name_candidate = entities["person_name_candidates"][0]
        if name_candidate:
            lines.append(_pick(t, "no_results_named").format(name=name_candidate))
        else:
            lines.append(_pick(t, "no_results"))
    elif intent == "repeat_offender_search":
        lines.append(_pick(t, "repeat_offender_summary").format(n=n, plural="s" if n != 1 else ""))
    elif intent == "risk_query":
        lines.append(_pick(t, "risk_summary").format(n=n, plural="ies" if n != 1 else "y"))
    elif intent == "gang_query":
        lines.append(_pick(t, "gang_summary").format(n=n, plural="ies" if n != 1 else "y", plural2="s" if n != 1 else ""))
    elif intent == "person_lookup" and n > 0:
        lines.append(_pick(t, "person_summary").format(name=results[0].get("name", "")))
        if n > 1:
            lines.append(_pick(t, "result_count").format(n=n, plural="s" if n != 1 else ""))
    elif intent == "fir_lookup" and n > 0:
        lines.append(_pick(t, "fir_found").format(fir_number=results[0].get("fir_number", entities.get("fir_number_candidate", ""))))
    else:
        lines.append(_pick(t, "result_count").format(n=n, plural="s" if n != 1 else ""))

    if alias_matches:
        best = alias_matches[0]
        if best["method"] != "exact":
            lines.append(t["alias_note"].format(resolved=best["name"], reason=best["reason"]))

    # Non-path network_query (a single person resolved -> their direct
    # connections listed) can still have hit the same duplicate-name
    # situation the path branch above handles — surface it here too.
    if intent == "network_query" and engine_payload:
        for note in (engine_payload.get("ambiguous_matches") or []):
            lines.append(_pick(t, "ambiguous_name_note").format(
                count=note["count"], term=note["term"], chosen=note["chosen_label"],
                connections=note["chosen_connections"], plural="" if note["chosen_connections"] == 1 else "s"))

    insights = None
    if n > 0 and intent in ("crime_type_search", "location_search", "statistics_query"):
        districts = {r.get("district") for r in results if r.get("district")}
        crime_types = {r.get("crime_type") for r in results if r.get("crime_type")}
        if len(districts) == 1 and len(crime_types) > 1:
            insights = f"All results are concentrated in {list(districts)[0]}."
        elif len(crime_types) == 1:
            insights = f"All results are '{list(crime_types)[0]}' cases."

    # expand any police abbreviations present in the raw query for clarity
    abbrev_hits = abbreviation_glossary.expand_all_in_text(entities.get("_raw_text", ""))
    if abbrev_hits and language == "en":
        expansions = "; ".join(f"{a}={b}" for a, b in abbrev_hits[:2])
        insights = (insights + f" ({expansions})") if insights else expansions

    facts = build_facts(intent, results, entities, n)

    return {"text": " ".join(lines), "insights": insights, "facts": facts}


_SAMPLE_FIELDS = (
    "name", "alias", "fir_number", "district", "crime_type", "status", "age", "gender",
    "risk_category", "risk_score", "prior_convictions", "gang_affiliation", "registration_date",
    "police_station", "modus_operandi",
)


def build_facts(intent: str, results: list, entities: dict, result_count: int = None) -> dict:
    """Bounded, JSON-safe grounding payload — deliberately small (top 5
    rows, whitelisted fields only) so a local model has enough to write
    a real sentence but no room to pad with dozens of unrequested
    details, and no way to reference something outside this payload
    without failing ollama_client._looks_grounded()."""
    n = result_count if result_count is not None else len(results)
    sample = []
    for r in (results or [])[:5]:
        sample.append({k: r[k] for k in _SAMPLE_FIELDS if r.get(k) not in (None, "")})
    return {
        "intent": intent,
        "result_count": n,
        "sample": sample,
        "query_districts": entities.get("districts") or [],
        "query_crime_types": entities.get("crime_types") or [],
    }


def clarification_text(kind: str, language: str = "en") -> str:
    """kind: 'person' | 'general' | 'network' — see brain.py for triggers."""
    t = TEMPLATES.get(language, TEMPLATES["en"])
    key = {"person": "clarify_person", "network": "clarify_network"}.get(kind, "clarify_general")
    return _pick(t, key)


def follow_up_suggestions(intent: str, results: list) -> list:
    """Deterministic, intent-aware next-query suggestions — no LLM needed."""
    if not results:
        return ["Show me all repeat offenders", "List recent FIRs in Bengaluru Urban",
                "Show high-risk offenders"]
    base = {
        "repeat_offender_search": ["Show network connections for the top offender",
                                    "Filter to EXTREME risk only", "Show their gang affiliation"],
        "risk_query": ["Show their case history", "Show network connections",
                        "Filter by Bengaluru Urban district"],
        "gang_query": ["Show the full gang network graph", "Which gang has the highest average risk?"],
        "crime_type_search": ["Show repeat offenders among these", "Show similar cases to the first one",
                               "Filter by district"],
        "person_lookup": ["Show their network connections", "Show their full case timeline",
                           "What's their risk score breakdown?"],
    }
    return base.get(intent, ["Show me repeat offenders", "Show high-risk offenders",
                              "List recent FIRs in Bengaluru Urban"])
