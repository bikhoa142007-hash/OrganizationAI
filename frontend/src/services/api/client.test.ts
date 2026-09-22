import { describe, expect, it, vi } from 'vitest'
import { ApiClient } from './client'
import { mapResult, type History } from './index'

describe('HTTP client', () => {
  it('keeps the intent key after a lost response and maps conflict errors', async () => {
    const transport = vi.fn().mockRejectedValueOnce(new TypeError('Network'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'CONFLICT', message: 'Stale revision', correlation_id: 'c1' }), { status: 409 }))
    const client = new ApiClient('http://localhost/api', () => 'DEMO-MAKER-01', transport)
    await expect(client.request('/plans/p/draft', 'PUT', { expected_revision: 0 })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
    await expect(client.request('/plans/p/draft', 'PUT', { expected_revision: 0 })).rejects.toMatchObject({ code: 'CONFLICT', status: 409, correlationId: 'c1' })
    expect(transport.mock.calls[0][1].headers['Idempotency-Key']).toBe(transport.mock.calls[1][1].headers['Idempotency-Key'])
    expect(transport.mock.calls[0][1].headers['X-Demo-Actor']).toBe('DEMO-MAKER-01')
  })
  it('maps persisted factual uncertainty without deriving an outcome', () => {
    const h: History = { plan: { plan_id: 'p', maker_id: 'maker', payload: { title: 'Campaign' }, attachments: [], revision: 4, current_round: 1,
      state: { plan_status: 'PENDING_APPROVAL', processing_stage: 'HUMAN_REVIEW_REQUIRED', approval_round_status: 'ACTIVE' } }, rounds: [], audit: [], versions: [], records: [
      { kind: 'engine_decision', body: { approval_round: 1, outcome: 'HUMAN_REVIEW_REQUIRED', escalation_category: 'FACT_UNCERTAIN', reason: 'Unresolved KPI', budget_validation: {}, applied_rule_ids: ['NO_EVIDENCE_CONFLICT'] } },
      { kind: 'evaluation', body: { approval_round: 1, feasibility_score: 99, media_confidence: .99, evidence: [], missing_facts: ['Unverified text'], evidence_conflicts: [{ conflict_id: 'c', description: '1200 versus 12000' }] } },
    ] }
    const result = mapResult(h)
    expect(result.variant).toBe('HUMAN_REVIEW')
    expect(result.statusLabel).toContain('FACT_UNCERTAIN')
    expect(result.evidence).toEqual(expect.arrayContaining([expect.objectContaining({ value: '1200 versus 12000' }), expect.objectContaining({ value: 'Unverified text' })]))
  })
})

it.each([401, 403, 409, 422])('keeps structured HTTP %s errors with actionable Vietnamese guidance', async status => {
  const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'TEST_ERROR', message: 'detail', correlation_id: 'trace' }), { status }))
  const client = new ApiClient('http://localhost/api', () => 'actor', transport)
  const guidance = { 401: 'Chọn lại actor', 403: 'không có quyền', 409: 'Tải lại', 422: 'Kiểm tra dữ liệu' }
  await expect(client.request('/plans')).rejects.toMatchObject({ code: 'TEST_ERROR', status, correlationId: 'trace', message: expect.stringContaining(guidance[status as keyof typeof guidance]) })
})

it('loads the review queue from the authorization-enforced backend endpoint', async () => {
  const transport = vi.fn().mockResolvedValue(new Response('[]'))
  const client = new ApiClient('http://localhost/api', () => 'DEMO-CHECKER-01', transport)
  const { createApiServices } = await import('./index')
  expect(await createApiServices(client).review.listPendingReviews()).toEqual([])
  expect(transport.mock.calls[0][0]).toBe('http://localhost/api/reviews')
})
