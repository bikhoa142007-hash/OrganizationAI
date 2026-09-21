"""Explicit synthetic demo configuration; no Role 1 expectations at runtime."""
from pathlib import Path

from src.backend.domain.policy import (
    ApprovalConfiguration, AuthoritySnapshot, BudgetConfiguration, Criterion,
    PolicySnapshot, MANDATORY_FIELDS,
)

MAKER = 'DEMO-MAKER-01'
CHECKER = 'DEMO-CHECKER-01'
ADMIN = 'DEMO-ADMIN-01'
ENGINE = 'DEMO-EVALUATOR-01'
PRINCIPALS = {MAKER: {'MAKER'}, CHECKER: {'CHECKER'}, ADMIN: {'ADMIN'},
              'DEMO-DUAL-01': {'MAKER', 'CHECKER'}, ENGINE: {'EVALUATOR'}}


def configuration():
    return ApprovalConfiguration(
        PolicySnapshot('DEMO-HTTP-POLICY', 'DEMO-HTTP-1', True, MANDATORY_FIELDS,
                       (Criterion('strategy', 100),), ('mock-1',),
                       ('image/png', 'image/jpeg', 'image/webp'), 5_000_000),
        (BudgetConfiguration('DEMO-HTTP-BUDGET', 'VND', 0, '100000000', 'DEMO-DEPT-01', True),),
        AuthoritySnapshot('DEMO-HTTP-AUTHORITY', 'VND', '100000000', ('DEMO-DEPT-01',),
                          CHECKER, ADMIN, CHECKER, True),
    )


def demo_database(path):
    path = Path(path).resolve()
    if not path.name.startswith('demo-') or path.suffix != '.sqlite3':
        raise ValueError('Demo database must be named demo-*.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
