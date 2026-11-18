"""Validate a design-stage distribution review record, without approving a release."""

import argparse
from datetime import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]


def validate(document):
    schema = json.loads((ROOT / 'schemas/distribution-review.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    if document['distribution']['scope_confirmed'] and document['distribution']['kind'] == 'undecided':
        raise ValueError('A confirmed scope must specify a distribution kind')
    components = {item['id']: item for item in document['components']}
    evidence = {item['id']: item for item in document['evidence']}
    for collection in ['components', 'evidence', 'requirements']:
        ids = [item['id'] for item in document[collection]]
        if len(ids) != len(set(ids)):
            raise ValueError(f'Duplicate IDs in {collection}')
    for item in [*document['components'], *document['requirements']]:
        for reference in item['evidence_refs']:
            if reference not in evidence:
                raise ValueError(f'Unknown evidence reference: {reference}')
    for item in document['requirements']:
        if item['reviewed_at'] is not None:
            timestamp = datetime.fromisoformat(item['reviewed_at'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None or 'T' not in item['reviewed_at']:
                raise ValueError('Review timestamps require an ISO datetime with a timezone')
        if item['component_ref'] not in components:
            raise ValueError(f'Unknown component: {item["component_ref"]}')
        if item['state'] in {'done', 'not_applicable'} and not document['distribution']['scope_confirmed']:
            raise ValueError('Confirm the distribution scope before closing requirements')
        if item['state'] == 'not_applicable' and components[item['component_ref']]['inclusion'] == 'unknown':
            raise ValueError('Unknown inclusion cannot be marked not applicable')
        if item['state'] not in {'done', 'not_applicable'}:
            continue
        component = components[item['component_ref']]
        if component['inclusion'] == 'unknown' or (item['state'] == 'done' and component['review_state'] != 'reviewed'):
            raise ValueError('Resolve component inclusion and license review before marking done')
        digest = document['distribution']['artifact_sha256']
        if digest is None:
            raise ValueError('A completed requirement needs a specific distribution artifact hash')
        if not any(evidence[ref]['kind'] in {'artifact_inspection', 'fulfillment_record'}
                   and evidence[ref]['artifact_sha256'] == digest for ref in item['evidence_refs']):
            raise ValueError('Collected license text alone is not fulfillment evidence for this artifact')
    return {'record_valid': True, 'distribution_readiness': 'not_assessed',
            'open_requirements': sum(item['state'] not in {'done', 'not_applicable'} for item in document['requirements'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    # Validation errors deliberately fail this development tool; no records are edited.
    print(json.dumps(validate(json.loads(args.record.read_text(encoding='utf-8'))), indent=2))


if __name__ == '__main__':
    main()
