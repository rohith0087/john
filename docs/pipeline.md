# IDN Watch: from public updates to sales follow-up

[Open the editable diagram](https://www.tldraw.com/f/NO7OKl61thLcJxOR_6lnj).

The board has a client overview, the detailed processing flow, and a map of engine responsibilities. These stages are functions in the current local application, not separately deployed services.

## Which comes first?

Basic collection checks come first. Then normalization creates a consistent record, and the structured-data validator checks that record. Human source review comes later and is separate from both.

| Stage | What happens | What moves forward |
| --- | --- | --- |
| Scope and collection | Refresh selected parent IDNs; fetch configured public sources and discover a bounded number of articles. Check allowed URLs and usable title/body. | Extracted article text and source metadata. |
| Evidence capture | Save a snapshot of text, URL, date and capture details; retain original HTML when fetched. | Traceable source evidence. |
| Normalization engine | Classify supported developments; map parent IDN/facility; standardize dates, stage, capacity, investment and supporting passages. | One consistent candidate record. Unsupported stories are excluded. |
| Structured-data validator | Check schema, dates, numeric bounds, units, evidence fields and comparable entities. | A structurally valid record. This does not independently prove the article or extracted interpretation is true. |
| Version and replay check | Compare stable source identity, snapshot and payload. | New/changed facts become a pending version. Unchanged input retains the current version, corrections and approval. |
| Editorial review | Inspect evidence, correct facts with a note, explicitly source-check when appropriate, then approve/reject/reset. | Approved collected versions enter the default sales feed. Corrections are validated again and create a pending version. |
| Action and ranking rules | Generate a practical follow-up and score shared factors for eligible records. | A sorted, explainable list of recommendations. |
| Presentation | Filter by selected IDNs before choosing top actions. Open the expanded list or account brief with evidence and context visuals. | Account research and qualification guidance for sales. |

## What happens between the engines?

Normalization does not hand straight to ranking. It passes through structured validation, version/replay handling and editorial eligibility first. The default sales API ranks approved collected records. An explicitly selected draft preview can also score pending records; it does not approve them.

Rejected or pending records stay outside the default sales feed. Repeated content does not automatically lose prior approval. Changed source content does need review again. Related articles can be flagged, but cross-source event merging is not implemented.

Fetch failures, excluded stories and failed candidates appear in collection outcomes. Previously saved good data is retained. When a public page cannot be fetched, a manually imported excerpt can enter the same snapshot, normalization, validation and review path with its provenance retained.

## Current ranking versus a future recommendation engine

The current application already generates suggested actions with rules. It uses one shared scoring method:

- Scale of change: 30 points.
- Supplier relevance: 25 points.
- Next-step clarity: 15 points.
- Article recency: 15 points.
- Source verification: 15 points.

Approval does not itself increase source-verification points. Priority scores are not buying probability, forecast revenue or proof of procurement demand.

A future personalized recommendation engine could extend or replace this rules layer using supplier products, territory, account/CRM context and evaluated feedback. It is not an additional implemented service in the current pipeline.

## Example to explain during the demo

An official article announces an emergency department growing from 14 to 25 beds. The collector captures the article. Normalization records the parent IDN, facility, planned stage and the two comparable bed counts with their evidence. Validation checks the values and units. Version handling decides whether this is new or changed. An editor reviews and approves it. The rules suggest checking project timing and purchasing responsibility, explain its priority, and show a source-backed capacity comparison in the brief.

The 78.6% planned increase describes that facility's announced bed capacity, not forecast sales or demand.

## Code map

- `collector.py`: collection, extraction, snapshots, collection outcomes.
- `intelligence.py`: normalization, structured-fact validation, rule-based actions, scores and visual specifications.
- `app.py`: ingestion validation, version/replay handling, editorial corrections, decisions and feed eligibility.
- `recommendations.py`: ranking and reference-record support.
- `web/`: widgets, expanded recommendations, account briefs and review UI.

Diagram sources: [processing flow](pipeline-flow.mmd), [engine responsibilities](engine-responsibilities.mmd), and [client overview](client-overview.mmd).

