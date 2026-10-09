import type { AuthUser } from '../types/auth'
import { resolveApiBaseUrl } from './apiBaseUrl'

export class AuthApiError extends Error {
  public correlation_id: string | null

  constructor(
    public status: number,
    message: string,
    public code: string | null = null,
    public correlationId: string | null = null,
  ) {
    super(message)
    this.name = 'AuthApiError'
    this.correlation_id = correlationId
  }
}

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

function stringProperty(value: unknown, key: string): string | null {
  if (!value || typeof value !== 'object' || !(key in value)) return null
  const property = (value as Record<string, unknown>)[key]
  return typeof property === 'string' && property.length > 0 ? property : null
}

async function request(
  path: string,
  method: 'GET' | 'POST',
  body?: unknown,
  expectedStatus?: number,
): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${resolveApiBaseUrl()}${path}`, {
      method,
      credentials: 'include',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new AuthApiError(0, 'Could not connect to the authentication service.', 'NETWORK_ERROR')
  }

  const headerCorrelationId = response.headers.get('X-Correlation-ID')
  if (response.status === 204) {
    if (expectedStatus === undefined || expectedStatus === 204) return undefined
    throw new AuthApiError(response.status, 'Authentication service returned an unexpected response.', 'UNEXPECTED_STATUS', headerCorrelationId)
  }

  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthApiError(
      response.status,
      stringProperty(data, 'message') ?? 'Authentication request failed.',
      stringProperty(data, 'code') ?? 'HTTP_ERROR',
      stringProperty(data, 'correlation_id') ?? headerCorrelationId,
    )
  }

  if (expectedStatus !== undefined && response.status !== expectedStatus) {
    throw new AuthApiError(
      response.status,
      'Authentication service returned an unexpected response.',
      'UNEXPECTED_STATUS',
      stringProperty(data, 'correlation_id') ?? headerCorrelationId,
    )
  }
  return data
}

function parseUser(data: unknown): AuthUser {
  if (!data || typeof data !== 'object' || !('user' in data) || !isAuthUser(data.user)) {
    throw new AuthApiError(502, 'Authentication service returned an invalid response.', 'INVALID_RESPONSE')
  }
  return data.user
}

export const authService = {
  async getRegistrationConfig(): Promise<{ registration_enabled: boolean }> {
    const data = await request('/auth/config', 'GET')
    if (!data || typeof data !== 'object' || !('registration_enabled' in data) ||
        typeof data.registration_enabled !== 'boolean') {
      throw new AuthApiError(502, 'Authentication service returned invalid registration settings.', 'INVALID_RESPONSE')
    }
    return { registration_enabled: data.registration_enabled }
  },

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
    await request('/auth/logout', 'POST', undefined, 204)
  },
}
