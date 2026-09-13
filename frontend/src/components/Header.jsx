import { Bell, Globe, ChevronRight, Moon, Sun } from 'lucide-react'
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLanguage } from '../i18n/LanguageContext'
import { useTheme } from '../theme/ThemeContext'
import { getStationsUnreadCount } from '../services/api'
import HelpTarget from './HelpTarget'

// Language now comes from the shared LanguageContext instead of being
// passed in per-page — previously only CrimeChat.jsx wired up a
// language/onLanguageToggle prop pair on this component, so every other
// page (Dashboard, Analytics, Cases, Profiles, Network) never even
// showed the toggle button. Now every page that renders <Header> gets
// the same toggle, backed by the same global state, automatically.
export default function Header({ title, subtitle, user, alerts = [] }) {
  const [time, setTime] = useState(new Date())
  const [unreadMessages, setUnreadMessages] = useState(0)
  const { language, toggleLanguage, t } = useLanguage()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    // BUG FIX (master-prompt review, section 6): the bell used to be
    // purely decorative — no click handler, no real count, `alerts`
    // was always an empty default. Now backed by the real
    // StationMessage table (services/station_messaging.py) and
    // clicking it opens the actual Messages page, not a dropdown that
    // goes nowhere.
    const poll = () => getStationsUnreadCount().then(d => setUnreadMessages(d.unread_count)).catch(() => {})
    poll()
    const id = setInterval(poll, 15000)
    return () => clearInterval(id)
  }, [])

  const fmt = tm => tm.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  const fmtDate = tm => tm.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })
  const alertCount = alerts.length + unreadMessages

  return (
    <header className="top-header">
      {/* Breadcrumb */}
      <div style={{ flex: 1 }}>
        <div className="header-breadcrumb">
          <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>KSP / SCRB</span>
          <ChevronRight size={12} style={{ display: 'inline', margin: '0 4px', color: 'var(--border-strong)' }} />
          <span>{title}</span>
          {subtitle && (
            <>
              <ChevronRight size={12} style={{ display: 'inline', margin: '0 4px', color: 'var(--border-strong)' }} />
              <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>{subtitle}</span>
            </>
          )}
        </div>
      </div>

      {/* Right controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        {/* Clock */}
        <div style={{
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: '0.72rem',
          color: 'var(--text-muted)',
          textAlign: 'right',
          lineHeight: 1.4,
        }}>
          <div style={{ fontWeight: 600, color: 'var(--text-3)' }}>{fmt(time)}</div>
          <div style={{ fontSize: '0.62rem' }}>{fmtDate(time)}</div>
        </div>

        {/* Divider */}
        <div style={{ width: 1, height: 28, background: 'var(--border)' }} />

        {/* Language toggle — applies app-wide now, not just to this page */}
        <HelpTarget id="header-lang-toggle" label="Language toggle" category="header"
          description="Switches every page's interface text, and the assistant's replies, between English and Kannada. AI chat replies in the Chat page translate separately."
          keywords={['language', 'kannada', 'english', 'toggle', 'globe']}>
          <button
            onClick={toggleLanguage}
            title={language === 'en' ? 'Switch to Kannada' : 'Switch to English'}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: language === 'kn' ? '#0B1D3A' : 'var(--surface-subtle)',
              border: `1px solid ${language === 'kn' ? '#C5A028' : 'var(--border)'}`,
              borderRadius: 5, padding: '4px 10px', cursor: 'pointer',
              fontSize: '0.72rem', fontWeight: 600,
              color: language === 'kn' ? '#C5A028' : 'var(--text-4)',
              transition: 'all 0.15s',
            }}
          >
            <Globe size={12} />
            {language === 'en' ? 'EN' : 'ಕನ್ನಡ'}
          </button>
        </HelpTarget>

        {/* Dark / Light theme toggle — available app-wide, post-login,
            per spec. Persisted via ThemeContext/localStorage. */}
        <HelpTarget id="header-theme-toggle" label="Theme toggle" category="header"
          description="Switches the whole application between light and dark mode. Your choice is remembered for next time."
          keywords={['theme', 'dark mode', 'light mode', 'toggle', 'appearance']}>
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--surface-subtle)',
              border: '1px solid var(--border)',
              borderRadius: 5, width: 30, height: 28, cursor: 'pointer',
              color: theme === 'dark' ? 'var(--gold-500)' : 'var(--text-4)',
              transition: 'all 0.15s',
            }}
          >
            {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
          </button>
        </HelpTarget>

        {/* Alerts bell — now a real, functional entry point into inter-
            station messaging, not a decorative showpiece. */}
        <HelpTarget id="header-alerts" label="Notifications" category="header"
          description="Opens Station Messages. Shows a live count of unread inter-station messages."
          keywords={['alerts', 'notifications', 'bell', 'messages']}>
          <div style={{ position: 'relative' }}>
            <button onClick={() => navigate('/messages')} title="Station Messages" style={{
              background: 'none', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', padding: 4,
              color: 'var(--text-muted)',
            }}>
              <Bell size={16} />
            </button>
            {alertCount > 0 && (
              <span style={{
                position: 'absolute', top: 0, right: 0,
                width: 14, height: 14, borderRadius: '50%',
                background: '#C0392B', color: '#fff',
                fontSize: '0.55rem', fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {alertCount > 9 ? '9+' : alertCount}
              </span>
            )}
          </div>
        </HelpTarget>

        {/* Divider */}
        <div style={{ width: 1, height: 28, background: 'var(--border)' }} />

        {/* User badge */}
        <HelpTarget id="header-user-badge" label="Signed-in officer" category="header" asBox
          description="Your signed-in officer identity and role, shown on every page."
          keywords={['user', 'officer', 'account', 'role']}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '4px 10px',
            background: 'var(--surface-subtle)',
            border: '1px solid var(--border)',
            borderRadius: 6,
          }}>
            <div style={{
              width: 24, height: 24, borderRadius: '50%',
              background: '#0B1D3A',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.6rem', fontWeight: 700, color: '#C5A028',
            }}>
              {user?.full_name?.split(' ').map(w => w[0]).join('').slice(0, 2) || 'KS'}
            </div>
            <div>
              <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-2)', lineHeight: 1.2 }}>
                {user?.full_name?.split(' ').slice(0, 2).join(' ') || 'Officer'}
              </div>
              <div style={{ fontSize: '0.6rem', color: 'var(--text-faint)', textTransform: 'capitalize' }}>
                {user?.role}
              </div>
            </div>
          </div>
        </HelpTarget>
      </div>
    </header>
  )
}
