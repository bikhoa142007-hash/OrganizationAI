import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { StatePanel } from '../ui'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, sessionError, refresh } = useAuth()
  const location = useLocation()

  if (isLoading) return <p role="status">Đang khôi phục phiên đăng nhập…</p>
  if (sessionError) return <StatePanel kind="error" title="Không thể kiểm tra phiên đăng nhập" description={sessionError} action={<button type="button" onClick={() => void refresh()}>Thử lại</button>} />
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: { pathname: location.pathname, search: location.search, hash: location.hash } }} replace />
  }
  return children
}
