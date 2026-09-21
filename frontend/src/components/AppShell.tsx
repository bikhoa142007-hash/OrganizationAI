import { DemoActor } from './DemoActor'
import { NavLink, Outlet } from 'react-router-dom'

const navigation = [
  { label: 'Landing', to: '/' },
  { label: 'Danh sách', to: '/plans' },
  { label: 'Hồ sơ mới', to: '/plans/new' },
  { label: 'Review Queue', to: '/review' },
  { label: 'Audit', to: '/audit' },
  { label: 'Verify', to: '/verify' },
  { label: 'Policy', to: '/policy' },
]

export function AppShell() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OrganizationAI</p>
          <h1>Marketing Plan Approval</h1>
        </div>
        <DemoActor />
      </header>
      <nav className="navigation" aria-label="Điều hướng chính">
        {navigation.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
