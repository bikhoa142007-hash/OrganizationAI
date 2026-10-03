import { createContext, useContext, useEffect, useState, type PropsWithChildren } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AuthApiError, authService } from '../services/auth'
import type { AuthUser } from '../types/auth'

interface AuthContextValue {
  user: AuthUser | null
  roles: string[]
  isAuthenticated: boolean
  isLoading: boolean
  sessionError: string
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
  const [isLoading, setIsLoading] = useState(requiresSession)
  const [sessionError, setSessionError] = useState('')

  useEffect(() => {
    if (!requiresSession) {
      setIsLoading(false)
      setSessionError('')
      return
    }

    let active = true
    setIsLoading(true)
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
      .finally(() => { if (active) setIsLoading(false) })
    return () => { active = false }
  }, [requiresSession, location.pathname])

  useEffect(() => {
    function handleExpired() {
      setUser(null)
      navigate('/login', {
        replace: true,
        state: {
          from: { pathname: location.pathname, search: location.search, hash: location.hash },
          notice: 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.',
        },
      })
    }
    function handleAccessDenied() {
      navigate('/access-denied', { replace: true })
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
    return authenticatedUser
  }

  async function register(username: string, contact: string, password: string) {
    return authService.register(username, contact, password)
  }

  async function refresh(): Promise<AuthUser | null> {
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
    }
  }

  async function logout() {
    await authService.logout()
    setUser(null)
    setSessionError('')
  }

  const value: AuthContextValue = {
    user,
    roles: user?.roles ?? [],
    isAuthenticated: user !== null,
    isLoading,
    sessionError,
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
