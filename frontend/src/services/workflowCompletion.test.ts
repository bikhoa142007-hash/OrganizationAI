import { afterEach, expect, it, vi } from 'vitest'
import { resolveApiBaseUrl } from './apiBaseUrl'
import { AuthApiError } from './auth'
import { workflowCompletionService } from './workflowCompletion'

const dashboard = {
  as_of: '2026-10-12T08:30:00+00:00',
  principal_scope: 'MAKER_OWN',
  counts: { draft: 4, pending_ai: 2, human_review: 1, approved: 3, rejected: 1 },
  active_assignments: 3,
}

afterEach(() => vi.restoreAllMocks())

it('fetches and validates the backend aggregate with the authenticated cookie session', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(dashboard), { status: 200 }),
  )

  await expect(workflowCompletionService.getDashboard()).resolves.toEqual(dashboard)

  expect(fetchSpy).toHaveBeenCalledWith(
    `${resolveApiBaseUrl()}/workflow/dashboard`,
    { method: 'GET', credentials: 'include' },
  )
})

it('rejects malformed or non-UTC dashboard snapshots', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    ...dashboard,
    as_of: '2026-10-12T08:30:00',
  }), { status: 200 }))

  await expect(workflowCompletionService.getDashboard()).rejects.toMatchObject({
    status: 502,
    code: 'INVALID_RESPONSE',
  } satisfies Partial<AuthApiError>)
})

it('fetches private note content only from the assigned-plan endpoint', async () => {
  const note = {
    note_id: '8c4204a9-4bf2-49bb-8b62-7da84a6785a7',
    plan_id: '4f02d26e-17ee-428b-b2d1-3f83b69a9db7',
    approval_round: 1,
    author_id: 'ec2f572e-01cd-46fe-90ad-21c69e5913dc',
    created_at: '2026-10-12T08:30:00+00:00',
    content: 'Internal review detail',
  }
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ items: [note] }), { status: 200 }),
  )

  await expect(workflowCompletionService.getInternalNotes(note.plan_id)).resolves.toEqual([note])
  expect(fetchSpy).toHaveBeenCalledWith(
    `${resolveApiBaseUrl()}/workflow/plans/${note.plan_id}/internal-notes`,
    { method: 'GET', credentials: 'include' },
  )
})

it('posts a retry against the same approval round and validates the immutable run result', async () => {
  const result = {
    plan_id: '4f02d26e-17ee-428b-b2d1-3f83b69a9db7',
    plan_version: 2,
    approval_round: 3,
    run_id: 'RUN-0003-RETRY-1',
    run_status: 'FAILED',
    processing_stage: 'HUMAN_REVIEW_REQUIRED',
    decision_id: null,
    attempt_number: 2,
    result_disposition: 'APPLIED',
  }
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(result), { status: 200 }),
  )

  await expect(workflowCompletionService.retryEvaluation(result.plan_id, 3, {
    expected_plan_version: 2,
    expected_round_revision: 9,
  }, 'retry-key')).resolves.toEqual(result)
  expect(fetchSpy).toHaveBeenCalledWith(
    `${resolveApiBaseUrl()}/workflow/plans/${result.plan_id}/rounds/3/evaluation-retries`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'retry-key' },
      body: JSON.stringify({ expected_plan_version: 2, expected_round_revision: 9 }),
    },
  )

  vi.mocked(fetchSpy).mockResolvedValueOnce(new Response(JSON.stringify({ ...result, result_disposition: 'INVALID' }), { status: 200 }))
  await expect(workflowCompletionService.retryEvaluation(result.plan_id, 3, {
    expected_plan_version: 2,
    expected_round_revision: 9,
  }, 'retry-key-2')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})

it('posts a note with an idempotency key and rejects unexpected sensitive fields', async () => {
  const note = {
    note_id: '8c4204a9-4bf2-49bb-8b62-7da84a6785a7',
    plan_id: '4f02d26e-17ee-428b-b2d1-3f83b69a9db7',
    approval_round: null,
    author_id: 'ec2f572e-01cd-46fe-90ad-21c69e5913dc',
    created_at: '2026-10-12T08:30:00Z',
    content: 'Internal review detail',
  }
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(note), { status: 201 }),
  )

  await expect(workflowCompletionService.addInternalNote(note.plan_id, {
    approval_round: null,
    content: note.content,
  }, 'note-key')).resolves.toEqual(note)
  expect(fetchSpy).toHaveBeenCalledWith(
    `${resolveApiBaseUrl()}/workflow/plans/${note.plan_id}/internal-notes`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'note-key' },
      body: JSON.stringify({ approval_round: null, content: note.content }),
    },
  )

  vi.mocked(fetchSpy).mockResolvedValueOnce(new Response(JSON.stringify({ ...note, content: undefined, secret: 'unexpected' }), { status: 201 }))
  await expect(workflowCompletionService.addInternalNote(note.plan_id, {
    approval_round: null,
    content: note.content,
  }, 'note-key-2')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
