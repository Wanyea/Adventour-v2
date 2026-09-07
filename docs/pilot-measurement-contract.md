# Phase 2 pilot measurement contract — v1, September 7, 2026

Status: owner approved the small feedback controls on September 7, explicitly
restricted to the pilot version. Not yet implemented telemetry or an iOS release.
Fits existing discovery, interaction logging, ratings and data tooling (features
4, 7, 16, 19, 21–23). No additional product phase or social feature. This narrow
pilot-only UI approval satisfies the AGENTS.md freeze for the controls below.

## Pilot-only boundary — owner approved

Pilot feedback panels, voluntary Feedback entries, instrumented invitations,
sampling counters, study outbox and additional study snapshots exist only in the
pilot experience. The standard build must neither show them nor collect/send
these additional study records. Existing core interaction logging, ratings and
reviews continue normally in both builds. No public settings switch enables the
study; do not infer pilot participation just from TestFlight installation.

Use an explicit build configuration (existing react-native-config integration)
that defaults to standard when absent or invalid. Pilot enablement also requires
an active, server-recognized study enrollment for the authenticated account and
the pilot request context. An enrolled friend using the standard build must not
trigger extra study capture. A client-supplied pilot flag is not authorization.
Server-created request/decision study context, rather than arbitrary feedback
metadata, binds uploads to the correct study. Background workers must not
misclassify normal traffic as study data.

Allow delivery of already captured, valid pilot feedback after reconnect only
under the same participant/study policy; revocation or withdrawal stops new
capture and is honored during upload. Standard builds do not flush a leftover
pilot outbox. Do not copy study enrollment or counters into ordinary preferences.

Keep one app source tree, backend and recommendation algorithm. This explicit
owner-requested build distinction gates study instrumentation, not competing
recommendation implementations. Real pilot feedback may inform separately
reviewed future improvements; no pilot-only ranking branch or silent population
training is authorized. UI additions must remain in small cohesive modules.

Before distribution, demonstrate both configurations: pilot controls plus joined
study records, and standard UI with zero study requests/records, including for
an enrolled account. Missing build settings, non-enrolled accounts and background
refresh must fail closed for study capture. Standard release verification checks
the effective native configuration, not just a JavaScript environment file.
Exact native build/signing wiring and these checks are still implementation work.

## Decisions this pilot must support

| Question | Evidence needed | Do not substitute |
|---|---|---|
| Did we acquire useful local inventory? | Requested region/window; acquisition outcome; eligible counts; source coverage and independently supplied misses | Empty results as proof there is nothing nearby |
| Does the recommendation match the stated interest? | Explicit relevance answer tied to the exact request/card | A cafe keyword, a high score, or general appeal |
| Would this person enjoy it? | Explicit appeal answer; separate post-visit rating | Acceptance, directions or dwell time as satisfaction |
| Why did they pass? | Optional taste/context/factual reason | Every rejection as a lasting dislike |
| Is it usable and accurately described? | Time/location/access/link evidence and user-reported problems | Public webpage as admission, or fresh fetch as current occurrence |
| Which ranking/source changes deserve another test? | Versioned inputs, exact exposure, labeled outcomes, untouched evaluation sample | Before/after averages across different people, cities or inventories |
| Is using the pilot comfortable? | Prompt delivery/skip/completion, answer time, end-of-period burden feedback | More mandatory responses as better research |

The owner's E1–E4 reviews and supplied Last Bite link are development evidence.
They motivate separating these questions, not universal taste assumptions.

## Tester experience: short, optional, attached to the actual card

Intro copy: “Help us find places worth your time. We record the recommendations
you see, your choices and occasional optional feedback. Honest dislikes help too.”
Explain selected launch location use and pilot retention before collecting study
data. No hidden biography, contacts collection or background location tracking.

Keep onboarding interests and normal swiping. Testers do not enter scores, sources,
coordinates, device details or visit diaries. There are no minimum daily tasks,
streaks, prizes for positive answers, push reminders or required written reviews.

Proposed small feedback panel inside existing Discover/details, preserving the
card title and image/category context. Never overlay directions or force an answer
before the next swipe. A sampled decision stays attached to its original card
even if the deck changes. No new navigation entry, palette or UI dependency.

The panel asks ONE question at a time, assigning appeal/relevance in randomized
two-question blocks per participant, independently of score, source and swipe sign.
For relevance, an explicit current filter or saved interest must exist. If several
apply, store and display the selected interest, chosen uniformly from that set.
If no interest exists, sample appeal only and record that eligibility difference.

| ID / construct | Exact wording | Stored values and visible labels |
|---|---|---|
| `appeal_v1` | “How appealing is **[name]** to you?” | 0 Not at all; 1 Slightly; 2 Moderately; 3 Very; 4 Extremely; null Can't tell |
| `relevance_v1` | “How well does **[name]** match your interest in **[interest]**?” | 0 Not at all; 1 Slightly; 2 Moderately; 3 Very well; 4 Extremely well; null Can't tell |
| `reason_v1` (optional after a pass or low answer) | “What was the main reason?” | `taste` Not my kind of activity; `setting` Wrong atmosphere or format; `distance` Too far; `timing` Wrong time; `price_booking` Cost or booking; `familiar` Already know it; `unclear` Not enough information; `facts` Something looks wrong; `other` Something else |

Always include Skip, with no answer preselected. Reason selection is single-choice
to keep it quick; optional note up to 280 characters supports nuance. For a factual
problem, optional subtype: location, date/time, closed/cancelled, sold out/access,
broken link, wrong category/description, other. Reports are observations pending
verification, not automatic global fact overrides. Existing closed-report behavior
must stay distinct and visibly confirmed.

One optional free-text note can capture “prefer markets over a formal class”;
the reason taxonomy does not pretend to encode all individual taste. Never require
an explanation of a low rating. A neutral “Thanks, saved” acknowledges any answer.

Sampling v1: after a qualifying exposure, independently sample with probability
0.25, then offer at the next natural pause. At most two automatic prompts per
session, three per tester-local day, and ten minutes between offers. A session
ends after 30 minutes of inactivity. Never prompt merely on a background refresh.
Explicit Skip is final for that invitation. Caps/assignment persist across restarts.
These are proposed burden limits, not proven optimal constants; freeze them before
the measured wave. No repeated prompting to turn missing answers into responses.

An unobtrusive voluntary “Feedback” entry on an existing card/detail allows a
tester to report an unsampled success/problem. Voluntary and sampled responses
remain separate in reports. No extra automatic post-visit prompt: use existing
1–5 trip-stop ratings and optional notes, tied to a confirmed/manual arrival.
Label 1 Very poor, 2 Poor, 3 Okay, 4 Good, 5 Excellent; preserve historical raw
ratings under their old instrument version rather than relabeling them retroactively.
Directions or GPS proximity do not prove attendance or enjoyment.

## Automatic data contract

All records carry `schema_version`, `pilot_id`, pseudonymous `participant_id`,
server UTC timestamp, app build and backend release. Identity mapping stays separate
from exported analysis. Synthetic/dev activity remains excluded from human results;
real friends are a pilot cohort, not fake/dev users.

| Record and keys | Required fields and meaning |
|---|---|
| Request: `request_id`, `session_id` | Selected launch coordinates, GPS/manual origin, location accuracy if supplied, radius, requested date window plus IANA timezone, explicit filters, saved interests snapshot, context origin (`explicit`/`default`), received/completed time, status/error, acquisition job ID, cold/warm coverage state |
| Retrieval snapshot: `request_id`, `snapshot_id` | Owned index/source versions, immutable scoring configuration and input history/assertions as of the decision, candidate entity/occurrence IDs, scores/features and ordered exclusion stages/counts, deterministic tie rule, final ranked IDs, retrieval/ranking/acquisition durations and provider-call counts |
| Served decision: `decision_id`, `request_id` | `item_kind=place/event`, canonical place ID or source/series/occurrence identity, rank/surface, exact allowed card payload and score components, tags and their rule/evidence origin, model version (or chronological ordering), item/source revision, freshness/access/availability/location evidence and explicit unknowns |
| Exposure: `exposure_id`, `decision_id` | Actual visible card revision, foreground/focus and visibility-rule version, start/end/duration, first qualifying impression, position, explanation opened, offline/retry state |
| Action: `action_id`, `decision_id` | Accept/reject/open source/navigate/manual arrival/rate and result; client time plus server receipt, sequence, idempotency key; optional existing stop/trip ID. Link intent, successful handoff and actual visit are different events |
| Invitation: `invitation_id`, `decision_id` | Question/instrument version, target interest, sampling probability/assignment, eligibility, cap state, offered/skipped/answered/abandoned, presentation time, source `sampled`/`voluntary` |
| Feedback: `feedback_id`, `invitation_id`, `decision_id` | Construct, ordinal response or explicit unknown, optional reason/subtype/note, observed-before-visit versus after-visit, response duration, revision/superseded ID; capture original answer and corrections |
| Source/acquisition run: `run_id` | Region/window, source ID and adapter version, permission reference, attempt/success times, bytes/requests/duration, raw count, parsed/dedup/eligible counts and exclusions, error/backoff, published-at/verified-at/expiry where applicable |

An event organizer recheck may change its facts: create a new display revision and
link actions to the revision actually used. Do not replace the original served
facts with today's DB row. Preserve event trace even after live occurrence expiry,
only for fields whose retention permits this; otherwise mark expired evidence
unavailable and exclude full-replay claims. Never save Google display content into
telemetry, screenshots or payloads to bypass the data boundary.

Full candidate snapshots may reference immutable permitted dataset partitions
instead of copying them for every request; a mutable table or hash alone is not
enough to replay a ranking. Log pre-filter candidate membership and ordered
exclusions so a missing item can be distinguished from an acquired-but-filtered one.
No need to snapshot the whole world. Store only the bounded requested area/pool.

The 0–4 answers are ordinal categories, not calibrated probabilities. Unknown,
skipped, not asked, abandoned, upload pending and rejected-invalid are distinct.
Never impute any as zero. No conversion of historical owner 0–2 labels or visit
1–5 ratings to this scale without an explicit separately reported mapping.

Exposure v1: foreground, focused screen, at least 50% of the card visible for
one continuous second; a direct card action records an interaction exposure even
if faster. A fetched/prefetched/offscreen event is not an impression. Deduplicate
study impression denominators per participant/decision, retaining raw revisits.
This is Adventour's declared operational definition, not an industry certification.

Validate enums, bounds, foreign keys, user ownership and versions at the server.
Retry acknowledged writes idempotently, including after app restart; log receipt
separately from device occurrence and flag clock skew. Only show “saved” after
acknowledgment; pending uploads remain identifiable. Corrections append revisions.

Raw selected launch coordinates are restricted to operational replay; propose
30-day pilot retention, then purge them and location-bearing raw exports unless
the tester explicitly agrees to further collection. Retain coarse regional counts
and anonymous aggregates. User-authored notes and linked responses support deletion
and export. This is a proposed study policy, not a legal-compliance assertion.
Retention cleanup must preserve aggregate denominators and flag non-replayable rows.

## Current code versus required changes

- Place `recommendation_decision` preserves individual returned payload/rank and
  model; it lacks a complete request/candidate/history/version snapshot.
- `place_event_service` already checks decision ownership and deduplicates action
  types. It does not implement this invitation/feedback protocol or offline queue.
- Current deck impressions are focus/foreground aware; verify viewport, duration,
  revisions and delivery against the above contract before counting exposures.
  Its current 700ms polling checks half-card visibility at an instant; that is not
  proof of one continuous second. Version this change instead of blending measures.
- Event listing is chronological within the region/window and has no per-user
  decision trace. Record that baseline honestly; do not invent a personal fit.
- Current `personal_v1` assigns negative category feedback to every reject. Before
  friends testing, version a correction: logistical/factual reasons must not train
  negative taste; unknown-reason rejects can hide that item but do not establish a
  category dislike. Explicit taste evidence stays separate from contextual evidence.
  Do not reinterpret historical ambiguous rejects as known taste judgments.
- New questionnaire responses initially feed study analysis only. Do not silently
  change live weights or generate preference biographies from them during the wave.
  Any later richer-attributes/summary comparison uses versioned supported evidence
  and the fair A/B/C protocol in preference-profile-assessment.md.

## Analysis and a finite review point

Two willing testers first exercise the tasks while explaining how they understand
the questions. Do not coach positive answers. Verify it is easy to skip, that
“matches cafes” differs from “I like this,” and that optional feedback typically
takes under ten seconds. Revise wording before freezing v1 if it fails. These
two people's observations are development data, not held-out validation.

Then run one seven-day exploratory friends wave; invitation starts only after the
technical gates below pass. Report at day seven even if participation is sparse.
Do not demand quotas from friends or silently extend the study until scores look
good. Coverage target for useful diagnosis: five distinct people, 30 answered
sampled card questions and three unseeded locations; these are planning targets,
not power calculations or statistical proof. Below target means insufficient
evidence with a stated next decision, not a fabricated pass.

Freeze question/sampling/ranking/config versions before the wave. Existing personal
history may evolve under the declared policy; snapshot it. No concurrent weight
tuning on the evaluation sample. Assign development/evaluation participants before
answers arrive when cohort size permits; keep all of one person's records together.
If too few independent participants/regions remain, report descriptive results
only. More swipes by one friend do not create more independent people.

Report numerator/denominator, number of people, locations, missingness, model and
date range for each metric, separately for places/events and cold/warm regions:

- Coverage: requests with any eligible result / valid completed requests; empty
  reasons; acquisition failure and completion time; no distant-region fallback.
- Relevance: count of 3/4 answers / answered known sampled relevance questions,
  alongside the entire 0–4 distribution and unknown rate. Appeal is a separate
  identical calculation. Report per-person results and their unweighted average;
  volunteered labels are separately tabulated, not mixed into the sample.
- Usability: independent confirmed factual/access failures / inspected unique
  items, plus unresolved user reports. Broken links and sold-out pages count as
  operational problems, not negative cafe preferences.
- Behavior: accepts / distinct exposed decisions; arrivals / accepts; 4/5 visit
  ratings / rated visits. Show unrated/unconfirmed visits; never claim causal
  improvement or satisfaction from conversion alone.
- Burden and instrumentation: answered / offered prompts, skips/abandonment,
  median and p90 response time, per-person prompts/day, pending/rejected uploads,
  joins complete / acknowledged feedback, replay matches / sampled requests.

End-of-wave check-in (once, optional, outside app): “How did the amount of feedback
we asked for feel?” Too little / About right / Too much; optional “What got in your
way?” Keep wording/instrument version in the report. No unsolicited messages sent.

Do not assert city-wide event recall: there is no complete regional ground truth.
An event supplied after retrieval is a diagnosed miss, never an organic find.
Track acquisition, eligibility and ranking misses separately. Source yield reports
unique verified eligible occurrences per run plus factual accuracy and cost;
raw text matches do not make a source useful for a particular person's taste.

This convenience sample can identify failures and promising changes. It cannot
alone establish population fit or resolve the harness's missing holdout. Do not
invent a statistical-significance threshold or treat the suggested sample size
as adequate power. Approve a separate frozen comparison before claiming a winner.

## Go/no-go and review checkpoints

1. **Before friends:** implement the approved pilot-only controls and place/event
   trace plus export before changing acquisition/ranking. Show the exact phone
   card, response, persisted joined row and score calculation to the owner.
2. **Technical rehearsal:** all acknowledged feedback joins to the correct original
   decision/version; retry/restart produces no duplicate outcome; no offscreen
   impressions; skip/unknown stay distinct; no cross-user joins or provider-content
   retention. Replay the same ranking from immutable inputs. Any violation blocks
   invitation until corrected, regardless of subjective fit scores.
3. **Coverage/device rehearsal:** show an unseeded GPS region acquired on the PC,
   correct local deck, honest event gaps, working source links and expired/sold-out
   exclusion. Verify PC outage/cold acquisition states and feedback delivery after
   reconnect. Then repeat on an off-network iPhone with real auth and TestFlight.
4. **Day-seven review:** a small per-person/region report, concrete good/bad cards,
   evidence-linked diagnoses and exactly one recommended next slice. Owner decides
   Phase 2 acceptance against existing exit criteria; no automatic graduation.

Existing Phase 2 source-quality, hours/access and Phase 1 acceptance gaps remain.
No UI change or collection pipeline is claimed built by this design document.

## Method references

[Pew questionnaire design](https://www.pewresearch.org/writing-survey-questions/)
supports neutral, specific questions, careful response options and pretesting.
[Pew on open-response burden](https://www.pewresearch.org/decoded/2021/10/14/why-do-some-open-ended-survey-questions-result-in-higher-item-nonresponse-rates-than-others/)
supports keeping written responses optional rather than the main instrument.
[Wang et al., Denoising Implicit Feedback for Recommendation](https://arxiv.org/abs/2006.04153)
examines noisy implicit interactions; Adventour therefore measures explicit appeal
and outcomes separately from swipes. These inform our design; no standardized
validated Adventour questionnaire or generalization guarantee is claimed.
