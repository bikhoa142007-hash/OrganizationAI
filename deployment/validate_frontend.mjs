import { pathToFileURL } from 'node:url'
import { isIP } from 'node:net'

export function validatePublicApiUrl(value) {
  let url
  try { url = new URL(value) } catch { throw new Error('VITE_API_BASE_URL must be a public HTTPS API URL ending in /api') }
  if (url.protocol !== 'https:' || url.pathname !== '/api' || url.search || url.hash ||
      url.username || url.password || url.hostname === 'localhost' ||
      url.hostname.endsWith('.localhost') || isIP(url.hostname) || url.hostname.startsWith('[')) {
    throw new Error('VITE_API_BASE_URL must use a public HTTPS hostname and exactly /api')
  }
  return value
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  validatePublicApiUrl(process.env.VITE_API_BASE_URL)
  console.log('Public HTTPS API URL validated')
}
