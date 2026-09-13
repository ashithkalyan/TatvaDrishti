/**
 * KAVACH — Local Intent Router
 * ================================
 * Routes a message typed/spoken into the Hovering Assistant to one of
 * three places (see KAVACH_vs_DRISHTI_Analysis.md's architecture
 * diagram):
 *
 *   1. UI Knowledge Registry (this file + helpRegistry.js)  — "what is
 *      this button", point-and-click, spatial phrases
 *   2. The existing brain.py chat pipeline (services/api.js)  — real
 *      case-data questions, forwarded to /api/chat exactly as
 *      CrimeChat.jsx already does
 *   3. general_knowledge.py, glossary terms (BNS/IPC, "what's an FIR")
 *      — already handled INSIDE the same /api/chat call by brain.py's
 *      own bounded fallback (see backend/brain/general_knowledge.py),
 *      so #2 and #3 share one code path here: anything that isn't a
 *      UI question just goes to /api/chat and brain.py sorts out
 *      which of the two it is.
 *
 * "Local" is deliberate: this classifier runs entirely in the browser,
 * so deciding "is this a UI question" never costs a network round
 * trip, and point-and-click / spatial resolution literally cannot run
 * anywhere but the browser (they read live DOM geometry). The pattern
 * language below is intentionally kept in lock-step with
 * backend/brain/intent_engine.py's UI_HELP_QUESTION_PATTERNS /
 * UI_HELP_TARGET_PATTERNS — that backend copy is a safety net for a UI
 * question typed into the ordinary case-chat box instead of here; if
 * you change one, change both.
 */

export const ROUTE_TO_PAGE = {
  '/': 'Dashboard',
  '/chat': 'Chat',
  '/network': 'Network',
  '/analytics': 'Analytics',
  '/cases': 'Cases',
  '/profiles': 'Profiles',
}

export function pageNameForPath(pathname) {
  return ROUTE_TO_PAGE[pathname] || pathname
}

// ── 1. UI-help classification ──────────────────────────────────────────
const UI_HELP_QUESTION_PATTERNS = [
  /\bwhat is this\b/, /\bwhat does this\b/, /\bwhat'?s this\b/,
  /\bwhat is that\b/, /\bwhat does that\b/, /\bwhat'?s that\b/,
  /\bhow do i\b/, /\bhow does .* work\b/, /\bhow can i\b/,
  /\bwhere (is|can i find|do i)\b/,
  /\bwhat (is|does|are) (the|this|that)\b/,
]
const UI_HELP_TARGET_PATTERNS = [
  /\bbutton\b/, /\bicon\b/, /\btab\b/, /\bmenu\b/, /\bdropdown\b/,
  /\bpanel\b/, /\bscreen\b/, /\bpage\b/, /\btoolbar\b/, /\bsidebar\b/,
  /\bsymbol\b/, /\bwidget\b/, /\btoggle\b/, /\bchip\b/, /\btooltip\b/,
  /\bfeature\b/, /\boption\b/, /\bclick(ed|ing)?\b/, /\btap(ped|ping)?\b/,
  /\bapp\b/,
]

/** True only when the message reads as a question about the KAVACH
 *  screen itself — requires BOTH a question shape and an explicit UI
 *  noun, same conservative AND-gate as the backend copy, so a real
 *  case question ("what is his risk score") never gets misrouted. */
export function classifyUiHelp(text) {
  const t = (text || '').toLowerCase().trim()
  const hasQuestion = UI_HELP_QUESTION_PATTERNS.some(p => p.test(t))
  const hasTarget = UI_HELP_TARGET_PATTERNS.some(p => p.test(t))
  return hasQuestion && hasTarget
}

// ── 2. Spatial phrases ("left of the text box") ───────────────────────
const DIRECTION_PATTERNS = [
  { dir: 'left', re: /\bleft of\b|\bto the left of\b/ },
  { dir: 'right', re: /\bright of\b|\bto the right of\b/ },
  { dir: 'above', re: /\babove\b|\bover the\b|\btop of\b/ },
  { dir: 'below', re: /\bbelow\b|\bunder(neath)?\b|\bbeneath\b/ },
  { dir: 'near', re: /\bnext to\b|\bnear\b|\bbeside\b|\bclose to\b/ },
]

/** Extracts { direction, anchorPhrase } from a spatial question, or
 *  null if the message doesn't read as one. anchorPhrase is the noun
 *  phrase that follows the directional cue — resolved to a concrete
 *  registry entry by the caller (fuzzy-matched the same way any other
 *  typed phrase is) before resolveSpatial() below can run. */
export function parseSpatialQuery(text) {
  const t = (text || '').toLowerCase().trim()
  const match = DIRECTION_PATTERNS.find(d => d.re.test(t))
  if (!match) return null
  const idx = t.search(match.re)
  const cueMatch = t.slice(idx).match(match.re)
  const after = t.slice(idx + (cueMatch ? cueMatch[0].length : 0))
  const anchorPhrase = after
    .replace(/^(the|a|an|of)\s+/, '')
    .replace(/[?.!]+$/, '')
    .trim()
  if (!anchorPhrase) return null
  return { direction: match.dir, anchorPhrase }
}

const WINDOW_PX = 180
const CROSS_AXIS_TOLERANCE = 48

function midY(r) { return r.top + r.height / 2 }
function midX(r) { return r.left + r.width / 2 }
function centerDistance(a, b) {
  return Math.hypot(midX(a) - midX(b), midY(a) - midY(b))
}

/** Given the resolved anchor entry, a direction, and every entry
 *  registered on the current page, returns entries that sit in that
 *  geometric direction from the anchor — plain arithmetic on
 *  getBoundingClientRect() output, closest first. No model involved;
 *  composes directly with the fuzzy anchor-resolution step above it. */
export function resolveSpatial(anchorEntry, direction, allEntries) {
  const anchorRect = anchorEntry?.getRect?.()
  if (!anchorRect) return []
  const scored = []
  for (const e of allEntries) {
    if (e.id === anchorEntry.id) continue
    const r = e.getRect?.()
    if (!r || (r.width === 0 && r.height === 0)) continue

    let inDirection = false
    let distance = 0
    if (direction === 'left') {
      const dx = anchorRect.left - r.right
      inDirection = dx >= -4 && dx <= WINDOW_PX && Math.abs(midY(r) - midY(anchorRect)) <= CROSS_AXIS_TOLERANCE
      distance = dx
    } else if (direction === 'right') {
      const dx = r.left - anchorRect.right
      inDirection = dx >= -4 && dx <= WINDOW_PX && Math.abs(midY(r) - midY(anchorRect)) <= CROSS_AXIS_TOLERANCE
      distance = dx
    } else if (direction === 'above') {
      const dy = anchorRect.top - r.bottom
      inDirection = dy >= -4 && dy <= WINDOW_PX && Math.abs(midX(r) - midX(anchorRect)) <= CROSS_AXIS_TOLERANCE
      distance = dy
    } else if (direction === 'below') {
      const dy = r.top - anchorRect.bottom
      inDirection = dy >= -4 && dy <= WINDOW_PX && Math.abs(midX(r) - midX(anchorRect)) <= CROSS_AXIS_TOLERANCE
      distance = dy
    } else if (direction === 'near') {
      distance = centerDistance(r, anchorRect)
      inDirection = distance <= WINDOW_PX
    }
    if (inDirection) scored.push({ entry: e, distance })
  }
  return scored.sort((a, b) => a.distance - b.distance).map(s => s.entry)
}

// ── 3. Instant local matching (before falling back to the backend) ────
// Covers the common case — an exact label/keyword mention — with zero
// network latency. Only genuinely fuzzy/misspelled/phonetic phrasing
// needs the backend's reuse of alias_resolver.resolve_name() (see
// services/api.js's resolveUiHelp() and brain/ui_help_registry.py).
export function localQuickMatch(query, entries) {
  const q = (query || '').toLowerCase()
  if (!q) return []
  const scored = []
  for (const e of entries) {
    const label = (e.label || '').toLowerCase()
    if (label && label.length > 2 && q.includes(label)) {
      scored.push({ entry: e, confidence: 0.97, reason: `You mentioned "${e.label}" directly` })
      continue
    }
    const kw = (e.keywords || []).find(k => k && k.length > 2 && q.includes(k.toLowerCase()))
    if (kw) {
      scored.push({ entry: e, confidence: 0.93, reason: `Matched keyword "${kw}"` })
    }
  }
  return scored.sort((a, b) => b.confidence - a.confidence)
}
