import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, MessageSquare, Network, BarChart2,
  FolderOpen, Users, Shield, LogOut, ClipboardList, Newspaper, MessageCircle
} from 'lucide-react'
import { useLanguage } from '../i18n/LanguageContext'
import HelpTarget from './HelpTarget'

// Nav items reference translation KEYS (not literal English strings) so
// the whole sidebar — not just the chat page — follows the language
// toggle in Header.jsx. `help` feeds the Hovering Assistant's UI
// Knowledge Registry (see components/HelpTarget.jsx) — every nav item
// is a one-time retrofit, described once here.
const NAV = [
  { section: 'Intelligence' },
  { to: '/',        icon: LayoutDashboard, labelKey: 'navDashboard', exact: true,
    help: { description: "Overview of today's FIR count, open cases, high-risk offenders, and district activity as glanceable summary numbers.", keywords: ['dashboard', 'home', 'overview', 'summary'] } },
  { to: '/chat',    icon: MessageSquare,   labelKey: 'navChat',       badge: 'AI',
    help: { description: 'Ask KAVACH questions about cases, offenders, or trends in plain language — the deterministic case-data brain, grounded only in real records.', keywords: ['chat', 'ask', 'kavach', 'ai', 'brain'] } },
  { to: '/network', icon: Network,         labelKey: 'navNetwork',
    help: { description: 'Interactive graph of known associates, gang affiliations, and links between offenders.', keywords: ['network', 'graph', 'gang', 'associates', 'links'] } },
  { section: 'Analytics' },
  { to: '/analytics',icon: BarChart2,      labelKey: 'navAnalytics',
    help: { description: 'Trend charts, hotspot maps, and prediction-accuracy tracking across all recorded FIRs.', keywords: ['analytics', 'trends', 'hotspot', 'charts', 'predictions'] } },
  { to: '/cases',   icon: FolderOpen,      labelKey: 'navCases',
    help: { description: 'Search, filter, and open individual FIR case records; ingest new scanned documents here.', keywords: ['cases', 'fir', 'files', 'search', 'ingest'] } },
  { to: '/profiles',icon: Users,           labelKey: 'navProfiles',
    help: { description: 'Search and review individual offender risk profiles, modus operandi history, and identity confidence.', keywords: ['profiles', 'offenders', 'risk', 'identity'] } },
  { to: '/logbook', icon: ClipboardList,   labelKey: 'navLogbook',
    help: { description: 'Hotspot patrol operations — AI recommendations, officer assignments, and outcomes, with daily/weekly/monthly/yearly summaries.', keywords: ['logbook', 'patrol', 'operations', 'hotspot'] } },
  { section: 'Communications' },
  { to: '/notice-board', icon: Newspaper,  labelKey: 'navNoticeBoard',
    help: { description: 'Daily, monthly, and yearly intelligence bulletin — urgent notices, recent cases, and operational updates.', keywords: ['notice board', 'bulletin', 'intelligence', 'news'] } },
  { to: '/messages', icon: MessageCircle,  labelKey: 'navMessages',
    help: { description: 'Inter-station messaging — select a police station and send or receive messages.', keywords: ['messages', 'station', 'chat', 'communication'] } },
]

export default function Sidebar({ user, onLogout, loggingOut = false }) {
  const { t } = useLanguage()
  const initials = user?.full_name
    ? user.full_name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'KSP'

  return (
    <aside className="sidebar">
      {/* Logo */}
      <HelpTarget id="sidebar-logo" label={t('appName')} category="chrome" asBox
        description="KAVACH — Karnataka AI Voice & Crime Hub. The application's identity mark; not interactive."
        keywords={['logo', 'kavach', 'brand']}>
        <div className="sidebar-logo">
          <div style={{
            width: 34, height: 34, borderRadius: 6,
            background: 'linear-gradient(135deg, #C5A028 0%, #8A6E1A 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0
          }}>
            <Shield size={18} color="#fff" />
          </div>
          <div>
            <div className="logo-text">{t('appName')}</div>
            <div className="logo-sub">Karnataka State Police</div>
          </div>
        </div>
      </HelpTarget>

      {/* Online status */}
      <HelpTarget id="sidebar-status" label="Connection status" category="chrome" asBox
        description="Shows KAVACH is connected to the backend and your session is active."
        keywords={['status', 'online', 'connection', 'secure']}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 16px',
          borderBottom: '1px solid rgba(197,160,40,0.1)',
        }}>
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: '#0F7A5A',
            boxShadow: '0 0 0 2px rgba(15,122,90,0.3)',
          }} />
          <span style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.4)', letterSpacing: '0.04em' }}>
            {t('secureConnection')} ● {t('online')}
          </span>
        </div>
      </HelpTarget>

      {/* Nav */}
      <nav style={{ flex: 1, overflowY: 'auto', minHeight: 0, padding: '0.5rem 0' }}>
        {NAV.map((item, i) => {
          if (item.section) {
            return <div key={i} className="nav-section-label">{item.section}</div>
          }
          return (
            <HelpTarget
              key={item.to}
              id={`sidebar-nav-${item.labelKey}`}
              label={t(item.labelKey)}
              category="sidebar-nav"
              description={item.help?.description}
              keywords={item.help?.keywords}
            >
              <NavLink
                to={item.to}
                end={item.exact}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                <item.icon size={15} className="nav-icon" />
                <span style={{ flex: 1 }}>{t(item.labelKey)}</span>
                {item.badge && (
                  <span style={{
                    fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.06em',
                    background: 'rgba(197,160,40,0.2)', color: '#C5A028',
                    padding: '2px 6px', borderRadius: 3,
                  }}>
                    {item.badge}
                  </span>
                )}
              </NavLink>
            </HelpTarget>
          )
        })}
      </nav>

      {/* Bottom: User info */}
      <div style={{ borderTop: '1px solid rgba(197,160,40,0.15)', padding: '0.75rem 1rem' }}>
        <HelpTarget id="sidebar-user" label="Your officer identity" category="chrome" asBox
          description="Your signed-in officer identity — name, role, and badge number."
          keywords={['profile', 'officer', 'identity', 'badge number']}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <div style={{
              width: 30, height: 30, borderRadius: '50%',
              background: 'rgba(197,160,40,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.72rem', fontWeight: 700, color: '#C5A028', flexShrink: 0
            }}>
              {initials}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.9)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.full_name || 'Officer'}
              </div>
              <div style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.35)', textTransform: 'capitalize' }}>
                {user?.role} ● {user?.badge_number || 'KSP'}
              </div>
            </div>
          </div>
        </HelpTarget>
        <HelpTarget id="sidebar-logout" label={t('signOut')} category="chrome"
          description="Signs you out. KAVACH automatically exports this session's chat history to PDF before logging you out."
          keywords={['logout', 'sign out', 'exit']}>
          <button
            onClick={onLogout}
            disabled={loggingOut}
            title={loggingOut ? 'Preparing your chat export before signing out…' : undefined}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 8,
              background: 'rgba(192,57,43,0.1)', border: '1px solid rgba(192,57,43,0.2)',
              borderRadius: 5, padding: '6px 10px', cursor: loggingOut ? 'wait' : 'pointer',
              color: 'rgba(255,100,80,0.8)', fontSize: '0.72rem', fontWeight: 500,
              transition: 'all 0.15s', opacity: loggingOut ? 0.7 : 1,
            }}
            onMouseOver={e => e.currentTarget.style.background = 'rgba(192,57,43,0.2)'}
            onMouseOut={e => e.currentTarget.style.background = 'rgba(192,57,43,0.1)'}
          >
            <LogOut size={12} />
            {loggingOut ? 'Exporting chat & signing out…' : t('signOut')}
          </button>
        </HelpTarget>
      </div>
    </aside>
  )
}
