import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect, type Page } from '@playwright/test'

const apiBase = process.env.VITE_API_BASE_URL?.replace(/\/$/, '')
const password = process.env.AUTH_SEED_PASSWORD
const python = process.env.ORGANIZATIONAI_TEST_PYTHON
const image = resolve(import.meta.dirname, '../../tests/fixtures/ba/v2.1/images/creative-pass.png')
if (!apiBase || !password || !python || !process.env.DATABASE_URL) {
  throw new Error('Set the temporary PostgreSQL API, seeded test password, Python interpreter, and DATABASE_URL.')
}

type Rubric = {
  rubric_id: string
  rubric_version: string
  status: 'ACTIVE'
  criteria: Array<{ criterion_id: string; label: string; weight: number }>
}

type EvaluationRun = {
  id: string
  attempt_number: number
  status: string
  failure_reason: string | null
  result_disposition: string | null
  input_hash: string
  policy_snapshot_hash: string
  model_id: string | null
  model_version: string | null
  evaluation: { agent_errors?: Array<{ component: string; code: string; message?: string }> } | null
  strategy_evaluation: { status?: string; error_code?: string | null } | null
}

type LivePlan = {
  id: string
  code: string
  status: string
  processing_stage: string
  current_version: number
  current_round: number
  revision: number
  versions: Array<{ version_number: number; round_number: number; payload: { summary: string } }>
  ai_evaluations: EvaluationRun[]
}

const criterionIds = [
  'objective', 'audience', 'channel', 'timeline', 'kpi', 'budget_efficiency', 'risk_control',
]
const criterionLabels = [
  'Objective', 'Audience', 'Channel', 'Timeline', 'KPI', 'Budget efficiency', 'Risk control',
]

function rubric(revision: number, weights: number[]): Rubric {
  return {
    rubric_id: `synthetic-publication-e2e-${revision}`,
    rubric_version: String(revision),
    status: 'ACTIVE',
    criteria: criterionIds.map((criterion_id, index) => ({
      criterion_id,
      label: criterionLabels[index],
      weight: weights[index],
    })),
  }
}

function localDateTime(minutesAgo: number): string {
  const date = new Date(Date.now() - minutesAgo * 60_000)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

async function login(page: Page, username: string, destination: string) {
  await page.goto('/login')
  await page.getByLabel('Tên đăng nhập, mã người dùng hoặc email').fill(username)
  await page.locator('#login-password').fill(password!)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page).toHaveURL(new RegExp(`${destination.replaceAll('/', '\\/')}$`))
}

async function createRubricRevision(page: Page, value: Rubric, revision: number, reason: string) {
  await page.goto('/workflow/configuration')
  await expect(page.getByRole('heading', { name: 'Cấu hình phê duyệt' })).toBeVisible()
  await page.getByLabel('Loại cấu hình').selectOption('strategy_rubric')
  await expect(page.getByRole('note')).toContainText('evaluator hiện chỉ hỗ trợ bộ trọng số baseline')
  await page.getByLabel('Giá trị JSON').fill(JSON.stringify(value, null, 2))
  await page.getByLabel(/Hiệu lực từ thời điểm/).fill(localDateTime(10 - revision * 2))
  await page.getByLabel('Lý do thay đổi').fill(reason)
  await page.getByRole('button', { name: 'Tạo revision bất biến' }).click()
  await expect(page.getByRole('status').filter({ hasText: `Đã tạo revision ${revision}` })).toBeVisible()
}

async function readPlan(page: Page, planId: string): Promise<LivePlan> {
  return page.evaluate(async ({ base, id }) => {
    const response = await fetch(`${base}/workflow/plans/${encodeURIComponent(id)}`, { credentials: 'include' })
    if (!response.ok) throw new Error(`Plan detail returned HTTP ${response.status}.`)
    return await response.json() as LivePlan
  }, { base: apiBase!, id: planId })
}

async function waitForReview(page: Page, planId: string): Promise<LivePlan> {
  await expect.poll(async () => {
    const plan = await readPlan(page, planId)
    return plan.status === 'PENDING_APPROVAL'
      && plan.processing_stage === 'HUMAN_REVIEW_REQUIRED'
      && plan.ai_evaluations.length > 0
  }, { timeout: 180_000 }).toBe(true)
  return readPlan(page, planId)
}

async function createSubmittedPlan(page: Page, title: string): Promise<string> {
  await page.goto('/workflow/plans/new')
  await page.getByLabel('Tên kế hoạch').fill(title)
  await page.getByLabel('Bộ phận').fill('e2e-browser')
  const checker = page.getByLabel('Người phê duyệt')
  await expect(checker.locator('option').nth(1)).toBeAttached()
  await checker.selectOption({ index: 1 })
  await page.getByRole('button', { name: 'Lưu bản nháp' }).click()
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Chỉnh sửa và gửi lại' }).click()
  await page.getByRole('textbox', { name: 'Mục tiêu', exact: true }).fill('Measure qualified product trial registrations.')
  await page.getByLabel('Bộ phận').fill('e2e-browser')
  await page.getByLabel('Ngày bắt đầu').fill('2026-11-01')
  await page.getByLabel('Ngày kết thúc').fill('2026-11-30')
  await page.getByLabel('Ngân sách (đơn vị nhỏ nhất)').fill('50000000')
  await page.getByLabel('Đối tượng mục tiêu').fill('Opted-in customers aged 25 to 40.')
  await page.getByLabel('Tóm tắt chiến lược').fill('Synthetic PostgreSQL browser acceptance plan.')
  await page.getByLabel('KPI kỳ vọng').fill('Count verified product trial registrations.')
  await page.getByLabel('Kênh triển khai').fill('social, in-store demo')
  await page.getByLabel('Ghi chú').fill('Synthetic local publication acceptance fixture.')
  await page.getByLabel('Chọn ảnh đính kèm').setInputFiles(image)
  const planId = new URL(page.url()).pathname.split('/').filter(Boolean).at(-2)
  if (!planId) throw new Error('Could not identify the synthetic plan id from its edit route.')
  await page.getByRole('button', { name: 'Gửi duyệt' }).click()
  await expect(page).toHaveURL(new RegExp(`/workflow/plans/${planId}$`), { timeout: 180_000 })
  await waitForReview(page, planId)
  return planId
}

function runPythonJson(source: string, ...args: string[]): unknown {
  const output = execFileSync(python!, ['-c', source, ...args], {
    cwd: resolve(import.meta.dirname, '../..'),
    encoding: 'utf8',
    env: process.env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  return JSON.parse(output.trim()) as unknown
}

function readRoundRubric(planId: string) {
  return runPythonJson(`
import json, sys
from uuid import UUID
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from src.backend.db.models.approval_configuration import AuthWorkflowRoundConfigurationSnapshot
engine = create_engine(__import__('os').environ['DATABASE_URL'])
with Session(engine) as session:
    item = session.scalar(select(AuthWorkflowRoundConfigurationSnapshot).where(
        AuthWorkflowRoundConfigurationSnapshot.plan_id == UUID(sys.argv[1]),
        AuthWorkflowRoundConfigurationSnapshot.approval_round == 1,
    ))
    assert item is not None
    rubric = item.configurations['strategy_rubric']
    print(json.dumps({'snapshot_hash': item.snapshot_hash, 'revision': rubric['revision'],
        'revision_id': rubric['revision_id'], 'weights': [c['weight'] for c in rubric['value']['criteria']]}, sort_keys=True))
engine.dispose()
`, planId) as { snapshot_hash: string; revision: number; revision_id: string; weights: number[] }
}

function markLatestRunFailed(planId: string, failureCode: string) {
  return runPythonJson(`
import json, sys
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from src.backend.db.models.auth_workflow import AuthWorkflowEvaluationRun
engine = create_engine(__import__('os').environ['DATABASE_URL'])
with Session(engine) as session:
    run = session.scalar(select(AuthWorkflowEvaluationRun).where(
        AuthWorkflowEvaluationRun.plan_id == UUID(sys.argv[1]),
        AuthWorkflowEvaluationRun.round_number == 1,
    ).order_by(AuthWorkflowEvaluationRun.attempt_number.desc()).limit(1).with_for_update())
    assert run is not None and run.attempt_number == 1
    value = dict(run.evaluation or {})
    value['status'] = 'FAILED'
    value['agent_errors'] = [{
        'component': 'strategy_evaluation', 'code': sys.argv[2],
        'message': 'Synthetic local browser acceptance failure fixture.',
    }]
    run.evaluation = value
    run.status = 'FAILED'
    run.failure_reason = sys.argv[2]
    run.result_disposition = 'APPLIED'
    run.completed_at = datetime.now(timezone.utc)
    session.commit()
    print(json.dumps({'attempt_number': run.attempt_number, 'failure_code': run.failure_reason}))
engine.dispose()
`, planId, failureCode)
}

test('integrated dashboard, config snapshots, Checker notes, terminal errors and one retry per round', async ({ browser }) => {
  const adminContext = await browser.newContext()
  const makerContext = await browser.newContext()
  const checkerContext = await browser.newContext()
  const admin = await adminContext.newPage()
  const maker = await makerContext.newPage()
  const checker = await checkerContext.newPage()
  try {
    await login(admin, 'admin', '/workflow/plans')
    await admin.goto('/workflow/dashboard')
    await expect(admin.getByRole('heading', { name: 'Tổng quan kế hoạch marketing' })).toBeVisible()
    await expect(admin.getByLabel('Số liệu kế hoạch theo trạng thái')).toBeVisible()

    await createRubricRevision(admin, rubric(1, [16, 14, 15, 15, 15, 15, 10]), 1,
      'Synthetic browser test for a valid rubric the evaluator does not support.')
    await login(maker, 'maker', '/workflow/plans')
    await maker.goto('/workflow/configuration')
    await expect(maker.getByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    const configurationDenied = await maker.evaluate(async base => (
      await fetch(`${base}/workflow/configuration`, { credentials: 'include' })
    ).status, apiBase)
    expect(configurationDenied).toBe(403)

    const terminalPlanId = await createSubmittedPlan(maker, `Synthetic terminal rubric ${new Date().toISOString()}`)
    const terminalPlan = await waitForReview(maker, terminalPlanId)
    expect(terminalPlan.ai_evaluations[0].strategy_evaluation?.error_code).toBe('EVALUATOR_RUBRIC_UNSUPPORTED')

    await createRubricRevision(admin, rubric(2, [15, 15, 15, 15, 15, 15, 10]), 2,
      'Synthetic baseline rubric revision after the first round was captured.')
    const terminalSnapshot = readRoundRubric(terminalPlanId)
    expect(terminalSnapshot.revision).toBe(1)
    expect(terminalSnapshot.weights).toEqual([16, 14, 15, 15, 15, 15, 10])

    await login(checker, 'checker', '/workflow/reviews')
    const assignedTerminalRetry = await checker.evaluate(async ({ base, id, revision }) => {
      const response = await fetch(`${base}/workflow/plans/${id}/rounds/1/evaluation-retries`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'terminal-rubric-retry-assigned' },
        body: JSON.stringify({ expected_plan_version: 1, expected_round_revision: revision }),
      })
      return { status: response.status, body: await response.json() }
    }, { base: apiBase, id: terminalPlanId, revision: terminalPlan.revision })
    expect(assignedTerminalRetry.status).toBe(409)
    await checker.goto(`/workflow/plans/${terminalPlanId}`)
    await expect(checker.locator('.auth-ai-results')).toContainText('Hồ sơ đang chờ Checker xem xét.')
    await expect(checker.locator('.auth-ai-results')).not.toContainText('EVALUATOR_RUBRIC_UNSUPPORTED')
    await expect(checker.getByRole('button', { name: 'Chạy lại AI' })).toHaveCount(0)
    await expect(checker.getByRole('heading', { name: 'Ghi chú nội bộ' })).toBeVisible()
    await checker.getByLabel('Thêm ghi chú cho Checker').fill('Synthetic private Checker note for browser acceptance.')
    await checker.getByRole('button', { name: 'Thêm ghi chú' }).click()
    await expect(checker.getByRole('list', { name: 'Ghi chú nội bộ' })).toContainText('Synthetic private Checker note for browser acceptance.')
    const makerNoteAccess = await maker.evaluate(async ({ base, id }) => (
      await fetch(`${base}/workflow/plans/${id}/internal-notes`, { credentials: 'include' })
    ).status, { base: apiBase, id: terminalPlanId })
    expect(makerNoteAccess).toBe(403)

    const retryPlanId = await createSubmittedPlan(maker, `Synthetic retry snapshot ${new Date().toISOString()}`)
    const retryPlan = await waitForReview(maker, retryPlanId)
    expect(retryPlan.ai_evaluations[0].strategy_evaluation?.error_code).not.toBe('EVALUATOR_RUBRIC_UNSUPPORTED')
    await createRubricRevision(admin, rubric(3, [16, 14, 15, 15, 15, 15, 10]), 3,
      'Change current rubric after round two; retry must continue using its saved baseline snapshot.')
    const retrySnapshot = readRoundRubric(retryPlanId)
    expect(retrySnapshot.revision).toBe(2)
    expect(retrySnapshot.weights).toEqual([15, 15, 15, 15, 15, 15, 10])
    expect(markLatestRunFailed(retryPlanId, 'INVALID_SCHEMA')).toEqual({ attempt_number: 1, failure_code: 'INVALID_SCHEMA' })

    const makerRetryAccess = await maker.evaluate(async ({ base, id, revision }) => {
      const response = await fetch(`${base}/workflow/plans/${id}/rounds/1/evaluation-retries`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'maker-must-not-retry' },
        body: JSON.stringify({ expected_plan_version: 1, expected_round_revision: revision }),
      })
      return response.status
    }, { base: apiBase, id: retryPlanId, revision: retryPlan.revision })
    expect(makerRetryAccess).toBe(403)

    await checker.goto(`/workflow/plans/${retryPlanId}`)
    await expect(checker.getByRole('button', { name: 'Chạy lại AI' })).toBeVisible()
    await checker.getByRole('button', { name: 'Chạy lại AI' }).click()
    await expect(checker.getByRole('region', { name: 'Chạy lại đánh giá AI' }).getByRole('status')).toHaveText('Hồ sơ đang chờ Checker xem xét.', { timeout: 180_000 })
    await expect.poll(async () => (await readPlan(checker, retryPlanId)).ai_evaluations.length).toBe(2)
    const retried = await readPlan(checker, retryPlanId)
    expect(retried.ai_evaluations.map(item => item.attempt_number)).toEqual([1, 2])
    expect(retried.ai_evaluations[0].failure_reason).toBe('INVALID_SCHEMA')
    expect(retried.ai_evaluations[1].status).toBe('FAILED')
    expect(retried.ai_evaluations[1].strategy_evaluation?.error_code).toBe('STRATEGY_NOT_CONFIGURED')
    expect(retried.ai_evaluations[0].input_hash).toBe(retried.ai_evaluations[1].input_hash)
    expect(retried.ai_evaluations[0].policy_snapshot_hash).toBe(retried.ai_evaluations[1].policy_snapshot_hash)
    expect(retried.ai_evaluations[0].model_id).toBe(retried.ai_evaluations[1].model_id)
    expect(retried.ai_evaluations[0].model_version).toBe(retried.ai_evaluations[1].model_version)
    await expect(checker.getByRole('button', { name: 'Chạy lại AI' })).toHaveCount(0)
    const secondManualRetry = await checker.evaluate(async ({ base, id, revision }) => {
      const response = await fetch(`${base}/workflow/plans/${id}/rounds/1/evaluation-retries`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'checker-second-retry' },
        body: JSON.stringify({ expected_plan_version: 1, expected_round_revision: revision }),
      })
      return response.status
    }, { base: apiBase, id: retryPlanId, revision: retried.revision })
    expect(secondManualRetry).toBe(409)

    const conflictPlanId = await createSubmittedPlan(maker, `Synthetic terminal policy conflict ${new Date().toISOString()}`)
    const conflictPlan = await waitForReview(maker, conflictPlanId)
    expect(markLatestRunFailed(conflictPlanId, 'POLICY_OUTPUT_CONFLICT')).toEqual({
      attempt_number: 1, failure_code: 'POLICY_OUTPUT_CONFLICT',
    })
    await checker.goto(`/workflow/plans/${conflictPlanId}`)
    await expect(checker.locator('.auth-ai-results')).toContainText('Hồ sơ đang chờ Checker xem xét.')
    await expect(checker.locator('.auth-ai-results')).not.toContainText('POLICY_OUTPUT_CONFLICT')
    await expect(checker.getByRole('button', { name: 'Chạy lại AI' })).toHaveCount(0)
    const conflictRetry = await checker.evaluate(async ({ base, id, revision }) => {
      const response = await fetch(`${base}/workflow/plans/${id}/rounds/1/evaluation-retries`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'policy-conflict-is-terminal' },
        body: JSON.stringify({ expected_plan_version: 1, expected_round_revision: revision }),
      })
      return response.status
    }, { base: apiBase, id: conflictPlanId, revision: conflictPlan.revision })
    expect(conflictRetry).toBe(409)

    await admin.goto('/workflow/dashboard')
    await expect(admin.getByRole('heading', { name: 'Tổng quan kế hoạch marketing' })).toBeVisible()
    await expect(admin.getByText('Chờ Checker')).toBeVisible()
  } finally {
    await adminContext.close()
    await makerContext.close()
    await checkerContext.close()
  }
})
