import { create } from 'zustand'

/**
 * KAVACH — Screen-context store
 * =================================
 * Small global store tracking what the officer is actually looking at
 * right now: current route + any open modal (see
 * KAVACH_vs_DRISHTI_Analysis.md, "4. Screen-context awareness"). Two
 * payoffs: (a) "what am I looking at" gets a real contextual answer
 * from the Hovering Assistant, and (b) a vague typed question gets
 * scoped to only the current page's registered elements (see
 * helpRegistry.js's getByPage()), which sharply improves match
 * accuracy over searching the whole app's vocabulary at once.
 *
 * `page` is set automatically by HoveringAssistant.jsx from
 * react-router's useLocation() — nothing else needs to touch it.
 * `modal` is opt-in: a component that opens a modal/drawer calls
 * setModal('FIRDetail', { firNumber }) when it opens and clearModal()
 * when it closes (see Cases.jsx's FIR detail modal for the pattern).
 * A modal not wired up simply leaves `modal` null — the assistant
 * still works fine scoped to the page alone, it just can't name the
 * open modal specifically.
 */
export const useScreenContext = create((set) => ({
  page: 'Dashboard',
  pagePath: '/',
  modal: null,        // e.g. 'FIRDetail' | 'AccusedProfile' | 'DocumentIngest' | null
  modalMeta: null,    // e.g. { firNumber: '...' }

  setPage: (page, pagePath) => set({ page, pagePath }),
  setModal: (modal, modalMeta = null) => set({ modal, modalMeta }),
  clearModal: () => set({ modal: null, modalMeta: null }),
}))
