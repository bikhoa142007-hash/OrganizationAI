import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'
import { AuthenticatedWorkflowFormPage } from './AuthenticatedWorkflowFormPage'

const checker = { id: 'checker-1', display_name: 'Checker One' }
const blankPayload: WorkflowPayload = {
  title: '', objective: '', summary: '', department: '', start_date: '', end_date: '',
  budget_minor_units: '', currency: 'VND', target_audience: '', channels: [], kpi_expected: '', notes: '',
}

function planFixture(overrides: Partial<WorkflowPlan> = {}): WorkflowPlan {
  return {
    id: 'plan-1', code: 'MKT-1', payload: { ...blankPayload }, status: 'DRAFT', processing_stage: 'DRAFT',
    maker_id: 'maker-1', maker_name: 'Maker One', checker_id: null, checker_name: null,
    current_version: 0, current_round: 0, revision: 0, decision_reason: null,
    attachments: [], versions: [], ai_evaluations: [], engine_decisions: [], history: [],
    created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
    ...overrides,
  }
}

function CurrentRoute() {
  const location = useLocation()
  return <p data-testid="current-route">{location.pathname}</p>
}

function renderForm(path = '/workflow/plans/new') {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/workflow/plans/new" element={<AuthenticatedWorkflowFormPage />} />
    <Route path="/workflow/plans/:planId/edit" element={<AuthenticatedWorkflowFormPage />} />
    <Route path="/workflow/plans/:planId" element={<CurrentRoute />} />
    <Route path="/workflow/plans" element={<CurrentRoute />} />
  </Routes></MemoryRouter>)
}

function readyCheckers() {
  vi.spyOn(authWorkflowService, 'listCheckers').mockResolvedValue([checker])
}

async function enterValidSubmission(budgetMinorUnits: string) {
  const payload: WorkflowPayload = {
    ...blankPayload, title: 'Zero budget campaign', objective: 'Reach customers', summary: 'Plan summary',
    start_date: '2026-10-01', end_date: '2026-10-31', budget_minor_units: budgetMinorUnits,
  }
  await screen.findByRole('option', { name: 'Checker One' })
  fireEvent.change(screen.getByLabelText('Tên kế hoạch'), { target: { value: payload.title } })
  fireEvent.change(screen.getByLabelText('Mục tiêu'), { target: { value: payload.objective } })
  fireEvent.change(screen.getByLabelText('Tóm tắt chiến lược'), { target: { value: payload.summary } })
  fireEvent.change(screen.getByLabelText('Ngày bắt đầu'), { target: { value: payload.start_date } })
  fireEvent.change(screen.getByLabelText('Ngày kết thúc'), { target: { value: payload.end_date } })
  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: payload.budget_minor_units } })
  fireEvent.change(screen.getByLabelText(/Người phê duyệt/), { target: { value: checker.id } })
  const image = new File(['pixels'], 'campaign.png', { type: 'image/png' })
  fireEvent.change(screen.getByLabelText('Chọn ảnh đính kèm'), { target: { files: [image] } })
  return { payload, image }
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('creates an incomplete draft and navigates to the server-assigned detail route', async () => {
  readyCheckers()
  const create = vi.spyOn(authWorkflowService, 'createPlan').mockResolvedValue(planFixture({
    payload: { ...blankPayload, title: 'Campaign draft' },
  }))
  renderForm()

  fireEvent.change(screen.getByLabelText('Tên kế hoạch'), { target: { value: 'Campaign draft' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))

  await waitFor(() => expect(create).toHaveBeenCalledWith({ ...blankPayload, title: 'Campaign draft' }, null))
  expect(await screen.findByTestId('current-route')).toHaveTextContent('/workflow/plans/plan-1')
})

it('edits an existing draft with its current expected revision', async () => {
  readyCheckers()
  const existing = planFixture({ payload: { ...blankPayload, title: 'Current title' }, revision: 7 })
  vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValue(existing)
  const update = vi.spyOn(authWorkflowService, 'updatePlan').mockResolvedValue(planFixture({
    payload: { ...blankPayload, title: 'Updated title' }, revision: 8,
  }))
  renderForm('/workflow/plans/plan-1/edit')

  fireEvent.change(await screen.findByLabelText('Tên kế hoạch'), { target: { value: 'Updated title' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))

  await waitFor(() => expect(update).toHaveBeenCalledWith(
    'plan-1', { ...blankPayload, title: 'Updated title' }, null, 7,
  ))
  expect(await screen.findByTestId('current-route')).toHaveTextContent('/workflow/plans/plan-1')
})

it('shows contract-specific field errors before submit and does not call the API', async () => {
  readyCheckers()
  const create = vi.spyOn(authWorkflowService, 'createPlan')
  renderForm()

  await screen.findByRole('option', { name: 'Checker One' })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))

  expect(await screen.findByText('Tên kế hoạch là bắt buộc khi gửi duyệt.')).toBeVisible()
  expect(screen.getByText('Chọn ngày bắt đầu trước khi gửi.')).toBeVisible()
  expect(screen.getByText('Ngân sách phải là số nguyên không âm, tối đa 24 chữ số.')).toBeVisible()
  expect(screen.getByText('Thêm ít nhất một ảnh PNG, JPEG hoặc WebP trước khi gửi.')).toBeVisible()
  expect(create).not.toHaveBeenCalled()
})

it('shows Checker loading and disables submit until the current Checker response arrives', async () => {
  let finishCheckers!: (value: typeof checker[]) => void
  vi.spyOn(authWorkflowService, 'listCheckers').mockImplementation(() => new Promise(resolve => { finishCheckers = resolve }))
  renderForm()

  expect(screen.getByText('Đang tải danh sách Checker…')).toBeVisible()
  expect(screen.getByLabelText(/Người phê duyệt/)).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Gửi duyệt' })).toBeDisabled()
  finishCheckers([checker])
  expect(await screen.findByRole('option', { name: 'Checker One' })).toBeVisible()
  expect(screen.getByLabelText(/Người phê duyệt/)).toBeEnabled()
})

it('rejects attachments that exceed the backend byte limit before calling upload', async () => {
  readyCheckers()
  const create = vi.spyOn(authWorkflowService, 'createPlan')
  renderForm()

  const largeImage = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })
  fireEvent.change(screen.getByLabelText('Chọn ảnh đính kèm'), { target: { files: [largeImage] } })

  expect(await screen.findByText('Ảnh vượt quá giới hạn 5 MiB của backend.')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))
  expect(create).not.toHaveBeenCalled()
})

it('rejects images above the backend pixel limit before create or upload', async () => {
  readyCheckers()
  const close = vi.fn()
  vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 5001, height: 5000, close }))
  const create = vi.spyOn(authWorkflowService, 'createPlan')
  renderForm()

  const largeImage = new File(['image'], 'large.png', { type: 'image/png' })
  fireEvent.change(screen.getByLabelText('Chọn ảnh đính kèm'), { target: { files: [largeImage] } })
  expect(await screen.findByText('Ảnh vượt quá giới hạn 25 megapixel của backend.')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))
  expect(create).not.toHaveBeenCalled()
  expect(close).toHaveBeenCalledOnce()
})

it('submits only after create, upload and submit succeed, using returned revisions', async () => {
  readyCheckers()
  const requestPayload: WorkflowPayload = {
    ...blankPayload, title: 'Campaign', objective: 'Reach customers', summary: 'Plan summary',
    start_date: '2026-10-01', end_date: '2026-10-31', budget_minor_units: '500000', channels: ['Email'],
  }
  const created = planFixture({ payload: requestPayload, checker_id: checker.id, checker_name: checker.display_name, revision: 2 })
  const uploaded = planFixture({ ...created, revision: 3, attachments: [{
    id: 'attachment-1', filename: 'campaign.png', media_type: 'image/png', byte_size: 6,
    content_hash: 'a'.repeat(64), created_at: '2026-10-01T00:01:00Z',
  }] })
  const submitted = planFixture({ ...uploaded, status: 'PENDING_APPROVAL', processing_stage: 'AI_PENDING', revision: 4, current_version: 1, current_round: 1 })
  const create = vi.spyOn(authWorkflowService, 'createPlan').mockResolvedValue(created)
  const upload = vi.spyOn(authWorkflowService, 'uploadAttachment').mockResolvedValue(uploaded)
  const submit = vi.spyOn(authWorkflowService, 'submitPlan').mockResolvedValue(submitted)
  renderForm()

  await screen.findByRole('option', { name: 'Checker One' })
  fireEvent.change(screen.getByLabelText('Tên kế hoạch'), { target: { value: requestPayload.title } })
  fireEvent.change(screen.getByLabelText('Mục tiêu'), { target: { value: requestPayload.objective } })
  fireEvent.change(screen.getByLabelText('Tóm tắt chiến lược'), { target: { value: requestPayload.summary } })
  fireEvent.change(screen.getByLabelText('Ngày bắt đầu'), { target: { value: requestPayload.start_date } })
  fireEvent.change(screen.getByLabelText('Ngày kết thúc'), { target: { value: requestPayload.end_date } })
  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: requestPayload.budget_minor_units } })
  fireEvent.change(screen.getByLabelText(/Kênh triển khai/), { target: { value: 'Email' } })
  fireEvent.change(screen.getByLabelText(/Người phê duyệt/), { target: { value: checker.id } })
  const image = new File(['pixels'], 'campaign.png', { type: 'image/png' })
  fireEvent.change(screen.getByLabelText('Chọn ảnh đính kèm'), { target: { files: [image] } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))

  await waitFor(() => expect(submit).toHaveBeenCalledWith('plan-1', 3))
  expect(create).toHaveBeenCalledWith(requestPayload, checker.id)
  expect(upload).toHaveBeenCalledWith('plan-1', image, 2)
  expect(create.mock.invocationCallOrder[0]).toBeLessThan(upload.mock.invocationCallOrder[0]!)
  expect(upload.mock.invocationCallOrder[0]).toBeLessThan(submit.mock.invocationCallOrder[0]!)
  expect(await screen.findByTestId('current-route')).toHaveTextContent('/workflow/plans/plan-1')
})

it('accepts a zero budget for submission and describes it as a non-negative integer', async () => {
  readyCheckers()
  const created = planFixture({
    payload: { ...blankPayload, title: 'Zero budget campaign', objective: 'Reach customers', summary: 'Plan summary', start_date: '2026-10-01', end_date: '2026-10-31', budget_minor_units: '0' },
    checker_id: checker.id, checker_name: checker.display_name, revision: 2,
  })
  const uploaded = planFixture({ ...created, revision: 3, attachments: [{
    id: 'attachment-1', filename: 'campaign.png', media_type: 'image/png', byte_size: 6,
    content_hash: 'a'.repeat(64), created_at: '2026-10-01T00:01:00Z',
  }] })
  const submitted = planFixture({ ...uploaded, status: 'PENDING_APPROVAL', processing_stage: 'AI_PENDING', revision: 4, current_version: 1, current_round: 1 })
  const create = vi.spyOn(authWorkflowService, 'createPlan').mockResolvedValue(created)
  vi.spyOn(authWorkflowService, 'uploadAttachment').mockResolvedValue(uploaded)
  const submit = vi.spyOn(authWorkflowService, 'submitPlan').mockResolvedValue(submitted)
  renderForm()

  const { payload, image } = await enterValidSubmission('0')
  expect(screen.getByText(/số nguyên không âm/)).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))

  await waitFor(() => expect(submit).toHaveBeenCalledWith('plan-1', 3))
  expect(create).toHaveBeenCalledWith(payload, checker.id)
  expect(authWorkflowService.uploadAttachment).toHaveBeenCalledWith('plan-1', image, 2)
})

it('continues to reject negative and non-integer budgets before creating a plan', async () => {
  readyCheckers()
  const create = vi.spyOn(authWorkflowService, 'createPlan')
  renderForm()

  await enterValidSubmission('-1')
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(await screen.findByText('Ngân sách phải là số nguyên không âm, tối đa 24 chữ số.')).toBeVisible()
  expect(create).not.toHaveBeenCalled()

  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: '1.5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByText('Ngân sách phải là số nguyên không âm, tối đa 24 chữ số.')).toBeVisible()
  expect(create).not.toHaveBeenCalled()
})

it('keeps the typed values and selected file after a 422 upload error', async () => {
  readyCheckers()
  const saved = planFixture({ payload: { ...blankPayload, title: 'My campaign' } })
  vi.spyOn(authWorkflowService, 'createPlan').mockResolvedValue(saved)
  vi.spyOn(authWorkflowService, 'uploadAttachment').mockRejectedValue(new AuthApiError(422, 'Upload a valid PNG, JPEG, or WebP image.', 'VALIDATION_ERROR', 'trace-422'))
  vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValue(saved)
  renderForm()

  fireEvent.change(screen.getByLabelText('Tên kế hoạch'), { target: { value: 'My campaign' } })
  const image = new File(['pixels'], 'campaign.png', { type: 'image/png' })
  fireEvent.change(screen.getByLabelText('Chọn ảnh đính kèm'), { target: { files: [image] } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Upload a valid PNG, JPEG, or WebP image.')
  expect(screen.getByText('Mã tham chiếu: trace-422')).toBeVisible()
  expect(screen.getByLabelText('Tên kế hoạch')).toHaveValue('My campaign')
  expect(screen.getByText(/campaign.png.*chờ tải lên/)).toBeVisible()
})

it('refreshes a conflicted revision without replacing local edits until the user chooses', async () => {
  readyCheckers()
  const original = planFixture({ payload: { ...blankPayload, title: 'Original' }, checker_id: checker.id, checker_name: checker.display_name, revision: 2 })
  const latest = planFixture({ payload: { ...blankPayload, title: 'Server version' }, checker_id: checker.id, checker_name: checker.display_name, revision: 5 })
  vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValueOnce(original).mockResolvedValueOnce(latest)
  vi.spyOn(authWorkflowService, 'updatePlan').mockRejectedValue(new AuthApiError(409, 'The plan changed. Reload it before saving.', 'CONFLICT', 'trace-409'))
  renderForm('/workflow/plans/plan-1/edit')

  fireEvent.change(await screen.findByLabelText('Tên kế hoạch'), { target: { value: 'My local edit' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))

  expect(await screen.findByRole('heading', { name: 'Máy chủ có revision mới hơn' })).toBeVisible()
  expect(screen.getByLabelText('Tên kế hoạch')).toHaveValue('My local edit')
  expect(screen.getByText(/revision 5/)).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Dùng bản mới nhất' }))
  expect(screen.getByLabelText('Tên kế hoạch')).toHaveValue('Server version')
})

it('retains form values after a 422 create response', async () => {
  readyCheckers()
  const create = vi.spyOn(authWorkflowService, 'createPlan').mockRejectedValue(new AuthApiError(
    422, 'title is required before submission.', 'VALIDATION_ERROR', 'trace-validation',
  ))
  renderForm()

  fireEvent.change(screen.getByLabelText('Tên kế hoạch'), { target: { value: 'Keep this draft' } })
  fireEvent.click(screen.getByRole('button', { name: 'Lưu bản nháp' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('title is required before submission.')
  expect(screen.getByLabelText('Tên kế hoạch')).toHaveValue('Keep this draft')
  expect(create).toHaveBeenCalledOnce()
})
