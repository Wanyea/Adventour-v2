import math
from datetime import datetime
from urllib.parse import quote_plus


CITY_TRANSPORT_GUIDANCE = [
    {
        "matches": ("new york", "nyc", "brooklyn", "manhattan", "queens", "bronx"),
        "provider": "MTA / OMNY",
        "source_url": "https://www.mta.info/fares-tolls/subway-bus/tap-and-ride",
        "transit_setup": "Use OMNY tap-and-ride for subway and local bus. Tap the same card or phone each time for transfers and fare capping.",
        "walk_setup": "Use walking plus MTA subway/bus as the backup. Keep the same OMNY card or wallet device for every tap.",
        "rideshare_setup": "Use rideshare for late-night hops or neighborhoods that are awkward by subway, but keep OMNY ready for most route legs.",
        "rental_setup": "Skip rental cars for most NYC routes unless the Adventour leaves the city; parking will usually add stress.",
        "setup_steps": [
            "Choose one contactless card, phone wallet, or OMNY card before the first ride.",
            "Use the same payment method for transfers and fare capping.",
            "Check MTA service status before the first long hop.",
        ],
    },
    {
        "matches": ("san francisco", "sf", "bay area", "oakland", "berkeley"),
        "provider": "Clipper",
        "source_url": "https://www.clippercard.com/",
        "transit_setup": "Set up Clipper in your phone wallet or bring a Clipper card for Muni, BART, Caltrain, ferries, and other Bay Area transit.",
        "walk_setup": "Use walking for clustered stops and keep Clipper ready for hills, BART, Muni, ferries, or longer cross-city hops.",
        "rideshare_setup": "Use rideshare for steep or late legs, but Clipper is the cleanest setup for most Bay Area transit.",
        "rental_setup": "Avoid rental cars inside San Francisco unless the route leaves the city; parking can dominate the day.",
        "setup_steps": [
            "Add Clipper to Apple Wallet or Google Wallet, or bring a physical card.",
            "Load enough value for Muni/BART legs before leaving.",
            "Check whether any ferry or regional rail leg needs extra timing buffer.",
        ],
    },
    {
        "matches": ("austin",),
        "provider": "CapMetro",
        "source_url": "https://www.capmetro.org/",
        "transit_setup": "Set up CapMetro tickets or passes for bus, Rapid, and rail legs. Keep rideshare as a backup for late-night or spread-out stops.",
        "walk_setup": "Use walking for compact neighborhoods and keep CapMetro or rideshare ready for heat, hills, or longer jumps.",
        "rideshare_setup": "Use rideshare for late-night returns or low-frequency transit legs; CapMetro can still cover downtown and major corridors.",
        "rental_setup": "Consider a rental only when the route leaves central Austin or spans several far-apart neighborhoods.",
        "setup_steps": [
            "Check CapMetro route timing before committing to a transit-heavy day.",
            "Save a rideshare backup for late-night legs.",
            "If using rail, confirm the service window for the trip date.",
        ],
    },
    {
        "matches": ("orlando",),
        "provider": "LYNX / SunRail",
        "source_url": "https://www.golynx.com/",
        "transit_setup": "Prepare LYNX fare payment for bus legs and check SunRail only if the route lines up with its corridor and service hours.",
        "walk_setup": "Use walking only for tightly clustered stops; Orlando routes often need rideshare, rental, or LYNX between areas.",
        "rideshare_setup": "Use rideshare for theme-park, nightlife, and cross-neighborhood hops where transit timing is thin.",
        "rental_setup": "A rental car may be the simplest setup for spread-out Orlando routes; save parking notes with the route.",
        "setup_steps": [
            "Check whether LYNX or SunRail actually serves the stop cluster.",
            "Use rideshare or rental for spread-out attractions and late returns.",
            "Save parking or pickup notes before starting the route.",
        ],
    },
]


class TravelLogisticsService:
    """Build provider-neutral booking guidance for planned Adventours.

    The first beta version should not invent flight or lodging quotes. This
    service returns explicit connection/status metadata so the app can show
    useful planning steps now and later plug in booking providers cleanly.
    """

    def build_booking_plan(
        self,
        route_days,
        party_size=1,
        destination_label=None,
        origin_label=None,
        travel_dates=None,
        trip_style=None,
        lodging_type=None,
        stay_neighborhood=None,
        preferred_local_transport=None,
    ):
        days = max(1, len(route_days))
        nights = self._lodging_nights(days, travel_dates or {})
        stop_count = sum(len(day.get("stops", [])) for day in route_days)
        estimated_segments = max(0, stop_count - days)
        destination = destination_label or "your destination"
        lodging_type = (lodging_type or "").strip() or None
        stay_neighborhood = (stay_neighborhood or "").strip() or None
        preferred_local_transport = self._normalize_transport_preference(preferred_local_transport)
        route_distance_meters = self._route_distance_meters(route_days)
        style = trip_style or ("day" if days == 1 else "vacation")
        duration_alignment = self._duration_alignment(style, days, nights, travel_dates or {})
        local_transport = self._local_transport(
            days=days,
            stop_count=stop_count,
            estimated_segments=estimated_segments,
            destination=destination,
            route_distance_meters=route_distance_meters,
            party_size=max(1, int(party_size or 1)),
            preferred_local_transport=preferred_local_transport,
        )
        dates_ready = bool((travel_dates or {}).get("start") and (travel_dates or {}).get("end"))
        flight_ready = bool(origin_label and destination_label and dates_ready)
        stay_ready = bool(destination_label and dates_ready)
        components = [
            {
                "id": "flight",
                "type": "flight",
                "label": "Flights",
                "status": self._flight_status(days, nights, flight_ready),
                "estimate": None,
                "action": self._flight_action(days, nights, origin_label),
                "required_inputs": ["origin", "destination", "dates", "traveler_count"],
                "missing_inputs": self._component_missing_inputs(
                    ["origin", "destination", "dates", "traveler_count"],
                    {
                        "origin": origin_label,
                        "destination": destination_label,
                        "dates": dates_ready,
                        "traveler_count": party_size,
                    },
                ),
                "next_steps": self._flight_next_steps(days, nights, origin_label, destination_label, travel_dates or {}, party_size),
                "provider_options": self._flight_provider_options(days, nights, origin_label, destination_label, travel_dates or {}, party_size),
                "search_hint": self._search_hint("flight", origin_label, destination_label, travel_dates or {}, party_size),
                "stores_reservation": True,
            },
            {
                "id": "stay",
                "type": "stay",
                "label": "Stay",
                "status": self._stay_status(nights, stay_ready),
                "nights": nights,
                "estimate": None,
                "action": self._stay_action(nights),
                "required_inputs": ["dates", "party_size", "lodging_type", "neighborhood"],
                "missing_inputs": self._component_missing_inputs(
                    ["dates", "party_size", "lodging_type", "neighborhood"],
                    {
                        "dates": dates_ready,
                        "party_size": party_size,
                        "lodging_type": lodging_type if nights > 0 else "not_needed",
                        "neighborhood": stay_neighborhood if nights > 0 else "not_needed",
                    },
                ),
                "lodging_type": lodging_type,
                "stay_neighborhood": stay_neighborhood,
                "next_steps": self._stay_next_steps(nights, destination_label, travel_dates or {}, party_size, lodging_type, stay_neighborhood),
                "provider_options": self._stay_provider_options(nights, destination_label, travel_dates or {}, party_size, lodging_type, stay_neighborhood),
                "search_hint": self._search_hint("stay", origin_label, destination_label, travel_dates or {}, party_size, nights, lodging_type, stay_neighborhood),
                "stores_reservation": True,
            },
            local_transport,
            {
                "id": "tickets",
                "type": "event_or_place",
                "label": "Tickets and reservations",
                "status": "manual_or_link_out",
                "estimate": None,
                "action": "Use place and event links, then save confirmation numbers in Adventour.",
                "next_steps": [
                    "Open source or reservation links for timed-entry stops and local events.",
                    "Save each confirmation number in Adventour before starting the route.",
                    "Add notes for arrival windows, cancellation rules, and who booked it.",
                ],
                "provider_options": [
                    {
                        "label": "Use attached place/event links",
                        "url": None,
                        "note": "Adventour keeps provider links with the stop or event so booking details can be saved after checkout.",
                    },
                ],
                "stores_reservation": True,
            },
        ]
        missing_inputs = self._missing_inputs(days, nights, origin_label, destination_label, travel_dates or {})
        reservation_storage = {
            "status": "ready",
            "endpoint": "/api/reservations",
            "supported_types": ["flight", "stay", "local_transport", "event", "place"],
            "message": "Adventour can store provider names, confirmation numbers, dates, links, notes, and total cost.",
        }
        booking_action_links = self._booking_action_links(components)
        next_best_actions = self._next_best_actions(components, missing_inputs)
        prep_checklist = self._prep_checklist(components, missing_inputs, duration_alignment)
        summary = self._booking_summary(components, missing_inputs, reservation_storage, duration_alignment)
        planning_burden = self._planning_burden(components, missing_inputs, prep_checklist, summary)
        booking_timeline = self._booking_timeline(
            prep_checklist=prep_checklist,
            booking_action_links=booking_action_links,
            planning_burden=planning_burden,
            missing_inputs=missing_inputs,
        )
        booking_handoff = self._booking_handoff(
            components=components,
            booking_action_links=booking_action_links,
            booking_timeline=booking_timeline,
            missing_inputs=missing_inputs,
            summary=summary,
        )
        booking_checklist = self._booking_checklist(
            components=components,
            missing_inputs=missing_inputs,
            booking_action_links=booking_action_links,
            reservation_storage=reservation_storage,
            booking_timeline=booking_timeline,
            booking_handoff=booking_handoff,
            prep_checklist=prep_checklist,
            summary=summary,
        )

        return {
            "status": "provider_ready_contract",
            "destination": destination_label,
            "origin": origin_label,
            "party_size": max(1, int(party_size or 1)),
            "trip_style": style,
            "lodging_type": lodging_type,
            "stay_neighborhood": stay_neighborhood,
            "preferred_local_transport": preferred_local_transport,
            "days": days,
            "nights": nights,
            "travel_dates": travel_dates or {},
            "duration_alignment": duration_alignment,
            "components": components,
            "booking_action_links": booking_action_links,
            "reservation_storage": reservation_storage,
            "missing_inputs": missing_inputs,
            "next_best_actions": next_best_actions,
            "prep_checklist": prep_checklist,
            "summary": summary,
            "planning_burden": planning_burden,
            "booking_timeline": booking_timeline,
            "booking_handoff": booking_handoff,
            "booking_checklist": booking_checklist,
            "assumptions": [
                "Flight and stay prices are not estimated until live providers or manual reservations are connected.",
                "Local travel is a planning range based on route length, not a fare quote.",
                "Reservation storage is Adventour-owned and can preserve confirmation details without storing restricted provider place data.",
            ],
        }

    def _flight_status(self, days, nights, flight_ready):
        if days == 1 and nights == 0:
            return "optional_for_day_trip"
        return "ready_for_provider" if flight_ready else "needs_provider"

    def _stay_status(self, nights, stay_ready):
        if nights == 0:
            return "not_needed_for_day_trip"
        return "ready_for_provider" if stay_ready else "needs_provider"

    def _lodging_nights(self, days, travel_dates):
        start = self._parse_date((travel_dates or {}).get("start"))
        end = self._parse_date((travel_dates or {}).get("end"))
        if start and end and end > start:
            return max(0, (end.date() - start.date()).days)
        return max(0, days - 1)

    def _parse_date(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            return None

    def _duration_alignment(self, style, days, nights, travel_dates):
        normalized_style = str(style or "").strip().lower() or ("day" if days == 1 else "vacation")
        start = self._parse_date((travel_dates or {}).get("start"))
        end = self._parse_date((travel_dates or {}).get("end"))
        has_date_range = bool(start and end)
        headline = "Trip duration matches the route."
        message = "The selected trip style, itinerary days, and travel dates agree."
        next_action = None
        status = "aligned"
        severity = "pass"

        if has_date_range and end < start:
            status = "needs_attention"
            severity = "fail"
            headline = "Travel dates are out of order."
            message = "The end date comes before the start date, so Adventour cannot trust the booking packet."
            next_action = "Fix the travel date range before booking."
        elif normalized_style == "day" and nights > 0:
            status = "watch"
            severity = "warn"
            headline = "Day trip has overnight dates."
            message = "This route has one itinerary day, but the selected dates add an overnight stay."
            next_action = "Switch to Weekend/Vacation or shorten the date range before booking."
        elif normalized_style == "weekend" and days > 3:
            status = "watch"
            severity = "warn"
            headline = "Weekend trip has vacation-length route days."
            message = "This is marked as a weekend, but the itinerary spans more than three days."
            next_action = "Switch to Vacation or reduce the route length."
        elif normalized_style == "weekend" and has_date_range and nights > 3:
            status = "watch"
            severity = "warn"
            headline = "Weekend dates look longer than expected."
            message = "This is marked as a weekend, but the travel dates include more than three nights."
            next_action = "Switch to Vacation or tighten the travel dates."
        elif normalized_style == "vacation" and days < 3 and nights < 2:
            status = "watch"
            severity = "warn"
            headline = "Vacation plan looks short."
            message = "This is marked as a vacation, but it currently behaves more like a day or weekend route."
            next_action = "Add more route days or switch the trip style."

        return {
            "status": status,
            "severity": severity,
            "headline": headline,
            "message": message,
            "next_action": next_action,
            "trip_style": normalized_style,
            "route_days": days,
            "calendar_nights": nights,
            "has_date_range": has_date_range,
        }

    def _missing_inputs(self, days, nights, origin_label, destination_label, travel_dates):
        missing = []
        if days > 1 and not origin_label:
            missing.append("origin")
        if not destination_label:
            missing.append("destination")
        if (days > 1 or nights > 0) and not travel_dates.get("start"):
            missing.append("start_date")
        if (days > 1 or nights > 0) and not travel_dates.get("end"):
            missing.append("end_date")
        return missing

    def _booking_summary(self, components, missing_inputs, reservation_storage, duration_alignment=None):
        status_scores = {
            "not_needed_for_day_trip": 1.0,
            "optional_for_day_trip": 1.0,
            "ready_for_provider": 0.85,
            "estimated": 0.8,
            "manual_or_link_out": 0.65,
            "needs_provider": 0.35,
            "provider_needed": 0.35,
        }
        component_scores = [
            status_scores.get(component.get("status"), 0.45)
            for component in components
        ]
        base_score = sum(component_scores) / len(component_scores) if component_scores else 0.0
        missing_penalty = min(0.36, len(missing_inputs) * 0.12)
        duration_penalty = 0.16 if (duration_alignment or {}).get("status") == "needs_attention" else (
            0.08 if (duration_alignment or {}).get("status") == "watch" else 0.0
        )
        storage_bonus = 0.08 if reservation_storage.get("status") == "ready" else 0.0
        readiness_score = max(0.0, min(1.0, base_score - missing_penalty - duration_penalty + storage_bonus))

        ready_statuses = {
            "not_needed_for_day_trip",
            "optional_for_day_trip",
            "ready_for_provider",
            "estimated",
        }
        provider_statuses = {"ready_for_provider", "manual_or_link_out"}
        blocked_statuses = {"needs_provider", "provider_needed"}
        estimate_ready_count = sum(1 for component in components if component.get("estimate"))
        next_action_count = sum(len(component.get("next_steps") or []) for component in components)

        if (duration_alignment or {}).get("status") == "needs_attention":
            message = (duration_alignment or {}).get("message") or "Fix trip duration details before booking."
        elif (duration_alignment or {}).get("status") == "watch":
            message = (duration_alignment or {}).get("message") or "Review trip duration before booking."
        elif missing_inputs:
            message = "Add trip details before Adventour can prepare booking steps."
        elif readiness_score >= 0.85:
            message = "Booking steps are ready to prepare and confirmations can be saved."
        else:
            message = "Some booking pieces still need provider or manual confirmation."

        return {
            "readiness_score": round(readiness_score, 3),
            "ready_component_count": sum(1 for component in components if component.get("status") in ready_statuses),
            "provider_action_count": sum(1 for component in components if component.get("status") in provider_statuses),
            "blocked_component_count": sum(1 for component in components if component.get("status") in blocked_statuses),
            "missing_input_count": len(missing_inputs),
            "missing_inputs": missing_inputs,
            "estimate_ready_count": estimate_ready_count,
            "next_action_count": next_action_count,
            "reservation_storage_ready": reservation_storage.get("status") == "ready",
            "duration_alignment_status": (duration_alignment or {}).get("status"),
            "duration_alignment_message": (duration_alignment or {}).get("message"),
            "message": message,
        }

    def _flight_action(self, days, nights, origin_label):
        if days == 1 and nights == 0:
            return "Flights are optional for day trips. Save a flight or train confirmation if this launch point is not local."
        if origin_label:
            return "Connect flight search to quote round trips, then save the confirmation number here."
        return "Add a departure city and trip dates when flight search is connected."

    def _stay_action(self, nights):
        if nights == 0:
            return "No overnight stay needed for this day plan unless you want to save one manually."
        return f"Plan {nights} night{'s' if nights != 1 else ''} near the route, then save hotel or home-share details."

    def _component_missing_inputs(self, required_inputs, available_inputs):
        missing = []
        for field in required_inputs:
            value = available_inputs.get(field)
            if value is None or value is False or value == "":
                missing.append(field)
        return missing

    def _flight_next_steps(self, days, nights, origin_label, destination_label, travel_dates, party_size):
        if days == 1 and nights == 0:
            return [
                "Skip flights if this is local; otherwise save a train or flight confirmation manually.",
                "Use local transport setup for the actual Adventour route.",
            ]

        steps = []
        if not origin_label:
            steps.append("Add your departure city so Adventour can prepare flight search.")
        if not destination_label:
            steps.append("Pick a destination before searching flights.")
        if not travel_dates.get("start") or not travel_dates.get("end"):
            steps.append("Add start and end dates before comparing round trips.")
        if origin_label and destination_label and travel_dates.get("start") and travel_dates.get("end"):
            steps.append(f"Search round trips for {party_size} traveler{'s' if party_size != 1 else ''}.")
            steps.append("Save airline, confirmation number, total cost, and arrival time in Adventour.")
        return steps

    def _stay_next_steps(self, nights, destination_label, travel_dates, party_size, lodging_type=None, stay_neighborhood=None):
        if nights == 0:
            return [
                "No stay is required for this day route.",
                "Save a hotel or home-share only if you decide to extend the trip.",
            ]

        steps = []
        if not destination_label:
            steps.append("Pick a destination before searching stays.")
        if not travel_dates.get("start") or not travel_dates.get("end"):
            steps.append("Add travel dates before comparing stays.")
        if lodging_type:
            readable_type = self._lodging_type_label(lodging_type).lower()
            steps.append(f"Compare {readable_type} options for cancellation flexibility, fees, and check-in timing.")
        else:
            steps.append("Choose hotel or home-share based on group size, kitchen needs, and cancellation flexibility.")
        if stay_neighborhood:
            steps.append(f"Use {stay_neighborhood} as the starting neighborhood for stay search, then adjust around the first or last stop.")
        else:
            steps.append("Prefer a neighborhood near the first or last stop to reduce arrival-day friction.")
        steps.append(f"Save the stay confirmation and total cost for {party_size} traveler{'s' if party_size != 1 else ''}.")
        return steps

    def _flight_provider_options(self, days, nights, origin_label=None, destination_label=None, travel_dates=None, party_size=1):
        if days == 1 and nights == 0:
            return [
                {
                    "label": "Manual flight or train",
                    "url": self._search_url(
                        "flight or train",
                        origin_label,
                        destination_label,
                        travel_dates or {},
                        party_size,
                    ) if origin_label and destination_label else None,
                    "note": "Only needed if the launch point is not local.",
                },
            ]
        google_flights_url = self._search_url(
            "round trip flights",
            origin_label,
            destination_label,
            travel_dates or {},
            party_size,
            base_url="https://www.google.com/travel/flights",
        )
        return [
            {
                "label": "Google Flights",
                "url": google_flights_url,
                "note": "Good first pass for date and airline comparison.",
            },
            {
                "label": "Airline direct",
                "url": self._search_url(
                    "airline direct round trip",
                    origin_label,
                    destination_label,
                    travel_dates or {},
                    party_size,
                ) if origin_label and destination_label else None,
                "note": "Use after comparing prices so changes and confirmations stay with the airline.",
            },
        ]

    def _stay_provider_options(self, nights, destination_label=None, travel_dates=None, party_size=1, lodging_type=None, stay_neighborhood=None):
        search_destination = self._stay_search_destination(destination_label, stay_neighborhood)
        if nights == 0:
            return [
                {
                    "label": "Optional manual stay",
                    "url": self._search_url(
                        "hotel or home share",
                        None,
                        search_destination,
                        travel_dates or {},
                        party_size,
                    ) if destination_label else None,
                    "note": "Use only if you extend the trip.",
                },
            ]
        hotels_url = self._search_url(
            "hotels",
            None,
            search_destination,
            travel_dates or {},
            party_size,
            nights=nights,
            base_url="https://www.google.com/travel/hotels",
        )
        home_share_url = self._search_url(
            "home share stay",
            None,
            search_destination,
            travel_dates or {},
            party_size,
            nights=nights,
            base_url="https://www.airbnb.com/s/all",
        )
        options = [
            {
                "label": "Hotels",
                "url": hotels_url,
                "note": self._stay_provider_note("hotel", stay_neighborhood),
            },
            {
                "label": "Home-share",
                "url": home_share_url,
                "note": self._stay_provider_note("home_share", stay_neighborhood),
            },
        ]
        if lodging_type == "home_share":
            return [options[1], options[0]]
        return options

    def _search_url(
        self,
        query_prefix,
        origin_label=None,
        destination_label=None,
        travel_dates=None,
        party_size=1,
        nights=None,
        base_url="https://www.google.com/search",
    ):
        destination = destination_label or "destination"
        start = (travel_dates or {}).get("start")
        end = (travel_dates or {}).get("end")
        date_text = f"{start} to {end}" if start and end else "travel dates"
        origin_text = f"{origin_label} to " if origin_label else ""
        nights_text = f", {nights} night{'s' if nights != 1 else ''}" if nights else ""
        query = (
            f"{query_prefix} {origin_text}{destination}, {date_text}, "
            f"{party_size} traveler{'s' if party_size != 1 else ''}{nights_text}"
        )
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}q={quote_plus(query)}"

    def _search_hint(self, component_type, origin_label, destination_label, travel_dates, party_size, nights=None, lodging_type=None, stay_neighborhood=None):
        destination = destination_label or "destination"
        start = travel_dates.get("start")
        end = travel_dates.get("end")
        date_text = f"{start} to {end}" if start and end else "your travel dates"
        if component_type == "flight":
            origin = origin_label or "origin"
            return f"{origin} to {destination}, {date_text}, {party_size} traveler{'s' if party_size != 1 else ''}"
        if nights and nights > 0:
            lodging = self._lodging_type_label(lodging_type).lower() if lodging_type else "stay"
            area = f" near {stay_neighborhood}" if stay_neighborhood else ""
            return f"{lodging} in {destination}{area}, {date_text}, {nights} night{'s' if nights != 1 else ''}, {party_size} guest{'s' if party_size != 1 else ''}"
        return f"{destination}, optional stay, {party_size} guest{'s' if party_size != 1 else ''}"

    def _lodging_type_label(self, lodging_type):
        return {
            "hotel": "Hotel",
            "home_share": "Home-share",
            "flexible": "Hotel or home-share",
        }.get(lodging_type, str(lodging_type or "Stay").replace("_", " ").title())

    def _stay_search_destination(self, destination_label, stay_neighborhood=None):
        if stay_neighborhood and destination_label:
            return f"{stay_neighborhood}, {destination_label}"
        return destination_label

    def _stay_provider_note(self, provider_type, stay_neighborhood=None):
        area_note = f" near {stay_neighborhood}" if stay_neighborhood else ""
        if provider_type == "home_share":
            return f"Useful for groups that want shared space, kitchens, or longer stays{area_note}."
        return f"Useful for cancellation policies, neighborhood fit, and check-in timing{area_note}."

    def _next_best_actions(self, components, missing_inputs):
        if missing_inputs:
            return [
                {
                    "type": "missing_input",
                    "label": "Complete trip details",
                    "detail": "Add " + ", ".join(missing_inputs).replace("_", " ") + " before booking search is ready.",
                },
            ]

        actions = []
        for component in components:
            if component.get("status") in {"ready_for_provider", "estimated", "manual_or_link_out"}:
                steps = component.get("next_steps") or []
                actions.append({
                    "type": component.get("type"),
                    "label": component.get("label"),
                    "detail": steps[0] if steps else component.get("action"),
                })
        return actions[:4]

    def _planning_burden(self, components, missing_inputs, prep_checklist, summary):
        prep_items = (prep_checklist or {}).get("items") or []
        action_needed = [item for item in prep_items if item.get("status") == "action_needed"]
        manual_items = [item for item in prep_items if item.get("status") == "manual"]
        optional_items = [item for item in prep_items if item.get("status") == "optional"]
        ready_items = [item for item in prep_items if item.get("status") == "ready"]
        components_by_type = {component.get("type"): component for component in components or []}

        setup_items = []
        local_transport = components_by_type.get("local_transport") or {}
        if local_transport.get("setup_provider"):
            setup_items.append({
                "type": "local_transport",
                "label": "Local travel setup",
                "provider": local_transport.get("setup_provider"),
                "detail": local_transport.get("setup"),
                "source_url": local_transport.get("setup_source_url"),
            })

        provider_actions = [
            component
            for component in (components or [])
            if component.get("status") in {"ready_for_provider", "manual_or_link_out", "estimated"}
        ]
        burden_score = min(
            1.0,
            len(missing_inputs) * 0.18
            + len(action_needed) * 0.20
            + len(manual_items) * 0.10
            + len(setup_items) * 0.08
            + max(0, len(provider_actions) - len(ready_items)) * 0.04
            + (1 - float((summary or {}).get("readiness_score") or 0)) * 0.20,
        )
        if burden_score >= 0.6:
            level = "high"
            headline = "This route still has planning friction before it feels smooth."
        elif burden_score >= 0.32:
            level = "medium"
            headline = "This route is usable, but a few planning pieces need attention."
        else:
            level = "low"
            headline = "Planning burden is low; Adventour can guide most of this route."

        highest_friction = self._highest_friction_item(action_needed, manual_items, setup_items, optional_items)
        next_action = (
            highest_friction.get("action")
            or highest_friction.get("detail")
            if highest_friction else None
        ) or "Review booking links and save confirmations as you reserve."

        return {
            "level": level,
            "score": round(burden_score, 3),
            "headline": headline,
            "next_action": next_action,
            "action_needed_count": len(action_needed),
            "manual_count": len(manual_items),
            "optional_count": len(optional_items),
            "setup_count": len(setup_items),
            "provider_action_count": len(provider_actions),
            "highest_friction_item": highest_friction,
            "setup_items": setup_items,
            "booking_order": self._booking_order(prep_items),
        }

    def _highest_friction_item(self, action_needed, manual_items, setup_items, optional_items):
        if action_needed:
            return self._planning_item_payload(action_needed[0], "action_needed")
        if setup_items:
            item = setup_items[0]
            return {
                "id": item.get("type"),
                "label": item.get("label"),
                "status": "setup",
                "detail": item.get("detail"),
                "action": f"Open {item.get('provider')} setup before starting local travel." if item.get("provider") else item.get("detail"),
                "source_url": item.get("source_url"),
            }
        if manual_items:
            return self._planning_item_payload(manual_items[0], "manual")
        if optional_items:
            return self._planning_item_payload(optional_items[0], "optional")
        return None

    def _planning_item_payload(self, item, status):
        return {
            "id": item.get("id"),
            "label": item.get("label"),
            "status": status,
            "detail": item.get("detail"),
            "action": item.get("action"),
            "component_type": item.get("component_type"),
            "source_url": item.get("source_url"),
        }

    def _booking_order(self, prep_items):
        priority = {
            "duration_alignment": 0,
            "trip_details": 1,
            "flight": 2,
            "stay": 3,
            "local_transport": 4,
            "tickets": 5,
        }
        return [
            self._planning_item_payload(item, item.get("status"))
            for item in sorted(
                prep_items or [],
                key=lambda item: (priority.get(item.get("id"), 9), item.get("priority", 9)),
            )
        ][:5]

    def _booking_timeline(self, prep_checklist, booking_action_links, planning_burden, missing_inputs):
        prep_items = (prep_checklist or {}).get("items") or []
        links_by_component = {
            link.get("component_type"): link
            for link in (booking_action_links or [])
            if link.get("component_type")
        }
        timeline = []

        if missing_inputs:
            trip_item = next((item for item in prep_items if item.get("id") == "trip_details"), None)
            timeline.append(self._timeline_item(
                phase="unlock",
                label="Finish trip basics",
                status="action_needed",
                detail=(trip_item or {}).get("detail") or "Add " + ", ".join(missing_inputs).replace("_", " ") + ".",
                action=(trip_item or {}).get("action") or "Finish origin, dates, and destination before booking.",
                component_type="missing_input",
                priority=1,
            ))
            return {
                "status": "needs_details",
                "headline": "Finish trip basics before booking the Adventour.",
                "items": timeline,
            }

        phase_by_item = {
            "flight": "book",
            "stay": "book",
            "local_transport": "setup",
            "tickets": "reserve",
            "trip_details": "ready",
        }
        timeline_priority = {
            "flight": 2,
            "stay": 3,
            "local_transport": 4,
            "tickets": 5,
        }
        for item in prep_items:
            item_id = item.get("id")
            if item_id == "trip_details" and item.get("status") == "ready":
                continue
            link = links_by_component.get(item.get("component_type"))
            if item_id == "tickets":
                link = links_by_component.get("event_or_place") or link
            timeline.append(self._timeline_item(
                phase=phase_by_item.get(item_id, "prep"),
                label=item.get("label"),
                status=item.get("status"),
                detail=item.get("detail"),
                action=item.get("action"),
                component_type=item.get("component_type"),
                priority=timeline_priority.get(item_id, item.get("priority", 9)),
                provider=link.get("provider_label") if link else item.get("provider"),
                source_url=(link.get("url") if link else item.get("source_url")),
                stores_reservation=bool(link.get("stores_reservation")) if link else item.get("status") in {"manual", "ready"},
                reservation_type=link.get("reservation_type") if link else None,
            ))

        status = "low_friction" if (planning_burden or {}).get("level") == "low" else "needs_attention"
        return {
            "status": status,
            "headline": self._booking_timeline_headline(status, timeline),
            "items": sorted(timeline, key=lambda item: (item.get("priority", 9), item.get("label") or ""))[:6],
        }

    def _timeline_item(
        self,
        phase,
        label,
        status,
        detail,
        action,
        component_type,
        priority=9,
        provider=None,
        source_url=None,
        stores_reservation=False,
        reservation_type=None,
    ):
        return {
            "phase": phase,
            "label": label,
            "status": status,
            "detail": detail,
            "action": action,
            "component_type": component_type,
            "priority": priority,
            "provider": provider,
            "source_url": source_url,
            "stores_reservation": bool(stores_reservation),
            "reservation_type": reservation_type,
        }

    def _booking_timeline_headline(self, status, timeline):
        if status == "needs_attention":
            action_count = sum(1 for item in timeline if item.get("status") == "action_needed")
            if action_count:
                return f"{action_count} booking step{'s' if action_count != 1 else ''} still need details."
            return "A few booking or setup steps still need attention."
        saveable_count = sum(1 for item in timeline if item.get("stores_reservation"))
        if saveable_count:
            return "Book, save confirmations, then launch with the route in one place."
        return "Travel setup is ready enough to launch."

    def _booking_handoff(self, components, booking_action_links, booking_timeline, missing_inputs, summary):
        quote_ready = [
            self._handoff_link_payload(link, "quote")
            for link in booking_action_links or []
            if link.get("component_type") in {"flight", "stay"} and link.get("url")
        ]
        save_ready = [
            self._handoff_link_payload(link, "save")
            for link in booking_action_links or []
            if link.get("stores_reservation")
        ]
        setup_ready = [
            self._handoff_component_payload(component)
            for component in components or []
            if component.get("type") == "local_transport" and component.get("status") == "estimated"
        ]
        required_inputs = self._handoff_required_inputs(components, missing_inputs)
        timeline_items = (booking_timeline or {}).get("items") or []
        saveable_timeline_count = sum(1 for item in timeline_items if item.get("stores_reservation"))
        ready_to_quote_count = len(quote_ready)
        ready_to_save_count = len(save_ready) + saveable_timeline_count

        if missing_inputs:
            status = "needs_details"
            headline = "Add trip basics so Adventour can open the right booking searches."
            next_step = f"Add {required_inputs[0]['label'].lower()}."
        elif ready_to_quote_count or ready_to_save_count:
            status = "ready"
            headline = "Travel handoff is ready: open links, book, then save confirmations here."
            next_step = "Open the first booking link, compare options, then save the confirmation in Adventour."
        else:
            status = "manual"
            headline = "Travel handoff needs manual provider links before this route feels bookable."
            next_step = "Review the booking checklist and add provider details manually."

        return {
            "status": status,
            "headline": headline,
            "next_step": next_step,
            "readiness_score": (summary or {}).get("readiness_score"),
            "ready_to_quote_count": ready_to_quote_count,
            "ready_to_save_count": ready_to_save_count,
            "missing_input_count": len(required_inputs),
            "quote_ready": quote_ready[:3],
            "save_ready": save_ready[:4],
            "setup_ready": setup_ready[:2],
            "required_inputs": required_inputs,
        }

    def _booking_checklist(
        self,
        components,
        missing_inputs,
        booking_action_links,
        reservation_storage,
        booking_timeline,
        booking_handoff,
        prep_checklist,
        summary,
    ):
        components = components or []
        action_links = booking_action_links or []
        handoff = booking_handoff or {}
        timeline_items = (booking_timeline or {}).get("items") or []
        prep_items = (prep_checklist or {}).get("items") or []
        missing_inputs = missing_inputs or []
        local_transport = next((component for component in components if component.get("type") == "local_transport"), {})
        save_ready_count = int(handoff.get("ready_to_save_count") or 0)
        quote_ready_count = int(handoff.get("ready_to_quote_count") or 0)
        saveable_timeline_count = sum(1 for item in timeline_items if item.get("stores_reservation"))
        provider_link_count = len([link for link in action_links if link.get("url")])
        reservation_ready = (reservation_storage or {}).get("status") == "ready"

        items = []
        if missing_inputs:
            readable = ", ".join(str(item).replace("_", " ") for item in missing_inputs)
            items.append({
                "id": "trip_basics",
                "label": "Trip basics",
                "status": "action_needed",
                "detail": f"Missing {readable}. Adventour needs these before booking searches are reliable.",
                "action": f"Add {readable} before booking this route.",
                "blocking": True,
                "missing_inputs": missing_inputs,
            })
        else:
            items.append({
                "id": "trip_basics",
                "label": "Trip basics",
                "status": "ready",
                "detail": "Destination, party size, and route context are ready enough for booking setup.",
                "action": "Review the generated booking links when you are ready to compare options.",
                "blocking": False,
                "missing_inputs": [],
            })

        items.append({
            "id": "provider_links",
            "label": "Provider links",
            "status": "ready" if provider_link_count else "manual",
            "detail": (
                f"{provider_link_count} booking link{'s' if provider_link_count != 1 else ''} prepared."
                if provider_link_count
                else "No provider links are ready yet; use manual search until a provider is connected."
            ),
            "action": (
                "Open the first booking link, compare options, then save the confirmation here."
                if provider_link_count
                else "Add provider links or use manual booking searches for this route."
            ),
            "blocking": bool(missing_inputs),
            "link_count": provider_link_count,
            "quote_ready_count": quote_ready_count,
        })

        items.append({
            "id": "reservation_wallet",
            "label": "Reservation wallet",
            "status": "ready" if reservation_ready else "manual",
            "detail": (
                f"{save_ready_count or saveable_timeline_count} save-ready slot{'s' if (save_ready_count or saveable_timeline_count) != 1 else ''} can store confirmations."
                if reservation_ready
                else "Reservation storage is not connected yet."
            ),
            "action": (
                "After booking, save provider, confirmation number, cost, and notes in Adventour."
                if reservation_ready
                else "Connect reservation storage before relying on this packet for confirmations."
            ),
            "blocking": not reservation_ready,
            "save_ready_count": save_ready_count or saveable_timeline_count,
        })

        if local_transport:
            transport_ready = local_transport.get("status") == "estimated"
            items.append({
                "id": "local_transport",
                "label": "Local travel",
                "status": "ready" if transport_ready else "manual",
                "detail": local_transport.get("setup") or local_transport.get("action") or "Choose how the group will move between stops.",
                "action": (
                    (local_transport.get("setup_steps") or [None])[0]
                    or local_transport.get("action")
                    or "Pick local transport before starting the route."
                ),
                "blocking": False,
                "provider": local_transport.get("setup_provider"),
                "source_url": local_transport.get("setup_source_url"),
            })

        ticket_item = next((item for item in prep_items if item.get("id") == "tickets"), None)
        items.append({
            "id": "tickets_and_rsvps",
            "label": "Tickets and RSVPs",
            "status": (ticket_item or {}).get("status") or "manual",
            "detail": (ticket_item or {}).get("detail") or "Timed-entry stops and local events can be booked externally and saved here.",
            "action": (ticket_item or {}).get("action") or "Open event or place links, then save reservation notes in Adventour.",
            "blocking": False,
        })

        blocking_count = sum(1 for item in items if item.get("blocking"))
        ready_count = sum(1 for item in items if item.get("status") == "ready")
        action_count = sum(1 for item in items if item.get("status") in {"action_needed", "manual"})
        if blocking_count:
            status = "needs_details"
            headline = "A few trip basics are blocking the booking packet."
        elif action_count:
            status = "ready_with_manual_steps"
            headline = "Booking is usable; Adventour marked the manual pieces."
        else:
            status = "ready"
            headline = "Booking, saving, and local setup are ready."

        next_item = next((item for item in items if item.get("blocking")), None)
        if not next_item:
            next_item = next((item for item in items if item.get("status") != "ready"), None)

        return {
            "status": status,
            "headline": headline,
            "readiness_score": (summary or {}).get("readiness_score"),
            "blocking_count": blocking_count,
            "ready_count": ready_count,
            "action_count": action_count,
            "items": items,
            "next_action": (next_item or {}).get("action") or handoff.get("next_step"),
        }

    def _handoff_link_payload(self, link, action_kind):
        return {
            "id": link.get("id"),
            "component_type": link.get("component_type"),
            "label": link.get("label"),
            "provider_label": link.get("provider_label"),
            "url": link.get("url"),
            "reservation_type": link.get("reservation_type"),
            "search_hint": link.get("search_hint"),
            "draft_title": link.get("draft_title"),
            "draft_provider": link.get("draft_provider"),
            "draft_booking_url": link.get("draft_booking_url"),
            "draft_notes": link.get("draft_notes"),
            "action_kind": action_kind,
        }

    def _handoff_component_payload(self, component):
        estimate = component.get("estimate") or {}
        recommended_option = next(
            (option for option in component.get("options") or [] if option.get("recommended")),
            None,
        )
        return {
            "id": component.get("id"),
            "component_type": component.get("type"),
            "label": component.get("label"),
            "provider_label": component.get("setup_provider"),
            "url": component.get("setup_source_url"),
            "estimate": {
                "currency": estimate.get("currency", "USD"),
                "per_person_low": estimate.get("per_person_low"),
                "per_person_high": estimate.get("per_person_high"),
            } if estimate else None,
            "recommended_option": {
                "id": recommended_option.get("id"),
                "label": recommended_option.get("label"),
                "why": recommended_option.get("why"),
            } if recommended_option else None,
        }

    def _handoff_required_inputs(self, components, missing_inputs):
        labels = {
            "origin": "Departure city",
            "destination": "Destination",
            "start_date": "Start date",
            "end_date": "End date",
            "dates": "Trip dates",
            "traveler_count": "Traveler count",
            "party_size": "Party size",
            "lodging_type": "Stay style",
            "neighborhood": "Stay neighborhood",
        }
        seen = set()
        required = []
        for field in list(missing_inputs or []):
            if field not in seen:
                seen.add(field)
                required.append({"id": field, "label": labels.get(field, field.replace("_", " ").title())})
        for component in components or []:
            for field in component.get("missing_inputs") or []:
                key = f"{component.get('type')}_{field}"
                if key in seen:
                    continue
                seen.add(key)
                required.append({
                    "id": key,
                    "label": labels.get(field, field.replace("_", " ").title()),
                    "component_type": component.get("type"),
                })
        return required[:6]

    def _booking_action_links(self, components):
        links = []
        for component in components:
            provider_option = next(
                (option for option in component.get("provider_options") or [] if option.get("url")),
                None,
            )
            if not provider_option and component.get("setup_source_url"):
                provider_option = {
                    "label": component.get("setup_provider") or component.get("label"),
                    "url": component.get("setup_source_url"),
                    "note": component.get("setup") or component.get("action"),
                }
            if not provider_option:
                continue

            reservation_type = self._reservation_type_for_component(component.get("type"))
            reservation_notes = [
                component.get("action"),
                provider_option.get("note"),
                f"Search hint: {component.get('search_hint')}" if component.get("search_hint") else None,
            ]
            links.append({
                "id": component.get("id"),
                "component_type": component.get("type"),
                "label": component.get("label"),
                "status": component.get("status"),
                "provider_label": provider_option.get("label"),
                "url": provider_option.get("url"),
                "note": provider_option.get("note") or component.get("action"),
                "search_hint": component.get("search_hint"),
                "stores_reservation": bool(component.get("stores_reservation")),
                "reservation_type": reservation_type,
                "draft_title": self._reservation_title_for_component(component, reservation_type),
                "draft_provider": provider_option.get("label"),
                "draft_booking_url": provider_option.get("url"),
                "draft_notes": "\n".join(note for note in reservation_notes if note),
            })

        priority = {
            "flight": 1,
            "stay": 2,
            "local_transport": 3,
            "event_or_place": 4,
        }
        return sorted(links, key=lambda item: (priority.get(item.get("component_type"), 9), item.get("label") or ""))[:4]

    def _reservation_type_for_component(self, component_type):
        if component_type == "event_or_place":
            return "place"
        if component_type in {"flight", "stay", "local_transport"}:
            return component_type
        return "other"

    def _reservation_title_for_component(self, component, reservation_type):
        label = component.get("label") or "Booking"
        if reservation_type == "local_transport":
            return f"{label} setup"
        if reservation_type == "place":
            return "Tickets or place reservation"
        return label

    def _prep_checklist(self, components, missing_inputs, duration_alignment=None):
        items = []
        components_by_type = {component.get("type"): component for component in components}

        if (duration_alignment or {}).get("status") in {"watch", "needs_attention"}:
            items.append({
                "id": "duration_alignment",
                "label": "Trip duration",
                "status": "action_needed" if (duration_alignment or {}).get("status") == "needs_attention" else "manual",
                "priority": 1,
                "detail": (duration_alignment or {}).get("message") or "Review the selected trip style, route days, and travel dates.",
                "action": (duration_alignment or {}).get("next_action") or "Confirm whether this is a day, weekend, or vacation plan.",
                "component_type": "trip_duration",
            })

        if missing_inputs:
            items.append({
                "id": "trip_details",
                "label": "Trip details",
                "status": "action_needed",
                "priority": 2 if (duration_alignment or {}).get("status") in {"watch", "needs_attention"} else 1,
                "detail": "Add " + ", ".join(missing_inputs).replace("_", " ") + ".",
                "action": "Finish destination, origin, and dates before provider searches.",
                "component_type": "missing_input",
            })
        else:
            items.append({
                "id": "trip_details",
                "label": "Trip details",
                "status": "ready",
                "priority": 5,
                "detail": "Destination, dates, and party details are ready enough for this route.",
                "action": "Use the booking cards below when you are ready to reserve.",
                "component_type": "trip",
            })

        flight = components_by_type.get("flight") or {}
        if flight.get("status") == "needs_provider":
            items.append(self._prep_item_from_component(
                flight,
                "flight",
                "Arrival travel",
                "action_needed",
                2,
                "Search flights or trains once origin and dates are set.",
            ))
        elif flight.get("status") == "ready_for_provider":
            items.append(self._prep_item_from_component(
                flight,
                "flight",
                "Arrival travel",
                "ready",
                3,
                "Compare flight or train options and save the confirmation.",
            ))
        elif flight.get("status") == "optional_for_day_trip":
            items.append(self._prep_item_from_component(
                flight,
                "flight",
                "Arrival travel",
                "optional",
                5,
                "Skip if this is local; save a flight or train only if needed.",
            ))

        stay = components_by_type.get("stay") or {}
        if stay.get("status") == "needs_provider":
            items.append(self._prep_item_from_component(
                stay,
                "stay",
                "Stay",
                "action_needed",
                2,
                "Choose lodging type and neighborhood before overnight travel.",
            ))
        elif stay.get("status") == "ready_for_provider":
            items.append(self._prep_item_from_component(
                stay,
                "stay",
                "Stay",
                "ready",
                3,
                "Compare hotel or home-share options near the route.",
            ))
        elif stay.get("status") == "not_needed_for_day_trip":
            items.append(self._prep_item_from_component(
                stay,
                "stay",
                "Stay",
                "optional",
                5,
                "No overnight stay is needed for this route.",
            ))

        local_transport = components_by_type.get("local_transport") or {}
        if local_transport:
            recommended_option = next(
                (option for option in local_transport.get("options") or [] if option.get("recommended")),
                None,
            )
            mode_label = recommended_option.get("label") if recommended_option else local_transport.get("label")
            items.append({
                "id": "local_transport",
                "label": "Local travel",
                "status": "ready" if local_transport.get("status") == "estimated" else "action_needed",
                "priority": 2,
                "detail": f"{mode_label} is the current best local setup.",
                "action": (local_transport.get("next_steps") or [local_transport.get("action") or "Check local transport before leaving."])[0],
                "component_type": "local_transport",
                "provider": local_transport.get("setup_provider"),
                "source_url": local_transport.get("setup_source_url"),
                "estimate": local_transport.get("estimate"),
            })

        tickets = components_by_type.get("event_or_place") or {}
        if tickets:
            items.append(self._prep_item_from_component(
                tickets,
                "tickets",
                "Tickets and reservations",
                "manual",
                3,
                "Open place/event links and save confirmations in Adventour.",
            ))

        return {
            "status": self._prep_checklist_status(items),
            "headline": self._prep_checklist_headline(items),
            "items": sorted(items, key=lambda item: (item.get("priority", 9), item.get("label", ""))),
        }

    def _prep_item_from_component(self, component, item_id, label, status, priority, fallback_action):
        steps = component.get("next_steps") or []
        return {
            "id": item_id,
            "label": label,
            "status": status,
            "priority": priority,
            "detail": component.get("action") or fallback_action,
            "action": steps[0] if steps else fallback_action,
            "component_type": component.get("type"),
            "provider_options": component.get("provider_options", [])[:2],
            "missing_inputs": component.get("missing_inputs", []),
        }

    def _prep_checklist_status(self, items):
        statuses = {item.get("status") for item in items}
        if "action_needed" in statuses:
            return "needs_attention"
        if statuses.intersection({"manual", "optional"}):
            return "ready_with_optional_steps"
        return "ready"

    def _prep_checklist_headline(self, items):
        action_count = sum(1 for item in items if item.get("status") == "action_needed")
        if action_count:
            return f"{action_count} prep item{'s' if action_count != 1 else ''} need attention before this route is smooth."
        manual_count = sum(1 for item in items if item.get("status") in {"manual", "optional"})
        if manual_count:
            return "Core travel setup is ready; a few optional or manual details can be saved."
        return "Travel setup is ready to prepare."

    def _local_transport(self, days, stop_count, estimated_segments, destination, route_distance_meters=None, party_size=1, preferred_local_transport=None):
        guidance = self._destination_transport_guidance(destination)
        options = self._transport_options(
            days,
            estimated_segments,
            route_distance_meters,
            party_size,
            guidance,
            preferred_local_transport,
        )
        recommended_option = next((option for option in options if option["recommended"]), options[0])
        if recommended_option["id"] == "walk":
            mode = "walking_or_rideshare"
            label = "Walkable route"
            action = guidance.get("walk_setup") if guidance else f"Keep {destination} simple: open directions between stops and use rideshare only when needed."
        elif recommended_option["id"] == "transit":
            mode = "public_transit_or_rideshare"
            label = "Transit plus rideshare"
            action = guidance.get("transit_setup") if guidance else "Check whether the city uses a transit card/app, then save that setup note to the route."
        elif recommended_option["id"] == "rental_car":
            mode = "rental_car" if preferred_local_transport == "rental_car" else "transit_pass_or_rental"
            label = "Rental car" if preferred_local_transport == "rental_car" else "Transit pass or rental"
            action = guidance.get("rental_setup") if guidance else "Consider a day transit pass or rental if the route spans several neighborhoods."
        else:
            mode = "rideshare"
            label = "Rideshare flexible"
            action = guidance.get("rideshare_setup") if guidance else "Use rideshare for longer hops and walking between close stops."

        estimate = recommended_option["estimate"]

        return {
            "id": "local_transport",
            "type": "local_transport",
            "label": label,
            "status": "estimated",
            "mode": mode,
            "estimated_segments": estimated_segments,
            "preferred_local_transport": preferred_local_transport,
            "route_distance_meters": round(route_distance_meters) if route_distance_meters is not None else None,
            "estimate": {
                "currency": "USD",
                "per_person_low": estimate["per_person_low"],
                "per_person_high": estimate["per_person_high"],
            },
            "options": options,
            "action": action,
            "setup": action,
            "setup_provider": guidance.get("provider") if guidance else None,
            "setup_source_url": guidance.get("source_url") if guidance else None,
            "setup_steps": guidance.get("setup_steps", []) if guidance else [
                "Check local transit passes or apps before leaving.",
                "Keep rideshare as a backup for weather, late-night, or low-frequency legs.",
            ],
            "next_steps": guidance.get("setup_steps", []) if guidance else [
                "Check local transit passes or apps before leaving.",
                "Keep rideshare as a backup for weather, late-night, or low-frequency legs.",
            ],
            "provider_options": [
                {
                    "label": guidance.get("provider") if guidance else "Local transit or rideshare",
                    "url": guidance.get("source_url") if guidance else None,
                    "note": action,
                },
            ],
            "stores_reservation": True,
        }

    def _transport_options(self, days, estimated_segments, route_distance_meters, party_size, guidance=None, preferred_local_transport=None):
        segments = max(1, estimated_segments)
        distance = route_distance_meters or 0
        walkable = route_distance_meters is not None and distance <= 3000 and estimated_segments <= 3
        transit_preferred = route_distance_meters is None or distance <= 18000
        rental_preferred = days > 1 and route_distance_meters is not None and distance > 25000
        rideshare_preferred = not walkable and not transit_preferred and not rental_preferred

        options = [
            {
                "id": "walk",
                "label": "Walk",
                "recommended": walkable,
                "estimate": {"currency": "USD", "per_person_low": 0, "per_person_high": 0},
                "setup": guidance.get("walk_setup") if guidance else "Bring comfortable shoes and open stop-by-stop directions.",
                "why": "Best when stops cluster tightly.",
            },
            {
                "id": "transit",
                "label": "Train or bus",
                "recommended": transit_preferred and not walkable,
                "estimate": {"currency": "USD", "per_person_low": 6 * days, "per_person_high": 24 * days},
                "setup": guidance.get("transit_setup") if guidance else "Check the local transit pass or app before leaving.",
                "why": "Good for city routes with several medium-distance hops.",
            },
            {
                "id": "rideshare",
                "label": "Rideshare",
                "recommended": rideshare_preferred,
                "estimate": {
                    "currency": "USD",
                    "per_person_low": round((12 * segments) / max(1, party_size)),
                    "per_person_high": round((32 * segments) / max(1, party_size)),
                },
                "setup": guidance.get("rideshare_setup") if guidance else "Keep a rideshare app ready for late-night or weather-sensitive legs.",
                "why": "Flexible backup when stops are spread out.",
            },
            {
                "id": "rental_car",
                "label": "Rental car",
                "recommended": rental_preferred,
                "estimate": {
                    "currency": "USD",
                    "per_person_low": round((45 * days) / max(1, party_size)),
                    "per_person_high": round((120 * days) / max(1, party_size)),
                },
                "setup": guidance.get("rental_setup") if guidance else "Reserve parking-aware lodging and save rental confirmation details.",
                "why": "Useful when the route spans far-apart neighborhoods or day trips.",
            },
        ]
        if preferred_local_transport:
            for option in options:
                option["recommended"] = option["id"] == preferred_local_transport
                if option["recommended"]:
                    option["why"] = f"{option['why']} Picked because you prefer {option['label'].lower()} for this trip."
        return options

    def _normalize_transport_preference(self, value):
        normalized = (value or "").strip().lower()
        aliases = {
            "auto": None,
            "public_transit": "transit",
            "train": "transit",
            "bus": "transit",
            "car": "rental_car",
            "rental": "rental_car",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in {"walk", "transit", "rideshare", "rental_car"}:
            return normalized
        return None

    def _destination_transport_guidance(self, destination):
        normalized = (destination or "").lower()
        for guidance in CITY_TRANSPORT_GUIDANCE:
            if any(token in normalized for token in guidance["matches"]):
                return guidance
        return None

    def _route_distance_meters(self, route_days):
        total = 0.0
        found_segment = False
        for day in route_days:
            points = [
                self._stop_coordinates(stop)
                for stop in day.get("stops", [])
            ]
            points = [point for point in points if point]
            for index in range(1, len(points)):
                segment = self._haversine_meters(points[index - 1], points[index])
                if segment is not None:
                    total += segment
                    found_segment = True
        return total if found_segment else None

    def _stop_coordinates(self, stop):
        recommendation = stop.get("recommendation") or stop
        lat = recommendation.get("latitude") or recommendation.get("display", {}).get("latitude")
        lng = recommendation.get("longitude") or recommendation.get("display", {}).get("longitude")
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)

    def _haversine_meters(self, start, end):
        lat1, lon1 = start
        lat2, lon2 = end
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
