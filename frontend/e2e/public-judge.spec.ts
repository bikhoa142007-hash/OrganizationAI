import { expect, test } from '@playwright/test'

test('public Challenge A runs isolated Mock suites and classifies new synthetic input', async ({ page }, testInfo) => {
  const consoleErrors: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await page.goto('/challenge-a')
  await expect(page.getByRole('heading', { name: 'Verify workflow' })).toBeVisible()
  await expect(page.getByText('Judge công khai, không cần tạo tài khoản')).toBeVisible()
  await expect(page.getByText('Bước đầu tiên: bấm “Run 4 cases” để chạy Verify chung.')).toBeVisible()

  const generalRequest = page.waitForRequest(request => request.url().endsWith('/public/judge/runs'))
  const generalResponse = page.waitForResponse(response => response.url().endsWith('/public/judge/runs'))
  await page.getByRole('button', { name: 'Run 4 cases' }).click()
  const [general, generalResult] = await Promise.all([generalRequest, generalResponse])
  expect(general.method()).toBe('POST')
  expect(general.postDataJSON()).toEqual({ suite: 'general' })
  expect(general.headers().authorization).toBeUndefined()
  expect(general.headers().cookie).toBeUndefined()
  expect(generalResult.status()).toBe(200)
  await expect(page.getByText('4/4 PASS', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Verify → Escalation · 5 ca' }).click()
  const escalationRequest = page.waitForRequest(request => request.url().endsWith('/public/judge/runs'))
  const escalationResponse = page.waitForResponse(response => response.url().endsWith('/public/judge/runs'))
  await page.getByRole('button', { name: 'Run 5 cases' }).click()
  const [escalation, escalationResult] = await Promise.all([escalationRequest, escalationResponse])
  expect(escalation.postDataJSON()).toEqual({ suite: 'escalation' })
  expect(escalationResult.status()).toBe(200)
  await expect(page.getByText('5/5 PASS', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Đánh giá đầu vào mới' }).click()
  await expect(page.getByRole('heading', { name: 'SIMULATED_AUTO_APPROVE' })).toBeVisible()
  await expect(page.getByText('MOCK · NOT_MEASURED')).toBeVisible()
  await page.getByLabel('Kênh').fill('UNLISTED_CHANNEL')
  await page.getByRole('button', { name: 'Đánh giá đầu vào mới' }).click()
  await expect(page.getByRole('heading', { name: 'HUMAN_REVIEW_REQUIRED' })).toBeVisible()
  await expect(page.getByText('POLICY_OUT_OF_SCOPE', { exact: true })).toBeVisible()
  await expect(page.getByText('Câu hỏi chuyển tiếp')).toBeVisible()

  await page.screenshot({ path: testInfo.outputPath('challenge-a-public.png'), fullPage: true })
  expect(consoleErrors).toEqual([])
})
