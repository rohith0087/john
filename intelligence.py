"""Small, explainable extraction and prioritization rules for selected IDNs."""
from datetime import date
import math
import re
from urllib.parse import urlparse, urlunparse

SYSTEM_NAMES = {'adventhealth': 'AdventHealth', 'hca': 'HCA Healthcare',
                'piedmont': 'Piedmont Healthcare', 'wellstar': 'Wellstar Health System', 'novant': 'Novant Health'}
SYSTEM_HOSTS = {
    'adventhealth': {'www.adventhealth.com','www.prnewswire.com'},
    'hca': {'www.hcafloridahealthcare.com','investor.hcahealthcare.com','hcahealthcaretoday.com'},
    'piedmont': {'www.piedmont.org'}, 'wellstar': {'www.wellstar.org'}, 'novant': {'www.novanthealth.org'},
}
SYSTEM_REGIONS = {'adventhealth':'Multistate · Florida collection', 'hca':'Multistate · Florida collection',
                  'piedmont':'Georgia', 'wellstar':'Georgia', 'novant':'North & South Carolina'}
CATEGORIES = {'Expansion', 'Ownership & partnerships', 'Leadership', 'Financial'}
STAGES = {'announced', 'planned', 'underway', 'completed', 'unknown'}
ALIASES = {
    'adventhealth': ['AdventHealth Carrollwood', 'AdventHealth Daytona Beach', 'AdventHealth Winter Garden',
                     'AdventHealth Wesley Chapel', 'AdventHealth Louisville', 'AdventHealth Lake Nona',
                     'AdventHealth Lake Wales', 'AdventHealth Manchester', 'AdventHealth Sebring'],
    'hca': ['HCA Florida Raulerson Hospital', 'HCA Florida Highlands Hospital', 'HCA Florida Aventura Hospital', 'HCA Florida Brandon Hospital',
            'HCA Florida Blake Hospital', 'HCA Florida North Florida Hospital', 'HCA HealthONE'],
    'piedmont': ['Piedmont Newton', 'Piedmont Walton', 'Piedmont Henry', 'Piedmont Rockdale', 'Piedmont Atlanta', 'Piedmont Macon'],
    'wellstar': ['Wellstar Kennestone Regional Medical Center','Wellstar Columbia County Medical Center','Wellstar Paulding Medical Center', 'Stephens County Hospital', 'Mountain Lakes Medical Center'],
    'novant': ['Novant Health New Hanover Regional Medical Center','New Hanover Regional Medical Center','Novant Health Scotts Hill Medical Center','Novant Health Leland Medical Center'],
}


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def canonical_url(value):
    u = urlparse(value)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError('Use an HTTPS source URL without credentials or a custom port.')
    # Preserve reserved separators, but normalize equivalent slug spellings.
    def decode_slug(match):
        char = chr(int(match[0][1:], 16))
        return char if char.isascii() and (char.isalnum() or char in '-._~$') else match[0].upper()
    path = re.sub(r'%[0-9a-fA-F]{2}', decode_slug, u.path)
    return urlunparse(('https', u.hostname.lower(), re.sub('/+', '/', path).rstrip('/') or '/', '', '', ''))


def quote(value, limit=320):
    return clean(value)[:limit]


def sentences(text):
    return [clean(s) for s in re.split(r'(?<=[.!?])\s+|\n+', text) if len(clean(s)) > 15]


def classify(title, text):
    t = title.lower()
    if re.search(r'\b(?:adds?|acquires?|launch|expand|introduc)',t) and re.search(r'technology|treatment|robotic|thrombectomy|hyperbaric|transplant program|new physicians|new specialists',t):
        return 'Expansion', 'Headline describes a service capability; this does not establish a construction project.'
    checks = [
        ('Ownership & partnerships', r'acquisit|acquir|merger|joint venture|partnership|agreement to (?:buy|purchase)'),
        ('Leadership', r'appoint|(?:names?|named) .{0,70}(?:chief|ceo|cfo|president|vice president)|leadership change'),
        ('Financial', r'(?:financial|quarter|annual).{0,20}results|earnings|operating margin|revenue|senior notes|capital spending'),
        ('Expansion', r'expan(?:sion|d)|new hospital|relocation hospital|patient tower|breaks? ground|groundbreaking|construction|new emergency|first patients.{0,80}(?:hospital|medical center)|(?:opens?|opened|opening).{0,80}(?:building|hospital|medical center|health campus|new locations|clinic|urgent care)|(?:approved to build|will build|to build its first).{0,60}(?:hospital|medical center)'),
    ]
    for category, pattern in checks:
        if re.search(pattern, t):
            # A donation or community event mentioning "expand" is not a facility project.
            if category == 'Expansion' and re.search(r'donat|fundrais|charit|volunteer|awards?', t) and not re.search(r'hospital|tower|construction|department', t):
                return None, 'Community/fundraising headline without a clear facility development.'
            return category, 'Headline contains a bounded supplier-relevant development rule.'
    return None, 'No supported expansion, transaction, leadership, or financial development in the headline.'


def entity_for(system, title, text):
    haystack = title + ' ' + text[:1800]
    for scope in [title,text[:1800]]:
        for entity in ALIASES[system]:
            if entity.lower() in scope.lower() or (entity == 'HCA Florida Raulerson Hospital' and 'raulerson' in title.lower()):
                return entity, 'matched'
    if system == 'adventhealth' and 'the villages' in haystack.lower():
        return 'AdventHealth · The Villages project', 'matched'
    return SYSTEM_NAMES[system], 'system_only'


def development_stage(title, text):
    if re.search(r'first patients (?:receive|treated)|welcomes? (?:its )?first patients',title,re.I): return 'completed'
    if re.search(r'\b(completes?|completed|opens?|opened|celebrates? opening)\b', title, re.I):
        return 'completed'
    if re.search(r'breaks? ground|groundbreaking|construction.{0,40}(begins|underway|milestone)|under construction', title, re.I):
        return 'underway'
    if re.search(r'plan|will |expected|anticipated|proposed|opening to patients|approved to build', title + ' ' + text[:2000], re.I):
        return 'planned'
    return 'announced'


def extract_metrics(text, entity, stage):
    metrics = []
    for sentence in sentences(text):
        # Only compare two values from one sentence referring to the same capacity.
        match = re.search(r'from\s+([\d,]+)(?:\s+(?:inpatient\s+)?beds?)?\s+to\s+([\d,]+)(?:\s+(?:inpatient\s+)?beds?)?', sentence, re.I)
        context = sentence[max(0,match.start()-35):match.start()] + sentence[match.end():match.end()+24] if match else ''
        if match and re.search(r'\bbeds?\b|inpatient capacity', context, re.I):
            before, after = [int(v.replace(',', '')) for v in match.groups()]
            if 0 <= before < after <= 10000:
                scope = 'Emergency-department beds' if re.search(r'emergency|\bER\b', sentence) else 'Inpatient beds'
                metrics.append({'label': scope, 'unit': 'beds', 'baseline': before, 'target': after,
                                'basis': 'reported' if stage == 'completed' else 'planned', 'entity': entity,
                                'evidence': quote(sentence)})
                break
    if not metrics:
        for sentence in sentences(text):
            match = re.search(r'\b(\d{1,4})\s+(?:new|additional)\s+(inpatient\s+|hospital\s+|patient care\s+|intensive.{0,25}care\s+)?beds\b', sentence, re.I)
            addition = re.search(r'\badd(?:ing)?\s+(\d{1,4})\s+(?:inpatient\s+)?(?:hospital\s+)?beds\b',sentence,re.I)
            if match or addition:
                value = int((match or addition).group(1))
                if 0 < value <= 10000:
                    metrics.append({'label': 'Additional inpatient beds' if 'inpatient' in sentence.lower() else 'Additional beds',
                                    'unit': 'beds', 'baseline': None, 'target': value,
                                    'basis': 'reported' if stage == 'completed' else 'planned',
                                    'entity': entity, 'evidence': quote(sentence)})
                    break
    return metrics


def extract_financial_comparison(text, entity):
    for sentence in sentences(text):
        if re.search(r'^Revenues?\b', sentence, re.I) and re.search(r'compared (?:to|with)|versus', sentence, re.I):
            amounts = re.findall(r'\$\s*([\d,.]+)\s*(billion|million)\b', sentence, re.I)
            if len(amounts)==2 and re.search(r'prior.year|previous year|same period|20\d\d', sentence, re.I):
                values=[round(float(number.replace(',',''))*(1e9 if unit.lower()=='billion' else 1e6),2) for number,unit in amounts]
                return [{'label':'Reported revenue comparison','unit':'USD','baseline':values[1],'target':values[0],
                         'basis':'reported','entity':entity,'evidence':quote(sentence),
                         'baseline_label':'Comparison period (source)','target_label':'Reporting period (source)'}]
    return []


def extract_budget(text):
    for sentence in sentences(text):
        match = re.search(r'\$\s*([\d,.]+)\s*(million|billion)\b', sentence, re.I)
        if re.search(r'master facility plan|regional (?:investment|plan)|strategic plan',sentence,re.I): continue
        if re.search(r'\bsince\b.{0,160}\b(?:invested|investment)\b|\b(?:over|during) the (?:past|last) \w+ years\b',sentence,re.I): continue
        if match and re.search(r'project|expansion|invest|construction|tower|hospital', sentence, re.I):
            return {'amount': float(match.group(1).replace(',', '')) * (1e9 if match.group(2).lower() == 'billion' else 1e6),
                    'currency': 'USD', 'qualifier': 'nearly' if re.search(r'(?:nearly|almost)\s+\$', sentence, re.I) else 'approximately' if re.search(r'(?:approximately|about)\s+\$',sentence,re.I) else 'more_than' if re.search(r'(?:more than|over|upwards of)\s+\$', sentence, re.I) else 'reported',
                    'evidence': quote(sentence)}
    return None


def extract_milestones(text):
    result = []
    for sentence in sentences(text):
        if re.search(r'expected|anticipated|scheduled|set to|by 20\d\d|opening to patients', sentence, re.I) and re.search(r'open|complet|finish|begin|construction|welcome patients', sentence, re.I):
            years = re.findall(r'\b20\d\d\b', sentence)
            if years and len(sentence) <= 500:
                result.append({'label': 'Reported schedule', 'date_text': sentence[:300], 'basis': 'planned', 'year': int(years[-1]), 'evidence': quote(sentence)})
        if len(result) == 3:
            break
    return result


def normalize_article(article, system):
    title, text = clean(article['title']), article['text']
    category, relevance = classify(title, text)
    if not category:
        return None, relevance
    entity, match = entity_for(system, title, '' if category=='Leadership' else text)
    if category=='Leadership' and match=='system_only': match='system_level'
    stage = development_stage(title, text)
    if category in {'Leadership','Financial'}: stage='announced'
    kind = 'service_capability' if category=='Expansion' and re.search(r'technology|treatment|robotic|thrombectomy|hyperbaric|transplant program|\bphysicians?\b|\bspecialists?\b', title, re.I) and not re.search(r'tower|construction|hospital expansion',title,re.I) else 'facility_project' if category=='Expansion' else 'organizational'
    if kind=='service_capability' and stage!='completed': stage='announced'
    metrics = extract_metrics(text, entity, stage) if category == 'Expansion' else []
    if category == 'Financial': metrics = extract_financial_comparison(text,entity)
    budget = extract_budget(text) if category == 'Expansion' else None
    warnings = ['Rule-based extraction: review the facts against the saved source before approval.']
    if match == 'system_only': warnings.append('Facility not matched to the pilot dictionary; this is assigned at system level.')
    if not article.get('publication_date'): warnings.append('Article publication date was not found; collection time is not a substitute.')
    if category == 'Expansion' and not metrics: warnings.append('No comparable capacity figures were extracted. A growth percentage is unavailable.')
    if re.search(r'seeks? (?:state )?approval|applied for state approval',title+' '+text[:600],re.I): warnings.append('The source describes a pending approval application. Proposed capacity is not authorized or operational capacity.')
    keywords = {'Expansion': r'expan|construction|beds|tower|project|capacity', 'Ownership & partnerships': r'acquir|acquisit|venture|partner|agreement', 'Leadership': r'appoint|chief|president|ceo', 'Financial': r'revenue|margin|earnings|results|financial'}
    supporting = [s for s in sentences(text) if re.search(keywords[category], s, re.I)]
    if category=='Expansion':
        summary=f'The source reports an expansion involving {entity}; its extracted stage is {stage}.' if kind!='service_capability' else f'The source reports a new or expanded service capability at {entity}. No construction project or purchasing budget is established by this update.'
        if metrics:
            m=metrics[0]
            summary+=f" It describes {m['target']} {m['label'].lower()}"+(f", compared with a baseline of {m['baseline']}." if m['baseline'] is not None else '; a comparable baseline was not found.')
        if budget: summary+=f" Reported project investment is { {'more_than':'more than ','nearly':'nearly ','approximately':'approximately '}.get(budget['qualifier'],'') }${budget['amount']/1000000:g} million."
    elif category=='Financial': summary=f'The source reports financial results for {entity}. Any extracted comparison retains the source statement and needs fiscal-period review.'
    elif category=='Leadership': summary=f'The source reports a leadership appointment involving {entity}. Confirm roles, effective dates, and purchasing responsibility before changing account contacts.'
    else: summary=f'The source reports an ownership or partnership development involving {entity}. Confirm the affected organizations, transaction stage, and contracting implications.'
    return {
        'schema_version': 2, 'extraction_version': 'rules-2026-10-21.1', 'input_kind': 'collected', 'system': system, 'title': title,
        'source_date': article.get('publication_date'), 'publication_date': article.get('publication_date'),
        'event_date': None, 'category': category, 'summary': summary, 'implication': '',
        'source_url': canonical_url(article['url']), 'profile': None, 'profile_page': None,
        'evidence_text': quote(supporting[0] if supporting else title),
        'evidence_status': 'source_retrieved' if article.get('capture_method') != 'manual_import' else 'imported_text',
        'entity': entity, 'entity_match': match, 'development_status': stage, 'metrics': metrics,
        'development_kind': kind,
        'budget': budget, 'milestones': extract_milestones(text) if category in {'Expansion','Ownership & partnerships'} else [], 'extraction_warnings': warnings,
        'source_id': article['source_id'], 'snapshot_id': article['snapshot_id'],
        'editor_note': '', 'source_checked': False,
    }, relevance


def validate_facts(item):
    if item.get('schema_version') != 2 or item.get('system') not in SYSTEM_NAMES or item.get('category') not in CATEGORIES:
        raise ValueError('Invalid normalized development.')
    if item.get('development_status') not in STAGES:
        raise ValueError('Invalid development status.')
    if item.get('evidence_status') not in {'source_retrieved', 'imported_text', 'source_checked'}:
        raise ValueError('Invalid evidence state.')
    if type(item.get('source_checked')) is not bool or item['source_checked'] != (item['evidence_status'] == 'source_checked'):
        raise ValueError('Source-check flag and evidence status must agree.')
    for field in ['title', 'summary', 'entity', 'source_id', 'snapshot_id', 'evidence_text']:
        if not isinstance(item.get(field), str) or not 0 < len(item[field]) <= (3000 if field == 'summary' else 1000):
            raise ValueError('Missing or oversized ' + field)
    for key in ['source_date', 'publication_date', 'event_date']:
        if item.get(key) is not None:
            date.fromisoformat(item[key])
    if item['source_date'] != item['publication_date']:
        raise ValueError('Publication dates must agree.')
    canonical_url(item['source_url'])
    if not isinstance(item.get('metrics'), list) or len(item['metrics']) > 4:
        raise ValueError('Up to four capacity measurements are supported.')
    for metric in item['metrics']:
        if metric.get('unit') not in {'beds','USD'} or metric.get('basis') not in {'planned', 'reported'}:
            raise ValueError('Use beds or USD with a planned or reported basis.')
        if metric.get('entity') != item['entity']:
            raise ValueError('A capacity comparison must refer to the same facility.')
        for key in ['baseline', 'target']:
            value = metric.get(key)
            if value is None and key == 'baseline': continue
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= (10000 if metric['unit']=='beds' else 1e12) or (metric['unit']=='beds' and value!=int(value)):
                raise ValueError('Use nonnegative, finite figures; bed counts must be whole numbers up to 10,000.')
        if metric['unit']=='beds' and metric['target']<=0:
            raise ValueError('The displayed bed count must be positive.')
        if metric['unit']=='beds' and metric.get('baseline') is not None and metric['target'] <= metric['baseline']:
            raise ValueError('Planned/expanded capacity must exceed the baseline.')
        if not clean(metric.get('evidence')) or not clean(metric.get('label')):
            raise ValueError('Capacity figures need a label and supporting source text.')


def recommend(record, as_of):
    category, stage, entity = record['category'], record['development_status'], record['entity']
    metrics, budget = record.get('metrics', []), record.get('budget')
    if category == 'Expansion':
        scope = 30 if re.search(r'new (?:[\w-]+\s+){0,3}hospital\b(?!\s+beds?)', record['title'], re.I) else 25 if 'tower' in record['title'].lower() else 20
        breadth = 24 if metrics else 18
        if stage == 'completed':
            action = f'Assess ongoing supply and service needs at {entity}'
            why = 'The reported expansion is complete. Check operating supply, service, and replenishment needs; construction purchasing may already be closed.'
        else:
            action = f'Confirm project timing and purchasing responsibility at {entity}'
            why = 'The reported facility project may affect equipment, supply, or service needs. Product fit, budget availability, and an active purchasing window still need qualification.'
        steps = ['Confirm the latest project status against the saved article and newer updates.', 'Identify facility versus system purchasing responsibility and the relevant contacts.', 'Check product fit and any published procurement milestones before outreach.']
        if record.get('development_kind')=='service_capability':
            scope, breadth = 12,12
            action = f'Check the service change and product fit at {entity}'
            why = 'A clinical service or technology capability is reported. Check relevance to your product category; a hospital construction project or new purchasing budget is not established.'
            steps = ['Confirm the clinical service, team, or technology being introduced.', 'Check whether your product category supports that service.', 'Identify the relevant service-line and purchasing contacts before outreach.']
        if any('pending approval' in warning for warning in record.get('extraction_warnings',[])):
            action=f'Check approval status and planning contacts at {entity}'
            why='The source describes proposed capacity requiring state approval. Confirm approval, scope, and timing before treating it as an active purchasing opportunity.'
    elif category == 'Ownership & partnerships':
        scope, breadth = 25, 21
        if re.search(r'college|education|training', record['title'], re.I): scope, breadth = 18, 8
        action = f'Check account and contracting changes at {entity}'
        why = 'An ownership or partnership change can affect contracting relationships. Shared purchasing and new supplier demand are not established by the announcement alone.'
        steps = ['Confirm the transaction stage and affected organizations.', 'Check for explicit changes in contracting or purchasing ownership.', 'Update account planning only after those changes are supported.']
    elif category == 'Leadership':
        scope, breadth = 15, 16
        action = f'Confirm new responsibilities before updating contacts at {entity}'
        why = 'A leadership appointment may change account relationships. Purchasing authority and relevance to your category still need checking.'
        steps = ['Verify names, roles, and effective dates.', 'Identify responsibility for your product category.', 'Update the account contact map with the confirmed information.']
    else:
        scope, breadth = 20, 18
        action = f'Review the financial update before revising the account plan for {entity}'
        why = 'Financial results provide account context. Revenue or margin changes alone do not establish a supplier budget or intent to buy.'
        steps = ['Check the fiscal period, units, and comparable figures.', 'Separate historical results from management guidance.', 'Look for an explicit link to capital or operating priorities before outreach.']
    action_points = 13 if metrics or budget else 10
    if stage == 'completed' and category == 'Expansion': action_points = 9
    published = record.get('publication_date')
    age = (as_of - date.fromisoformat(published)).days if published else None
    recency = 15 if age is not None and 0 <= age <= 30 else 10 if age is not None and 30 < age <= 90 else 5 if age is not None and 90 < age <= 180 else 0
    evidence = 15 if record.get('source_checked') else 8 if record['evidence_status'] == 'source_retrieved' else 4
    reasons = [
        ('scope', 'Scale of the account change', 30, scope, f'{category} rule applied to a {stage} development. Reported amounts and capacity remain tied to their source.'),
        ('breadth', 'Relevance across supplier categories', 25, breadth, 'General supplier relevance assessed by development type; this is not product-specific personalization.'),
        ('action', 'Clarity of the next step', 15, action_points, 'Specific capacity/budget evidence supports qualification.' if metrics or budget else 'A category-level follow-up is available; scope and timing may still be unclear.'),
        ('recency', 'Article recency', 15, recency, f'Article publication date: {published}.' if published else 'No publication date extracted; freshness receives zero points.'),
        ('evidence', 'Source verification', 15, evidence, 'Source checked during local content review.' if record.get('source_checked') else 'Selected source text was imported manually; extracted facts need review.' if record['evidence_status'] == 'imported_text' else 'Article text was retrieved; extracted facts have not yet been checked by a reviewer.'),
    ]
    factors = [dict(key=k, label=l, maximum=m, points=p, reason=r) for k,l,m,p,r in reasons]
    return dict(record, headline=record['title'], action_title=action, rationale=why, steps=steps,
                factors=factors, score=sum(f['points'] for f in factors), assessment_current=True,
                evidence_label='Source checked' if record.get('source_checked') else 'Source check pending',
                visual=build_visual(record), scoring_basis='rules-v1')


def build_visual(record):
    metrics = record.get('metrics', [])
    if metrics:
        m = metrics[0]
        if m['unit']=='USD':
            return dict(m,type='financial',title=m['label'],source_url=record['source_url'],
                        growth_percent=round((m['target']-m['baseline'])/m['baseline']*100,1) if m['baseline'] else None,
                        note='Two comparable amounts from one source statement. Fiscal-period comparability needs review; no revenue forecast or purchasing budget is inferred.')
        baseline, target = m['baseline'], m['target']
        delta = target - baseline if baseline is not None else None
        growth = round(delta / baseline * 100, 1) if baseline and delta is not None else None
        return {'type': 'capacity', 'title': m['label'], 'entity': m['entity'], 'unit': m['unit'],
                'baseline': baseline, 'target': target, 'change': delta, 'growth_percent': growth,
                'basis': m['basis'], 'evidence': m['evidence'], 'source_url': record['source_url'],
                'scenario_available': baseline is not None and baseline > 0 and m['basis'] == 'planned', 'budget':record.get('budget'), 'milestones':record.get('milestones',[]),
                'note': 'A comparison of source-reported capacity, not a revenue or demand forecast.' + (' Planned capacity is not confirmed operational capacity.' if m['basis'] == 'planned' else ' Completion and capacity are reported by the source as of its publication date.')}
    return {'type': 'timeline', 'title': 'Development timeline', 'entity': record['entity'],
            'publication_date': record.get('publication_date'), 'stage': record['development_status'],
            'milestones': record.get('milestones', []), 'budget': record.get('budget'),
            'note': 'Only source-reported dates and amounts are shown. No growth curve is inferred from an announcement.'}
