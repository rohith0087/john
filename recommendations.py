"""Transparent, shared prioritization of evidence-backed research actions.

Scores are editorial heuristics, not buying probabilities. Playbooks are bound to
the full source record so revised content cannot silently inherit an old judgment.
"""
from datetime import date
import hashlib
import json
from pathlib import Path
from intelligence import recommend, canonical_url

PLAYBOOKS = Path(__file__).resolve().parent / 'data' / 'recommendation_playbooks.json'
FIELDS = ('system', 'title', 'source_date', 'event_date', 'category', 'summary',
          'implication', 'source_url', 'profile', 'profile_page', 'evidence_text', 'evidence_status')
METHOD = {
    'name': 'Shared editorial priority',
    'description': 'The same criteria apply to every account. Priority scores help sales teams plan account follow-up; they do not predict a sale.',
    'factors': [
        {'key': 'scope', 'label': 'Scale of the account change', 'maximum': 30},
        {'key': 'breadth', 'label': 'Relevance across supplier categories', 'maximum': 25},
        {'key': 'action', 'label': 'Clarity of the next step', 'maximum': 15},
        {'key': 'recency', 'label': 'Recency', 'maximum': 15},
        {'key': 'evidence', 'label': 'Source verification', 'maximum': 15},
    ],
    'notes': [
        'Collected updates use shared category and project-stage rules. The original six profile examples retain their manually assessed factors.',
        'Recency: 15 points at 0–30 days, 10 at 31–90, 5 at 91–180, and 0 after 180 days. Unknown or future publication dates receive 0.',
        'Collected updates use article publication dates; legacy examples use unverified profile dates. Neither is automatically an event date.',
        'Evidence: 8 points for directly retrieved article text, 4 for imported text, 15 after an explicit source check, and 0 for profile-only evidence. Approval alone does not verify a source.',
        'The sales view includes approved collected updates. Draft preview is explicit. Rejected records remain in content review. Ties use recency, then record ID.',
    ],
}


def fingerprint(record):
    payload = {key: record[key] for key in FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def unique_sources(records):
    """Collapse URL spelling aliases in the feed while retaining every audit record."""
    groups = {}
    for record in records:
        if record.get('schema_version') != 2:
            groups[('legacy', record['id'])] = [record]
            continue
        key = (record['system'], canonical_url(record['source_url']).rstrip('/'))
        groups.setdefault(key, []).append(record)
    result = []
    for key, group in groups.items():
        canonical_id = hashlib.sha256('|'.join(key).encode()).hexdigest()[:24] if key[0] != 'legacy' else None
        primary = next((r for r in group if r['id'] == canonical_id), None)
        result.append(primary or max(group, key=lambda r:(bool(r.get('source_checked')), r.get('recorded_at',''), r.get('version',0))))
    return result


def rank_signals(records, as_of=None, playbooks=None):
    as_of = as_of or date.today()
    if playbooks is None:
        playbooks = json.loads(PLAYBOOKS.read_text(encoding='utf-8'))
    result = []
    for record in unique_sources(records):
        if record['status'] == 'rejected':
            continue
        if record.get('schema_version') == 2:
            result.append(recommend(record, as_of))
            continue
        book = playbooks.get(record['source_url'], {})
        matched = book.get('evidence_digest') == fingerprint(record)
        if not matched:
            book = {
                'headline': record['title'],
                'action_title': 'Check the source before planning account follow-up',
                'rationale': 'This update needs a fresh content review before its sales relevance can be assessed.',
                'steps': ['Check the original source and affected entity.', 'Confirm dates, development stage, and supplier relevance.'],
                'scope': [0, 'Development scope has not been assessed for this version.'],
                'breadth': [0, 'Broad supplier relevance has not been assessed for this version.'],
                'action': [0, 'A specific follow-up has not been assessed for this version.'],
            }
        age = (as_of - date.fromisoformat(record['source_date'])).days
        recency = 15 if 0 <= age <= 30 else 10 if 30 < age <= 90 else 5 if 90 < age <= 180 else 0
        factors = []
        for factor in METHOD['factors']:
            key = factor['key']
            if key == 'recency':
                points = recency
                reason = f"Profile entry dated {record['source_date']} ({age} days before scoring). Article and event dates remain unverified."
            elif key == 'evidence':
                points = 0
                reason = 'Supporting evidence is a profile headline. The original article has not been independently verified.'
            else:
                points, reason = book[key]
            if not isinstance(points, int) or not 0 <= points <= factor['maximum']:
                raise ValueError('Invalid editorial factor points.')
            factors.append(dict(factor, points=points, reason=reason))
        result.append(dict(record,
                           headline=book.get('headline', record['title']),
                           action_title=book['action_title'], rationale=book['rationale'], steps=book['steps'],
                           score=sum(f['points'] for f in factors), factors=factors,
                           assessment_current=matched, evidence_label='Source verification needed'))
    # Stable secondary order, including deterministic tie handling.
    result.sort(key=lambda r: r['id'])
    result.sort(key=lambda r: r['source_date'] or '', reverse=True)
    result.sort(key=lambda r: r['score'], reverse=True)
    return {'recommendations': result, 'method': METHOD, 'scored_on': as_of.isoformat()}
