import type { VerifyResultRow, VerifyRun, VerifyRunSummary, VerifySuite } from '../../types'
import type { VerifyService } from '../interfaces'
import { mockVerifyCases } from './mockVerifyData'

const CASE_DELAY_MS = 650

export class MockVerifyService implements VerifyService {
  private runSequence = 0
  private readonly runs = new Map<string, VerifyRun>()

  async startRun(suite: VerifySuite): Promise<VerifyRun> {
    const runId = `mock-verify-${++this.runSequence}`
    const rows: VerifyResultRow[] = mockVerifyCases[suite].map((row): VerifyResultRow => ({ ...row, status: 'PENDING', pass: undefined, reason: undefined, error: null }))
    const run: VerifyRun = {
      runId,
      suite,
      status: 'RUNNING',
      rows,
      summary: summarize(rows),
      startedAt: new Date().toISOString(),
      currentCaseId: rows[0]?.caseId ?? null,
      dataSource: 'MOCK',
    }
    this.runs.set(runId, run)
    void this.runSequentially(runId, suite)
    return cloneRun(run)
  }

  async getRun(runId: string): Promise<VerifyRun | null> {
    const run = this.runs.get(runId)
    return run ? cloneRun(run) : null
  }

  private async runSequentially(runId: string, suite: VerifySuite) {
    const cases = mockVerifyCases[suite]
    for (const [index, completedCase] of cases.entries()) {
      const run = this.runs.get(runId)
      if (!run || run.status !== 'RUNNING') return

      const row = run.rows[index]
      if (!row) return
      run.currentCaseId = row.caseId
      run.rows[index] = { ...row, status: 'RUNNING', startedAt: new Date().toISOString() }
      run.summary = summarize(run.rows)

      await delay(CASE_DELAY_MS)

      const completedAt = new Date().toISOString()
      const currentRun = this.runs.get(runId)
      if (!currentRun || currentRun.status !== 'RUNNING') return
      const currentRow = currentRun.rows[index]
      if (!currentRow) return
      currentRun.rows[index] = {
        ...completedCase,
        startedAt: currentRow.startedAt,
        completedAt,
        durationMs: CASE_DELAY_MS,
      }
      currentRun.summary = summarize(currentRun.rows)
    }

    const run = this.runs.get(runId)
    if (!run) return
    run.status = 'COMPLETED'
    run.completedAt = new Date().toISOString()
    run.currentCaseId = null
    run.summary = summarize(run.rows)
  }
}

function summarize(rows: VerifyResultRow[]): VerifyRunSummary {
  const passedCases = rows.filter((row) => row.status === 'PASS').length
  const failedCases = rows.filter((row) => row.status === 'FAIL').length
  const errorCases = rows.filter((row) => row.status === 'ERROR').length
  const completedCases = passedCases + failedCases + errorCases
  return {
    totalCases: rows.length,
    completedCases,
    passedCases,
    failedCases,
    errorCases,
    progressPercent: rows.length === 0 ? 0 : Math.round((completedCases / rows.length) * 100),
  }
}

function cloneRun(run: VerifyRun): VerifyRun {
  return {
    ...run,
    rows: run.rows.map((row) => ({
      ...row,
      generatedQuestion: row.generatedQuestion ? [...row.generatedQuestion] : [],
      appliedRuleIds: row.appliedRuleIds ? [...row.appliedRuleIds] : [],
      error: row.error ? { ...row.error } : null,
    })),
    summary: run.summary ? { ...run.summary } : undefined,
    error: run.error ? { ...run.error } : null,
  }
}

function delay(durationMs: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, durationMs))
}
