# Event discovery experiment v1 — agent-run portion complete

Owner approved the preceding comparison's next experiment. This run tests
September 26–27, 2026 in NYC with cafe interest, using unseen event dates rather
than tuning against the known September 20 home-cafe example.

**Outcome:** general queries produced two coffee-centered leads, one requiring a
21+ age check; explicit source queries produced **zero additional verified
target-weekend events** in this small budget. No source is ready for automatic
ingestion based on this study. Human relevance assessment remains pending.

## Frozen method and result

Protocol committed as d4cc4bf6 before discovery. Three general searches and three
source-restricted searches each retained the first two distinct URLs, in order.
All 12 selected URLs have dispositions in results.json. Three linked organizer
pages were inspected as allowed, for 15 distinct page URLs total. Same-page
excerpts were revisited; no extra search queries, sign-ins or paid calls.

The general arm yielded three verified distinct listings plus one conditional
listing. Two are coffee-centered. The source arm yielded none verified for the
weekend. This is yield within the selected slots, not recall: source queries
covered the month whereas general queries specified dates. Date specificity,
search-engine behavior, small sample size and duplicate aliases confound a
head-to-head source-quality conclusion.

| Lead | Frozen cafe rubric | Key observation |
| --- | --- | --- |
| [Regalia: Community Brewing](https://www.multimodalroasting.com/events/regalia-community-brewing-msmaz-ghcgb) | 60 = 50 activity + 10 participation | Sep26, 13:00–14:45, LIC roastery lab; hands-on brewing. Lab is not assumed to be a cafe. |
| [Brew & House](https://brewandhouse.avenueticket.com/event/nyc02) | 60 = 50 activity + 10 participation | Sep27, 11:00–14:00, Manhattan rooftop; specialty coffee and dancing. 21+ check needed; printed EST label conflicts with NYC's seasonal offset. |
| [Yes Chef Food Fest](https://yescheffoodfest.com/) | 10 participation | Sep26–27, 11:00–19:00, Queens; broad food festival, no established cafe setting/coffee focus. |
| [Peoples' Voice Cafe](https://www.judson.org/calendar/peoples-voice-cafe-9-26-26) | 0 established cafe-rubric evidence | Sep26, 20:00–22:00, NYC community performance hall. Coffeehouse name alone is insufficient. Zero is not a quality verdict. |

One weekend food-festival listing covers two occurrences but counts as one unique
event concept in the table. The two Brew & House URLs are one event. NYC for FREE
www/non-www aliases redirect to one calendar; cached versions differed. They
consume selected slots but never inflate event yield.

## What failed and what was learned

- Partiful searches returned wrong-day events, not a usable target-weekend set.
  This disproves success of these particular queries, not Partiful's usefulness.
- Luma surfaced a relevant cafe organizer calendar. Visible dates were absent;
  following its coffee-meetup link established September 6, outside the target.
  Exact address was registration-gated; no registration or bypass was attempted.
- NYC for FREE's returned calendar exposed no Sep26–27 occurrence; rendering and
  publication limits mean we cannot conclude the publisher has no events then.
- The cabaret calendar returned July on open after September search snippets.
  Search snippets must not establish event freshness.
- Linked venue/organizer evidence helped verify Regalia without an owned POI
  match. No structured extraction automation was deployed or success-rate claimed.
  The known Partiful example remains the separate positive JSON-LD diagnostic.
- Activity, setting and format matter independently. The workshop and dance party
  tie at 60 even though a person could prefer one strongly. This motivates a
  richer user representation, but does not prove an LLM would improve ranking.

These are assistant-coded diagnostic labels; neither the scores nor the source
selection have been validated by independent human judgments. No authenticity
or local-community-quality claim is made from marketing prose.

## Human review, with scores hidden

[review.md](review.md) contains the four candidate summaries in non-score order.
Give fit 0 (not for me), 1 (maybe), 2 (would consider), or unknown, and a short
reason. Judge the activity independently of whether that weekend fits your
personal calendar. Separately flag unclear access or factual errors.
This measures a named reviewer's preferences, not population quality.

## Source and preference follow-through

Keep website/organizer collection within Phase 2. A subsequent predeclared
catalog traversal should resolve public occurrence dates and canonical links,
measure new eligible event yield and use an established collection/storage basis
before production. Source-restricted web search alone did not pass this check.
Do not add an adapter that merely repeats these searches every six hours.

The owner's natural-language preference idea was evaluated separately in
[preference-profile-assessment.md](../../../preference-profile-assessment.md).
No taste bio was created for Jackie or any account. No local model was installed,
and no LLM-ranking or personalization lift experiment was claimed.

Verification: protocol LF SHA256
59303d2ede519383a07b9e6708093297b44e75d7fd75e5de0f8042c83606457b
matches its pre-retrieval commit; 12/12 selected URL dispositions accounted for;
score arithmetic checked; supplied friend URL absent from selected results.
No application, DB, source roster or UI changes.

