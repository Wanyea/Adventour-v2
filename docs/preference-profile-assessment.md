# Preference summaries — assessment, not an implementation decision

Owner raised a natural-language taste biography plus reusable prompt modules
while approving the next Phase 2 event discovery experiment. The idea is a
proposal to evaluate, not authorization to silently replace the recommender,
infer a real person's biography, build extra profile UI, or open another phase.

## Verdict

Keep the evidence-backed preference-summary idea as a candidate auxiliary
representation. Keep structured preferences and interaction history authoritative.
Test whether language adds value over the same facts represented as tags or
attributes. Do not give one LLM responsibility for discovery, verification and
final card construction.

[Language-Based User Profiles for Recommendation](https://arxiv.org/abs/2402.15623)
generated compact profiles from rating histories and evaluated them on MovieLens,
including cold-start comparisons. [Ramos et al., ACL 2024](https://aclanthology.org/2024.acl-long.753/)
evaluated natural-language profiles on rating benchmarks and user-editability.
These support feasibility, not effectiveness for short-lived local events, our
data, or any particular small local model.

Separating retrieval from scoring is a conventional recommender architecture;
[Google's overview](https://developers.google.com/machine-learning/recommendation/overview/types)
also distinguishes final reranking for diversity/freshness. Adventour's unusual
challenge is the combination of sparse taste evidence and incomplete, perishable
event inventory. Stronger ranking cannot recover an absent event.

## What the code currently does

- User.preferences is a 500-character string used for comma-separated onboarding
  tags. It is not a natural-language bio. Do not repurpose it for prose.
- personal_ranking_service.py reads the requesting user's last 90 days of
  impressions, accept/reject/arrival/rating history. Latest taste vote per entity
  is aggregated by tags, with a small-sample denominator adjustment.
- A saved-tag match contributes 0.5; feedback contributes up to +/-0.2 before
  shrinkage, distance up to 0.2, independent/regional policy 0.1, recent impression
  -0.1. Recent accepts/arrivals/ratings and rejects temporarily hide that place.
  These are declared policy weights, not learned or calibrated probabilities.
- Place tags come from category sets and limited name hints. Text nuance such as
  quiet workspace versus coffee-and-dancing is not represented well.
- local_event_service.py returns fresh regional events in time order; the
  current LocalEventsSection request sends coordinates and radius, not personal
  history. The six-hour worker refreshes only UCF and NYC Parks adapters.
- There is no taste-summary model, semantic user embedding, learned source
  preference or LLM card generator in this serving path. Current ranking does
  not establish dwell time with named friends. No such facts about Jackie exist
  merely because they appeared in the owner's hypothetical example.
- Neither ollama nor llama-server was found on PATH in this check. That alone
  does not prove no local model exists elsewhere. No model benchmark was run.

## Proposed representation

Store observations separately from interpretations. A preference assertion
should carry its supporting decision/review IDs, observation count, last update,
context, and whether it was explicitly stated or inferred. Evidence strength
should derive from observations, not an LLM's unsupported confidence number.

A synopsis is a bounded, versioned view of those assertions. It may say, in a
synthetic example: 'Often chooses small coffee tastings. Quiet-versus-lively
preference is unknown.' It must not invent friend relationships, dwell time,
income, demographic-based taste, or certainty about a new user.

Keep today's city, companions, available time and explicit request separate from
long-term taste. One rejection may mean wrong distance or timing. An acceptance
does not prove a satisfying visit. Explicit recent feedback should be able to
correct a prior inference. Preserve conflicting/context-dependent preferences.

Rebuild periodically from evidence, rather than repeatedly summarizing only the
previous summary; otherwise errors and lost exceptions can accumulate. Version,
invalidate and rebuild when evidence is corrected/deleted. Automatic updates
need not interrupt a user, but personalization should be understandable and
correctable, not deliberately concealed. No new controls are implemented here.

## Where language could help

1. Offline/asynchronous item enrichment: identify activity, setting, atmosphere,
   format, access and time from permitted evidence. Keep evidence references and
   unknown values. Do not infer authenticity from polished copy or obscurity.
2. User representation: compress established nuanced preferences, optionally
   producing an embedding for retrieval alongside ordinary tag retrieval.
3. Optional shortlist reranking: evaluate a fixed small set of owned candidate
   IDs against explicit context and supported preferences. Return IDs and
   evidence references; backend constructs cards from validated records.
4. Source prioritization: estimate verified unique yield, factual reliability,
   freshness, acquisition cost and observed satisfaction by region/interest.
   Keep these statistics separate from a prose bio. Sparse personal data should
   borrow cautiously from aggregate evidence and retain source diversity.

Crawl useful sources once for a region/interest cohort, not separately for every
person's prompt. Refresh the occurrence facts that expire, while retaining
permitted durable venue/organizer identities and Adventour's own observations.
Collection/storage rights and costs remain source-specific; a public webpage
or successful extraction is not automatically permission to build a database.

## Prompt composition and enforcement

The owner's MadLibs analogy is useful: stable instruction template, explicit
current constraints, versioned supported taste assertions, and a bounded
candidate-facts block. Call this prompt composition; external event text is data,
never an instruction module.

DB-first retrieval, allowed sources, budgets, date/location/access checks and
the no-paid-deck rule must be code-enforced. No instruction can authorize an
LLM to bypass those gates or fill an empty deck from memory. Paid LLM calls to
populate a deck would also conflict with the literal no-paid-API deck rule.

Use a constrained response structure such as candidate ID, component assessment,
supporting fact IDs and unknowns. Validate both shape and meaning: IDs belong to
the supplied candidates, evidence exists, dates/coordinates are valid, and facts
match the authoritative record. Valid JSON alone can still contain false facts.
Reapply eligibility before display and preserve the deterministic baseline on
model timeout or invalid output.

Fixed templates and low sampling variability improve control but do not
establish deterministic or correct rankings. Measure repeat runs, reordered
candidate inputs, latency and invalid/unsupported output rates. A local model
avoids per-call provider fees but still consumes hardware, time and maintenance.

## Fair bounded comparison for a later profile experiment

Do not combine new discovery coverage, extra user information and a new model
into one result. Freeze candidate facts and historical evidence before comparison:

- A: existing tags/history baseline.
- B: richer structured preference assertions and item attributes.
- C: exactly B's evidence, additionally expressed as a compact synopsis for a
  pinned local model or tested as an embedding.

B versus A measures added representation detail; C versus B tests whether the
language/model layer adds value. Give all arms the same constraints and candidates.
Evaluate independently supplied human preferences, unsupported assertions, valid
event selection, top-k relevance/diversity, latency and compute cost. Keep one
untouched sample and record model/prompt versions before running. Allow C to lose.

The current event-source experiment has assistant-coded relevance points and
a human-review sheet. It is not this three-arm model experiment. No user histories
were exported, biography persisted, weights tuned, or LLM serving path added.

