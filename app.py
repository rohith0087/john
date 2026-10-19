"""Local IDN Watch ingestion and editorial preview. Python standard library only."""
import argparse
from datetime import date, datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import secrets
import sqlite3
import threading
from urllib.parse import urlparse, parse_qs
from recommendations import rank_signals
import collector
from intelligence import validate_facts, normalize_article, canonical_url, clean, recommend, SYSTEM_NAMES, SYSTEM_HOSTS, SYSTEM_REGIONS

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'watch.db'
SYSTEMS = SYSTEM_NAMES
STATUSES = {'pending', 'approved', 'rejected'}
CATEGORIES = {'Expansion', 'Ownership & partnerships', 'Leadership', 'Financial'}


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path=DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY, current_version INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')));
      CREATE TABLE IF NOT EXISTS versions (
        signal_id TEXT NOT NULL REFERENCES signals(id), version INTEGER NOT NULL,
        digest TEXT NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL,
        PRIMARY KEY(signal_id,version));
      CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY, signal_id TEXT NOT NULL, version INTEGER NOT NULL,
        status TEXT NOT NULL, reviewed_at TEXT NOT NULL,
        FOREIGN KEY(signal_id,version) REFERENCES versions(signal_id,version));
    ''')
    return db


def validate(item):
    if not isinstance(item, dict):
        raise ValueError('Each record must be an object.')
    if item.get('schema_version') == 2:
        return validate_facts(item)
    required = {'system','title','source_date','event_date','category','summary',
                'implication','source_url','profile','profile_page','evidence_text','evidence_status'}
    if set(item) != required:
        raise ValueError('Record fields do not match the input schema.')
    for field in required - {'event_date','profile_page'}:
        if not isinstance(item[field], str) or not item[field].strip():
            raise ValueError(f'Missing or invalid {field}.')
    if item['system'] not in SYSTEMS or item['category'] not in CATEGORIES:
        raise ValueError('Unknown system or category.')
    if item['evidence_status'] != 'profile_only':
        raise ValueError('This importer accepts profile-only evidence.')
    date.fromisoformat(item['source_date'])
    if item['event_date'] is not None:
        date.fromisoformat(item['event_date'])
    if type(item['profile_page']) is not int or item['profile_page'] < 1:
        raise ValueError('Invalid PDF page.')
    u = urlparse(item['source_url'])
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('Evidence URL must use HTTPS without credentials.')


def ingest(items, path=DB, origin='import', expected=None):
    if not isinstance(items, list):
        raise ValueError('Input must be an array of records.')
    for item in items:
        validate(item)
    counts = {'created': 0, 'revised': 0, 'unchanged': 0}
    db = connect(path)
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            for item in items:
                identity = item['system'] + '|' + item['source_url'].rstrip('/')
                sid = hashlib.sha256(identity.encode()).hexdigest()[:24]
                payload = json.dumps(item, sort_keys=True, ensure_ascii=False)
                digest = hashlib.sha256(payload.encode()).hexdigest()
                old = db.execute('SELECT s.current_version,v.digest FROM signals s JOIN versions v '
                                 'ON v.signal_id=s.id AND v.version=s.current_version WHERE s.id=?', (sid,)).fetchone()
                if expected and (sid != expected[0] or not old or old['current_version'] != expected[1]):
                    raise RuntimeError('This update changed. Reload it before saving corrections.')
                if old and origin == 'collector':
                    previous = json.loads(db.execute('SELECT payload FROM versions WHERE signal_id=? AND version=?', (sid, old['current_version'])).fetchone()[0])
                    if previous.get('schema_version') == 2 and previous.get('snapshot_id') == item.get('snapshot_id') and (previous.get('editor_note') or previous.get('extraction_version')==item.get('extraction_version')):
                        counts['unchanged'] += 1
                        continue
                if old and old['digest'] == digest:
                    counts['unchanged'] += 1
                    continue
                version = old['current_version'] + 1 if old else 1
                if old:
                    db.execute("UPDATE signals SET current_version=?,status='pending' WHERE id=?", (version,sid))
                    counts['revised'] += 1
                else:
                    db.execute("INSERT INTO signals VALUES (?,1,'pending')", (sid,))
                    counts['created'] += 1
                db.execute('INSERT INTO versions VALUES (?,?,?,?,?)', (sid,version,digest,payload,now()))
    finally:
        db.close()
    return counts


def current(path=DB):
    db = connect(path)
    try:
        rows = db.execute('SELECT s.id,s.status,s.current_version,v.payload,v.recorded_at '
                          'FROM signals s JOIN versions v ON v.signal_id=s.id AND v.version=s.current_version').fetchall()
        result = [dict(json.loads(r['payload']), id=r['id'], status=r['status'],
                       version=r['current_version'], recorded_at=r['recorded_at']) for r in rows]
        return sorted(result, key=lambda x:(x['source_date'] or '',x['id']), reverse=True)
    finally:
        db.close()


def review(sid, version, status, path=DB):
    if status not in STATUSES or type(version) is not int:
        raise ValueError('Invalid review status or version.')
    db = connect(path)
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT current_version FROM signals WHERE id=?', (sid,)).fetchone()
            if not row:
                raise KeyError('Update not found.')
            if row['current_version'] != version:
                raise RuntimeError('This update has changed. Reload before reviewing it.')
            db.execute('UPDATE signals SET status=? WHERE id=?', (status,sid))
            db.execute('INSERT INTO reviews(signal_id,version,status,reviewed_at) VALUES (?,?,?,?)',
                       (sid,version,status,now()))
    finally:
        db.close()


def history(sid, path=DB):
    db = connect(path)
    try:
        versions = [dict(r) for r in db.execute('SELECT version,payload,recorded_at FROM versions WHERE signal_id=? ORDER BY version', (sid,))]
        for v in versions:
            v['payload'] = json.loads(v['payload'])
        reviews = [dict(r) for r in db.execute('SELECT version,status,reviewed_at FROM reviews WHERE signal_id=? ORDER BY id', (sid,))]
        return {'versions':versions,'reviews':reviews}
    finally:
        db.close()


def edit_record(sid, version, changes, path=DB):
    if type(version) is not int or not isinstance(changes, dict):
        raise ValueError('Supply a current version and correction fields.')
    allowed = {'title','summary','entity','category','development_status','publication_date','event_date','metrics','budget','milestones','editor_note','source_checked'}
    if set(changes) - allowed: raise ValueError('Unsupported correction field.')
    before = next((r for r in current(path) if r['id'] == sid), None)
    if not before: raise KeyError('Update not found.')
    if before.get('schema_version') != 2: raise ValueError('Profile examples remain reference records; import the source article before correcting facts.')
    item = {k:v for k,v in before.items() if k not in {'id','status','version','recorded_at'}}
    item.update(changes)
    if not clean(item.get('editor_note')): raise ValueError('Add a short note explaining the correction or source check.')
    item['source_date'] = item['publication_date']
    item['evidence_status'] = 'source_checked' if item['source_checked'] else ('imported_text' if collector.snapshot(item['snapshot_id'],path)['capture_method'] == 'manual_import' else 'source_retrieved')
    if 'entity' in changes: item['entity_match'] = 'reviewed'
    source = collector.snapshot(item['snapshot_id'], path)
    for metric in item['metrics']:
        if clean(metric['evidence']) not in clean(source['body']): raise ValueError('Capacity evidence must be an exact passage from the saved source text.')
        for key in ['baseline','target']:
            value = metric.get(key)
            if value is None: continue
            if metric['unit']=='USD':
                amounts=[float(n.replace(',',''))*(1e9 if unit.lower()=='billion' else 1e6) for n,unit in re.findall(r'\$\s*([\d,.]+)\s*(billion|million)',metric['evidence'],re.I)]
                supported=any(abs(amount-value)<.01 for amount in amounts)
            else:
                supported=bool(re.search(r'\b' + re.escape(f'{int(value):,}') + r'\b|\b' + str(int(value)) + r'\b', metric['evidence']))
            if not supported: raise ValueError('Both compared values must appear in the supporting source passage, with matching units.')
    if item.get('budget'):
        budget = item['budget']
        if type(budget.get('amount')) not in (int,float) or not 0 < budget['amount'] <= 1e12 or budget.get('currency') != 'USD' or clean(budget.get('evidence')) not in clean(source['body']):
            raise ValueError('A budget needs a positive USD amount and a passage from the saved source.')
        supported_amounts=[float(n.replace(',',''))*(1e9 if unit.lower()=='billion' else 1e6) for n,unit in re.findall(r'\$\s*([\d,.]+)\s*(billion|million)',budget['evidence'],re.I)]
        if not any(abs(amount-budget['amount'])<.01 for amount in supported_amounts):
            raise ValueError('The budget amount must appear with matching units in its source passage.')
    if not isinstance(item.get('milestones'),list) or len(item['milestones']) > 3:
        raise ValueError('Up to three source-reported schedule statements are supported.')
    for milestone in item['milestones']:
        if clean(milestone.get('evidence')) not in clean(source['body']) or not clean(milestone.get('date_text')):
            raise ValueError('Schedule statements need supporting text from the saved source.')
    ingest([item], path, origin='editor', expected=(sid, version))
    return next(r for r in current(path) if r['id'] == sid)


def import_article(data, path=DB):
    system = data.get('system')
    if system not in SYSTEMS: raise ValueError('Choose a configured IDN.')
    url = collector.allowed_url(data.get('url', ''))
    # Imports are explicitly attributed to the selected system and reviewed as drafts.
    if urlparse(url).hostname not in SYSTEM_HOSTS[system]:
        raise ValueError('Choose an official source host configured for this IDN.')
    title, text = clean(data.get('title')), str(data.get('text') or '').strip()
    if not 10 <= len(title) <= 600 or not 180 <= len(text) <= 60000:
        raise ValueError('Supply an article headline and 180–60,000 characters of visible article text.')
    published = data.get('publication_date') or None
    if published: date.fromisoformat(published)
    article = collector.save_snapshot({'url':url,'title':title,'text':text,'publication_date':published}, '', 'manual-' + system, 'manual_import', path)
    item, reason = normalize_article(article, system)
    if not item: raise ValueError('This article did not match a supported development: ' + reason)
    counts = ingest([item], path, origin='collector')
    return dict(counts, id=hashlib.sha256((system + '|' + url.rstrip('/')).encode()).hexdigest()[:24])


def serve(port):
    collector.recover_interrupted(DB)
    token = secrets.token_urlsafe(32)
    hosts = {f'127.0.0.1:{port}',f'localhost:{port}'}
    origins = {'http://' + h for h in hosts}

    class Handler(BaseHTTPRequestHandler):
        def respond(self, value, status=200, content_type='application/json; charset=utf-8'):
            raw = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def local_request(self):
            return self.headers.get('Host') in hosts and (
                not self.headers.get('Origin') or self.headers.get('Origin') in origins)

        def do_GET(self):
            if not self.local_request():
                return self.respond({'error':'Local access only.'},403)
            route = urlparse(self.path).path
            if route == '/api/signals':
                return self.respond({'signals':current(),'systems':SYSTEMS,'regions':SYSTEM_REGIONS,'review_token':token})
            if route == '/api/recommendations':
                query = parse_qs(urlparse(self.path).query)
                rows = [r for r in current() if r.get('schema_version') == 2]
                drafts = sum(r['status']=='pending' for r in rows)
                if query.get('include_drafts') != ['1']: rows = [r for r in rows if r['status']=='approved']
                return self.respond(dict(rank_signals(rows), drafts_available=drafts))
            if route == '/api/collection':
                return self.respond(collector.status(DB))
            if route.startswith('/api/snapshots/'):
                try: return self.respond(collector.snapshot(route.split('/')[-1], DB))
                except KeyError: return self.respond({'error':'Source snapshot not found.'},404)
            if route.startswith('/api/signals/') and route.endswith('/brief'):
                sid = route.split('/')[3]
                rows = current()
                record = next((r for r in rows if r['id']==sid), None)
                if not record: return self.respond({'error':'Update not found.'},404)
                recommendation = recommend(record,date.today()) if record.get('schema_version')==2 else None
                entity_words = set(re.findall(r'[a-z]{4,}', record.get('entity','').lower())) - {'adventhealth','healthcare','florida','hospital','healthone'}
                related = [dict(id=r['id'],title=r['title'],source_url=r['source_url'],status=r['status']) for r in rows if r['id']!=sid and r['system']==record['system'] and r['category']==record['category'] and entity_words.intersection(re.findall(r'[a-z]{4,}',r['title'].lower()))]
                return self.respond({'signal':record,'recommendation':recommendation,'related':related[:5]})
            if route == '/api/sources':
                path = ROOT/'data'/'source_inventory.json'
                return self.respond(json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'links':[]})
            if route.startswith('/api/signals/') and route.endswith('/history'):
                result = history(route.split('/')[3])
                return self.respond(result,200 if result['versions'] else 404)
            files = {path:('index.html','text/html') for path in ['/', '/ui', '/ui/', '/recommendations', '/review', '/sources']}
            files.update({'/app.js':('app.js','text/javascript'), '/widgets.js':('widgets.js','text/javascript'), '/widgets.css':('widgets.css','text/css'),
                     '/style.css':('style.css','text/css'),'/favicon.svg':('favicon.svg','image/svg+xml')})
            if route in files:
                name,mime = files[route]
                return self.respond((ROOT/'web'/name).read_bytes(),content_type=mime+'; charset=utf-8')
            self.respond({'error':'Not found.'},404)

        def do_POST(self):
            if not self.local_request() or self.headers.get('X-Review-Token') != token:
                return self.respond({'error':'Reload the local preview before saving.'},403)
            if self.path not in {'/api/review','/api/edit','/api/collect','/api/import'}:
                return self.respond({'error':'Not found.'},404)
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length < 140000:
                    raise ValueError('Invalid request size.')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data,dict):
                    raise ValueError('Expected an object.')
                if self.path == '/api/review':
                    review(data['id'],data['version'],data['status'])
                    return self.respond({'saved':True})
                if self.path == '/api/edit':
                    return self.respond({'saved':True,'signal':edit_record(data['id'], data['version'], data['changes'])})
                if self.path == '/api/import':
                    return self.respond(import_article(data))
                systems = data.get('systems', list(SYSTEMS))
                if not isinstance(systems,list) or not systems or any(s not in SYSTEMS for s in systems):
                    raise ValueError('Select at least one pilot health system to collect.')
                run_id, created = collector.start_run(sorted(set(systems)), DB)
                if created:
                    threading.Thread(target=collector.run_collection, args=(run_id,systems,DB,ingest), daemon=True).start()
                return self.respond({'run_id':run_id,'started':created},202)
            except RuntimeError as e:
                self.respond({'error':str(e)},409)
            except KeyError:
                self.respond({'error':'Missing field or unknown update.'},400)
            except (ValueError,TypeError) as error:
                self.respond({'error':str(error) or 'Invalid request.'},400)

    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'IDN Watch running at http://127.0.0.1:{port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    imp = commands.add_parser('import'); imp.add_argument('file',type=Path)
    web = commands.add_parser('serve'); web.add_argument('--port',type=int,default=8765)
    commands.add_parser('export')
    commands.add_parser('collect')
    args = parser.parse_args()
    if args.command == 'import':
        print(json.dumps(ingest(json.loads(args.file.read_text(encoding='utf-8'))),indent=2))
    elif args.command == 'export':
        print(json.dumps(current(),indent=2))
    elif args.command == 'collect':
        run_id, created = collector.start_run(list(SYSTEMS), DB)
        if created: collector.run_collection(run_id,list(SYSTEMS),DB,ingest)
        print(json.dumps(collector.status(DB),indent=2))
    else:
        serve(args.port)
