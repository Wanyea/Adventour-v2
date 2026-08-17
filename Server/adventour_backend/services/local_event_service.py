import math
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse

from sqlalchemy import func

from adventour_backend.models import LocalEvent, LocalEventInterest, User


EVENT_CATEGORY_TAGS = {
    "market": {"market", "shopping", "local", "food_drink"},
    "makers": {"market", "art_gallery", "shopping_market", "local"},
    "popup": {"market", "restaurant", "food_drink", "local"},
    "food": {"restaurant", "food_drink", "market"},
    "music": {"concert_hall", "nightlife", "performing_arts_theater"},
    "concert": {"concert_hall", "nightlife", "performing_arts_theater"},
    "art": {"art_gallery", "arts_culture", "museum"},
    "gallery": {"art_gallery", "arts_culture", "museum"},
    "theater": {"performing_arts_theater", "arts_culture"},
    "comedy": {"comedy_club", "nightlife", "arts_culture"},
    "outdoor": {"park", "outdoors", "garden"},
    "community": {"local", "market", "arts_culture"},
}

SOURCE_BADGES = {
    "official": "Official source",
    "community": "Community post",
    "local_blog": "Local write-up",
    "event_platform": "Event platform",
    "external": "External source",
    "unsourced": "Needs source",
}

TRUSTED_SOURCE_KINDS = {"official", "community", "local_blog", "event_platform", "external"}

EXTERNAL_EVENT_SOURCE_TEMPLATES = [
    {
        "label": "Local calendars",
        "source_type": "local_search",
        "query": "{destination} local events markets pop-ups {date_text} {preference_text}",
        "description": "Search local calendars, neighborhood blogs, and event roundups for this destination.",
        "action": "Open first when Adventour has no saved events; it is the broadest local-discovery sweep.",
        "reservation_hint": "Look for RSVP, ticket, timed-entry, or free-entry details on the linked event page.",
        "priority": 1,
    },
    {
        "label": "Official city calendar",
        "source_type": "official_search",
        "query": "{destination} official events calendar {date_text}",
        "description": "Check city, parks, library, tourism-board, and public-market listings.",
        "action": "Use this to confirm dates and avoid relying on stale blog posts.",
        "reservation_hint": "Official pages usually link to permits, ticketing, venue pages, or registration forms.",
        "priority": 2,
    },
    {
        "label": "Markets and pop-ups",
        "source_type": "market_popup_search",
        "query": "{destination} makers market night market pop-up food art {date_text} {preference_text}",
        "description": "Scout temporary markets, maker fairs, food pop-ups, and local vendor events.",
        "action": "Use this for the hidden-gem/social-experience lane Adventour should not miss.",
        "reservation_hint": "Confirm address, hours, vendor list, and whether the event is ticketed.",
        "priority": 3,
    },
    {
        "label": "Event platforms",
        "source_type": "event_platform_search",
        "query": "{destination} Eventbrite Meetup Dice local events {date_text} {preference_text}",
        "description": "Search event platforms for ticketed shows, workshops, meetups, and hosted walks.",
        "action": "Use this when the route needs a bookable social anchor.",
        "reservation_hint": "Save the provider confirmation or ticket link back into Adventour after booking.",
        "priority": 4,
    },
    {
        "label": "Community meetups",
        "source_type": "community_search",
        "query": "{destination} community events meetup social walks workshops {date_text} {preference_text}",
        "description": "Find hosted walks, workshops, meetups, and social events.",
        "action": "Use this when friends want something more social than a normal place stop.",
        "reservation_hint": "Check host rules, attendee limits, safety details, and cancellation policy.",
        "priority": 5,
    },
]


def _haversine_meters(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _date_window_bounds(date_window, now):
    date_window = date_window or {}
    raw_start = date_window.get("start")
    raw_end = date_window.get("end")
    start = _parse_datetime(raw_start)
    end = _parse_datetime(raw_end)

    if start and raw_start and len(str(raw_start)) <= 10:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if end and raw_end and len(str(raw_end)) <= 10:
        end = end.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    if start and not end:
        end = start + timedelta(days=1)
    if end and not start:
        start = now
    if start and end and end <= start:
        end = start + timedelta(days=1)

    return start, end


class LocalEventRecommendationService:
    """Recommend local/community events near a destination."""

    def recommend_events(
        self,
        location,
        radius_meters=8000,
        destination_label=None,
        limit=6,
        date_window=None,
        preference_tags=None,
        viewer_user_id=None,
        friend_user_ids=None,
    ):
        now = datetime.utcnow()
        start, end = _date_window_bounds(date_window, now)
        windowed = bool(start and end)
        query_start = max(now, start) if start else now
        query_end = end if end else now + timedelta(days=21)

        events = LocalEvent.query.filter(
            LocalEvent.status == "active",
            LocalEvent.starts_at >= query_start,
            LocalEvent.starts_at < query_end,
        ).all()

        scoring_horizon_days = max(1, (query_end - query_start).total_seconds() / 86400)
        date_window_payload = (
            {
                "start": query_start.isoformat(),
                "end": query_end.isoformat(),
                "source": "travel_dates",
            }
            if windowed
            else {
                "start": query_start.isoformat(),
                "end": query_end.isoformat(),
                "source": "default_21_day_window",
            }
        )

        social_context = self._social_context([event.id for event in events], viewer_user_id, friend_user_ids or [])
        scored = []
        for event in events:
            distance_meters = _haversine_meters(
                location.get("latitude"),
                location.get("longitude"),
                event.latitude,
                event.longitude,
            )
            if distance_meters is not None and distance_meters > radius_meters:
                continue

            closeness = 0.5 if distance_meters is None else _clamp(1 - (distance_meters / radius_meters))
            days_until = max(0, (event.starts_at - query_start).total_seconds() / 86400) if event.starts_at else scoring_horizon_days
            time_fit = 1.0 if windowed else _clamp(1 - (days_until / scoring_horizon_days))
            authenticity = _clamp(event.authenticity_score or 0.75)
            preference_fit = self._preference_fit(event, preference_tags or [])
            source_metadata = self._source_metadata(event)
            source_quality = source_metadata["trust_score"]
            reservation_readiness = self._reservation_readiness(event)
            source_freshness = self._source_freshness(event, source_metadata)
            social_signal = social_context.get(event.id, {}).get("signal", 0.0)
            baseline_score = _clamp(
                authenticity * 0.28
                + closeness * 0.18
                + time_fit * 0.18
                + preference_fit * 0.22
                + source_quality * 0.04
                + reservation_readiness * 0.06
                + source_freshness * 0.02
                + social_signal * 0.04
            )
            event_anchor_score = self._event_anchor_score(
                authenticity=authenticity,
                closeness=closeness,
                time_fit=time_fit,
                preference_fit=preference_fit,
                source_quality=source_quality,
                reservation_readiness=reservation_readiness,
                source_freshness=source_freshness,
                social_signal=social_signal,
            )
            scored.append((
                event_anchor_score,
                baseline_score,
                distance_meters,
                closeness,
                time_fit,
                preference_fit,
                source_quality,
                reservation_readiness,
                source_freshness,
                social_signal,
                event,
            ))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        event_payloads = [
            self._event_payload(
                event,
                score,
                distance_meters,
                time_fit,
                windowed,
                preference_fit,
                closeness,
                source_quality,
                reservation_readiness,
                source_freshness,
                social_signal,
                social_context.get(event.id, {}),
                source_metadata=self._source_metadata(event),
                baseline_score=baseline_score,
            )
            for (
                score,
                baseline_score,
                distance_meters,
                closeness,
                time_fit,
                preference_fit,
                source_quality,
                reservation_readiness,
                source_freshness,
                social_signal,
                event,
            ) in scored[:limit]
        ]
        external_sources = self._external_sources(
            destination_label or self._event_source_destination(event_payloads),
            date_window_payload,
            preference_tags or [],
        )
        summary = self._with_external_source_summary(self._event_summary(event_payloads), external_sources)
        return {
            "status": "ready" if scored else "empty",
            "destination": destination_label,
            "message": (
                "Events matched to your travel dates."
                if windowed and scored
                else "No local events found during those travel dates yet."
                if windowed
                else "Events from the next few weeks near this launch point."
                if scored
                else "No local events found nearby yet."
            ),
            "date_window": date_window_payload,
            "summary": summary,
            "event_plan": self._event_plan(event_payloads, summary, external_sources, windowed),
            "events": event_payloads,
            "external_sources": external_sources,
        }

    def _event_payload(
        self,
        event,
        score,
        distance_meters,
        time_fit=1.0,
        matched_travel_dates=False,
        preference_fit=0.0,
        closeness=None,
        source_quality=None,
        reservation_readiness=None,
        source_freshness=None,
        social_signal=0.0,
        social_context=None,
        source_metadata=None,
        baseline_score=None,
    ):
        authenticity = _clamp(event.authenticity_score or 0.75)
        source_metadata = source_metadata or self._source_metadata(event)
        if closeness is None:
            closeness = 0.5 if distance_meters is None else _clamp(1 - (distance_meters / 8000))
        if source_quality is None:
            source_quality = source_metadata["trust_score"]
        if reservation_readiness is None:
            reservation_readiness = self._reservation_readiness(event)
        if source_freshness is None:
            source_freshness = self._source_freshness(event, source_metadata)
        social_context = social_context or {}
        social_signal = _clamp(social_signal or social_context.get("signal", 0.0))
        event_readiness = self._event_readiness(
            event=event,
            time_fit=time_fit,
            preference_fit=preference_fit,
            source_quality=source_quality,
            reservation_readiness=reservation_readiness,
            source_freshness=source_freshness,
            social_signal=social_signal,
            source_metadata=source_metadata,
        )
        return {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "city": event.city,
            "category": event.category,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "starts_at": event.starts_at.isoformat() if event.starts_at else None,
            "ends_at": event.ends_at.isoformat() if event.ends_at else None,
            "distance_meters": round(distance_meters) if distance_meters is not None else None,
            "score": round(score, 3),
            "time_fit": round(time_fit, 3),
            "preference_fit": round(preference_fit, 3),
            "fit_label": "During trip" if matched_travel_dates else "Upcoming nearby",
            "explanation": self._explanation(
                event,
                distance_meters,
                time_fit,
                authenticity,
                matched_travel_dates,
                preference_fit,
                source_quality,
                reservation_readiness,
                social_context,
            ),
            "event_story": self._event_story(
                event=event,
                score=score,
                distance_meters=distance_meters,
                time_fit=time_fit,
                matched_travel_dates=matched_travel_dates,
                preference_fit=preference_fit,
                authenticity=authenticity,
                source_quality=source_quality,
                reservation_readiness=reservation_readiness,
                source_freshness=source_freshness,
                social_context=social_context,
                source_metadata=source_metadata,
            ),
            "event_readiness": event_readiness,
            "score_components": {
                "authenticity": round(authenticity, 3),
                "closeness": round(closeness, 3),
                "time_fit": round(time_fit, 3),
                "preference_fit": round(preference_fit, 3),
                "source_quality": round(source_quality, 3),
                "reservation_readiness": round(reservation_readiness, 3),
                "source_freshness": round(source_freshness, 3),
                "social_signal": round(social_signal, 3),
                "event_anchor_score": round(score, 3),
                "baseline_score": round(baseline_score if baseline_score is not None else score, 3),
            },
            "social": {
                "interested_count": social_context.get("interested_count", 0),
                "going_count": social_context.get("going_count", 0),
                "friend_interested_count": social_context.get("friend_interested_count", 0),
                "friend_going_count": social_context.get("friend_going_count", 0),
                "friend_preview": social_context.get("friend_preview", []),
                "friend_candidates": social_context.get("friend_candidates", []),
                "social_next_action": social_context.get("social_next_action"),
                "viewer_status": social_context.get("viewer_status"),
            },
            "source_name": event.source_name,
            "source_url": event.source_url,
            "source": source_metadata,
            "reservation_url": event.reservation_url,
            "price_low": event.price_low,
            "price_high": event.price_high,
            "authenticity_score": event.authenticity_score,
        }

    def _event_anchor_score(
        self,
        authenticity,
        closeness,
        time_fit,
        preference_fit,
        source_quality,
        reservation_readiness,
        source_freshness,
        social_signal,
    ):
        """Rank events as actionable social anchors, not just nearby listings."""
        return _clamp(
            authenticity * 0.18
            + preference_fit * 0.18
            + source_quality * 0.15
            + reservation_readiness * 0.16
            + source_freshness * 0.08
            + social_signal * 0.18
            + time_fit * 0.08
            + closeness * 0.04
        )

    def _preference_fit(self, event, preference_tags):
        category_tags = self._event_tags(event)
        normalized_preferences = {
            str(tag).strip().lower()
            for tag in preference_tags
            if str(tag).strip()
        }
        if not category_tags or not normalized_preferences:
            return 0.45
        direct_matches = category_tags.intersection(normalized_preferences)
        if direct_matches:
            return min(1.0, 0.65 + 0.15 * len(direct_matches))
        if "local" in category_tags:
            return 0.55
        return 0.35

    def _event_tags(self, event):
        category = (event.category or "").strip().lower()
        tags = {category} if category else set()
        tags.update(EVENT_CATEGORY_TAGS.get(category, set()))
        for key, mapped_tags in EVENT_CATEGORY_TAGS.items():
            if key and key in category:
                tags.update(mapped_tags)
        return {tag for tag in tags if tag}

    def _source_metadata(self, event):
        source_name = (event.source_name or "").strip()
        source_url = (event.source_url or "").strip()
        reservation_url = (event.reservation_url or "").strip()
        domain = self._source_domain(source_url)
        normalized = f"{source_name} {domain}".lower()

        if not source_name and not source_url and not event.host_user_id:
            kind = "unsourced"
            trust_score = 0.25
        elif any(term in normalized for term in ("official", "city calendar", "public library", ".gov")):
            kind = "official"
            trust_score = 0.92
        elif any(term in normalized for term in ("eventbrite", "meetup", "dice.fm", "ticketmaster")):
            kind = "event_platform"
            trust_score = 0.76
        elif any(term in normalized for term in ("blog", "local", "magazine", "community calendar", "timeout", "eater")):
            kind = "local_blog"
            trust_score = 0.74
        elif event.host_user_id or "community" in normalized:
            kind = "community"
            trust_score = 0.68
        else:
            kind = "external"
            trust_score = 0.58

        if source_url:
            trust_score += 0.04
        if reservation_url:
            trust_score += 0.04

        return {
            "kind": kind,
            "badge": SOURCE_BADGES.get(kind, "External source"),
            "source_name": source_name or None,
            "domain": domain,
            "trust_score": round(_clamp(trust_score), 3),
            "has_source_url": bool(source_url),
            "has_reservation_url": bool(reservation_url),
        }

    def _source_domain(self, source_url):
        if not source_url:
            return None
        try:
            domain = urlparse(source_url).netloc.lower()
        except (TypeError, ValueError):
            return None
        return domain[4:] if domain.startswith("www.") else domain

    def _event_readiness(
        self,
        event,
        time_fit,
        preference_fit,
        source_quality,
        reservation_readiness,
        source_freshness,
        social_signal,
        source_metadata=None,
    ):
        source_metadata = source_metadata or self._source_metadata(event)
        checks = [
            self._event_readiness_check(
                "source",
                "Source can be trusted",
                self._readiness_status(source_quality, pass_min=0.7, warn_min=0.55),
                source_quality,
                "70%+ source trust",
                "Open a reliable source or add one before treating this as a route anchor.",
            ),
            self._event_readiness_check(
                "reservation",
                "Reservation or details are actionable",
                "pass" if reservation_readiness >= 0.9 else "warn" if event.source_url else "fail",
                reservation_readiness,
                "Reservation link, or at least a source page",
                "Find RSVP, ticket, timed-entry, or free-entry details.",
            ),
            self._event_readiness_check(
                "freshness",
                "Source details look current",
                self._readiness_status(source_freshness, pass_min=0.75, warn_min=0.5),
                source_freshness,
                "Official/platform/RSVP source, or a current community post",
                "Confirm blog or external-source details before treating this as current.",
            ),
            self._event_readiness_check(
                "social",
                "Social signal exists",
                "pass" if social_signal >= 0.2 else "warn" if social_signal >= 0.1 else "watch",
                social_signal,
                "Friend or community interest",
                "Mark Interested/Going or invite friends to make this social.",
            ),
            self._event_readiness_check(
                "timing",
                "Timing works for the trip",
                self._readiness_status(time_fit, pass_min=0.75, warn_min=0.45),
                time_fit,
                "75%+ timing fit",
                "Confirm this happens during the Adventour window.",
            ),
            self._event_readiness_check(
                "taste",
                "Matches the trip mood",
                self._readiness_status(preference_fit, pass_min=0.65, warn_min=0.45),
                preference_fit,
                "65%+ taste fit",
                "Use event tags or a different source if this feels off-theme.",
            ),
        ]
        check_statuses = {check["name"]: check["status"] for check in checks}
        actionability_score = _clamp(
            source_quality * 0.28
            + reservation_readiness * 0.26
            + source_freshness * 0.14
            + social_signal * 0.16
            + time_fit * 0.12
            + preference_fit * 0.04
        )

        if (
            check_statuses["source"] == "pass"
            and check_statuses["freshness"] == "pass"
            and check_statuses["timing"] != "fail"
            and (
                check_statuses["reservation"] == "pass"
                or check_statuses["social"] == "pass"
            )
        ):
            status = "ready"
            headline = "Ready to use as a local event anchor."
        elif check_statuses["source"] != "fail" and actionability_score >= 0.58:
            status = "needs_confirmation"
            headline = "Promising event lead; confirm details before relying on it."
        else:
            status = "research"
            headline = "Needs more source or reservation research."

        if check_statuses["social"] == "pass" and status != "research":
            headline = "Social event anchor with friend/community signal."
        elif check_statuses["reservation"] == "pass" and status == "ready":
            headline = "Bookable local event with enough confidence to save."

        return {
            "status": status,
            "headline": headline,
            "score": round(actionability_score, 3),
            "source_badge": source_metadata.get("badge"),
            "checks": checks,
            "next_action": self._event_next_action(status, check_statuses, event),
        }

    def _event_readiness_check(self, name, label, status, value, target, action):
        return {
            "name": name,
            "label": label,
            "status": status,
            "value": round(_clamp(value or 0), 3),
            "target": target,
            "action": action,
        }

    def _readiness_status(self, value, pass_min, warn_min):
        value = _clamp(value or 0)
        if value >= pass_min:
            return "pass"
        if value >= warn_min:
            return "warn"
        return "fail"

    def _event_next_action(self, status, check_statuses, event):
        if status == "ready":
            return "Save reservation details or mark Going when this belongs in the Adventour."
        if check_statuses.get("freshness") != "pass" and event.source_url:
            return "Open the source and confirm the date, location, host, and RSVP details are current."
        if check_statuses.get("reservation") != "pass" and event.source_url:
            return "Open the source and confirm RSVP, ticket, or free-entry details."
        if check_statuses.get("source") == "fail":
            return "Find a stronger official, community, or local source before relying on this."
        return "Use this as a lead, then confirm timing and source details."

    def _external_sources(self, destination_label, date_window_payload, preference_tags):
        destination = destination_label or "this destination"
        start = (date_window_payload or {}).get("start")
        end = (date_window_payload or {}).get("end")
        if start and end:
            date_text = f"{str(start)[:10]} to {str(end)[:10]}"
        else:
            date_text = "upcoming"
        preference_text = " ".join(str(tag).replace("_", " ") for tag in (preference_tags or [])[:4] if tag)
        sources = [
            {
                "label": "Community submissions",
                "description": "Adventour-hosted event posts with source and reservation links.",
                "url": None,
                "source_type": "adventour",
                "query": None,
                "action": "Add events here when a friend or local source finds something Adventour should remember.",
                "reservation_hint": "Community posts should include a source link and reservation link when available.",
                "priority": 0,
            },
        ]
        for template in EXTERNAL_EVENT_SOURCE_TEMPLATES:
            query = template["query"].format(
                destination=destination,
                date_text=date_text,
                preference_text=preference_text,
            ).strip()
            sources.append({
                "label": template["label"],
                "description": template["description"],
                "url": self._event_search_url(query),
                "source_type": template["source_type"],
                "query": query,
                "action": template["action"],
                "reservation_hint": template["reservation_hint"],
                "priority": template["priority"],
            })
        return sources

    def _event_search_url(self, query):
        return f"https://www.google.com/search?q={quote_plus(query)}"

    def _event_source_destination(self, event_payloads):
        for event in event_payloads or []:
            if event.get("city"):
                return event["city"]
        return None

    def _reservation_readiness(self, event):
        if event.reservation_url:
            return 1.0
        if event.source_url:
            return 0.55
        return 0.20

    def _source_freshness(self, event, source_metadata=None):
        source_metadata = source_metadata or self._source_metadata(event)
        kind = source_metadata.get("kind")
        if event.reservation_url:
            return 1.0
        if kind in {"official", "event_platform"} and event.source_url:
            return 0.88
        if kind == "community" and event.source_url:
            return 0.76
        if kind in {"local_blog", "external"} and event.source_url:
            return 0.58
        if event.host_user_id:
            return 0.62
        return 0.25

    def _social_context(self, event_ids, viewer_user_id=None, friend_user_ids=None):
        if not event_ids:
            return {}

        raw_friend_user_ids = friend_user_ids or []
        friend_user_ids = []
        seen_friend_ids = set()
        for user_id in raw_friend_user_ids:
            if not user_id:
                continue
            parsed_id = int(user_id)
            if parsed_id in seen_friend_ids:
                continue
            seen_friend_ids.add(parsed_id)
            friend_user_ids.append(parsed_id)

        friend_records = []
        if friend_user_ids:
            users_by_id = {
                user.id: user
                for user in User.query.filter(User.id.in_(friend_user_ids)).all()
            }
            for user_id in friend_user_ids:
                user = users_by_id.get(user_id)
                if not user:
                    continue
                friend_records.append({
                    "user_id": user.id,
                    "display_name": user.display_name or user.username or "Friend",
                    "profile_picture": user.profile_picture,
                    "status": None,
                })

        context = {
            event_id: {
                "interested_count": 0,
                "going_count": 0,
                "friend_interested_count": 0,
                "friend_going_count": 0,
                "friend_preview": [],
                "friend_candidates": [dict(friend) for friend in friend_records[:5]],
                "viewer_status": None,
                "signal": 0.0,
                "social_next_action": None,
            }
            for event_id in event_ids
        }
        count_rows = (
            LocalEventInterest.query
            .with_entities(
                LocalEventInterest.event_id,
                LocalEventInterest.status,
                func.count(LocalEventInterest.id),
            )
            .filter(LocalEventInterest.event_id.in_(event_ids))
            .group_by(LocalEventInterest.event_id, LocalEventInterest.status)
            .all()
        )
        for event_id, status, count in count_rows:
            if event_id not in context:
                continue
            if status == "going":
                context[event_id]["going_count"] = int(count)
            elif status == "interested":
                context[event_id]["interested_count"] = int(count)

        if viewer_user_id:
            viewer_rows = (
                LocalEventInterest.query
                .filter(
                    LocalEventInterest.event_id.in_(event_ids),
                    LocalEventInterest.user_id == viewer_user_id,
                )
                .all()
            )
            for row in viewer_rows:
                if row.event_id in context:
                    context[row.event_id]["viewer_status"] = row.status

        if friend_user_ids:
            friend_rows = (
                LocalEventInterest.query
                .join(User, User.id == LocalEventInterest.user_id)
                .filter(
                    LocalEventInterest.event_id.in_(event_ids),
                    LocalEventInterest.user_id.in_(friend_user_ids),
                )
                .all()
            )
            for row in friend_rows:
                if row.event_id not in context:
                    continue
                if row.status == "going":
                    context[row.event_id]["friend_going_count"] += 1
                elif row.status == "interested":
                    context[row.event_id]["friend_interested_count"] += 1
                if len(context[row.event_id]["friend_preview"]) < 3:
                    context[row.event_id]["friend_preview"].append({
                        "user_id": row.user_id,
                        "display_name": row.user.display_name or row.user.username or "Friend",
                        "profile_picture": row.user.profile_picture,
                        "status": row.status,
                    })
                for candidate in context[row.event_id]["friend_candidates"]:
                    if candidate["user_id"] == row.user_id:
                        candidate["status"] = row.status
                        break

        for event_id, row in context.items():
            row["signal"] = _clamp(
                row["going_count"] * 0.20
                + row["interested_count"] * 0.10
                + row["friend_going_count"] * 0.20
                + row["friend_interested_count"] * 0.12,
                maximum=1.0,
            )
            row["social_next_action"] = self._event_social_next_action(row)
        return context

    def _event_social_next_action(self, social_context):
        social_context = social_context or {}
        friend_preview = social_context.get("friend_preview") or []
        friend_candidates = social_context.get("friend_candidates") or []
        viewer_status = social_context.get("viewer_status")

        if friend_preview:
            names = ", ".join(friend.get("display_name") or "Friend" for friend in friend_preview[:2])
            return f"Coordinate with {names} before making this a meetup stop."

        unreacted = [
            friend
            for friend in friend_candidates
            if not friend.get("status")
        ]
        if unreacted:
            names = ", ".join(friend.get("display_name") or "Friend" for friend in unreacted[:2])
            return f"Ask {names} to mark Interested or Going if this should become a meetup anchor."

        if viewer_status:
            return "You started the signal; invite friends or save RSVP details next."

        return "Mark Interested or Going to start the social signal for this event."

    def _event_summary(self, events):
        if not events:
            return {
                "event_count": 0,
                "top_score": 0,
                "average_score": 0,
                "readiness_score": 0.55,
                "reservation_ready_count": 0,
                "sourced_count": 0,
                "interested_count": 0,
                "going_count": 0,
                "friend_interested_count": 0,
                "friend_going_count": 0,
                "ready_event_count": 0,
                "social_anchor_count": 0,
                "needs_confirmation_count": 0,
                "source_mix": {},
                "source_summary": {
                    "trusted_source_count": 0,
                    "unsourced_count": 0,
                    "reservation_ready_count": 0,
                    "source_mix": {},
                    "source_badges": [],
                    "message": "No local event sources found yet.",
                },
                "social_readiness": self._social_readiness_summary(
                    events=[],
                    friend_going_count=0,
                    friend_interested_count=0,
                    going_count=0,
                    interested_count=0,
                    reservation_ready_count=0,
                    social_anchor_count=0,
                ),
                "top_event_title": None,
            }

        reservation_ready_count = sum(1 for event in events if event.get("reservation_url"))
        sourced_count = sum(1 for event in events if event.get("source_url") or event.get("source_name"))
        interested_count = sum((event.get("social") or {}).get("interested_count", 0) for event in events)
        going_count = sum((event.get("social") or {}).get("going_count", 0) for event in events)
        friend_interested_count = sum((event.get("social") or {}).get("friend_interested_count", 0) for event in events)
        friend_going_count = sum((event.get("social") or {}).get("friend_going_count", 0) for event in events)
        ready_event_count = sum(1 for event in events if (event.get("event_readiness") or {}).get("status") == "ready")
        needs_confirmation_count = sum(1 for event in events if (event.get("event_readiness") or {}).get("status") == "needs_confirmation")
        social_anchor_count = sum(1 for event in events if (event.get("event_story") or {}).get("social_ready"))
        source_mix = {}
        for event in events:
            source_kind = ((event.get("source") or {}).get("kind")) or "unsourced"
            source_mix[source_kind] = source_mix.get(source_kind, 0) + 1
        source_summary = self._source_summary(source_mix, reservation_ready_count)
        top_event = events[0]
        top_components = top_event.get("score_components") or {}
        top_readiness = top_event.get("event_readiness") or {}
        top_baseline_score = top_components.get("baseline_score", top_event.get("score", 0)) or 0
        blended_readiness_score = _clamp(
            (top_readiness.get("score", top_event.get("score", 0)) or 0) * 0.55
            + (top_event.get("score", 0) or 0) * 0.25
            + (top_components.get("source_quality", 0) or 0) * 0.10
            + (top_components.get("reservation_readiness", 0) or 0) * 0.10
        )
        readiness_score = (
            max(blended_readiness_score, top_event.get("score", 0) or 0, top_baseline_score)
            if top_readiness.get("status") == "ready"
            else blended_readiness_score
        )

        return {
            "event_count": len(events),
            "top_score": round(top_event.get("score", 0) or 0, 3),
            "average_score": round(sum(event.get("score", 0) or 0 for event in events) / len(events), 3),
            "readiness_score": round(readiness_score, 3),
            "reservation_ready_count": reservation_ready_count,
            "sourced_count": sourced_count,
            "interested_count": interested_count,
            "going_count": going_count,
            "friend_interested_count": friend_interested_count,
            "friend_going_count": friend_going_count,
            "ready_event_count": ready_event_count,
            "social_anchor_count": social_anchor_count,
            "needs_confirmation_count": needs_confirmation_count,
            "source_mix": source_mix,
            "source_summary": source_summary,
            "social_readiness": self._social_readiness_summary(
                events=events,
                friend_going_count=friend_going_count,
                friend_interested_count=friend_interested_count,
                going_count=going_count,
                interested_count=interested_count,
                reservation_ready_count=reservation_ready_count,
                social_anchor_count=social_anchor_count,
            ),
            "top_event_title": top_event.get("title"),
        }

    def _social_readiness_summary(
        self,
        events,
        friend_going_count=0,
        friend_interested_count=0,
        going_count=0,
        interested_count=0,
        reservation_ready_count=0,
        social_anchor_count=0,
    ):
        events = events or []
        event_count = len(events)
        friend_signal_count = int(friend_going_count or 0) + int(friend_interested_count or 0)
        community_signal_count = int(going_count or 0) + int(interested_count or 0)
        top_social_event = next(
            (
                event
                for event in events
                if ((event.get("social") or {}).get("friend_going_count", 0)
                    + (event.get("social") or {}).get("friend_interested_count", 0)) > 0
            ),
            events[0] if events else None,
        )
        friend_score = _clamp(friend_going_count * 0.45 + friend_interested_count * 0.28)
        community_score = _clamp(going_count * 0.22 + interested_count * 0.12)
        anchor_share = social_anchor_count / max(1, event_count)
        reservation_share = reservation_ready_count / max(1, event_count)
        score = _clamp(
            friend_score * 0.44
            + community_score * 0.22
            + anchor_share * 0.20
            + reservation_share * 0.14
        )

        if event_count == 0:
            status = "needs_scouting"
            headline = "No social event anchor is available yet."
        elif friend_going_count:
            status = "ready"
            headline = f"{friend_going_count} friend{'s' if friend_going_count != 1 else ''} already going."
        elif friend_interested_count:
            status = "ready"
            headline = f"{friend_interested_count} friend{'s' if friend_interested_count != 1 else ''} interested in a local event."
        elif social_anchor_count or community_signal_count:
            status = "watch"
            headline = "Local event has community signal, but no selected friend signal yet."
        else:
            status = "needs_signal"
            headline = "Local events need friend or community signal before they feel social."

        if status == "ready":
            next_action = "Coordinate who wants to go and save RSVP or ticket details."
        elif status == "watch":
            next_action = "Mark Interested/Going or invite friends before treating this as a meetup anchor."
        elif event_count:
            next_action = "Use Interested/Going to start the social signal for this event."
        else:
            next_action = "Scout current local calendars or add an event your group wants to attend."

        meetup_checklist = self._meetup_checklist(
            status=status,
            event_count=event_count,
            friend_signal_count=friend_signal_count,
            community_signal_count=community_signal_count,
            reservation_ready_count=reservation_ready_count,
            social_anchor_count=social_anchor_count,
            top_social_event=top_social_event,
        )

        return {
            "status": status,
            "headline": headline,
            "score": round(score, 3),
            "event_count": event_count,
            "friend_signal_count": friend_signal_count,
            "community_signal_count": community_signal_count,
            "friend_going_count": int(friend_going_count or 0),
            "friend_interested_count": int(friend_interested_count or 0),
            "going_count": int(going_count or 0),
            "interested_count": int(interested_count or 0),
            "social_anchor_count": int(social_anchor_count or 0),
            "reservation_ready_count": int(reservation_ready_count or 0),
            "meetup_ready": status == "ready",
            "top_social_event": {
                "id": top_social_event.get("id"),
                "title": top_social_event.get("title"),
                "reservation_url": top_social_event.get("reservation_url"),
                "source_url": top_social_event.get("source_url"),
            } if top_social_event else None,
            "next_action": next_action,
            "meetup_checklist": meetup_checklist,
            "blocking_count": sum(1 for item in meetup_checklist if item.get("blocking")),
        }

    def _meetup_checklist(
        self,
        status,
        event_count,
        friend_signal_count,
        community_signal_count,
        reservation_ready_count,
        social_anchor_count,
        top_social_event,
    ):
        has_event = event_count > 0
        has_friend_signal = friend_signal_count > 0
        has_social_signal = has_friend_signal or community_signal_count > 0 or social_anchor_count > 0
        has_reservation = reservation_ready_count > 0
        source_ready = bool((top_social_event or {}).get("source_url"))

        return [
            {
                "id": "event_anchor",
                "label": "Pick an event anchor",
                "status": "ready" if has_event else "missing",
                "detail": (top_social_event or {}).get("title") if has_event else "No saved local event is ready yet.",
                "action": "Use this as the meetup anchor." if has_event else "Scout local calendars or add a community event.",
                "blocking": not has_event,
            },
            {
                "id": "source",
                "label": "Confirm source",
                "status": "ready" if source_ready else "research",
                "detail": "Source link available." if source_ready else "Source link still needs confirmation.",
                "action": "Open the source before relying on the event.",
                "blocking": has_event and not source_ready,
            },
            {
                "id": "social_signal",
                "label": "Get friend signal",
                "status": "ready" if has_friend_signal else "watch" if has_social_signal else "missing",
                "detail": (
                    f"{friend_signal_count} friend signal{'s' if friend_signal_count != 1 else ''}."
                    if has_friend_signal
                    else "Community signal exists, but no selected friend has reacted yet."
                    if has_social_signal
                    else "No one has marked Interested or Going yet."
                ),
                "action": "Coordinate who wants to go." if has_friend_signal else "Ask friends to mark Interested or Going.",
                "blocking": status != "ready" and not has_friend_signal,
            },
            {
                "id": "reservation",
                "label": "Save RSVP or ticket",
                "status": "ready" if has_reservation else "manual",
                "detail": (
                    f"{reservation_ready_count} event{'s' if reservation_ready_count != 1 else ''} have reservation links."
                    if has_reservation
                    else "RSVP or ticket link still needs checking."
                ),
                "action": "Save reservation details in Adventour." if has_reservation else "Open the source and confirm RSVP, ticket, or free-entry details.",
                "blocking": False,
            },
        ]

    def _with_external_source_summary(self, summary, external_sources):
        summary = dict(summary or {})
        source_summary = dict(summary.get("source_summary") or {})
        actionable_sources = [
            source
            for source in (external_sources or [])
            if source.get("url")
        ]
        source_summary["external_source_count"] = len(external_sources or [])
        source_summary["actionable_external_source_count"] = len(actionable_sources)
        source_summary["external_source_types"] = [
            source.get("source_type")
            for source in actionable_sources
            if source.get("source_type")
        ]
        recommended_source = self._recommended_external_source(summary, actionable_sources)
        if recommended_source:
            source_summary["recommended_external_source"] = recommended_source
            for source in external_sources or []:
                source["is_recommended"] = source.get("source_type") == recommended_source.get("source_type")
                if source["is_recommended"]:
                    source["recommended_reason"] = recommended_source.get("reason")
        source_summary["scouting_brief"] = self._scouting_brief(
            summary,
            recommended_source,
            actionable_sources,
        )
        if not summary.get("event_count") and actionable_sources:
            source_summary["message"] = (
                "No saved local events found yet, but Adventour has date-aware external sources to scout."
            )
        summary["source_summary"] = source_summary
        return summary

    def _scouting_brief(self, summary, recommended_source, actionable_sources):
        summary = summary or {}
        source_summary = summary.get("source_summary") or {}
        social_readiness = summary.get("social_readiness") or {}
        recommended_source = recommended_source or {}
        event_count = int(summary.get("event_count") or 0)
        reservation_ready_count = int(summary.get("reservation_ready_count") or 0)
        ready_event_count = int(summary.get("ready_event_count") or 0)
        needs_confirmation_count = int(summary.get("needs_confirmation_count") or 0)
        trusted_source_count = int(source_summary.get("trusted_source_count") or 0)
        unsourced_count = int(source_summary.get("unsourced_count") or 0)
        social_status = social_readiness.get("status")

        if not event_count:
            status = "needs_event_anchor"
            headline = "Scout a local event anchor."
            detail = "No saved local events matched this launch point or trip window yet."
            next_action = "Open the recommended search, then add the strongest market, pop-up, show, or community event back into Adventour."
            missing = [
                self._scouting_gap("event_anchor", "Saved local event", True, "Find one current event worth building around."),
                self._scouting_gap("source", "Source link", True, "Attach the event page, calendar, or local write-up."),
                self._scouting_gap("reservation", "RSVP details", False, "Add a ticket, RSVP, or free-entry note when available."),
            ]
        elif not reservation_ready_count:
            status = "needs_booking_link"
            headline = "Find RSVP or ticket details."
            detail = f"{event_count} event lead{'s' if event_count != 1 else ''} found, but none are bookable from Adventour yet."
            next_action = "Use the event-platform scout to find RSVP, ticket, timed-entry, or free-entry details."
            missing = [
                self._scouting_gap("reservation", "Reservation details", True, "Confirm how the group gets in."),
                self._scouting_gap("source", "Source quality", trusted_source_count <= 0, "Prefer official, platform, or local-community sources."),
                self._scouting_gap("social_signal", "Friend signal", social_status != "ready", "Ask friends to mark Interested or Going."),
            ]
        elif trusted_source_count <= 0 or unsourced_count >= event_count:
            status = "needs_trusted_source"
            headline = "Confirm the event source."
            detail = "Saved events need stronger official, community, or local-source proof before they should anchor a trip."
            next_action = "Open an official or local calendar source and update the event with the current host/date details."
            missing = [
                self._scouting_gap("source", "Trusted source", True, "Confirm the event with an official, platform, or local calendar link."),
                self._scouting_gap("freshness", "Current details", True, "Check date, location, host, and cancellation details."),
                self._scouting_gap("social_signal", "Friend signal", social_status != "ready", "Ask friends to mark Interested or Going."),
            ]
        elif social_status != "ready":
            status = "needs_social_anchor"
            headline = "Turn this event into a social anchor."
            detail = "Events are sourced, but selected friends have not signaled interest yet."
            next_action = "Share the event with friends and ask them to mark Interested or Going before relying on it socially."
            missing = [
                self._scouting_gap("social_signal", "Friend signal", True, "Get at least one selected friend to react."),
                self._scouting_gap("meetup_plan", "Meetup plan", False, "Confirm time, host rules, and where the group meets."),
                self._scouting_gap("reservation", "RSVP details", reservation_ready_count <= 0, "Save reservation or free-entry details."),
            ]
        elif needs_confirmation_count or ready_event_count <= 0:
            status = "confirm_details"
            headline = "Confirm timing before launch."
            detail = "A promising event is present, but at least one confidence check still needs a human pass."
            next_action = "Open the source and confirm date, location, host, and RSVP details before starting the Adventour."
            missing = [
                self._scouting_gap("freshness", "Current details", True, "Check the event page before launch."),
                self._scouting_gap("reservation", "Reservation saved", reservation_ready_count <= 0, "Save confirmation or free-entry details."),
            ]
        else:
            status = "ready"
            headline = "Local event scouting looks trip-ready."
            detail = "Adventour has a sourced, actionable event with enough social or booking confidence."
            next_action = "Save reservation details or keep this as the route's local social anchor."
            missing = []

        return {
            "status": status,
            "headline": headline,
            "detail": detail,
            "next_action": next_action,
            "goal": recommended_source.get("goal") or status,
            "recommended_source": {
                "label": recommended_source.get("label"),
                "source_type": recommended_source.get("source_type"),
                "url": recommended_source.get("url"),
                "query": recommended_source.get("query"),
                "reason": recommended_source.get("reason"),
            } if recommended_source else None,
            "missing": missing,
            "blocking_count": sum(1 for item in missing if item.get("blocking")),
            "actionable_source_count": len(actionable_sources or []),
        }

    def _scouting_gap(self, gap_id, label, blocking, action):
        return {
            "id": gap_id,
            "label": label,
            "blocking": bool(blocking),
            "action": action,
        }

    def _recommended_external_source(self, summary, actionable_sources):
        if not actionable_sources:
            return None

        event_count = int(summary.get("event_count") or 0)
        reservation_ready_count = int(summary.get("reservation_ready_count") or 0)
        source_summary = summary.get("source_summary") or {}
        trusted_source_count = int(source_summary.get("trusted_source_count") or 0)
        social_readiness = summary.get("social_readiness") or {}
        social_status = social_readiness.get("status")

        if not event_count:
            preferred_type = "market_popup_search"
            reason = "Best first scout because no saved local events matched this route yet."
            goal = "discover_hidden_local_events"
        elif not reservation_ready_count:
            preferred_type = "event_platform_search"
            reason = "Best next scout because the route needs RSVP, ticket, or booking links."
            goal = "find_bookable_event_anchor"
        elif trusted_source_count <= 0:
            preferred_type = "official_search"
            reason = "Best next scout because saved events need official or trusted confirmation."
            goal = "confirm_event_source_quality"
        elif social_status != "ready":
            preferred_type = "community_search"
            reason = "Best next scout because the route needs a better social meetup anchor."
            goal = "find_social_event_anchor"
        else:
            preferred_type = "local_search"
            reason = "Best broad scout to keep local event options fresh."
            goal = "refresh_local_event_options"

        preferred = next(
            (source for source in actionable_sources if source.get("source_type") == preferred_type),
            actionable_sources[0],
        )
        return {
            "label": preferred.get("label"),
            "source_type": preferred.get("source_type"),
            "url": preferred.get("url"),
            "query": preferred.get("query"),
            "reason": reason,
            "goal": goal,
        }

    def _source_summary(self, source_mix, reservation_ready_count):
        trusted_source_count = sum(
            count
            for kind, count in (source_mix or {}).items()
            if kind in TRUSTED_SOURCE_KINDS
        )
        unsourced_count = (source_mix or {}).get("unsourced", 0)
        source_badges = [
            {
                "kind": kind,
                "badge": SOURCE_BADGES.get(kind, kind.replace("_", " ").title()),
                "count": count,
            }
            for kind, count in sorted(
                (source_mix or {}).items(),
                key=lambda item: (item[0] == "unsourced", item[0]),
            )
        ]

        if trusted_source_count and reservation_ready_count:
            message = "Local event picks include trusted sources and reservation links."
        elif trusted_source_count:
            message = "Local event picks include trusted sources; some may still need reservation research."
        elif reservation_ready_count:
            message = "Some local event picks have reservation links, but source quality is still light."
        else:
            message = "Local event picks need stronger sources before they should feel trip-ready."

        return {
            "trusted_source_count": trusted_source_count,
            "unsourced_count": unsourced_count,
            "reservation_ready_count": reservation_ready_count,
            "source_mix": source_mix or {},
            "source_badges": source_badges,
            "message": message,
        }

    def _event_plan(self, events, summary, external_sources, windowed):
        summary = summary or {}
        source_summary = summary.get("source_summary") or {}
        trusted_source_count = source_summary.get("trusted_source_count", 0) or 0
        reservation_ready_count = summary.get("reservation_ready_count", 0) or 0
        external_sources = external_sources or []
        items = []

        if events:
            top_event = events[0]
            source = top_event.get("source") or {}
            social = top_event.get("social") or {}
            readiness = top_event.get("event_readiness") or {}
            readiness_status = readiness.get("status")
            items.append({
                "id": "top_event",
                "label": "Anchor event",
                "status": "ready" if readiness_status == "ready" else "research",
                "priority": 1,
                "detail": top_event.get("title"),
                "action": readiness.get("next_action") or (
                    "Reserve or save details for this event." if top_event.get("reservation_url") else "Open the source link and confirm timing before relying on it."
                ),
                "event_id": top_event.get("id"),
                "readiness_status": readiness_status,
                "readiness_score": readiness.get("score"),
                "source_badge": source.get("badge"),
                "source_url": top_event.get("source_url"),
                "reservation_url": top_event.get("reservation_url"),
            })
            if social.get("friend_going_count") or social.get("friend_interested_count"):
                items.append({
                    "id": "friend_signal",
                    "label": "Friend signal",
                    "status": "social",
                    "priority": 2,
                    "detail": self._social_plan_detail(social),
                    "action": "Coordinate who wants to go before locking the route.",
                })
            else:
                items.append({
                    "id": "friend_signal",
                    "label": "Friend signal",
                    "status": "optional",
                    "priority": 4,
                    "detail": "No selected friends have marked interest yet.",
                    "action": "Use Interested/Going to make this visible to friends.",
                })

        if trusted_source_count:
            items.append({
                "id": "source_quality",
                "label": "Source quality",
                "status": "ready",
                "priority": 3,
                "detail": f"{trusted_source_count} trusted source{'s' if trusted_source_count != 1 else ''} found.",
                "action": "Open the source before reserving so details are current.",
            })
        else:
            items.append({
                "id": "source_quality",
                "label": "Source quality",
                "status": "research",
                "priority": 2,
                "detail": "No trusted source is attached yet.",
                "action": "Use external sources to confirm current local events.",
            })

        if reservation_ready_count:
            items.append({
                "id": "reservation",
                "label": "Reservation",
                "status": "ready",
                "priority": 3,
                "detail": f"{reservation_ready_count} event{'s' if reservation_ready_count != 1 else ''} have reservation links.",
                "action": "Reserve timed-entry events and save confirmation details in Adventour.",
            })
        elif events:
            items.append({
                "id": "reservation",
                "label": "Reservation",
                "status": "manual",
                "priority": 3,
                "detail": "Events were found, but reservation links are missing.",
                "action": "Check the source page for RSVP, ticket, or free-entry details.",
            })

        if not events:
            source = next((item for item in external_sources if item.get("url")), None)
            recommended_source = (summary.get("source_summary") or {}).get("recommended_external_source") or {}
            items.append({
                "id": "external_scouting",
                "label": "External scouting",
                "status": "research",
                "priority": 1,
                "detail": "No matching local events are saved in Adventour yet.",
                "action": "Open local calendars and community listings for this destination.",
                "source_url": source.get("url") if source else None,
            })
            if recommended_source.get("url"):
                items.append({
                    "id": "recommended_external_source",
                    "label": "Best scout source",
                    "status": "research",
                    "priority": 1,
                    "detail": recommended_source.get("label"),
                    "action": recommended_source.get("reason") or "Open this source first for the strongest local event lead.",
                    "source_url": recommended_source.get("url"),
                    "source_type": recommended_source.get("source_type"),
                    "query": recommended_source.get("query"),
                })
            for source in external_sources[:4]:
                if not source.get("url"):
                    continue
                items.append({
                    "id": f"external_{source.get('source_type')}",
                    "label": source.get("label"),
                    "status": "research",
                    "priority": 2 + int(source.get("priority") or 0),
                    "detail": source.get("description"),
                    "action": source.get("action") or "Open this source and confirm current event details.",
                    "source_url": source.get("url"),
                })

        status = self._event_plan_status(items)
        return {
            "status": status,
            "headline": self._event_plan_headline(status, events, summary, windowed),
            "items": sorted(items, key=lambda item: (item.get("priority", 9), item.get("label", ""))),
        }

    def _social_plan_detail(self, social):
        friend_going = social.get("friend_going_count", 0)
        friend_interested = social.get("friend_interested_count", 0)
        parts = []
        if friend_going:
            parts.append(f"{friend_going} friend{'s' if friend_going != 1 else ''} going")
        if friend_interested:
            parts.append(f"{friend_interested} friend{'s' if friend_interested != 1 else ''} interested")
        return ", ".join(parts) if parts else "No friend signal yet."

    def _event_plan_status(self, items):
        statuses = {item.get("status") for item in items}
        if "ready" in statuses and "research" not in statuses:
            return "ready"
        if "ready" in statuses:
            return "needs_confirmation"
        return "needs_scouting"

    def _event_plan_headline(self, status, events, summary, windowed):
        if status == "ready":
            return "Local event plan is ready to save or reserve."
        if status == "needs_confirmation":
            return "Good local event leads found; confirm source or reservation details."
        if events:
            return "Events are nearby, but Adventour needs stronger source details."
        if windowed:
            return "No saved events match those travel dates yet; scout current local calendars."
        return "No saved local events nearby yet; use external sources to scout."

    def _event_story(
        self,
        event,
        score,
        distance_meters,
        time_fit,
        matched_travel_dates,
        preference_fit,
        authenticity,
        source_quality,
        reservation_readiness,
        source_freshness,
        social_context=None,
        source_metadata=None,
    ):
        social_context = social_context or {}
        source_metadata = source_metadata or {}
        friend_signal = (
            social_context.get("friend_going_count", 0)
            + social_context.get("friend_interested_count", 0)
        )
        community_signal = (
            social_context.get("going_count", 0)
            + social_context.get("interested_count", 0)
        )
        metrics = [
            {
                "id": "local_signal",
                "label": "Local",
                "value": round(authenticity, 3),
                "display": f"{round(authenticity * 100)}%",
            },
            {
                "id": "taste_fit",
                "label": "Taste",
                "value": round(preference_fit, 3),
                "display": f"{round(preference_fit * 100)}%",
            },
            {
                "id": "source",
                "label": "Source",
                "value": round(source_quality, 3),
                "display": source_metadata.get("badge") or f"{round(source_quality * 100)}%",
            },
        ]
        if friend_signal or community_signal:
            metrics.append({
                "id": "social",
                "label": "Social",
                "value": round((social_context.get("signal") or 0), 3),
                "display": (
                    f"{friend_signal} friend{'s' if friend_signal != 1 else ''}"
                    if friend_signal
                    else f"{community_signal} Adventourer{'s' if community_signal != 1 else ''}"
                ),
            })
        if source_freshness >= 0.75:
            metrics.append({
                "id": "freshness",
                "label": "Current",
                "value": round(source_freshness, 3),
                "display": "Confirmed",
            })
        if reservation_readiness >= 0.9:
            metrics.append({
                "id": "reservation",
                "label": "Reserve",
                "value": round(reservation_readiness, 3),
                "display": "Ready",
            })

        reasons = []
        cautions = []
        if matched_travel_dates:
            reasons.append("It lands inside your travel window.")
        elif time_fit >= 0.75:
            reasons.append("It is coming up soon enough to plan around.")
        if preference_fit >= 0.65:
            reasons.append("It overlaps with the taste signals in this Adventour.")
        elif preference_fit >= 0.5:
            reasons.append("It is a local wildcard that still fits the route.")
        if authenticity >= 0.85:
            reasons.append("It has a strong local/community signal.")
        if friend_signal:
            reasons.append("Selected friends already have social signal here.")
        elif community_signal:
            reasons.append("Other Adventourers have shown interest.")
        if reservation_readiness >= 0.9:
            reasons.append("There is a reservation or ticket link ready.")
        elif source_quality >= 0.7:
            reasons.append("A trusted source is attached for confirmation.")
        else:
            cautions.append("Confirm the source before making this a route anchor.")
        if source_freshness < 0.75:
            cautions.append("Confirm the event date and host details are still current.")
        if reservation_readiness < 0.5:
            cautions.append("Reservation details may require manual research.")

        if friend_signal:
            headline = f"Social anchor: {friend_signal} friend{'s' if friend_signal != 1 else ''} connected."
        elif reservation_readiness >= 0.9 and source_quality >= 0.7:
            headline = "Bookable local event with a trusted source."
        elif source_freshness < 0.75 and source_quality >= 0.7:
            headline = "Promising local event lead to confirm."
        elif authenticity >= 0.85:
            headline = "Local-feeling event worth building around."
        elif preference_fit >= 0.65:
            headline = "Event match for this Adventour's taste."
        else:
            headline = "Useful local event lead to scout."

        return {
            "headline": headline,
            "reasons": reasons[:4],
            "cautions": cautions[:2],
            "metrics": metrics[:5],
            "confidence": round(_clamp(score), 3),
            "source_badge": source_metadata.get("badge"),
            "reservation_ready": reservation_readiness >= 0.9,
            "social_ready": friend_signal > 0,
            "distance_label": self._distance_label(distance_meters),
        }

    def _distance_label(self, distance_meters):
        if distance_meters is None:
            return None
        if distance_meters < 1000:
            return f"{round(distance_meters)} m away"
        return f"{distance_meters / 1609.344:.1f} mi away"

    def _explanation(
        self,
        event,
        distance_meters,
        time_fit,
        authenticity,
        matched_travel_dates,
        preference_fit,
        source_quality=0.35,
        reservation_readiness=0.2,
        social_context=None,
    ):
        reasons = []
        if matched_travel_dates:
            reasons.append("Happens during your trip dates")
        elif time_fit >= 0.75:
            reasons.append("Coming up soon")
        if distance_meters is not None and distance_meters <= 1600:
            reasons.append("Close to your route")
        elif distance_meters is not None and distance_meters <= 5000:
            reasons.append("Nearby local option")
        if preference_fit >= 0.65:
            reasons.append("Matches your Adventour interests")
        elif preference_fit >= 0.5:
            reasons.append("Good local wildcard")
        if authenticity >= 0.85:
            reasons.append("Strong local signal")
        social_context = social_context or {}
        if social_context.get("friend_going_count", 0) > 0:
            reasons.append("A friend is going")
        elif social_context.get("friend_interested_count", 0) > 0:
            reasons.append("A friend is interested")
        elif social_context.get("going_count", 0) > 0:
            reasons.append("Adventourers are going")
        elif social_context.get("interested_count", 0) > 0:
            reasons.append("Adventourers are interested")
        if source_quality >= 0.75:
            reasons.append("Reliable source attached")
        if event.reservation_url:
            reasons.append("Reservation link ready")
        elif event.source_url:
            reasons.append("Source link available")
        return reasons[:5]
