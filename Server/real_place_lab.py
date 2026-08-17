import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from adventour_backend.models import Friendship, User, db
from adventour_backend.providers.place_providers import GooglePlacesProvider, ProviderRegistry
from adventour_backend.services.itinerary_service import ItineraryRecommendationService
from adventour_backend.services.recommender_evaluation_service import RecommendationEvaluationService
from adventour_backend.services.recommender_service import RecommendationService, SCORING_PROFILES
from adventour_backend.services.travel_logistics_service import TravelLogisticsService


SERVER_DIR = Path(__file__).resolve().parent
SUITE_STATUS_RANK = {
    "needs_attention": 0,
    "watch": 1,
    "ready": 2,
}

REAL_PLACE_SUITES = {
    "friend_beta": [
        {
            "id": "orlando_spontaneous",
            "destination_label": "Orlando",
            "lat": 28.5383832,
            "lng": -81.3789269,
            "radius": 8000,
            "limit": 12,
            "tags": ["cafe", "restaurant", "market", "art_gallery", "park"],
            "scoring_profile": "authenticity_forward",
            "planned": False,
        },
        {
            "id": "austin_day_route",
            "destination_label": "Austin",
            "lat": 30.2672,
            "lng": -97.7431,
            "radius": 8000,
            "limit": 24,
            "tags": ["cafe", "restaurant", "concert_hall", "art_gallery", "market"],
            "scoring_profile": "phase1_balanced",
            "planned": True,
            "pace": "balanced",
            "trip_style": "day",
            "budget_profile": "flexible",
            "days": 1,
        },
        {
            "id": "chicago_friend_blend",
            "destination_label": "Chicago",
            "lat": 41.8781,
            "lng": -87.6298,
            "radius": 8000,
            "limit": 16,
            "tags": ["cafe", "restaurant", "market"],
            "friend_tags": [
                ["museum", "art_gallery", "park"],
            ],
            "scoring_profile": "group_friendly",
            "planned": False,
        },
        {
            "id": "seattle_friend_route",
            "destination_label": "Seattle",
            "lat": 47.6062,
            "lng": -122.3321,
            "radius": 8000,
            "limit": 24,
            "tags": ["cafe", "bakery", "market"],
            "friend_tags": [
                ["museum", "art_gallery", "park"],
            ],
            "scoring_profile": "group_friendly",
            "planned": True,
            "pace": "balanced",
            "trip_style": "day",
            "budget_profile": "flexible",
            "days": 1,
        },
        {
            "id": "nyc_events_route",
            "destination_label": "NYC",
            "lat": 40.7306,
            "lng": -73.9352,
            "radius": 8000,
            "limit": 24,
            "tags": ["cafe", "restaurant", "market", "art_gallery", "performing_arts_theater"],
            "scoring_profile": "fresh_discovery",
            "planned": True,
            "pace": "full",
            "trip_style": "day",
            "budget_profile": "flexible",
            "days": 1,
        },
        {
            "id": "nyc_weekend_quotes",
            "destination_label": "NYC",
            "lat": 40.7306,
            "lng": -73.9352,
            "radius": 8000,
            "limit": 24,
            "tags": ["cafe", "restaurant", "market", "art_gallery", "performing_arts_theater"],
            "scoring_profile": "phase1_balanced",
            "planned": True,
            "pace": "balanced",
            "trip_style": "weekend",
            "budget_profile": "flexible",
            "days": 2,
            "origin_label": "Orlando, FL",
            "travel_dates": {
                "start": "2026-09-18",
                "end": "2026-09-20",
            },
            "lodging_type": "hotel",
            "stay_neighborhood": "Williamsburg",
            "preferred_local_transport": "transit",
        },
    ],
}


def load_env(env_file):
    selected = Path(env_file) if env_file else SERVER_DIR / ".env.local"
    load_dotenv(selected, override=True)
    return selected


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def create_user(tags, suffix="user"):
    user = User(
        firebase_uid=f"real-place-lab-{suffix}",
        email=f"real-place-lab-{suffix}@adventour.local",
        username=f"real_place_lab_{suffix}",
        display_name=f"Real Place Lab {suffix}".replace("_", " ").title(),
        preferences=",".join(tags),
    )
    db.session.add(user)
    db.session.commit()
    return user


def create_lab_party(tags, friend_tags=None):
    user = create_user(tags, "viewer")
    friends = [
        create_user(tags_for_friend, f"friend_{index}")
        for index, tags_for_friend in enumerate(friend_tags or [], start=1)
    ]
    for friend in friends:
        db.session.add(Friendship(user_id=user.id, friend_id=friend.id, status="accepted"))
    db.session.commit()
    return user, friends


def print_result(result):
    print(f"Scoring profile: {result.get('scoring_profile')}")
    print(f"Query tags: {', '.join(result['query_tags'])}")
    if result["provider_errors"]:
        print(f"Provider errors: {json.dumps(result['provider_errors'], indent=2)}")
    if not result["recommendations"]:
        print("No recommendations returned.")
        print_readiness_report(result)
        return

    for index, item in enumerate(result["recommendations"], start=1):
        components = item["components"]
        display = item["display"]
        print(f"\n{index}. {item['name']} | score={item['score']} | distance={item['distance_meters']}m")
        print(f"   rating={display.get('rating')} reviews={display.get('user_ratings_total')} price={display.get('price_level')}")
        print(f"   types={', '.join(display.get('types') or [])}")
        print(f"   explanation: {item['explanation']}")
        print(
            "   components: "
            f"personal={components['personal_fit']} "
            f"group={components['group_fit']} "
            f"auth={components['authenticity']} "
            f"quality={components['quality']} "
            f"context={components['context_fit']} "
            f"chain_penalty={components['chain_penalty']} "
            f"price_penalty={components['price_penalty']}"
        )
    print_readiness_report(result)


def print_itinerary_result(result):
    readiness = result.get("route_readiness") or {}
    print(f"Scoring profile: {result.get('scoring_profile')}")
    print(f"Route readiness: {readiness.get('label')} ({round((readiness.get('score') or 0) * 100)}%)")
    print(f"Stops: {readiness.get('planned_stop_count')}/{readiness.get('expected_stop_count')}")
    if readiness.get("warnings"):
        print(f"Warnings: {' | '.join(readiness['warnings'])}")
    if readiness.get("strengths"):
        print(f"Strengths: {' | '.join(readiness['strengths'])}")
    price = (result.get("price_breakdown") or {}).get("per_person") or {}
    if price:
        print(f"Known estimate: ${price.get('total_known_low')}-${price.get('total_known_high')} / person")

    provider_errors = result.get("provider_errors") or []
    if provider_errors:
        print(f"Provider errors: {json.dumps(provider_errors, indent=2)}")

    for day in result.get("days", []):
        print(f"\n{day['title']}")
        print(f"  {day['summary']}")
        party_fit = day.get("party_fit") or {}
        if party_fit.get("message"):
            print(f"  party fit: {party_fit['message']}")
        for index, stop in enumerate(day.get("stops", []), start=1):
            recommendation = stop["recommendation"]
            display = recommendation.get("display") or {}
            print(
                f"  {index}. {stop['time_window']} | {stop['label']} | "
                f"{recommendation['name']} | score={recommendation.get('score')} "
                f"| rating={display.get('rating')} reviews={display.get('user_ratings_total')}"
            )
            alternatives = stop.get("alternatives") or []
            if alternatives:
                first_swap = alternatives[0]
                impact = first_swap.get("swap_impact") or {}
                reasons = ", ".join(impact.get("reasons") or [])
                print(f"     swap: {first_swap['name']} ({reasons})")
    print_readiness_report(result)


def print_readiness_report(result):
    report = RecommendationEvaluationService().scenario_readiness_report(result)
    print("")
    print(f"Scenario readiness: {report['status']} ({'friend-ready' if report['ready_for_friend_testing'] else 'not friend-ready yet'})")
    print(f"  {report['headline']}")
    for check in report.get("checks") or []:
        status = check["status"]
        value = check.get("value")
        print(f"  - {status}: {check['label']} ({value} / {check['target']})")
    if report.get("next_actions"):
        print("  next actions:")
        for action in report["next_actions"][:3]:
            print(f"    - {action}")


def print_profile_comparison(args):
    print("Live planned route profile comparison")
    print("profile | scenario readiness | route readiness | stops | first stop")
    print("-" * 88)
    for profile_name in sorted(SCORING_PROFILES):
        result = run_lab(args, scoring_profile=profile_name, planned=args.planned)
        scenario_readiness = RecommendationEvaluationService().scenario_readiness_report(result)
        if args.planned:
            readiness = result.get("route_readiness") or {}
            first_stop = next(
                (
                    stop["recommendation"]["name"]
                    for day in result.get("days", [])
                    for stop in day.get("stops", [])
                ),
                "none",
            )
            print(
                f"{profile_name} | {scenario_readiness['status']} | {readiness.get('label')} "
                f"{round((readiness.get('score') or 0) * 100)}% | "
                f"{readiness.get('planned_stop_count')}/{readiness.get('expected_stop_count')} | {first_stop}"
            )
        else:
            top = (result.get("recommendations") or [{}])[0].get("name", "none")
            print(f"{profile_name} | {scenario_readiness['status']} | n/a | n/a | {top}")


def scenario_args(args, scenario):
    values = vars(args).copy()
    values.update({
        key: value
        for key, value in scenario.items()
        if key not in {"id", "planned"}
    })
    return argparse.Namespace(**values)


def first_result_name(result):
    if result.get("mode") == "planned_itinerary":
        return next(
            (
                stop["recommendation"]["name"]
                for day in result.get("days", [])
                for stop in day.get("stops", [])
            ),
            None,
        )
    return (result.get("recommendations") or [{}])[0].get("name")


def suite_result_item(scenario, result):
    readiness = RecommendationEvaluationService().scenario_readiness_report(result)
    quality = result.get("recommendation_quality") or {}
    route_readiness = result.get("route_readiness") or {}
    test_verdict = readiness.get("test_verdict") or {}
    friend_readiness = readiness.get("friend_readiness") or {}
    quote_readiness = compact_quote_readiness(result)
    failed_checks = [
        {
            "name": check.get("name"),
            "label": check.get("label"),
            "status": check.get("status"),
            "value": check.get("value"),
            "target": check.get("target"),
            "message": check.get("message"),
        }
        for check in readiness.get("checks") or []
        if check.get("status") in {"fail", "warn", "unknown"}
    ]
    return {
        "id": scenario["id"],
        "destination_label": scenario.get("destination_label"),
        "planned": bool(scenario.get("planned")),
        "friend_count": len(scenario.get("friend_tags") or []),
        "scoring_profile": result.get("scoring_profile") or scenario.get("scoring_profile"),
        "status": readiness.get("status"),
        "ready_for_friend_testing": readiness.get("ready_for_friend_testing"),
        "beta_testable": readiness.get("beta_testable"),
        "headline": readiness.get("headline"),
        "metrics": readiness.get("metrics") or {},
        "route_label": route_readiness.get("label"),
        "route_score": route_readiness.get("score"),
        "top_pick": first_result_name(result),
        "test_verdict": compact_test_verdict(test_verdict),
        "friend_readiness": compact_friend_readiness(friend_readiness),
        "quote_readiness": quote_readiness,
        "pipeline_diagnostic": compact_pipeline_diagnostic(quality.get("diagnostic")),
        "failed_checks": failed_checks[:6],
        "warnings": readiness.get("warnings") or [],
        "next_actions": readiness.get("next_actions") or [],
    }


def compact_test_verdict(test_verdict):
    if not test_verdict:
        return None

    return {
        "status": test_verdict.get("status"),
        "headline": test_verdict.get("headline"),
        "score": test_verdict.get("score"),
        "friend_testable": bool(test_verdict.get("friend_testable")),
        "dimensions": [
            {
                "name": dimension.get("name"),
                "label": dimension.get("label"),
                "status": dimension.get("status"),
                "score": dimension.get("score"),
                "summary": dimension.get("summary"),
            }
            for dimension in test_verdict.get("dimensions") or []
        ],
        "blockers": test_verdict.get("blockers") or [],
        "next_actions": test_verdict.get("next_actions") or [],
    }


def compact_friend_readiness(friend_readiness):
    if not friend_readiness:
        return None

    return {
        "status": friend_readiness.get("status"),
        "headline": friend_readiness.get("headline"),
        "covered_member_count": friend_readiness.get("covered_member_count"),
        "underserved_count": friend_readiness.get("underserved_count"),
        "coverage_share": friend_readiness.get("coverage_share"),
        "average_group_fit": friend_readiness.get("average_group_fit"),
        "next_actions": friend_readiness.get("next_actions") or [],
    }


def compact_quote_readiness(result):
    trip_packet = result.get("trip_packet") or {}
    price_breakdown = result.get("price_breakdown") or {}
    cost_confidence = trip_packet.get("cost_confidence") or {}
    quote_plan = (
        price_breakdown.get("quote_plan")
        or trip_packet.get("quote_plan")
        or cost_confidence.get("quote_plan")
        or {}
    )
    if not quote_plan:
        return None

    required_count = int(quote_plan.get("required_count") or 0)
    ready_count = int(quote_plan.get("ready_count") or 0)
    missing_inputs = quote_plan.get("missing_inputs") or []
    items = [
        {
            "type": item.get("type"),
            "label": item.get("label"),
            "status": item.get("status"),
            "ready": bool(item.get("ready")),
            "missing_inputs": item.get("missing_inputs") or [],
            "primary_url": item.get("primary_url"),
        }
        for item in quote_plan.get("items") or []
    ]
    return {
        "status": quote_plan.get("status"),
        "required_count": required_count,
        "ready_count": ready_count,
        "missing_input_count": len(missing_inputs),
        "ready_coverage": round(ready_count / required_count, 3) if required_count else 1,
        "missing_inputs": missing_inputs,
        "message": quote_plan.get("message"),
        "items": items,
    }


def compact_pipeline_diagnostic(diagnostic):
    if not diagnostic:
        return None

    primary_issue = diagnostic.get("primary_issue") or {}
    return {
        "status": diagnostic.get("status"),
        "headline": diagnostic.get("headline"),
        "primary_issue": {
            "name": primary_issue.get("name"),
            "label": primary_issue.get("label"),
            "status": primary_issue.get("status"),
            "score": primary_issue.get("score"),
            "summary": primary_issue.get("summary"),
            "next_action": primary_issue.get("next_action"),
        } if primary_issue else None,
        "summary": diagnostic.get("summary") or {},
        "next_actions": diagnostic.get("next_actions") or [],
    }


def suite_dimension_summary(items):
    summary = {}
    for item in items:
        for dimension in ((item.get("test_verdict") or {}).get("dimensions") or []):
            name = dimension.get("name")
            status = dimension.get("status") or "unknown"
            if not name:
                continue
            row = summary.setdefault(name, {"pass": 0, "warn": 0, "fail": 0, "unknown": 0})
            row[status] = row.get(status, 0) + 1
    return {
        name: counts
        for name, counts in sorted(summary.items())
    }


def suite_pipeline_issue_summary(items):
    summary = {}
    for item in items:
        issue = ((item.get("pipeline_diagnostic") or {}).get("primary_issue") or {})
        name = issue.get("name")
        if not name:
            continue
        row = summary.setdefault(name, {"count": 0, "labels": set(), "statuses": {}})
        row["count"] += 1
        if issue.get("label"):
            row["labels"].add(issue["label"])
        status = issue.get("status") or "unknown"
        row["statuses"][status] = row["statuses"].get(status, 0) + 1
    return {
        name: {
            "count": data["count"],
            "labels": sorted(data["labels"]),
            "statuses": data["statuses"],
        }
        for name, data in sorted(summary.items())
    }


def suite_remediation_plan(items):
    buckets = {}

    def add(bucket, scenario_id, label, action, severity="watch"):
        if not action:
            return
        row = buckets.setdefault(bucket, {
            "id": bucket,
            "label": label,
            "scenario_ids": [],
            "actions": [],
            "severity": severity,
        })
        if scenario_id not in row["scenario_ids"]:
            row["scenario_ids"].append(scenario_id)
        if action not in row["actions"]:
            row["actions"].append(action)
        if severity == "needs_attention":
            row["severity"] = "needs_attention"

    for item in items:
        scenario_id = item.get("id")
        verdict = item.get("test_verdict") or {}
        for blocker in verdict.get("blockers") or []:
            add("scenario_blockers", scenario_id, "Scenario blockers", blocker, "needs_attention")
        for action in verdict.get("next_actions") or []:
            add("verdict_actions", scenario_id, "Friend beta next actions", action, item.get("status") or "watch")

        friend_readiness = item.get("friend_readiness") or {}
        if int(item.get("friend_count") or 0) > 0 and not verdict.get("friend_testable"):
            action = (
                (friend_readiness.get("next_actions") or [None])[0]
                or friend_readiness.get("headline")
                or "Rebuild this route with group-friendly scoring or swap in stops for underserved travelers."
            )
            add("friend_coverage", scenario_id, "Friend coverage", action, "needs_attention")

        quote_readiness = item.get("quote_readiness") or {}
        if (quote_readiness.get("required_count") or 0) > 0 and quote_readiness.get("status") != "ready_to_quote":
            missing = quote_readiness.get("missing_inputs") or []
            action = (
                f"Add {', '.join(missing[:3])} so flight/stay quote links are ready."
                if missing
                else quote_readiness.get("message")
                or "Add missing trip basics so flight/stay quote links are ready."
            )
            add("travel_quotes", scenario_id, "Travel quote readiness", action, "needs_attention")

        diagnostic = item.get("pipeline_diagnostic") or {}
        primary_issue = diagnostic.get("primary_issue") or {}
        if primary_issue.get("next_action"):
            add(
                f"pipeline_{primary_issue.get('name') or 'issue'}",
                scenario_id,
                primary_issue.get("label") or "Pipeline diagnostic",
                primary_issue.get("next_action"),
                "needs_attention" if primary_issue.get("status") == "fail" else "watch",
            )

        for failed_check in item.get("failed_checks") or []:
            add(
                f"check_{failed_check.get('name') or 'unknown'}",
                scenario_id,
                failed_check.get("label") or "Readiness check",
                failed_check.get("message"),
                "needs_attention" if failed_check.get("status") == "fail" else "watch",
            )

    ordered = sorted(
        buckets.values(),
        key=lambda row: (
            0 if row["severity"] == "needs_attention" else 1,
            -len(row["scenario_ids"]),
            row["label"],
        ),
    )
    return [
        {
            **row,
            "scenario_count": len(row["scenario_ids"]),
            "actions": row["actions"][:3],
        }
        for row in ordered[:8]
    ]


def run_suite(args):
    scenarios = REAL_PLACE_SUITES[args.suite]
    items = []
    for scenario in scenarios:
        result = run_lab(
            scenario_args(args, scenario),
            scoring_profile=scenario.get("scoring_profile"),
            planned=bool(scenario.get("planned")),
        )
        items.append(suite_result_item(scenario, result))

    ready_count = sum(1 for item in items if item["status"] == "ready")
    watch_count = sum(1 for item in items if item["status"] == "watch")
    attention_count = sum(1 for item in items if item["status"] == "needs_attention")
    beta_testable_count = sum(1 for item in items if item["beta_testable"])
    friend_testable_count = sum(
        1
        for item in items
        if (item.get("test_verdict") or {}).get("friend_testable")
    )
    friend_scenario_count = sum(1 for item in items if int(item.get("friend_count") or 0) > 0)
    friend_ready_count = sum(
        1
        for item in items
        if int(item.get("friend_count") or 0) > 0
        and (item.get("test_verdict") or {}).get("friend_testable")
    )
    quote_scenario_count = sum(
        1
        for item in items
        if ((item.get("quote_readiness") or {}).get("required_count") or 0) > 0
    )
    quote_ready_count = sum(
        1
        for item in items
        if ((item.get("quote_readiness") or {}).get("required_count") or 0) > 0
        and (item.get("quote_readiness") or {}).get("status") == "ready_to_quote"
    )
    status = "ready" if ready_count == len(items) else "watch" if attention_count == 0 else "needs_attention"
    report = {
        "suite": args.suite,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "scenario_count": len(items),
        "ready_count": ready_count,
        "watch_count": watch_count,
        "needs_attention_count": attention_count,
        "beta_testable_count": beta_testable_count,
        "friend_testable_count": friend_testable_count,
        "friend_scenario_count": friend_scenario_count,
        "friend_ready_count": friend_ready_count,
        "quote_scenario_count": quote_scenario_count,
        "quote_ready_count": quote_ready_count,
        "dimension_summary": suite_dimension_summary(items),
        "pipeline_issue_summary": suite_pipeline_issue_summary(items),
        "remediation_plan": suite_remediation_plan(items),
        "scenarios": items,
    }
    report["friend_testing_gate"] = suite_friend_testing_gate(report)
    report["quote_testing_gate"] = suite_quote_testing_gate(report)
    report["gate"] = suite_gate(
        report,
        min_status=getattr(args, "min_suite_status", "watch"),
        require_friend_ready=bool(getattr(args, "require_friend_ready", False)),
        require_quote_ready=bool(getattr(args, "require_quote_ready", False)),
    )
    return report


def suite_friend_testing_gate(report):
    friend_scenarios = [
        item
        for item in report.get("scenarios") or []
        if int(item.get("friend_count") or 0) > 0
    ]
    failed = [
        item["id"]
        for item in friend_scenarios
        if not ((item.get("test_verdict") or {}).get("friend_testable"))
    ]
    ready_count = len(friend_scenarios) - len(failed)
    return {
        "required": bool(friend_scenarios),
        "passed": not failed,
        "ready_count": ready_count,
        "scenario_count": len(friend_scenarios),
        "failed_scenarios": failed,
        "message": (
            "All friend scenarios are ready for trusted friend testing."
            if friend_scenarios and not failed
            else "Some friend scenarios still need stronger traveler coverage before testing."
            if failed
            else "No friend scenarios were included in this suite."
        ),
    }


def suite_quote_testing_gate(report):
    quote_scenarios = [
        item
        for item in report.get("scenarios") or []
        if ((item.get("quote_readiness") or {}).get("required_count") or 0) > 0
    ]
    failed = [
        item["id"]
        for item in quote_scenarios
        if (item.get("quote_readiness") or {}).get("status") != "ready_to_quote"
    ]
    ready_count = len(quote_scenarios) - len(failed)
    return {
        "required": bool(quote_scenarios),
        "passed": not failed,
        "ready_count": ready_count,
        "scenario_count": len(quote_scenarios),
        "failed_scenarios": failed,
        "message": (
            "All trip quote scenarios have flight/stay quote links ready."
            if quote_scenarios and not failed
            else "Some trip quote scenarios still need origin, dates, or stay details."
            if failed
            else "No trip quote scenarios were included in this suite."
        ),
    }


def suite_gate(report, min_status="watch", require_friend_ready=False, require_quote_ready=False):
    required_rank = SUITE_STATUS_RANK[min_status]
    failed = [
        item["id"]
        for item in report.get("scenarios") or []
        if SUITE_STATUS_RANK.get(item.get("status"), -1) < required_rank
    ]
    friend_gate = report.get("friend_testing_gate") or {}
    friend_failed = friend_gate.get("failed_scenarios") or []
    quote_gate = report.get("quote_testing_gate") or {}
    quote_failed = quote_gate.get("failed_scenarios") or []
    all_failed = list(dict.fromkeys(
        failed
        + (friend_failed if require_friend_ready else [])
        + (quote_failed if require_quote_ready else [])
    ))
    return {
        "min_status": min_status,
        "requires_friend_ready": bool(require_friend_ready),
        "requires_quote_ready": bool(require_quote_ready),
        "passed": not all_failed,
        "failed_scenarios": all_failed,
        "status_failed_scenarios": failed,
        "friend_failed_scenarios": friend_failed if require_friend_ready else [],
        "quote_failed_scenarios": quote_failed if require_quote_ready else [],
    }


def write_suite_report(path, report):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path


def print_suite_report(report):
    print(f"Real-place readiness suite: {report['suite']}")
    print(
        f"Status: {report['status']} | "
        f"ready={report['ready_count']} watch={report['watch_count']} "
        f"needs_attention={report['needs_attention_count']} "
        f"beta_testable={report['beta_testable_count']}/{report['scenario_count']} "
        f"friend_testable={report.get('friend_ready_count', 0)}/{report.get('friend_scenario_count', 0)} "
        f"quotes_ready={report.get('quote_ready_count', 0)}/{report.get('quote_scenario_count', 0)}"
    )
    friend_gate = report.get("friend_testing_gate") or {}
    if friend_gate.get("required"):
        print(
            f"Friend gate: {'passed' if friend_gate.get('passed') else 'failed'} "
            f"({friend_gate.get('ready_count', 0)}/{friend_gate.get('scenario_count', 0)} friend scenarios ready)"
        )
        if friend_gate.get("failed_scenarios"):
            print(f"Friend gate failures: {', '.join(friend_gate['failed_scenarios'])}")
    quote_gate = report.get("quote_testing_gate") or {}
    if quote_gate.get("required"):
        print(
            f"Quote gate: {'passed' if quote_gate.get('passed') else 'failed'} "
            f"({quote_gate.get('ready_count', 0)}/{quote_gate.get('scenario_count', 0)} trip quote scenarios ready)"
        )
        if quote_gate.get("failed_scenarios"):
            print(f"Quote gate failures: {', '.join(quote_gate['failed_scenarios'])}")
    gate = report.get("gate") or {}
    if gate:
        print(
            f"Gate: {'passed' if gate.get('passed') else 'failed'} "
            f"(min={gate.get('min_status')})"
        )
        if gate.get("failed_scenarios"):
            print(f"Gate failures: {', '.join(gate['failed_scenarios'])}")
    remediation_plan = report.get("remediation_plan") or []
    if remediation_plan:
        print("")
        print("Top remediation steps:")
        for index, item in enumerate(remediation_plan[:4], start=1):
            action = (item.get("actions") or ["Review this scenario."])[0]
            print(
                f"{index}. {item.get('label')} "
                f"({item.get('scenario_count', 0)} scenario{'s' if item.get('scenario_count', 0) != 1 else ''}): "
                f"{action}"
            )
    print("")
    print("scenario | status | verdict | party | route | top pick | next action")
    print("-" * 124)
    for item in report["scenarios"]:
        verdict = item.get("test_verdict") or {}
        action = (
            verdict.get("next_actions")
            or verdict.get("blockers")
            or item.get("next_actions")
            or item.get("warnings")
            or [""]
        )[0]
        route = item.get("route_label") or "basket"
        traveler_count = 1 + int(item.get("friend_count") or 0)
        party = f"{traveler_count} traveler{'s' if traveler_count != 1 else ''}"
        verdict_status = verdict.get("status") or "n/a"
        print(
            f"{item['id']} | {item['status']} | {verdict_status} | {party} | {route} | "
            f"{item.get('top_pick') or 'none'} | {action}"
        )


def run_lab(args, scoring_profile=None, planned=False):
    app = create_app()
    with app.app_context():
        db.create_all()
        user, friends = create_lab_party(args.tags, getattr(args, "friend_tags", None))
        member_ids = [friend.id for friend in friends]
        recommendation_service = RecommendationService(
            ProviderRegistry(providers=[GooglePlacesProvider()])
        )
        constraints = {
            "limit": args.limit,
            "avoid_chains": True,
            **({"scoring_profile": scoring_profile or args.scoring_profile} if scoring_profile or args.scoring_profile else {}),
        }
        if planned:
            constraints.update({
                "pace": args.pace,
                "trip_style": args.trip_style,
                "budget_profile": args.budget_profile,
            })
            for key in [
                "origin_label",
                "travel_dates",
                "lodging_type",
                "stay_neighborhood",
                "preferred_local_transport",
            ]:
                value = getattr(args, key, None)
                if value:
                    constraints[key] = value
            return ItineraryRecommendationService(
                recommendation_service,
                local_event_service=None,
                travel_logistics_service=TravelLogisticsService(),
            ).recommend_itinerary(
                user=user,
                member_ids=member_ids,
                location={"latitude": args.lat, "longitude": args.lng},
                radius_meters=args.radius,
                constraints=constraints,
                party_size=max(1, 1 + len(friends)),
                days=args.days,
                destination_label=args.destination_label,
            )

        return recommendation_service.recommend(
            user=user,
            member_ids=member_ids,
            location={"latitude": args.lat, "longitude": args.lng},
            radius_meters=args.radius,
            constraints=constraints,
        )


def main():
    parser = argparse.ArgumentParser(description="Run Adventour ranking against live Google Places candidates.")
    parser.add_argument("--env-file", default=None, help="Path to the backend env file. Defaults to Server/.env.local.")
    parser.add_argument("--lat", type=float, default=37.421998333333335, help="Search latitude.")
    parser.add_argument("--lng", type=float, default=-122.084, help="Search longitude.")
    parser.add_argument("--radius", type=int, default=1200, help="Search radius in meters.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum recommendations to print.")
    parser.add_argument("--tags", nargs="+", default=["cafe", "restaurant", "park"], help="User taste tags.")
    parser.add_argument(
        "--friend-tags",
        action="append",
        nargs="+",
        default=[],
        help="Optional accepted friend taste tags. Repeat for multiple synthetic friends.",
    )
    parser.add_argument("--scoring-profile", choices=sorted(SCORING_PROFILES), help="Named recommender profile to test.")
    parser.add_argument("--planned", action="store_true", help="Build a planned itinerary route from live provider candidates.")
    parser.add_argument("--all-profiles", action="store_true", help="Compare every named scoring profile. This calls the provider once per profile.")
    parser.add_argument("--suite", choices=sorted(REAL_PLACE_SUITES), help="Run a fixed real-place readiness suite. This calls the provider once per scenario.")
    parser.add_argument("--days", type=int, default=1, help="Planned itinerary days when using --planned.")
    parser.add_argument("--pace", choices=["relaxed", "balanced", "full"], default="balanced", help="Planned route pace.")
    parser.add_argument("--budget-profile", choices=["budget", "flexible", "splurge"], default="flexible", help="Planned route budget profile.")
    parser.add_argument("--trip-style", choices=["day", "weekend", "vacation"], default="day", help="Planned trip style.")
    parser.add_argument("--destination-label", default="Live Lab City", help="Readable label for planned itinerary output.")
    parser.add_argument("--output", help="Optional path to save a JSON report. Most useful with --suite.")
    parser.add_argument(
        "--min-suite-status",
        choices=["watch", "ready"],
        default="watch",
        help="Minimum scenario status for the suite gate. Defaults to watch, meaning no needs_attention scenarios.",
    )
    parser.add_argument(
        "--fail-on-suite-gate",
        action="store_true",
        help="Exit with code 1 when --suite does not meet --min-suite-status.",
    )
    parser.add_argument(
        "--require-friend-ready",
        action="store_true",
        help="Make the suite gate fail when friend scenarios are not friend-testable.",
    )
    parser.add_argument(
        "--require-quote-ready",
        action="store_true",
        help="Make the suite gate fail when trip quote scenarios are missing flight or stay quote links.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON result.")
    args = parser.parse_args()

    env_path = load_env(args.env_file)
    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit(f"GOOGLE_API_KEY is not configured. Checked {env_path}.")

    if args.all_profiles:
        print_profile_comparison(args)
        return

    if args.suite:
        report = run_suite(args)
        if args.output:
            output_path = write_suite_report(args.output, report)
            if not args.json:
                print(f"Saved suite report to {output_path}")
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_suite_report(report)
        if args.fail_on_suite_gate and not (report.get("gate") or {}).get("passed"):
            raise SystemExit(1)
        return

    result = run_lab(args, planned=args.planned)

    if args.json:
        print(json.dumps({
            **result,
            "scenario_readiness": RecommendationEvaluationService().scenario_readiness_report(result),
        }, indent=2))
    elif args.planned:
        print_itinerary_result(result)
    else:
        print_result(result)


if __name__ == "__main__":
    main()
