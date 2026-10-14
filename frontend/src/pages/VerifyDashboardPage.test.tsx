import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { VerifyDashboardPage } from './VerifyDashboardPage'

const run = {
  run_id: 'JUDGE-NEW-CASE-1', suite: 'escalation', status: 'COMPLETED', mode: 'MOCK',
  data_classification: 'SYNTHETIC', started_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:00:02Z', duration_ms: 2000,
  summary: { total_cases: 1, passed_cases: 1, failed_cases: 0, error_cases: 0 },
  rows: [{
    case_id: 'NEW-CASE-1', case_name: 'Synthetic uncertainty case', status: 'PASS', passed: true,
    expected_action: 'HUMAN_REVIEW_REQUIRED', expected_category: 'FACT_UNCERTAIN',
    actual_action: 'HUMAN_REVIEW_REQUIRED', actual_category: 'FACT_UNCERTAIN',
    started_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:00:02Z', duration_ms: 2000,
    reason: 'OCR evidence conflicts with the submitted budget.',
    questions: [{ category: 'FACT_UNCERTAIN', question: 'Which submitted budget value is supported by the source document?', evidence_references: ['attachment:vendor-quote'] }],
    evidence: [], applied_rule_ids: [], audit: [{
      event_id: 'AUDIT-1', action: 'ENGINE_ROUTED', timestamp: '2026-10-09T10:00:02Z',
      input_sha256: 'sha256-fixture', reason: 'OCR evidence conflicts with the submitted budget.',
    }],
  }],
}

function renderPage() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(run), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)
  render(<MemoryRouter><VerifyDashboardPage /></MemoryRouter>)
  return fetchMock
}

describe('Judge Verify dashboard', () => {
  it('shows one first-use instruction for the first Verify action', () => {
    renderPage()

    expect(screen.getByText('Bước đầu tiên: bấm “Run 4 cases” để chạy Verify chung.')).toBeTruthy()
    expect(document.querySelector('.verify-first-use')?.tagName).toBe('P')
  })

  it('offers the four-case general run and five-case escalation run', () => {
    renderPage()

    expect(screen.getByRole('button', { name: /Verify chung.*4 ca/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Bộ hồi quy tổng hợp/i })).toBeNull()
    expect(screen.getByText(/Catalog tham chiếu có 15 ca tổng hợp/i)).toBeTruthy()
  })

  it('runs the selected suite and shows the specific escalation question', async () => {
    const fetchMock = renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run.*5/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(fetchMock.mock.calls[0][0]).toContain('/public/judge/runs')
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ suite: 'escalation' })
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết NEW-CASE-1' }))

    expect(screen.getByText('Which submitted budget value is supported by the source document?')).toBeTruthy()
    expect(screen.getByText('attachment:vendor-quote')).toBeTruthy()
    expect(screen.getAllByText('FACT_UNCERTAIN').length).toBeGreaterThan(0)
    expect(screen.getByText('Audit events')).toBeTruthy()
    expect(screen.getByText(/Action: ENGINE_ROUTED.*Input SHA-256: sha256-fixture.*Reason:/)).toBeTruthy()
  })

  it('provides a structured new-input form and warns against confidential data', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Thử một bộ dữ liệu có cấu trúc' })).toBeTruthy()
    expect(screen.getByText(/không nhập dữ liệu cá nhân hoặc bí mật/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Đánh giá đầu vào mới/i })).toBeTruthy()
    expect(screen.queryByRole('link', { name: /đăng nhập|tạo tài khoản/i })).toBeNull()
  })
})
