import type { AuditEvent, PlanId, RunId } from '../../types'
import type { AuditService } from '../interfaces'

export class MockAuditService implements AuditService {
  private readonly events: AuditEvent[] = [
    {
      eventId: 'mock-audit-1', action: 'PROCESSING_STARTED', actorId: 'system', timestamp: '2026-09-21T08:20:00Z',
      inputVersion: 'mock-input-v1', policyVersion: 'mock-policy-v1', modelVersion: 'mock-model-v1',
      reason: 'Service đã nhận hồ sơ để xử lý.', previousState: null,
      newState: { planStatus: 'PENDING_APPROVAL', processingStage: 'AI_PROCESSING', approvalRoundStatus: 'ACTIVE' },
    },
    {
      eventId: 'mock-audit-2', action: 'ESCALATED_TO_HUMAN_REVIEW', actorId: 'system', timestamp: '2026-09-21T08:30:00Z',
      inputVersion: 'mock-input-v1', policyVersion: 'mock-policy-v1', modelVersion: 'mock-model-v1',
      reason: 'Service chuyển hồ sơ tới người có thẩm quyền xem xét.',
      previousState: { planStatus: 'PENDING_APPROVAL', processingStage: 'AI_PROCESSING', approvalRoundStatus: 'ACTIVE' },
      newState: { planStatus: 'PENDING_APPROVAL', processingStage: 'HUMAN_REVIEW_REQUIRED', approvalRoundStatus: 'ACTIVE' },
    },
  ]

  async listByPlan(planId: PlanId): Promise<AuditEvent[]> {
    return this.events.filter((event) => !event.eventId.startsWith('mock-review-') || event.eventId.includes(planId))
  }

  async listByRun(_runId: RunId): Promise<AuditEvent[]> {
    return [...this.events]
  }

  appendReviewDecision(planId: PlanId, action: string, reason: string, previousState: AuditEvent['newState'], newState: AuditEvent['newState']) {
    this.events.push({
      eventId: `mock-review-${planId}-${this.events.length + 1}`, action, actorId: 'judge-demo-reviewer',
      timestamp: new Date().toISOString(), inputVersion: 'mock-input-v1', policyVersion: 'mock-policy-v1', modelVersion: 'mock-model-v1',
      reason, previousState, newState,
    })
  }
}
