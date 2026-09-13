/**
 * KAVACH — dev-mode HelpTarget coverage check
 * ================================================
 * "Enforce full coverage, don't hope for it." — a dev-mode console
 * warning that fires whenever a button, icon, or interactive element
 * renders without a <HelpTarget> ancestor. This is what actually gets
 * KAVACH to "the assistant never says I don't know" for the UI itself:
 * not a smarter guesser, just zero untagged elements. Turn the logged
 * list into a literal checklist to clear screen-by-screen before demo
 * day (see KAVACH_vs_DRISHTI_Analysis.md).
 *
 * Dev-build only (import.meta.env.DEV) — this never runs, and adds
 * zero overhead, in a production/judge-facing build.
 */
const INTERACTIVE_SELECTOR = [
  'button',
  '[role="button"]',
  'input[type="submit"]',
  'input[type="button"]',
  'a[href]',
].join(', ')

let debounceTimer = null

function scan() {
  const all = document.querySelectorAll(INTERACTIVE_SELECTOR)
  const untagged = []
  all.forEach((el) => {
    if (!el.closest('[data-help-id]')) untagged.push(el)
  })
  if (untagged.length > 0) {
    // eslint-disable-next-line no-console
    console.warn(
      `[HoveringAssistant] ${untagged.length} interactive element(s) on this screen have no <HelpTarget> ` +
      `ancestor yet — the assistant can't explain them. Wrap each one (see components/HelpTarget.jsx).`,
      untagged,
    )
  }
}

function scheduleScan() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(scan, 800)
}

/** Call once, high in the app tree, dev-mode only. Returns a cleanup
 *  function. Re-scans on any DOM mutation (route change, modal open,
 *  data load) so the warning stays accurate as the officer navigates. */
export function startCoverageCheck() {
  if (!import.meta.env.DEV || typeof window === 'undefined' || typeof MutationObserver === 'undefined') {
    return () => {}
  }
  const observer = new MutationObserver(scheduleScan)
  observer.observe(document.body, { childList: true, subtree: true })
  scheduleScan()
  return () => {
    observer.disconnect()
    clearTimeout(debounceTimer)
  }
}
