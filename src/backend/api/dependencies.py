from dataclasses import dataclass
import os

from src.backend.demo import PRINCIPALS, ENGINE, configuration, demo_database
from src.backend.repositories.approval import ApprovalRepository
from src.backend.application.workflow import ApprovalWorkflow


@dataclass(frozen=True)
class Settings:
    app_env: str = 'production'
    database: str = 'runtime/demo-organization.sqlite3'
    cors_origins: tuple[str, ...] = ('http://127.0.0.1:5173', 'http://localhost:5173')
    mock_mode: str = 'pass'

    @classmethod
    def from_environment(cls):
        return cls(os.getenv('APP_ENV', 'production'),
                   os.getenv('DEMO_DATABASE', 'runtime/demo-organization.sqlite3'),
                   tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(',') if x.strip()),
                   os.getenv('DEMO_MOCK_MODE', 'pass'))

    def validate(self):
        if '*' in self.cors_origins:
            raise ValueError('Explicit CORS origins required')
        if self.mock_mode not in ('pass', 'review', 'timeout', 'error', 'malformed'):
            raise ValueError('Unsupported demo mock mode')


def open_workflow(settings):
    repository = ApprovalRepository(demo_database(settings.database))
    return ApprovalWorkflow(repository, configuration(), PRINCIPALS, evaluator_id=ENGINE)
