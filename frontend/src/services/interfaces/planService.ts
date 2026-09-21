import type {
  AttachmentRef,
  PlanDraftPayload,
  PlanId,
  PlanView,
  ProcessingSnapshot,
  ResultView,
  ServiceRequestMeta,
} from '../../types'

export interface PlanService {
  listPlans(): Promise<PlanView[]>
  getPlan(planId: PlanId): Promise<PlanView | null>
  saveDraft(
    planId: PlanId,
    payload: PlanDraftPayload,
    meta: ServiceRequestMeta,
  ): Promise<PlanView | null>
  uploadAttachment(
    planId: PlanId,
    file: File,
    meta: ServiceRequestMeta,
  ): Promise<AttachmentRef | null>
  submitPlan(planId: PlanId, meta: ServiceRequestMeta): Promise<PlanView | null>
  getProcessingStatus(planId: PlanId): Promise<ProcessingSnapshot>
  getResult(planId: PlanId): Promise<ResultView | null>
  stopProcessing(planId: PlanId, meta: ServiceRequestMeta): Promise<ProcessingSnapshot>
  retryProcessing(planId: PlanId, meta: ServiceRequestMeta): Promise<ProcessingSnapshot>
}
