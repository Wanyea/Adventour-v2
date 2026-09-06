"""Authenticity scoring, built only from signals that survived measurement.

Most of what the brief proposed did not survive. Measured on the Palm Coast
labels (gem vs generic/not_worth/junk, among places that pass the junk filter):

    Overture confidence          AUC 0.821   <- strongest, and not a closure artifact
    has socials                  AUC 0.647   weak
    H3 cell density              AUC 0.388   weak, and INVERTED from the assumption
    category rarity              AUC 0.565   no signal  (the brief's core idea)
    local name affinity          AUC 0.553   no signal
    chain_class                  AUC 0.523   no signal post-filter
    statewide name count         AUC 0.446   no signal

Two of those deserve comment.

**Category rarity failed outright.** The brief argued locally-rare categories are
more authentic -- the "Oaxacan mole specialist in Pittsburgh" intuition. In the
data, every one of the top gems is a plain `restaurant`, the single most common
category in the metro (232 of them). Rarity would have penalised all of them.

**Density is backwards.** The brief proposed penalising dense POI clusters as
tourist traps. Denser cells actually contain *more* gems -- because restaurants
cluster where the good areas are. The owner's own answer named European Village
and the Flagler Beach strip. Clustering is where locals go, not a warning sign.

Weights below are deliberately round. With n=46 there is nothing to fit, and
fitting them would only encode this sample's noise.
"""

import math

# Round numbers, not fitted. Confidence carries most of it because it is the only
# signal strong enough on this sample to justify weight.
W_CONFIDENCE = 0.65
W_SOCIALS = 0.15
W_DENSITY = 0.20

# Policy, not prediction. Post-filter, chain_class does not predict gems -- but the
# product exists to favour local places, and Gate 6 showed the classifier is
# accurate (10 of 12 human chain calls matched). This is a product rule applied on
# top of the learned score, and it is kept separate so it can be tuned or exposed
# as a user preference without disturbing the measured part.
CHAIN_MULTIPLIER = {"independent": 1.0, "regional": 1.0, "chain": 0.55}

# Cell density is log-scaled then squashed. Palm Coast cells top out around 40
# KEEP places; Orlando goes far higher, so the reference is generous.
DENSITY_REFERENCE = 40.0


# Serving-time floor, deliberately separate from the junk tiers. A place below
# this is not structurally junk -- it is a real record that the evidence does not
# support recommending. Kept apart from `tier` so that re-scoring never rewrites
# structural classification.
#
# Chosen at 0.30 because on the labelled sample any floor from 0.25 to 0.40 costs
# zero gems and zero solids, and 0.30 is the lowest that catches the case the
# owner raised (`DREAM BIG with Katia.`, a kids' art-lesson studio filed as
# art_gallery, scoring 0.272 — uncatchable by name or category). 0.50 was
# rejected: it starts costing real gems.
#
# Caveat: this removes ~118 places, of which only one is labelled. The rest are
# unverified, so the floor is evidence-backed at 0.30 and speculative above it.
AUTHENTICITY_FLOOR = 0.30


def density_component(cell_density):
    if not cell_density or cell_density <= 0:
        return 0.0
    return min(1.0, math.log1p(cell_density) / math.log1p(DENSITY_REFERENCE))


def authenticity_score(confidence, has_socials, cell_density, chain_class):
    """Return (score in 0..1, component breakdown).

    The breakdown is returned because the working agreement requires showing the
    score that produced a recommendation, not just the recommendation.
    """
    conf = float(confidence or 0.0)
    components = {
        "confidence": W_CONFIDENCE * conf,
        "socials": W_SOCIALS * (1.0 if has_socials else 0.0),
        "density": W_DENSITY * density_component(cell_density),
    }
    base = sum(components.values())
    multiplier = CHAIN_MULTIPLIER.get(chain_class, 1.0)
    components["chain_multiplier"] = multiplier
    return round(base * multiplier, 4), components


def explain(name, score, components, chain_class):
    """One human-readable line, for the deck preview and for debugging."""
    bits = []
    if components["confidence"] >= 0.55:
        bits.append("well-established")
    elif components["confidence"] <= 0.35:
        bits.append("thinly attested")
    if components["socials"] > 0:
        bits.append("active online")
    if components["density"] >= 0.15:
        bits.append("in a busy local area")
    if chain_class == "chain":
        bits.append("chain, downweighted")
    elif chain_class == "regional":
        bits.append("small local chain")
    return f"{score:.2f} — " + (", ".join(bits) if bits else "no strong signal")
