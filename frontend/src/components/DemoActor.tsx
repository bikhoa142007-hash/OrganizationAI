import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, demoActor } from '../services/api/client'

export interface ActorConfig {
  actor: string
  roles: string[]
  actors: Array<{ id: string; roles: string[] }>
}
const ActorContext = createContext<ActorConfig | null>(null)
export const useActor = () => useContext(ActorContext)

export function DemoSession({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<ActorConfig | null>(null), [error, setError] = useState('')
  useEffect(() => { let active = true; api.request<ActorConfig>('/config').then(c => { if (active) setConfig(c) }).catch(e => { if (active) setError(String(e)) }); return () => { active = false } }, [])
  if (error) return <section role="alert"><p>{error}</p><button onClick={() => { sessionStorage.removeItem('organization-demo-actor'); window.location.assign('/') }}>Chọn lại Maker demo</button></section>
  if (!config) return <p role="status">Đang xác minh actor demo…</p>
  return <ActorContext.Provider value={config}>{children}</ActorContext.Provider>
}

export function RequireRole({ role, children }: { role: string; children: ReactNode }) {
  const actor = useActor()
  return actor?.roles.includes(role) ? children : <p role="alert">Không có quyền {role} cho chức năng này. Chọn actor phù hợp trên thanh đầu trang.</p>
}

export function DemoActor() {
  const config = useActor()
  return <div className="mode-badge"><label htmlFor="demo-actor">Demo actor · MOCK VLM </label>
    <select id="demo-actor" value={demoActor()} onChange={e => { sessionStorage.setItem('organization-demo-actor', e.target.value); window.location.assign('/plans') }}>
      {config?.actors.map(a => <option key={a.id} value={a.id}>{a.id} ({a.roles.join(', ')})</option>)}
    </select><p>Phiên demo dùng chung · không phải đăng nhập production.</p>
    <p>Maker: lập hồ sơ của mình. Checker: duyệt hồ sơ được giao. Admin: xem cấu hình demo; không tự có quyền duyệt.</p>
  </div>
}
