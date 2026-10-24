import { useEffect, useState } from 'react'
import { FileText, Database } from 'lucide-react'

interface Doc {
  doc_id: string
  filename: string
  doc_type: string
  chunk_count: number
}

export default function Sidebar() {
  const [docs, setDocs] = useState<Doc[]>([])

  useEffect(() => {
    fetch('/api/documents')
      .then(res => res.json())
      .then(data => setDocs(data.documents))
      .catch(console.error)
  }, [])

  return (
    <aside style={{
      width: '280px',
      borderRight: '1px solid #333',
      backgroundColor: '#1a1a1a',
      display: 'flex',
      flexDirection: 'column'
    }}>
      <div style={{ padding: '16px', borderBottom: '1px solid #333', fontWeight: '600' }}>
        Indexed Documents
      </div>

      <div style={{ overflowY: 'auto', flex: 1, padding: '8px' }}>
        {docs.map(doc => (
          <div key={doc.doc_id} style={{
            padding: '12px',
            borderRadius: '6px',
            marginBottom: '4px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px',
            backgroundColor: 'transparent',
            transition: 'background-color 0.2s'
          }} onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#2a2a2a'}
             onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
            {doc.doc_type === 'csv' || doc.doc_type === 'xlsx'
              ? <Database size={18} color="#60a5fa" style={{ marginTop: '2px' }} />
              : <FileText size={18} color="#f87171" style={{ marginTop: '2px' }} />
            }
            <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <span style={{ fontSize: '14px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {doc.filename}
              </span>
              <span style={{ fontSize: '12px', color: '#888' }}>
                {doc.chunk_count} chunks
              </span>
            </div>
          </div>
        ))}
        {docs.length === 0 && (
          <div style={{ padding: '16px', textAlign: 'center', color: '#888', fontSize: '14px' }}>
            No documents indexed.
          </div>
        )}
      </div>
    </aside>
  )
}