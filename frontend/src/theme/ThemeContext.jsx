import { createContext, useContext, useState, useEffect, useCallback } from 'react'

/**
 * KAVACH — Theme (Dark / Light)
 * =================================
 * Available after login, from the main app UI (Header) — never touches
 * the Login page's own design, per spec. Persisted to localStorage so
 * it survives a reload/re-login.
 *
 * Mechanics: sets `data-theme="dark"|"light"` on <html>. Every themed
 * rule in index.css reads CSS custom properties (--surface, --text-1,
 * --border, etc.) that are redefined once under `[data-theme="dark"]`
 * — components never hardcode "if dark then #111" anywhere; they just
 * use the variable and the attribute switch handles the rest. Works
 * identically for CSS classes AND inline `style={{ background:
 * 'var(--surface)' }}` — CSS custom properties resolve the same way in
 * both.
 */
const ThemeContext = createContext(null)
const STORAGE_KEY = 'kavach_theme'

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved === 'dark' || saved === 'light') return saved
    } catch { /* localStorage unavailable — fall through to default */ }
    return 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem(STORAGE_KEY, theme) } catch { /* best-effort persistence */ }
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}
