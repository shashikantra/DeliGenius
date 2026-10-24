import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useState, useRef, useEffect } from 'react'
import { Send, User, Bot, ExternalLink, ThumbsUp, ThumbsDown, X } from 'lucide-react'

interface Citation {
  id: number
  kind: 'doc' | 'sql'
  chunk_id?: string
  filename?: string
  page?: number
  sql_kind?: string
  sql_summary?: string
  sql_query?: string
  sql_data?: string[][]
}

interface Message {
  role: 'user' | 'assistant'
  text: string
  citations?: Citation[]
  confidence?: number
  abstained?: boolean
  request_id?: string
}

// Bulletproof Markdown Table Parser
const renderEvidenceContent = (text: string) => {
  if (!text) return <div style={{ whiteSpace: 'pre-wrap' }}>{text}</div>;

  const lines = text.trim().split('\n').map(l => l.trim()).filter(l => l.length > 0);

  const headerIndex = lines.findIndex(l => l.includes('|') && !l.includes('---'));
  const separatorIndex = lines.findIndex(l => l.includes('---'));

  if (headerIndex === -1 || separatorIndex === -1) {
    return <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', lineHeight: '1.6' }}>{text}</div>;
  }

  const parseRow = (line: string) => {
    return line.replace(/^\||\|$/g, '').split('|').map(c => c.trim());
  };

  const headers = parseRow(lines[headerIndex]);
  const dataRows = lines.slice(separatorIndex + 1).map(parseRow);
  const prefixText = lines.slice(0, headerIndex).join('\n');

  return (
    <div>
      {prefixText && <div style={{ marginBottom: '12px', fontSize: '14px', color: '#aaa' }}>{prefixText}</div>}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
        <thead>
          <tr style={{ backgroundColor: '#444', color: '#fff' }}>
            {headers.map((h, i) => (
              <th key={i} style={{ border: '1px solid #555', padding: '8px', fontWeight: 'bold' }}>
                {h || ' '}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dataRows.map((row, i) => (
            <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#2a2a2a' : '#333' }}>
              {headers.map((_, j) => (
                <td key={j} style={{ border: '1px solid #555', padding: '8px', color: '#ddd' }}>
                  {row[j] || ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default function Chat({ model }: { model: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)
  const [citationText, setCitationText] = useState<string>('')
  const [loadingCitation, setLoadingCitation] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return

    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: userMsg }])
    setLoading(true)

    const body = { question: userMsg, acl: 'internal', k: 8, model: model }
    console.log("🟢 [FRONTEND] Sending request:", body)  // <--- ADD THIS

    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userMsg, acl: 'internal', k: 8, model: model })
      })

      console.log("🟢 [FRONTEND] Response status:", res.status)  // <--- ADD THIS

      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()

      if (data.abstained) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          text: `[Abstained] ${data.reason || 'Not enough evidence to answer.'}`,
          abstained: true
        }])
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          text: data.answer,
          citations: data.citations,
          confidence: data.confidence,
          request_id: data.request_id
        }])
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: "⚠️ Error: The API timed out or returned an invalid response."
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleCitationClick = async (citation: Citation) => {
    setActiveCitation(citation)
    setCitationText('')
    setLoadingCitation(true)

    const API_BASE = import.meta.env.VITE_API_URL || '/api';

    if (citation.kind === 'sql') {
      setLoadingCitation(false)
      return
    }

    if (!citation.chunk_id) {
      setCitationText("No chunk_id available.")
      setLoadingCitation(false)
      return
    }

    try {
      const res = await fetch(`${API_BASE}/chunks/${citation.chunk_id}`)
      if (!res.ok) throw new Error("Chunk not found")
      const data = await res.json()
      setCitationText(data.text)
    } catch (err) {
      setCitationText("Could not fetch chunk text. Ensure the backend has the /chunks/{id} endpoint.")
    } finally {
      setLoadingCitation(false)
    }
  }

  const sendFeedback = async (msg: Message, vote: 'up' | 'down') => {
    if (!msg.request_id) return
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: msg.request_id,
          question: "n/a",
          answer: msg.text,
          vote
        })
      })
      alert(`Feedback saved! Thank you.`)
    } catch {
      alert("Failed to save feedback.")
    }
  }

  return (
    <main style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#242424', position: 'relative' }}>

      {/* CITATION MODAL */}
      {activeCitation && (
        <div style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ backgroundColor: '#333', padding: '24px', borderRadius: '8px', maxWidth: '800px', width: '90%', position: 'relative', maxHeight: '80%', display: 'flex', flexDirection: 'column' }}>
            <button onClick={() => setActiveCitation(null)} style={{ position: 'absolute', top: '16px', right: '16px', background: 'transparent', border: 'none', color: 'white', cursor: 'pointer' }}><X size={20}/></button>
            <h3 style={{ marginTop: 0, marginBottom: '16px', color: 'white' }}>
              {activeCitation.kind === 'doc' ? `${activeCitation.filename} (p. ${activeCitation.page})` : `SQL: ${activeCitation.sql_kind}`}
            </h3>

            {loadingCitation ? (
              <div style={{ color: '#aaa', padding: '20px 0' }}>Loading evidence...</div>
            ) : activeCitation.kind === 'sql' ? (
              <div style={{ color: '#ccc', fontSize: '14px', lineHeight: '1.6', overflowY: 'auto', flex: 1 }}>

                {/* 1. Render the data table FIRST */}
                {activeCitation.sql_data && activeCitation.sql_data.length > 0 ? (
                  <div style={{ overflowX: 'auto', marginBottom: '24px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', textAlign: 'left' }}>
                      <tbody>
                        {activeCitation.sql_data.map((row, i) => (
                          <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#2a2a2a' : '#333' }}>
                            {row.map((cell, j) => (
                              <td key={j} style={{ border: '1px solid #555', padding: '10px', color: '#fff' }}>
                                {String(cell)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ color: '#888', marginBottom: '24px' }}>No data rows returned.</div>
                )}

                {/* 2. Render the SQL Query SECOND */}
                <details>
                  <summary style={{ cursor: 'pointer', color: '#aaa', marginBottom: '8px', fontSize: '12px' }}>
                    Show SQL Query
                  </summary>
                  <div style={{
                    padding: '12px',
                    backgroundColor: '#111',
                    borderRadius: '6px',
                    fontFamily: 'monospace',
                    color: '#4ade80',
                    whiteSpace: 'pre-wrap',
                    fontSize: '12px'
                  }}>
                    {activeCitation.sql_query || "No SQL query available"}
                  </div>
                </details>

                {/* 3. Render the Summary */}
                <div style={{ marginTop: '16px', fontSize: '13px', color: '#aaa' }}>
                  <strong>Summary:</strong> {activeCitation.sql_summary}
                </div>
              </div>
            ) : (
              <div style={{ color: '#ccc', fontSize: '14px', lineHeight: '1.6', overflowY: 'auto', flex: 1 }}>
                {renderEvidenceContent(citationText)}
              </div>
            )}
          </div>
        </div>
      )}

      {/* CHAT HISTORY */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        {messages.length === 0 && !loading && (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#888' }}>
            Ask a question about your deli's inventory, sales, or RIA reports.
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: msg.role === 'user' ? '#3b82f6' : '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>

            <div style={{ maxWidth: '75%', padding: '12px 16px', borderRadius: '12px', backgroundColor: msg.role === 'user' ? '#1e3a8a' : msg.abstained ? '#450a0a' : '#333', border: msg.abstained ? '1px solid #7f1d1d' : 'none' }}>
              <div style={{ fontSize: '15px', lineHeight: 1.6, color: 'white' }}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({node, ...props}) => <table style={{ borderCollapse: 'collapse', width: '100%', marginTop: '8px', marginBottom: '8px' }} {...props} />,
                    th: ({node, ...props}) => <th style={{ border: '1px solid #555', padding: '8px', textAlign: 'left', backgroundColor: '#444' }} {...props} />,
                    td: ({node, ...props}) => <td style={{ border: '1px solid #555', padding: '8px' }} {...props} />,
                    p: ({node, ...props}) => <p style={{ margin: '0 0 8px 0' }} {...props} />
                  }}
                >
                  {msg.text}
                </ReactMarkdown>
              </div>

              {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {msg.citations.map(c => (
                    <button
                      key={c.id}
                      onClick={() => handleCitationClick(c)}
                      style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', backgroundColor: '#111', padding: '4px 8px', borderRadius: '4px', color: '#a3a3a3', border: '1px solid #444', cursor: 'pointer' }}
                    >
                      <ExternalLink size={12} />
                      {c.kind === 'doc' ? `${c.filename} (p. ${c.page})` : `SQL: ${c.sql_kind}`}
                    </button>
                  ))}
                </div>
              )}

              {msg.role === 'assistant' && msg.request_id && !msg.abstained && (
                <div style={{ marginTop: '12px', display: 'flex', gap: '8px', borderTop: '1px solid #444', paddingTop: '8px' }}>
                  <button onClick={() => sendFeedback(msg, 'up')} style={{ background: 'transparent', border: 'none', color: '#888', cursor: 'pointer', padding: 0 }}><ThumbsUp size={14} /></button>
                  <button onClick={() => sendFeedback(msg, 'down')} style={{ background: 'transparent', border: 'none', color: '#888', cursor: 'pointer', padding: 0 }}><ThumbsDown size={14} /></button>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* LOADING INDICATOR */}
        {loading && (
          <div style={{ display: 'flex', gap: '16px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={18} />
            </div>
            <div style={{ padding: '12px 16px', borderRadius: '12px', backgroundColor: '#333', display: 'flex', alignItems: 'center', gap: '8px', color: 'white' }}>
              <span className="spinner" style={{ width: '16px', height: '16px', border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              Thinking...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* INPUT BOX */}
      <div style={{ padding: '24px', borderTop: '1px solid #333', backgroundColor: '#1a1a1a' }}>
        <form onSubmit={sendMessage} style={{ display: 'flex', gap: '12px' }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask anything about your data..."
            style={{ flex: 1, padding: '14px 16px', borderRadius: '8px', border: '1px solid #444', backgroundColor: '#242424', color: 'white', fontSize: '15px', outline: 'none' }}
          />
          <button type="submit" disabled={loading || !input.trim()} style={{ padding: '0 24px', borderRadius: '8px', border: 'none', backgroundColor: '#3b82f6', color: 'white', cursor: 'pointer', opacity: (loading || !input.trim()) ? 0.5 : 1 }}>
            <Send size={20} />
          </button>
        </form>
      </div>

      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
    </main>
  )
}