import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { AppShell } from '../components/AppShell'
import { DemoSession, RequireRole } from '../components/DemoActor'
import { api } from '../services/api/client'
import { createApiServices } from '../services/api'
import { ServicesProvider } from '../services/ServiceProvider'
import { PlanFormPage } from './PlanFormPage'
import { ResultPage } from './ResultPage'

function config(role: string) {
  const actor = `DEMO-${role}-01`
  sessionStorage.setItem('organization-demo-actor', actor)
  vi.spyOn(api, 'request').mockResolvedValue({ actor, roles: [role],
    actors: [{ id: actor, roles: [role] }], department: 'DEMO-DEPT-01', checker_id: 'DEMO-CHECKER-01' })
}
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear() })

it.each(['MAKER', 'CHECKER', 'ADMIN'])('shows server roles and role-specific navigation for %s', async role => {
  config(role)
  render(<MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<RequireRole role="MAKER"><p>Create allowed</p></RequireRole>} /></Route></Routes></MemoryRouter>)
  expect(await screen.findByLabelText(/Demo actor/)).toHaveValue(`DEMO-${role}-01`)
  expect(screen.queryByRole('link', { name: 'Hồ sơ mới' }) !== null).toBe(role === 'MAKER')
  expect(screen.queryByRole('link', { name: 'Review Queue' }) !== null).toBe(role === 'CHECKER')
  if (role !== 'MAKER') expect(screen.getByRole('alert')).toHaveTextContent('Không có quyền MAKER')
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
  render(<MemoryRouter><DemoSession><ServicesProvider services={services}><PlanFormPage /></ServicesProvider></DemoSession></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Điền đủ')
  for (const [label, value] of [['Tên chiến dịch', 'test'], ['Mục tiêu', 'Tiếp cận khách hàng mới'], ['Tóm tắt', 'Chiến lược quảng bá theo tuần'], ['Ngày bắt đầu', '2026-10-01'], ['Ngày kết thúc', '2026-10-31'], ['Ngân sách', '50000000']]) {
    fireEvent.change(screen.getByLabelText(new RegExp(label)), { target: { value } })
  }
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByRole('alert')).toHaveTextContent('không dùng test')
  fireEvent.change(screen.getByLabelText(/Tên chiến dịch/), { target: { value: 'Chiến dịch tháng mười' } })
  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByRole('alert')).toHaveTextContent('lớn hơn 0')
  fireEvent.change(screen.getByLabelText(/Ngân sách/), { target: { value: '50000000' } })
  fireEvent.change(screen.getByLabelText(/Ngày kết thúc/), { target: { value: '2026-09-30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gửi duyệt' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Ngày kết thúc')
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
  if (variant === 'HUMAN_REVIEW') expect(screen.getByText('Chờ Checker · chưa có quyết định cuối')).toBeVisible()
  else expect(screen.getByRole('heading', { name: 'Quyết định cuối cùng' })).toBeVisible()
})
