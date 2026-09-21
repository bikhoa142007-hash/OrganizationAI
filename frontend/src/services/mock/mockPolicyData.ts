import type { PolicyView } from '../../types'

/**
 * Demo-only policy view. It is display data rather than executable frontend
 * policy. A real adapter must replace it with the policy owned by R1/R2.
 * NEEDS CONTRACT RECONCILIATION WITH R1/R2.
 */
export const mockCurrentPolicy: PolicyView = {
  policyVersion: 'mock-policy-v1',
  policyName: 'Mock Marketing Plan Approval Policy',
  status: 'Mock snapshot for judge demo',
  dataSource: 'MOCK',
  rules: [
    { ruleId: 'INPUT_INTEGRITY', title: 'Input integrity', description: 'Mock display rule for a complete and valid submission snapshot.', scope: 'Submitted plan input', action: 'Route incomplete or invalid input for review', reference: 'mock-policy-v1#INPUT_INTEGRITY' },
    { ruleId: 'EVAL_VALID', title: 'Evaluation validity', description: 'Mock display rule for a valid evaluation envelope.', scope: 'Evaluation output', action: 'Route invalid evaluation output for review', reference: 'mock-policy-v1#EVAL_VALID' },
    { ruleId: 'MEDIA_PASS', title: 'Media check', description: 'Mock display rule for media evaluation evidence.', scope: 'Attached media', action: 'Route non-passing media evidence for review', reference: 'mock-policy-v1#MEDIA_PASS' },
    { ruleId: 'MEDIA_CONFIDENCE', title: 'Media confidence', description: 'Mock display rule for the confidence returned with media evidence.', scope: 'Media evaluation', action: 'Route insufficient confidence for review', reference: 'mock-policy-v1#MEDIA_CONFIDENCE' },
    { ruleId: 'FEASIBILITY_SCORE', title: 'Feasibility score', description: 'Mock display rule for a structured feasibility observation.', scope: 'Strategy evaluation', action: 'Route an insufficient score for review', reference: 'mock-policy-v1#FEASIBILITY_SCORE' },
    { ruleId: 'FEASIBILITY_CONFIDENCE', title: 'Feasibility confidence', description: 'Mock display rule for confidence in the feasibility observation.', scope: 'Strategy evaluation', action: 'Route insufficient confidence for review', reference: 'mock-policy-v1#FEASIBILITY_CONFIDENCE' },
    { ruleId: 'BUDGET_LIMIT', title: 'Budget limit', description: 'Mock display rule for the configured budget boundary.', scope: 'Budget configuration', action: 'Route a budget exception for review', reference: 'mock-policy-v1#BUDGET_LIMIT' },
    { ruleId: 'AUTHORITY_LIMIT', title: 'Authority limit', description: 'Mock display rule for the configured authority boundary.', scope: 'Authority configuration', action: 'Route authority exceptions for review', reference: 'mock-policy-v1#AUTHORITY_LIMIT' },
    { ruleId: 'NO_HARD_VIOLATION', title: 'Hard-violation check', description: 'Mock display rule for deterministic hard violations.', scope: 'Policy evidence', action: 'Route detected hard violations for review', reference: 'mock-policy-v1#NO_HARD_VIOLATION' },
    { ruleId: 'NO_EVIDENCE_CONFLICT', title: 'Evidence conflict check', description: 'Mock display rule for conflicting evidence.', scope: 'Evaluation evidence', action: 'Route conflicting evidence for review', reference: 'mock-policy-v1#NO_EVIDENCE_CONFLICT' },
    { ruleId: 'POLICY_ENABLED', title: 'Policy availability', description: 'Mock display rule for an active policy snapshot.', scope: 'Policy snapshot', action: 'Route inactive policy snapshots for review', reference: 'mock-policy-v1#POLICY_ENABLED' },
    { ruleId: 'PLAN_PENDING', title: 'Plan pending state', description: 'Mock display rule for a plan that is still pending approval.', scope: 'Plan state', action: 'Route non-pending plans for review', reference: 'mock-policy-v1#PLAN_PENDING' },
    { ruleId: 'ROUND_ACTIVE', title: 'Approval round state', description: 'Mock display rule for an active approval round.', scope: 'Approval round', action: 'Route inactive rounds for review', reference: 'mock-policy-v1#ROUND_ACTIVE' },
  ],
}
