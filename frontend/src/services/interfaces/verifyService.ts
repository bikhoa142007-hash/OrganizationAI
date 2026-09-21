import type { VerifyRun, VerifySuite } from '../../types'

export interface VerifyService {
  startRun(suite: VerifySuite): Promise<VerifyRun>
  getRun(runId: string): Promise<VerifyRun | null>
}
