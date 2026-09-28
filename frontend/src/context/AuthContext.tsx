import { createContext, useContext, useEffect, useState, type PropsWithChildren } from 'react'
import { useLocation } from 'react-router-dom'
import { authService } from '../services/auth'
import type { AuthUser } from '../types/auth'

interface AuthContextValue {
  user: AuthUser | null
  roles: string[]
  isAuthenticated: boolean
  isLoading: boolean
  login: (identifier: string, password: string, rememberMe: boolean) => Promise<void>
  logout: () => Promise<void>
  register: (username: string, contact: string, password: string) => ReturnType<typeof authService.register>
  refresh: () => Promise<AuthUser | null>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: PropsWithChildren) {
  const location = useLocation()
  const requiresSession = ['/login', '/register', '/account'].includes(location.pathname)
    || location.pathname === '/workflow'
    || location.pathname.startsWith('/workflow/')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(requiresSession)

  useEffect(() => {
    if (!requiresSession) {
      setIsLoading(false)
      return
    }

    let active = true
    setIsLoading(true)
    authService.me()
      .then(currentUser => { if (active) setUser(currentUser) })
      .catch(() => { if (active) setUser(null) })
      .finally(() => { if (active) setIsLoading(false) })
    return () => { active = false }
  }, [requiresSession])

  async function login(identifier: string, password: string, rememberMe: boolean) {
    const authenticatedUser = await authService.login(identifier, password, rememberMe)
    setUser(authenticatedUser)
  }

  async function register(username: string, contact: string, password: string) {
    return authService.register(username, contact, password)
  }

  async function refresh(): Promise<AuthUser | null> {
    try {
      const currentUser = await authService.me()
      setUser(currentUser)
      return currentUser
    } catch {
      setUser(null)
      return null
    }
  }

  async function logout() {
    try {
      await authService.logout()
    } catch {
      // Clear client state even when the server cannot be reached.
    } finally {
      setUser(null)
    }
  }

  const value: AuthContextValue = {
    user,
    roles: user?.roles ?? [],
    isAuthenticated: user !== null,
    isLoading,
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
