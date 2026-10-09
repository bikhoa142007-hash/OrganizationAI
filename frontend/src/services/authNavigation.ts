export function homeForRoles(roles: readonly string[]): string {
  if (roles.includes('ADMIN')) return '/workflow/plans'
  if (roles.includes('MAKER')) return '/workflow/plans'
  if (roles.includes('CHECKER')) return '/workflow/reviews'
  return '/access-denied'
}

export function safeReturnPath(state: unknown, roles: readonly string[]): string {
  if (!state || typeof state !== 'object' || !('from' in state)) return homeForRoles(roles)
  const from = state.from
  const path = typeof from === 'string'
    ? from
    : from && typeof from === 'object' && 'pathname' in from && typeof from.pathname === 'string'
      ? `${from.pathname}${'search' in from && typeof from.search === 'string' ? from.search : ''}${'hash' in from && typeof from.hash === 'string' ? from.hash : ''}`
      : ''
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return homeForRoles(roles)
  if (['/login', '/register'].includes(path.split(/[?#]/, 1)[0])) return homeForRoles(roles)
  return path
}
