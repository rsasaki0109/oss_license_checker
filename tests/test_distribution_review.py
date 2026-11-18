from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import ValidationError
from scripts.validate_distribution_review import validate


ROOT = Path(__file__).resolve().parents[1]


class DistributionReviewAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.draft = json.loads((ROOT / 'examples/validation/calibrex/distribution-review.draft.json').read_text())

    def completed_record(self):
        record = deepcopy(self.draft)
        record['distribution'].update(kind='container', scope_confirmed=True, artifact_sha256='a' * 64)
        record['components'][0]['inclusion'] = 'bundled'
        item = record['requirements'][1]
        item.update(state='done', reviewed_by='example-reviewer', reviewed_at='2026-11-18T00:00:00Z')
        return record

    def test_calibrex_draft_remains_open_without_fabricating_a_distribution_decision(self):
        result = validate(self.draft)
        self.assertEqual(result['open_requirements'], 5)
        self.assertEqual(self.draft['distribution']['kind'], 'source')
        self.assertFalse(self.draft['distribution']['scope_confirmed'])
        self.assertEqual(result['distribution_readiness'], 'not_assessed')

    def test_collected_mcap_license_does_not_complete_the_distribution_requirement(self):
        record = self.completed_record()
        with self.assertRaisesRegex(ValueError, 'Collected license text alone'):
            validate(record)

    def test_fulfillment_evidence_is_bound_to_the_actual_artifact(self):
        record = self.completed_record()
        record['evidence'].append({'id':'inspection', 'kind':'artifact_inspection',
            'location':'example:artifact-check', 'sha256':'b'*64, 'artifact_sha256':'a'*64,
            'description':'Example record: inspected placement of notice in this artifact'})
        record['requirements'][1]['evidence_refs'].append('inspection')
        self.assertEqual(validate(record)['distribution_readiness'], 'not_assessed')
        record['distribution']['artifact_sha256'] = 'c'*64
        with self.assertRaisesRegex(ValueError, 'fulfillment evidence'):
            validate(record)

    def test_unconfirmed_scope_cannot_close_requirements(self):
        for state in ['done', 'not_applicable']:
            record = self.completed_record()
            record['distribution']['scope_confirmed'] = False
            record['requirements'][1]['state'] = state
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, 'Confirm the distribution scope'):
                validate(record)

    def test_unknown_inclusion_cannot_be_dismissed(self):
        record = self.completed_record()
        record['components'][0]['inclusion'] = 'unknown'
        record['requirements'][1]['state'] = 'not_applicable'
        with self.assertRaisesRegex(ValueError, 'Unknown inclusion'):
            validate(record)

    def test_completed_requirement_needs_review_attribution(self):
        record = self.completed_record()
        record['requirements'][1]['reviewed_by'] = None
        with self.assertRaises(ValidationError):
            validate(record)

    def test_review_timestamp_requires_a_real_datetime_and_timezone(self):
        for timestamp in ['2026-99-99T00:00:00Z', '2026-11-18T00:00:00']:
            record = self.completed_record()
            record['requirements'][1]['reviewed_at'] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises((ValueError, ValidationError)):
                validate(record)

    def test_dangling_references_duplicates_and_unknown_fields_are_rejected(self):
        record = deepcopy(self.draft)
        record['requirements'][0]['component_ref'] = 'nonexistent'
        with self.assertRaisesRegex(ValueError, 'Unknown component'):
            validate(record)
        record = deepcopy(self.draft)
        record['evidence'].append(record['evidence'][0])
        with self.assertRaisesRegex(ValueError, 'Duplicate IDs'):
            validate(record)
        record = deepcopy(self.draft)
        record['distribution']['approved'] = True
        with self.assertRaises(ValidationError):
            validate(record)
