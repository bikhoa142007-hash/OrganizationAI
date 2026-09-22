import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validatePublicApiUrl } from './validate_frontend.mjs'

test('accepts deployed HTTPS API URL', () => {
  assert.equal(validatePublicApiUrl('https://api.example.com/api'), 'https://api.example.com/api')
})
test('rejects missing, localhost, HTTP and incorrect API paths', () => {
  for (const value of [undefined, '', 'http://api.example.com/api', 'https://localhost/api',
    'https://127.0.0.1/api', 'https://[::1]/api', 'https://api.example.com',
    'https://api.example.com/api/', 'https://user:pass@api.example.com/api',
    'https://api.example.com/api?secret=value']) assert.throws(() => validatePublicApiUrl(value))
})
