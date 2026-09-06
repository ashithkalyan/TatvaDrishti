import { useState, useEffect, useCallback } from 'react'
import Header from '../components/Header'
import HelpTarget from '../components/HelpTarget'
import { getHotspotOpsSummary, listHotspotOperations } from '../services/api'
import {
  ClipboardList, Clock, CheckCircle2, PlayCircle, Users, Truck,
  RefreshCw, Filter, MapPin,
} from 'lucide-react'

const PERIODS = [
  { id: 'day', label: 'Daily' },
  { id: 'week', label: 'Weekly' },
  { id: 'month', label: 'Monthly' },
  { id: 'year', label: 'Yearly' },
]

const STATUS_META = {
  recommended: { label: 'Recommended', color: '#94A3B8', icon: ClipboardList },
  assigned:    { label: 'Assigned',    color: '#E67E22', icon: Users },
  started:     { label: 'In Progress', color: '#2563EB', icon: PlayCircle },
  completed:   { label: 'Completed',   color: '#0F7A5A', icon: CheckCircle2 },
}

function SummaryCard({ label, value, color, Icon }) {
  return (
    <div className="kpi-card" style={{ borderTop: `3px solid ${color}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Icon size={16} color={color} />
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

export default function Logbook({ user }) {
  const [period, setPeriod] = useState('week')
  const [summary, setSummary] = useState(null)
  const [operations, setOperations] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [districtFilter, setDistrictFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, ops] = await Promise.all([
        getHotspotOpsSummary(period),
        listHotspotOperations({ status: statusFilter || undefined, district: districtFilter || undefined }),
      ])
      setSummary(s)
      setOperations(ops.operations || [])
    } finally {
      setLoading(false)
    }
  }, [period, statusFilter, districtFilter])

  useEffect(() => { load() }, [load])

  const districts = [...new Set(operations.map(o => o.district))].sort()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header title="Hotspot Operations Logbook" subtitle="Patrol recommendations, assignments & outcomes" user={user} />
      <div className="page-content">

        {/* Period tabs */}
        <HelpTarget id="logbook-period-tabs" label="Summary period" category="logbook-toolbar"
          description="Switches the summary cards below between daily, weekly, monthly, and yearly totals."
          keywords={['daily', 'weekly', 'monthly', 'yearly', 'period', 'summary']}>
          <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
            {PERIODS.map(p => (
              <button key={p.id} onClick={() => setPeriod(p.id)} style={{
                padding: '6px 16px', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer',
                borderRadius: 6, border: `1px solid ${period === p.id ? '#0B1D3A' : 'var(--border)'}`,
                background: period === p.id ? '#0B1D3A' : 'var(--surface)',
                color: period === p.id ? '#C5A028' : 'var(--text-4)',
              }}>
                {p.label}
              </button>
            ))}
            <button onClick={load} title="Refresh" style={{
              marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5,
              padding: '6px 12px', fontSize: '0.75rem', border: '1px solid var(--border)',
              background: 'var(--surface)', borderRadius: 6, cursor: 'pointer', color: 'var(--text-4)',
            }}>
              <RefreshCw size={12} style={loading ? { animation: 'spin 0.8s linear infinite' } : {}} /> Refresh
            </button>
          </div>
        </HelpTarget>

        {/* Summary cards */}
        {summary && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12, marginBottom: 20 }}>
            <SummaryCard label="Total Operations" value={summary.total_operations} color="#0B1D3A" Icon={ClipboardList} />
            <SummaryCard label="Awaiting Review" value={summary.recommended} color={STATUS_META.recommended.color} Icon={STATUS_META.recommended.icon} />
            <SummaryCard label="Assigned" value={summary.assigned} color={STATUS_META.assigned.color} Icon={STATUS_META.assigned.icon} />
            <SummaryCard label="In Progress" value={summary.started} color={STATUS_META.started.color} Icon={STATUS_META.started.icon} />
            <SummaryCard label="Completed" value={summary.completed} color={STATUS_META.completed.color} Icon={STATUS_META.completed.icon} />
            <SummaryCard label="Districts Covered" value={summary.districts_covered.length} color="#7E22CE" Icon={MapPin} />
          </div>
        )}

        {/* Top crime types / districts for the period */}
        {summary && (summary.top_crime_types?.length > 0 || summary.top_districts?.length > 0) && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
            <div className="card">
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>Most Active Crime Types</div>
              {summary.top_crime_types.length === 0 ? (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-faint)' }}>No operations logged for this period.</div>
              ) : summary.top_crime_types.map(c => (
                <div key={c.crime_type} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', padding: '4px 0', color: 'var(--text-3)' }}>
                  <span>{c.crime_type}</span><strong>{c.count}</strong>
                </div>
              ))}
            </div>
            <div className="card">
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>Most Patrol Activity</div>
              {summary.top_districts.length === 0 ? (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-faint)' }}>No operations logged for this period.</div>
              ) : summary.top_districts.map(d => (
                <div key={d.district} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', padding: '4px 0', color: 'var(--text-3)' }}>
                  <span>{d.district}</span><strong>{d.count}</strong>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <Filter size={13} color="var(--text-faint)" />
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{
            padding: '5px 10px', fontSize: '0.75rem', border: '1px solid var(--border)', borderRadius: 5,
            background: 'var(--surface)', color: 'var(--text-3)', cursor: 'pointer',
          }}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <select value={districtFilter} onChange={e => setDistrictFilter(e.target.value)} style={{
            padding: '5px 10px', fontSize: '0.75rem', border: '1px solid var(--border)', borderRadius: 5,
            background: 'var(--surface)', color: 'var(--text-3)', cursor: 'pointer',
          }}>
            <option value="">All districts</option>
            {districts.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        {/* Operations table — the actual logbook record */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>District</th><th>Crime Type</th><th>Recommended Action</th>
                <th>Status</th><th>Team / Vehicle</th><th>Officer</th><th>Logged</th>
              </tr>
            </thead>
            <tbody>
              {operations.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-faint)' }}>
                  {loading ? 'Loading…' : 'No hotspot operations logged yet — confirm a recommendation from the Analytics hotspot map to see it here.'}
                </td></tr>
              )}
              {operations.map(op => {
                const meta = STATUS_META[op.status] || STATUS_META.recommended
                return (
                  <tr key={op.operation_id}>
                    <td>{op.district}{op.police_station ? ` — ${op.police_station}` : ''}</td>
                    <td>{op.crime_type}</td>
                    <td style={{ maxWidth: 220 }}>{op.recommended_action || '—'}</td>
                    <td>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.68rem', fontWeight: 700,
                        padding: '2px 8px', borderRadius: 999, color: meta.color, background: `${meta.color}18`,
                      }}>
                        <meta.icon size={10} /> {meta.label}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.72rem' }}>
                      {op.assigned_team && <div><Users size={10} style={{ marginRight: 3, verticalAlign: -1 }} />{op.assigned_team}</div>}
                      {op.assigned_vehicle && <div><Truck size={10} style={{ marginRight: 3, verticalAlign: -1 }} />{op.assigned_vehicle}</div>}
                      {!op.assigned_team && !op.assigned_vehicle && '—'}
                    </td>
                    <td style={{ fontSize: '0.72rem' }}>{op.officer_username || '—'}</td>
                    <td style={{ fontSize: '0.7rem', color: 'var(--text-faint)' }}>
                      <Clock size={10} style={{ marginRight: 3, verticalAlign: -1 }} />
                      {op.created_at ? new Date(op.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
