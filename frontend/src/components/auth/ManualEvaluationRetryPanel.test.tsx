import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AuthApiError } from '../../services/auth'
import { workflowCompletionService } from '../../services/workflowCompletion'
import { ManualEvaluationRetryPanel } from './ManualEvaluationRetryPanel'

const props = {
  planId: '4f02d26e-17ee-428b-b2d1-3f83b69a9db7',
  planVersion: 2,
  approvalRound: 3,
  roundRevision: 9,
  isAssignedChecker: true,
  isRetryAvailable: true,
}
const result = {
  plan_id: props.planId,
  plan_version: 2,
  approval_round: 3,
  run_id: 'RUN-0003-RETRY-1',
  run_status: 'FAILED' as const,
  processing_stage: 'HUMAN_REVIEW_REQUIRED',
  decision_id: null,
  attempt_number: 2,
  result_disposition: 'APPLIED' as const,
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('does not show retry controls outside an assigned Checker eligible state', () => {
  const { rerender } = render(<ManualEvaluationRetryPanel {...props} isAssignedChecker={false} />)
  expect(screen.queryByRole('button', { name: 'Chạy lại AI' })).not.toBeInTheDocument()
  rerender(<ManualEvaluationRetryPanel {...props} isRetryAvailable={false} />)
  expect(screen.queryByRole('button', { name: 'Chạy lại AI' })).not.toBeInTheDocument()
})

it('reuses the idempotency key after a transient failure and reports fail-closed retry status', async () => {
  const key = 'b9b2752a-4288-4cc4-8b81-8ab174fa9556'
  vi.stubGlobal('crypto', { randomUUID: () => key })
  const retry = vi.spyOn(workflowCompletionService, 'retryEvaluation')
    .mockRejectedValueOnce(new AuthApiError(503, 'Unavailable', 'UNAVAILABLE'))
    .mockResolvedValue(result)
  const onRetryComplete = vi.fn()
  render(<ManualEvaluationRetryPanel {...props} onRetryComplete={onRetryComplete} />)

  fireEvent.click(screen.getByRole('button', { name: 'Chạy lại AI' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể chạy lại đánh giá AI.')
  fireEvent.click(screen.getByRole('button', { name: 'Chạy lại AI' }))

  expect(await screen.findByRole('status')).toHaveTextContent('kết thúc cần Checker xem xét')
  expect(retry).toHaveBeenCalledTimes(2)
  expect(retry).toHaveBeenNthCalledWith(1, props.planId, 3, {
    expected_plan_version: 2,
    expected_round_revision: 9,
  }, key)
  expect(retry).toHaveBeenNthCalledWith(2, props.planId, 3, {
    expected_plan_version: 2,
    expected_round_revision: 9,
  }, key)
  expect(onRetryComplete).toHaveBeenCalledWith(result)
})
