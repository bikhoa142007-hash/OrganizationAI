import { describe, expect, it } from 'vitest'
import { resolveApiBaseUrl } from './apiBaseUrl'

describe('API base URL configuration', () => {
  it('accepts a service origin or an origin with /api', () => {
    expect(resolveApiBaseUrl('https://auth-stage.onrender.com', false)).toBe('https://auth-stage.onrender.com/api')
    expect(resolveApiBaseUrl('https://auth-stage.onrender.com/api', false)).toBe('https://auth-stage.onrender.com/api')
  })

  it('uses the local default only in development and rejects insecure production URLs', () => {
    expect(resolveApiBaseUrl('', true)).toBe('http://localhost:8010/api')
    expect(() => resolveApiBaseUrl('', false)).toThrow('must be configured')
    expect(() => resolveApiBaseUrl('http://auth-stage.onrender.com', false)).toThrow('HTTPS')
  })

  it('rejects paths or URL credentials that could redirect authenticated requests', () => {
    expect(() => resolveApiBaseUrl('https://auth-stage.onrender.com/other', false)).toThrow()
    expect(() => resolveApiBaseUrl('https://user:secret@auth-stage.onrender.com', false)).toThrow()
  })
})
