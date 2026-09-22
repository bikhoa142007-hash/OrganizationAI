import {
  Activity, BookOpenCheck, BriefcaseBusiness, ChevronDown, ClipboardCheck,
  FilePlus2, FlaskConical, LayoutDashboard, Menu, PanelLeftClose, ShieldCheck, X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '../services/SessionProvider'
import { StatePanel } from './ui'

const navigation = [
  { label: 'Tổng quan', to: '/', icon: LayoutDashboard },
  { label: 'Kế hoạch', to: '/plans', icon: BriefcaseBusiness },
  { label: 'Tạo kế hoạch', to: '/plans/new', icon: FilePlus2, roles: ['MAKER'] },
  { label: 'Chờ tôi duyệt', to: '/review', icon: ClipboardCheck, roles: ['CHECKER'] },
  { label: 'Lịch sử audit', to: '/audit', icon: Activity },
  { label: 'Chính sách', to: '/policy', icon: BookOpenCheck },
  { label: 'Verify', to: '/verify', icon: FlaskConical, section: 'Công cụ demo' },
]

export function AppShell() {
  const { config, loading, error, refresh, switchActor } = useSession()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setOpen(false), [location.pathname])

  const allowedNavigation = useMemo(
    () => navigation.filter(item => !item.roles || item.roles.some(role => config?.roles.includes(role))),
    [config?.roles],
  )
  const current = allowedNavigation.find(item => item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to))

  return <div className="app-shell">
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`} aria-label="Điều hướng ứng dụng">
      <div className="brand-block">
        <span className="brand-mark"><ShieldCheck aria-hidden="true" /></span>
        <div><strong>OrganizationAI</strong><span>Marketing Approval</span></div>
        <button className="icon-button sidebar-close" type="button" onClick={() => setOpen(false)} aria-label="Đóng điều hướng"><PanelLeftClose /></button>
      </div>

      <nav className="sidebar-nav">
        {allowedNavigation.map((item, index) => {
          const previousSection = allowedNavigation[index - 1]?.section
          const showSection = item.section && item.section !== previousSection
          const Icon = item.icon
          return <div key={item.to}>
            {showSection && <p className="nav-section-label">{item.section}</p>}
            <NavLink to={item.to} end={item.to === '/'}><Icon aria-hidden="true" /><span>{item.label}</span></NavLink>
          </div>
        })}
      </nav>

      <div className="sidebar-session">
        <div className="session-label"><span className="status-dot" /> Phiên demo đã xác thực</div>
        {loading ? <p className="session-loading">Đang tải phiên...</p> : error ? <button className="text-button" type="button" onClick={() => void refresh()}>Tải lại phiên</button> : config && <>
          <label htmlFor="demo-actor">Tài khoản hiện tại</label>
          <div className="actor-select-wrap">
            <select id="demo-actor" aria-label="Demo actor" value={config.actor} onChange={event => switchActor(event.target.value)}>
              {config.actors.map(actor => <option key={actor.id} value={actor.id}>{actor.id}</option>)}
            </select>
            <ChevronDown aria-hidden="true" />
          </div>
          <p>{config.roles.join(' + ') || 'Không có role'}</p>
          <dl><div><dt>Môi trường</dt><dd>{config.environment}</dd></div><div><dt>Provider</dt><dd>{config.provider}</dd></div></dl>
        </>}
      </div>
    </aside>

    {open && <button className="sidebar-scrim" aria-label="Đóng điều hướng" type="button" onClick={() => setOpen(false)} />}

    <div className="workspace">
      <header className="workspace-header">
        <button className="icon-button mobile-menu" type="button" onClick={() => setOpen(value => !value)} aria-label={open ? 'Đóng menu' : 'Mở menu'}>{open ? <X /> : <Menu />}</button>
        <div><span>OrganizationAI</span><strong>{current?.label ?? 'Kế hoạch marketing'}</strong></div>
        <div className="header-context"><span>{config?.roles.join(' / ') || 'Đang tải role'}</span><small>{config?.actor || 'Phiên demo'}</small></div>
      </header>
      <main className="workspace-content">
        {loading ? <StatePanel kind="loading" title="Đang xác minh phiên demo" /> : error ? <StatePanel kind="error" title="Không thể xác thực phiên" description={error} action={<button className="button button-secondary" type="button" onClick={() => void refresh()}>Thử lại</button>} /> : <Outlet />}
      </main>
    </div>
  </div>
}
