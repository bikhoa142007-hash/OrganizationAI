import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { test, expect, type Page } from '@playwright/test'
import { resolve } from 'node:path'

const apiBaseValue = process.env.VITE_API_BASE_URL
const password = process.env.AUTH_SEED_PASSWORD
const clockFile = process.env.SLA_TEST_CLOCK_FILE
const apiContainer = process.env.SLA_TEST_API_CONTAINER
const clockFileInApi = process.env.SLA_TEST_CLOCK_CONTAINER_FILE ?? '/sla-test/clock.json'
const workerScriptInApi = process.env.SLA_TEST_WORKER_SCRIPT ?? '/workspace/scripts/run_sla_clocked_worker.py'
if (!apiBaseValue || !password || !clockFile || !apiContainer) {
  throw new Error('Set VITE_API_BASE_URL, AUTH_SEED_PASSWORD, SLA_TEST_CLOCK_FILE, and SLA_TEST_API_CONTAINER for SLA browser acceptance.')
}
const apiBase = apiBaseValue.replace(/\/$/, '')
const image = resolve(import.meta.dirname, '../../tests/fixtures/ba/v2.1/images/creative-pass.png')
const initialClock = new Date().toISOString()
const authenticatedPages = new WeakSet<Page>()

type SlaRound = {
  version_number: number
  round_number: number
  applicable: boolean
  status: string
  configuration_revision: number | null
  duration_minutes: number | null
  warning_before_minutes: number | null
  started_at: string | null
  warning_at: string | null
  due_at: string | null
  closed_at: string | null
}

type LivePlan = {
  id: string
  code: string
  status: string
  processing_stage: string
  current_version: number
  current_round: number
  versions: Array<{ version_number: number; round_number: number; payload: { summary: string } }>
  ai_evaluations: Array<{ provider?: string }>
  sla_current: SlaRound | null
  sla_history: SlaRound[]
  history: Array<{ action: string }>
}

type LiveNotification = {
  event_type: string
  plan_id: string
  plan_code: string
  round_number: number
  title: string
}

async function login(page: Page, username: string, destination: string) {
  await page.goto('/login')
  await page.getByLabel('Tên đăng nhập, mã người dùng hoặc email').fill(username)
  await page.locator('#login-password').fill(password)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page).toHaveURL(new RegExp(`${destination.replaceAll('/', '\\/')}$`))
  authenticatedPages.add(page)
}

async function readPlan(page: Page, planId: string): Promise<LivePlan> {
  return page.evaluate(async ({ base, id }) => {
    const response = await fetch(`${base}/workflow/plans/${encodeURIComponent(id)}`, { credentials: 'include' })
    if (!response.ok) throw new Error(`Plan reload failed: HTTP ${response.status}`)
    return await response.json() as LivePlan
  }, { base: apiBase, id: planId })
}

async function waitForReview(page: Page, planId: string): Promise<LivePlan> {
  const end = Date.now() + 120_000
  let current = await readPlan(page, planId)
  while (Date.now() < end) {
    if (current.status === 'PENDING_APPROVAL' && current.processing_stage === 'HUMAN_REVIEW_REQUIRED'
      && current.ai_evaluations.length > 0) return current
    await page.waitForTimeout(500)
    current = await readPlan(page, planId)
  }
  throw new Error('Mock evaluation did not reach persisted human review within two minutes.')
}

async function readNotifications(page: Page): Promise<LiveNotification[]> {
  return page.evaluate(async base => {
    const response = await fetch(`${base}/workflow/notifications?offset=0&limit=100`, { credentials: 'include' })
    if (!response.ok) throw new Error(`Notification reload failed: HTTP ${response.status}`)
    const body = await response.json() as { items: LiveNotification[] }
    return body.items
  }, apiBase)
}

function setClock(value: string) {
  writeFileSync(clockFile, `${JSON.stringify({ now: value })}\n`, { encoding: 'utf8' })
}

function stableSlaHistory(entry: NonNullable<SlaRound['sla_current']>) {
  return Object.fromEntries(Object.entries(entry).filter(([key]) => key !== 'seconds_until_due'))
}

function localDateTime(minutesAgo: number): string {
  const date = new Date(Date.now() - minutesAgo * 60_000)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function runWorker(): number {
  const result = execFileSync('docker', [
    'exec', '-e', `SLA_TEST_CLOCK_FILE=${clockFileInApi}`, apiContainer,
    'python', workerScriptInApi,
  ], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim()
  const match = result.match(/^notifications_created=(\d+)$/m)
  if (!match) throw new Error(`Temporary SLA worker returned an unexpected result: ${result.slice(0, 200)}`)
  return Number(match[1])
}

test('Admin configures SLA; Maker submits, Checker receives reminders, decides late, and resubmission retains round history', async ({ browser }) => {
  const adminContext = await browser.newContext()
  const makerContext = await browser.newContext()
  const checkerContext = await browser.newContext()
  const admin = await adminContext.newPage()
  const maker = await makerContext.newPage()
  const checker = await checkerContext.newPage()
  const pageErrors: string[] = []
  for (const page of [admin, maker, checker]) {
    page.on('pageerror', error => pageErrors.push(error.message))
    page.on('console', message => {
      if (message.type() !== 'error') return
      // The unauthenticated /auth/me probe on a fresh login page is expected to return 401.
      if (!authenticatedPages.has(page) && /401 \(Unauthorized\)/.test(message.text())) return
      pageErrors.push(message.text())
    })
  }

  try {
    setClock(initialClock)

    await login(admin, 'admin', '/workflow/plans')
    await login(checker, 'checker', '/workflow/reviews')
    const checkerId = await checker.evaluate(async base => {
      const response = await fetch(`${base}/auth/me`, { credentials: 'include' })
      if (!response.ok) throw new Error(`Could not identify the signed-in Checker (HTTP ${response.status}).`)
      const body = await response.json() as { user?: { id?: string; roles?: string[] } }
      const user = body.user
      if (!user?.id || !user.roles?.includes('CHECKER')) throw new Error('The seeded checker account is not an eligible Checker.')
      return user.id
    }, apiBase)
    await admin.goto('/workflow/configuration')
    await admin.getByLabel('Loại cấu hình').selectOption('checker_assignment')
    await admin.getByLabel('Giá trị JSON').fill(JSON.stringify({
      maker_may_select_other: false,
      defaults: [{ department: 'Marketing', checker_id: checkerId }],
    }, null, 2))
    await admin.getByLabel(/Hiệu lực từ thời điểm/).fill(localDateTime(1))
    await admin.getByLabel('Lý do thay đổi').fill('Synthetic PostgreSQL SLA browser default Checker assignment.')
    await admin.getByRole('button', { name: 'Tạo revision bất biến' }).click()
    await expect(admin.getByRole('status').filter({ hasText: 'Đã tạo revision' })).toBeVisible()

    await admin.goto('/workflow/sla')
    await expect(admin.getByRole('heading', { name: 'Cấu hình SLA duyệt' })).toBeVisible()
    await expect(admin.locator('.sla-config-state')).toHaveText('Chưa có cấu hình được lưu · SLA đang tắt')
    await admin.getByLabel('Bật SLA cho vòng duyệt mới').check()
    const duration = admin.getByRole('group', { name: 'Thời hạn' })
    const warning = admin.getByRole('group', { name: 'Cảnh báo trước hạn' })
    await duration.getByLabel('Giờ').fill('0')
    await duration.getByLabel('Phút').fill('2')
    await warning.getByLabel('Giờ').fill('0')
    await warning.getByLabel('Phút').fill('1')
    await admin.getByLabel('Lý do thay đổi').fill('Temporary PostgreSQL SLA browser acceptance configuration.')
    await admin.getByRole('button', { name: 'Lưu revision' }).click()
    await expect(admin.getByRole('status')).toContainText('revision 1')
    await expect(admin.locator('.sla-config-state')).toContainText('Revision 1 · Đang bật')

    await login(maker, 'maker', '/workflow/plans')
    await expect(maker.getByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
    await maker.getByRole('link', { name: 'Tạo kế hoạch' }).click()
    const title = `Temporary SLA browser ${new Date().toISOString()}`
    await maker.getByLabel('Tên kế hoạch').fill(title)
    const checkerSelect = maker.getByLabel('Người phê duyệt')
    await checkerSelect.selectOption(checkerId)
    await maker.getByRole('button', { name: 'Lưu bản nháp' }).click()
    await expect(maker.getByRole('heading', { name: title, exact: true })).toBeVisible()
    await maker.getByRole('link', { name: 'Chỉnh sửa và gửi lại' }).click()
    await maker.getByRole('textbox', { name: 'Mục tiêu', exact: true }).fill('Measure qualified product trial registrations.')
    await maker.getByLabel('Bộ phận').fill('Marketing')
    await maker.getByLabel('Ngày bắt đầu').fill('2026-11-01')
    await maker.getByLabel('Ngày kết thúc').fill('2026-11-30')
    await maker.getByLabel('Ngân sách (đơn vị nhỏ nhất)').fill('50000000')
    await maker.getByLabel('Đối tượng mục tiêu').fill('Opted-in customers aged 25 to 40.')
    const originalSummary = 'Temporary SLA browser round one summary.'
    await maker.getByLabel('Tóm tắt chiến lược').fill(originalSummary)
    await maker.getByLabel('KPI kỳ vọng').fill('Count verified product trial registrations.')
    await maker.getByLabel('Kênh triển khai').fill('social, in-store demo')
    await maker.getByLabel('Ghi chú').fill('Temporary PostgreSQL SLA browser acceptance; Mock VLM is used.')
    await maker.getByLabel('Chọn ảnh đính kèm').setInputFiles(image)
    const planId = new URL(maker.url()).pathname.split('/').filter(Boolean).at(-2)
    expect(planId).toMatch(/^[0-9a-f-]{36}$/i)
    const submitStartedAt = Date.now()
    await maker.getByRole('button', { name: 'Gửi duyệt' }).click()
    await maker.waitForURL(new RegExp(`/workflow/plans/${planId}$`), { timeout: 120_000 })

    let roundOne = await waitForReview(maker, planId!)
    expect(roundOne.current_version).toBe(1)
    expect(roundOne.current_round).toBe(1)
    expect(roundOne.sla_current).toMatchObject({ applicable: true, status: 'IN_PROGRESS', configuration_revision: 1, duration_minutes: 2, warning_before_minutes: 1 })
    // The API timestamps rounds with UTC wall time; the mounted clock file controls only the SLA worker.
    const roundStartedAt = Date.parse(roundOne.sla_current!.started_at!)
    expect(roundStartedAt).toBeGreaterThanOrEqual(submitStartedAt - 30_000)
    expect(roundStartedAt).toBeLessThanOrEqual(Date.now() + 30_000)
    expect(roundOne.ai_evaluations[0].provider).toBe('MOCK_VLM')
    expect(roundOne.sla_history).toHaveLength(1)
    await expect(maker.locator('.workflow-sla-status')).toHaveText('Đang trong hạn')

    await checker.goto(`/workflow/plans/${planId}`)
    await expect(checker.getByRole('heading', { name: title, exact: true })).toBeVisible()
    await expect(checker.locator('.workflow-sla-status')).toHaveText('Đang trong hạn')
    await expect(checker.locator('.workflow-sla-card')).toContainText('Cấu hình revision 1')

    const warningAt = Date.parse(roundOne.sla_current!.warning_at!)
    const dueAt = Date.parse(roundOne.sla_current!.due_at!)
    setClock(new Date(warningAt - 1).toISOString())
    roundOne = await readPlan(maker, planId!)
    expect(roundOne.sla_current?.status).toBe('IN_PROGRESS')
    expect(runWorker()).toBe(0)

    setClock(new Date(warningAt + 1).toISOString())
    roundOne = await readPlan(checker, planId!)
    expect(roundOne.sla_current?.status).toBe('WARNING')
    await checker.reload()
    await expect(checker.locator('.workflow-sla-status')).toHaveText('Sắp đến hạn')
    expect(runWorker()).toBe(1)
    const checkerWarning = (await readNotifications(checker)).filter(item => item.plan_id === planId && item.event_type === 'SLA_WARNING' && item.round_number === 1)
    expect(checkerWarning).toHaveLength(1)
    await checker.goto('/workflow/notifications')
    const warningCard = checker.locator('.auth-notification-card').filter({ hasText: roundOne.code }).filter({ hasText: 'Sắp đến hạn duyệt kế hoạch' })
    await expect(warningCard).toHaveCount(1)
    await warningCard.getByRole('link', { name: /Mở kế hoạch/ }).click()
    await expect(checker).toHaveURL(new RegExp(`/workflow/plans/${planId}$`))

    expect((await readPlan(maker, planId!)).sla_current?.status).toBe('WARNING')
    await checker.reload()
    await expect(checker.locator('.workflow-sla-status')).toHaveText('Sắp đến hạn')

    setClock(new Date(dueAt + 1).toISOString())
    expect((await readPlan(checker, planId!)).sla_current?.status).toBe('OVERDUE')
    roundOne = await readPlan(checker, planId!)
    await checker.reload()
    await expect(checker.locator('.workflow-sla-status')).toHaveText('Quá hạn')
    expect(runWorker()).toBe(2)
    const checkerOverdue = (await readNotifications(checker)).filter(item => item.plan_id === planId && item.event_type === 'SLA_OVERDUE' && item.round_number === 1)
    expect(checkerOverdue).toHaveLength(1)
    const makerOverdue = (await readNotifications(maker)).filter(item => item.plan_id === planId && item.event_type === 'SLA_OVERDUE' && item.round_number === 1)
    expect(makerOverdue).toHaveLength(1)
    expect(runWorker()).toBe(0)

    await checker.getByLabel('Lý do override AI').fill('Temporary acceptance: checker inspected the version-one snapshot.')
    await checker.getByLabel('Lý do hoặc nhận xét').fill('Revise attribution details before approval.')
    await checker.getByRole('button', { name: 'Từ chối', exact: true }).click()
    await expect(checker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Đã từ chối')
    roundOne = await readPlan(checker, planId!)
    expect(roundOne.status).toBe('REJECTED')
    expect(roundOne.sla_current?.status).toBe('CLOSED_LATE')
    expect(Date.parse(roundOne.sla_current!.closed_at!)).toBeGreaterThanOrEqual(dueAt)

    await admin.goto('/workflow/sla')
    await expect(admin.locator('.sla-config-state')).toContainText('Revision 1 · Đang bật')
    await duration.getByLabel('Phút').fill('3')
    await warning.getByLabel('Phút').fill('1')
    await admin.getByLabel('Lý do thay đổi').fill('Increase the temporary acceptance round duration to three minutes.')
    await admin.getByRole('button', { name: 'Lưu revision' }).click()
    await expect(admin.getByRole('status')).toContainText('revision 2')
    const immutableRoundOne = await readPlan(admin, planId!)
    expect(stableSlaHistory(immutableRoundOne.sla_history[0])).toEqual(stableSlaHistory(roundOne.sla_history[0]!))
    expect(immutableRoundOne.sla_history[0]).toMatchObject({ configuration_revision: 1, duration_minutes: 2, status: 'CLOSED_LATE' })

    await maker.goto(`/workflow/plans/${planId}`)
    await expect(maker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Đã từ chối')
    await maker.getByRole('link', { name: 'Chỉnh sửa và gửi lại' }).click()
    const revisedSummary = 'Temporary SLA browser round two with explicit attribution details.'
    await maker.getByLabel('Tóm tắt chiến lược').fill(revisedSummary)
    await maker.getByLabel('Ghi chú').fill('The checker feedback is addressed in version two.')
    await maker.getByRole('button', { name: 'Gửi duyệt' }).click()
    const roundTwo = await waitForReview(maker, planId!)
    expect(roundTwo.current_version).toBe(2)
    expect(roundTwo.current_round).toBe(2)
    expect(roundTwo.versions.map(version => version.version_number)).toEqual([1, 2])
    expect(roundTwo.versions[0].payload.summary).toBe(originalSummary)
    expect(roundTwo.versions[1].payload.summary).toBe(revisedSummary)
    expect(roundTwo.sla_history).toHaveLength(2)
    expect(stableSlaHistory(roundTwo.sla_history[0])).toEqual(stableSlaHistory(roundOne.sla_history[0]!))
    expect(roundTwo.sla_current).toMatchObject({ applicable: true, status: 'IN_PROGRESS', configuration_revision: 2, duration_minutes: 3, warning_before_minutes: 1 })

    const roundTwoDue = Date.parse(roundTwo.sla_current!.due_at!)
    await expect.poll(async () => (await readPlan(checker, planId!)).sla_current?.status, {
      timeout: 180_000, intervals: [1_000],
    }).toBe('OVERDUE')
    setClock(new Date().toISOString())
    // Simulates worker recovery after downtime: first observation is overdue, so no stale warning is replayed.
    expect(runWorker()).toBe(2)
    const roundTwoCheckerNotices = (await readNotifications(checker)).filter(item => item.plan_id === planId && item.round_number === 2)
    const roundTwoMakerNotices = (await readNotifications(maker)).filter(item => item.plan_id === planId && item.round_number === 2)
    expect(roundTwoCheckerNotices.filter(item => item.event_type === 'SLA_WARNING')).toHaveLength(0)
    expect(roundTwoMakerNotices.filter(item => item.event_type === 'SLA_WARNING')).toHaveLength(0)
    expect(roundTwoCheckerNotices.filter(item => item.event_type === 'SLA_OVERDUE')).toHaveLength(1)
    expect(roundTwoMakerNotices.filter(item => item.event_type === 'SLA_OVERDUE')).toHaveLength(1)

    await checker.goto(`/workflow/plans/${planId}`)
    await expect(checker.locator('.workflow-sla-status')).toHaveText('Quá hạn')
    await checker.getByLabel('Lý do override AI').fill('Temporary acceptance: checker inspected the revised version-two snapshot.')
    await checker.getByLabel('Lý do hoặc nhận xét').fill('Approved after attribution details were clarified.')
    await checker.getByRole('button', { name: 'Phê duyệt', exact: true }).click()
    await expect(checker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Đã duyệt')
    const finalPlan = await readPlan(checker, planId!)
    expect(finalPlan.status).toBe('APPROVED')
    expect(finalPlan.sla_history.map(item => item.status)).toEqual(['CLOSED_LATE', 'CLOSED_LATE'])
    expect(finalPlan.sla_history[0].due_at).toBe(roundOne.sla_history[0].due_at)
    expect(finalPlan.sla_history[1].configuration_revision).toBe(2)
    expect(finalPlan.history.some(event => event.action === 'REJECTED')).toBe(true)
    expect(finalPlan.history.some(event => event.action === 'APPROVED')).toBe(true)
    await expect(checker.locator('.workflow-sla-history')).toContainText('Lịch sử SLA (2 vòng)')
    expect(pageErrors).toEqual([])
  } finally {
    await adminContext.close()
    await makerContext.close()
    await checkerContext.close()
  }
})
