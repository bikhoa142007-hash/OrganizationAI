import { useEffect, useState } from 'react'
import { api, demoActor } from '../services/api/client'

export function DemoActor() {
  const [actors, setActors] = useState<Array<{ id: string; roles: string[] }>>([]), [error, setError] = useState('')
  useEffect(() => { api.request<{ actors: Array<{ id: string; roles: string[] }> }>('/config').then(c => setActors(c.actors)).catch(e => setError(String(e))) }, [])
  return <div className="mode-badge"><label htmlFor="demo-actor">Demo actor · MOCK VLM </label>
    <select id="demo-actor" value={demoActor()} disabled={!actors.length} onChange={e => { sessionStorage.setItem('organization-demo-actor', e.target.value); window.location.assign('/plans') }}>
      {actors.map(a => <option key={a.id} value={a.id}>{a.id} ({a.roles.join(', ')})</option>)}
    </select>{error && <p role="alert">{error}</p>}
  </div>
}
