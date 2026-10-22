"""Bounded public-page collection, immutable source snapshots, and refresh history."""
from datetime import datetime, timezone, date
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from urllib.parse import urljoin, urlparse
import urllib.request

from intelligence import canonical_url, clean, normalize_article, SYSTEM_HOSTS
import openai_pipeline

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'data' / 'collectors.json'
ALLOWED = set().union(*SYSTEM_HOSTS.values())


def now():
    return datetime.now(timezone.utc).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path):
    db = sqlite3.connect(path, timeout=15, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS collection_runs (
        id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
        status TEXT NOT NULL, systems TEXT NOT NULL, totals TEXT NOT NULL);
      CREATE UNIQUE INDEX IF NOT EXISTS one_running_collection ON collection_runs ((1)) WHERE status='running';
      CREATE TABLE IF NOT EXISTS collection_items (
        id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, source_id TEXT NOT NULL, url TEXT NOT NULL,
        status TEXT NOT NULL, message TEXT NOT NULL, signal_id TEXT, recorded_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS article_snapshots (
        id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
        publication_date TEXT, captured_at TEXT NOT NULL, capture_method TEXT NOT NULL,
        source_id TEXT NOT NULL, body_hash TEXT NOT NULL, raw_html TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS collected_articles (
        url TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, last_fetched_at TEXT NOT NULL,
        relevance TEXT NOT NULL, source_id TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS source_health (
        source_id TEXT PRIMARY KEY, last_attempt TEXT, last_success TEXT, last_error TEXT);
    ''')
    return db


def allowed_url(url):
    result = canonical_url(url)
    if urlparse(result).hostname not in ALLOWED:
        raise ValueError('This source host is outside the pilot allowlist.')
    if urlparse(url).path.endswith('/') and not result.endswith('/'):
        result += '/'
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Source redirected; review its configured URL before collecting.')


def fetch(url):
    url = allowed_url(url)
    if os.name == 'nt':
        shell = shutil.which('pwsh') or shutil.which('powershell')
        if not shell:
            raise RuntimeError('PowerShell is needed for Windows certificate trust.')
        process = subprocess.run([shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
                                  str(ROOT / 'scripts' / 'fetch_public.ps1'), '-Url', url],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace',
                                 timeout=25, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            result = json.loads(process.stdout.lstrip('\ufeff'))
        except json.JSONDecodeError:
            raise RuntimeError('The public-source request did not return a readable response.')
        if process.returncode or result.get('error'):
            raise RuntimeError(result.get('error', 'Source request failed.')[:300])
        return result['html']
    request = urllib.request.Request(url, headers={'User-Agent': 'IDNWatch/0.2 (local research prototype)'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=18) as response:
        body = response.read(2500001)
        if len(body) > 2500000:
            raise ValueError('Source exceeds the 2.5 MB collection limit.')
        return body.decode('utf-8', errors='replace')


class PublicHTML(HTMLParser):
    VOID = {'meta','link','br','hr','img','input','source','wbr','embed','area','base','col','param','track'}

    def __init__(self, body_markers=None):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.title_parts, self.h1, self.all_parts, self.body_parts = [], [], [], []
        self.links, self.meta, self.dates = [], {}, []
        self.link = None
        self.scope_depth = None
        self.ignore = 0
        self.h1_offset = 0
        self.body_offset = None
        self.article_end = None
        self.body_markers = body_markers or ('rich-text-content','release-body','field--name-body')

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script','style','noscript','svg'):
            self.ignore += 1
        if tag == 'meta': self.meta[a.get('property') or a.get('name') or ''] = a.get('content', '')
        if tag == 'time' and a.get('datetime'): self.dates.append(a['datetime'])
        if tag == 'a' and a.get('href'): self.link = [a['href'], []]
        if tag == 'h1': self.h1_offset = len(self.all_parts)
        if tag not in self.VOID:
            self.stack.append(tag)
            marker = a.get('class', '')
            if self.scope_depth is None and any(token in marker.split() for token in self.body_markers):
                self.scope_depth = len(self.stack)
                if self.body_offset is None: self.body_offset = len(self.all_parts)

    def handle_endtag(self, tag):
        if tag == 'article' and self.article_end is None: self.article_end = len(self.all_parts)
        if tag == 'a' and self.link:
            self.links.append((self.link[0], clean(' '.join(self.link[1]))))
            self.link = None
        if tag in ('p','li','h2','h3','div') and self.scope_depth is not None:
            self.body_parts.append('\n')
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            if self.scope_depth is not None and index + 1 <= self.scope_depth:
                self.scope_depth = None
            self.stack = self.stack[:index]
        if tag in ('script','style','noscript','svg') and self.ignore:
            self.ignore -= 1

    def handle_data(self, value):
        if self.ignore or not value.strip(): return
        value = clean(value)
        if 'title' in self.stack: self.title_parts.append(value)
        if 'h1' in self.stack: self.h1.append(value)
        if self.link: self.link[1].append(value)
        self.all_parts.append(value)
        if self.scope_depth is not None: self.body_parts.append(value + ' ')


def publication_date(parser, html):
    candidates = [parser.meta.get(key, '') for key in ['article:published_time','date','datePublished','publication_date']]
    candidates += parser.dates
    candidates += re.findall(r'"datePublished"\s*:\s*"([^"<>]+)"', html)
    for candidate in candidates:
        try: return date.fromisoformat(candidate[:10]).isoformat()
        except ValueError: pass
    # Restrict fallback dates to the article header, not related-story footers.
    header = ' '.join(parser.all_parts[parser.h1_offset:])[:1600]
    match = re.search(r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),\s+(20\d\d)', header)
    if match:
        month, day, year = match.groups()
        month_number = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(month[:3].lower()) + 1
        return date(int(year), month_number, int(day)).isoformat()
    return None


def parse_article(html, url):
    markers = {'www.piedmont.org':('rich-text--body',), 'www.wellstar.org':('article-content',), 'www.novanthealth.org':('content-article-body',)}
    parser = PublicHTML(markers.get(urlparse(url).hostname)); parser.feed(html)
    title = clean(' '.join(parser.h1)) or parser.meta.get('og:title') or clean(' '.join(parser.title_parts))
    title = re.split(r'\s+\|\s+', title)[0]
    if not title or len(title) > 600: raise ValueError('A usable article headline was not found.')
    text = ''.join(parser.body_parts).strip()
    if urlparse(url).hostname == 'www.prnewswire.com' and parser.body_offset is not None:
        text = '\n'.join(parser.all_parts[parser.body_offset:parser.article_end])
        text = re.split(r'\nSOURCE\b|\nMore From This Source\b', text)[0]
    if len(text) < 180:
        full = '\n'.join(parser.all_parts)
        start = full.find(title)
        text = full[start + len(title):] if start >= 0 else ''
        text = re.split(r'\n(?:Recent News|Related News|Related Articles|More From This Source)\n', text)[0]
    if len(text) < 180: raise ValueError('Article-body extraction returned too little text; import the visible source text for review.')
    return {'url': allowed_url(url), 'title': title, 'text': text[:60000], 'publication_date': publication_date(parser, html)}


def discover(html, source):
    parser = PublicHTML(); parser.feed(html)
    result = []
    links = list(parser.links)
    # HCA's public page embeds its initial newsroom results as page data.
    if source['id'] == 'hca-florida':
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if match:
            def walk(value):
                if isinstance(value, dict):
                    if isinstance(value.get('url'), str) and '/about-us/newsroom/' in value['url']:
                        links.append((value['url'], str(value.get('title') or value.get('name') or '')))
                    for child in value.values(): walk(child)
                elif isinstance(value, list):
                    for child in value: walk(child)
            try: walk(json.loads(match.group(1)))
            except json.JSONDecodeError: pass
    for href, title in links:
        try: url = allowed_url(urljoin(source['index_url'], href))
        except ValueError: continue
        host, path = urlparse(url).hostname, urlparse(url).path
        if source['id'] == 'advent-press':
            valid = host == 'www.prnewswire.com' and path.startswith('/news-releases/') and 'adventhealth' in (path + title).lower() and path.endswith('.html')
        elif source['id'] == 'hca-florida':
            valid = host == 'www.hcafloridahealthcare.com' and path.startswith('/about-us/newsroom/')
        elif source['system'] in {'piedmont','wellstar','novant'}:
            prefix={'piedmont':'/news/','wellstar':'/articles/','novant':'/newsroom/'}[source['system']]
            excluded={'/articles/newsroom','/articles','/newsroom/releases','/newsroom/media-inquiries','/newsroom/resources','/newsroom/awards','/newsroom/facility-information','/newsroom/alerts','/newsroom/newsroom'}
            valid=host in SYSTEM_HOSTS[source['system']] and path.startswith(prefix) and path.rstrip('/') not in excluded
        else:
            valid = host == 'www.adventhealth.com' and path.startswith('/news/') and not path.startswith('/news/search')
        if valid and url not in result: result.append(url)
    return result[:source['max_articles']]


def save_snapshot(article, raw_html, source_id, method, path):
    normalized_text = clean(article['text'])
    digest = hashlib.sha256(json.dumps([article['title'], normalized_text, article.get('publication_date')], ensure_ascii=False).encode()).hexdigest()
    sid = hashlib.sha256((article['url'] + '|' + digest).encode()).hexdigest()[:32]
    with connect(path) as db:
        db.execute('INSERT OR IGNORE INTO article_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (sid, article['url'], article['title'], article['text'], article.get('publication_date'), now(), method, source_id, digest, raw_html[:2500000]))
        db.execute('INSERT INTO collected_articles VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET snapshot_id=excluded.snapshot_id,last_fetched_at=excluded.last_fetched_at',
                   (article['url'], sid, now(), 'unclassified', source_id))
        saved = dict(db.execute('SELECT * FROM article_snapshots WHERE id=?', (sid,)).fetchone())
    return dict(article, snapshot_id=sid, source_id=source_id, capture_method=saved['capture_method'])


def snapshot(snapshot_id, path):
    with connect(path) as db:
        row = db.execute('SELECT id,url,title,body,publication_date,captured_at,capture_method,source_id,body_hash FROM article_snapshots WHERE id=?', (snapshot_id,)).fetchone()
    if not row: raise KeyError('Snapshot not found.')
    return dict(row)


def record_item(run_id, source_id, url, status, message, path, signal_id=None):
    with connect(path) as db:
        db.execute('INSERT INTO collection_items(run_id,source_id,url,status,message,signal_id,recorded_at) VALUES (?,?,?,?,?,?,?)',
                   (run_id, source_id, url, status, message[:500], signal_id, now()))


def start_run(systems, path):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT id FROM collection_runs WHERE status='running'").fetchone()
        if row: return row['id'], False
        cursor = db.execute('INSERT INTO collection_runs(started_at,status,systems,totals) VALUES (?,?,?,?)', (now(), 'running', json.dumps(systems), '{}'))
        return cursor.lastrowid, True


def run_collection(run_id, systems, path, importer, fetcher=fetch, ai_client=None):
    if ai_client is not None:
        return run_gpt_collection(run_id, systems, path, importer, fetcher, ai_client)
    totals = {key: 0 for key in ['created','revised','unchanged','excluded','failed','retrieved']}
    try:
        for source in json.loads(CONFIG.read_text(encoding='utf-8')):
            if source['system'] not in systems: continue
            source_errors, successes = [], 0
            urls = list(source['seeds'])
            try:
                index_html = fetcher(source['index_url'])
                urls.extend(discover(index_html, source))
                record_item(run_id, source['id'], source['index_url'], 'discovered', f'Found {len(set(urls))} bounded candidate links.', path)
            except Exception as error:
                source_errors.append(str(error)[:250]); totals['failed'] += 1
                record_item(run_id, source['id'], source['index_url'], 'failed', str(error), path)
            for url in list(dict.fromkeys(urls))[:source['max_articles']]:
                try:
                    html = fetcher(url)
                    article = save_snapshot(parse_article(html, url), html, source['id'], 'http', path)
                    totals['retrieved'] += 1; successes += 1
                    item, reason = normalize_article(article, source['system'])
                    with connect(path) as db:
                        db.execute('UPDATE collected_articles SET relevance=? WHERE url=?', ('candidate' if item else reason, article['url']))
                    if item:
                        counts = importer([item], path, origin='collector')
                        for key in ['created','revised','unchanged']: totals[key] += counts[key]
                        status = next((key for key in ['created','revised','unchanged'] if counts[key]), 'unchanged')
                        signal_id = hashlib.sha256((item['system'] + '|' + item['source_url'].rstrip('/')).encode()).hexdigest()[:24]
                        record_item(run_id, source['id'], url, status, reason, path, signal_id)
                    else:
                        totals['excluded'] += 1
                        record_item(run_id, source['id'], url, 'excluded', reason, path)
                except Exception as error:
                    totals['failed'] += 1; source_errors.append(str(error)[:250])
                    record_item(run_id, source['id'], url, 'failed', str(error), path)
            with connect(path) as db:
                db.execute('INSERT INTO source_health VALUES (?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=COALESCE(excluded.last_success,source_health.last_success),last_error=excluded.last_error',
                           (source['id'], now(), now() if successes else None, '; '.join(source_errors) or None))
        status = 'partial' if totals['failed'] and totals['retrieved'] else 'failed' if totals['failed'] else 'completed'
    except Exception as error:
        totals['failed'] += 1; status = 'failed'
        record_item(run_id, 'pipeline', '', 'failed', str(error), path)
    with connect(path) as db:
        db.execute('UPDATE collection_runs SET finished_at=?,status=?,totals=? WHERE id=?', (now(), status, json.dumps(totals), run_id))


def run_gpt_collection(run_id, systems, path, importer, fetcher, ai_client):
    totals = {key: 0 for key in ['created','revised','unchanged','excluded','failed','retrieved',
                                'searched','gpt_summaries','cached_summaries']}
    seen = set()
    try:
        for system in sorted(set(systems)):
            source_id = 'gpt-search-' + system
            errors, successes = [], 0
            try:
                search = ai_client.search(system, path)
                urls = search['urls']
                totals['searched'] += 1
                record_item(run_id, source_id, '', 'searched',
                            f'GPT web search returned {len(urls)} bounded official-source article link(s).', path)
                for url in urls[:ai_client.config.articles_per_system]:
                    if (system, url) in seen:
                        continue
                    seen.add((system, url))
                    try:
                        html = fetcher(allowed_url(url))
                        article = save_snapshot(parse_article(html, url), html, source_id, 'http', path)
                        totals['retrieved'] += 1
                        successes += 1
                        # A search citation alone is never treated as fetched article text.
                        if not re.search(r'\b' + ('HCA' if system == 'hca' else system) + r'\b',
                                         article['title'] + ' ' + article['text'], re.I):
                            reason = 'The retrieved article does not identify the selected parent IDN.'
                            item = None
                        elif article.get('publication_date') and (date.today() - date.fromisoformat(article['publication_date'])).days not in range(ai_client.config.lookback_days + 1):
                            reason = f'Article publication is outside the current {ai_client.config.lookback_days}-day search window.'
                            item = None
                        else:
                            item, reason = normalize_article(article, system)
                        with connect(path) as db:
                            db.execute('UPDATE collected_articles SET relevance=? WHERE url=?',
                                       ('candidate' if item else reason, article['url']))
                        if not item:
                            totals['excluded'] += 1
                            record_item(run_id, source_id, url, 'excluded', reason, path)
                            continue
                        item, cached = ai_client.summarize(article, item, path)
                        totals['cached_summaries' if cached else 'gpt_summaries'] += 1
                        item['discovery'] = {'method': 'openai_web_search', 'model': search['model'],
                                             'response_id': search['response_id']}
                        counts = importer([item], path, origin='collector')
                        for key in ['created','revised','unchanged']:
                            totals[key] += counts[key]
                        outcome = next((key for key in ['created','revised','unchanged'] if counts[key]), 'unchanged')
                        signal_id = hashlib.sha256((item['system'] + '|' + item['source_url'].rstrip('/')).encode()).hexdigest()[:24]
                        record_item(run_id, source_id, url, outcome,
                                    'Cached GPT summary reused.' if cached else 'GPT summary generated from saved article text; source review required.', path, signal_id)
                    except Exception as error:
                        totals['failed'] += 1
                        errors.append(str(error)[:250])
                        record_item(run_id, source_id, url, 'failed', str(error), path)
            except Exception as error:
                totals['failed'] += 1
                errors.append(str(error)[:250])
                record_item(run_id, source_id, '', 'failed', str(error), path)
            with connect(path) as db:
                db.execute('INSERT INTO source_health VALUES (?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=COALESCE(excluded.last_success,source_health.last_success),last_error=excluded.last_error',
                           (source_id, now(), now() if successes else None, '; '.join(errors) or None))
    except Exception as error:
        totals['failed'] += 1
        record_item(run_id, 'pipeline', '', 'failed', str(error), path)
    outcome = 'partial' if totals['failed'] and totals['retrieved'] else 'failed' if totals['failed'] else 'completed'
    with connect(path) as db:
        db.execute('UPDATE collection_runs SET finished_at=?,status=?,totals=? WHERE id=?',
                   (now(), outcome, json.dumps(totals), run_id))


def status(path):
    with connect(path) as db:
        row = db.execute('SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()
        run = dict(row) if row else None
        if run:
            run['systems'] = json.loads(run['systems']); run['totals'] = json.loads(run['totals'])
            run['items'] = [dict(r) for r in db.execute('SELECT * FROM collection_items WHERE run_id=? ORDER BY id', (run['id'],))]
        health = {r['source_id']: dict(r) for r in db.execute('SELECT * FROM source_health')}
        article_count = db.execute('SELECT COUNT(*) FROM collected_articles').fetchone()[0]
    sources = [dict(source, **{k:v for k,v in health.get(source['id'], {}).items() if k != 'source_id'}) for source in json.loads(CONFIG.read_text(encoding='utf-8'))]
    engine = openai_pipeline.public_status()
    if engine['mode'] == 'gpt':
        sources = [dict(id='gpt-search-' + system, system=system,
                        name=openai_pipeline.SYSTEM_NAMES[system] + ' · official-source web search',
                        index_url='https://' + sorted(hosts)[0],
                        note=f"Search covers the last {engine['lookback_days']} days on: " + ', '.join(sorted(hosts)) + '. Article text must be fetched before summarizing.',
                        **{k:v for k,v in health.get('gpt-search-' + system, {}).items() if k != 'source_id'})
                   for system, hosts in SYSTEM_HOSTS.items()]
    return {'sources': sources, 'last_run': run, 'article_count': article_count, 'engine': engine}


def recover_interrupted(path):
    with connect(path) as db:
        db.execute("UPDATE collection_runs SET status='interrupted',finished_at=? WHERE status='running'", (now(),))
