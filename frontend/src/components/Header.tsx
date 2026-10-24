import { Activity } from 'lucide-react'

interface HeaderProps {
  isHealthy: boolean
  models: {id: string, primary: boolean}[]
  selectedModel: string
  setSelectedModel: (m: string) => void
}

export default function Header({ isHealthy, models, selectedModel, setSelectedModel }: HeaderProps) {
  return (
    <header style={{
      padding: '16px 24px',
      borderBottom: '1px solid #333',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      backgroundColor: '#1a1a1a'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '24px', fontWeight: 'bold' }}>DeliGenius</span>
        <span style={{ fontSize: '12px', color: '#888', marginTop: '6px' }}>RAG Agent</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px' }}>
          <Activity size={16} color={isHealthy ? '#4ade80' : '#ef4444'} />
          <span style={{ color: isHealthy ? '#4ade80' : '#ef4444' }}>
            {isHealthy ? 'Connected' : 'Offline'}
          </span>
        </div>

        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          style={{
            padding: '6px 12px',
            borderRadius: '4px',
            backgroundColor: '#333',
            color: 'white',
            border: '1px solid #444',
            outline: 'none'
          }}
        >
          {models.map(m => (
            <option key={m.id} value={m.id}>{m.id}</option>
          ))}
        </select>
      </div>
    </header>
  )
}