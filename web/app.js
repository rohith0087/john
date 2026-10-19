'use strict';

const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; };
const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  spark: '<path d="m12 3 2.8 6.2L21 12l-6.2 2.8L12 21l-2.8-6.2L3 12l6.2-2.8Z"/><path d="M20 2v4m-2-2h4"/>',
  'check-square': '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-7"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  building: '<path d="M4 21V5l8-2v18M12 9h8v12M2 21h20M7 7v1m0 3v1m0 3v1m9-3h1m-1 4h1"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18m-14 4h3m4 0h3"/>',
  sliders: '<path d="M4 7h7m4 0h5M4 17h3m4 0h9"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  expand: '<path d="M14 3h7v7m0-7-7 7M10 21H3v-7m0 7 7-7"/>',
  'arrow-right': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 7-7"/><circle cx="12" cy="12" r="1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.2"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  link: '<path d="M14 3h7v7m0-7L10 14M10 5H4v15h15v-6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  partnership: '<path d="m3 12 5-7 4 2 4-2 5 7-5 7-4-2-4 2Z"/><path d="m8 11 4-4m-2 9 4-5 3 2"/>',
  leadership: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  financial: '<path d="M5 21V11m7 10V4m7 17v-7M2 21h20"/>',
};
function icon(name) { const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); node.setAttribute('viewBox', '0 0 24 24'); node.setAttribute('class', 'icon'); node.setAttribute('aria-hidden', 'true'); node.innerHTML = paths[name] || paths.info; return node; }
function hydrateIcons(root = document) { root.querySelectorAll('[data-icon]').forEach(node => node.replaceChildren(icon(node.dataset.icon))); }
function button(label, cls, onClick, iconName) { const node = el('button', cls); node.type = 'button'; if (iconName) node.append(icon(iconName)); node.append(document.createTextNode(label)); if (onClick) node.addEventListener('click', onClick); return node; }
function safeLink(url, label, cls) { const node = el('a', cls, label); try { const parsed = new URL(url); if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return el('span', cls, 'Source URL unavailable'); node.href = parsed.href; node.target = '_blank'; node.rel = 'noopener noreferrer'; } catch { return el('span', cls, 'Source URL unavailable'); } return node; }
const formatDate = (value, year = true) => value ? new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', ...(year ? {year:'numeric'} : {}), timeZone:'UTC'}).format(new Date(value + 'T00:00:00Z')) : 'Not found';
const statusLabels = {pending:'Awaiting review', approved:'Approved', rejected:'Rejected'};
const storageKey = 'idn-watch-health-systems';
let records = [], recommendations = [], systems = {}, systemRegions = {}, method = null, token = '', selected = [], view = 'overview', sourceLinks = null, sourcePage = 0, scoredOn = '', detailId = null, toastTimer;
let collectionState = null, collectionPoll = null, editingRecord = null;
const briefs = new Map();
const pageSize = 25;
const included = r => selected.includes(r.system);
const activeRecommendations = () => recommendations.filter(r => included(r) && ($('preview-drafts').checked || r.status === 'approved'));
const selectedRecords = () => records.filter(r => included(r) && r.schema_version === 2);
function filteredRecommendations() { const query = $('recommendation-search').value.toLowerCase().trim(), category = $('recommendation-category').value; return activeRecommendations().filter(r => (!category || r.category === category) && `${r.headline} ${r.action_title} ${r.title} ${r.rationale} ${systems[r.system]}`.toLowerCase().includes(query)); }
function filteredReviews() { const query = $('review-search').value.toLowerCase().trim(), status = $('review-status').value; return records.filter(r => included(r) && ($('record-type').value === 'all' || r.schema_version === 2) && (!status || r.status === status) && `${r.title} ${r.summary} ${systems[r.system]}`.toLowerCase().includes(query)); }
function filteredSources() { const query = $('source-search').value.toLowerCase().trim(); return (sourceLinks || []).filter(r => included(r) && `${r.url} ${r.profile} ${systems[r.system]}`.toLowerCase().includes(query)); }
function notify(text) { clearTimeout(toastTimer); $('message').textContent = text; $('message').hidden = false; toastTimer = setTimeout(() => { $('message').hidden = true; }, 7000); }
async function request(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw Error(data.error || 'The request could not be completed.'); return data; }
async function load(initial = false) {
  $('workspace-content').setAttribute('aria-busy', 'true');
  try {
    const [feed, ranked, collected] = await Promise.all([request('/api/signals'), request('/api/recommendations?include_drafts=1'), request('/api/collection')]);
    records = feed.signals; systems = feed.systems; systemRegions = feed.regions || {}; token = feed.review_token;
    const importSelection=$('import-system').value; $('import-system').replaceChildren(...Object.entries(systems).map(([key,name])=>{const option=el('option','',name);option.value=key;return option;})); if (Object.hasOwn(systems,importSelection)) $('import-system').value=importSelection;
    recommendations = ranked.recommendations; method = ranked.method; scoredOn = ranked.scored_on;
    collectionState = collected; briefs.clear();
    if (initial) { try { const saved = JSON.parse(localStorage.getItem(storageKey)); selected = Array.isArray(saved) ? [...new Set(saved.filter(key => Object.hasOwn(systems, key)))] : Object.keys(systems); } catch { selected = Object.keys(systems); } }
    $('load-error').hidden = true; $('workspace-content').hidden = false;
    render(); renderMethod(); renderCollection();
    if (collectionState.last_run?.status === 'running' && !collectionPoll) scheduleCollectionPoll();
  } catch (error) { $('load-error').hidden = false; $('load-error-text').textContent = error.message; if (initial) $('workspace-content').hidden = true; throw error; }
  finally { $('workspace-content').setAttribute('aria-busy', 'false'); }
}
function metadata(r) { const line = el('div', 'record-meta'), name = el('span', 'system-name'); name.append(el('span', 'system-dot ' + r.system), document.createTextNode(systems[r.system])); line.append(name, el('span', 'meta-divider', '·'), el('span', '', r.category)); return line; }
function monogram(key) { return el('span', 'system-monogram ' + key, ({hca:'HCA',adventhealth:'AH',piedmont:'PH',wellstar:'WS',novant:'NH'}[key] || key.slice(0,2).toUpperCase())); }
function emptyState(title, description, manage = false) { const box = el('div', 'empty'); box.append(icon('radar'), el('h3', '', title), el('p', '', description)); if (manage) box.append(button('Choose health systems', 'button primary', openSystems)); return box; }
function render() {
  const active = activeRecommendations(), focused = selectedRecords();
  $('metric-systems').textContent = String(selected.length).padStart(2, '0');
  $('metric-actions').textContent = String(active.length).padStart(2, '0');
  $('metric-pending').textContent = String(focused.filter(r => !r.source_checked).length).padStart(2, '0');
  const latest = focused.map(r => r.publication_date).filter(Boolean).sort().at(-1);
  $('metric-date').textContent = latest ? formatDate(latest, false) : '—';
  $('metric-date').title = latest ? 'Latest collected article: ' + formatDate(latest) : 'No article publication date found';
  $('coverage-label').textContent = `${selected.length} health system${selected.length === 1 ? '' : 's'}`;
  $('nav-count').textContent = active.length; $('all-count').textContent = active.length;
  const drafts = focused.filter(r => r.status === 'pending').length;
  $('draft-count').textContent = `(${drafts})`;
  $('feed-mode-label').textContent = $('preview-drafts').checked ? 'Draft preview · includes updates awaiting review' : 'Sales feed · approved collected updates';
  document.querySelector('.feed-mode').classList.toggle('is-preview', $('preview-drafts').checked);
  $('sidebar-systems').replaceChildren(); $('coverage-cards').replaceChildren();
  for (const key of selected) {
    const side = el('div', 'sidebar-system'); side.append(el('span', 'system-dot ' + key), document.createTextNode(systems[key])); $('sidebar-systems').append(side);
    const card = el('div', 'coverage-system'), text = el('div'); text.append(el('strong', '', systems[key]), el('small', '', `${focused.filter(r => r.system === key).length} collected update${focused.filter(r => r.system === key).length === 1 ? "" : "s"}`)); card.append(monogram(key), text, icon('chevron')); $('coverage-cards').append(card);
  }
  if (!selected.length) { $('sidebar-systems').append(el('div', 'sidebar-system', 'No systems selected')); $('coverage-cards').append(el('p', 'panel-note', 'Choose a health system to see its recommendations.')); }
  $('top-recommendations').replaceChildren();
  active.slice(0, 3).forEach((r, index) => $('top-recommendations').append(recommendationRow(r, index + 1, active[index + 1])));
  if (!active.length) {
    const empty = emptyState(selected.length ? 'No approved updates yet' : 'Choose your accounts', selected.length ? `${drafts} candidate update(s) await review. Review the source and extracted facts before approving a version for the sales feed.` : 'Choose the health systems you want to follow.', !selected.length);
    if (selected.length) empty.append(button('Review candidate updates', 'button primary', () => switchView('review')));
    $('top-recommendations').append(empty);
  }
  $('category-landscape').replaceChildren();
  for (const [category, label, graphic] of [['Expansion','Expansions','building'],['Ownership & partnerships','Ownership & partnerships','partnership'],['Leadership','Leadership changes','leadership'],['Financial','Financial developments','financial']]) {
    const item = el('div', 'landscape-item'), graphicBox = el('span', 'landscape-icon'), content = el('div'); graphicBox.append(icon(graphic)); content.append(el('strong', '', String(focused.filter(r => r.category === category).length).padStart(2, '0')), el('small', '', label)); item.append(graphicBox, content); $('category-landscape').append(item);
  }
  renderRecommendations(); renderReviews(); if (typeof renderWidgets === 'function') renderWidgets(); if (view === 'sources' && sourceLinks !== null) renderSources();
}
function recommendationRow(r, rank, next) {
  const row = el('article', 'recommendation-row'), number = el('span', 'rank-number', String(rank).padStart(2, '0')); number.setAttribute('aria-label', 'Priority ' + rank);
  const content = el('div'), meta = metadata(r);
  meta.append(el('span', 'source-state ' + (r.source_checked ? 'checked' : ''), r.evidence_label));
  if (r.status === 'pending') meta.append(el('span', 'draft-badge', 'Draft'));
  const headline = button(r.headline, 'recommendation-title', () => openDetail(r.id));
  headline.setAttribute('aria-label', 'Account update: ' + r.headline);
  const context = el('dl', 'sales-context');
  context.append(el('dt', '', 'Why it matters'), el('dd', 'sales-impact', r.rationale), el('dt', '', 'Suggested next step'), el('dd', 'suggested-step', r.action_title));
  content.append(meta, headline, context);
  const bottom = el('div', 'row-bottom'), whyWrap = el('div', 'why-wrap');
  const why = button('Why prioritized?', 'why-button', null, 'info'), popover = el('div', 'reason-popover');
  const tooltipId = `why-${view}-${rank}-${r.id}-${rowSequence++}`; popover.id = tooltipId; popover.hidden = true; popover.setAttribute('role', 'tooltip');
  why.setAttribute('aria-describedby', tooltipId); why.setAttribute('aria-expanded', 'false'); why.setAttribute('aria-label', 'Why prioritized: ' + r.headline);
  popover.append(el('strong', '', `Priority ${rank} · ${r.score}/100`));
  const leadingFactors = [...r.factors].sort((a, b) => b.points - a.points).slice(0, 2);
  for (const factor of leadingFactors) popover.append(el('p', 'popover-explanation', factor.reason));
  for (const factor of r.factors) { const line = el('div', 'reason-line'); line.append(el('span', '', factor.label), el('b', '', `${factor.points}/${factor.maximum}`)); popover.append(line); }
  const gap = next ? r.score - next.score : null;
  const comparison = next ? gap ? `${gap} point${gap === 1 ? "" : "s"} above the next item in this view.` : 'Tied on points; the newer source date, then record ID, breaks the tie.' : 'No lower-ranked item in this view.';
  popover.append(el('p', 'popover-note', `${comparison} ${r.evidence_label}. Open the account brief for supporting evidence.`));
  let pinned = false, hovered = false, focused = false, suppressed = false, closeTimer;
  const update = () => {
    const open = !suppressed && (pinned || hovered || focused);
    popover.hidden = !open; why.setAttribute('aria-expanded', String(open));
    if (open) { const rect = why.getBoundingClientRect(); popover.classList.toggle('above', rect.bottom + popover.offsetHeight + 20 > window.innerHeight && rect.top > popover.offsetHeight + 15); }
  };
  whyWrap.addEventListener('mouseenter', () => { clearTimeout(closeTimer); hovered = true; suppressed = false; update(); });
  whyWrap.addEventListener('mouseleave', () => { closeTimer = setTimeout(() => { hovered = false; if (!focused) suppressed = false; update(); }, 140); });
  why.addEventListener('focus', () => { focused = true; suppressed = false; update(); });
  why.addEventListener('blur', () => { focused = false; if (!hovered) suppressed = false; update(); });
  why.addEventListener('click', () => { pinned = !pinned; suppressed = !pinned; update(); });
  whyWrap.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); pinned = false; suppressed = true; update(); } });
  whyWrap.closePopover = () => { pinned = false; hovered = false; focused = false; suppressed = true; update(); };
  whyWrap.append(why, el('span', 'score-caption', `Priority score ${r.score}/100`), popover);
  const details = button('View account brief', 'detail-link', () => openDetail(r.id)); details.append(icon('arrow-right')); details.setAttribute('aria-label', 'View account brief: ' + r.headline);
  bottom.append(whyWrap, details); content.append(bottom); row.append(number, content); return row;
}
let rowSequence = 0;
function renderRecommendations() {
  const rows = filteredRecommendations(); $('recommendation-count').textContent = `${rows.length} recommendation${rows.length === 1 ? '' : 's'} for your selected systems`;
  $('all-recommendations').replaceChildren(); rows.forEach((r, index) => $('all-recommendations').append(recommendationRow(r, index + 1, rows[index + 1])));
  if (!rows.length) $('all-recommendations').append(emptyState('No recommendations in this view', selected.length ? 'Try another search or development category, or check editorial review.' : 'Choose a health system to build your list.', !selected.length));
}
function reviewButtons(r) {
  const actions = el('div', 'review-actions');
  for (const [status, label, cls] of [['approved','Approve','primary'],['rejected','Reject','secondary'],['pending','Reset','secondary']]) {
    const control = button(label, 'button ' + cls, () => saveReview(r, status, actions)); control.setAttribute('aria-pressed', String(r.status === status)); control.setAttribute('aria-label', `${label}: ${r.title}`); actions.append(control);
  }
  return actions;
}
async function saveReview(r, status, controls) {
  controls.querySelectorAll('button').forEach(node => { node.disabled = true; });
  try {
    await request('/api/review', {method:'POST', headers:{'Content-Type':'application/json','X-Review-Token':token}, body:JSON.stringify({id:r.id, version:r.version, status})});
    await load();
    if ($('detail-dialog').open && detailId === r.id) {
      const brief = await request(`/api/signals/${r.id}/brief`); briefs.set(r.id, brief);
      renderDetail(r.id);
      $('detail-content').querySelector('button[aria-pressed="true"]')?.focus({preventScroll:true});
    }
    notify(`${statusLabels[status]} saved. ${r.schema_version!==2?'Profile examples remain reference records outside the collected sales feed.':status === 'rejected' ? 'Removed from the sales feed; the record is retained.' : status === 'approved' ? 'This version is now in the sales feed. Source verification remains a separate check.' : 'Returned to the draft review queue.'}`);
  } catch (error) { notify(error.message); } finally { controls.querySelectorAll('button').forEach(node => { node.disabled = false; }); }
}
function renderReviews() {
  const rows = filteredReviews(); $('review-count').textContent = `${rows.length} development${rows.length === 1 ? '' : 's'} · decisions and earlier versions are retained`;
  $('review-records').replaceChildren();
  for (const r of rows) {
    const card = el('article', 'panel review-card'), head = el('div', 'review-card-head'); head.append(metadata(r), el('span', 'status-badge ' + r.status, statusLabels[r.status]));
    card.append(head, el('h2', '', r.title), el('p', '', r.summary));
    card.append(el('p', 'record-provenance', r.schema_version === 2 ? `${r.entity} · ${r.development_status} · Article ${formatDate(r.publication_date)} · ${r.source_checked ? 'Source checked' : 'Facts need review'}` : 'Profile reference example · original article not retrieved'));
    const bottom = el('div', 'review-bottom'), left = el('div','review-left');
    left.append(button('View account brief', 'detail-link', () => openDetail(r.id)));
    if (r.schema_version === 2) left.append(button('Review / correct facts', 'button secondary', () => openEditor(r.id)));
    bottom.append(left, reviewButtons(r)); card.append(bottom); $('review-records').append(card);
  }
  if (!rows.length) $('review-records').append(emptyState('No records match', 'Try another review status or search, or change your health systems.', !selected.length));
}
async function switchView(next, focusHeading = true, updateAddress = true) {
  if (!['overview','recommendations','review','sources','widgets'].includes(next)) return;
  view = next;
  const copy = {
    widgets:['DESIGN COLLECTION','Recommendation widgets',null,'Explore dashboard layouts built around the way your team works.','Widget gallery'],
    overview:['SALES INTELLIGENCE','Account overview',null,'Track account changes and plan your next follow-up.','Overview'],
    recommendations:['ACCOUNT PLANNING','Recommended follow-up',null,'See what changed, why it matters to sales, and the suggested next step.','Recommendations'],
    review:['CONTENT MANAGEMENT','Content review',null,'Check account updates and suggested follow-up before approving the content.','Content review'],
    sources:['SOURCE INFORMATION','Source library',null,'Find the references behind your account updates.','Source library'],
  }[next];
  $('page-eyebrow').textContent = copy[0]; $('page-title').replaceChildren(document.createTextNode(copy[1])); if (copy[2]) $('page-title').append(el('br'), el('span', '', copy[2])); $('page-intro').textContent = copy[3]; $('breadcrumb-current').textContent = copy[4];
  for (const name of ['overview','recommendations','review','sources','widgets']) $(name + '-view').hidden = name !== next;
  document.querySelectorAll('[data-view]').forEach(node => { node.classList.toggle('active', node.dataset.view === next); if (node.dataset.view === next) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current'); });
  document.querySelectorAll('.why-wrap').forEach(node => node.closePopover?.());
  document.body.classList.toggle('widget-gallery-page', next === 'widgets');
  if (updateAddress) { const address = next === 'overview' ? '/' : next === 'widgets' ? '/ui' : '/' + next; if (location.pathname !== address) history.pushState({view:next}, '', address); }
  if (next === 'widgets' && typeof renderWidgets === 'function') renderWidgets();
  if (next === 'recommendations') renderRecommendations();
  if (next === 'sources') await loadSources();
  if (focusHeading) { $('main').focus({preventScroll:true}); window.scrollTo({top:0, behavior:'instant'}); }
}
async function loadSources() {
  if (sourceLinks !== null) return renderSources();
  $('source-list').replaceChildren(el('div', 'loading', 'Loading source links…')); $('source-count').textContent = '';
  try { const data = await request('/api/sources'); sourceLinks = data.links; renderSources(); } catch (error) { $('source-list').replaceChildren(emptyState('Source library unavailable', error.message)); $('source-list').append(button('Try again', 'button secondary', loadSources)); }
}
function renderSources() {
  const rows = filteredSources(), pages = Math.max(1, Math.ceil(rows.length / pageSize)); sourcePage = Math.min(sourcePage, pages - 1);
  $('source-count').textContent = `${rows.length} source links for your selected systems · discovery inventory`;
  $('source-list').replaceChildren();
  for (const r of rows.slice(sourcePage * pageSize, (sourcePage + 1) * pageSize)) { const row = el('div', 'source-row'), text = el('div'); text.append(el('strong', '', systems[r.system]), safeLink(r.url, r.url), el('span', 'source-page-ref', `${r.profile} · page ${r.page}`)); row.append(monogram(r.system), text); $('source-list').append(row); }
  if (!rows.length) $('source-list').append(emptyState('No source links match', 'Try another domain or choose a different health system.', !selected.length));
  $('source-page').textContent = `Page ${sourcePage + 1} of ${pages}`; $('source-prev').disabled = sourcePage === 0; $('source-next').disabled = sourcePage + 1 >= pages;
}
function openSystems() {
  $('system-options').replaceChildren();
  for (const [key, name] of Object.entries(systems)) { const option = el('label', 'system-option'), text = el('div'), checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.name = 'system'; checkbox.value = key; checkbox.checked = selected.includes(key); text.append(el('strong', '', name), el('small', '', `${systemRegions[key] || 'Health system'} · IDN · ${records.filter(r => r.system === key && r.schema_version === 2).length} collected updates`)); option.append(monogram(key), text, checkbox); $('system-options').append(option); }
  $('systems-dialog').showModal();
}
function renderMethod() {
  if (!method) return;
  const root = $('method-content'); root.replaceChildren(el('p', 'method-description', method.description));
  for (const factor of method.factors) { const row = el('div', 'method-factor'); row.append(el('span', '', factor.label), el('strong', '', factor.maximum + ' points')); root.append(row); }
  const notes = el('ul', 'method-notes'); method.notes.forEach(note => notes.append(el('li', '', note))); root.append(notes, el('p', 'small-text', `Scored on ${formatDate(scoredOn)}. The total is a provisional editorial priority, not a calibrated probability or financial prediction.`));
}
async function openDetail(id) { try { const brief = await request(`/api/signals/${id}/brief`); briefs.set(id, brief); detailId = id; renderDetail(id); if (!$('detail-dialog').open) $('detail-dialog').showModal(); $('detail-dialog').scrollTop = 0; } catch(error) { notify(error.message); } }
function renderDetail(id) {
  const r = records.find(item => item.id === id), rec = briefs.get(id)?.recommendation || recommendations.find(item => item.id === id); if (!r) return;
  const root = $('detail-content'); root.replaceChildren();
  const heading = el('div', 'drawer-heading'), close = button('', 'icon-button', () => $('detail-dialog').close(), 'close'); close.setAttribute('aria-label', 'Close account brief'); heading.append(el('span', '', 'ACCOUNT BRIEF'), close);
  const body = el('div', 'drawer-body'), title = el('h2', '', rec ? rec.headline : r.title); title.id = 'detail-title'; body.append(metadata(r), title);
  const overview = el('section', 'brief-overview'); overview.append(el('h3', '', 'What changed'), el('p', 'drawer-lead', r.summary));
  if (rec) overview.append(el('h3', '', 'Why it matters to sales'), el('p', 'drawer-lead', rec.rationale));
  body.append(overview);
  body.append(el('div', 'evidence-callout ' + (r.source_checked ? 'checked-callout' : ''), r.schema_version === 2 ? (r.source_checked ? 'Source checked during local content review. Check for later developments before acting on historical plans.' : 'Article text saved · extracted facts need review. Retrieval alone does not verify every extracted value or the latest project status.') : 'Profile reference only · the original source has not been collected.'));
  if (r.schema_version === 2) {
    const factBar = el('div','brief-factbar'); factBar.append(el('span','',r.entity), el('span','stage-badge',r.development_status), button('Review / correct facts','text-button',()=>openEditor(id))); body.append(factBar);
    if (rec?.visual) body.append(renderVisual(rec.visual));
    if (r.extraction_warnings?.length && !r.source_checked) { const warnings=el('ul','extraction-warnings'); r.extraction_warnings.forEach(w=>warnings.append(el('li','',w))); body.append(warnings); }
    const related = briefs.get(id)?.related || [];
    if (related.length) { const box=el('details','related-coverage'); box.append(el('summary','','Related coverage · check for the same event')); const list=el('ul'); related.forEach(item=>{const li=el('li');li.append(safeLink(item.source_url,item.title));list.append(li);}); box.append(el('p','small-text','Possible overlap based on facility and development type. Records are retained separately until reviewed.'),list);body.append(box); }
  }
  if (rec) {
    const section = el('section', 'drawer-section'); section.append(el('h3', '', 'Suggested next step'), el('p', 'brief-action', rec.action_title)); const list = el('ol', 'step-list'); rec.steps.forEach(step => list.append(el('li', '', step))); section.append(list); body.append(section);
    const priority = el('section', 'drawer-section'), priorityHeading = el('div', 'priority-heading'), score = el('div', 'priority-score'); score.append(el('strong', '', rec.score), el('span', '', '/ 100 points')); priorityHeading.append(el('h3', '', 'Why this is prioritized'), score); priority.append(priorityHeading);
    const active = activeRecommendations(), index = active.findIndex(item => item.id === id), next = active[index + 1];
    if (index >= 0) priority.append(el('p', '', `Ranked ${index + 1} of ${active.length} for your selected health systems.${next ? rec.score === next.score ? ' Tied with the next item; the newer source date, then record ID, breaks the tie.' : ` ${rec.score - next.score} point${rec.score - next.score === 1 ? "" : "s"} above the next item.` : ''}`));
    for (const factor of rec.factors) { const block = el('div', 'factor-block'), line = el('div', 'factor-heading'), progress = el('progress', 'factor-track'); progress.max = factor.maximum; progress.value = factor.points; progress.setAttribute('aria-label', factor.label); line.append(el('span', '', factor.label), el('b', '', `${factor.points} / ${factor.maximum}`)); block.append(line, progress, el('p', '', factor.reason)); priority.append(block); }
    priority.append(el('p', 'review-note', `Shared priority criteria · Scored ${formatDate(scoredOn)}. These points help prioritize account follow-up; they do not predict a sale.`)); body.append(priority);
  } else body.append(el('p', 'review-note', 'This record is excluded from the recommendation list. Reset its review status to return it for assessment.'));
  const evidence = el('section', 'drawer-section'); evidence.append(el('h3', '', 'Source & verification'), el('blockquote', 'source-quote', r.evidence_text));
  const source = safeLink(r.source_url, 'Open original source', 'source-link'); source.append(icon('link')); evidence.append(source);
  const reference = r.schema_version === 2 ? r.source_id : `${r.profile} · page ${r.profile_page}`;
  const grid = el('div', 'detail-grid'); for (const [label, value] of [['Source reference',reference],[r.schema_version === 2 ? 'Article publication date' : 'Profile entry date',formatDate(r.source_date)],['Event date',r.event_date ? formatDate(r.event_date) : 'Not verified'],['Content review',statusLabels[r.status]]]) { const item = el('div','',label); item.append(el('strong','',value)); grid.append(item); } evidence.append(grid);
  if (r.implication) evidence.append(el('h3', '', 'Sales qualification notes'), el('p', '', r.implication)); body.append(evidence);
  if(r.editor_note)evidence.append(el('p','review-note','Review note: '+r.editor_note));
  const editorial = el('section', 'drawer-section drawer-bottom'); editorial.append(el('h3', '', 'Content review'), reviewButtons(r), el('p', 'review-note', 'Approve includes this version in the local sales feed. Reject removes it; reset returns it to review. These decisions do not verify the source or publish to the client’s platform.'));
  const history = el('details'), summary = el('summary', 'history-toggle', 'Version & decision history'), historyBody = el('div');
  history.append(summary, historyBody);
  history.addEventListener('toggle', async () => {
    if (!history.open || history.dataset.loaded) return;
    historyBody.textContent = 'Loading history…';
    try {
      const data = await request(`/api/signals/${id}/history`);
      historyBody.replaceChildren(el('p', 'review-note', `${data.versions.length} stored versions. Current version: ${r.version}.`));
      for (const version of [...data.versions].reverse()) {
        const entry = el('details', 'version-entry'), facts = version.payload;
        entry.append(el('summary', '', `Version ${version.version}${version.version === r.version ? ' · current' : ''} · ${new Date(version.recorded_at).toLocaleString()}`));
        entry.append(el('strong', '', facts.title), el('p', '', facts.summary));
        if (facts.schema_version === 2) {
          entry.append(el('p', 'small-text', `${facts.entity} · ${facts.category} · ${facts.development_status} · ${facts.source_checked ? 'Source checked' : 'Source check pending'}`));
          for (const metric of facts.metrics || []) entry.append(el('p', 'small-text', `${metric.label}: ${metric.baseline ?? 'Unknown baseline'} → ${metric.target} ${metric.unit}. Source: ${metric.evidence}`));
          if (facts.editor_note) entry.append(el('p', 'review-note', 'Review note: ' + facts.editor_note));
        }
        historyBody.append(entry);
      }
      const list = el('ul', 'history-list');
      for (const decision of data.reviews) list.append(el('li', '', `Version ${decision.version} · ${statusLabels[decision.status]} · ${new Date(decision.reviewed_at).toLocaleString()}`));
      if (!data.reviews.length) historyBody.append(el('p', 'review-note', 'No editorial decisions recorded.'));
      historyBody.append(list); history.dataset.loaded = 'true';
    } catch (error) { historyBody.textContent = error.message; }
  });
  editorial.append(history); body.append(editorial); root.append(heading, body);
}
function exportData(kind) { if (!method) return notify('Load the workspace before exporting.'); if (kind === 'sources' && sourceLinks === null) return notify('Load the source library before exporting.'); const rows = kind === 'recommendations' ? filteredRecommendations() : kind === 'review' ? filteredReviews() : filteredSources(); const data = {exported_at:new Date().toISOString(), selected_systems:selected, note:'Check each record’s provenance, review status, and source verification. Editorial approval does not verify all facts or publish externally.', ...(kind === 'recommendations' ? {scored_on:scoredOn, includes_drafts:$('preview-drafts').checked, method, recommendations:rows} : kind === 'review' ? {signals:rows} : {links:rows})}; const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)], {type:'application/json'})), link = el('a'); link.href = url; link.download = `idn-watch-${kind}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); notify(`Exported ${rows.length} ${kind === 'sources' ? 'source links' : 'records'} with supporting references.`); }

function svgNode(tag, attrs = {}, text) { const node=document.createElementNS('http://www.w3.org/2000/svg',tag); for(const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value)); if(text!==undefined) node.textContent=text; return node; }
function renderVisual(visual) {
  const section=el('section','context-visual drawer-section'); section.append(el('h3','',visual.title));
  section.append(el('p','visual-entity',visual.entity));
  if(visual.type==='capacity') {
    const planned=visual.basis==='planned', baseline=visual.baseline, target=visual.target;
    const kpi=el('div','visual-kpi'); kpi.append(el('strong','',visual.growth_percent!==null ? `${visual.growth_percent}%` : String(target)),el('span','',visual.growth_percent!==null ? `${planned?'Planned':'Reported'} capacity increase` : `${planned?'Planned':'Reported'} additional beds · baseline unavailable`)); section.append(kpi);
    const figure=el('figure','capacity-figure');
    const svg=svgNode('svg',{viewBox:'0 0 500 158',role:'img','aria-label':baseline!==null ? `${visual.entity}: ${baseline} baseline beds and ${target} ${planned?'planned':'reported'} beds.` : `${visual.entity}: ${target} additional beds; baseline not available.`});
    const max=Math.max(target,baseline||0), width=300, start=155, scale=value=>value/max*width;
    const items=baseline!==null ? [[planned?'Baseline in article':'Before expansion',baseline,false],[planned?'Announced plan':'After expansion',target,planned]] : [['Announced additions',target,planned]];
    items.forEach(([label,value,dashed],index)=>{const y=25+index*56;svg.append(svgNode('text',{x:0,y:y+20,class:'chart-label'},label),svgNode('rect',{x:start,y,width:scale(value),height:30,rx:3,class:dashed?'chart-bar planned':'chart-bar'}),svgNode('text',{x:Math.min(start+scale(value)+8,485),y:y+20,class:'chart-value'},value));});
    svg.append(svgNode('line',{x1:start,y1:132,x2:start+width,y2:132,class:'chart-axis'}),svgNode('text',{x:start,y:150,class:'chart-tick'},'0'),svgNode('text',{x:start+width,y:150,'text-anchor':'end',class:'chart-tick'},max+' beds'));
    figure.append(svg); const table=el('table','visual-table');const tbody=el('tbody'); for(const [label,value] of items){const row=el('tr');row.append(el('th','',label),el('td','',value+' beds'));tbody.append(row);}table.append(tbody);figure.append(table);section.append(figure);
    if(visual.scenario_available) {
      const details=el('details','scenario-box');details.append(el('summary','','Explore a planning scenario'));
      details.append(el('p','small-text','Illustrate a share of the announced additional capacity. This is an assumption, not a forecast or measured construction progress.'));
      const label=el('label','scenario-label','Assumed share of announced additional capacity'), slider=el('input');slider.type='range';slider.min='0';slider.max='100';slider.step='5';slider.value='75';slider.setAttribute('aria-label','Assumed share of announced additional capacity');label.append(slider);
      const output=el('output','scenario-output');const update=()=>{const value=Number(slider.value),beds=baseline+Math.round((target-baseline)*value/100);output.textContent=`${value}% assumed delivery → approximately ${beds} beds (${baseline} baseline + ${beds-baseline} additional).`;};slider.addEventListener('input',update);update();details.append(label,output,el('p','small-text',`Scenario bounds: ${baseline}–${target} beds, using the article’s reported baseline and plan. No probability or completion date is implied.`));section.append(details);
    }
    const evidence=el('details','visual-evidence'); evidence.append(el('summary','','Source passage for these figures'),el('p','',visual.evidence));section.append(evidence);
  } else if(visual.type==='financial') {
    const comparison=el('div','financial-comparison');
    for(const [label,value] of [[visual.baseline_label,visual.baseline],[visual.target_label,visual.target]]){const row=el('div');row.append(el('span','',label),el('strong','',new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:2}).format(value)));const bar=el('progress');bar.max=Math.max(visual.baseline,visual.target);bar.value=value;bar.setAttribute('aria-label',label);row.append(bar);comparison.append(row);}section.append(comparison);
    if(visual.growth_percent!==null)section.append(el('p','',`${visual.growth_percent>=0?'+':''}${visual.growth_percent}% reported comparison. Review the fiscal periods in the source passage.`));
    const evidence=el('details','visual-evidence');evidence.append(el('summary','','Source passage for this comparison'),el('p','',visual.evidence));section.append(evidence);
  } else {
    const timeline=el('ol','event-timeline');
    const published=el('li');published.append(el('strong','',visual.publication_date?formatDate(visual.publication_date):'Publication date not found'),el('span','','Article publication · not necessarily the event date'));timeline.append(published);
    for(const milestone of visual.milestones||[]){const item=el('li');item.append(el('strong','','Source-reported plan'),el('span','',milestone.date_text));timeline.append(item);}
    const stage=el('li');stage.append(el('strong','',`Stage: ${visual.stage}`),el('span','','Extracted from the announcement; review for later changes.'));timeline.append(stage);section.append(timeline);
  }
  if(visual.budget){const value=visual.budget.amount/1000000;const budget=el('div','reported-budget');budget.append(el('span','','Reported project investment'),el('strong','',`${({more_than:'More than ',nearly:'Nearly ',approximately:'Approximately '}[visual.budget.qualifier]||'')}$${value.toLocaleString()}M`));section.append(budget);}
  if(visual.type==='capacity'&&visual.milestones?.length){const schedule=el('details','visual-evidence');schedule.append(el('summary','','Source-reported schedule'));visual.milestones.forEach(m=>schedule.append(el('p','',m.date_text)));section.append(schedule);}
  section.append(el('p','visual-note',visual.note));
  if(visual.source_url) section.append(safeLink(visual.source_url,'Open the supporting source','source-link'));
  return section;
}
function renderCollection() {
  if(!collectionState)return;
  const run=collectionState.last_run, running=run?.status==='running';
  $('refresh-button').disabled=running; $('refresh-button').replaceChildren(icon('radar'),document.createTextNode(running?'Refreshing…':'Refresh updates'));
  $('collection-indicator').className='collection-indicator '+(running?'running':run?.status==='partial'||run?.status==='failed'?'partial':'');
  const processed=run?.items?.filter(item=>['created','revised','unchanged','excluded'].includes(item.status)).length||0;
  $('collection-summary').textContent=running?`Collecting public sources · ${processed} article(s) processed`:run?`Last collection ${new Date(run.finished_at||run.started_at).toLocaleString()} · ${run.status} · ${run.totals.retrieved||0} articles retrieved`:'No collection run yet. Refresh to retrieve public articles.';
  const root=$('collection-content');root.replaceChildren();
  root.append(el('p','subtext','Coverage is bounded to these sources. Failed requests remain visible; no articles are removed when a source is unavailable.'));
  for(const source of collectionState.sources){const box=el('section','collector-source');box.append(el('h3','',source.name),safeLink(source.index_url,new URL(source.index_url).hostname,'source-link'),el('p','',source.note));box.append(el('p','small-text',source.last_success?`Last article retrieval: ${new Date(source.last_success).toLocaleString()}`:'No successful article retrieval recorded.'));if(source.last_error)box.append(el('p','source-error',source.last_error));root.append(box);}
  if(run){root.append(el('h3','',`Latest run · ${run.status}`));const totals=run.totals;root.append(el('p','small-text',`${totals.created||0} new · ${totals.revised||0} revised · ${totals.unchanged||0} unchanged · ${totals.excluded||0} excluded · ${totals.failed||0} failed requests`));const list=el('div','collection-log');for(const item of run.items){const row=el('div','collection-log-row');row.append(el('span','log-status '+item.status,item.status),el('p','',item.message));if(item.url)row.append(safeLink(item.url,new URL(item.url).hostname,'source-link'));list.append(row);}root.append(list);}
}
function scheduleCollectionPoll(){if(collectionPoll)return;collectionPoll=setTimeout(async()=>{collectionPoll=null;try{collectionState=await request('/api/collection');renderCollection();if(collectionState.last_run?.status==='running')scheduleCollectionPoll();else{await load();notify('Collection finished. Review the candidate updates and source results.');}}catch(error){notify('Could not check collection progress: '+error.message);}},1500);}
async function refreshCollection(){if(!selected.length)return notify('Choose at least one health system to collect.');$('refresh-button').disabled=true;try{await request('/api/collect',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify({systems:selected})});collectionState=await request('/api/collection');renderCollection();scheduleCollectionPoll();}catch(error){$('refresh-button').disabled=false;notify(error.message);}}
function openImport(){ $('import-error').textContent='';$('import-dialog').showModal(); }
async function openEditor(id){
  const r=records.find(row=>row.id===id);if(!r||r.schema_version!==2)return;
  try{const saved=await request(`/api/snapshots/${r.snapshot_id}`);editingRecord=r;
    for(const [field,value] of [['headline',r.title],['summary',r.summary],['entity',r.entity],['category',r.category],['stage',r.development_status],['date',r.publication_date||''],['event-date',r.event_date||''],['note',r.editor_note||'']])$('edit-'+field).value=value;
    const metric=r.metrics?.find(m=>m.unit==='beds');$('edit-has-capacity').checked=!!metric;
    $('edit-capacity-label').value=metric?.label||'';$('edit-baseline').value=metric?.baseline??'';$('edit-target').value=metric?.target??'';$('edit-basis').value=metric?.basis||'planned';$('edit-capacity-evidence').value=metric?.evidence||'';
    $('edit-source-checked').checked=!!r.source_checked;$('edit-error').textContent='';
    const financial=r.metrics?.find(m=>m.unit==='USD');$('financial-fields').hidden=!financial;$('edit-financial-baseline').value=financial?financial.baseline/1000000:'';$('edit-financial-target').value=financial?financial.target/1000000:'';$('edit-financial-evidence').value=financial?.evidence||'';
    $('edit-has-budget').checked=!!r.budget;$('edit-budget-amount').value=r.budget?r.budget.amount/1000000:'';$('edit-budget-qualifier').value=r.budget?.qualifier||'reported';$('edit-budget-evidence').value=r.budget?.evidence||'';$('edit-schedule').value=(r.milestones||[]).map(m=>m.evidence).join('\n');
    $('edit-source-meta').textContent=`${saved.capture_method==='http'?'HTTP retrieval':'Imported source text'} · captured ${new Date(saved.captured_at).toLocaleString()} · ${saved.url}`;$('edit-source-text').textContent=saved.body;
    capacityRequirements();$('edit-dialog').showModal();
  }catch(error){notify(error.message);}
}
function capacityRequirements(){const enabled=$('edit-has-capacity').checked;for(const id of ['edit-capacity-label','edit-target','edit-capacity-evidence'])$(id).required=enabled;}
async function saveEditor(event){
  event.preventDefault();if(!editingRecord)return;$('edit-submit').disabled=true;$('edit-error').textContent='';
  const r=editingRecord, entity=$('edit-entity').value.trim();
  const metrics=$('edit-has-capacity').checked?[{label:$('edit-capacity-label').value.trim(),unit:'beds',baseline:$('edit-baseline').value===''?null:Number($('edit-baseline').value),target:Number($('edit-target').value),basis:$('edit-basis').value,entity,evidence:$('edit-capacity-evidence').value.trim()}]:[];
  const financial=r.metrics?.find(m=>m.unit==='USD');if(financial)metrics.push({...financial,entity,baseline:Number($('edit-financial-baseline').value)*1000000,target:Number($('edit-financial-target').value)*1000000,evidence:$('edit-financial-evidence').value.trim()});
  const budget=$('edit-has-budget').checked?{amount:Number($('edit-budget-amount').value)*1000000,currency:'USD',qualifier:$('edit-budget-qualifier').value,evidence:$('edit-budget-evidence').value.trim()}:null;
  const milestones=$('edit-schedule').value.split('\n').map(s=>s.trim()).filter(Boolean).map(text=>({label:'Reported schedule',date_text:text,basis:'planned',evidence:text,year:Number(text.match(/20\d\d/g)?.at(-1))||null}));
  const changes={title:$('edit-headline').value.trim(),summary:$('edit-summary').value.trim(),entity,category:$('edit-category').value,development_status:$('edit-stage').value,publication_date:$('edit-date').value||null,event_date:$('edit-event-date').value||null,metrics,budget,milestones,editor_note:$('edit-note').value.trim(),source_checked:$('edit-source-checked').checked};
  try{await request('/api/edit',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify({id:r.id,version:r.version,changes})});$('edit-dialog').close();await load();if($('detail-dialog').open&&detailId===r.id){const brief=await request(`/api/signals/${r.id}/brief`);briefs.set(r.id,brief);renderDetail(r.id);}notify('Reviewed version saved and returned to content review. Approve it to include it in the sales feed.');}catch(error){$('edit-error').textContent=error.message;}finally{$('edit-submit').disabled=false;}
}
async function saveImport(event){event.preventDefault();$('import-submit').disabled=true;$('import-error').textContent='';try{const data={system:$('import-system').value,url:$('import-url').value.trim(),title:$('import-headline').value.trim(),publication_date:$('import-date').value||null,text:$('import-text').value};await request('/api/import',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify(data)});$('import-dialog').close();$('import-form').reset();await load();await switchView('review');notify('Source text saved. The normalized candidate is ready for review.');}catch(error){$('import-error').textContent=error.message;}finally{$('import-submit').disabled=false;}}

hydrateIcons();
document.querySelectorAll('[data-view]').forEach(node => node.addEventListener('click', () => switchView(node.dataset.view)));
document.querySelectorAll('[data-close]').forEach(node => node.addEventListener('click', () => $(node.dataset.close).close()));
for (const id of ['manage-button','manage-sidebar','coverage-manage']) $(id).addEventListener('click', openSystems);
for (const id of ['method-button','list-method']) $(id).addEventListener('click', () => { if (method) $('method-dialog').showModal(); });
for (const id of ['expand-recommendations','view-all']) $(id).addEventListener('click', () => switchView('recommendations'));
$('recommendation-search').addEventListener('input', renderRecommendations); $('recommendation-category').addEventListener('change', renderRecommendations);
$('review-search').addEventListener('input', renderReviews); $('review-status').addEventListener('change', renderReviews);
$('record-type').addEventListener('change',renderReviews);
$('preview-drafts').addEventListener('change',render);
$('refresh-button').addEventListener('click',refreshCollection);
$('collection-details').addEventListener('click',()=>{renderCollection();$('collection-dialog').showModal();});
$('import-button').addEventListener('click',openImport);
$('collection-import').addEventListener('click',()=>{$('collection-dialog').close();openImport();});
$('edit-has-capacity').addEventListener('change',capacityRequirements);
$('edit-form').addEventListener('submit',saveEditor);
$('import-form').addEventListener('submit',saveImport);
$('source-search').addEventListener('input', () => { sourcePage = 0; renderSources(); });
$('source-prev').addEventListener('click', () => { sourcePage = Math.max(0, sourcePage - 1); renderSources(); $('sources-view').scrollIntoView({block:'start'}); });
$('source-next').addEventListener('click', () => { sourcePage++; renderSources(); $('sources-view').scrollIntoView({block:'start'}); });
for (const kind of ['recommendations','review','sources']) $('export-' + kind).addEventListener('click', () => exportData(kind));
$('systems-form').addEventListener('submit', event => { event.preventDefault(); selected = Array.from($('system-options').querySelectorAll('input:checked'), node => node.value); sourcePage = 0; let persisted = true; try { localStorage.setItem(storageKey, JSON.stringify(selected)); } catch { persisted = false; } $('systems-dialog').close(); render(); notify(persisted ? 'Health systems saved. Recommendations now reflect your selection.' : 'Selection applied for this visit. Browser storage is unavailable.'); });
document.addEventListener('click', event => { document.querySelectorAll('.why-wrap').forEach(node => { if (!node.contains(event.target)) node.closePopover?.(); }); });
document.addEventListener('keydown', event => { if (event.key === 'Escape') document.querySelectorAll('.why-wrap').forEach(node => node.closePopover?.()); });
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target !== dialog) return; const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); }));
$('retry').addEventListener('click', () => load(!records.length).catch(() => {}));
const initialView = () => ({'/ui':'widgets','/ui/':'widgets','/recommendations':'recommendations','/review':'review','/sources':'sources'}[location.pathname] || 'overview');
window.addEventListener('popstate', () => switchView(initialView(), true, false));
load(true).then(() => switchView(initialView(), false, false)).catch(() => {});
