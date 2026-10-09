import { describe, expect, it } from 'vitest'
import { MockVerifyService } from './mockVerifyService'

describe('MockVerifyService', () => {
  it('refuses to present canned results as a fresh Verify run', async () => {
    await expect(new MockVerifyService().startRun('escalation'))
      .rejects.toThrow('Verify requires a fresh backend run')
  })
})
