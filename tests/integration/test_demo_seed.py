import pytest

from src.backend.seed_demo import seed
from src.backend.repositories.approval import ApprovalRepository


def test_seed_repeat_preserves_audit(tmp_path):
    path = tmp_path / 'demo-seed.sqlite3'
    assert len(seed(path, 'demo')['created']) == 8
    repo = ApprovalRepository(path)
    before = repo.history('DEMO-SEED-FACTS')
    repo.close()
    assert len(seed(path, 'demo')['existing']) == 8
    repo = ApprovalRepository(path)
    assert repo.history('DEMO-SEED-FACTS') == before
    repo.close()
    with pytest.raises(ValueError):
        seed(tmp_path / 'production.sqlite3', 'demo')
    with pytest.raises(ValueError):
        seed(path, 'production')


def test_seed_preserves_submitted_policy_after_configuration_upgrade(tmp_path, monkeypatch):
    from dataclasses import replace
    import src.backend.seed_demo as module
    current = module.configuration
    def previous_configuration(**kwargs):
        config = current(**kwargs)
        return replace(config, policy=replace(config.policy, policy_version='DEMO-HTTP-1', auto_approval_policy_enabled=True))
    # Reproduce an old enabled-policy snapshot. Human scenarios use current
    # configuration so their explicit decisions apply.
    def legacy_for_auto(**kwargs):
        return previous_configuration(**kwargs) if kwargs.get('auto_approval') else current(**kwargs)
    monkeypatch.setattr(module, 'configuration', legacy_for_auto)
    path = tmp_path / 'demo-upgrade.sqlite3'
    seed(path, 'demo')
    repo = ApprovalRepository(path)
    before = repo.history('DEMO-SEED-AUTO')
    repo.close()
    monkeypatch.setattr(module, 'configuration', current)
    assert seed(path, 'demo')['created'] == []
    repo = ApprovalRepository(path)
    assert repo.history('DEMO-SEED-AUTO') == before
    assert repo.history('DEMO-SEED-APPROVED')['plan']['state']['plan_status'] == 'APPROVED'
    assert repo.history('DEMO-SEED-REJECTED')['plan']['state']['plan_status'] == 'REJECTED'
    assert repo.history('DEMO-SEED-DRAFT')['plan']['state']['plan_status'] == 'DRAFT'
    repo.close()
