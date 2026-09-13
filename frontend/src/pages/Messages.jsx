import { useState, useEffect, useRef, useCallback } from 'react'
import Header from '../components/Header'
import HelpTarget from '../components/HelpTarget'
import { getStations, getStationThread, markStationThreadRead, sendStationMessage } from '../services/api'
import { Send, Building2, ArrowLeftRight, Inbox } from 'lucide-react'

export default function Messages({ user }) {
  const [stations, setStations] = useState([])
  const [myStation, setMyStation] = useState('')
  const [otherStation, setOtherStation] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    getStations().then(d => { setStations(d.stations); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const loadThread = useCallback(async () => {
    if (!myStation || !otherStation) return
    const data = await getStationThread(myStation, otherStation)
    setMessages(data.messages)
    markStationThreadRead(myStation, otherStation).catch(() => {})
  }, [myStation, otherStation])

  useEffect(() => {
    loadThread()
    // Lightweight polling — no websocket infra in this project, and a
    // 4s poll is plenty responsive for an inter-station desk tool
    // without the operational overhead of a persistent connection.
    const id = setInterval(loadThread, 4000)
    return () => clearInterval(id)
  }, [loadThread])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || !myStation || !otherStation || sending) return
    setSending(true)
    setInput('')
    try {
      await sendStationMessage(myStation, otherStation, text)
      await loadThread()
    } finally {
      setSending(false)
    }
  }

  const stationLabel = (id) => {
    const s = stations.find(s => String(s.unit_id) === String(id))
    return s ? `${s.unit_name} (${s.district})` : ''
  }

  const ready = myStation && otherStation && myStation !== otherStation

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header title="Station Messages" subtitle="Inter-station communication" user={user} />
      <div className="page-content" style={{ display: 'flex', flexDirection: 'column' }}>

        {/* Station selection */}
        <HelpTarget id="messages-station-select" label="Station selection" category="messages-toolbar"
          description="Choose your station and the station you want to message. Both must be selected before a conversation opens."
          keywords={['station', 'select', 'from', 'to']}>
          <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>My Station</div>
              <select value={myStation} onChange={e => setMyStation(e.target.value)} style={{
                width: '100%', padding: '7px 10px', fontSize: '0.8rem', border: '1px solid var(--border)',
                borderRadius: 6, background: 'var(--surface)', color: 'var(--text-1)', cursor: 'pointer',
              }}>
                <option value="">Select your station…</option>
                {stations.map(s => <option key={s.unit_id} value={s.unit_id}>{s.unit_name} ({s.district})</option>)}
              </select>
            </div>
            <ArrowLeftRight size={16} color="var(--text-faint)" style={{ marginTop: 18, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Conversing With</div>
              <select value={otherStation} onChange={e => setOtherStation(e.target.value)} style={{
                width: '100%', padding: '7px 10px', fontSize: '0.8rem', border: '1px solid var(--border)',
                borderRadius: 6, background: 'var(--surface)', color: 'var(--text-1)', cursor: 'pointer',
              }}>
                <option value="">Select destination station…</option>
                {stations.filter(s => String(s.unit_id) !== String(myStation)).map(s => (
                  <option key={s.unit_id} value={s.unit_id}>{s.unit_name} ({s.district})</option>
                ))}
              </select>
            </div>
          </div>
        </HelpTarget>

        {/* Chat interface */}
        <div className="card" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
          {!ready ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', gap: 8 }}>
              <Building2 size={28} />
              <div style={{ fontSize: '0.82rem' }}>
                {loading ? 'Loading stations…' : 'Select both stations above to open the conversation.'}
              </div>
            </div>
          ) : (
            <>
              <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', background: 'var(--surface-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-2)' }}>
                  {stationLabel(myStation)} <ArrowLeftRight size={11} style={{ margin: '0 6px', verticalAlign: -1 }} color="var(--text-faint)" /> {stationLabel(otherStation)}
                </div>
              </div>
              <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {messages.length === 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-faint)', gap: 6 }}>
                    <Inbox size={22} />
                    <div style={{ fontSize: '0.78rem' }}>No messages yet — send the first one below.</div>
                  </div>
                )}
                {messages.map(m => {
                  const isMine = String(m.from_unit_id) === String(myStation)
                  return (
                    <div key={m.message_id} style={{ display: 'flex', justifyContent: isMine ? 'flex-end' : 'flex-start' }}>
                      <div style={{ maxWidth: '70%' }}>
                        <div style={{
                          background: isMine ? 'var(--navy-900)' : 'var(--surface-subtle)',
                          color: isMine ? '#fff' : 'var(--text-1)',
                          border: isMine ? 'none' : '1px solid var(--border)',
                          borderRadius: isMine ? '10px 10px 2px 10px' : '10px 10px 10px 2px',
                          padding: '8px 12px', fontSize: '0.8rem', lineHeight: 1.4,
                        }}>
                          {m.text}
                        </div>
                        <div style={{ fontSize: '0.62rem', color: 'var(--text-faint)', marginTop: 3, textAlign: isMine ? 'right' : 'left' }}>
                          {m.sender_username ? `${m.sender_username} · ` : ''}
                          {new Date(m.sent_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
              <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--border)' }}>
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') send() }}
                  placeholder={`Message ${stationLabel(otherStation)}…`}
                  style={{ flex: 1, padding: '8px 12px', fontSize: '0.8rem', border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface)', color: 'var(--text-1)' }}
                />
                <button onClick={send} disabled={!input.trim() || sending} style={{
                  width: 38, height: 38, borderRadius: 6, border: 'none',
                  background: input.trim() && !sending ? '#0B1D3A' : 'var(--border)',
                  color: input.trim() && !sending ? '#C5A028' : 'var(--text-faint)',
                  cursor: input.trim() && !sending ? 'pointer' : 'not-allowed',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <Send size={14} />
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
