"""Tiered filter derived from the Palm Coast ground truth (Gate 6).

Four tiers, because the labels showed "show it / don't show it" is too coarse:

  KEEP      a real destination
  DROP      never show -- condos, churches, dojos, corporate shells, roads
  GATED     real, but only for someone who asked for it (golf, rinks, kids' classes)
  MOBILE    real and often good, but not a fixed place you can navigate to

The rules are tuned for ZERO false positives against the human labels. Dropping a
place the owner called a gem is far worse than leaving junk in -- junk gets swiped
away in a second, a missing gem is invisible.
"""

import re

# --- categories where every labeled instance was rejected -------------------
# `historic_site` is the big one: in Palm Coast, Overture uses it for condos,
# apartments, roads (Dixie Highway) and neighbourhoods (P Section). Removing it
# alone drops 195,622 records nationally.
DROP_CATEGORIES = {
    "historic_site",
    "religious_organization",
    "sport_or_recreation_club",
    "christian_place_of_worship", "place_of_worship", "jewish_place_of_worship",
    "muslim_place_of_worship", "buddhist_temple", "hindu_temple",
    "cemetery", "school", "high_school", "elementary_school", "middle_school",
    "gym", "fitness_studio", "sport_or_fitness_facility", "swimming_pool",
    "sport_field", "stadium_arena",
    # Tourist ticket booths and currency-exchange desks. Never a destination.
    "ticket_office_or_booth", "currency_exchange", "travel_agency",
}

# Real, but only if the user explicitly wants this kind of thing. The reviewer:
# "if someone had interest in golf I would, otherwise it's not a real destination."
# The outdoor rink they flagged lands here too -- a genuine facility, not junk.
GATED_CATEGORIES = {
    "golf_course", "country_club", "marina", "campground", "rv_park",
    "bowling_alley", "shooting_range", "equestrian_facility", "skate_park",
    "skating_rink", "ice_rink", "tennis_court", "batting_cage",
    "dance_school", "art_school", "music_school",
}

# Real but not navigable to a fixed address.
MOBILE_CATEGORIES = {"food_truck_stand", "caterer", "catering_service", "food_truck"}

# --- name patterns ----------------------------------------------------------
# Every pattern below is verified to fire on zero places the reviewer liked.
# Note what is deliberately ABSENT: a bare "Co." suffix would match
# "Vessel Sandwich Co." and "Coquina Coast Brewing Co.", both gems.
RESIDENTIAL = re.compile(
    r"\b(hoa|homeowners?|home owners?|condominium|condos?|condo assoc|townhomes?|"
    r"apartments?|property owners?|property manag|realty|real estate|"
    r"villas? at|residences?|mobile home|rv resort)\b", re.I)

RELIGIOUS = re.compile(
    r"\b(ministr(y|ies)|church|chapel|temple|synagogue|mosque|parish|"
    r"congregation|worship|diocese|missionary|vbs)\b", re.I)

MARTIAL_OR_INSTRUCTION = re.compile(
    r"\b(karate|jiu[\s-]?jitsu|jujitsu|taekwondo|tae kwon do|martial arts|"
    r"dojo|kickboxing|mma academy|self[\s-]?defense)\b", re.I)

CIVIC_OR_ORG = re.compile(
    r"\b(veterans?|american legion|rotary club|lions club|elks lodge|"
    r"chamber of commerce|city of|county of|school district|"
    r"high school|elementary|middle school)\b", re.I)

VICE_RETAIL = re.compile(
    r"\b(vapor|vape|smoke shop|smokeshop|tobacco|hookah|cbd store)\b", re.I)

# Institutional facilities: real places, but not open to the public. From the
# Orlando labels -- student dining, a sorority house, campus tennis courts, an
# observatory "not open to the public". Ten of 137 in a metro containing UCF.
#
# PREFIX ONLY, and that restriction is load-bearing. A naive \bucf\b matched
# `Gringos Locos UCF` -- a gem, where UCF is a location suffix on an independent
# restaurant. As an operator prefix it means the institution runs the place; as a
# suffix it just means "near campus".
INSTITUTIONAL_OPERATOR = re.compile(
    r"^\s*(ucf|university of|college of|univ\.? of)\b", re.I)

INSTITUTIONAL_FACILITY = re.compile(
    r"\b(sorority|fraternity|dining services|dining hall|student union|"
    r"residence hall|dormitory)\b", re.I)

# Tourist ticket resellers. The owner labelled one an outright trap -- the only
# trap label in either metro, and precisely what Adventour exists to avoid.
TICKET_RESELLER = re.compile(
    r"\b(discount .{0,20}tickets|ticket office|park tickets|currency exchange)\b", re.I)

# Instruction businesses: you enrol, you do not drop in. Distinct from the GATED
# tier, where a golf course or a rink can still be walked into on the day. These
# hide under many categories -- `dance_school` and `art_school` have zero records
# in the index, while lesson businesses sit under performing_arts_venue,
# sport_court, art_gallery and even restaurant.
INSTRUCTION = re.compile(
    r"\b(lessons?|classes|tutoring|daycare|day care|pre-?school|childcare|"
    r"child care|school of|swim school|driving school)\b", re.I)

# Corporate shells: an entity name, not a storefront. `inc` and `llc` only as a
# terminal token, so "Lincoln" and mid-name uses are untouched.
CORPORATE = re.compile(
    r"(\b(llc|l\.l\.c|inc|corp|corporation|holdings|enterprises|"
    r"group|partners|ventures)\.?\s*$)", re.I)

# Some names identify a destination so unambiguously that they override whatever
# category Overture assigned. This exists because `skate_park` turned out to hold
# 13 state parks against 4 real skate parks -- "state park" and "skate park"
# differ by one transposed character, and that corruption reached the taxonomy.
# Gating Washington Oaks Gardens State Park as a skate park is exactly the kind of
# error a category-only filter cannot see.
PROTECTED_DESTINATION = re.compile(
    r"\b(state park|national park|state forest|national forest|state preserve|"
    r"nature preserve|wildlife refuge|botanical garden|state recreation area|"
    r"national seashore|state beach|scenic trail)\b", re.I)

NAME_RULES = [
    ("residential", RESIDENTIAL),
    ("religious", RELIGIOUS),
    ("martial_arts", MARTIAL_OR_INSTRUCTION),
    ("civic_org", CIVIC_OR_ORG),
    ("vice_retail", VICE_RETAIL),
    ("institutional", INSTITUTIONAL_OPERATOR),
    ("institutional", INSTITUTIONAL_FACILITY),
    ("ticket_reseller", TICKET_RESELLER),
    ("instruction", INSTRUCTION),
    ("corporate_shell", CORPORATE),
]


def classify(name, basic_category):
    """Return (tier, reason). Tier is one of KEEP / DROP / GATED / MOBILE."""
    cat = (basic_category or "").strip().lower()
    name = name or ""

    # Runs first: a protected destination outranks a bad category assignment.
    if PROTECTED_DESTINATION.search(name):
        return "KEEP", "protected:public_land"

    if not cat:
        return "DROP", "no_category"
    if cat in DROP_CATEGORIES:
        return "DROP", f"category:{cat}"
    for label, rx in NAME_RULES:
        if rx.search(name):
            return "DROP", f"name:{label}"
    if cat in MOBILE_CATEGORIES:
        return "MOBILE", f"category:{cat}"
    if cat in GATED_CATEGORIES:
        return "GATED", f"category:{cat}"
    return "KEEP", "-"


# Real destinations that require a ticket or reservation before you can walk in.
# From the Orlando labels: Islands of Adventure, Universal Studios and Orlando
# Shakespeare Theater were all labelled *gems*. This is an attribute, not a tier
# -- it should change how a card is presented, not whether it is shown.
BOOKING_CATEGORIES = {
    "theme_park", "amusement_park", "water_park", "zoo", "aquarium",
    "performing_arts_venue", "theatre_venue", "concert_hall", "opera_house",
    "escape_room", "gaming_venue", "observatory", "science_attraction",
}

BOOKING_NAME = re.compile(
    r"(theater|theatre|escape room|ballet|opera|symphony|philharmonic)", re.I)


def needs_booking(name, basic_category):
    """True when a visitor should expect to buy a ticket or reserve ahead."""
    cat = (basic_category or "").strip().lower()
    if cat in BOOKING_CATEGORIES:
        return True
    return bool(BOOKING_NAME.search(name or ""))
