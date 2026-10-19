# IDN Watch — account intelligence

A working local prototype for sales teams following selected IDNs in Georgia, the Carolinas, and Florida. It collects a bounded set of public articles, normalizes developments, produces explainable recommendations, and queues facts for editorial review. The compact dashboard shows the top three approved recommendations; account briefs show evidence, follow-up steps, charts, and review history.

## Run and try it

Python 3.11+; no pip packages, API key, or subscription required. Windows collection uses PowerShell and the normal Windows certificate trust store.

```powershell
python app.py serve
```

Open http://127.0.0.1:8765. Click **Refresh updates**, inspect **Collection details**, then open **Content review**. Review a draft, correct facts if necessary, and approve it to place that version in the local sales feed. **Preview draft recommendations** lets you inspect pending suggestions separately. Health-system selections are saved in this browser and filter before the top three are chosen.

A fresh clone starts without the local collected database or review decisions. Refresh and review updates to populate the feed. To load the six earlier profile reference examples into review, run `python app.py import data/profile_examples.json`; these do not populate the collected sales feed.

For a client walkthrough, see the [processing pipeline and engine responsibilities](docs/pipeline.md), including the editable tldraw board and Mermaid sources.

The earlier demonstration articles remain: HCA Florida Raulerson's announced emergency-department expansion and AdventHealth Daytona Beach's reported completed expansion. Their review notes identify the assistant's local demonstration checks; these are not client sign-off. Other collected candidates await review. The original six profile examples remain available as reference records in review, outside the collected sales feed.

SQLite stores data in `data/watch.db`. The server listens only on loopback. It is a single-reviewer development app, with same-origin/session-token write safeguards, not production authentication or integration with the client's dashboard.

## Widget gallery

Open http://127.0.0.1:8765/ui or choose **Widget gallery** in the navigation. Seven working layouts place the same recommendation feed among clearly labeled illustrative sales metrics:

1. Vertical feed with internal scrolling beside a pipeline/engagement view.
2. Horizontal rail with scroll snapping, previous/next controls, and keyboard arrows.
3. Priority spotlight with manual paging and direct account-brief access.
4. Compact action list showing up to three recommendations.
5. Recommendation strip: a shallow, manually paged row between dashboard charts and metrics.
6. Tabbed recommendation tile: a bounded, scrolling tile filtered by development type.
7. Two-card module: two recommendations beside the opportunity pipeline.

Layout buttons show one option or all seven. The gallery explicitly includes labeled drafts by default so scrolling can be demonstrated; **Approved updates only** switches the entire collection to reviewed items. Health-system selection applies to every model. Recommendations come from the existing API; surrounding pipeline figures are illustrative and are not inferred from the news.

**View all** opens the full searchable recommendation page at `/recommendations`, preserving the gallery's draft mode and providing a return link. Each widget can open the same account brief, with evidence and review history. The former full-page-style list-and-insight model has been replaced by the compact recommendation strip. The old “Before you contact the account” panel has been removed from Overview.

## Collection and normalization

The configured parent IDNs are AdventHealth, HCA Healthcare, Piedmont Healthcare (Georgia), Wellstar Health System (Georgia), and Novant Health (Carolinas). Facilities are evidence locations within these IDNs, not separate target accounts. Account settings and source-text import use this shared registry.

Regional collectors use official Piedmont news, Wellstar newsroom, and Novant press releases. Each refresh retrieves at most five articles per added IDN, combining selected expansion URLs with bounded newsroom discovery. The first regional run retrieved 15 articles without errors, producing 10 candidates and excluding five. Four expansion records were source-checked locally for demonstration: Piedmont Walton's October 14 opening, Piedmont Newton's September 22 relocation filing, Wellstar Columbia County's August 26 opening, and Novant's June 15 proposed-bed application. This does not establish current procurement demand or complete IDN coverage. Review notes distinguish local demonstration checks from client sign-off.

Extraction keeps room counts separate from bed counts, flags pending approval, preserves approximate investment qualifiers, and avoids assigning an entire capital-plan budget to one tower. Service-line recruitment/technology changes receive capability-level follow-ups; incidental facilities in a system executive's remit do not turn the executive appointment into a facility-level event.

The existing Florida sources in `data/collectors.json` cover AdventHealth West Florida issuer releases on PRNewswire, HCA Florida's newsroom, and an AdventHealth newsroom attempt. These cover selected divisions; the additional regional collectors are described above. Articles are fetched from fixed public hosts, without redirects or disabled certificate verification. Collection runs asynchronously and reports created/revised/unchanged/excluded/failed outcomes. It does not run on a schedule.

Direct AdventHealth newsroom requests currently return HTTP 403 in this environment. **Import source text** accepts a title, allowed source URL, publication date, and browser-visible text as a local draft. The app records that this is a manual excerpt rather than a complete HTTP capture. No login is needed for the configured public sources. Failed requests retain previously stored data and show coverage gaps.

The rules identify supported expansion, ownership/partnership, leadership, and financial headlines; irrelevant coverage is logged as excluded. Records carry a health system, facility match, development stage, article date (nullable), source evidence, extracted capacity/investment facts, and source-reported schedule passages. Unknown matches and dates remain visible uncertainties. Saved source snapshots preserve the retrieved text and original HTML when available. Repeated source URLs/snapshots do not duplicate records. Changed content creates a new pending version; same-snapshot refreshes preserve documented editorial corrections. Related coverage is flagged for review but is not automatically merged across URLs.

## Recommendations and sales presentation

The same rule-based method applies to every account: scale of change (30), relevance across supplier categories (25), next-step clarity (15), article recency (15), and source verification (15). Retrieved text earns 8 evidence points, manually imported text 4, explicitly checked source facts 15. Approval alone does not improve evidence quality. Unknown/future publication dates earn no recency points. Ties use publication date, then record ID.

Recommendations derive from the normalized development, rather than six fixed playbooks. Completed expansions suggest qualifying ongoing supplies and services; planned projects suggest checking scope, timing, and purchasing responsibilities. Service/technology launches use narrower capability-oriented actions. Scores express provisional editorial priority, not buying probability or predicted revenue. Supplier-specific products, CRM context, and learned ranking are deferred.

Each card separates **what changed**, **why it matters**, and **suggested next step**. Priority reasons work on hover, focus, or click. The account brief adds qualification steps, evidence, assumptions, source links, and version history. Segoe UI, navy navigation, blue actions, and neutral surfaces maintain a familiar business interface. There are no promotional prototype/phase labels in the sales UI.

## Charts and scenarios

Charts use extracted, source-supported comparisons, with a zero axis and an accessible values table. For example, Raulerson's announced emergency beds increase from 14 to 25 (78.6% planned); Daytona Beach reports inpatient capacity from 362 to 466 (28.7% reported). They describe different facilities and measures and are never combined.

A planned capacity comparison offers a 0–100% scenario slider over the announced additional beds. It cannot exceed the source plan. It represents a user assumption, not construction progress, a demand forecast, or a revenue projection. Completed expansions do not offer a future-growth slider. Missing baseline means no percentage. When numeric comparison is unavailable, the brief shows only source-reported schedule/investment context. Explicit comparable financial amounts can produce a historical two-period chart; no financial forecast is invented.

## Review and audit

Editors can correct the headline, summary, facility, category, stage, dates, capacity, existing financial comparison, budget, and schedule. Supporting metric passages must exist in the saved source and contain the corresponding values/units. A review note is required. The source-check checkbox is separate from approval. Corrections create a new pending version and retain the previous payload and decisions; stale edits are rejected. Version history shows prior facts and review notes. These validations establish traceability, not automatic semantic fact checking.

Approve adds the current collected version to the local sales feed; reject removes it; reset returns it to pending. No action publishes to the client platform. JSON exports carry review/provenance information and identify draft previews. The source library's 554 extracted profile links are a reference inventory, not 554 monitored sources.

## Structure and API

- `app.py`: local server, versioned ingestion, editing, review, import, and APIs.
- `collector.py`, `scripts/fetch_public.ps1`: bounded collection, snapshots, source health, run outcomes.
- `intelligence.py`: normalization, evidence validation, generic recommendations, chart specifications.
- `recommendations.py`: ranking and legacy reference support.
- `web/`: dashboard, review workspace, account brief, and source library.
- `tests/`: original pipeline checks and live-pipeline fixtures.

Read endpoints: `/api/signals`, `/api/recommendations` (approved collected records), `/api/recommendations?include_drafts=1`, `/api/collection`, `/api/signals/{id}/brief`, `/api/signals/{id}/history`, `/api/snapshots/{id}`, `/api/sources`.

Token-protected local writes: `POST /api/collect`, `/api/import`, `/api/edit`, `/api/review`. The page obtains its session token from `/api/signals`. CLI collection is also available with `python app.py collect`.

## Checks and remaining scope

```powershell
# Keep temporary SQLite fixtures within this workspace in restricted environments.
New-Item -ItemType Directory -Force .test-temp
$env:TEMP = (Resolve-Path .test-temp).Path
$env:TMP = $env:TEMP
python -m unittest discover -s tests -q
node --check web/app.js
```

37 tests cover replay, revisions, stale review/edit protection, source failure, publication dates, relevance rules, same-entity capacity bounds, unsupported corrections, imported provenance, leadership classification, financial units, and discovery. Browser checks cover refresh, corrections, approval to feed, manual import, graphs, and bounded scenarios.

This is a functional Phase 1 prototype, not a finished monitoring service. Broader source coverage, evaluated extraction recall/precision, cross-source event merging, scheduled jobs, production access control, supplier personalization, CRM integration, and client validation remain future work. No forecasting accuracy or sales-lift claim has been established.
