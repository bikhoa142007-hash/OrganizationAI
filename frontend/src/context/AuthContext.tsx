import { createContext, useContext, useEffect, useLayoutEffect, useState, type PropsWithChildren } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AuthApiError, authService } from '../services/auth'
import type { AuthUser } from '../types/auth'

interface AuthContextValue {
  user: AuthUser | null
  roles: string[]
  isAuthenticated: boolean
  isLoading: boolean
  sessionError: string
  sessionNotice: string
  login: (identifier: string, password: string, rememberMe: boolean) => Promise<AuthUser>
  logout: () => Promise<void>
  register: (username: string, contact: string, password: string) => ReturnType<typeof authService.register>
  refresh: () => Promise<AuthUser | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: PropsWithChildren) {
  const location = useLocation()
  const navigate = useNavigate()
  const requiresSession = ['/', '/login', '/register', '/account', '/access-denied'].includes(location.pathname)
    || location.pathname === '/workflow'
    || location.pathname.startsWith('/workflow/')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [sessionInitialized, setSessionInitialized] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [sessionError, setSessionError] = useState('')
  const [sessionNotice, setSessionNotice] = useState('')
  const isLoading = (requiresSession && !sessionInitialized) || isRefreshing

  useEffect(() => {
    if (!requiresSession || sessionInitialized) return

    let active = true
    setSessionError('')
    authService.me()
      .then(currentUser => { if (active) { setUser(currentUser); setSessionError('') } })
      .catch(reason => {
        if (!active) return
        setUser(null)
        if (!(reason instanceof AuthApiError && reason.status === 401)) {
          setSessionError('Không thể kiểm tra phiên đăng nhập. Hãy thử lại khi dịch vụ khả dụng.')
        }
      })
      .finally(() => { if (active) setSessionInitialized(true) })
    return () => { active = false }
  }, [requiresSession, sessionInitialized])

  useLayoutEffect(() => {
    function handleExpired() {
      setUser(null)
      setSessionError('')
      setSessionNotice('Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.')
      navigate('/login', {
        replace: true,
        state: {
          from: { pathname: location.pathname, search: location.search, hash: location.hash },
        },
      })
    }
    function handleAccessDenied() {
      navigate('/access-denied', {
        replace: true,
        state: { from: { pathname: location.pathname, search: location.search, hash: location.hash } },
      })
    }
    window.addEventListener('organizationai:auth-expired', handleExpired)
    window.addEventListener('organizationai:access-denied', handleAccessDenied)
    return () => {
      window.removeEventListener('organizationai:auth-expired', handleExpired)
      window.removeEventListener('organizationai:access-denied', handleAccessDenied)
    }
  }, [location.pathname, location.search, location.hash, navigate])

  async function login(identifier: string, password: string, rememberMe: boolean): Promise<AuthUser> {
    const authenticatedUser = await authService.login(identifier, password, rememberMe)
    setUser(authenticatedUser)
    setSessionError('')
    setSessionNotice('')
    return authenticatedUser
  }

  async function register(username: string, contact: string, password: string) {
    const createdUser = await authService.register(username, contact, password)
    setSessionError('')
    return createdUser
  }

  async function refresh(): Promise<AuthUser | null> {
    setIsRefreshing(true)
    try {
      const currentUser = await authService.me()
      setUser(currentUser)
      setSessionError('')
      return currentUser
    } catch (reason) {
      setUser(null)
      setSessionError(reason instanceof AuthApiError && reason.status === 401
        ? ''
        : 'Không thể kiểm tra phiên đăng nhập. Hãy thử lại khi dịch vụ khả dụng.')
      return null
    } finally {
      setIsRefreshing(false)
    }
  }

  async function logout() {
    await authService.logout()
    setUser(null)
    setSessionError('')
    setSessionNotice('')
  }

  const value: AuthContextValue = {
    user,
    roles: user?.roles ?? [],
    isAuthenticated: user !== null,
    isLoading,
    sessionError,
    sessionNotice,
    login,
    logout,
    register,
    refresh,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthProvider is required before using authentication state.')
  return context
}
