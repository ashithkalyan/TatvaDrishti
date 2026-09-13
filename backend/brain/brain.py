"""
KAVACH Brain — Orchestrator
==============================
The single entry point that chains every tested module into one
pipeline. This is the piece that turns 17 individually-verified brain
modules into an actual conversational system.

PIPELINE
  1. Recall memory        — current-session history + cross-session recall
                             (memory_engine.py)
  2. Extract entities      — crime types, districts, dates, names, thresholds
                             (entity_extractor.py)
  3. Resolve person names  — alias / phonetic / transliteration / fuzzy
                             (alias_resolver.py, transliteration.py)
  4. Classify intent       — pattern-based, explainable
                             (intent_engine.py)
  4.5 Clarify if ambiguous — if the officer's intent can't be pinned down
                             confidently enough to answer safely, KAVACH
                             asks a short follow-up question instead of
                             guessing (see _needs_clarification below).
  5. Route                 — either build SQL against the live DB
                             (sql_builder.py) or dispatch to a specialist
                             engine (prediction / similarity / timeline /
                             recommendation / graph)
  6. Generate response     — deterministic, grounded templates
                             (response_generator.py). If a local LLM is
                             running (ollama_client.py), the same facts
                             are optionally handed to it to write a more
                             conversational reply — verified against the
                             facts afterward, never trusted blind.
  7. Store this turn        — memory_engine.py, plus update the officer's
                             working context (current district/suspect/etc.)

Every stage's output is included in the returned dict — that IS the
explainability layer: nothing here is hidden between "the officer asked"
and "the officer got an answer."
"""
import random
import re
import sqlite3
from datetime import datetime

from . import (alias_resolver, entity_extractor, intent_engine, sql_builder,
               response_generator, memory_engine, ollama_client, reasoning_trace,
               prediction_engine, similarity_engine, timeline_engine,
               recommendation_engine, graph_engine, reference_resolver, general_knowledge,
               document_context, document_intent, facts_enrichment, ingestion_engine, case_memory)
from services import hotspot_ops

# Intents where, if the officer didn't actually name anyone, KAVACH should
# ask who rather than silently run a query that can only return noise or
# an empty set. Kept as a set (not hardcoded inline) so it's obvious at a
# glance which intents this protects.
_NEEDS_NAME_INTENTS = {"person_lookup": "person", "network_query": "network"}

# ── Pure small talk ──────────────────────────────────────────────────────
# Answered directly, with ZERO database query and ZERO fabricated result
# count — deliberately checked BEFORE anything that might otherwise treat
# "hello" as a data query (see process_query's step 2.2). This matters
# even when the officer has genuine leftover investigator context from an
# earlier, unrelated case (current_suspect/current_fir/etc. — see
# memory_engine.get_context()): a greeting is never a data query, no
# matter how much focus context happens to exist in the background.
_GREETING_PATTERNS = [
    (r'^(hi+|hello+|hey+|yo+|sup|namaste|namaskara)$', 'hello'),
    (r'^good\s*(morning|afternoon|evening|night)$', 'hello'),
    (r'^how are you\??$', 'hello'),
    (r'^(thanks?|thank you|thx|ty|much appreciated)$', 'thanks'),
    (r'^(bye|goodbye|see\s?you|cya|good\s?night|take\s?care)$', 'bye'),
    (r'^(ok|okay|k|kk|sure|alright|got it|noted|cool|nice|great|good)$', 'ack'),
    (r'^(test|testing|123|check)$', 'ack'),
]

_GREETING_REPLIES = {
    "hello": [
        "Hello! Ask me about a case, an FIR number, a suspect, a gang, or a crime trend — or attach a PDF and I'll work through it with you.",
        "Hi there. I can look up FIRs, suspects, gang networks, crime trends, or predictions — what would you like to check?",
    ],
    "thanks": [
        "You're welcome — let me know if there's anything else to look into.",
        "Anytime. Ask away if you need anything else.",
    ],
    "bye": [
        "Take care — this chat stays in your history if you need it again.",
        "Goodbye — you can pick this conversation back up anytime from Chat History.",
    ],
    "ack": [
        "Got it — what would you like to look into?",
        "Understood. Let me know what you'd like to check next.",
    ],
}


def _classify_greeting(message: str):
    """Returns a greeting 'kind' ('hello'/'thanks'/'bye'/'ack') for pure
    small talk, or None for anything else — deliberately a small,
    literal pattern set (never a fuzzy/LLM classification) so it can
    never accidentally swallow a real query that happens to start
    politely."""
    t = " ".join((message or "").lower().split()).rstrip("!.?,; ")
    for pattern, kind in _GREETING_PATTERNS:
        if re.match(pattern, t):
            return kind
    return None


# ── Case-briefing chat requests ("what's already been investigated on
# this case") — see case_memory.py's module docstring for the feature
# this powers: institutional memory scoped to the CASE, not the
# officer, so it survives a transfer to a different officer. Deliberately
# pattern-based, like the greeting classifier above, rather than a new
# intent_engine.py pattern, since it needs an FIR reference from EITHER
# the message OR working_context — a routing decision that depends on
# session state, not sentence shape alone.
_CASE_BRIEFING_PATTERNS = [
    r"\bwhat.?s (already )?been investigated\b",
    r"\bwhat has (already )?been (investigated|checked|done)\b",
    r"\bbrief me on\b",
    r"\bcase (briefing|handoff|history|summary)\b",
    r"\bwho.?s (worked|handled) this case\b",
    r"\bwhat.?s (still )?unresolved\b",
    r"\bwhich leads (have been|were) (already )?checked\b",
    r"\bcatch me up\b",
    r"\bwhat do we know (about|on) this case\b",
]


def _is_case_briefing_request(message: str) -> bool:
    t = " ".join((message or "").lower().split())
    return any(re.search(p, t) for p in _CASE_BRIEFING_PATTERNS)


def _handle_case_briefing(conn, user_id, session_id, message, language, session_history,
                           trace_log, fir_number) -> dict:
    """
    Answers "what's already been investigated on this case" by
    assembling case_memory.case_briefing() — dedicated case notes,
    checked-lead history (feedback_engine.py), and the pre-existing
    investigation-update log — into one coherent answer. Genuinely
    different from _handle_fir_number_lookup(): that one answers "what
    IS this FIR" from the case record itself; this one answers "what
    has already been DONE on it" — exactly the institutional-memory gap
    a case transfer creates for whichever officer picks it up next.
    """
    from . import case_memory

    trace_log.append(f"Case-briefing request detected for FIR {fir_number} — assembling case notes, "
                      "checked-lead feedback, and the investigation-update log (see case_memory.py)")
    briefing = case_memory.case_briefing(conn, fir_number)
    text = case_memory.case_briefing_text(briefing)
    response_source = "template"
    if briefing.get("found") and ollama_client.is_available():
        polished = ollama_client.polish_response(text, language=language)
        if polished != text:
            text = polished
            response_source = "ollama_polish"
            trace_log.append("Briefing phrasing polished by local Ollama (facts unchanged)")

    result_dict = {
        "session_id": session_id, "message": message, "interpretation": text,
        "insights": None, "notable_insight": None, "intent": "case_briefing", "intent_confidence": 1.0,
        "sql_generated": None, "routed_engine": None, "alias_matches": [], "memory_recalled": None,
        "results": [], "result_count": 0,
        "follow_up_suggestions": ([] if not briefing.get("found") else
                                   ["Add a note to this case", "Mark an unresolved thread", "Show recommended leads"]),
        "pipeline_trace": trace_log, "engine_payload": None, "identity_reasoning_trace": None,
        "needs_clarification": False, "network_snapshot": None, "response_source": response_source,
        "document_attached": None, "document_draft": None,
        "timestamp": datetime.now().isoformat(),
    }
    memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                              entities={}, sql_generated=None)
    memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                              full_response=result_dict)
    if briefing.get("found"):
        memory_engine.update_context(conn, user_id, current_fir={"fir_number": fir_number}, recent_case_ids=fir_number)

    return result_dict


def _needs_clarification(intent_result: dict, entities: dict, has_resolvable_focus: bool):
    """
    Returns a clarification 'kind' (see response_generator.clarification_text)
    if KAVACH should ask a follow-up question instead of answering, else None.

    Deliberately conservative — this only fires for the two cases where
    guessing would actively risk a wrong or misleading answer: (a) a
    person/network-centric question with literally no name mentioned, and
    (b) the lowest-confidence catch-all intent firing with zero extracted
    entities and no genuinely resolvable focus to fall back on. Every
    other case is left to run the query and report real results (or a
    real "no records found") rather than interrupt the officer
    unnecessarily.

    `has_resolvable_focus` MUST mean "there is something concrete
    (current_suspect/current_fir/current_district/recent_case_ids — see
    memory_engine.get_context()) that a vague message could plausibly be
    continuing" — NOT merely "this session has prior turns". Those are
    very different things: a session can have five prior turns and
    still have nothing in focus (e.g. every one of them was itself a
    clarification request, or a general-knowledge answer). Passing
    "any history exists" here was the actual bug behind "typing
    gibberish returns 30 unrelated records after the first message in a
    session" — see brain.py's process_query() for the fix and the two
    screenshots that reported it.
    """
    intent = intent_result["intent"]
    confidence = intent_result.get("confidence", 0)

    if intent in _NEEDS_NAME_INTENTS and not entities.get("person_name_candidates") \
            and not entities.get("_reference_resolved_person_id"):
        return _NEEDS_NAME_INTENTS[intent]

    has_any_entity = bool(
        entities.get("districts") or entities.get("crime_types")
        # BUG FIX (§2.4 — see entity_extractor.has_reliable_name_signal()):
        # a bare, unsupported capitalized word no longer counts as "an
        # entity was found" here either, so a message like "What's the
        # capital of France?" reaches this general clarification branch
        # instead of silently being treated as having a real focus.
        or entity_extractor.has_reliable_name_signal(entities.get("_raw_text", ""), entities.get("person_name_candidates"))
        or entities.get("threshold")
        or entities.get("date_from") or entities.get("fir_number_candidate")
    )
    if intent == "general_search" and confidence <= 0.3 and not has_any_entity and not has_resolvable_focus:
        return "general"

    return None


def _network_snapshot(conn, person_id: int, max_edges: int = 6):
    """
    A SMALL, bounded 1-hop neighbourhood around a single person — built
    for inline display inside a chat bubble (see frontend MiniNetworkGraph),
    not the full investigation-grade network explorer on the Network page.
    Returns None rather than an empty graph when there's nothing to show,
    so the frontend never renders a pointless empty box.
    """
    if not person_id:
        return None
    edges_raw = conn.execute("""
        SELECT PersonIdentityID_A, PersonIdentityID_B, RelationshipType, Strength
        FROM PersonNetworkLink WHERE PersonIdentityID_A=? OR PersonIdentityID_B=?
        ORDER BY Strength DESC LIMIT ?
    """, (person_id, person_id, max_edges)).fetchall()
    if not edges_raw:
        return None

    neighbour_ids = {person_id}
    for a, b, _rel, _s in edges_raw:
        neighbour_ids.add(a)
        neighbour_ids.add(b)
    placeholders = ",".join("?" * len(neighbour_ids))
    persons = conn.execute(
        f"SELECT PersonIdentityID, CanonicalName, RiskCategory FROM PersonIdentity "
        f"WHERE PersonIdentityID IN ({placeholders})", tuple(neighbour_ids)
    ).fetchall()

    nodes = [{"data": {"id": str(pid), "label": name, "risk": risk or "LOW",
                        "is_center": pid == person_id}} for pid, name, risk in persons]
    edges = [{"data": {"id": f"{a}-{b}", "source": str(a), "target": str(b),
                        "relationship": rel, "strength": s}} for a, b, rel, s in edges_raw]
    return {"nodes": nodes, "edges": edges, "center_id": str(person_id)}


def _build_identity_reasoning_trace(conn, person_id) -> dict:
    """
    Builds a REAL audit trace for 'why is this flagged as one person
    across multiple FIRs' — using the actual MatchConfidence/MatchMethod
    values stored by alias_resolver.cluster_identities() at seeding
    time (or, for live-ingested records, at commit time). Nothing here
    is invented for display purposes; every factor traces to a stored
    row.
    """
    links = conn.execute("""
        SELECT a.AccusedName, a.AgeYear, a.FatherOrSpouseName, cm.CrimeNo,
               pil.MatchConfidence, pil.MatchMethod
        FROM PersonIdentityLink pil
        JOIN Accused a ON pil.AccusedMasterID = a.AccusedMasterID
        JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
        WHERE pil.PersonIdentityID = ?
    """, (person_id,)).fetchall()

    if len(links) <= 1:
        # Deliberately NOT routed through build_trace()'s match-ratio formula:
        # with zero computed factors, that formula would land on 0/1 = "0%
        # confidence", which reads to an officer as "we doubt this identity" —
        # backwards for the one case (a single, unambiguous record) where
        # there is nothing to be uncertain about in the first place.
        return {
            "conclusion": "Single-record identity — only one FIR is linked, so no cross-case "
                           "name/alias matching was needed or performed",
            "confidence": None,
            "confidence_pct": "N/A (single record)",
            "factors_matched": [], "factors_not_matched": [],
            "factors_unavailable": [reasoning_trace.factor(
                "name_similarity", "not_available", detail="Only one linked FIR record on file")],
            "factor_coverage": "0/1 factors computed",
            "officer_summary": "Only one FIR is linked to this identity, so there was no cross-case "
                                "match to verify — this is not a low-confidence result, there was simply "
                                "nothing to cross-reference.",
        }

    methods_seen = {row["MatchMethod"] for row in links}
    factors = [
        reasoning_trace.factor(
            "name_similarity", "match", weight=0.30,
            detail=f"{len(links)} record(s) linked via: {', '.join(sorted(methods_seen))}",
        ),
        reasoning_trace.factor(
            "father_or_spouse_name_match",
            "match" if len({r["FatherOrSpouseName"] for r in links if r["FatherOrSpouseName"]}) <= 1
                     and any(r["FatherOrSpouseName"] for r in links) else "not_available",
            weight=0.20,
            detail="Consistent father/spouse name across linked records" if any(r["FatherOrSpouseName"] for r in links)
                   else "Father/spouse name not recorded on these FIRs",
        ),
        reasoning_trace.factor(
            "age_consistency", "match", weight=0.15,
            detail=f"Ages recorded: {sorted({r['AgeYear'] for r in links if r['AgeYear']})}",
        ),
        reasoning_trace.factor("phone_match", "not_available",
                                detail="Not part of the cross-FIR name-clustering pass — see the network graph for phone-based links"),
        reasoning_trace.factor("fingerprint_match", "not_available"),
    ]
    avg_conf = sum(r["MatchConfidence"] for r in links) / len(links)
    fir_list = [r["CrimeNo"] for r in links]
    fir_display = ", ".join(fir_list[:4]) + (f", +{len(fir_list) - 4} more" if len(fir_list) > 4 else "")
    conclusion = f"Same individual across {len(links)} FIR record(s): {fir_display}"
    trace = reasoning_trace.build_trace(conclusion, factors)
    trace["all_linked_fir_numbers"] = fir_list
    trace["stored_match_confidence_avg"] = round(avg_conf, 3)
    trace["officer_summary"] = reasoning_trace.summarise_for_officer(trace)
    return trace


def _get_known_person_names(conn, limit=2000):
    rows = conn.execute("SELECT name FROM vw_person_flat LIMIT ?", (limit,)).fetchall()
    return [r[0] for r in rows if r[0]]


def _row_to_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _handle_fir_number_lookup(conn, user_id, session_id, message, entities, language,
                               session_history, trace_log, stream_sink=None) -> dict:
    """
    Exact-match lookup for a pasted/typed 18-digit FIR number — bypasses
    intent classification and clarification entirely, because there is
    nothing ambiguous about a specific case number. Honest either way:
    a real match returns real details; no match returns a plain 'no such
    FIR number on file', never a guess at what the case might be.
    """
    fir_number = entities["fir_number_candidate"]
    trace_log.append(f"Detected an 18-digit FIR/Crime Number ({fir_number}) — running a direct exact-match lookup")
    sql_text = "SELECT * FROM vw_fir_flat WHERE fir_number = ?"
    row = conn.execute(sql_text, (fir_number,)).fetchone()
    results = [dict(row)] if row else []

    response = response_generator.generate("fir_lookup", results, entities, language=language)
    text = response["text"]
    response_source = "template"
    notable = None
    if results:
        if stream_sink:
            conversational_text = ollama_client.compose_conversational_streaming(
                text, response["facts"], "fir_lookup", language=language, stream_sink=stream_sink)
        else:
            composed = ollama_client.compose_conversational(text, response["facts"], "fir_lookup", language=language)
            conversational_text = composed["text"] if composed else None
            notable = composed["notable"] if composed else None
        if conversational_text:
            text = conversational_text
            response_source = "ollama_grounded"
            trace_log.append("Response composed conversationally by local Ollama, grounded in the exact FIR record")
        else:
            polished = ollama_client.polish_response(text, language=language)
            if polished != text:
                text = polished
                response_source = "ollama_polish"
                trace_log.append("Response polished by local Ollama (facts unchanged, phrasing only)")
    else:
        polished = ollama_client.polish_response(text, language=language)
        if polished != text:
            text = polished
            response_source = "ollama_polish"
            trace_log.append("Response polished by local Ollama (facts unchanged, phrasing only)")

    result_dict = {
        "session_id": session_id, "message": message, "interpretation": text,
        "insights": response.get("insights"), "notable_insight": notable,
        "intent": "fir_lookup", "intent_confidence": 1.0,
        "sql_generated": sql_text, "routed_engine": None, "alias_matches": [], "memory_recalled": None,
        "results": results, "result_count": len(results),
        "follow_up_suggestions": response_generator.follow_up_suggestions("fir_lookup", results),
        "pipeline_trace": trace_log, "engine_payload": None, "identity_reasoning_trace": None,
        "needs_clarification": False, "network_snapshot": None, "response_source": response_source,
        "document_attached": None, "document_draft": None,
        "timestamp": datetime.now().isoformat(),
    }
    memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                              entities=entities, sql_generated=sql_text)
    memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                              full_response=result_dict)
    if results:
        memory_engine.update_context(conn, user_id, current_fir={"fir_number": fir_number}, recent_case_ids=fir_number)

    return result_dict


def _handle_document_query(conn, user_id, session_id, message, language, session_history,
                            trace_log, document, stream_sink=None) -> dict:
    """
    Answers a question about the document attached to THIS session,
    grounded in its extracted text via Ollama — never the case
    database. See document_context.py for how "attached to this
    session" is stored/scoped, and ollama_client.answer_from_document()
    for the same grounding discipline compose_conversational() applies
    to SQL rows, applied here to document text instead.

    response_source="document_grounded" (or "template" for the honest
    "can't answer that" / "Ollama isn't running" cases) — deliberately
    never "ollama_grounded", so the Reasoning panel can never make a
    document answer look like a verified database fact.
    """
    trace_log.append(f"Document attached to this session ({document['filename']}, "
                      f"{document['char_count']} characters) — answering from its extracted "
                      "text via local Ollama, never the case database")

    if not ollama_client.is_available():
        text = (f'A document is attached to this chat ("{document["filename"]}", '
                f'{document["char_count"]} characters extracted), but answering questions '
                "about it needs the local Ollama model, which isn't running right now. "
                'You can still say "extract this into a case" to pull it into a review '
                "form without needing Ollama at all.")
        response_source = "template"
    else:
        if stream_sink:
            answer = ollama_client.answer_from_document_streaming(
                message, document["text"], document["filename"], language=language, stream_sink=stream_sink)
        else:
            answer = ollama_client.answer_from_document(
                message, document["text"], document["filename"], language=language)
        if answer:
            text = answer
            response_source = "document_grounded"
            trace_log.append("Answer composed by local Ollama, grounded in the attached document's "
                              "extracted text and verified against it before use")
        else:
            text = ("I couldn't confidently answer that from the attached document — either it "
                    "doesn't mention this, or the local model's answer didn't stay grounded in the "
                    "extracted text, so I'm not showing it. Try rephrasing, or check the document "
                    "directly.")
            response_source = "template"
            trace_log.append("Document answer rejected (unavailable, empty, or failed the "
                              "document-grounding check) — showed an honest 'can't answer' message "
                              "instead of a guess")

    result_dict = {
        "session_id": session_id, "message": message, "interpretation": text,
        "insights": None, "notable_insight": None, "intent": "document_query", "intent_confidence": 1.0,
        "sql_generated": None, "routed_engine": None, "alias_matches": [], "memory_recalled": None,
        "results": [], "result_count": 0,
        "follow_up_suggestions": ["Summarize this document", "Extract this into a case",
                                   "What's the FIR number in this?"],
        "pipeline_trace": trace_log, "engine_payload": None, "identity_reasoning_trace": None,
        "needs_clarification": False, "network_snapshot": None, "response_source": response_source,
        "document_attached": {"filename": document["filename"], "char_count": document["char_count"]},
        "document_draft": None,
        "timestamp": datetime.now().isoformat(),
    }
    memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                              entities={}, sql_generated=None)
    memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                              full_response=result_dict)

    return result_dict


def _handle_document_extract(conn, user_id, session_id, message, language, session_history,
                              trace_log, document, explicit_commit_request=False) -> dict:
    """
    Builds a case REVIEW DRAFT from the document attached to this
    session — reuses the exact same ingestion_engine.parse_fields() the
    file-upload path in Cases.jsx uses, plus a live
    resolve_or_link_person_identity() check per candidate name so the
    officer sees "possible existing record" hints before they even open
    the review form.

    NEVER writes to the database. Whether the officer said "extract
    this into a case" or "put it in the database" makes no behavioural
    difference here — both just populate the draft and wait; the ONLY
    path that ever calls ingestion_engine.commit_draft() is main.py's
    POST /api/ingest/confirm, which is only ever reached by an explicit
    "Confirm & Save" click in the UI (see frontend DocumentReviewCard.jsx).
    A chat sentence alone can never write a case record — that gate is
    enforced here by simple omission: this function has no code path to
    commit_draft() at all.
    """
    trace_log.append(f"Extraction requested for the attached document ({document['filename']}) — "
                      "running parse_fields() on its stored text; building a review draft only, "
                      "never writing to the database")
    draft = ingestion_engine.parse_fields(document["text"])

    district_id = None
    if draft.get("districts_detected"):
        row = conn.execute("SELECT DistrictID FROM District WHERE DistrictName=?",
                            (draft["districts_detected"][0],)).fetchone()
        district_id = row[0] if row else None

    # entity_extractor's name-candidate scan is a closed-world, capitalised-
    # word heuristic tuned for short chat queries (see its own docstring) —
    # reused as-is here (same as Cases.jsx's upload flow) because changing
    # it would also change chat-query name matching everywhere else. For
    # THIS feature only (the live "possible existing record" hint, which
    # doesn't exist anywhere else), filter out common FIR-boilerplate
    # header words that a document scan turns up but a chat query never
    # would — purely cosmetic, and draft["person_name_candidates"] itself
    # (what actually populates the editable review-card fields, exactly
    # like Cases.jsx already does) is left completely untouched.
    _DOC_HEADER_NOISE = {"crime", "crime no", "age", "complainant", "accused", "police",
                          "police station", "district", "offence", "report", "date", "fir"}
    identity_hints = []
    for name in (draft.get("person_name_candidates") or []):
        if name.lower() in _DOC_HEADER_NOISE:
            continue
        if len(identity_hints) >= 5:
            break
        hint = ingestion_engine.resolve_or_link_person_identity(conn, name, draft.get("age_guess"), district_id)
        identity_hints.append({
            "name": name,
            "possible_existing_match": (not hint["is_new"]),
            "matched_against": hint.get("matched_against"),
            "match_confidence": hint.get("match_confidence"),
        })
    draft["identity_hints"] = identity_hints
    if any(h["possible_existing_match"] for h in identity_hints):
        trace_log.append("Live identity check found possible existing record(s) for one or more "
                          "candidate names — surfaced in the draft, resolved for real at confirm time")

    if explicit_commit_request:
        text = (f'I\'ve pulled "{document["filename"]}" into a review draft below — nothing is saved '
                'yet. Check every field (especially the crime number, district, and station), then '
                'click "Confirm & Save" to write it to the database. I won\'t commit a case straight '
                "from a chat message; that step always needs your explicit confirmation.")
    else:
        text = (f'Here\'s a draft extracted from "{document["filename"]}" — review and correct '
                "anything below, then confirm to save it as a case.")

    response_source = "template"
    if ollama_client.is_available():
        polished = ollama_client.polish_response(text, language=language)
        if polished != text:
            text = polished
            response_source = "ollama_polish"
            trace_log.append("Draft-intro phrasing polished by local Ollama (facts unchanged)")

    result_dict = {
        "session_id": session_id, "message": message, "interpretation": text,
        "insights": None, "notable_insight": None, "intent": "document_extract", "intent_confidence": 1.0,
        "sql_generated": None, "routed_engine": None, "alias_matches": [], "memory_recalled": None,
        "results": [], "result_count": 0, "follow_up_suggestions": [],
        "pipeline_trace": trace_log, "engine_payload": None, "identity_reasoning_trace": None,
        "needs_clarification": False, "network_snapshot": None, "response_source": response_source,
        "document_attached": {"filename": document["filename"], "char_count": document["char_count"]},
        "document_draft": draft,
        "timestamp": datetime.now().isoformat(),
    }
    memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                              entities={}, sql_generated=None)
    memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                              full_response=result_dict)

    return result_dict


def process_query(conn: sqlite3.Connection, user_id: int, session_id: str,
                   message: str, language: str = "en", stream_sink=None) -> dict:
    """
    stream_sink: optional callable, forwarded straight through to
    ollama_client's streaming compose functions when the officer's
    message is answered via a live LLM call (the main SQL-grounded path
    or document Q&A). None (the default) means "run exactly as before,
    fully synchronous, single JSON response" — see main.py's POST
    /api/chat. When provided, main.py's POST /api/chat/stream bridges it
    to Server-Sent Events — see that endpoint's docstring for the
    token/confirm/retract protocol. Every other branch of this pipeline
    (clarification, general knowledge, FIR-number lookup, zero-result
    replies) never touches stream_sink at all, since none of them
    involve a live token-by-token LLM call — the SSE endpoint
    "fake-streams" (chunks word-by-word) those already-final,
    already-safe strings instead, which needs no change here.
    """
    trace_log = []  # human-readable pipeline trace, for the explainability panel

    # ── 1. Memory recall ────────────────────────────────────────────────
    session_history = memory_engine.get_session_history(conn, user_id, session_id, limit=6)
    cross_session_hits = memory_engine.recall_relevant_context(conn, user_id, session_id, message)
    memory_recall = None
    if cross_session_hits:
        best = cross_session_hits[0]
        memory_recall = {"date": memory_engine.format_recall_date(best["timestamp"]), "text": best["text"]}
        trace_log.append(f"Memory: recalled a related query from session {best['session_id']} "
                          f"(similarity {best['score']})")

    # ── 2. Entity extraction ────────────────────────────────────────────
    entities = entity_extractor.extract(message)
    entities["_raw_text"] = message
    trace_log.append(f"Entities extracted: crime_types={entities['crime_types']}, "
                      f"districts={entities['districts']}, names={entities['person_name_candidates']}")

    # ── 2.2 Pure small talk — see _classify_greeting()'s module-level
    #    comment for why this runs before anything else and ignores
    #    prior context entirely. Gated on zero entities so "hi, can you
    #    show me theft cases" still goes through the normal pipeline —
    #    only fires when NOTHING else in the message could be a query.
    if not any(entities.get(k) for k in
               ("crime_types", "districts", "person_name_candidates", "date_from", "fir_number_candidate")):
        greeting_kind = _classify_greeting(message)
        if greeting_kind:
            trace_log.append(f"Pure small talk detected ('{greeting_kind}') — answered directly, "
                              "no database query run")
            text = random.choice(_GREETING_REPLIES[greeting_kind])
            response_source = "template"
            if ollama_client.is_available():
                polished = ollama_client.polish_response(text, language=language)
                if polished != text:
                    text = polished
                    response_source = "ollama_polish"

            result_dict = {
                "session_id": session_id, "message": message, "interpretation": text,
                "insights": None, "notable_insight": None, "intent": "small_talk", "intent_confidence": 1.0,
                "sql_generated": None, "routed_engine": None, "alias_matches": [], "memory_recalled": None,
                "results": [], "result_count": 0, "follow_up_suggestions": [],
                "pipeline_trace": trace_log, "engine_payload": None, "identity_reasoning_trace": None,
                "needs_clarification": False, "network_snapshot": None, "response_source": response_source,
                "document_attached": None, "document_draft": None,
                "timestamp": datetime.now().isoformat(),
            }
            memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                                      entities=entities, sql_generated=None)
            memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                                      full_response=result_dict)

            return result_dict

    # ── 2.3 In-session reference resolution ("he", "that gang", "the
    #    second one") — only ever ADDS a candidate the officer didn't
    #    type; never overrides an explicit name. See reference_resolver.py
    #    for exactly what it does and doesn't attempt. ───────────────────
    working_context = memory_engine.get_context(conn, user_id)
    reference_resolver.resolve_references(message, entities, working_context, trace_log)

    # ── 2.35 UI-help safety net ────────────────────────────────────────
    # An officer asking "what does this icon do" straight into the case-
    # chat box (instead of the floating Hovering Assistant, which is the
    # real, instant answer to that question) used to fall through to the
    # SQL pipeline, search for zero matching records, and answer with a
    # confusing "no records found". See intent_engine.is_ui_help_query's
    # module note for exactly why this is scoped so narrowly. Same
    # has_any_entity_early guard as general_knowledge below — a real case
    # question is never hijacked by this.
    has_any_entity_early = bool(
        entities.get("districts") or entities.get("crime_types")
        # BUG FIX (§2.4): a bare person_name_candidate no longer counts on
        # its own — see entity_extractor.has_reliable_name_signal()'s
        # docstring for the exact "BNS" / "France" failure this closes.
        or entity_extractor.has_reliable_name_signal(message, entities.get("person_name_candidates"))
        or entities.get("date_from")
        or entities.get("fir_number_candidate") or entities.get("_reference_resolved_person_id")
        or entities.get("_resolved_gang")
    )
    if not has_any_entity_early and intent_engine.is_ui_help_query(message):
        text = intent_engine.UI_HELP_REDIRECT.get(language, intent_engine.UI_HELP_REDIRECT["en"])
        trace_log.append("Matched UI-help pattern (question about the app's own interface, not case "
                          "data) — redirected to the Hovering Assistant instead of running a case search")

        result_dict = {
            "session_id": session_id, "message": message, "interpretation": text,
            "insights": None, "notable_insight": None, "intent": "ui_help_redirect", "intent_confidence": 1.0,
            "sql_generated": None, "routed_engine": None, "alias_matches": [],
            "memory_recalled": memory_recall, "results": [], "result_count": 0,
            "follow_up_suggestions": [], "pipeline_trace": trace_log, "engine_payload": None,
            "identity_reasoning_trace": None, "needs_clarification": False,
            "network_snapshot": None, "response_source": "template",
            "document_attached": None, "document_draft": None,
            "timestamp": datetime.now().isoformat(),
        }
        memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                                  entities=entities, sql_generated=None)
        memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                                  full_response=result_dict)
        return result_dict

    # ── 2.4 Bounded general-knowledge fallback ───────────────────────────
    # For questions that aren't about the case data at all ("what is a
    # charge sheet?", "what can you ask me?", "IPC 302?") — answered from
    # a small curated table (general_knowledge.py), NEVER from the
    # database and NEVER from the LLM's own general knowledge. Guarded by
    # has_any_entity so a real case question that happens to use one of
    # these words (e.g. a person's bail status) is never hijacked by a
    # generic definition — this only fires when the message carries no
    # district/crime-type/name/date/FIR to actually query against.
    gk_answer, gk_topic = (None, None) if has_any_entity_early else general_knowledge.match(message)
    if gk_answer:
        text = f"General guidance — not case-specific: {gk_answer}"
        polished = ollama_client.polish_response(text, language=language)
        if polished != text and "General guidance" in polished:
            # Only accept the polish if it kept the disclaimer prefix intact —
            # this label must never be silently dropped by phrasing rewrite.
            text = polished
            trace_log.append("General-knowledge answer polished by local Ollama (facts unchanged)")
        trace_log.append(f'Matched general-knowledge topic "{gk_topic}" — answered from the curated '
                          "reference table, not the case database")

        result_dict = {
            "session_id": session_id, "message": message, "interpretation": text,
            "insights": None, "notable_insight": None, "intent": "general_knowledge", "intent_confidence": 1.0,
            "sql_generated": None, "routed_engine": None, "alias_matches": [],
            "memory_recalled": memory_recall, "results": [], "result_count": 0,
            "follow_up_suggestions": [], "pipeline_trace": trace_log, "engine_payload": None,
            "identity_reasoning_trace": None, "needs_clarification": False,
            "network_snapshot": None, "response_source": "general_knowledge",
            "document_attached": None, "document_draft": None,
            "timestamp": datetime.now().isoformat(),
        }
        memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                                  entities=entities, sql_generated=None)
        memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                                  full_response=result_dict)

        return result_dict

    # ── 2.5. Case-briefing request — "what's already been investigated
    #    on this case", asked in chat. Checked before the plain FIR-
    #    number short-circuit below so "brief me on FIR 190420..."
    #    gets the assembled institutional-memory briefing rather than
    #    the bare single-record lookup; a plain pasted FIR number with
    #    no briefing language still falls through to that lookup
    #    exactly as before. See case_memory.py's module docstring for
    #    why this exists — case notes, checked-lead history, and the
    #    investigation-update log are scoped to the CASE, not the
    #    officer, specifically so this answer survives a transfer to a
    #    different officer, unlike conversation_memory/investigator_context. ──
    target_fir = entities.get("fir_number_candidate") or (working_context.get("current_fir") or {}).get("fir_number")
    if target_fir and _is_case_briefing_request(message):
        return _handle_case_briefing(conn, user_id, session_id, message, language,
                                      session_history, trace_log, target_fir)

    # ── 2.6. Direct FIR-number short-circuit ─────────────────────────────
    # An 18-digit FIR/Crime Number is the most unambiguous thing an officer
    # can type — route it straight to an exact lookup rather than through
    # intent classification, so it's never mistaken for an unclear query
    # that needs clarification (entity_extractor.py has the format note).
    if entities.get("fir_number_candidate"):
        return _handle_fir_number_lookup(conn, user_id, session_id, message, entities,
                                          language, session_history, trace_log, stream_sink=stream_sink)

    # ── 2.7. Document chat — only when a PDF/photo is attached to THIS
    #    session (see document_context.py). Checked after the general-
    #    knowledge fallback and the FIR-number short-circuit (both stay
    #    exactly as reliable as before, document or no document) but
    #    before name resolution / intent classification, so "summarize
    #    this" or "extract this into a case" never has to fight the
    #    normal case-query classifier for a decision it isn't equipped
    #    to make. document_intent.classify() is conservative: an
    #    ordinary case query ("show repeat offenders in Mysuru") is
    #    never hijacked just because a document happens to be attached.
    attached_document = document_context.get_document(conn, user_id, session_id)
    if attached_document:
        doc_intent = document_intent.classify(message, has_any_entity_early)
        if doc_intent["mode"] == "extract":
            trace_log.append(f'Document intent: extraction/commit request matched '
                              f'("{doc_intent["matched_pattern"]}")')
            return _handle_document_extract(conn, user_id, session_id, message, language,
                                             session_history, trace_log, attached_document,
                                             explicit_commit_request=doc_intent["explicit_commit"])
        if doc_intent["mode"] == "query":
            trace_log.append(f'Document intent: content question matched ("{doc_intent["matched_pattern"]}")')
            return _handle_document_query(conn, user_id, session_id, message, language,
                                           session_history, trace_log, attached_document,
                                           stream_sink=stream_sink)
        trace_log.append("A document is attached to this session, but the message reads as an "
                          "ordinary case-database query — routed through the normal pipeline")

    # ── 3. Name resolution ──────────────────────────────────────────────
    alias_matches = []
    if entities["person_name_candidates"]:
        known_names = _get_known_person_names(conn)
        for candidate in entities["person_name_candidates"]:
            matches = alias_resolver.resolve_name(candidate, known_names)
            alias_matches.extend(matches[:3])
        if alias_matches:
            trace_log.append(f"Name resolution: {len(alias_matches)} candidate match(es), "
                              f"top = {alias_matches[0]['name']} ({alias_matches[0]['method']})")

    # ── 4. Intent classification (with follow-up merge) ─────────────────
    has_prior = len(session_history) > 0
    intent_result = intent_engine.classify(message, entities, has_prior_context=has_prior)
    trace_log.append(f"Intent: {intent_result['intent']} (matched: {intent_result['matched_pattern']})")

    # A resolved in-session reference (e.g. "the second one") means we
    # already know EXACTLY who this is about, even when the wording is
    # too generic for intent_engine to recognise as a profile request —
    # "tell me more about the second one" doesn't look like "person
    # lookup" on the words alone, but it plainly is once the reference
    # has resolved. Without this, the query fell through to the generic
    # catch-all and the resolved person was silently ignored.
    if entities.get("_reference_resolved_person_id") and intent_result["intent"] in ("general_search", "follow_up_filter"):
        intent_result = {**intent_result, "intent": "person_lookup",
                          "matched_pattern": "in-session reference resolved to a specific person"}
        trace_log.append("Intent read as person_lookup: an in-session reference resolved to a specific "
                          "person, so this is a profile request even though the wording alone was generic")

    if intent_result["intent"] == "follow_up_filter" and session_history:
        last_user_turn = next((t for t in reversed(session_history) if t["role"] == "user"), None)
        if last_user_turn and last_user_turn.get("entities"):
            merged = dict(last_user_turn["entities"])
            for k, v in entities.items():
                if v:
                    merged[k] = v
            entities = merged
            trace_log.append("Follow-up detected: merged filters from the previous turn in this session")

    # ── 4.5. Clarify if genuinely ambiguous, rather than guess ──────────
    # has_resolvable_focus (NOT has_prior — that flag only controls the
    # narrower "only/just/filter..." follow-up-phrase detection above, a
    # deliberately different and looser signal) — see
    # _needs_clarification()'s docstring for why conflating the two was
    # the actual bug.
    has_resolvable_focus = bool(
        working_context.get("current_suspect") or working_context.get("current_fir")
        or working_context.get("current_district") or working_context.get("recent_case_ids")
    )
    clarification_kind = _needs_clarification(intent_result, entities, has_resolvable_focus)
    if clarification_kind:
        text = response_generator.clarification_text(clarification_kind, language=language)
        polished = ollama_client.polish_response(text, language=language)
        if polished != text:
            text = polished
            trace_log.append("Clarification phrasing polished by local Ollama (facts unchanged)")
        trace_log.append(f"Confidence too low to answer safely — asked for clarification ('{clarification_kind}') "
                          "instead of guessing")

        result_dict = {
            "session_id": session_id, "message": message, "interpretation": text,
            "insights": None, "notable_insight": None,
            "intent": intent_result["intent"], "intent_confidence": intent_result["confidence"],
            "sql_generated": None, "routed_engine": None, "alias_matches": alias_matches[:5],
            "memory_recalled": memory_recall, "results": [], "result_count": 0,
            "follow_up_suggestions": [], "pipeline_trace": trace_log, "engine_payload": None,
            "identity_reasoning_trace": None, "needs_clarification": True,
            "network_snapshot": None, "response_source": "template",
            "document_attached": None, "document_draft": None,
            "timestamp": datetime.now().isoformat(),
        }
        memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                                  entities=entities, sql_generated=None)
        memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                                  full_response=result_dict)

        return result_dict

    # ── 5. Route: SQL or specialist engine ──────────────────────────────
    route_result = sql_builder.build(intent_result["intent"], entities, resolved_names=alias_matches)
    results, sql_text, engine_payload = [], None, None

    if route_result.get("route"):
        engine_payload = _dispatch_specialist(route_result["route"], conn, entities, alias_matches, results_hint=route_result)
        results = engine_payload.get("results", [])
        trace_log.append(f"Routed to specialist engine: {route_result['route']}")
    else:
        sql_text = route_result["sql"]
        try:
            cursor = conn.execute(sql_text, route_result.get("params", ()))
            results = _row_to_dicts(cursor)
        except sqlite3.Error as e:
            trace_log.append(f"SQL error (query returned no results): {e}")
            results = []

    # ── 6. Response generation ──────────────────────────────────────────
    response = response_generator.generate(
        intent_result["intent"], results, entities,
        alias_matches=alias_matches, memory_recall=memory_recall, language=language,
        engine_payload=engine_payload,
    )
    text = response["text"]
    response_source = "template"
    notable = None

    # ── 6.1 Richer grounding facts (Layer 1) ─────────────────────────────
    # response_generator.build_facts() only ever hands Ollama a flat
    # 5-row sample + a count — enough to paraphrase, not enough to say
    # anything an investigator would call insight. facts_enrichment.py
    # adds a few EXTRA, still 100%-deterministic facts (computed here in
    # Python, never left for the LLM to work out) so compose_conversational
    # below has real material: a person's case history / network / risk
    # breakdown, or a month-over-month trend + district breakdown. See
    # facts_enrichment.py's module docstring for exactly what's added and
    # why. This only ever ADDS keys to response["facts"] — it never
    # changes `text`, so the deterministic template is untouched either way.
    if results:
        if intent_result["intent"] in ("person_lookup", "repeat_offender_search"):
            top_person_id = results[0].get("person_id")
            if top_person_id:
                facts_enrichment.enrich_person_facts(conn, top_person_id, response["facts"])
                trace_log.append("Facts enriched with case history, network size, and risk "
                                  "breakdown for the top-ranked person — richer material for "
                                  "the conversational rewrite below, not just a flat row")
        elif intent_result["intent"] in ("crime_type_search", "statistics_query", "location_search"):
            facts_enrichment.enrich_trend_facts(conn, entities, response["facts"])
            trace_log.append("Facts enriched with a month-over-month trend and a district/station "
                              "breakdown — both computed in Python, handed to the LLM as given facts")

    # ── 6.2 Conversation memory for tone/continuity (Layer 2) ────────────
    # The last few ALREADY-GENERATED turns (not raw DB rows) — passed to
    # compose_conversational so a reply can flow naturally from what was
    # just said ("also found...", avoiding repeating itself) without ever
    # becoming a second source of facts. See
    # ollama_client._recent_turns_block()'s docstring for how that
    # separation is enforced in the prompt itself.
    recent_turns = session_history[-6:] if session_history else []

    if results:
        # Richer, free(r)-form conversational rewrite — grounded in the
        # same facts, verified before being trusted. Never runs for zero
        # results (see ollama_client.compose_conversational docstring).
        if stream_sink:
            context_text = ollama_client.grounding_context_text(response["facts"], recent_turns)
            conversational_text = ollama_client.compose_conversational_streaming(
                text, response["facts"], intent_result["intent"], language=language,
                recent_turns=recent_turns, context_text=context_text, stream_sink=stream_sink,
            )
        else:
            composed = ollama_client.compose_conversational(
                text, response["facts"], intent_result["intent"], language=language,
                recent_turns=recent_turns,
            )
            conversational_text = composed["text"] if composed else None
            notable = composed["notable"] if composed else None
        if conversational_text:
            text = conversational_text
            response_source = "ollama_grounded"
            trace_log.append("Response composed conversationally by local Ollama, grounded in the "
                              "actual query results (now including the richer facts above) and "
                              "verified against them before use")
            if notable:
                trace_log.append(f'Self-critique note surfaced: "{notable}"')
        else:
            lightly_polished = ollama_client.polish_response(text, language=language)
            if lightly_polished != text:
                text = lightly_polished
                response_source = "ollama_polish"
                trace_log.append("Response polished by local Ollama model (facts unchanged, phrasing only)")
    else:
        lightly_polished = ollama_client.polish_response(text, language=language)
        if lightly_polished != text:
            text = lightly_polished
            response_source = "ollama_polish"
            trace_log.append("Response polished by local Ollama model (facts unchanged, phrasing only)")

    # Real reasoning trace for identity-focused intents — built from
    # actually-stored MatchConfidence/MatchMethod data, not recomputed
    # for display purposes.
    identity_trace = None
    if intent_result["intent"] in ("person_lookup", "repeat_offender_search") and results:
        top_person_id = results[0].get("person_id")
        if top_person_id:
            identity_trace = _build_identity_reasoning_trace(conn, top_person_id)
            trace_log.append(f"Reasoning trace built for person_id={top_person_id}: "
                              f"{identity_trace['confidence_pct']} confidence, "
                              f"{identity_trace['factor_coverage']}")

    # ── Small inline network snapshot (chat-bubble sized, not the full
    #    Network page graph) — only attached when there's an actual
    #    connection to show. ──────────────────────────────────────────
    network_snapshot = None
    snapshot_person_id = None
    if intent_result["intent"] == "network_query" and engine_payload and engine_payload.get("snapshot"):
        # graph_engine already built this directly from the heterogeneous
        # Person/Phone/Vehicle/Case graph (see _snapshot_from_path /
        # _snapshot_from_neighbors above) — a discovered multi-hop path
        # renders as the ACTUAL chain, not a generic person-only 1-hop
        # neighbourhood re-queried fresh from the DB below.
        network_snapshot = engine_payload["snapshot"]
    elif results and intent_result["intent"] in ("person_lookup", "repeat_offender_search", "gang_query", "risk_query"):
        snapshot_person_id = results[0].get("person_id")
    elif intent_result["intent"] == "network_query" and engine_payload and engine_payload.get("center"):
        snapshot_person_id = str(engine_payload["center"]).lstrip("P")
    if snapshot_person_id:
        try:
            snapshot_person_id = int(snapshot_person_id)
        except (TypeError, ValueError):
            snapshot_person_id = None
    if not network_snapshot and snapshot_person_id:
        network_snapshot = _network_snapshot(conn, snapshot_person_id)
        if network_snapshot:
            trace_log.append(f"Attached a small network snapshot for person_id={snapshot_person_id} "
                              f"({len(network_snapshot['nodes'])} nodes, {len(network_snapshot['edges'])} links)")

    suggestions = response_generator.follow_up_suggestions(intent_result["intent"], results)

    result_dict = {
        "session_id": session_id,
        "message": message,
        "interpretation": text,
        "insights": response.get("insights"),
        "notable_insight": notable,
        "intent": intent_result["intent"],
        "intent_confidence": intent_result["confidence"],
        "sql_generated": sql_text,
        "routed_engine": route_result.get("route"),
        "alias_matches": alias_matches[:5],
        "memory_recalled": memory_recall,
        "results": results[:30],
        "result_count": len(results),
        "follow_up_suggestions": suggestions,
        "pipeline_trace": trace_log,
        "engine_payload": engine_payload,
        "identity_reasoning_trace": identity_trace,
        "needs_clarification": False,
        "network_snapshot": network_snapshot,
        "response_source": response_source,
        "document_attached": None,
        "document_draft": None,
        "timestamp": datetime.now().isoformat(),
    }

    # ── 7. Store memory + update working context ────────────────────────
    memory_engine.store_turn(conn, user_id, session_id, len(session_history), "user", message,
                              entities=entities, sql_generated=sql_text)
    memory_engine.store_turn(conn, user_id, session_id, len(session_history) + 1, "assistant", text,
                              full_response=result_dict)

    context_updates = {}
    if entities.get("districts"):
        context_updates["current_district"] = entities["districts"][0]
    if intent_result["intent"] == "person_lookup" and results:
        context_updates["current_suspect"] = {"id": results[0].get("person_id"), "name": results[0].get("name")}
        context_updates["recent_person_ids"] = results[0].get("person_id")
    if results and route_result.get("target") == "fir" and results[0].get("fir_number"):
        context_updates["current_fir"] = {"fir_number": results[0]["fir_number"]}
        context_updates["recent_case_ids"] = results[0]["fir_number"]

    # Gang tracked whenever this turn's results actually carry a gang
    # affiliation — feeds "that gang" / "the syndicate" resolution next
    # turn (reference_resolver.py).
    top_gang = next((r.get("gang_affiliation") for r in results if r.get("gang_affiliation")), None)
    if top_gang:
        context_updates["current_gang"] = top_gang

    # Ordered snapshot of EXACTLY this turn's results (overwritten, not
    # accumulated) — feeds "the second one" / "the first result" next
    # turn. Reset the other list explicitly so a stale ordinal reference
    # from an earlier person-search can't wrongly resolve after a later
    # FIR search, or vice versa.
    if results and results[0].get("person_id") is not None:
        person_ids = []
        for r in results[:10]:
            try:
                person_ids.append(int(r.get("person_id")))
            except (TypeError, ValueError):
                pass
        if person_ids:
            context_updates["last_turn_person_ids"] = person_ids
            context_updates["last_turn_fir_numbers"] = []
    elif results and results[0].get("fir_number"):
        context_updates["last_turn_fir_numbers"] = [r["fir_number"] for r in results[:10] if r.get("fir_number")]
        context_updates["last_turn_person_ids"] = []

    context_updates["recent_searches"] = message
    if context_updates:
        memory_engine.update_context(conn, user_id, **context_updates)

    return result_dict


def _graph_snapshot_node(G, node_id, center_id):
    attrs = G.nodes[node_id]
    return {"data": {"id": node_id, "label": attrs.get("label", node_id), "type": attrs.get("type"),
                      "risk": attrs.get("risk") or "LOW", "is_center": node_id == center_id}}


def _snapshot_from_neighbors(G, center_id):
    """JSON-safe {"nodes","edges","center_id"} shape for one node's direct
    neighbourhood — same shape _network_snapshot() below builds from the DB,
    but sourced from the in-memory heterogeneous graph so phone/vehicle/case
    neighbours render too, not just other people."""
    nodes = [_graph_snapshot_node(G, center_id, center_id)]
    edges = []
    for n in G.neighbors(center_id):
        nodes.append(_graph_snapshot_node(G, n, center_id))
        rel = "linked_to"
        if G.has_edge(center_id, n):
            rel = list(G.get_edge_data(center_id, n).values())[0].get("relationship", "linked_to")
        elif G.has_edge(n, center_id):
            rel = list(G.get_edge_data(n, center_id).values())[0].get("relationship", "linked_to")
        edges.append({"data": {"id": f"{center_id}-{n}", "source": center_id, "target": n, "relationship": rel}})
    return {"nodes": nodes, "edges": edges, "center_id": center_id}


def _snapshot_from_path(G, path: dict, center_id: str):
    """Same shape, but built directly from one discovered multi-hop path —
    so the chat-bubble mini-graph shows the ACTUAL Person->Phone->Phone->
    Person->Vehicle->Case chain that was found, not a generic 1-hop
    neighbourhood that wouldn't include any of it."""
    nodes, seen = [], set()
    for node_id in path["path"]:
        if node_id in seen:
            continue
        seen.add(node_id)
        nodes.append(_graph_snapshot_node(G, node_id, center_id))
    edges = [{"data": {"id": f"{s['from']}-{s['to']}-{i}", "source": s["from"], "target": s["to"],
                        "relationship": s["relationship"]}}
             for i, s in enumerate(path["steps"])]
    return {"nodes": nodes, "edges": edges, "center_id": center_id}


def _dispatch_specialist(route: str, conn, entities: dict, alias_matches: list, results_hint: dict) -> dict:
    """Calls the appropriate specialist engine and normalises its output
    into a {"results": [...], **extra} shape the rest of the pipeline expects."""

    if route == "prediction_engine":
        district = entities["districts"][0] if entities.get("districts") else "Bengaluru Urban"
        crime = entities["crime_types"][0] if entities.get("crime_types") else "Theft"
        did_row = conn.execute("SELECT DistrictID FROM District WHERE DistrictName=?", (district,)).fetchone()
        csh_row = conn.execute("SELECT CrimeSubHeadID FROM CrimeSubHead WHERE CrimeHeadName=?", (crime,)).fetchone()
        if not did_row or not csh_row:
            return {"results": [], "forecast": None}
        rows = conn.execute(
            "SELECT Year, Month, CaseCount FROM CrimeTrend WHERE DistrictID=? AND CrimeSubHeadID=? ORDER BY Year, Month",
            (did_row[0], csh_row[0])
        ).fetchall()
        history = [{"year": r[0], "month": r[1], "count": r[2]} for r in rows]
        next_month = (datetime.now().month % 12) + 1
        forecast = prediction_engine.forecast_next_month(history, target_month=next_month)
        anomalies = prediction_engine.flag_anomalies(history)
        return {"results": [{"district": district, "crime_type": crime, **forecast}],
                "forecast": forecast, "anomalies": anomalies}

    if route == "similarity_engine":
        rows = conn.execute("""
            SELECT fir_id AS case_id, fir_number, crime_type, weapon_used AS weapon,
                   vehicle_involved AS vehicle, occurrence_time AS time, police_station,
                   crime_description AS mo_text
            FROM vw_fir_flat ORDER BY registration_date DESC LIMIT 120
        """).fetchall()
        cols = ["case_id", "fir_number", "crime_type", "weapon", "vehicle", "time", "police_station", "mo_text"]
        cases = [dict(zip(cols, r)) for r in rows]
        if not cases:
            return {"results": []}
        target = cases[0]
        matches = similarity_engine.find_similar_cases(target, cases, top_k=5, min_score=25)
        return {"results": matches, "target_case": target}

    if route == "timeline_engine":
        row = conn.execute("SELECT CaseMasterID, CrimeNo, CrimeRegisteredDate FROM CaseMaster ORDER BY CrimeRegisteredDate DESC LIMIT 1").fetchone()
        if not row:
            return {"results": []}
        case_id, fir_number, reg_date = row
        updates = conn.execute(
            "SELECT UpdateDate, UpdateText, OfficerName FROM InvestigationUpdate WHERE CaseMasterID=?", (case_id,)
        ).fetchall()
        update_dicts = [{"update_date": u[0], "update_text": u[1], "officer_name": u[2]} for u in updates]
        timeline = timeline_engine.build_timeline(update_dicts, reg_date)
        completeness = timeline_engine.timeline_completeness(timeline)
        return {"results": timeline, "fir_number": fir_number, "completeness": completeness}

    if route == "recommendation_engine":
        row = conn.execute("SELECT fir_id, crime_type FROM vw_fir_flat ORDER BY registration_date DESC LIMIT 1").fetchone()
        if not row:
            return {"results": []}
        case = {"crime_type": row[1]}
        leads = recommendation_engine.recommend_leads_with_stats(conn, case, timeline_gaps=None, network_hit_count=0)
        return {"results": leads}

    if route == "hotspot_ops_engine":
        # "What hotspot operations were completed today?", "Show pending
        # hotspot actions", "Summarize hotspot operations this month",
        # "Which areas had the most patrol activity this week?", "Which
        # crime patterns are repeatedly appearing in the logbook?" — see
        # _hotspot_ops_dispatch() and services/hotspot_ops.py. Reads the
        # SAME HotspotOperation table the Analytics page's hotspot click
        # panel writes to — one dataset, not a duplicate copy for the
        # chatbot to answer from.
        return _hotspot_ops_dispatch(conn, entities.get("_raw_text", ""))

    if route == "graph_engine":
        # ── Build the FULL heterogeneous graph: Person + Phone + Vehicle + Case ──
        # BUG FIX (KAVACH_vs_DRISHTI_Analysis.md §2.1 — "your best feature
        # exists and is wired to nothing"): this used to build a person-only
        # graph from PersonNetworkLink alone, even though
        # graph_engine.find_hidden_paths() and the entire
        # Phone/PersonPhoneLink/PhoneCallLink/Vehicle/PersonVehicleLink/
        # VehicleSighting schema already exist and are fully seeded with a
        # real traceable demo chain (see seed_data.py's
        # seed_phones_vehicles()). graph_engine.NODE_TYPES already covers
        # "person","phone","vehicle","location","case" — nothing here
        # needed to be redesigned, only actually called.
        persons = conn.execute("SELECT PersonIdentityID, CanonicalName, RiskCategory FROM PersonIdentity").fetchall()
        nodes = [{"id": f"P{r[0]}", "type": "person", "label": r[1], "risk": r[2]} for r in persons]
        edges = []
        for a, b, rel, strength in conn.execute(
            "SELECT PersonIdentityID_A, PersonIdentityID_B, RelationshipType, Strength FROM PersonNetworkLink"
        ).fetchall():
            edges.append({"source": f"P{a}", "target": f"P{b}", "relationship": rel or "linked_to"})

        for phone_id, phone_number in conn.execute("SELECT PhoneID, PhoneNumber FROM Phone").fetchall():
            nodes.append({"id": f"PH{phone_id}", "type": "phone", "label": phone_number})
        for person_id, phone_id in conn.execute("SELECT PersonIdentityID, PhoneID FROM PersonPhoneLink").fetchall():
            edges.append({"source": f"P{person_id}", "target": f"PH{phone_id}", "relationship": "used_phone"})
        for from_ph, to_ph, call_date, _dur in conn.execute(
            "SELECT FromPhoneID, ToPhoneID, CallDate, DurationSeconds FROM PhoneCallLink"
        ).fetchall():
            edges.append({"source": f"PH{from_ph}", "target": f"PH{to_ph}", "relationship": "called",
                           "call_date": call_date})

        for vehicle_id, reg_no, vtype in conn.execute("SELECT VehicleID, RegistrationNumber, VehicleType FROM Vehicle").fetchall():
            nodes.append({"id": f"V{vehicle_id}", "type": "vehicle", "label": reg_no, "vehicle_type": vtype})
        for person_id, vehicle_id in conn.execute("SELECT PersonIdentityID, VehicleID FROM PersonVehicleLink").fetchall():
            edges.append({"source": f"P{person_id}", "target": f"V{vehicle_id}", "relationship": "owns_vehicle"})

        seen_case_ids = set()
        for vehicle_id, case_id, crime_no in conn.execute("""
            SELECT vs.VehicleID, vs.CaseMasterID, cm.CrimeNo FROM VehicleSighting vs
            JOIN CaseMaster cm ON cm.CaseMasterID = vs.CaseMasterID
        """).fetchall():
            if case_id not in seen_case_ids:
                nodes.append({"id": f"C{case_id}", "type": "case", "label": crime_no})
                seen_case_ids.add(case_id)
            edges.append({"source": f"V{vehicle_id}", "target": f"C{case_id}", "relationship": "seen_near"})

        G = graph_engine.build_graph(nodes, edges)

        # ── Name resolution — BUG FIX (§2.3: duplicate names silently
        # resolve to the wrong person). The seed data genuinely contains
        # two different people both named "Naveen Poojary" (PersonIdentityID
        # 87 and 334) — 87 has zero connections, 334 has one. The old code
        # did `LIMIT 1` with no ORDER BY, so whichever row SQLite happened
        # to return first silently became "the" person — a real chance of
        # reporting "no records found" for someone who plainly has
        # connections. Now: when a name matches more than one identity,
        # prefer the one with the most connections in the graph we just
        # built (the more central match is the far more likely intended
        # target for a NETWORK question specifically), and surface the
        # ambiguity honestly rather than hiding it.
        raw_text = entities.get("_raw_text", "") or ""
        _TWO_PERSON_RE = re.compile(
            r'connect(ed|ion)?\s+(to|with)|\blink(ed)?\s+(to|with)|'
            r'relationship\s+(to|with|between)|\brelated\s+to\b|\bin touch with\b|'
            r'know(s)?\s+each other|\bbetween\b.*\band\b',
            re.IGNORECASE,
        )
        looks_like_two_person_query = bool(_TWO_PERSON_RE.search(raw_text))
        name_terms = results_hint.get("name_terms") or []

        def _resolve_best(term):
            rows = conn.execute(
                "SELECT PersonIdentityID FROM PersonIdentity WHERE CanonicalName = ?", (term,)
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    "SELECT PersonIdentityID FROM PersonIdentity WHERE CanonicalName LIKE ?", (f"%{term}%",)
                ).fetchall()
            if not rows:
                return None, 0
            if len(rows) == 1:
                return f"P{rows[0][0]}", 1
            best_id, best_degree = None, -1
            for (row_id,) in rows:
                node_id = f"P{row_id}"
                degree = G.degree(node_id) if node_id in G else 0
                if degree > best_degree:
                    best_id, best_degree = node_id, degree
            return best_id, len(rows)

        ambiguous_matches = []

        def _resolve_and_track(term):
            node_id, match_count = _resolve_best(term)
            if node_id and match_count > 1:
                ambiguous_matches.append({
                    "term": term, "count": match_count,
                    "chosen_label": G.nodes[node_id].get("label"),
                    "chosen_connections": G.degree(node_id),
                })
            return node_id

        # Prefer full (multi-word) name candidates for identifying DISTINCT
        # people — far more reliable than a bare single word, which
        # alias_resolver may have fuzzy-matched against several unrelated
        # people who merely share a first name. (Caught in testing: asking
        # about ONE person, "Naveen Poojary", produced name_terms containing
        # BOTH "Naveen Poojary" and an unrelated "Naveen Prasad" purely
        # because the single word "Naveen" fuzzy-matches multiple people —
        # that used to wrongly turn a single-person query into a two-person
        # path search.)
        full_name_candidates = [c for c in (entities.get("person_name_candidates") or []) if " " in c]
        distinct_targets = list(dict.fromkeys(filter(None, (_resolve_and_track(t) for t in full_name_candidates))))

        if len(distinct_targets) < 2 and looks_like_two_person_query:
            # Text clearly reads as a connection question but full-name
            # extraction alone didn't surface two people (short/single-word
            # names, e.g. "How is Ramesh connected to Suresh"). Fall back to
            # the already alias-resolved, confidence-filtered name list
            # rather than raw single words — reusing raw candidates here
            # would reopen the exact false-positive risk above (e.g. the
            # word "How" itself substring-matching some unrelated
            # "...Chowdary").
            for term in name_terms:
                node_id = _resolve_and_track(term)
                if node_id and node_id not in distinct_targets:
                    distinct_targets.append(node_id)
                if len(distinct_targets) >= 2:
                    break

        if not distinct_targets:
            for term in name_terms:
                node_id = _resolve_and_track(term)
                if node_id:
                    distinct_targets.append(node_id)
                    break

        # ── Two named people -> multi-hop path discovery ─────────────────
        # This is the literal "how is X connected to Y" capability — the
        # engine was always here (graph_engine.find_hidden_paths), it was
        # simply never called from anywhere. max_hops=6 (not the function's
        # default of 4) so the full seeded demo chain — Person -> Phone ->
        # Phone -> Person -> Vehicle -> Case is 5 hops end-to-end — is
        # always within reach.
        if len(distinct_targets) >= 2 and looks_like_two_person_query:
            source_id, target_id = distinct_targets[0], distinct_targets[1]
            paths = graph_engine.find_hidden_paths(G, source_id, target_id, max_hops=6)
            return {
                "results": [], "paths": paths, "center": source_id, "target": target_id,
                "source_label": G.nodes[source_id].get("label", source_id),
                "target_label": G.nodes[target_id].get("label", target_id),
                "ambiguous_matches": ambiguous_matches,
                "snapshot": _snapshot_from_path(G, paths[0], source_id) if paths else None,
            }

        if distinct_targets:
            target_id = distinct_targets[0]
            connections = list(G.neighbors(target_id))
            results = []
            for n in connections:
                attrs = G.nodes[n]
                is_person = attrs.get("type") == "person"
                results.append({
                    "id": n, "type": attrs.get("type"), "label": attrs.get("label"),
                    "risk_category": attrs.get("risk") if is_person else None,
                    # kept for any existing caller still reading person-shaped fields
                    "person_id": n.lstrip("P") if is_person else None,
                    "name": attrs.get("label") if is_person else None,
                })
            return {"results": results, "center": target_id, "ambiguous_matches": ambiguous_matches,
                    "snapshot": _snapshot_from_neighbors(G, target_id)}
        if name_terms:
            # A name WAS searched for (network_query requires one — see
            # brain.py's _NEEDS_NAME_INTENTS) but matched nobody in the
            # identity table. Report that honestly rather than silently
            # substituting the state's most-connected people below,
            # which would look like an answer to the search but has
            # nothing to do with the name that was actually typed — the
            # same bug class reported and fixed for person_lookup in
            # sql_builder.py above.
            return {"results": [], "center": None, "searched_name": name_terms[0]}
        top = graph_engine.compute_centrality(G, node_type_filter="person")[:10]
        return {"results": top}

    return {"results": []}


def _parse_hotspot_ops_query(text: str) -> dict:
    """Turns free text into hotspot_ops.py call parameters — see the
    dispatch block below for how each combination becomes a response.
    Deliberately simple keyword matching, same philosophy as the rest of
    this file: an inspectable mapping from officer phrasing to a real
    query, not a black box."""
    t = text.lower()
    period = None
    if re.search(r'\btoday\b|\bthis day\b', t):
        period = "day"
    elif re.search(r'\bthis week\b|\bweekly\b|\bpast week\b', t):
        period = "week"
    elif re.search(r'\bthis month\b|\bmonthly\b|\bpast month\b', t):
        period = "month"
    elif re.search(r'\bthis year\b|\byearly\b|\bannual\b|\bpast year\b', t):
        period = "year"

    statuses, status = None, None
    if re.search(r'\bpending\b|\bopen\b|\bnot (yet )?complete', t):
        statuses = ["recommended", "assigned", "started"]
    elif re.search(r'\bcompleted?\b|\bfinished\b|\bdone\b', t):
        status = "completed"
    elif re.search(r'\bstarted\b|\bin progress\b|\bongoing\b', t):
        status = "started"
    elif re.search(r'\bassigned\b', t):
        status = "assigned"

    shape = "list"
    if re.search(r'\bsummar', t):
        shape = "summary"
    elif re.search(r'\bwhich (area|district|station)\b|\bmost patrol\b|\bmost active\b', t):
        shape = "top_districts"
    elif re.search(r'crime pattern|repeatedly|recurring|repeat.*appear', t):
        shape = "top_crime_types"

    return {"period": period, "statuses": statuses, "status": status, "shape": shape}


def _hotspot_ops_dispatch(conn, message: str) -> dict:
    parsed = _parse_hotspot_ops_query(message)
    shape = parsed["shape"]

    if shape in ("summary", "top_districts", "top_crime_types"):
        s = hotspot_ops.summary(conn, period=parsed["period"] or "week")
        if shape == "top_districts":
            results = s["top_districts"]
            label = "Patrol activity by district" + (f" ({s['period']})" if s['period'] else "")
        elif shape == "top_crime_types":
            results = s["top_crime_types"]
            label = "Recurring crime patterns in the logbook" + (f" ({s['period']})" if s['period'] else "")
        else:
            results = [s]
            label = "Hotspot operations summary" + (f" ({s['period']})" if s['period'] else "")
        return {"results": results, "shape": shape, "summary": s, "intent_label": label}

    ops = hotspot_ops.list_operations(
        conn, status=parsed["status"], statuses=parsed["statuses"], period=parsed["period"], limit=100
    )
    return {"results": ops, "shape": "list", "intent_label": "Hotspot operations"}
