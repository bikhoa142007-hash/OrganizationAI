import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
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
    started_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:00:02Z', duration_ms: 2000,
    reason: 'OCR evidence conflicts with the submitted budget.',
    questions: [{ category: 'FACT_UNCERTAIN', question: 'Which submitted budget value is supported by the source document?', evidence_references: ['attachment:vendor-quote'] }],
    evidence: [], applied_rule_ids: [], audit: [{
      event_id: 'AUDIT-1', action: 'ENGINE_ROUTED', timestamp: '2026-10-09T10:00:02Z',
      input_sha256: 'sha256-fixture', reason: 'OCR evidence conflicts with the submitted budget.',
    }],
  }],
}

function renderPage(mode: 'demo' | 'public' = 'demo') {
  const startRun = vi.fn().mockResolvedValue(demoRun)
  const services = { verify: { startRun, getRun: vi.fn() } } as unknown as FrontendServices
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(publicRun), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)
  render(<MemoryRouter><ServicesProvider services={services}><VerifyDashboardPage mode={mode} /></ServicesProvider></MemoryRouter>)
  return { fetchMock, startRun }
}

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
    expect(screen.getByText(/không nhập dữ liệu cá nhân hoặc bí mật/i)).toBeTruthy()
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

})
