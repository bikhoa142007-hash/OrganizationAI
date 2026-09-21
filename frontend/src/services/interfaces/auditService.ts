import type { AuditEvent, PlanId, RunId } from '../../types'

export interface AuditService {
  listByPlan(planId: PlanId): Promise<AuditEvent[]>
  listByRun(runId: RunId): Promise<AuditEvent[]>
}
