import { test, expect, type Page } from '@playwright/test'
import { resolve } from 'node:path'

const password = process.env.AUTH_SEED_PASSWORD
const makerUsername = process.env.AUTH_E2E_MAKER_USERNAME ?? 'maker'
const checkerUsername = process.env.AUTH_E2E_CHECKER_USERNAME ?? 'checker'
const configuredApiBase = process.env.VITE_API_BASE_URL
if (!configuredApiBase) {
  throw new Error('Set VITE_API_BASE_URL explicitly before running the Auth E2E tests.')
}
const apiBase = configuredApiBase.replace(/\/$/, '')
const protectedPlanIds = new Set([
  'c0e31c28-aaca-4a29-b73c-ac50e1029b52',
  '79bba034-53a9-4fb2-b906-e9cee2d8b6b7',
  '0c50b0eb-d31c-40a8-8fdd-99bcaa083e62',
])
const image = resolve(import.meta.dirname, '../../tests/fixtures/ba/v2.1/images/creative-pass.png')

type LivePlan = {
  id: string
  status: string
  processing_stage: string
  current_version: number
  current_round: number
  versions: Array<{ version_number: number; round_number: number; payload: { summary: string } }>
  ai_evaluations: LiveEvaluation[]
  history: Array<{ action: string; details: Record<string, unknown> }>
}

type LiveEvaluation = {
  run_id?: string
  provider?: string
  status?: string
  version_number?: number
  round_number?: number
  model_id?: string | null
  model_version?: string | null
  visual_extraction?: { status?: string; model_id?: string | null; model_version?: string | null } | null
  media_evaluation?: { status?: string; model_id?: string | null; model_version?: string | null; prompt_version?: string | null; schema_version?: string | null } | null
  strategy_evaluation?: { status?: string; model_id?: string | null; model_version?: string | null; prompt_version?: string | null; schema_version?: string | null } | null
}

async function login(
  page: Page,
  username: string,
  expectedDestination: '/workflow/plans' | '/workflow/reviews',
  expectedRole: 'MAKER' | 'CHECKER',
) {
  await page.goto('/login')
  await page.getByLabel('Tên đăng nhập, mã người dùng hoặc email').fill(username)
  await page.locator('#login-password').fill(password!)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  const expectedUrl = new URL(expectedDestination, new URL(page.url()).origin).href
  await expect(page).toHaveURL(expectedUrl)

  const session = await page.evaluate(async base => {
    const response = await fetch(`${base}/auth/me`, { credentials: 'include' })
    const body = await response.json().catch(() => null) as {
      user?: { username?: string; roles?: string[] }
    } | null
    return {
      status: response.status,
      username: body?.user?.username ?? null,
      roles: body?.user?.roles ?? [],
    }
  }, apiBase)
  expect(session.status).toBe(200)
  expect(session.username).toBe(username)
  expect(session.roles).toEqual([expectedRole])
}

async function readPlan(page: Page, id: string): Promise<LivePlan> {
  return page.evaluate(async ({ base, planId }) => {
    const response = await fetch(`${base}/workflow/plans/${encodeURIComponent(planId)}`, { credentials: 'include' })
    if (!response.ok) throw new Error(`Could not reload the synthetic plan (HTTP ${response.status}: ${(await response.text()).slice(0, 240)}).`)
    return await response.json() as LivePlan
  }, { base: apiBase, planId: id })
}

async function waitForReview(page: Page, id: string): Promise<LivePlan> {
  const deadline = Date.now() + 180_000
  let plan = await readPlan(page, id)
  while (Date.now() < deadline) {
    if (plan.status === 'PENDING_APPROVAL' && plan.processing_stage === 'HUMAN_REVIEW_REQUIRED'
      && plan.ai_evaluations.length > 0) return plan
    await page.waitForTimeout(1_000)
    plan = await readPlan(page, id)
  }
  throw new Error('The submitted plan did not reach persisted Checker review within three minutes.')
}

test('live Auth Maker-to-Checker browser workflow preserves a rejected version through resubmission', async ({ browser }) => {
  test.skip(!password, 'Set AUTH_SEED_PASSWORD in the local test process to use the seeded local accounts.')
  const browserErrors: string[] = []
  const makerContext = await browser.newContext()
  const checkerContext = await browser.newContext()
  const maker = await makerContext.newPage()
  const checker = await checkerContext.newPage()
  maker.on('pageerror', error => browserErrors.push(error.message))
  checker.on('pageerror', error => browserErrors.push(error.message))

  try {
    await login(maker, makerUsername, '/workflow/plans', 'MAKER')
    await expect(maker.getByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
    let title: string
    let planId: string
    let firstRound: LivePlan
    const resumable = maker.locator('.auth-workflow-table tbody tr')
      .filter({ hasText: 'Synthetic local Auth browser ' })
      .filter({ hasText: 'Chờ duyệt' })
    const resumableCount = await resumable.count()
    if (resumableCount > 1) {
      const candidateIds = await resumable.evaluateAll(rows => rows.map(row => {
        const href = row.querySelector<HTMLAnchorElement>('td a')?.getAttribute('href')
        return href?.split('/').at(-1) ?? '<missing-id>'
      }))
      throw new Error(
        `Found ${resumableCount} pending synthetic plans; refusing to choose one: ${candidateIds.join(', ')}`,
      )
    }
    if (resumableCount === 1) {
      const row = resumable.first()
      const href = await row.locator('td a').getAttribute('href')
      expect(href).toBeTruthy()
      planId = href!.split('/').at(-1)!
      title = (await row.locator('td a strong').textContent()) ?? ''
      await maker.goto(`/workflow/plans/${planId}`)
      firstRound = await waitForReview(maker, planId)
    } else {
      await maker.getByRole('link', { name: 'Tạo kế hoạch' }).click()
      title = `Synthetic local Auth browser ${new Date().toISOString()}`
      await maker.getByLabel('Tên kế hoạch').fill(title)
      const checkerSelect = maker.getByLabel('Người phê duyệt')
      await expect(checkerSelect.locator('option').nth(1)).toBeAttached()
      await checkerSelect.selectOption({ index: 1 })
      await maker.getByRole('button', { name: 'Lưu bản nháp' }).click()
      await expect(maker.getByRole('heading', { name: title, exact: true })).toBeVisible()
      await expect(maker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Bản nháp')

      await maker.getByRole('link', { name: 'Chỉnh sửa và gửi lại' }).click()
      await maker.getByRole('textbox', { name: 'Mục tiêu', exact: true }).fill('Measure qualified product trial registrations.')
      await maker.getByLabel('Bộ phận').fill('Marketing')
      await maker.getByLabel('Ngày bắt đầu').fill('2026-11-01')
      await maker.getByLabel('Ngày kết thúc').fill('2026-11-30')
      await maker.getByLabel('Ngân sách (đơn vị nhỏ nhất)').fill('50000000')
      await maker.getByLabel('Đối tượng mục tiêu').fill('Opted-in customers aged 25 to 40.')
      await maker.getByLabel('Tóm tắt chiến lược').fill('Initial synthetic plan summary for version one.')
      await maker.getByLabel('KPI kỳ vọng').fill('Count verified product trial registrations.')
      await maker.getByLabel('Kênh triển khai').fill('social, in-store demo')
      await maker.getByLabel('Ghi chú').fill('Synthetic browser workflow; manual Checker review is expected.')
      await maker.getByLabel('Chọn ảnh đính kèm').setInputFiles(image)
      const formPath = new URL(maker.url()).pathname.split('/').filter(Boolean)
      planId = formPath.at(-2)!
      expect(planId).toMatch(/^[0-9a-f-]{36}$/i)
      await maker.getByRole('button', { name: 'Gửi duyệt' }).click()
      await maker.waitForURL(new RegExp(`/workflow/plans/${planId}$`), { timeout: 180_000 })
      firstRound = await waitForReview(maker, planId)
    }
    expect(protectedPlanIds.has(planId)).toBe(false)
    await expect(maker.getByRole('heading', { name: title, exact: true })).toBeVisible({ timeout: 180_000 })
    expect(firstRound.current_version).toBe(1)
    expect(firstRound.current_round).toBe(1)
    expect(firstRound.ai_evaluations).toHaveLength(1)
    const originalEvaluation = structuredClone(firstRound.ai_evaluations[0])
    const originalSummary = firstRound.versions[0].payload.summary

    await login(checker, checkerUsername, '/workflow/reviews', 'CHECKER')
    await expect(checker.getByRole('heading', { name: 'Kế hoạch chờ tôi duyệt' })).toBeVisible()
    await expect(checker.getByRole('link', { name: new RegExp(title) })).toBeVisible()
    await checker.goto(`/workflow/plans/${planId}`)
    await expect(checker.getByRole('heading', { name: title, exact: true })).toBeVisible()
    await checker.getByLabel('Lý do override AI').fill('Synthetic local review; Checker inspected the submitted snapshot.')
    await checker.getByRole('button', { name: 'Từ chối', exact: true }).click()
    await expect(checker.getByRole('alert')).toContainText('Nhập lý do từ chối')
    await checker.getByLabel('Lý do hoặc nhận xét').fill('Clarify how verified trials are attributed to the campaign.')
    await checker.getByRole('button', { name: 'Từ chối', exact: true }).click()
    await expect(checker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Đã từ chối')

    await maker.goto(`/workflow/plans/${planId}`)
    await expect(maker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Đã từ chối')
    await maker.getByRole('link', { name: 'Chỉnh sửa và gửi lại' }).click()
    const revisedSummary = 'Revised synthetic plan with an explicit attribution method and review checkpoint.'
    await maker.getByLabel('Tóm tắt chiến lược').fill(revisedSummary)
    await maker.getByLabel('Ghi chú').fill('The checker feedback is addressed in this second submitted version.')
    await maker.getByRole('button', { name: 'Gửi duyệt' }).click()
    const secondRound = await waitForReview(maker, planId)
    expect(secondRound.current_version).toBe(2)
    expect(secondRound.current_round).toBe(2)
    expect(secondRound.versions.map(version => version.version_number)).toEqual([1, 2])
    expect(secondRound.versions[0].payload.summary).toBe(originalSummary)
    expect(secondRound.versions[1].payload.summary).toBe(revisedSummary)
    expect(secondRound.ai_evaluations).toHaveLength(2)
    expect(secondRound.ai_evaluations[0]).toEqual(originalEvaluation)

    await checker.goto(`/workflow/plans/${planId}`)
    await expect(checker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Chờ duyệt')
    await checker.getByLabel('Lý do hoặc nhận xét').fill('The second submission addresses the requested attribution detail.')
    await checker.getByLabel('Lý do override AI').fill('Synthetic local review; Checker inspected the revised snapshot.')
    await checker.getByRole('button', { name: 'Phê duyệt', exact: true }).click()
    await expect(checker.locator('.auth-workflow-page-heading .workflow-status')).toHaveText('Đã duyệt')

    const finalPlan = await readPlan(checker, planId)
    expect(finalPlan.status).toBe('APPROVED')
    expect(finalPlan.versions.map(version => version.version_number)).toEqual([1, 2])
    expect(finalPlan.ai_evaluations).toHaveLength(2)
    expect(finalPlan.ai_evaluations[0]).toEqual(originalEvaluation)
    expect(finalPlan.history.some(event => event.action === 'REJECTED')).toBe(true)
    expect(finalPlan.history.some(event => event.action === 'APPROVED')).toBe(true)
    expect(browserErrors).toEqual([])
    await maker.goto('/workflow/plans')
    await expect(maker.getByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
    await expect(maker.locator('.auth-workflow-table tbody tr').first()).toBeVisible()
    const retainedSyntheticPlans = await maker.locator('.auth-workflow-table tbody tr').evaluateAll(rows =>
      rows.map(row => {
        const link = row.querySelector<HTMLAnchorElement>('td a')
        return {
          id: link?.getAttribute('href')?.split('/').at(-1),
          title: link?.querySelector('strong')?.textContent,
          status: row.querySelector('td:nth-child(3)')?.textContent?.trim(),
        }
      }).filter(row => row.title?.startsWith('Synthetic local Auth browser ')),
    )
    console.log(`Synthetic Auth plans retained: ${JSON.stringify(retainedSyntheticPlans)}`)
  } finally {
    await makerContext.close()
    await checkerContext.close()
  }
})

test('lists retained synthetic Auth plans without changing them', async ({ page }) => {
  test.skip(!password, 'Set AUTH_SEED_PASSWORD in the local test process to use the seeded local account.')
  await login(page, makerUsername, '/workflow/plans', 'MAKER')
  await expect(page.getByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
  await expect(page.locator('.auth-workflow-table tbody tr').first()).toBeVisible()
  const retained = await page.locator('.auth-workflow-table tbody tr').evaluateAll(rows =>
    rows.map(row => {
      const link = row.querySelector<HTMLAnchorElement>('td a')
      return {
        id: link?.getAttribute('href')?.split('/').at(-1),
        title: link?.querySelector('strong')?.textContent,
        status: row.querySelector('td:nth-child(3)')?.textContent?.trim(),
      }
    }).filter(row => row.title?.startsWith('Synthetic local Auth browser ')),
  )
  expect(retained.length).toBeGreaterThan(0)
  expect(retained.every(row => !protectedPlanIds.has(row.id ?? ''))).toBe(true)
  console.log(`Synthetic Auth plans retained: ${JSON.stringify(retained)}`)
  const completed = retained.find(row => row.status?.includes('Đã duyệt'))
  if (completed?.id) {
    const detail = await readPlan(page, completed.id)
    console.log(`Synthetic Auth evaluation steps: ${JSON.stringify(detail.ai_evaluations.map(run => ({
      run_id: run.run_id,
      version: run.version_number,
      round: run.round_number,
      provider: run.provider,
      status: run.status,
      model_id: run.model_id,
      visual_extraction: run.visual_extraction && {
        status: run.visual_extraction.status,
        model_id: run.visual_extraction.model_id,
        model_version: run.visual_extraction.model_version,
      },
      media_evaluation: run.media_evaluation && {
        status: run.media_evaluation.status,
        model_id: run.media_evaluation.model_id,
        model_version: run.media_evaluation.model_version,
        prompt_version: run.media_evaluation.prompt_version,
        schema_version: run.media_evaluation.schema_version,
      },
      strategy_evaluation: run.strategy_evaluation && {
        status: run.strategy_evaluation.status,
        model_id: run.strategy_evaluation.model_id,
        model_version: run.strategy_evaluation.model_version,
        prompt_version: run.strategy_evaluation.prompt_version,
        schema_version: run.strategy_evaluation.schema_version,
      },
    })))}`)
  }
})
