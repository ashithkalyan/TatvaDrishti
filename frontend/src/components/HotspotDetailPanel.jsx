import { useState, useEffect } from 'react'
import { X, AlertTriangle, Clock, FileText, ShieldAlert, Users, Truck, CheckCircle2, Loader2 } from 'lucide-react'
import { getHotspotRecommendation, createHotspotOperation, updateHotspotOperationStatus } from '../services/api'

const RISK_COLORS = { High: '#C0392B', Medium: '#E67E22', Low: '#0F7A5A', Unknown: '#94A3B8' }

/**
 * KAVACH — Hotspot intelligence panel
 * =======================================
 * "AI Recommendation -> Officer Review -> Assign Team/Vehicle -> Start
 * Action -> Complete Action" — every arrow here is a real button an
 * officer clicks, and every click is a real API call (see
 * backend/services/hotspot_ops.py). Nothing auto-advances: KAVACH
 * generates the recommendation and stops; everything past that is the
 * officer's own confirmed action, persisted so it's still there if
 * this panel is closed and reopened, or reviewed by a supervisor later.
 */
export default function HotspotDetailPanel({ hotspot, onClose }) {
  const [rec, setRec] = useState(null)
  const [loading, setLoading] = useState(true)
  const [operation, setOperation] = useState(null)
  const [busy, setBusy] = useState(false)
  const [team, setTeam] = useState('')
  const [vehicle, setVehicle] = useState('')
  const [notes, setNotes] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setOperation(null)
    getHotspotRecommendation(hotspot.district, hotspot.crime_type, hotspot.police_station)
      .then(data => { if (!cancelled) setRec(data) })
      .catch(() => { if (!cancelled) setRec(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [hotspot.district, hotspot.crime_type, hotspot.police_station])

  const logRecommendation = async () => {
    setBusy(true)
    try {
      const created = await createHotspotOperation({
        district: hotspot.district, crime_type: hotspot.crime_type, police_station: hotspot.police_station,
        latitude: hotspot.lat, longitude: hotspot.lng,
        recommended_action: rec.recommended_action, suggested_period: rec.suggested_period, reason: rec.reason,
      })
      setOperation({ operation_id: created.operation_id, status: 'recommended' })
    } finally {
      setBusy(false)
    }
  }

  const advance = async (status, extra = {}) => {
    setBusy(true)
    try {
      await updateHotspotOperationStatus(operation.operation_id, { status, ...extra })
      setOperation(o => ({ ...o, status, ...extra }))
    } finally {
      setBusy(false)
    }
  }

  const riskColor = RISK_COLORS[rec?.risk_level] || RISK_COLORS.Unknown

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 2000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
    }} onClick={onClose}>
      <div
        style={{
          background: 'var(--surface)', borderRadius: 12, width: '100%', maxWidth: 560, maxHeight: '85vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 24px 60px rgba(0,0,0,0.35)', animation: 'slideUp 0.2s ease-out',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '14px 18px', background: 'linear-gradient(135deg, #0B1D3A 0%, #112347 100%)',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.55)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Hotspot Intelligence
            </div>
            <div style={{ fontSize: '1.05rem', fontWeight: 700, color: '#C5A028', marginTop: 2 }}>
              {hotspot.police_station ? `${hotspot.police_station}, ` : ''}{hotspot.district}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.75)', marginTop: 2 }}>
              {hotspot.crime_type} · {hotspot.case_count} case{hotspot.case_count === 1 ? '' : 's'} on record
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 6,
            width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', cursor: 'pointer', flexShrink: 0,
          }}>
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, minHeight: 0, padding: '16px 18px' }}>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: '0.8rem', padding: '2rem 0', justifyContent: 'center' }}>
              <Loader2 size={16} className="spin-icon" style={{ animation: 'spin 0.8s linear infinite' }} />
              Analyzing on-file records for this area…
            </div>
          ) : !rec || rec.total_incidents === 0 ? (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', padding: '1.5rem 0', textAlign: 'center' }}>
              No detailed FIR records on file for this exact district/crime-type combination yet.
            </div>
          ) : (
            <>
              {/* Risk + peak time row */}
              <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                <div style={{ flex: 1, background: 'var(--surface-subtle)', border: `1px solid ${riskColor}40`, borderRadius: 8, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.62rem', color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    <ShieldAlert size={11} /> Risk Level
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: riskColor, marginTop: 2 }}>{rec.risk_level}</div>
                </div>
                <div style={{ flex: 1, background: 'var(--surface-subtle)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.62rem', color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    <Clock size={11} /> Peak Period
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-2)', marginTop: 2, textTransform: 'capitalize' }}>
                    {rec.peak_period || 'Not enough timestamped records'}
                  </div>
                </div>
              </div>

              {/* Recent incidents */}
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-3)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                <FileText size={12} /> Recent Incidents
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
                {rec.recent_incidents.map(inc => (
                  <div key={inc.fir_number} style={{ background: 'var(--surface-subtle)', border: '1px solid var(--border)', borderRadius: 6, padding: '7px 10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem' }}>
                      <span style={{ fontFamily: 'monospace', color: '#1D4ED8', fontWeight: 600 }}>{inc.fir_number}</span>
                      <span style={{ color: 'var(--text-faint)' }}>{inc.date}</span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', marginTop: 3 }}>{inc.brief}</div>
                  </div>
                ))}
              </div>

              {/* Recommendation */}
              <div style={{
                background: 'linear-gradient(135deg, rgba(197,160,40,0.08), rgba(11,29,58,0.04))',
                border: '1px solid rgba(197,160,40,0.3)', borderRadius: 8, padding: '12px 14px', marginBottom: 12,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.68rem', fontWeight: 700, color: '#8A6E1A', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                  <AlertTriangle size={12} /> AI Recommendation — requires officer review
                </div>
                <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-2)' }}>{rec.recommended_action}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-4)', marginTop: 4, lineHeight: 1.5 }}>{rec.reason}</div>
              </div>

              {/* Human-in-the-loop workflow */}
              {!operation && (
                <button onClick={logRecommendation} disabled={busy} style={{
                  width: '100%', padding: '10px', background: '#0B1D3A', color: '#C5A028', border: 'none',
                  borderRadius: 6, fontSize: '0.78rem', fontWeight: 600, cursor: busy ? 'wait' : 'pointer',
                }}>
                  {busy ? 'Logging…' : 'Review & log this recommendation'}
                </button>
              )}

              {operation?.status === 'recommended' && (
                <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-3)', marginBottom: 8 }}>Assign team & vehicle</div>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <div style={{ flex: 1, position: 'relative' }}>
                      <Users size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
                      <input value={team} onChange={e => setTeam(e.target.value)} placeholder="e.g. Patrol Team B"
                        style={{ width: '100%', padding: '6px 8px 6px 26px', fontSize: '0.75rem', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface)', color: 'var(--text-1)' }} />
                    </div>
                    <div style={{ flex: 1, position: 'relative' }}>
                      <Truck size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
                      <input value={vehicle} onChange={e => setVehicle(e.target.value)} placeholder="e.g. KA-01-P-1234"
                        style={{ width: '100%', padding: '6px 8px 6px 26px', fontSize: '0.75rem', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface)', color: 'var(--text-1)' }} />
                    </div>
                  </div>
                  <button onClick={() => advance('assigned', { assigned_team: team || undefined, assigned_vehicle: vehicle || undefined })}
                    disabled={busy} style={{ width: '100%', padding: '8px', background: '#C5A028', color: '#0B1D3A', border: 'none', borderRadius: 6, fontSize: '0.75rem', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
                    {busy ? 'Assigning…' : 'Confirm assignment'}
                  </button>
                </div>
              )}

              {operation?.status === 'assigned' && (
                <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginBottom: 8 }}>
                    Assigned to <strong>{team || 'the assigned team'}</strong>{vehicle ? ` · ${vehicle}` : ''}. Ready to begin.
                  </div>
                  <button onClick={() => advance('started')} disabled={busy} style={{
                    width: '100%', padding: '8px', background: '#0F7A5A', color: '#fff', border: 'none',
                    borderRadius: 6, fontSize: '0.75rem', fontWeight: 700, cursor: busy ? 'wait' : 'pointer',
                  }}>
                    {busy ? 'Starting…' : 'Start action'}
                  </button>
                </div>
              )}

              {operation?.status === 'started' && (
                <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-3)', marginBottom: 6 }}>Outcome notes (optional)</div>
                  <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                    placeholder="e.g. No incidents during patrol window."
                    style={{ width: '100%', padding: 8, fontSize: '0.75rem', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface)', color: 'var(--text-1)', fontFamily: 'inherit', resize: 'vertical', marginBottom: 8 }} />
                  <button onClick={() => advance('completed', { notes: notes || undefined })} disabled={busy} style={{
                    width: '100%', padding: '8px', background: '#1D4ED8', color: '#fff', border: 'none',
                    borderRadius: 6, fontSize: '0.75rem', fontWeight: 700, cursor: busy ? 'wait' : 'pointer',
                  }}>
                    {busy ? 'Completing…' : 'Complete action'}
                  </button>
                </div>
              )}

              {operation?.status === 'completed' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(15,122,90,0.1)', border: '1px solid rgba(15,122,90,0.3)', borderRadius: 8, padding: 12, color: '#0F7A5A', fontSize: '0.78rem', fontWeight: 600 }}>
                  <CheckCircle2 size={16} /> Logged in the Hotspot Operations record — operation #{operation.operation_id}.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
