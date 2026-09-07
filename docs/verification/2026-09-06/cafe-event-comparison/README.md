# NYC cafe event comparison — September 20, 2026

**Result: The Last Bite Turns 1! Home Cafe was missed.** The owner supplied
[its Partiful link](https://partiful.com/e/g82v9vaY5E2YPxRq2OYT) after fixed-query retrieval.
It is absent by URL and title from the 24-URL selected pool. Its later 100/100
experimental relevance score is a user-supplied diagnostic, never an organic find.
No application code, source roster, event DB, user history or screen was changed.

## Three arms

| Arm | Observed result |
| --- | --- |
| Live DB | 302 NYC Parks records; none overlap September 20. Production sorts chronologically and has no personalized event fit score. |
| Existing NYC source with date override | 30 September 20 rows: 17 pass existing normalization, 1 cancelled/closed, 3 ambiguous locations, 9 restricted programs. Experimental scores 0–10; no established cafe or coffee activity. |
| Frozen public-web pass | Six queries, first five distinct URLs each, 24 pooled URLs. Five ranked listing entries across four publisher pages; unverified and unreviewed leads remain unranked. Friend event absent. |

The same six-hour refresh still only revisits configured sources. Moving the
date window forward cannot make a home-bakery event appear in a Parks-only source.

## Ranked reviewed web sample

| Listing | Coffee / cafe / participation | Score | Provenance |
| --- | --- | --- | --- |
| [Storytelling Art Fair](https://www.sequoiacafenyc.com/events) | 0 / 40 / 10 | 50 | Previously seen, resurfaced |
| [Final Shop Day](https://www.sequoiacafenyc.com/events) | 0 / 40 / 0 | 40 | Previously seen, resurfaced |
| [Traveler's Company popup](https://www.yosekaland.com/upcoming-events) | 0 / 0 / 10 | 10 | Fixed search |
| [Street Works Earth](https://www.climateweeknyc.org/event-search/past-events/2026-street-works-earth) | 0 / 0 / 10 | 10 | Fixed search |
| [Urban Bear street fair](https://www.theurbanbear.com/) | 0 / 0 / 10 | 10 | Previously seen, resurfaced |

Final Shop Day is a special closing announcement, with uncertain event-like
activity, at the same time/place as the fair. These are not two independent
recommendations. The source itself, not Google, establishes the cafe location
and coffee service. Low-scoring controls are not asserted to be good cafe picks.

An apparently strong matcha-journaling lead was excluded when its linked
[organizer page](https://luma.com/56mb9i0y?ref=somo) established Philadelphia.
Coffee fellowship, bingo and a NYC for FREE matcha popup could not be verified
through successful page retrieval. An MBA coffee-chat aggregator lacks an
accessible organizer link and remains unverified. Recruitment over coffee also
illustrates an intent mismatch the three-component rubric handles poorly.

## Separate user-supplied diagnosis

The public Partiful event's structured metadata gives September 20, noon–3 p.m.
America/New_York and an NYC location. Its description establishes a temporary
home cafe, coffee/chai service, tasting samples and an open-invite anniversary
gathering. RSVP is requested; optional baked-goods purchases are offered.
No RSVP was submitted or capacity independently verified.

Unchanged v0 rules give **50 + 40 + 10 = 100**. The original rule explicitly
allowed temporary cafe settings before this link was supplied. This is a coarse,
hand-specified relevance score, not 100% likelihood of enjoyment, a trained model,
or demonstrated recommendation quality.

The web reader failed on this URL; ordinary unauthenticated HTTP returned 200
with Event JSON-LD and public metadata. Therefore this example demonstrates
extractability *once supplied*. It does not establish public search indexing,
availability of a Partiful discovery feed, crawling rights, or platform-wide
coverage. The event mentioned an organizer Instagram account; following that
account now would be a user-seeded experiment, not retrospective discovery.

## Gaps and next bounded Phase 2 experiment — proposed, not implemented

1. **Discovery coverage:** evaluate permitted public event catalogs and links
   from local newsletters, cafe/bakery websites and organizer posts to Partiful
   and similar event pages. Explicitly measure links found without event names.
   Broad date-plus-keyword web searches alone missed this example.
2. **Event extraction and representation:** read public Event structured dates
   in local time; distinguish the event, organizer and temporary venue. Allow a
   verified temporary venue without requiring an existing indexed cafe.
   Keep date, city, access and freshness eligibility ahead of relevance.
3. **Relevance labels:** retain separate activity, setting and format evidence:
   cafe drinks, desserts/baking, tasting, home cafe/pop-up and social gathering.
   An incidental coffee mention at a recruitment session must not become a
   coffee-centered activity. A single category is insufficient for these overlaps.
4. **Validation:** this supplied example becomes a known regression case.
   Measure discovery separately from extraction and ranking on another frozen
   unseen sample; ask for human cafe-fit judgments. Do not tune only to this host,
   bake the supplied URL into retrieval, or count rediscovering it as held-out success.

This is within existing Phase 2 event coverage/relevance work, not an extra
product feature or phase. No source is promoted into production by this report.

## Audit and replay

- Protocol committed as **7b42d3ec** before retrieval; LF-normalized SHA256
  **c6ce681b418d10ceca06f18cfd64d3ace1fae8718725e3b46a97430aab390f6a**.
  Windows checkout uses CRLF; replay normalizes line endings only.
- `search-manifest.json` preserves selected per-query URLs and ordering. First
  three queries were initially batched and repeated unchanged individually when
  batch attribution was merged; merged results were not added.
- Eleven unique matching event/venue pages attempted, including two linked
  verification pages; repeat opens did not add candidates. The separate
  owner-supplied diagnostic is outside the discovery arm.
- Cafe-looking leads were prioritized for review, followed by two non-cafe
  controls. That review ordering was not preregistered. Unreviewed pool entries
  are neither scored nor treated as irrelevant.
- Queries/weights were frozen before reveal; manual evidence coding finished
  after reveal. Prior Sequoia/other exposure is marked. This is not a fully blind
  automated-classification benchmark.
- `baseline.json` records read-only DB/source observations. Parks scores use
  conservative manual title/venue/category evidence; unknown earns zero, not a
  factual assertion that coffee or participation is absent.
- `labels.json` contains diagnostic facts/URLs and evidence decisions, not
  copied event descriptions, personal contact/guest data, home addresses or images.
- From repo root: `Server\.venv\Scripts\python.exe docs/verification/2026-09-06/cafe-event-comparison/score.py`.
  This checks the frozen protocol hash and reproduces `scores.json`.
- Verification: replay passed; protocol content equals its pre-retrieval commit
  after line-ending normalization. No app tests or screen changes were needed.

