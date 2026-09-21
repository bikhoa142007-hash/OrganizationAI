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
