import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthenticatedVerifyPage } from './AuthenticatedVerifyPage'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { VerifyRun } from '../services/authWorkflow'

function makeRun(status: VerifyRun['status'] = 'COMPLETED'): VerifyRun {
  return {
    run_id: 'VERIFY-1234', suite: 'competition', suite_version: 'VERIFY-1.0', status,
    environment: 'SYNTHETIC_TEST', provider_mode: 'MOCK_VLM (external calls disabled)',
    timezone: 'Asia/Ho_Chi_Minh', started_at: '2026-10-15T01:00:00Z', completed_at: '2026-10-15T01:00:04Z',
    duration_ms: 4000, commit_sha: null, configuration: {}, current_case_id: null,
    completed_cases: 4, passed_cases: 4, failed_cases: 0,
    rows: ['TC01', 'TC02', 'TC03', 'TC04'].map((caseId, index) => ({
      case_id: caseId,
      case_name: `Synthetic case ${caseId}`,
      input: { plan: { budget_minor_units: String((index + 3) * 1_000_000) } },
      status: 'PASS',
      expected: { outcome: index === 0 ? 'AUTO_APPROVED' : index === 2 ? 'AUTO_REJECTED' : 'HUMAN_REVIEW_REQUIRED' },
      actual: {
        decision: { outcome: index === 0 ? 'AUTO_APPROVED' : index === 2 ? 'AUTO_REJECTED' : 'HUMAN_REVIEW_REQUIRED' },
        decision_source: index === 2 ? 'SYSTEM_AUTO_REJECT' : undefined,
        evaluation: { status: 'SUCCEEDED' },
        audit: [{ action: index === 0 ? 'AUTO_APPROVED' : index === 2 ? 'AUTO_REJECTED' : 'ENGINE_ROUTED' }],
      },
      assertions: [{ name: 'audit_actions', expected: ['PLAN_SUBMITTED'], actual: ['PLAN_SUBMITTED'], passed: true }],
      reason: null,
      started_at: '2026-10-15T01:00:00Z',
      completed_at: '2026-10-15T01:00:01Z',
      duration_ms: 1000,
    })),
  }
}

function renderPage() {
  return render(<MemoryRouter><AuthenticatedVerifyPage /></MemoryRouter>)
}

afterEach(() => vi.restoreAllMocks())

describe('AuthenticatedVerifyPage', () => {
  it('restores the latest actual report and exposes all four cases and the mock labels', async () => {
    vi.spyOn(authWorkflowService, 'getLatestVerifyRun').mockResolvedValue(makeRun())
    vi.spyOn(authWorkflowService, 'getVerifyRun').mockResolvedValue(makeRun())
    renderPage()

    expect(await screen.findByText('VERIFY-1234')).toBeTruthy()
    expect(screen.getByText('Chỉ dữ liệu tổng hợp')).toBeTruthy()
    expect(screen.getByText(/Mock VLM · không gọi dịch vụ AI ngoài/)).toBeTruthy()
    for (const caseId of ['TC01', 'TC02', 'TC03', 'TC04']) expect(screen.getByText(caseId)).toBeTruthy()
    expect(screen.getByText(/AUTO_REJECTED · Hệ thống tự từ chối \(fixture Verify\)/)).toBeTruthy()
    expect(screen.getByText('Nguồn quyết định: SYSTEM_AUTO_REJECT')).toBeTruthy()
    expect(screen.getByText('4 / 4 PASS · 0 FAIL')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'mở Verify runbook' })).toBeTruthy()
  })

  it('starts one idempotent run and downloads its JSON report', async () => {
    vi.spyOn(authWorkflowService, 'getLatestVerifyRun').mockRejectedValue(new AuthApiError(404, 'No Verify run is available.'))
    const start = vi.spyOn(authWorkflowService, 'startVerifyRun').mockResolvedValue(makeRun())
    vi.spyOn(authWorkflowService, 'downloadVerifyReport').mockResolvedValue(new Blob(['{}'], { type: 'application/json' }))
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:verify-report')
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Chạy kiểm thử' }))
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
    expect(start.mock.calls[0][0]).toMatch(/^verify-/)
    fireEvent.click(await screen.findByRole('button', { name: 'Tải báo cáo JSON' }))
    await waitFor(() => expect(authWorkflowService.downloadVerifyReport).toHaveBeenCalledWith('VERIFY-1234'))
  })
})
