import { describe, expect, it, vi } from 'vitest'
import { PublicJudgeService } from './publicJudgeService'

function success(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('PublicJudgeService', () => {
  it('uses the isolated endpoint without cookies, demo actor, or client oracle fields', async () => {
    const transport = vi.fn().mockResolvedValue(success({
      run_id: 'JUDGE-1', suite: 'general', status: 'COMPLETED', mode: 'MOCK', data_classification: 'SYNTHETIC',
      started_at: '2026-10-14T00:00:00Z', completed_at: '2026-10-14T00:00:01Z', duration_ms: 1000,
      summary: { total_cases: 4, passed_cases: 3, failed_cases: 1, error_cases: 0 }, rows: [],
    }))
    const service = new PublicJudgeService('https://judge.example/api', false, transport)

    const result = await service.startRun('general')
    const [url, init] = transport.mock.calls[0] as [RequestInfo | URL, RequestInit]

    expect(url).toBe('https://judge.example/api/public/judge/runs')
    expect(init.credentials).toBe('omit')
    const headers = new Headers(init.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.has('X-Demo-Actor')).toBe(false)
    expect(JSON.parse(String(init.body))).toEqual({ suite: 'general' })
    expect(result.summary?.totalCases).toBe(4)
  })

  it('sends only typed user input and preserves the unverified, unmeasured labels', async () => {
    const transport = vi.fn().mockResolvedValue(success({
      run_id: 'JUDGE-INPUT-1', mode: 'MOCK', processing_mode: 'DETERMINISTIC_INPUT_SIMULATION',
      data_classification: 'USER_SUPPLIED_UNVERIFIED', quality_status: 'NOT_MEASURED',
      outcome: 'HUMAN_REVIEW_REQUIRED', category: 'FACT_UNCERTAIN', policy_version: 'JUDGE-INPUT-SIMULATION-1.0',
      reason: 'The entered values differ and are unverified.', handoff_question: 'Which entered value has an approved source?',
      started_at: '2026-10-14T00:00:00Z', completed_at: '2026-10-14T00:00:00Z', duration_ms: 0,
      audit: { action: 'INPUT_EVALUATED', timestamp: '2026-10-14T00:00:00Z', input_sha256: 'hash', reason: 'The entered values differ.' },
    }))
    const service = new PublicJudgeService('https://judge.example/api', false, transport)
    const input = {
      title: 'Synthetic', department: 'DEMO-DEPT-01', objective: 'Objective', summary: 'Summary',
      target_audience: 'Demo audience', channel: 'DEMO_SOCIAL', currency: 'VND', budget_vnd: 50_000_000,
      source_budget_vnd: 42_000_000,
    }

    const result = await service.evaluateInput(input)
    const [url, init] = transport.mock.calls[0] as [RequestInfo | URL, RequestInit]

    expect(url).toBe('https://judge.example/api/public/judge/input-runs')
    expect(init.credentials).toBe('omit')
    expect(JSON.parse(String(init.body))).toEqual(input)
    expect(result.dataClassification).toBe('USER_SUPPLIED_UNVERIFIED')
    expect(result.qualityStatus).toBe('NOT_MEASURED')
    expect(result.category).toBe('FACT_UNCERTAIN')
  })

  it('does not surface arbitrary backend provider text in errors', async () => {
    const transport = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      code: 'UNAVAILABLE', message: 'secret provider traceback', correlation_id: 'corr-1', http_status: 503,
    }), { status: 503, headers: { 'Content-Type': 'application/json' } })))
    const service = new PublicJudgeService('https://judge.example/api', false, transport)

    await expect(service.startRun('escalation')).rejects.toMatchObject({
      code: 'UNAVAILABLE', correlationId: 'corr-1',
    })
    await expect(service.startRun('general')).rejects.toThrow('Judge chưa thể hoàn tất lần chạy này.')
  })
})
