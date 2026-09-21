export type { AuditService } from './auditService'
export type { PlanService } from './planService'
export type { PolicyService } from './policyService'
export type { ReviewService } from './reviewService'
export type { VerifyService } from './verifyService'

import type { AuditService } from './auditService'
import type { PlanService } from './planService'
import type { PolicyService } from './policyService'
import type { ReviewService } from './reviewService'
import type { VerifyService } from './verifyService'

export interface FrontendServices {
  plan: PlanService
  review: ReviewService
  audit: AuditService
  verify: VerifyService
  policy: PolicyService
}
