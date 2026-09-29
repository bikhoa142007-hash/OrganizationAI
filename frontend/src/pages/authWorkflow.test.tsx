import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { authService } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPlan } from '../types/authWorkflow'
import { AuthenticatedWorkflowDetailPage } from './AuthenticatedWorkflowDetailPage'

const checker = {
  id: 'checker-1', user_code: 'USR-CHECKER', username: 'checker', email: 'checker@example.com',
  phone: null, display_name: 'Checker One', status: 'ACTIVE' as const, roles: ['CHECKER'],
}

function planFixture(): WorkflowPlan {
  return {
    id: 'plan-1', code: 'MKT-1',
    payload: {
      title: 'Spring campaign', objective: 'Reach customers', summary: 'A measured plan',
      department: 'marketing', start_date: '2026-10-01', end_date: '2026-10-31',
      budget_minor_units: '50000000', currency: 'VND', target_audience: '', channels: [],
      kpi_expected: '', notes: '',
    },
    status: 'PENDING_APPROVAL', processing_stage: 'HUMAN_REVIEW_REQUIRED',
    maker_id: 'maker-1', maker_name: 'Maker One', checker_id: checker.id, checker_name: checker.display_name,
    current_version: 1, current_round: 1, revision: 4, decision_reason: 'EVAL_VALID requires review.',
    attachments: [], versions: [], history: [], created_at: '2026-09-29T10:00:00Z', updated_at: '2026-09-29T10:01:00Z',
    ai_evaluations: [{
      id: 'run-row-1', version_number: 1, round_number: 1, run_id: 'run-1', evaluation_id: 'eval-1',
      correlation_id: 'http-1', input_hash: 'a'.repeat(64), provider: 'MOCK_VLM', model_version: 'mock-1',
      policy_version: 'AUTH-WORKFLOW-POLICY-UNCONFIGURED-1',
      policy_snapshot_id: 'AUTH-WORKFLOW-POLICY-UNCONFIGURED', policy_snapshot_hash: 'b'.repeat(64),
      status: 'FAILED', attempts: 2, retried: true,
      failure_reason: 'PROVIDER_TIMEOUT', started_at: '2026-09-29T10:00:01Z',
      completed_at: '2026-09-29T10:00:02Z', created_at: '2026-09-29T10:00:00Z',
      evaluation: {
        evaluation_id: 'eval-1', plan_id: 'plan-1', plan_version: 1, approval_round: 1, run_id: 'run-1',
        status: 'TIMED_OUT', provider: 'MOCK_VLM', model_version: null, policy_version: 'POLICY-1',
        input_hash: 'a'.repeat(64), media_result: null, media_confidence: null,
        feasibility_score: null, feasibility_confidence: null, proposed_action: null,
        reason: 'Evaluation failed closed.', media_findings: [], evidence: [], evidence_conflicts: [],
        missing_facts: [], agent_errors: [{ component: 'provider', code: 'PROVIDER_TIMEOUT', message: 'Provider timed out.' }],
        criterion_scores: [], assumptions: [],
      },
    }],
    engine_decisions: [{
      id: 'decision-row-1', version_number: 1, round_number: 1, decision_id: 'decision-1',
      outcome: 'HUMAN_REVIEW_REQUIRED', created_at: '2026-09-29T10:00:02Z',
      decision: {
        reason: 'Human Review required: EVAL_VALID.', applied_rule_ids: ['EVAL_VALID'],
        rule_checks: [{ rule_id: 'EVAL_VALID', result: 'FAIL', observed_value: 'FAILED', applicable_rule_or_limit: 'Schema-valid success', evidence_refs: [] }],
        budget_validation: { result: 'UNKNOWN', budget_minor_units: '50000000', limit_minor_units: null, currency: 'VND' },
        escalation_category: 'FACT_UNCERTAIN',
      },
    }],
  }
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/workflow/plans/plan-1']}>
      <AuthProvider>
        <Routes><Route path="/workflow/plans/:planId" element={<AuthenticatedWorkflowDetailPage />} /></Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

it('shows the provider mode, evaluation failure, policy route and saved reason', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(checker)
  vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValue(planFixture())
  vi.spyOn(authWorkflowService, 'getAttachment').mockResolvedValue(new Blob())

  renderDetail()

  expect(await screen.findByText('Mô phỏng (Mock VLM)')).toBeVisible()
  expect(screen.getByText('PROVIDER_TIMEOUT', { exact: false })).toBeVisible()
  expect(screen.getByText('Đã chuyển Checker theo policy')).toBeVisible()
  expect(screen.getByText('Lý do chuyển Checker')).toBeVisible()
})

it('requires an override explanation and shows Checker API errors', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(checker)
  vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValue(planFixture())
  vi.spyOn(authWorkflowService, 'getAttachment').mockResolvedValue(new Blob())
  const decide = vi.spyOn(authWorkflowService, 'decide').mockRejectedValue(new Error('Round is no longer active.'))
  renderDetail()

  fireEvent.click(await screen.findByRole('button', { name: 'Phê duyệt' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Nhập lý do override')
  expect(decide).not.toHaveBeenCalled()

  fireEvent.change(screen.getByLabelText('Lý do override AI'), { target: { value: 'Reviewed the media manually.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Phê duyệt' }))
  await waitFor(() => expect(decide).toHaveBeenCalledWith(
    'plan-1', 1, 'APPROVED', '', 'Reviewed the media manually.',
  ))
  expect(await screen.findByRole('alert')).toHaveTextContent('Round is no longer active.')
})
