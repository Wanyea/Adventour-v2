import argparse
import json

from flask import Flask

from adventour_backend.models import db, Friendship, User
from adventour_backend.services.itinerary_service import ItineraryRecommendationService
from adventour_backend.services.travel_logistics_service import TravelLogisticsService
from adventour_backend.services.recommender_evaluation_service import RecommendationEvaluationService
from adventour_backend.services.recommender_service import RecommendationService, SCORING_PROFILES


class MockProviderRegistry:
    def __init__(self, candidates):
        self.candidates = candidates

    def search(self, tags, location, radius_meters=3200, constraints=None):
        return self.candidates, []


def candidate(name, place_id, types, rating, ratings_total, lat=37.422, lng=-122.084, price_level=2):
    return {
        "provider": "lab",
        "place_id": place_id,
        "name": name,
        "types": types,
        "rating": rating,
        "user_ratings_total": ratings_total,
        "price_level": price_level,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "business_status": "OPERATIONAL",
    }


SCENARIOS = {
    "local_food": {
        "users": [
            {"email": "local@example.com", "preferences": ["restaurant", "cafe"]},
        ],
        "candidates": [
            candidate("Starbucks", "chain-1", ["cafe", "restaurant"], 4.7, 5000),
            candidate("Maya's Corner Cafe", "gem-1", ["cafe", "restaurant"], 4.8, 42),
            candidate("Tourist Pier Grill", "tourist-1", ["restaurant"], 4.4, 9000),
            candidate("Quiet Sculpture Garden", "garden-1", ["park", "tourist_attraction"], 4.8, 40),
        ],
    },
    "group_blend": {
        "users": [
            {"email": "food@example.com", "preferences": ["restaurant", "cafe"]},
            {"email": "art@example.com", "preferences": ["museum", "art_gallery"]},
        ],
        "candidates": [
            candidate("Cafe Gallery", "balanced-1", ["cafe", "art_gallery"], 4.7, 75),
            candidate("Only Burgers", "food-only-1", ["restaurant"], 4.9, 80),
            candidate("Only Museum", "art-only-1", ["museum"], 4.9, 80),
            candidate("Museum Cafe Chain", "chain-2", ["museum", "cafe"], 4.5, 2000),
        ],
    },
    "budget": {
        "users": [
            {"email": "budget@example.com", "preferences": ["restaurant"]},
        ],
        "constraints": {"limit": 10, "avoid_chains": True, "price_max": 2},
        "candidates": [
            candidate("Affordable Noodles", "cheap-1", ["restaurant"], 4.5, 60, price_level=1),
            candidate("Expensive Tasting Room", "expensive-1", ["restaurant"], 4.8, 50, price_level=4),
            candidate("Local Bakery", "bakery-1", ["bakery", "cafe"], 4.7, 30, price_level=1),
        ],
    },
    "planned_city": {
        "users": [
            {"email": "planner-food@example.com", "preferences": ["restaurant", "cafe", "market"]},
            {"email": "planner-art@example.com", "preferences": ["museum", "art_gallery", "performing_arts_theater"]},
        ],
        "days": 1,
        "constraints": {"limit": 20, "avoid_chains": True, "pace": "balanced"},
        "candidates": [
            candidate("Corner Coffee", "coffee-1", ["cafe", "coffee_shop"], 4.7, 80, price_level=1),
            candidate("Sunrise Bakery", "bakery-1", ["bakery", "cafe"], 4.8, 65, price_level=1),
            candidate("City Art Walk", "art-1", ["art_gallery"], 4.8, 55, price_level=1),
            candidate("Neighborhood Museum", "museum-1", ["museum"], 4.6, 120, price_level=2),
            candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], 4.7, 45, price_level=1),
            candidate("Garden Market", "market-1", ["market", "tourist_attraction"], 4.6, 70, price_level=1),
            candidate("Indie Theater", "theater-1", ["performing_arts_theater"], 4.7, 95, price_level=3),
            candidate("Late Night Jazz", "jazz-1", ["bar", "concert_hall"], 4.6, 40, price_level=2),
        ],
    },
}


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def create_user(email, preferences):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"lab-{username}",
        email=email,
        username=username,
        display_name=username,
        preferences=",".join(preferences),
    )
    db.session.add(user)
    db.session.commit()
    return user


def make_lab_friends(users):
    for friend in users[1:]:
        db.session.add(Friendship(user_id=users[0].id, friend_id=friend.id, status="accepted"))
    db.session.commit()


def run_scenario(name, scoring_profile=None, planned=False):
    scenario = SCENARIOS[name]
    app = create_app()

    with app.app_context():
        db.create_all()
        users = [create_user(item["email"], item["preferences"]) for item in scenario["users"]]
        if len(users) > 1:
            make_lab_friends(users)
        recommendation_service = RecommendationService(MockProviderRegistry(scenario["candidates"]))
        constraints = dict(scenario.get("constraints", {"limit": 10, "avoid_chains": True}))
        if scoring_profile:
            constraints["scoring_profile"] = scoring_profile
        if planned:
            service = ItineraryRecommendationService(
                recommendation_service,
                local_event_service=None,
                travel_logistics_service=TravelLogisticsService(),
            )
            return service.recommend_itinerary(
                user=users[0],
                member_ids=[user.id for user in users[1:]],
                location={"latitude": 37.421998333333335, "longitude": -122.084},
                radius_meters=3200,
                constraints=constraints,
                party_size=len(users),
                days=scenario.get("days", 1),
                destination_label="Lab City",
            )

        service = recommendation_service
        result = service.recommend(
            user=users[0],
            member_ids=[user.id for user in users[1:]],
            location={"latitude": 37.421998333333335, "longitude": -122.084},
            radius_meters=3200,
            constraints=constraints,
        )
        return result


def print_result(name, result):
    print(f"\nScenario: {name}")
    print(f"Scoring profile: {result.get('scoring_profile')}")
    print(f"Query tags: {', '.join(result['query_tags'])}")
    print(f"Members: {result['member_count']}")
    print("")

    for index, item in enumerate(result["recommendations"], start=1):
        components = item["components"]
        print(f"{index}. {item['name']} | score={item['score']} | distance={item['distance_meters']}m")
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


def print_itinerary_result(name, result):
    readiness = result.get("route_readiness") or {}
    print(f"\nScenario: {name} planned route")
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

    for day in result.get("days", []):
        print(f"\n{day['title']}")
        print(f"  {day['summary']}")
        party_fit = day.get("party_fit") or {}
        if party_fit.get("message"):
            print(f"  party fit: {party_fit['message']}")
        for index, stop in enumerate(day.get("stops", []), start=1):
            recommendation = stop["recommendation"]
            print(
                f"  {index}. {stop['time_window']} | {stop['label']} | "
                f"{recommendation['name']} | score={recommendation.get('score')}"
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


def print_profile_comparison(name, planned=False):
    print(f"\nProfile comparison for {name}{' planned route' if planned else ''}")
    print("profile | scenario readiness | route readiness | stops | top pick")
    print("-" * 86)
    for profile_name in sorted(SCORING_PROFILES):
        result = run_scenario(name, scoring_profile=profile_name, planned=planned)
        scenario_readiness = RecommendationEvaluationService().scenario_readiness_report(result)
        if planned:
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


def main():
    parser = argparse.ArgumentParser(description="Run deterministic Adventour recommender scenarios.")
    parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS), default="local_food")
    parser.add_argument("--scoring-profile", choices=sorted(SCORING_PROFILES), help="Named recommender profile to test.")
    parser.add_argument("--planned", action="store_true", help="Build a planned itinerary route instead of a recommendation basket.")
    parser.add_argument("--all-profiles", action="store_true", help="Compare all named scoring profiles for the selected scenario.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a readable report.")
    args = parser.parse_args()

    if args.all_profiles:
        print_profile_comparison(args.scenario, planned=args.planned)
        return

    result = run_scenario(args.scenario, scoring_profile=args.scoring_profile, planned=args.planned)
    if args.json:
        print(json.dumps({
            **result,
            "scenario_readiness": RecommendationEvaluationService().scenario_readiness_report(result),
        }, indent=2))
    elif args.planned:
        print_itinerary_result(args.scenario, result)
    else:
        print_result(args.scenario, result)


if __name__ == "__main__":
    main()
