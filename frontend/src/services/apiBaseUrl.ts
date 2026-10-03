const DEVELOPMENT_API_BASE_URL = 'http://localhost:8010/api'

export function resolveApiBaseUrl(
  configured = import.meta.env.VITE_API_BASE_URL as string | undefined,
  development = import.meta.env.DEV,
): string {
  const value = configured?.trim()
  if (!value) {
    if (development) return DEVELOPMENT_API_BASE_URL
    throw new Error('VITE_API_BASE_URL must be configured for this deployment.')
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute API URL.')
  }

  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.search || url.hash || !['', '/', '/api'].includes(url.pathname)) {
    throw new Error('VITE_API_BASE_URL must be an API origin or an origin ending in /api.')
  }
  if (!development && url.protocol !== 'https:') {
    throw new Error('VITE_API_BASE_URL must use HTTPS in production.')
  }

  return `${url.origin}/api`
}

export function isDemoEnabled() {
  return import.meta.env.DEV || import.meta.env.VITE_DEMO_ENABLED === 'true'
}
