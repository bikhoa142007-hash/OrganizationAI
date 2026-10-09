import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { VerifyDashboardPage } from './VerifyDashboardPage'
import { ServicesProvider } from '../services/ServiceProvider'
import type { FrontendServices } from '../services/interfaces'
import type { VerifyRun } from '../types'

const run: VerifyRun = {
  runId: 'verify-run-1',
  suite: 'general',
  status: 'COMPLETED',
  startedAt: '2026-10-09T10:00:00Z',
  completedAt: '2026-10-09T10:00:02Z',
  dataSource: 'API',
  rows: [{
    caseId: 'NEW-CASE-1',
    caseName: 'Synthetic uncertainty case',
    expectedAction: 'HUMAN_REVIEW_REQUIRED',
    expectedCategory: 'FACT_UNCERTAIN',
    actualAction: 'HUMAN_REVIEW_REQUIRED',
    actualCategory: 'FACT_UNCERTAIN',
    generatedQuestion: [{ category: 'FACT_UNCERTAIN', question: 'Which submitted budget value is supported by the source document?', evidenceReferences: ['attachment:vendor-quote'] }],
    status: 'PASS',
    pass: true,
    reason: 'OCR evidence conflicts with the submitted budget.',
    startedAt: '2026-10-09T10:00:00Z',
    completedAt: '2026-10-09T10:00:02Z',
  }],
  summary: { totalCases: 1, completedCases: 1, passedCases: 1, failedCases: 0, errorCases: 0, progressPercent: 100 },
}

function renderPage() {
  const startRun = vi.fn().mockResolvedValue(run)
  const services = { verify: { startRun, getRun: vi.fn() } } as unknown as FrontendServices
  render(<MemoryRouter><ServicesProvider services={services}><VerifyDashboardPage /></ServicesProvider></MemoryRouter>)
  return startRun
}

describe('Judge Verify dashboard', () => {
  it('offers the four-case general run, five-case escalation run, and separate 15-case regression catalog', () => {
    renderPage()

    expect(screen.getByRole('button', { name: /Verify chung.*4 ca/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Bộ hồi quy tổng hợp.*15 ca/i })).toBeTruthy()
  })

  it('runs the selected suite and shows the specific escalation question', async () => {
    const startRun = renderPage()

    fireEvent.click(screen.getByRole('button', { name: /Verify → Escalation.*5 ca/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run.*5/i }))

    await waitFor(() => expect(startRun).toHaveBeenCalledWith('escalation'))
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết NEW-CASE-1' }))

    expect(screen.getByText('Which submitted budget value is supported by the source document?')).toBeTruthy()
    expect(screen.getByText('attachment:vendor-quote')).toBeTruthy()
    expect(screen.getAllByText('FACT_UNCERTAIN').length).toBeGreaterThan(0)
  })

  it('guides judges to enter a new synthetic plan through the isolated demo workflow', () => {
    renderPage()

    expect(screen.getByRole('link', { name: /nhập kế hoạch tổng hợp mới/i }).getAttribute('href')).toBe('/demo/plans/new')
    expect(screen.getByText(/không phải inference thật/i)).toBeTruthy()
  })
})
