import { useEffect, useRef, useState, useCallback } from 'react'
import { X, Crosshair } from 'lucide-react'
import { helpRegistry } from '../hoverAssistant/helpRegistry'
import { useLanguage } from '../i18n/LanguageContext'

/**
 * KAVACH — Inspector mode
 * ===========================
 * "Point at anything and I'll explain it" — the killer interaction
 * from KAVACH_vs_DRISHTI_Analysis.md. Modelled on browser DevTools'
 * element picker: the cursor becomes a crosshair, the nearest
 * registered <HelpTarget> ancestor under the pointer gets a live
 * highlight outline, and a click reports it straight back — a direct
 * lookup keyed to the literal DOM element the officer clicked, so
 * there is no language ambiguity to get wrong. Works on anything
 * registered, including things nobody specifically demoed.
 */
export default function InspectorOverlay({ active, onPick, onExit }) {
  const { t } = useLanguage()
  const [hovered, setHovered] = useState(null) // { entry, rect }
  const rafRef = useRef(null)

  const updateFromPoint = useCallback((x, y) => {
    const el = document.elementFromPoint(x, y)
    const host = el?.closest?.('[data-help-id]')
    if (!host) {
      setHovered(null)
      return
    }
    const id = host.getAttribute('data-help-id')
    const entry = helpRegistry.get(id)
    if (!entry) {
      setHovered(null)
      return
    }
    const rect = entry.getRect?.() || host.getBoundingClientRect()
    setHovered({ entry, rect })
  }, [])

  useEffect(() => {
    if (!active) { setHovered(null); return undefined }

    const onMove = (e) => updateFromPoint(e.clientX, e.clientY)
    const onClick = (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (hovered?.entry) onPick(hovered.entry)
    }
    const onKeyDown = (e) => { if (e.key === 'Escape') onExit() }
    // Keep the highlight box glued to its target through scrolling —
    // re-reads the same entry's live rect rather than re-hit-testing,
    // so a scroll mid-hover doesn't flicker the highlight away.
    const onScrollOrResize = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        setHovered(h => (h ? { ...h, rect: h.entry.getRect?.() || h.rect } : h))
      })
    }

    document.addEventListener('mousemove', onMove, true)
    document.addEventListener('click', onClick, true)
    document.addEventListener('keydown', onKeyDown, true)
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    document.body.style.cursor = 'crosshair'

    return () => {
      document.removeEventListener('mousemove', onMove, true)
      document.removeEventListener('click', onClick, true)
      document.removeEventListener('keydown', onKeyDown, true)
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
      document.body.style.cursor = ''
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, hovered?.entry?.id, onPick, onExit])

  if (!active) return null

  return (
    <>
      {/* Instruction banner */}
      <div style={{
        position: 'fixed', top: 14, left: '50%', transform: 'translateX(-50%)',
        zIndex: 9999, display: 'flex', alignItems: 'center', gap: 8,
        background: '#0B1D3A', border: '1px solid #C5A028', borderRadius: 999,
        padding: '6px 14px 6px 12px', boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
        pointerEvents: 'auto',
      }}>
        <Crosshair size={13} color="#C5A028" />
        <span style={{ fontSize: '0.75rem', color: '#fff', fontWeight: 500 }}>
          {t('haInspectorBanner')}
        </span>
        <button
          onClick={onExit}
          style={{
            display: 'flex', alignItems: 'center', gap: 3, marginLeft: 6,
            background: 'rgba(255,255,255,0.08)', border: 'none', borderRadius: 999,
            padding: '3px 9px', fontSize: '0.68rem', color: '#C5A028', cursor: 'pointer', fontWeight: 600,
          }}
        >
          <X size={11} /> Esc
        </button>
      </div>

      {/* Live highlight outline */}
      {hovered && (
        <>
          <div style={{
            position: 'fixed', zIndex: 9998, pointerEvents: 'none',
            left: hovered.rect.left - 4, top: hovered.rect.top - 4,
            width: hovered.rect.width + 8, height: hovered.rect.height + 8,
            border: '2px solid #C5A028', borderRadius: 6,
            background: 'rgba(197,160,40,0.12)',
            boxShadow: '0 0 0 3px rgba(197,160,40,0.15)',
            transition: 'all 0.06s ease-out',
          }} />
          <div style={{
            position: 'fixed', zIndex: 9999, pointerEvents: 'none',
            left: hovered.rect.left,
            top: Math.max(4, hovered.rect.top - 26),
            background: '#C5A028', color: '#0B1D3A',
            fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 4,
            whiteSpace: 'nowrap', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {hovered.entry.label}
          </div>
        </>
      )}
    </>
  )
}
