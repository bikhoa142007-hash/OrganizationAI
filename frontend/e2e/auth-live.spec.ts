import { test, expect, type Page, type Route } from '@playwright/test'
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

async function readMakerPlans(page: Page) {
  return page.evaluate(async base => {
    const response = await fetch(`${base}/workflow/plans?offset=0&limit=100`, { credentials: 'include' })
    if (!response.ok) throw new Error(`Could not reload the Maker plan list (HTTP ${response.status}).`)
    return await response.json() as Array<{ id: string; status: string; payload: { title: string } }>
  }, apiBase)
}

async function enterDraftTitle(page: Page, title: string, checkerId?: string): Promise<string> {
  await expect(page.getByLabel('Tên kế hoạch')).toBeVisible()
  await page.getByLabel('Tên kế hoạch').fill(title)
  const checkerSelect = page.getByLabel('Người phê duyệt')
  await expect(checkerSelect.locator('option').nth(1)).toBeAttached()
  const selectedCheckerId = checkerId ?? await checkerSelect.locator('option').nth(1).getAttribute('value')
  if (!selectedCheckerId) throw new Error('The seeded Auth E2E has no available Checker account.')
  await checkerSelect.selectOption(selectedCheckerId)
  return selectedCheckerId
}

async function saveDraftResponse(page: Page) {
  const responsePromise = page.waitForResponse(response => response.url() === `${apiBase}/workflow/plans`
    && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Lưu bản nháp' }).click()
  return responsePromise
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

test('creation intent replays a lost PostgreSQL draft response and rejects changed content', async ({ page, request }) => {
  test.skip(!password, 'Set AUTH_SEED_PASSWORD in the local test process to use the seeded local account.')
  await login(page, makerUsername, '/workflow/plans', 'MAKER')

  const title = `Synthetic lost-response ${new Date().toISOString()}`
  const changedTitle = `${title} changed`
  await page.goto('/workflow/plans/new')
  await page.waitForURL(/creation_intent=[\da-f-]{36}/i)
  const intentId = new URL(page.url()).searchParams.get('creation_intent')
  if (!intentId) throw new Error('The new form did not receive a creation intent.')
  expect(intentId).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i)

  const checkerId = await enterDraftTitle(page, title)
  const requestBody = { payload: { title, objective: '', summary: '', department: '', start_date: '', end_date: '',
    budget_minor_units: '', currency: 'VND', target_audience: '', channels: [], kpi_expected: '', notes: '' },
  checker_user_id: checkerId }
  const unauthenticatedIntentAttempt = await request.post(`${apiBase}/workflow/plans`, {
    data: requestBody,
    headers: { 'Idempotency-Key': `workflow-create:${intentId}` },
  })
  expect(unauthenticatedIntentAttempt.status()).toBe(401)

  let serverCreatedId = ''
  let serverCreatedStatus = 0
  const interceptedBody: { value?: Record<string, unknown> } = {}
  const abortCommittedResponse = async (route: Route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    interceptedBody.value = route.request().postDataJSON() as Record<string, unknown>
    const committedResponse = await route.fetch()
    serverCreatedStatus = committedResponse.status()
    const body = await committedResponse.json() as { id: string }
    serverCreatedId = body.id
    await route.abort('failed')
  }
  await page.route(`${apiBase}/workflow/plans`, abortCommittedResponse)
  await page.getByRole('button', { name: 'Lưu bản nháp' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Không nhận được xác nhận từ máy chủ' })).toBeVisible()
  expect(serverCreatedStatus).toBe(201)
  expect(serverCreatedId).toMatch(/^[0-9a-f-]{36}$/i)
  expect((interceptedBody.value?.payload as { title?: string } | undefined)?.title).toBe(title)
  expect(interceptedBody.value?.checker_user_id).toBe(checkerId)
  await page.unroute(`${apiBase}/workflow/plans`, abortCommittedResponse)

  await expect.poll(() => new URL(page.url()).searchParams.get('creation_pending')).toBe('1')
  const lostResponseUrl = page.url()
  await page.reload()
  expect(page.url()).toBe(lostResponseUrl)
  expect(new URL(page.url()).searchParams.get('creation_intent')).toBe(intentId)
  await expect(page.getByRole('heading', { name: 'Chưa xác định được kết quả tạo bản nháp' })).toBeVisible()

  const listPagePromise = page.context().waitForEvent('page')
  await page.getByRole('link', { name: 'Mở danh sách trong tab mới' }).click()
  const listPage = await listPagePromise
  await expect(listPage.getByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
  await expect(listPage.getByRole('link', { name: new RegExp(title) })).toBeVisible()
  await listPage.close()
  expect((await readMakerPlans(page)).filter(plan => plan.payload.title === title)).toHaveLength(1)

  await enterDraftTitle(page, title, checkerId)
  await page.getByRole('button', { name: 'Tôi đã kiểm tra — cho phép thử lại' }).click()
  const replayResponse = await saveDraftResponse(page)
  expect(replayResponse.status()).toBe(201)
  const replayedPlan = await replayResponse.json() as { id: string }
  expect(replayedPlan.id).toBe(serverCreatedId)
  await expect(page).toHaveURL(new RegExp(`/workflow/plans/${serverCreatedId}$`))

  await page.goto('/workflow/plans/new')
  await page.waitForURL(/creation_intent=[\da-f-]{36}/i)
  const freshIntentId = new URL(page.url()).searchParams.get('creation_intent')
  if (!freshIntentId) throw new Error('A new form did not receive a creation intent.')
  expect(freshIntentId).toMatch(/^[\da-f-]{36}$/i)
  expect(freshIntentId).not.toBe(intentId)
  await enterDraftTitle(page, title, checkerId)
  const freshIntentResponse = await saveDraftResponse(page)
  expect(freshIntentResponse.status()).toBe(201)
  const freshPlan = await freshIntentResponse.json() as { id: string }
  expect(freshPlan.id).not.toBe(serverCreatedId)
  await expect(page).toHaveURL(new RegExp(`/workflow/plans/${freshPlan.id}$`))

  await page.goto(`/workflow/plans/new?creation_intent=${encodeURIComponent(intentId)}&creation_pending=1`)
  await expect(page.getByRole('heading', { name: 'Chưa xác định được kết quả tạo bản nháp' })).toBeVisible()
  await enterDraftTitle(page, changedTitle, checkerId)
  await page.getByRole('button', { name: 'Tôi đã kiểm tra — cho phép thử lại' }).click()
  const changedPayloadResponse = await saveDraftResponse(page)
  expect(changedPayloadResponse.status()).toBe(409)
  const conflict = await changedPayloadResponse.json() as { code: string }
  expect(conflict.code).toBe('IDEMPOTENCY_CONFLICT')
  await expect(page.getByRole('heading', { name: 'Ý định tạo này đã được dùng với nội dung khác' })).toBeVisible()
  await expect(page.getByText(/Máy chủ không tạo thêm bản nháp/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Mở biểu mẫu mới' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lưu bản nháp' })).toBeDisabled()
  await page.getByRole('link', { name: 'Mở biểu mẫu mới' }).click()
  await page.waitForURL(/creation_intent=[\da-f-]{36}/i)
  expect(new URL(page.url()).searchParams.get('creation_intent')).not.toBe(intentId)

  const matchingDrafts = (await readMakerPlans(page)).filter(plan => plan.payload.title === title)
  expect(matchingDrafts).toHaveLength(2)
  expect(matchingDrafts.every(plan => plan.status === 'DRAFT')).toBe(true)
  expect((await readMakerPlans(page)).filter(plan => plan.payload.title === changedTitle)).toHaveLength(0)
  const createdEventCounts: number[] = []
  for (const draft of matchingDrafts) {
    const persisted = await readPlan(page, draft.id)
    const createdEvents = persisted.history.filter(event => event.action === 'CREATED').length
    expect(createdEvents).toBe(1)
    createdEventCounts.push(createdEvents)
  }

  console.log(`Creation intent E2E evidence: ${JSON.stringify({
    committedResponseAbortedBeforeBrowser: serverCreatedStatus === 201,
    reloadKeptIntent: true,
    sameIntentReturnedSamePlan: replayedPlan.id === serverCreatedId,
    freshIntentCreatedDifferentPlan: freshPlan.id !== serverCreatedId,
    changedPayloadStatus: changedPayloadResponse.status(),
    draftCountForOriginalPayload: matchingDrafts.length,
    changedPayloadDraftCount: 0,
    createdEventCountPerDraft: createdEventCounts,
    unauthenticatedSameIntentStatus: unauthenticatedIntentAttempt.status(),
  })}`)
})
