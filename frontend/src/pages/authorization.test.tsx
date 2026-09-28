import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { AppShell } from '../components/AppShell'
import { DemoSession } from '../components/DemoActor'
import { api } from '../services/api/client'
import { createApiServices } from '../services/api'
import { ServicesProvider } from '../services/ServiceProvider'
import { SessionProvider } from '../services/SessionProvider'
import { PlanFormPage } from './PlanFormPage'
import { ResultPage } from './ResultPage'

function config(role: string) {
  const actor = `DEMO-${role}-01`
  sessionStorage.setItem('organization-demo-actor', actor)
  vi.spyOn(api, 'request').mockResolvedValue({ actor, roles: [role],
    actors: [{ id: actor, roles: [role] }], environment: 'demo', department: 'DEMO-DEPT-01', checker_id: 'DEMO-CHECKER-01', currency: 'VND', provider: 'MOCK_VLM', mock_mode: 'pass',
    policy: { policy: { allowed_media_types: ['image/png', 'image/jpeg', 'image/webp'], max_attachment_bytes: 5000000 } }, capabilities: { stop: false, retry_evaluation: false, request_changes: false } })
}
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear() })

it.each(['MAKER', 'CHECKER', 'ADMIN'])('shows server roles and role-specific navigation for %s', async role => {
  config(role)
  render(<MemoryRouter><SessionProvider><Routes><Route element={<AppShell />}><Route index element={<p>Workspace</p>} /></Route></Routes></SessionProvider></MemoryRouter>)
  expect(await screen.findByLabelText(/Demo actor/)).toHaveValue(`DEMO-${role}-01`)
  expect(screen.queryByRole('link', { name: 'Tạo kế hoạch' }) !== null).toBe(role === 'MAKER')
  expect(screen.queryByRole('link', { name: 'Chờ tôi duyệt' }) !== null).toBe(role === 'CHECKER')
})

it('fails closed when the identity cannot be loaded', async () => {
  vi.spyOn(api, 'request').mockRejectedValue(new Error('Phiên demo không hợp lệ'))
  render(<DemoSession><button>Protected action</button></DemoSession>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Phiên demo không hợp lệ')
  expect(screen.queryByText('Protected action')).toBeNull()
})

it('explains required inputs and rejects placeholders, zero budget and reversed dates before mutation', async () => {
  config('MAKER')
  const services = createApiServices()
  services.plan.saveDraft = vi.fn()
  render(<MemoryRouter><SessionProvider><ServicesProvider services={services}><PlanFormPage /></ServicesProvider></SessionProvider></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getAllByText('Trường này bắt buộc khi gửi duyệt.').length).toBeGreaterThan(0)
  for (const [label, value] of [['Tên chiến dịch', 'test'], ['Mục tiêu', 'Tiếp cận khách hàng mới'], ['Tóm tắt', 'Chiến lược quảng bá theo tuần'], ['Ngày bắt đầu', '2026-10-01'], ['Ngày kết thúc', '2026-10-31'], ['Ngân sách', '50000000']]) {
    fireEvent.change(screen.getByLabelText(new RegExp(label)), { target: { value } })
  }
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByRole('alert')).toHaveTextContent('nội dung mẫu')
  fireEvent.change(screen.getByLabelText(/Tên chiến dịch/), { target: { value: 'Chiến dịch tháng mười' } })
  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByText('Ngân sách phải lớn hơn 0 khi gửi duyệt.')).toBeVisible()
  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: '50000000' } })
  fireEvent.change(screen.getByLabelText(/Ngày kết thúc/), { target: { value: '2026-09-30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByText('Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.')).toBeVisible()
  expect(services.plan.saveDraft).not.toHaveBeenCalled()
})

it.each(['HUMAN_REVIEW', 'HUMAN_DECISION'] as const)('separates AI recommendation and final decision: %s', async variant => {
  const services = createApiServices()
  services.plan.getResult = vi.fn().mockResolvedValue({ planId: 'p', title: 'Campaign', variant,
    statusLabel: variant === 'HUMAN_REVIEW' ? 'PENDING_APPROVAL' : 'APPROVED',
    decisionSource: variant === 'HUMAN_DECISION' ? 'CHECKER' : undefined,
    evidence: [{ id: 'recommendation', label: 'Khuyến nghị AI (không phải quyết định cuối)', value: 'RECOMMEND_AUTO_APPROVAL' }] })
  render(<MemoryRouter><ServicesProvider services={services}><ResultPage /></ServicesProvider></MemoryRouter>)
  expect(await screen.findByText('Khuyến nghị AI (không phải quyết định cuối)')).toBeVisible()
  if (variant === 'HUMAN_REVIEW') expect(screen.getByText('Kế hoạch đang chờ người có thẩm quyền thẩm định.')).toBeVisible()
  else expect(screen.getByText('CHECKER')).toBeVisible()
})
