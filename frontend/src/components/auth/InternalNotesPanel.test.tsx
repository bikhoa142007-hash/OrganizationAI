import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthApiError } from '../../services/auth'
import { workflowCompletionService, type WorkflowInternalNote } from '../../services/workflowCompletion'
import { InternalNotesPanel } from './InternalNotesPanel'

const planId = '4f02d26e-17ee-428b-b2d1-3f83b69a9db7'
const existingNote: WorkflowInternalNote = {
  note_id: '8c4204a9-4bf2-49bb-8b62-7da84a6785a7',
  plan_id: planId,
  approval_round: 2,
  author_id: 'ec2f572e-01cd-46fe-90ad-21c69e5913dc',
  created_at: '2026-10-12T08:30:00Z',
  content: 'Private note visible to the assigned Checker.',
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('renders notes as read-only history for the assigned Checker', async () => {
  vi.spyOn(workflowCompletionService, 'getInternalNotes').mockResolvedValue([existingNote])
  vi.spyOn(workflowCompletionService, 'addInternalNote')

  render(<InternalNotesPanel planId={planId} approvalRound={2} />)

  expect(await screen.findByText(existingNote.content)).toBeVisible()
  expect(screen.getByText(/UTC$/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Thêm ghi chú' })).toBeDisabled()
  expect(screen.queryByRole('button', { name: /sửa|xóa/i })).not.toBeInTheDocument()
})

it('posts a trimmed note with a stable idempotency key and appends it once', async () => {
  const user = userEvent.setup()
  const key = 'b9b2752a-4288-4cc4-8b81-8ab174fa9556'
  vi.stubGlobal('crypto', { randomUUID: () => key })
  vi.spyOn(workflowCompletionService, 'getInternalNotes').mockResolvedValue([])
  const add = vi.spyOn(workflowCompletionService, 'addInternalNote')
    .mockRejectedValueOnce(new AuthApiError(503, 'Unavailable', 'UNAVAILABLE'))
    .mockResolvedValue(existingNote)

  render(<InternalNotesPanel planId={planId} approvalRound={2} />)
  const input = await screen.findByLabelText(/Thêm ghi chú cho Checker/)
  await user.type(input, '  Needs human follow-up  ')
  await user.click(screen.getByRole('button', { name: 'Thêm ghi chú' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể tải hoặc lưu ghi chú nội bộ.')
  await user.click(screen.getByRole('button', { name: 'Thêm ghi chú' }))

  await waitFor(() => expect(add).toHaveBeenCalledTimes(2))
  expect(add).toHaveBeenNthCalledWith(1, planId, {
    approval_round: 2,
    content: 'Needs human follow-up',
  }, key)
  expect(add).toHaveBeenNthCalledWith(2, planId, {
    approval_round: 2,
    content: 'Needs human follow-up',
  }, key)
  expect(await screen.findByText(existingNote.content)).toBeVisible()
})

it('clears note content and hides the editor when assignment access is denied', async () => {
  vi.spyOn(workflowCompletionService, 'getInternalNotes').mockResolvedValue([existingNote])
  vi.spyOn(workflowCompletionService, 'addInternalNote').mockRejectedValue(
    new AuthApiError(403, 'Forbidden', 'FORBIDDEN'),
  )

  render(<InternalNotesPanel planId={planId} approvalRound={2} />)
  expect(await screen.findByText(existingNote.content)).toBeVisible()
  fireEvent.change(screen.getByLabelText(/Thêm ghi chú cho Checker/), { target: { value: 'new private text' } })
  fireEvent.click(screen.getByRole('button', { name: 'Thêm ghi chú' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Chỉ Checker đang được giao')
  expect(screen.queryByText(existingNote.content)).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Thêm ghi chú cho Checker')).not.toBeInTheDocument()
})
