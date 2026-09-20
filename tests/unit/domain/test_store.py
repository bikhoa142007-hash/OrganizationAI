import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.backend.domain.store import SnapshotStore
from src.backend.domain.models import MarketingPlan
from src.shared.validation import ValidationError


class SnapshotStoreTests(unittest.TestCase):
    def test_clean_migration_repeatable_seed_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wp2.sqlite'
            plan = MarketingPlan('synthetic', 1, 1, {}, ())
            with SnapshotStore(path) as store:
                store.migrate()
                store.migrate()
                store.append('plan', 'synthetic-v1', plan)
                store.append('plan', 'synthetic-v1', plan)
            with SnapshotStore(path) as store:
                self.assertEqual(store.read('plan', 'synthetic-v1'), plan.to_dict())
                with self.assertRaises(ValidationError):
                    store.append('plan', 'synthetic-v1', MarketingPlan('synthetic', 1, 1, {'changed': True}, ()))
                with self.assertRaises(sqlite3.IntegrityError):
                    store.connection.execute("DELETE FROM snapshots")

    def test_batch_is_atomic_on_conflict(self):
        with SnapshotStore(':memory:') as store:
            store.migrate()
            store.append('policy', 'existing', {'version': 1})
            with self.assertRaises(ValidationError):
                store.append_many((('policy', 'new', {'version': 2}),
                                   ('policy', 'existing', {'version': 3})))
            self.assertIsNone(store.read('policy', 'new'))
