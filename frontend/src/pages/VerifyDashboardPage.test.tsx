import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { VerifyDashboardPage } from './VerifyDashboardPage'
import { ServicesProvider } from '../services/ServiceProvider'
import type { FrontendServices } from '../services/interfaces'
import type { VerifyRun } from '../types'

const demoRun: VerifyRun = {
  runId: 'demo-run-1', suite: 'escalation', status: 'COMPLETED',
  startedAt: '2026-10-09T10:00:00Z', completedAt: '2026-10-09T10:00:02Z', dataSource: 'API',
  rows: [{
    caseId: 'DEMO-CASE-1', caseName: 'Synthetic uncertainty case',
    expectedAction: 'HUMAN_REVIEW_REQUIRED', expectedCategory: 'FACT_UNCERTAIN',
    actualAction: 'HUMAN_REVIEW_REQUIRED', actualCategory: 'FACT_UNCERTAIN',
    generatedQuestion: [{ category: 'FACT_UNCERTAIN', question: 'Which submitted budget value is supported by the source document?', evidenceReferences: ['attachment:vendor-quote'] }],
    status: 'PASS', pass: true, reason: 'Fixture evidence conflicts with the submitted budget.',
    startedAt: '2026-10-09T10:00:00Z', completedAt: '2026-10-09T10:00:02Z',
  }],
  summary: { totalCases: 1, completedCases: 1, passedCases: 1, failedCases: 0, errorCases: 0, progressPercent: 100 },
}

const publicRun = {
  run_id: 'JUDGE-NEW-CASE-1', suite: 'escalation', status: 'COMPLETED', mode: 'MOCK',
  data_classification: 'SYNTHETIC', started_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:00:02Z', duration_ms: 2000,
  summary: { total_cases: 1, passed_cases: 1, failed_cases: 0, error_cases: 0 },
  rows: [{
    case_id: 'NEW-CASE-1', case_name: 'Synthetic uncertainty case', status: 'PASS', passed: true,
    expected_action: 'HUMAN_REVIEW_REQUIRED', expected_category: 'FACT_UNCERTAIN',
    actual_action: 'HUMAN_REVIEW_REQUIRED', actual_category: 'FACT_UNCERTAIN',
    human_action_available: true, human_action_status: 'PENDING',
    started_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:00:02Z', duration_ms: 2000,
    reason: 'OCR evidence conflicts with the submitted budget.',
    questions: [{ category: 'FACT_UNCERTAIN', question: 'Which submitted budget value is supported by the source document?', evidence_references: ['attachment:vendor-quote'] }],
    evidence: [], applied_rule_ids: [], audit: [{
      event_id: 'AUDIT-1', action: 'ENGINE_ROUTED', timestamp: '2026-10-09T10:00:02Z',
      input_sha256: 'sha256-fixture', reason: 'OCR evidence conflicts with the submitted budget.',
    }],
  }],
}

const checkerActionResponse = {
  run_id: 'JUDGE-NEW-CASE-1', case_id: 'NEW-CASE-1', status: 'HUMAN_APPROVED', action: 'APPROVE',
  is_override: false, timestamp: '2026-10-15T01:02:03.000Z', input_sha256: 'sha256-case',
  reason: 'Checker reviewed the synthetic evidence.',
  audit: [{ event_id: 'ACTION-AUDIT-1', actor: 'ANONYMOUS_PUBLIC_JUDGE', action: 'HUMAN_APPROVED', timestamp: '2026-10-15T01:02:03.000Z', input_sha256: 'sha256-case', reason: 'Checker reviewed the synthetic evidence.' }],
  idempotent_replay: false,
}

const stopActionResponse = {
  ...checkerActionResponse,
  status: 'STOPPED', action: 'STOP', reason: 'Stop follow-up simulation after this result.',
  audit: [{ event_id: 'ACTION-AUDIT-STOP', actor: 'ANONYMOUS_PUBLIC_JUDGE', action: 'STOPPED', timestamp: '2026-10-15T01:02:03.000Z', input_sha256: 'sha256-case', reason: 'Stop follow-up simulation after this result.' }],
}

const publicInputRun = {
  run_id: 'JUDGE-INPUT-1', mode: 'MOCK', processing_mode: 'DETERMINISTIC_INPUT_SIMULATION',
  data_classification: 'USER_SUPPLIED_UNVERIFIED', quality_status: 'NOT_MEASURED',
  outcome: 'SIMULATED_AUTO_APPROVE', category: null, human_action_available: true, human_action_status: 'PENDING',
  policy_version: 'JUDGE-INPUT-SIMULATION-1.0', reason: 'Inputs fit the simulation scope.', handoff_question: null,
  started_at: '2026-10-15T01:00:00.000Z', completed_at: '2026-10-15T01:00:01.000Z', duration_ms: 1000,
  audit: { action: 'INPUT_EVALUATED', timestamp: '2026-10-15T01:00:01.000Z', input_sha256: 'sha256-input', reason: 'Inputs fit the simulation scope.' },
}

const simulatedOverrideResponse = {
  ...checkerActionResponse,
  run_id: 'JUDGE-INPUT-1', case_id: 'NEW_INPUT', status: 'HUMAN_REJECTED', action: 'REJECT', is_override: true,
  reason: 'The simulated auto outcome is being challenged.', idempotent_replay: true,
}

function renderPage(
  mode: 'demo' | 'public' = 'demo',
  runResponse: unknown = publicRun,
  actionResponse: unknown = checkerActionResponse,
  inputResponse: unknown = publicInputRun,
) {
  const startRun = vi.fn().mockResolvedValue(demoRun)
  const services = { verify: { startRun, getRun: vi.fn() } } as unknown as FrontendServices
  const fetchMock = vi.fn<typeof fetch>(input => {
    const url = String(input)
    const body = url.endsWith('/action') ? actionResponse : url.endsWith('/input-runs') ? inputResponse : runResponse
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<MemoryRouter><ServicesProvider services={services}><VerifyDashboardPage mode={mode} /></ServicesProvider></MemoryRouter>)
  return { fetchMock, startRun }
}

afterEach(() => vi.unstubAllGlobals())

describe('Judge Verify dashboard', () => {
  it('marks the existing route as Demo and preserves the 15-case regression option', () => {
    renderPage()

    expect(screen.getByText('Judge Demo · MOCK — không phải public acceptance')).toBeTruthy()
    expect(screen.getByText(/Kết quả MOCK chỉ xác nhận demo workflow/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Bộ hồi quy tổng hợp.*15 ca/i })).toBeTruthy()
    expect(screen.getByRole('link', { name: /nhập kế hoạch tổng hợp mới/i }).getAttribute('href')).toBe('/demo/plans/new')
  })

  it('shows one first-use instruction for the public mode', () => {
    renderPage('public')
    expect(screen.getByText('Bước đầu tiên: bấm “Run 4 cases” để chạy Verify chung.')).toBeTruthy()
    expect(document.querySelector('.verify-first-use')?.tagName).toBe('P')
  })

  it('offers only the public suites and keeps the new-input form out of Demo mode', () => {
    renderPage('public')

    expect(screen.getByRole('button', { name: /Verify chung.*4 ca/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Bộ hồi quy tổng hợp/i })).toBeNull()
    expect(screen.getByText(/Catalog tham chiếu có 15 ca tổng hợp/i)).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Thử một bộ dữ liệu có cấu trúc' })).toBeTruthy()
    expect(screen.getByText(/không nhập dữ liệu cá nhân\/bí mật/i)).toBeTruthy()
  })

  it('keeps the current Demo route on its existing VerifyService', async () => {
    const { fetchMock, startRun } = renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run.*5/i }))

    await waitFor(() => expect(startRun).toHaveBeenCalledWith('escalation'))
    expect(startRun).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText('DEMO RUN · MOCK')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết DEMO-CASE-1' }))

    expect(screen.getByText('Which submitted budget value is supported by the source document?')).toBeTruthy()
    expect(screen.getByText('attachment:vendor-quote')).toBeTruthy()
    expect(screen.getAllByText('FACT_UNCERTAIN').length).toBeGreaterThan(0)
  })

  it('runs the 15-case regression through the existing Demo VerifyService', async () => {
    const { fetchMock, startRun } = renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Bộ hồi quy tổng hợp.*15 ca/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run.*15/i }))

    await waitFor(() => expect(startRun).toHaveBeenCalledWith('regression'))
    expect(startRun).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText('DEMO RUN · MOCK')).toBeTruthy()
  })

  it('uses the isolated public client only when explicitly rendered in public mode', async () => {
    const { fetchMock, startRun } = renderPage('public')

    fireEvent.click(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run.*5/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(fetchMock.mock.calls[0][0]).toContain('/public/judge/runs')
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ suite: 'escalation' })
    expect(startRun).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết NEW-CASE-1' }))

    expect(screen.getByText('Which submitted budget value is supported by the source document?')).toBeTruthy()
    expect(screen.getByText('attachment:vendor-quote')).toBeTruthy()
    expect(screen.getByText('Audit events')).toBeTruthy()
    expect(screen.getByText(/Action: ENGINE_ROUTED.*Input SHA-256: sha256-fixture.*Reason:/)).toBeTruthy()
  })

  it('records a simulated Checker action only after a completed human-review case and retries the same intent', async () => {
    const idempotencyKey = '123e4567-e89b-42d3-a456-426614174000'
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => idempotencyKey) })
    const { fetchMock } = renderPage('public')

    expect(screen.queryByRole('heading', { name: 'Quyết định Checker mô phỏng' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Verify → Escalation · 5 ca' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run 5 cases' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết NEW-CASE-1' }))

    expect(screen.getByRole('heading', { name: 'Quyết định Checker mô phỏng' })).toBeTruthy()
    expect(screen.getByText('STOP')).toBeTruthy()
    expect(screen.getByText(/không hủy inference\/run đang chạy và không hoàn tác side effect/i)).toBeTruthy()
    const actionSelect = screen.getByLabelText('Thao tác mô phỏng') as HTMLSelectElement
    const reason = screen.getByLabelText('Lý do (bắt buộc, tối đa 500 ký tự)') as HTMLTextAreaElement
    const submit = screen.getByRole('button', { name: 'Ghi nhận thao tác mô phỏng' }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)

    fireEvent.change(actionSelect, { target: { value: 'APPROVE' } })
    fireEvent.change(reason, { target: { value: '  Checker reviewed the synthetic evidence.  ' } })
    expect(submit.disabled).toBe(false)
    fetchMock.mockRejectedValueOnce(new TypeError('connection reset after send'))
    fireEvent.click(submit)

    const retry = await screen.findByRole('button', { name: 'Thử lại đúng thao tác với cùng key' })
    expect((screen.getByLabelText('Thao tác mô phỏng') as HTMLSelectElement).disabled).toBe(true)
    fireEvent.click(retry)

    await screen.findByText('HUMAN_APPROVED')
    const actionCalls = fetchMock.mock.calls.slice(1)
    expect(actionCalls).toHaveLength(2)
    for (const [url, init] of actionCalls as unknown as Array<[RequestInfo | URL, RequestInit]>) {
      expect(String(url)).toContain('/runs/JUDGE-NEW-CASE-1/cases/NEW-CASE-1/action')
      expect(new Headers(init.headers).get('Idempotency-Key')).toBe(idempotencyKey)
      expect(JSON.parse(String(init.body))).toEqual({ action: 'APPROVE', reason: 'Checker reviewed the synthetic evidence.' })
    }
    expect(screen.getByText('ANONYMOUS_PUBLIC_JUDGE · HUMAN_APPROVED')).toBeTruthy()
    expect(screen.getByText('sha256-case')).toBeTruthy()
  })

  it('labels new-input actions as simulated overrides and uses the NEW_INPUT case id', async () => {
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => '123e4567-e89b-42d3-a456-426614174001') })
    const { fetchMock } = renderPage('public', publicRun, simulatedOverrideResponse)

    fireEvent.click(screen.getByRole('button', { name: 'Đánh giá đầu vào mới' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('heading', { name: 'Override mô phỏng' })).toBeTruthy()
    expect(screen.getByText(/không phải phê duyệt production/i)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Thao tác mô phỏng'), { target: { value: 'REJECT' } })
    fireEvent.change(screen.getByLabelText('Lý do (bắt buộc, tối đa 500 ký tự)'), { target: { value: 'Challenge the synthetic auto outcome.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ghi nhận thao tác mô phỏng' }))

    await screen.findByText('HUMAN_REJECTED')
    const [url, init] = fetchMock.mock.calls[1] as unknown as [RequestInfo | URL, RequestInit]
    expect(String(url)).toContain('/runs/JUDGE-INPUT-1/cases/NEW_INPUT/action')
    expect(JSON.parse(String(init.body))).toEqual({ action: 'REJECT', reason: 'Challenge the synthetic auto outcome.' })
    expect(screen.getByText('Có — override mô phỏng')).toBeTruthy()
    expect(screen.getByText(/idempotency replay/i)).toBeTruthy()
  })

  it('records STOP only after completion and describes it as post-result, not cancellation', async () => {
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => '123e4567-e89b-42d3-a456-426614174002') })
    const { fetchMock } = renderPage('public', publicRun, stopActionResponse)

    fireEvent.click(screen.getByRole('button', { name: 'Verify → Escalation · 5 ca' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run 5 cases' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết NEW-CASE-1' }))
    fireEvent.change(screen.getByLabelText('Thao tác mô phỏng'), { target: { value: 'STOP' } })
    fireEvent.change(screen.getByLabelText('Lý do (bắt buộc, tối đa 500 ký tự)'), { target: { value: 'Stop follow-up simulation after this result.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ghi nhận thao tác mô phỏng' }))

    await screen.findByRole('heading', { name: 'STOPPED' })
    const [url, init] = fetchMock.mock.calls[1] as unknown as [RequestInfo | URL, RequestInit]
    expect(String(url)).toContain('/runs/JUDGE-NEW-CASE-1/cases/NEW-CASE-1/action')
    expect(JSON.parse(String(init.body))).toEqual({ action: 'STOP', reason: 'Stop follow-up simulation after this result.' })
    expect(screen.getByText('Đã ghi STOPPED cho mô phỏng sau kết quả này; run trước đó không bị hủy.')).toBeTruthy()
  })

})
