from dataclasses import dataclass
import os

from src.backend.demo import PRINCIPALS, ENGINE, configuration, demo_database, DEPARTMENT_CHECKERS
from src.backend.repositories.approval import ApprovalRepository
from src.backend.application.workflow import ApprovalWorkflow


@dataclass(frozen=True)
class Settings:
    app_env: str = 'production'
    database: str = 'runtime/demo-organization.sqlite3'
    cors_origins: tuple[str, ...] = ('http://127.0.0.1:5173', 'http://localhost:5173')
    mock_mode: str = 'pass'
    public_judge_only: bool = False

    @classmethod
    def from_environment(cls):
        public_judge_only = os.getenv('PUBLIC_JUDGE_ONLY', 'false').strip().lower()
        if public_judge_only not in {'true', 'false'}:
            raise ValueError('PUBLIC_JUDGE_ONLY must be true or false.')
        return cls(os.getenv('APP_ENV', 'production'),
                   os.getenv('DEMO_DATABASE', 'runtime/demo-organization.sqlite3'),
                   tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(',') if x.strip()),
                   os.getenv('DEMO_MOCK_MODE', 'pass'),
                   public_judge_only == 'true')

    def validate(self):
        if self.public_judge_only and self.app_env != 'demo':
            raise ValueError('PUBLIC_JUDGE_ONLY requires APP_ENV=demo.')
        if '*' in self.cors_origins:
            raise ValueError('Explicit CORS origins required')
        if self.mock_mode not in ('pass', 'review', 'timeout', 'error', 'malformed'):
            raise ValueError('Unsupported demo mock mode')


def open_workflow(settings):
    repository = ApprovalRepository(demo_database(settings.database))
    return ApprovalWorkflow(repository, configuration(), PRINCIPALS, evaluator_id=ENGINE,
                            department_checkers=DEPARTMENT_CHECKERS)
