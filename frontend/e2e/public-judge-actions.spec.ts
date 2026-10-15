import { expect, test } from '@playwright/test'

test('public Judge action follows the simulated Checker API contract (mocked response)', async ({ page }) => {
  let actionRequestBody: unknown
  let actionRequestHeaders: Record<string, string> | undefined

  await page.route('**/api/public/judge/runs', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      run_id: 'JUDGE-E2E-1', suite: 'general', status: 'COMPLETED', mode: 'MOCK',
      data_classification: 'SYNTHETIC', started_at: '2026-10-15T01:00:00.000Z',
      completed_at: '2026-10-15T01:00:02.000Z', duration_ms: 2000,
      summary: { total_cases: 1, passed_cases: 1, failed_cases: 0, error_cases: 0 },
      rows: [{
        case_id: 'CASE-E2E-1', case_name: 'Synthetic fact uncertainty', status: 'PASS', passed: true,
        expected_action: 'HUMAN_REVIEW_REQUIRED', expected_category: 'FACT_UNCERTAIN',
        actual_action: 'HUMAN_REVIEW_REQUIRED', actual_category: 'FACT_UNCERTAIN',
        human_action_available: true, human_action_status: null,
        started_at: '2026-10-15T01:00:00.000Z', completed_at: '2026-10-15T01:00:02.000Z', duration_ms: 2000,
        reason: 'Synthetic evidence needs a human response.',
        questions: [{ category: 'FACT_UNCERTAIN', question: 'Which synthetic value has an approved source?' }],
        evidence: [], applied_rule_ids: [], audit: [],
      }],
    }),
  }))

  await page.route('**/api/public/judge/runs/JUDGE-E2E-1/cases/CASE-E2E-1/action', async route => {
    const request = route.request()
    actionRequestBody = request.postDataJSON()
    actionRequestHeaders = request.headers()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        run_id: 'JUDGE-E2E-1', case_id: 'CASE-E2E-1', status: 'HUMAN_APPROVED', action: 'APPROVE',
        is_override: false, timestamp: '2026-10-15T01:01:00.000Z', input_sha256: 'synthetic-e2e-hash',
        reason: 'Reviewed the synthetic evidence.',
        audit: [{
          event_id: 'AUDIT-E2E-1', actor: 'ANONYMOUS_PUBLIC_JUDGE', action: 'HUMAN_APPROVED',
          timestamp: '2026-10-15T01:01:00.000Z', input_sha256: 'synthetic-e2e-hash',
          reason: 'Reviewed the synthetic evidence.',
        }],
        idempotent_replay: false,
      }),
    })
  })

  await page.goto('/challenge-a')
  await page.getByRole('button', { name: 'Run 4 cases' }).click()
  await page.getByRole('button', { name: 'Chi tiết CASE-E2E-1' }).click()
  await page.getByLabel('Thao tác mô phỏng').selectOption('APPROVE')
  await page.getByLabel('Lý do (bắt buộc, tối đa 500 ký tự)').fill('  Reviewed the synthetic evidence.  ')
  await page.getByRole('button', { name: 'Ghi nhận thao tác mô phỏng' }).click()

  await expect(page.getByRole('heading', { name: 'HUMAN_APPROVED' })).toBeVisible()
  await expect(page.getByText('ANONYMOUS_PUBLIC_JUDGE · HUMAN_APPROVED')).toBeVisible()
  await expect(page.getByText('synthetic-e2e-hash')).toBeVisible()
  expect(actionRequestBody).toEqual({ action: 'APPROVE', reason: 'Reviewed the synthetic evidence.' })
  expect(actionRequestHeaders?.['idempotency-key']).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)
  expect(actionRequestHeaders?.authorization).toBeUndefined()
  expect(actionRequestHeaders?.cookie).toBeUndefined()
})
