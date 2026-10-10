import type { VerifyRun, VerifySuite } from '../../types'
import type { VerifyService } from '../interfaces'

export class MockVerifyService implements VerifyService {
  async startRun(_suite: VerifySuite): Promise<VerifyRun> {
    throw new Error('Verify requires a fresh backend run. Mock results are not accepted as evidence.')
  }

  async getRun(_runId: string): Promise<VerifyRun | null> {
    return null
  }
}
