export function homeForRoles(roles: readonly string[]): string {
  if (roles.includes('ADMIN')) return '/workflow/plans'
  if (roles.includes('MAKER')) return '/workflow/plans'
  if (roles.includes('CHECKER')) return '/workflow/reviews'
  return '/access-denied'
}

export function safeReturnPath(state: unknown, roles: readonly string[]): string {
  if (!state || typeof state !== 'object' || !('from' in state)) return homeForRoles(roles)
  const from = state.from
  const rawPath = typeof from === 'string'
    ? from
    : from && typeof from === 'object' && 'pathname' in from && typeof from.pathname === 'string'
      ? `${from.pathname}${'search' in from && typeof from.search === 'string' ? from.search : ''}${'hash' in from && typeof from.hash === 'string' ? from.hash : ''}`
      : ''

  if (!rawPath.startsWith('/') || rawPath.startsWith('//') || rawPath.includes('\\') || /[\u0000-\u001f]/.test(rawPath)) {
    return homeForRoles(roles)
  }

  try {
    const base = 'https://organizationai.invalid'
    const destination = new URL(rawPath, base)
    const decodedPathname = decodeURIComponent(destination.pathname)
    if (destination.origin !== base || decodedPathname.startsWith('//') || decodedPathname.includes('\\')) {
      return homeForRoles(roles)
    }
    if (['/login', '/register'].includes(destination.pathname)) return homeForRoles(roles)
    return `${destination.pathname}${destination.search}${destination.hash}`
  } catch {
    return homeForRoles(roles)
  }
}
