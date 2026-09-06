import { useSyncExternalStore } from 'react'

/**
 * KAVACH — UI Knowledge Registry
 * ==================================
 * This IS the "database" the Hovering Assistant answers UI questions
 * from — no ML, no external call, just a live map of "everything
 * currently on screen and what it means" (see
 * KAVACH_vs_DRISHTI_Analysis.md's write-up of the feature). Every
 * meaningful element gets wrapped once with <HelpTarget> (see
 * ../components/HelpTarget.jsx), which registers itself here on mount
 * and unregisters on unmount — so at any instant this map reflects
 * exactly what's rendered, on whichever page/modal is currently open.
 *
 * Implemented as a plain module-level singleton with a tiny pub/sub,
 * not a React context — functionally the same "central in-memory
 * store" the design calls for, but with no <Provider> to wrap around
 * the app and no re-render fan-out on every single mount/unmount
 * (dozens of elements register within the same tick on most page
 * loads). Components that need to react to registry changes (the dev
 * coverage checker, the assistant's "here's everything on this
 * screen" fallback) use the useHelpRegistry() hook below, which is a
 * thin useSyncExternalStore wrapper — plain reads (point-and-click,
 * the resolver) just call the methods directly and need no
 * subscription at all.
 *
 * entry shape:
 *   {
 *     id, label, description, descriptionKn, category,
 *     keywords: string[], page: string,
 *     getRect: () => DOMRect | null,
 *   }
 */
class HelpRegistry {
  constructor() {
    this.entries = new Map()
    this.listeners = new Set()
  }

  register(entry) {
    if (!entry?.id) return
    this.entries.set(entry.id, entry)
    this._emit()
  }

  unregister(id) {
    if (this.entries.delete(id)) this._emit()
  }

  get(id) {
    return this.entries.get(id) || null
  }

  getAll() {
    return Array.from(this.entries.values())
  }

  // Elements registered for the CURRENT page (or with no page tag at
  // all — a handful of chrome elements like the sidebar/header render
  // on every page and don't bother tagging one). This is what powers
  // "screen-context awareness": scoping a match to only what's
  // actually rendered right now sharply improves accuracy over
  // searching the whole app's vocabulary at once.
  getByPage(page) {
    return this.getAll().filter(e => !e.page || e.page === page)
  }

  subscribe(listener) {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  _emit() {
    this.listeners.forEach(fn => fn())
  }
}

export const helpRegistry = new HelpRegistry()

// Reactive snapshot for components that need to re-render when the
// registry changes (e.g. as the officer navigates between pages).
// getSnapshot() returns the same array reference until something
// actually changes, so this is cheap even with useSyncExternalStore's
// equality check.
let _cachedSnapshot = []
let _cachedVersion = -1
let _version = 0
helpRegistry.subscribe(() => { _version += 1 })

function _getSnapshot() {
  if (_cachedVersion !== _version) {
    _cachedSnapshot = helpRegistry.getAll()
    _cachedVersion = _version
  }
  return _cachedSnapshot
}

export function useHelpRegistry() {
  return useSyncExternalStore(
    (onStoreChange) => helpRegistry.subscribe(onStoreChange),
    _getSnapshot,
  )
}
