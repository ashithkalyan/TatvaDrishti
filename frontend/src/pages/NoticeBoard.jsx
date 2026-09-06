import { useState, useEffect, useCallback } from 'react'
import Header from '../components/Header'
import HelpTarget from '../components/HelpTarget'
import { getNoticeBoardFeed } from '../services/api'
import {
  FileText, Users, AlertTriangle, Link2, Shield, X,
  MapPin, Calendar, Radio,
} from 'lucide-react'

const VIEWS = [
  { id: 'day', label: 'Daily' },
  { id: 'month', label: 'Monthly' },
  { id: 'year', label: 'Yearly' },
]

const RISK_COLORS = { EXTREME: '#C0392B', HIGH: '#E67E22', MEDIUM: '#F39C12', LOW: '#0F7A5A' }

function initials(name) {
  return (name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function ProfileCard({ p, onClick }) {
  const color = RISK_COLORS[p.risk_category] || '#94A3B8'
  return (
    <HelpTarget id={`notice-profile-${p.person_id}`} label={p.name} category="notice-board"
      description={`Open ${p.name}'s intelligence card — risk level, gang affiliation, and their most recent linked FIR.`}
      keywords={['profile', 'offender', 'roster']}>
      <button onClick={onClick} style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: 10, width: '100%', textAlign: 'left',
        background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer',
        transition: 'box-shadow 0.15s',
      }}
        onMouseOver={e => e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'}
        onMouseOut={e => e.currentTarget.style.boxShadow = 'none'}
      >
        {/* Silhouette/initials placeholder — deliberately not a photograph. */}
        <div style={{
          width: 42, height: 42, borderRadius: '50%', flexShrink: 0,
          background: `${color}22`, border: `2px solid ${color}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.8rem', fontWeight: 700, color,
        }}>
          {initials(p.name)}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {p.name}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 2, alignItems: 'center' }}>
            <span style={{ fontSize: '0.62rem', fontWeight: 700, color, background: `${color}18`, padding: '1px 6px', borderRadius: 999 }}>
              {p.risk_category}
            </span>
            {p.gang_affiliation && (
              <span style={{ fontSize: '0.65rem', color: 'var(--text-faint)' }}>· {p.gang_affiliation}</span>
            )}
          </div>
        </div>
      </button>
    </HelpTarget>
  )
}

function ProfileModal({ p, onClose }) {
  const color = RISK_COLORS[p.risk_category] || '#94A3B8'
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }} onClick={onClose}>
      <div style={{ background: 'var(--surface)', borderRadius: 12, width: '100%', maxWidth: 420, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,0.35)' }} onClick={e => e.stopPropagation()}>
        <div style={{ padding: 16, background: 'linear-gradient(135deg, #0B1D3A, #112347)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 52, height: 52, borderRadius: '50%', background: `${color}33`, border: `2px solid ${color}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem', fontWeight: 700, color, flexShrink: 0 }}>
            {initials(p.name)}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#C5A028' }}>{p.name}</div>
            <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)' }}>{p.district || 'District not on file'}</div>
          </div>
          <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 6, width: 26, height: 26, color: '#fff', cursor: 'pointer', flexShrink: 0 }}>
            <X size={13} />
          </button>
        </div>
        <div style={{ padding: 16 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <span style={{ fontSize: '0.7rem', fontWeight: 700, color, background: `${color}18`, padding: '3px 10px', borderRadius: 999 }}>{p.risk_category} RISK</span>
            {p.gang_affiliation && <span style={{ fontSize: '0.7rem', color: 'var(--text-3)', background: 'var(--surface-subtle)', padding: '3px 10px', borderRadius: 999 }}>{p.gang_affiliation}</span>}
          </div>
          {p.modus_operandi && (
            <div style={{ fontSize: '0.78rem', color: 'var(--text-3)', marginBottom: 12, lineHeight: 1.5 }}>{p.modus_operandi}</div>
          )}
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10 }}>
            <div style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 6 }}>Most Recent Linked Case</div>
            {p.latest_fir_number ? (
              <>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-1)' }}>{p.latest_crime_type || 'Crime type not on file'}</div>
                <div style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#1D4ED8', marginTop: 2 }}>FIR: {p.latest_fir_number}</div>
              </>
            ) : (
              <div style={{ fontSize: '0.78rem', color: 'var(--text-faint)' }}>No case linked in the identity database yet.</div>
            )}
          </div>
          <a href={`/profiles?id=${p.person_id}`} style={{ display: 'block', marginTop: 14, textAlign: 'center', padding: '8px', background: '#0B1D3A', color: '#C5A028', borderRadius: 6, fontSize: '0.78rem', fontWeight: 600, textDecoration: 'none' }}>
            View full profile
          </a>
        </div>
      </div>
    </div>
  )
}

export default function NoticeBoard({ user }) {
  const [view, setView] = useState('day')
  const [feed, setFeed] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedProfile, setSelectedProfile] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    getNoticeBoardFeed(view).then(setFeed).finally(() => setLoading(false))
  }, [view])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header title="Police Intelligence Board" subtitle="Daily, monthly & yearly intelligence bulletin" user={user} />
      <div className="page-content">

        {/* Masthead */}
        <div style={{
          background: 'linear-gradient(135deg, #0B1D3A 0%, #112347 100%)', borderRadius: 10,
          padding: '16px 20px', marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12,
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Shield size={18} color="#C5A028" />
              <span style={{ fontSize: '1.1rem', fontWeight: 700, color: '#C5A028', letterSpacing: '0.02em' }}>KAVACH Intelligence Board</span>
            </div>
            {feed && (
              <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.6)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 5 }}>
                <Calendar size={11} />
                {view === 'day' && `Bulletin for ${new Date(feed.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' })}`}
                {view === 'month' && `Monthly digest — ${new Date(feed.date).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}`}
                {view === 'year' && `Annual overview — ${new Date(feed.date).getFullYear()}`}
              </div>
            )}
          </div>
          <HelpTarget id="notice-view-tabs" label="Bulletin period" category="notice-board"
            description="Switches the whole board between daily, monthly, and yearly intelligence summaries."
            keywords={['daily', 'monthly', 'yearly', 'view']}>
            <div style={{ display: 'flex', gap: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 8, padding: 4 }}>
              {VIEWS.map(v => (
                <button key={v.id} onClick={() => setView(v.id)} style={{
                  padding: '6px 14px', fontSize: '0.75rem', fontWeight: 600, borderRadius: 6, border: 'none', cursor: 'pointer',
                  background: view === v.id ? '#C5A028' : 'transparent',
                  color: view === v.id ? '#0B1D3A' : 'rgba(255,255,255,0.8)',
                }}>
                  {v.label}
                </button>
              ))}
            </div>
          </HelpTarget>
        </div>

        {loading || !feed ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading intelligence feed…</div>
        ) : (
          <>
            {/* Headline stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12, marginBottom: 18 }}>
              <div className="kpi-card blue"><FileText size={16} color="#2563EB" /><div className="kpi-value">{feed.headline_stats.total_firs}</div><div className="kpi-label">FIRs This Period</div></div>
              <div className="kpi-card green"><Users size={16} color="#0F7A5A" /><div className="kpi-value">{feed.headline_stats.arrests}</div><div className="kpi-label">Arrests</div></div>
              <div className="kpi-card red"><AlertTriangle size={16} color="#C0392B" /><div className="kpi-value">{feed.headline_stats.weapon_involved_cases}</div><div className="kpi-label">Weapon-Involved</div></div>
              <div className="kpi-card amber"><Link2 size={16} color="#E67E22" /><div className="kpi-value">{feed.headline_stats.gang_linked_cases}</div><div className="kpi-label">Gang-Linked</div></div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16, alignItems: 'start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Urgent notices */}
                <div className="card">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 700, color: '#C0392B', marginBottom: 10 }}>
                    <Radio size={14} /> Urgent Notices
                  </div>
                  {feed.urgent_notices.length === 0 ? (
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-faint)' }}>No high-gravity or weapon-involved cases for this period.</div>
                  ) : feed.urgent_notices.map(n => (
                    <div key={n.fir_number} style={{ borderLeft: '3px solid #C0392B', paddingLeft: 10, marginBottom: 10 }}>
                      <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-1)' }}>{n.crime_type} — {n.district}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-4)', marginTop: 2 }}>{n.brief}</div>
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-faint)', marginTop: 3, fontFamily: 'monospace' }}>FIR {n.fir_number} · {n.date}</div>
                    </div>
                  ))}
                </div>

                {/* Recent cases */}
                <div className="card">
                  <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-2)', marginBottom: 10 }}>Recent Cases &amp; Events</div>
                  {feed.recent_cases.length === 0 ? (
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-faint)' }}>No cases registered in this period.</div>
                  ) : feed.recent_cases.map(c => (
                    <div key={c.fir_number} style={{ padding: '8px 0', borderBottom: '1px solid var(--surface-subtle-2)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                        <strong style={{ color: 'var(--text-1)' }}>{c.crime_type}</strong>
                        <span style={{ color: 'var(--text-faint)', fontSize: '0.68rem' }}>{c.date}</span>
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-4)', display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                        <MapPin size={10} /> {c.district}{c.police_station ? ` — ${c.police_station}` : ''} · {c.status}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Featured profiles — high-alert roster */}
              <div className="card">
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-2)', marginBottom: 4 }}>High-Alert Roster</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-faint)', marginBottom: 10 }}>
                  Top offenders by computed risk score — click any card for their most recent linked case.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {feed.featured_profiles.map(p => (
                    <ProfileCard key={p.person_id} p={p} onClick={() => setSelectedProfile(p)} />
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {selectedProfile && <ProfileModal p={selectedProfile} onClose={() => setSelectedProfile(null)} />}
    </div>
  )
}
