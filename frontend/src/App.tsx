import { useEffect, useState } from 'react'
import Chat from './components/Chat'
import Sidebar from './components/Sidebar'
import Header from './components/Header'

export default function App() {
  const [models, setModels] = useState<{id: string, primary: boolean}[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [isHealthy, setIsHealthy] = useState(false)

  useEffect(() => {
    // Fetch models
    fetch('/api/models')
      .then(res => res.json())
      .then(data => {
        setModels(data.models)
        const primary = data.models.find((m: any) => m.primary)
        if (primary) setSelectedModel(primary.id)
      })
      .catch(console.error)

    // Poll health
    const checkHealth = () => {
      fetch('/api/health')
        .then(res => res.json())
        .then(data => setIsHealthy(data.status === 'ok'))
        .catch(() => setIsHealthy(false))
    }
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header
        isHealthy={isHealthy}
        models={models}
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <Chat model={selectedModel} />
      </div>
    </div>
  )
}