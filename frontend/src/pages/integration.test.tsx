import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { ServicesProvider } from '../services/ServiceProvider'
import { createApiServices } from '../services/api'
import { PlansPage } from './PlansPage'
import { ReviewQueuePage } from './ReviewQueuePage'

it('renders list loading, network error and empty state', async () => {
  const services = createApiServices()
  let reject!: (error: Error) => void
  services.plan.listPlans = vi.fn(() => new Promise<import('../types').PlanView[]>((_, r) => { reject = r }))
  render(<MemoryRouter><ServicesProvider services={services}><PlansPage /></ServicesProvider></MemoryRouter>)
  expect(screen.getByRole('status')).toHaveTextContent('Đang tải')
  reject(new Error('Network unavailable'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable')
})

it('keeps Checker conflict visible and sends explicit override reason', async () => {
  const services = createApiServices()
  services.review.listPendingReviews = vi.fn().mockResolvedValue([{ planId: 'p', title: 'Review campaign' }])
  services.review.getReview = vi.fn().mockResolvedValue({ planId: 'p', title: 'Review campaign', revision: 1 })
  services.review.decide = vi.fn().mockResolvedValue({ status: 'STALE', message: 'Stale revision: reload' })
  render(<MemoryRouter><ServicesProvider services={services}><ReviewQueuePage /></ServicesProvider></MemoryRouter>)
  fireEvent.click(await screen.findByText('Review campaign'))
  fireEvent.change(await screen.findByLabelText(/Lý do override/), { target: { value: 'Reviewed factual evidence' } })
  fireEvent.change(screen.getByLabelText(/^Lý do \*$/), { target: { value: 'Approved after review' } })
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận' }))
  await waitFor(() => expect(services.review.decide).toHaveBeenCalledWith('p', expect.objectContaining({ overrideReason: 'Reviewed factual evidence' }), expect.objectContaining({ expectedRevision: 1 })))
  expect(await screen.findByRole('alert')).toHaveTextContent('Stale revision')
  expect(screen.queryByRole('button', { name: 'Request Changes' })).toBeNull()
})
