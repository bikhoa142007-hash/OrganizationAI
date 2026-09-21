import pytest

from src.backend.seed_demo import seed
from src.backend.repositories.approval import ApprovalRepository


def test_seed_repeat_preserves_audit(tmp_path):
    path = tmp_path / 'demo-seed.sqlite3'
    assert len(seed(path, 'demo')['created']) == 5
    repo = ApprovalRepository(path)
    before = repo.history('DEMO-SEED-FACTS')
    repo.close()
    assert len(seed(path, 'demo')['existing']) == 5
    repo = ApprovalRepository(path)
    assert repo.history('DEMO-SEED-FACTS') == before
    repo.close()
    with pytest.raises(ValueError):
        seed(tmp_path / 'production.sqlite3', 'demo')
    with pytest.raises(ValueError):
        seed(path, 'production')
