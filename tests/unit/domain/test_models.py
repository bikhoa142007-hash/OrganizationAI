import unittest
from dataclasses import FrozenInstanceError

from src.shared.validation import ValidationError, canonical_hash
from src.backend.domain.models import AttachmentManifest, MarketingPlan, Actor


class DomainTests(unittest.TestCase):
    def test_manifest_is_immutable_and_strict(self):
        item = AttachmentManifest('a', 'a' * 64, 'image/png', 12)
        with self.assertRaises(FrozenInstanceError):
            item.byte_size = 13
        for size in (True, -1, '12'):
            with self.subTest(size=size), self.assertRaises(ValidationError):
                AttachmentManifest('a', 'a' * 64, 'image/png', size)

    def test_draft_can_be_incomplete_and_payload_is_deeply_frozen(self):
        payload = {'notes': ['synthetic']}
        plan = MarketingPlan('p', None, None, payload, ())
        payload['notes'].append('changed')
        self.assertEqual(plan.payload['notes'], ('synthetic',))
        with self.assertRaises(TypeError):
            plan.payload['x'] = 1

    def test_canonical_hash_uses_rfc8785(self):
        self.assertEqual(canonical_hash({'b': 1.0, 'a': -0.0}),
                         canonical_hash({'a': 0, 'b': 1}))

    def test_actor_rejects_extra_fields_and_blank_identity(self):
        with self.assertRaises(ValidationError):
            Actor.from_dict({'actor_type': 'SYSTEM', 'actor_id': 'x', 'admin': True})
        with self.assertRaises(ValidationError):
            Actor('HUMAN', ' ')
