import { afterEach, expect, it, vi } from 'vitest'
import { authService } from './auth'

const user = {
  id: 'user-1', user_code: 'USR-000001', username: 'maker', email: null,
  phone: '+84901234567', display_name: 'maker', status: 'ACTIVE', roles: ['MAKER'],
}

afterEach(() => vi.unstubAllGlobals())

it('logs in with an HttpOnly-cookie session request and never sends the demo actor header', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await authService.login('maker', 'local-secret', true)

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/auth/login')
  expect(options.credentials).toBe('include')
  expect(JSON.parse(String(options.body))).toEqual({
    identifier: 'maker', password: 'local-secret', remember_me: true,
  })
  expect(new Headers(options.headers).has('X-Demo-Actor')).toBe(false)
  expect(new Headers(options.headers).has('Authorization')).toBe(false)
})

it('registers through the authentication API without accepting a client role', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user }), {
    status: 201, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await authService.register('maker', '+84 (90) 123-4567', 'local-secret')

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/auth/register')
  expect(options.credentials).toBe('include')
  expect(JSON.parse(String(options.body))).toEqual({
    username: 'maker', contact: '+84 (90) 123-4567', password: 'local-secret',
  })
})

it('refreshes the session from the backend rather than a client-side flag', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  const currentUser = await authService.me()

  expect(currentUser).toEqual(user)
  expect(fetchMock.mock.calls[0][0]).toContain('/auth/me')
  expect((fetchMock.mock.calls[0][1] as RequestInit).credentials).toBe('include')
})

it('reads only the server registration feature switch', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ registration_enabled: false }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authService.getRegistrationConfig()).resolves.toEqual({ registration_enabled: false })
  expect(fetchMock.mock.calls[0][0]).toContain('/auth/config')
  expect((fetchMock.mock.calls[0][1] as RequestInit).credentials).toBe('include')
})
