import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { authService } from '../services/auth'
import { AccountHandoverPage } from './AccountHandoverPage'

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

it('reads the one-time token from the URL fragment and removes it from browser history', async () => {
  const user = userEvent.setup()
  window.history.replaceState(null, '', '/activate#token=synthetic-handover-token')
  const complete = vi.spyOn(authService, 'completeAccountHandover').mockResolvedValue(undefined)
  render(<MemoryRouter initialEntries={['/activate']}><AccountHandoverPage /></MemoryRouter>)

  expect(window.location.hash).toBe('')
  await user.type(screen.getByLabelText('Mật khẩu mới'), 'Recipient-chosen-password-123!')
  await user.type(screen.getByLabelText('Nhập lại mật khẩu'), 'Recipient-chosen-password-123!')
  await user.click(screen.getByRole('button', { name: 'Lưu mật khẩu' }))

  expect(complete).toHaveBeenCalledWith('synthetic-handover-token', 'Recipient-chosen-password-123!')
  expect(await screen.findByRole('heading', { name: 'Mật khẩu đã được cập nhật' })).toBeVisible()
})
