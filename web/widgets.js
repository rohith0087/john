'use strict';

let galleryLayout = 'all';
let galleryRenderKey = '';
let galleryCarouselCleanup = null;
const widgetLayouts = [
  {key:'vertical', name:'Vertical feed', tag:'THE DAILY BRIEF', description:'A focused queue beside your pipeline. Scroll through account updates without moving the rest of the dashboard.', fit:'Sidebar · internal scroll', theme:'blue'},
  {key:'horizontal', name:'Horizontal rail', tag:'ROOM TO EXPLORE', description:'Give recommendations a full row. Browse cards sideways while keeping the sales metrics above in view.', fit:'Full-width row · card carousel', theme:'teal'},
  {key:'spotlight', name:'Priority spotlight', tag:'ONE CLEAR NEXT STEP', description:'Give one account your attention. Move through the ranked feed one recommendation at a time.', fit:'Hero tile · paged recommendations', theme:'indigo'},
  {key:'compact', name:'Compact action list', tag:'SMALL FOOTPRINT, CLEAR SIGNAL', description:'A quiet, scannable list that sits comfortably among existing dashboard metrics.', fit:'Small tile · three recommendations', theme:'slate'},
  {key:'band', name:'Recommendation strip', tag:'DASHBOARD STRIP', description:'A single recommendation in a slim row between existing dashboard metrics and charts. Page through updates or open the full list.', fit:'Shallow row · manual paging', theme:'teal'},
  {key:'tabbed', name:'Tabbed recommendation tile', tag:'FILTERED TILE', description:'A small tile beside the pipeline. Switch between development types while keeping the dashboard in view.', fit:'Sidebar tile · category tabs', theme:'blue'},
  {key:'pair', name:'Two-card module', tag:'SIDE-BY-SIDE CARDS', description:'Show two priorities together in one dashboard module, alongside account activity and pipeline metrics.', fit:'Medium tile · two cards', theme:'slate'},
];

function galleryRows() {
  return recommendations.filter(r => included(r) && ($('widget-data').value === 'all' || r.status === 'approved'));
}
function widgetAction(r) {
  if (r.extraction_warnings?.some(w=>w.includes('pending approval'))) return 'Check approval and project timing';
  if (r.category === 'Expansion') return r.development_kind === 'service_capability' ? 'Review the new service capability' : r.development_status === 'completed' ? 'Review ongoing supply needs' : r.development_status === 'underway' ? 'Check project scope and timing' : 'Qualify the expansion opportunity';
  return {'Leadership':'Update the account contact map','Financial':'Review the account outlook','Ownership & partnerships':'Check purchasing implications'}[r.category] || 'Review the account update';
}
function widgetMetric(r) {
  const m = r.metrics?.find(m => m.unit === 'beds');
  if (m) return `${m.baseline === null ? '+' : m.baseline + ' → '}${m.target} ${m.label.toLowerCase()} · ${m.basis === 'planned' ? 'planned' : 'reported'}`;
  if (r.budget) return `${({more_than:'>',nearly:'Nearly ',approximately:'About '}[r.budget.qualifier] || '')}$${(r.budget.amount / 1e6).toLocaleString()}M reported investment`;
  return {planned:'Planned development',completed:'Reported completed',underway:'Work underway',announced:'New announcement'}[r.development_status] || 'Account development';
}
function widgetMeta(r) {
  const meta = el('div','wg-meta'); meta.append(el('span','wg-system', systems[r.system]), el('span','wg-state ' + r.status, r.status === 'approved' ? 'Reviewed' : 'Draft')); return meta;
}
function widgetWhy(r, rank) {
  const reason = el('details','wg-why'), label = el('summary','',`Why #${rank}?`);
  reason.append(label); const text=el('div','wg-why-content');
  text.append(el('strong','',`${r.score}/100 · shared priority criteria`));
  [...r.factors].sort((a,b)=>b.points-a.points).slice(0,2).forEach(f=>text.append(el('p','',`${f.label}: ${f.points}/${f.maximum}. ${f.reason}`)));
  text.append(el('p','',`${r.source_checked ? 'Source checked in local review.' : 'Source facts await review.'} Priority helps plan research; it does not confirm buying intent.`));
  reason.append(text); return reason;
}
function widgetCard(r, rank, variant='') {
  const card=el('article','wg-card '+variant), top=el('div','wg-card-top');
  top.append(el('span','wg-rank',String(rank).padStart(2,'0')), widgetMeta(r));
  const heading=button(widgetAction(r),'wg-action',()=>openDetail(r.id));
  heading.setAttribute('aria-label',`Open account brief: ${r.entity} · ${widgetAction(r)}`);
  card.append(top,heading,el('p','wg-entity',r.entity),el('p','wg-signal',r.headline),el('span','wg-metric',widgetMetric(r)));
  const bottom=el('div','wg-card-bottom');bottom.append(widgetWhy(r,rank),el('span','wg-date',formatDate(r.publication_date,false)));card.append(bottom);return card;
}
function widgetPanel(title, subtitle, rows, name) {
  const panel=el('section','wg-panel'), head=el('div','wg-panel-head'), mark=el('span','wg-icon');mark.append(icon('spark'));
  const copy=el('div');copy.append(el('h3','',title),el('p','',subtitle));head.append(mark,copy,el('span','wg-count',String(rows.length).padStart(2,'0')));panel.append(head);
  const footer=button('View all recommendations','wg-footer',()=>expandWidget(name));footer.append(icon('arrow-right'));footer.setAttribute('aria-label',`View all recommendations from ${name}`);
  return {panel,footer};
}
function expandWidget(name, category='') {
  $('preview-drafts').checked=$('widget-data').value==='all';
  $('recommendation-search').value='';$('recommendation-category').value=category;
  $('gallery-return').hidden=false;$('gallery-origin').textContent=`Expanded from ${name} · ${$('widget-data').value==='all'?'includes draft updates':'approved updates'}`;
  render();switchView('recommendations');
}
function mockMetrics(items=[['Tracked accounts','24','Across your territory'],['Open opportunities','18','In your active pipeline'],['Pipeline value','$1.24M','Across open opportunities']]) {
  const bar=el('div','demo-metrics');for(const [label,value,note] of items){const cell=el('div');cell.append(el('span','',label),el('strong','',value),el('small','',note));bar.append(cell);}return bar;
}
function mockPipeline(compact=false) {
  const box=el('section','demo-context-panel '+(compact?'small':'')),head=el('div','demo-panel-head');head.append(el('h3','','Opportunity pipeline'),el('span','','By stage'));box.append(head);
  const stages=[['Discovery',8,78],['Qualification',6,59],['Proposal',3,35],['Negotiation',1,19]];
  for(const [stage,count,percent] of stages){const line=el('div','demo-stage'),bar=el('span','demo-stage-track'),fill=el('i');fill.style.width=percent+'%';bar.append(fill);line.append(el('span','',stage),bar,el('b','',count));box.append(line);}
  box.append(el('p','demo-small-note','Illustrative sales data'));return box;
}
function mockAccounts() {
  const box=el('section','demo-context-panel'),head=el('div','demo-panel-head');head.append(el('h3','','Account engagement'),el('span','','Last 30 days'));box.append(head);
  const chart=el('div','demo-engagement'),ring=el('div','demo-ring');ring.append(el('strong','','16'),el('span','','accounts reached'));const legend=el('div','demo-legend');legend.append(el('span','','● 16 contacted'),el('span','','● 8 to follow up'));chart.append(ring,legend);box.append(chart,el('p','demo-small-note','Illustrative sales data'));return box;
}
function dashboardShell(type) {
  const shell=el('div','demo-dashboard '+type),header=el('div','demo-dashboard-header'),identity=el('div','demo-identity');
  const mark=el('span','demo-logo');mark.append(icon('building'));identity.append(mark,el('strong','','Account workspace'));
  const right=el('span','demo-period','Sales overview');header.append(identity,right);
  const sub=el('div','demo-dashboard-sub');sub.append(el('div','demo-page-name','Your territory at a glance'),el('span','demo-example','Example dashboard metrics'));
  shell.append(header,sub);return shell;
}
function verticalModel(rows) {
  const shell=dashboardShell('vertical-dashboard');shell.append(mockMetrics());
  const grid=el('div','demo-two-columns'),context=el('div','demo-context-column');context.append(mockPipeline(),mockAccounts());
  const {panel,footer}=widgetPanel('Recommended follow-up','Your ranked account updates',rows,'Vertical feed'),list=el('div','wg-vertical-list');list.tabIndex=0;list.setAttribute('role','region');list.setAttribute('aria-label','Scrollable vertical recommendations');
  rows.forEach((r,i)=>list.append(widgetCard(r,i+1)));panel.append(list,footer);grid.append(context,panel);shell.append(grid);return shell;
}
function horizontalModel(rows) {
  const shell=dashboardShell('horizontal-dashboard');shell.append(mockMetrics([['Follow-ups due','7','On your account plan'],['Active accounts','24','In your territory'],['Pipeline value','$1.24M','Across open opportunities']]));
  const {panel,footer}=widgetPanel('Recommended for your accounts','Browse the feed without leaving your dashboard',rows,'Horizontal rail');
  const rail=el('div','wg-horizontal-rail');rail.tabIndex=0;rail.setAttribute('role','region');rail.setAttribute('aria-label','Horizontal recommendation cards');rows.forEach((r,i)=>rail.append(widgetCard(r,i+1,'rail-card')));
  const controls=el('div','wg-rail-controls'),position=el('span','',rows.length?`1 of ${rows.length}`:'No updates'),prev=button('','wg-arrow',()=>move(-1),'chevron'),next=button('','wg-arrow',()=>move(1),'chevron');prev.classList.add('previous');prev.setAttribute('aria-label','Previous recommendation cards');next.setAttribute('aria-label','Next recommendation cards');
  function move(direction){const width=rail.firstElementChild?.getBoundingClientRect().width||300;rail.scrollBy({left:direction*(width+14),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
  function update(){const first=rail.firstElementChild;const index=first?Math.min(rows.length,Math.round(rail.scrollLeft/(first.getBoundingClientRect().width+14))+1):0;position.textContent=rows.length?`${index} of ${rows.length}`:'No updates';prev.disabled=rail.scrollLeft<2;next.disabled=rail.scrollLeft+rail.clientWidth>=rail.scrollWidth-2;}
  rail.addEventListener('scroll',update,{passive:true});rail.addEventListener('keydown',event=>{if(event.target!==rail)return;if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();move(event.key==='ArrowRight'?1:-1);}});
  const arrows=el('div');arrows.append(prev,next);controls.append(position,arrows);panel.append(rail,controls,footer);shell.append(panel);
  const observer=new ResizeObserver(update);observer.observe(rail);galleryCarouselCleanup=()=>observer.disconnect();return shell;
}
function spotlightModel(rows) {
  const shell=dashboardShell('spotlight-dashboard');shell.append(mockMetrics());const grid=el('div','demo-spotlight-grid'),hero=el('section','wg-spotlight'),content=el('div'),controls=el('div','wg-spotlight-controls');let index=0;
  const prev=button('','wg-arrow',()=>show(index-1),'chevron'),next=button('','wg-arrow',()=>show(index+1),'chevron'),position=el('span'),dots=el('div','wg-dots');prev.classList.add('previous');prev.setAttribute('aria-label','Previous spotlight recommendation');next.setAttribute('aria-label','Next spotlight recommendation');
  const dotsButtons=rows.map((r,i)=>{const dot=button('','wg-dot',()=>show(i));dot.setAttribute('aria-label',`Show spotlight recommendation ${i+1}: ${r.entity}`);dots.append(dot);return dot;});
  function show(value){index=Math.max(0,Math.min(rows.length-1,value));const r=rows[index];content.replaceChildren();prev.disabled=index<=0;next.disabled=index>=rows.length-1;position.textContent=rows.length?`${index+1} / ${rows.length}`:'0 / 0';dotsButtons.forEach((b,i)=>{b.setAttribute('aria-pressed',String(i===index));});if(!r){content.append(el('h3','','No recommendations in this selection'));return;}
    const label=el('div','wg-spotlight-label');label.append(icon('spark'),document.createTextNode(`PRIORITY ${index+1} · ACCOUNT FOLLOW-UP`));
    content.append(label,widgetMeta(r),el('h3','',widgetAction(r)),el('p','wg-spotlight-entity',r.entity),el('p','wg-spotlight-context',r.rationale),el('div','wg-spotlight-metric',widgetMetric(r)));
    const actions=el('div','wg-spotlight-actions'),details=button('View account brief','button primary',()=>openDetail(r.id));details.append(icon('arrow-right'));actions.append(details,widgetWhy(r,index+1));content.append(actions);
  }
  const left=el('div');left.append(prev,position,next);controls.append(left,dots,button('See all','wg-spotlight-all',()=>expandWidget('Priority spotlight')));hero.append(content,controls);grid.append(hero,mockPipeline(true));shell.append(grid);show(0);return shell;
}
function compactModel(rows) {
  const shell=dashboardShell('compact-dashboard'),grid=el('div','demo-compact-grid');grid.append(mockAccounts());
  const {panel,footer}=widgetPanel('Suggested follow-up',`Your top ${Math.min(3,rows.length)} account update${rows.length === 1 ? '' : 's'}`,rows,'Compact action list');const list=el('div','wg-compact-list');
  rows.slice(0,3).forEach((r,i)=>{const row=button('','wg-compact-row',()=>openDetail(r.id)),text=el('span','wg-compact-copy');text.append(el('strong','',widgetAction(r)),el('small','',r.entity));const rank=el('span','wg-rank',String(i+1).padStart(2,'0'));row.append(rank,text,el('span','wg-compact-status '+r.status,r.status==='pending'?'Draft':`${r.score}`),icon('chevron'));row.setAttribute('aria-label',`Open ${r.entity}: ${widgetAction(r)}${r.status==='pending'?' (draft)':''}`);list.append(row);});
  panel.append(list,footer);grid.append(panel);shell.append(mockMetrics([['Active opportunities','18','In your territory'],['Meetings this week','9','Across followed accounts']]),grid);return shell;
}
function bandModel(rows) {
  const shell=dashboardShell('band-dashboard');shell.append(mockMetrics());
  const band=el('section','wg-band'),content=el('div','wg-band-content');let index=0;
  const header=el('div','wg-band-label');header.append(icon('spark'),el('strong','','Recommended follow-up'));
  const controls=el('div','wg-band-controls'),prev=button('','wg-arrow previous',()=>show(index-1),'chevron'),next=button('','wg-arrow',()=>show(index+1),'chevron'),position=el('span');
  prev.setAttribute('aria-label','Previous strip recommendation');next.setAttribute('aria-label','Next strip recommendation');
  function show(value){index=Math.max(0,Math.min(rows.length-1,value));const r=rows[index];content.replaceChildren();prev.disabled=index===0;next.disabled=index===rows.length-1;position.textContent=`${index+1} / ${rows.length}`;
    const copy=el('div');copy.append(widgetMeta(r),button(widgetAction(r),'wg-action',()=>openDetail(r.id)),el('p','wg-entity',r.entity));
    const brief=button('View brief','text-button',()=>openDetail(r.id));content.append(el('span','wg-rank',String(index+1).padStart(2,'0')),copy,brief);
  }
  const all=button('See all','text-button',()=>expandWidget('Recommendation strip'));all.setAttribute('aria-label','View all recommendations from Recommendation strip');controls.append(prev,position,next,all);band.append(header,content,controls);show(0);shell.append(band);
  const context=el('div','demo-context-pair');context.append(mockPipeline(),mockAccounts());shell.append(context);return shell;
}
function tabbedModel(rows) {
  const shell=dashboardShell('tabbed-dashboard');shell.append(mockMetrics());const grid=el('div','demo-two-columns'),context=el('div','demo-context-column');context.append(mockPipeline(),mockAccounts());
  const {panel,footer}=widgetPanel('Account follow-up','Filter by the account change',rows,'Tabbed recommendation tile'),tabs=el('div','wg-category-tabs'),list=el('div','wg-tabbed-list');list.tabIndex=0;list.setAttribute('role','region');list.setAttribute('aria-label','Filtered recommendation updates');let active='';const controls=[];
  function choose(category){active=category;controls.forEach(([key,control])=>control.setAttribute('aria-pressed',String(key===category)));const filtered=rows.filter(r=>!category||r.category===category);list.replaceChildren();filtered.forEach(r=>list.append(widgetCard(r,rows.indexOf(r)+1)));if(!filtered.length)list.append(el('p','wg-tile-empty','No collected updates of this type in your selection.'));list.scrollTop=0;footer.textContent=`View all ${category ? category.toLowerCase()+' updates' : 'recommendations'}`;}
  for(const [key,label] of [['','All'],['Expansion','Expansion'],['Leadership','Leadership'],['Ownership & partnerships','Ownership']]){const tab=button(label,'wg-category-tab',()=>choose(key));tab.setAttribute('aria-label',`Filter tile: ${label}`);controls.push([key,tab]);tabs.append(tab);}
  footer.addEventListener('click',()=>{$('recommendation-category').value=active;renderRecommendations();});panel.append(tabs,list,footer);grid.append(context,panel);shell.append(grid);choose('');return shell;
}
function pairModel(rows) {
  const shell=dashboardShell('pair-dashboard');shell.append(mockMetrics());const grid=el('div','demo-pair-grid'),{panel,footer}=widgetPanel('Two accounts to focus on','Highest priority first',rows,'Two-card module'),cards=el('div','wg-card-pair');
  rows.slice(0,2).forEach((r,i)=>cards.append(widgetCard(r,i+1)));panel.append(cards,footer);grid.append(panel,mockPipeline());shell.append(grid);return shell;
}
function renderWidgets(force=false) {
  const rows=galleryRows(),key=JSON.stringify([galleryLayout,$('widget-data').value,selected,rows.map(r=>[r.id,r.version,r.status])]);
  if(!force&&key===galleryRenderKey)return;galleryRenderKey=key;galleryCarouselCleanup?.();galleryCarouselCleanup=null;
  $('gallery-data-status').textContent=`${rows.length} collected updates${rows.some(r=>r.status==='pending')?` · ${rows.filter(r=>r.status==='pending').length} drafts included for layout preview`:' · approved only'} · same feed in every layout`;
  const tabs=$('layout-tabs');tabs.replaceChildren();for(const [key,label] of [['all','All layouts'],...widgetLayouts.map(m=>[m.key,m.name])]){const tab=button(label,'layout-tab',()=>{galleryLayout=key;renderWidgets();$('widget-models').scrollIntoView({block:'start',behavior:'instant'});});tab.setAttribute('aria-pressed',String(galleryLayout===key));tabs.append(tab);}
  const root=$('widget-models');root.replaceChildren();
  if(!rows.length){root.append(emptyState('No updates in this selection','Include drafts for preview, or select health systems with reviewed recommendations.'));return;}
  const builders={vertical:verticalModel,horizontal:horizontalModel,spotlight:spotlightModel,compact:compactModel,band:bandModel,tabbed:tabbedModel,pair:pairModel};
  widgetLayouts.forEach((model,index)=>{if(galleryLayout!=='all'&&galleryLayout!==model.key)return;const section=el('section',`widget-model theme-${model.theme}`);section.id='model-'+model.key;section.setAttribute('aria-labelledby','model-title-'+model.key);const head=el('div','model-heading'),copy=el('div'),number=el('span','model-number','0'+(index+1));const title=el('h2','',model.name);title.id='model-title-'+model.key;copy.append(el('span','model-kicker',model.tag),title,el('p','',model.description));head.append(number,copy,el('span','model-fit',model.fit));section.append(head,builders[model.key](rows));root.append(section);});
}
$('widget-data').addEventListener('change',()=>renderWidgets());
$('return-widgets').addEventListener('click',()=>switchView('widgets'));
// Deferred scripts and the initial API requests can finish in either order.
if (method) renderWidgets();
