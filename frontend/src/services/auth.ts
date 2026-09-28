import type { AuthUser } from '../types/auth'

export class AuthApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'AuthApiError'
  }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8010/api').replace(/\/$/, '')

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
    return typeof candidate.id === 'string'
    && typeof candidate.user_code === 'string'
    && typeof candidate.username === 'string'
    && (typeof candidate.email === 'string' || candidate.email === null)
    && (typeof candidate.phone === 'string' || candidate.phone === null)
    && typeof candidate.display_name === 'string'
    && (candidate.status === 'ACTIVE' || candidate.status === 'DISABLED')
    && Array.isArray(candidate.roles)
    && candidate.roles.every(role => typeof role === 'string')
}

async function request(path: string, method: 'GET' | 'POST', body?: unknown): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      credentials: 'include',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new AuthApiError(0, 'Could not connect to the authentication service.')
  }

  if (response.status === 204) return undefined
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data && typeof data === 'object' && 'message' in data
      && typeof data.message === 'string'
      ? data.message
      : 'Authentication request failed.'
    throw new AuthApiError(response.status, message)
  }
  return data
}

function parseUser(data: unknown): AuthUser {
  if (!data || typeof data !== 'object' || !('user' in data) || !isAuthUser(data.user)) {
    throw new AuthApiError(502, 'Authentication service returned an invalid response.')
  }
  return data.user
}

export const authService = {
  async login(identifier: string, password: string, rememberMe = false): Promise<AuthUser> {
    return parseUser(await request('/auth/login', 'POST', {
      identifier, password, remember_me: rememberMe,
    }))
  },

  async register(username: string, contact: string, password: string): Promise<AuthUser> {
    return parseUser(await request('/auth/register', 'POST', { username, contact, password }))
  },

  async me(): Promise<AuthUser> {
    return parseUser(await request('/auth/me', 'GET'))
  },

  async logout(): Promise<void> {
    await request('/auth/logout', 'POST')
  },
}
