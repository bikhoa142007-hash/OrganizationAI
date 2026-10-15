import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  configurationKinds,
  approvalConfigurationService,
  type ConfigurationCurrent,
  type ConfigurationKind,
  type ConfigurationRevision,
} from '../services/approvalConfiguration'
import { AuthenticatedApprovalConfigurationPage } from './AuthenticatedApprovalConfigurationPage'

function revision(kind: ConfigurationKind, value: Record<string, unknown>, number = 1): ConfigurationRevision {
  return {
    revision_id: `${kind}-revision-${number}`, kind, revision: number, status: kind === 'approval_policy' ? 'DISABLED' : 'EFFECTIVE',
    effective_at: '2026-10-15T00:00:00Z', change_reason: 'Synthetic test revision', value,
    configuration_hash: `${String(number).padStart(64, '0')}`, changed_by: 'synthetic-admin', created_at: '2026-10-15T00:00:00Z',
  }
}

const current: ConfigurationCurrent = {
  as_of: '2026-10-15T00:00:00Z',
  items: configurationKinds.map(kind => ({
    kind,
    status: kind === 'approval_policy' ? 'DISABLED' : 'EFFECTIVE',
    current_revision: revision(kind, kind === 'approval_policy'
      ? { enabled: false, media_confidence_threshold: 0.85, feasibility_score_threshold_exclusive: 70, feasibility_confidence_threshold: 0.8 }
      : { synthetic: true }),
    next_scheduled_revision: null,
  })),
}

afterEach(() => vi.restoreAllMocks())

describe('Policy Owner sign-off UI', () => {
  it('submits the exact currently displayed configuration revision IDs and hashes', async () => {
    const user = userEvent.setup()
    vi.spyOn(approvalConfigurationService, 'current').mockResolvedValue(current)
    vi.spyOn(approvalConfigurationService, 'history').mockResolvedValue({
      kind: 'approval_policy', as_of: current.as_of, items: [current.items[0].current_revision!], offset: 0, limit: 50, total: 1,
    })
    const signed = {
      ...current.items[0].current_revision!,
      revision_id: 'approval_policy-revision-2', revision: 2, status: 'EFFECTIVE' as const,
      value: { enabled: true, media_confidence_threshold: 0.85, feasibility_score_threshold_exclusive: 70, feasibility_confidence_threshold: 0.8 },
      signoff: {
        candidate_revision_id: 'approval_policy-revision-1', approval_policy_revision_id: 'approval_policy-revision-2',
        approved_configuration_hash: '2'.repeat(64), policy_owner_id: 'synthetic-owner', signed_at: '2026-10-15T01:00:00Z',
        authority_revision_id: 'authority-revision-1', authority_configuration_hash: '3'.repeat(64),
        configuration_revisions: Object.fromEntries([
          ...configurationKinds.map(kind => [kind, {
            revision_id: `${kind}-revision-1`, configuration_hash: '1'.repeat(64),
          }] as const),
          ['approval_policy_candidate', {
            revision_id: 'approval_policy-revision-1', configuration_hash: '1'.repeat(64),
          }] as const,
        ]),
      },
    }
    const signOff = vi.spyOn(approvalConfigurationService, 'signOffPolicy').mockResolvedValue({ revision: signed, replayed: false })

    render(<MemoryRouter><AuthenticatedApprovalConfigurationPage /></MemoryRouter>)

    await user.click(await screen.findByRole('button', { name: 'Policy Owner ký và bật auto-approve' }))

    const expected = Object.fromEntries(current.items.map(item => [item.kind, {
      revision_id: item.current_revision!.revision_id,
      configuration_hash: item.current_revision!.configuration_hash,
    }]))
    expect(signOff).toHaveBeenCalledWith(expected)
    expect(await screen.findByRole('status')).toHaveTextContent('Đã ghi sign-off của Policy Owner cho revision 2')
  })
})
