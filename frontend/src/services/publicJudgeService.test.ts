import { describe, expect, it, vi } from 'vitest'
import { PublicJudgeService } from './publicJudgeService'

function success(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('PublicJudgeService', () => {

  it('keeps a suite request alive through a free-plan cold-start window, then preserves unknown-outcome semantics', async () => {
    vi.useFakeTimers()
    try {
      const transport = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Request aborted.', 'AbortError')), { once: true })
      }))
      const service = new PublicJudgeService('https://judge.example/api', false, transport)
      const outcome = service.startRun('general').catch(error => error)
      const [, init] = transport.mock.calls[0] as [RequestInfo | URL, RequestInit]
      const signal = init.signal as AbortSignal

      await vi.advanceTimersByTimeAsync(60_000)
      expect(signal.aborted).toBe(false)
      await vi.advanceTimersByTimeAsync(29_999)
      expect(signal.aborted).toBe(false)
      await vi.advanceTimersByTimeAsync(1)

      expect(signal.aborted).toBe(true)
      expect(transport).toHaveBeenCalledTimes(1)
      expect(await outcome).toMatchObject({
        code: 'OUTCOME_UNKNOWN',
        message: 'Request timed out; the outcome is unknown. Timeout does not stop server work or undo an effect.',
      })
    } finally {
      vi.useRealTimers()
    }
  })
  it('uses the isolated endpoint without cookies, demo actor, or client oracle fields', async () => {
    const transport = vi.fn().mockResolvedValue(success({
      run_id: 'JUDGE-1', suite: 'general', status: 'COMPLETED', mode: 'MOCK', data_classification: 'SYNTHETIC',
      started_at: '2026-10-14T00:00:00Z', completed_at: '2026-10-14T00:00:01Z', duration_ms: 1000,
      summary: { total_cases: 1, passed_cases: 1, failed_cases: 0, error_cases: 0 },
      rows: [{
        case_id: 'CASE-1', status: 'PASS', passed: true, actual_action: 'HUMAN_REVIEW_REQUIRED',
        human_action_available: true, human_action_status: 'PENDING',
        started_at: '2026-10-14T00:00:00Z', completed_at: '2026-10-14T00:00:01Z', duration_ms: 1000,
      }],
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
    expect(result.summary?.totalCases).toBe(1)
    expect(result.rows[0].humanActionStatus).toBe('PENDING')
  })

  it('sends only typed user input and preserves the unverified, unmeasured labels', async () => {
    const transport = vi.fn().mockResolvedValue(success({
      run_id: 'JUDGE-INPUT-1', mode: 'MOCK', processing_mode: 'DETERMINISTIC_INPUT_SIMULATION',
      data_classification: 'USER_SUPPLIED_UNVERIFIED', quality_status: 'NOT_MEASURED',
      outcome: 'HUMAN_REVIEW_REQUIRED', category: 'FACT_UNCERTAIN', policy_version: 'JUDGE-INPUT-SIMULATION-1.0',
      human_action_available: true, human_action_status: 'PENDING',
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
    expect(result.humanActionAvailable).toBe(true)
    expect(result.humanActionStatus).toBe('PENDING')
  })

  it('sends a completed-case action with its UUID idempotency key and maps the audit response', async () => {
    const timestamp = '2026-10-15T01:02:03.000Z'
    const transport = vi.fn().mockResolvedValue(success({
      run_id: 'JUDGE/RUN-1', case_id: 'CASE/1', status: 'HUMAN_APPROVED', action: 'APPROVE',
      is_override: false, timestamp, input_sha256: 'sha256-case', reason: 'Checker reviewed the synthetic evidence.',
      audit: [
        { event_id: 'RUN-AUDIT-1', action: 'ENGINE_RESULT_RECORDED', timestamp, input_sha256: 'sha256-case', reason: 'The synthetic evaluation completed.' },
        { event_id: 'AUDIT-1', actor: 'ANONYMOUS_PUBLIC_JUDGE', action: 'HUMAN_APPROVED', timestamp, input_sha256: 'sha256-case', reason: 'Checker reviewed the synthetic evidence.' },
      ],
      idempotent_replay: true,
    }))
    const service = new PublicJudgeService('https://judge.example/api', false, transport)

    const result = await service.actOnCase('JUDGE/RUN-1', 'CASE/1', 'APPROVE', 'Checker reviewed the synthetic evidence.', '123e4567-e89b-42d3-a456-426614174000')
    const [url, init] = transport.mock.calls[0] as [RequestInfo | URL, RequestInit]
    const headers = new Headers(init.headers)

    expect(url).toBe('https://judge.example/api/public/judge/runs/JUDGE%2FRUN-1/cases/CASE%2F1/action')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('omit')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('Idempotency-Key')).toBe('123e4567-e89b-42d3-a456-426614174000')
    expect(JSON.parse(String(init.body))).toEqual({ action: 'APPROVE', reason: 'Checker reviewed the synthetic evidence.' })
    expect(result).toEqual({
      runId: 'JUDGE/RUN-1', caseId: 'CASE/1', status: 'HUMAN_APPROVED', action: 'APPROVE', isOverride: false,
      timestamp, inputSha256: 'sha256-case', reason: 'Checker reviewed the synthetic evidence.',
      audit: [
        { eventId: 'RUN-AUDIT-1', actor: 'SYSTEM', action: 'ENGINE_RESULT_RECORDED', timestamp, inputSha256: 'sha256-case', reason: 'The synthetic evaluation completed.' },
        { eventId: 'AUDIT-1', actor: 'ANONYMOUS_PUBLIC_JUDGE', action: 'HUMAN_APPROVED', timestamp, inputSha256: 'sha256-case', reason: 'Checker reviewed the synthetic evidence.' },
      ],
      idempotentReplay: true,
    })
  })

  it('preserves final-action conflict status so the UI does not offer a different action', async () => {
    const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'ACTION_ALREADY_FINAL', message: 'A case action already exists.', correlation_id: 'corr-409', http_status: 409,
    }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
    const service = new PublicJudgeService('https://judge.example/api', false, transport)

    await expect(service.actOnCase('JUDGE-1', 'CASE-1', 'REJECT', 'Synthetic rejection reason.', '123e4567-e89b-42d3-a456-426614174000'))
      .rejects.toMatchObject({ code: 'ACTION_ALREADY_FINAL', correlationId: 'corr-409', httpStatus: 409, message: 'Ca tổng hợp này đã có hành động cuối cùng.' })
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
