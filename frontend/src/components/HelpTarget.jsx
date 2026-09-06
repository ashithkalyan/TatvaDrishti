import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { helpRegistry } from '../hoverAssistant/helpRegistry'
import { pageNameForPath } from '../hoverAssistant/uiIntentRouter'

/**
 * KAVACH — HelpTarget
 * =======================
 * Wrap any meaningful element (button, icon, panel, dropdown, badge —
 * see KAVACH_vs_DRISHTI_Analysis.md) once, and the Hovering Assistant
 * can explain it forever after: point-and-click inspector mode, typed
 * questions, and spatial phrases ("what's left of the send button")
 * all read straight from what's registered here. Retrofitting an
 * existing component is mechanical: wrap it, describe it, done — no
 * change to the wrapped element's own behaviour.
 *
 *   <HelpTarget
 *     id="chat-attach-btn"
 *     label="Attach File"
 *     description="Upload a scanned FIR, photograph, or PDF..."
 *     category="chat-toolbar"
 *     keywords={['paperclip', 'upload', 'attach', 'document', 'scan']}
 *   >
 *     <button><PaperclipIcon /></button>
 *   </HelpTarget>
 *
 * Renders as `display: contents` by default — a real DOM node (so
 * data-help-id is genuinely present for inspector mode's
 * elementFromPoint()/.closest() lookup, and so the registry has an
 * ancestor to register), but one that never affects layout: it
 * generates no box of its own, so it's safe to drop around an existing
 * element inside a flex/grid row without touching that row's spacing.
 * getRect() reads the wrapped element's own box (its first DOM child)
 * rather than the wrapper's, since a `display: contents` node has none.
 *
 * Pass `asBox` when you actually want HelpTarget to BE the rendered
 * box (e.g. wrapping something without a single element child) — it
 * then renders as a real `<span>`/`as` element instead of a
 * layout-transparent shell.
 */
export default function HelpTarget({
  id,
  label,
  description,
  descriptionKn,
  category,
  keywords = [],
  page,
  asBox = false,
  as: Tag = 'span',
  children,
  style,
  ...rest
}) {
  const ref = useRef(null)
  const location = useLocation()
  const resolvedPage = page || pageNameForPath(location.pathname)

  useEffect(() => {
    if (!id) return undefined
    helpRegistry.register({
      id,
      label,
      description,
      descriptionKn,
      category,
      keywords,
      page: resolvedPage,
      getRect: () => {
        const node = ref.current
        if (!node) return null
        if (asBox) return node.getBoundingClientRect()
        return (node.firstElementChild || node).getBoundingClientRect()
      },
    })
    return () => helpRegistry.unregister(id)
    // Re-register whenever the describable facts change — cheap (it's
    // a Map.set), and keeps the registry accurate if a page passes a
    // dynamic description (e.g. one that includes live state).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, label, description, descriptionKn, category, JSON.stringify(keywords), resolvedPage])

  const computedStyle = asBox ? style : { ...style, display: 'contents' }

  return (
    <Tag ref={ref} data-help-id={id} style={computedStyle} {...rest}>
      {children}
    </Tag>
  )
}
