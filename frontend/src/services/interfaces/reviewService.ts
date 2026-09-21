import type { PlanId, ReviewDecisionInput, ReviewDecisionResult, ReviewDetail, ReviewItem, ServiceRequestMeta } from '../../types'

export interface ReviewService {
  listPendingReviews(): Promise<ReviewItem[]>
  getReview(planId: PlanId): Promise<ReviewDetail | null>
  decide(
    planId: PlanId,
    input: ReviewDecisionInput,
    meta: ServiceRequestMeta,
  ): Promise<ReviewDecisionResult>
}
