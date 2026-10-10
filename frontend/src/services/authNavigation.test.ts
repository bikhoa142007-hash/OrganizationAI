import { describe, expect, it } from 'vitest'
import { homeForRoles, safeReturnPath } from './authNavigation'

describe('authenticated role destinations', () => {
  it('selects Maker as the primary destination for accounts with several roles', () => {
    expect(homeForRoles(['CHECKER', 'MAKER'])).toBe('/workflow/plans')
    expect(homeForRoles(['CHECKER'])).toBe('/workflow/reviews')
    expect(homeForRoles(['ADMIN'])).toBe('/workflow/plans')
    expect(homeForRoles([])).toBe('/access-denied')
  })

  it('keeps safe internal deep links including query and hash', () => {
    expect(safeReturnPath({ from: { pathname: '/workflow/plans/p-1', search: '?tab=history', hash: '#round-1' } }, ['MAKER']))
      .toBe('/workflow/plans/p-1?tab=history#round-1')
  })

  it('rejects external, malformed, and auth-loop destinations', () => {
    for (const from of [
      '//evil.example', '///evil.example', '/\\evil.example', '/%5cevil.example', '/%2f%2fevil.example',
      'https://evil.example', 'javascript:alert(1)', '/login', '/register', '/bad%path',
    ]) {
      expect(safeReturnPath({ from }, ['CHECKER'])).toBe('/workflow/reviews')
    }
  })

  it('rejects external and malformed return paths represented as router locations', () => {
    expect(safeReturnPath({ from: { pathname: 'https://evil.example', search: '', hash: '' } }, ['MAKER']))
      .toBe('/workflow/plans')
    expect(safeReturnPath({ from: { pathname: '/workflow/plans', search: '?tab=activity', hash: '#latest' } }, ['MAKER']))
      .toBe('/workflow/plans?tab=activity#latest')
  })
})
