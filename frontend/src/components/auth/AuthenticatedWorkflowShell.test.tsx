import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './RequireAuth'
import { AuthenticatedWorkflowShell } from './AuthenticatedWorkflowShell'
import { AuthProvider } from '../../context/AuthContext'
import { authService } from '../../services/auth'

const maker = {
  id: 'maker-1', user_code: 'USR-MAKER', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Maker One', status: 'ACTIVE' as const, roles: ['MAKER'],
}

function renderShell() {
  return render(<MemoryRouter initialEntries={['/workflow/plans']}>
    <AuthProvider>
      <Routes>
        <Route path="/workflow/plans" element={<RequireAuth><AuthenticatedWorkflowShell /></RequireAuth>}>
          <Route index element={<h1>Kế hoạch của tôi</h1>} />
        </Route>
      </Routes>
    </AuthProvider>
  </MemoryRouter>)
}

afterEach(() => vi.restoreAllMocks())

it('keeps keyboard focus inside the open navigation drawer and restores it on close', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  const { container } = renderShell()

  expect(await screen.findByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
  const toggle = screen.getByRole('button', { name: 'Mở menu điều hướng' })
  await user.click(toggle)

  const firstLink = screen.getByRole('link', { name: 'Tổng quan' })
  const lastLink = screen.getByRole('link', { name: 'Tài khoản' })
  const brandLink = screen.getByRole('link', { name: /OrganizationAI/ })
  expect(firstLink).toHaveFocus()
  expect(toggle).toHaveAttribute('aria-expanded', 'true')

  lastLink.focus()
  fireEvent.keyDown(document, { key: 'Tab' })
  expect(brandLink).toHaveFocus()

  brandLink.focus()
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
  expect(lastLink).toHaveFocus()

  await user.keyboard('{Escape}')
  expect(toggle).toHaveFocus()
  expect(toggle).toHaveAttribute('aria-expanded', 'false')

  await user.click(toggle)
  fireEvent.click(container.querySelector('.auth-workflow-sidebar-scrim')!)
  expect(toggle).toHaveFocus()
})
