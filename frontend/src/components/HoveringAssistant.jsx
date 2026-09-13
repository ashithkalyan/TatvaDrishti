import { useState, useRef, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { X, Crosshair, Send, MapPin } from 'lucide-react'
import { useLanguage } from '../i18n/LanguageContext'
import { useHelpRegistry } from '../hoverAssistant/helpRegistry'
import { useScreenContext } from '../hoverAssistant/screenContextStore'
import {
  classifyUiHelp, parseSpatialQuery, resolveSpatial, localQuickMatch, pageNameForPath,
} from '../hoverAssistant/uiIntentRouter'
import { resolveUiHelp, sendChatMessage } from '../services/api'
import InspectorOverlay from './InspectorOverlay'
import HelpTarget from './HelpTarget'
import AssistantMascot from './AssistantMascot'

// Answered locally, instantly, never forwarded anywhere — see the
// module note in uiIntentRouter.js for why this only needs to be a
// question-shape + UI-noun match, not real NLP.
const LOOKING_AT_RE = /\bwhat am i (looking at|on)\b|\bwhich (page|screen) am i\b|\bwhat page is this\b|\bwhere am i\b/
const SELF_CAPABILITY_RE = /\bwhat can you (do|help)\b|\bwhat are you\b|\bwho are you\b|\bwhat is this assistant\b|\bhow do you work\b/

let _msgCounter = 0
const nextMsgId = () => `ha_${Date.now()}_${_msgCounter++}`

// Same sessionStorage key CrimeChat.jsx uses (see its ensureSessionId())
// — a case-data or glossary question asked here becomes part of the
// SAME investigative session, so it shows up seamlessly if the officer
// later opens the full Chat page, and is included in that session's
// export exactly like any other turn. Pure UI-navigation answers
// (registry lookups) never call this at all — see submit() below.
const SESSION_KEY = 'kavach_active_chat_session'
function ensureAssistantSessionId() {
  let sid = sessionStorage.getItem(SESSION_KEY)
  if (!sid) {
    sid = `sess_${Math.random().toString(36).slice(2, 10)}`
    sessionStorage.setItem(SESSION_KEY, sid)
  }
  return sid
}

const toCandidate = (e) => ({ id: e.id, label: e.label || '', keywords: e.keywords || [] })

const DIRECTION_LABEL = { left: 'Left of', right: 'Right of', above: 'Above', below: 'Below', near: 'Near' }

export default function HoveringAssistant({ user }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const registryEntries = useHelpRegistry()
  const { page, modal, modalMeta, setPage } = useScreenContext()

  const [open, setOpen] = useState(false)
  const [inspecting, setInspecting] = useState(false)
  const [mascotState, setMascotState] = useState('idle')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const inputRef = useRef(null)
  const scrollRef = useRef(null)

  // Screen-context awareness (point 4 of the design doc) — the one
  // piece of wiring every page gets for free, no per-page opt-in.
  // Modal-level context (setModal/clearModal) is opt-in per component
  // — see screenContextStore.js.
  useEffect(() => {
    setPage(pageNameForPath(location.pathname), location.pathname)
  }, [location.pathname, setPage])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, loading])

  useEffect(() => {
    if (open && !inspecting) {
      const timer = setTimeout(() => inputRef.current?.focus(), 60)
      return () => clearTimeout(timer)
    }
    return undefined
  }, [open, inspecting])

  const pageEntries = () => registryEntries.filter(e => e.id !== 'ha-badge' && (!e.page || e.page === page))

  const pushMessage = (msg) => setMessages((m) => [...m, { id: nextMsgId(), ...msg }])

  const describeEntry = (entry) => {
    const desc = (language === 'kn' && entry.descriptionKn) ? entry.descriptionKn : entry.description
    return desc || `No description registered for "${entry.label}" yet.`
  }

  const flashSpeaking = () => {
    setMascotState('speaking')
    setTimeout(() => setMascotState('idle'), 1500)
  }

  const answerWithEntry = (entry, directionNote) => {
    pushMessage({ role: 'assistant', kind: 'ui_help', title: entry.label, note: directionNote, text: describeEntry(entry) })
    flashSpeaking()
  }

  const answerFallback = (customText) => {
    const entries = pageEntries().slice(0, 8)
    pushMessage({
      role: 'assistant',
      kind: 'fallback',
      text: customText || t('haFallbackText'),
      chips: entries,
    })
    setMascotState('idle')
  }

  const handlePick = (entry) => {
    setInspecting(false)
    setOpen(true)
    pushMessage({ role: 'user', kind: 'point', text: `${t('haPointedAt')}: ${entry.label}` })
    answerWithEntry(entry)
  }

  const submit = async (raw) => {
    const text = (raw ?? input).trim()
    if (!text || loading) return
    setInput('')
    pushMessage({ role: 'user', text })
    const lower = text.toLowerCase()

    // "What am I looking at" — answered straight from screen-context,
    // no matching needed at all.
    if (LOOKING_AT_RE.test(lower)) {
      const where = modal
        ? `${page} — ${modal}${modalMeta?.firNumber ? ` (${modalMeta.firNumber})` : ''}`
        : page
      pushMessage({ role: 'assistant', kind: 'context', text: `You're on the ${where} screen.` })
      flashSpeaking()
      return
    }

    // The assistant explaining itself.
    if (SELF_CAPABILITY_RE.test(lower)) {
      pushMessage({ role: 'assistant', kind: 'context', text: t('haSelfCapability') })
      flashSpeaking()
      return
    }

    // Spatial phrase — "left of the send button", "what's near the mic"
    const spatial = parseSpatialQuery(text)
    if (spatial) {
      const entries = pageEntries()
      let anchorEntry = localQuickMatch(spatial.anchorPhrase, entries)[0]?.entry
      if (!anchorEntry) {
        setLoading(true)
        setMascotState('thinking')
        try {
          const res = await resolveUiHelp(spatial.anchorPhrase, entries.map(toCandidate))
          const top = (res.matches || [])[0]
          anchorEntry = top ? entries.find((e) => e.id === top.id) : null
        } catch {
          anchorEntry = null
        } finally {
          setLoading(false)
        }
      }
      if (anchorEntry) {
        const found = resolveSpatial(anchorEntry, spatial.direction, entries)
        if (found.length > 0) {
          answerWithEntry(found[0], `${DIRECTION_LABEL[spatial.direction]} "${anchorEntry.label}"`)
          return
        }
        answerFallback(`I found "${anchorEntry.label}", but nothing registered is ${spatial.direction} of it on this screen.`)
        return
      }
      answerFallback()
      return
    }

    // UI-help question — "what is this icon", "what does X do"
    if (classifyUiHelp(text)) {
      const entries = pageEntries()
      const local = localQuickMatch(text, entries)
      if (local.length > 0 && local[0].confidence >= 0.9) {
        answerWithEntry(local[0].entry)
        return
      }
      setLoading(true)
      setMascotState('thinking')
      try {
        const res = await resolveUiHelp(text, entries.map(toCandidate))
        const top = (res.matches || [])[0]
        const entry = top ? entries.find((e) => e.id === top.id) : null
        if (entry && top.confidence >= 0.55) {
          answerWithEntry(entry)
        } else {
          answerFallback()
        }
      } catch {
        answerFallback()
      } finally {
        setLoading(false)
      }
      return
    }

    // Everything else — real case-data or glossary questions — go
    // straight to the SAME brain.py pipeline the Chat page uses.
    // brain.py sorts out data-vs-glossary itself (see
    // general_knowledge.py); this widget just displays the result.
    setLoading(true)
    setMascotState('thinking')
    try {
      const sid = ensureAssistantSessionId()
      const data = await sendChatMessage(text, sid, language)
      const kind = data.response_source === 'general_knowledge' ? 'general_knowledge' : 'case_data'
      pushMessage({ role: 'assistant', kind, text: data.interpretation, resultCount: data.result_count })
      flashSpeaking()
    } catch {
      pushMessage({ role: 'assistant', kind: 'error', text: t('haUnreachable') })
      setMascotState('idle')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <InspectorOverlay active={inspecting} onPick={handlePick} onExit={() => setInspecting(false)} />

      <HelpTarget
        id="ha-badge"
        label={t('haTitle')}
        description="Ask about anything on this screen, or get help with case data and terminology. Point at any button or icon for an instant explanation, or type a question here."
        category="assistant"
        keywords={['assistant', 'help', 'mascot', 'badge', 'guide']}
      >
        <button
          className="ha-badge"
          onClick={() => (inspecting ? setInspecting(false) : setOpen((o) => !o))}
          style={{ display: inspecting ? 'none' : 'flex' }}
          aria-label={t('haTitle')}
          title={t('haBadgeTitle')}
        >
          <AssistantMascot state={open ? mascotState : 'idle'} size={38} />
        </button>
      </HelpTarget>

      {open && !inspecting && (
        <div className="ha-panel">
          <div className="ha-panel-header">
            <AssistantMascot state={mascotState} size={28} />
            <div className="ha-panel-title">
              <div className="ha-panel-title-main">{t('haTitle')}</div>
              <div className="ha-panel-title-sub">
                <MapPin size={9} style={{ marginRight: 3, verticalAlign: -1 }} />
                {page}{modal ? ` · ${modal}` : ''}
              </div>
            </div>
            <button className="ha-icon-btn" onClick={() => setOpen(false)} aria-label="Close">
              <X size={14} />
            </button>
          </div>

          <div className="ha-messages" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="ha-empty-state">
                {t('haEmptyState')}
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`ha-msg ha-msg-${m.role}`}>
                {m.title && <div className="ha-msg-title">{m.title}</div>}
                {m.note && <div className="ha-msg-note">{m.note}</div>}
                <div className="ha-msg-text">{m.text}</div>
                {m.kind === 'general_knowledge' && (
                  <div className="ha-msg-badge">{t('haGeneralGuidance')}</div>
                )}
                {m.kind === 'case_data' && (
                  <div className="ha-msg-badge ha-msg-badge-case">
                    {m.resultCount ?? 0} record{m.resultCount === 1 ? '' : 's'} — {t('haFromDatabase')}
                  </div>
                )}
                {(m.kind === 'case_data' || m.kind === 'general_knowledge') && (
                  <button className="ha-link-btn" onClick={() => { setOpen(false); navigate('/chat') }}>
                    {t('haOpenInChat')}
                  </button>
                )}
                {m.chips && m.chips.length > 0 && (
                  <div className="ha-chip-row">
                    {m.chips.map((entry) => (
                      <button key={entry.id} className="ha-chip" onClick={() => answerWithEntry(entry)}>
                        {entry.label}
                      </button>
                    ))}
                  </div>
                )}
                {m.kind === 'fallback' && m.chips && m.chips.length === 0 && (
                  <span className="ha-chip-empty">{t('haNothingRegistered')}</span>
                )}
              </div>
            ))}
            {loading && (
              <div className="ha-msg ha-msg-assistant">
                <div className="ha-thinking-dots"><span /><span /><span /></div>
              </div>
            )}
          </div>

          <div className="ha-input-bar">
            <button
              className="ha-icon-btn ha-point-btn"
              title={t('haPointHint')}
              onClick={() => { setOpen(false); setInspecting(true) }}
            >
              <Crosshair size={14} />
            </button>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
              placeholder={t('haPlaceholder')}
            />
            <button
              className="ha-icon-btn ha-send-btn"
              onClick={() => submit()}
              disabled={!input.trim() || loading}
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      )}
    </>
  )
}
