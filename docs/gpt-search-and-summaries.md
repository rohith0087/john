# GPT search and summaries

The dashboard theme and layouts remain the same. The existing Refresh updates action can now run a GPT-backed discovery and summary path.

## Processing order in GPT mode

1. Load server-side configuration and verify a key is present.
2. Search for recent developments at each selected parent IDN using the Responses API web-search tool. Restrict discovery to that IDN's configured source hosts.
3. Take URLs from completed search-tool sources/citations, rather than links invented in model prose. Bound the article count and reject other hosts, credentials in URLs, PDFs and known index pages.
4. Fetch article HTML and extract title, body and publication date using the existing collector. Save the source snapshot. A search result does not bypass a failed article retrieval.
5. Apply existing development relevance, parent IDN/facility, stage and metric extraction rules. Articles explicitly outside the configured discovery window (30 days by default) are excluded; unknown dates remain uncertain.
6. Generate a factual sales-facing recap from the saved article and structured facts. Article passages receive numeric IDs. GPT returns one to three sentences with a selected passage ID for each; the server attaches the original passage, avoiding quotation drift. Reject unknown passage IDs and numeric tokens absent from the associated evidence. This is not complete semantic fact checking.
7. Run existing structured-data validation and version/replay handling. New or changed records become pending. Same-snapshot replay preserves editorial corrections and approval.
8. Review, source-check and approve as before. The shared rules still generate follow-up actions, rank approved items, and build the same evidence-backed visuals and widgets.

The older tldraw board describes the underlying collection/review/ranking workflow. In GPT mode, web search replaces newsroom-index discovery, and generated summaries are added after rule-based normalization and before ingestion validation. No supplier-personalized recommendation model has been added.

## Configuration and privacy

The ignored `.env` is local only; `.env.example` contains empty, non-secret configuration for Git. The API key stays in the Python process and is sent only in the authorization header to the fixed OpenAI API endpoint. Redirects are not followed. Static serving uses a fixed file list, so `.env` is not a web route. Status APIs expose mode, readiness and model only. No browser-side API key form or secret logging is added.

Changing `.env` takes effect on the next refresh/import. Existing saved data continues to load even when the key is missing. Missing credentials, quota problems, failed searches, blocked source pages and rejected summaries remain explicit errors. No generated output automatically counts as a checked source.

## Bounds and provenance

One search request per selected IDN, at most two web-tool calls per search request, and three article candidates per IDN are the defaults. The article limit can be configured between one and five. Each accepted candidate may require one summary call. These are request/workload limits; actual API charges depend on model and tool use.

Summary caching includes source snapshot identity, structured facts, model and prompt version. It avoids repeated summary calls for unchanged input. Source changes or model/prompt changes can require new summaries. Refresh still performs new searches. Cached summaries do not erase later editor corrections.

Each generated record carries its summary model, prompt version, generation time, response reference and supporting passages. Search discovery references and local token-usage rows are saved for audit. Rules-only summaries remain distinguishable from GPT-assisted drafts. If an editor changes the recap, the original generation passages remain its draft provenance and version history records the edit.

## Verification

The automated suite uses simulated API responses and fixture articles. It exercises the real collection, snapshot, summary validation, cache, ingest, correction, approval and replay path without making billable calls. It also checks that a failed article fetch cannot be replaced by a search snippet. Live model availability, API billing, TLS/network access and real search quality still need a smoke test with the user's configured key.

Official API references: [web search](https://developers.openai.com/api/docs/guides/tools-web-search), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

## Live key verification · October 21, 2026

A bounded live OpenAI web search returned two eligible official article links and an official page was fetched successfully. A separate live summary check used the previously saved Piedmont Walton opening article. The generated summary passed passage-reference and numeric-support checks, then passed ingestion validation as a pending record in a temporary database. Production feed records and approval decisions were not changed by these checks. The check confirms this key's access to the configured model and search tool; individual future articles can still fail retrieval or summary validation and remain explicit errors.

## Freshness and repeat discovery

Discovery now defaults to a 30-day publication window and prioritizes the newest qualifying announcements. `IDN_AI_LOOKBACK_DAYS` accepts 7–180 days. The search request includes previously collected URLs, and known newsroom index pages are excluded. Previously missed facility-opening and hospital-approval headlines now match supported development rules. URL encoding differences, such as a dollar sign versus its percent-encoded spelling, no longer create duplicate source identities. Historical alias records remain in the audit store but collapse in the recommendation feed.

The recommendations page distinguishes publication order from priority order and supports date-window filters. Cards show article publication dates. Collection status distinguishes added, updated and unchanged records. A recent collection time does not make an old publication new. No records are automatically approved or rotated to create an appearance of freshness.
