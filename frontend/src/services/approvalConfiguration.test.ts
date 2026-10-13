import { describe, expect, it } from 'vitest'
import { validateConfigurationValue } from './approvalConfiguration'

describe('workflow configuration draft validation', () => {
  it('keeps Admin drafts from enabling auto approval before PO sign-off', () => {
    expect(validateConfigurationValue('approval_policy', {
      enabled: true,
      media_confidence_threshold: 0.85,
      feasibility_score_threshold_exclusive: 70,
      feasibility_confidence_threshold: 0.8,
    })).toContain('PO phê duyệt')
  })

  it('rejects overlapping budget limits for one department', () => {
    expect(validateConfigurationValue('budget', {
      currency: 'VND',
      limits: [
        { department: 'Marketing', limit_minor_units: '100', active: true },
        { department: 'Marketing', limit_minor_units: '200', active: true },
      ],
    })).toContain('chồng lấn')
  })

  it('accepts a budget draft with VND integer minor units', () => {
    expect(validateConfigurationValue('budget', {
      currency: 'VND',
      limits: [{ department: 'Marketing', limit_minor_units: '1000000', active: true }],
    })).toBeNull()
  })

  it('requires rubric weights to total 100 across all supported criteria', () => {
    expect(validateConfigurationValue('strategy_rubric', {
      rubric_id: 'SYNTHETIC',
      rubric_version: '1',
      status: 'ACTIVE',
      criteria: [
        { criterion_id: 'objective', label: 'Mục tiêu', weight: 14 },
        { criterion_id: 'audience', label: 'Đối tượng', weight: 15 },
        { criterion_id: 'channel', label: 'Kênh', weight: 15 },
        { criterion_id: 'timeline', label: 'Thời gian', weight: 15 },
        { criterion_id: 'kpi', label: 'KPI', weight: 15 },
        { criterion_id: 'budget_efficiency', label: 'Hiệu quả ngân sách', weight: 15 },
        { criterion_id: 'risk_control', label: 'Kiểm soát rủi ro', weight: 10 },
      ],
    })).toContain('tổng trọng số bằng 100')
  })
})
