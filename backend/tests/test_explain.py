"""Explanation prompt, validator, retry, and template. The model is fake."""

import json

import pytest

from app.domain.models import City
from explain import (
    build_prompt,
    explain_routes,
    validation_problems,
)
from scoring import CityRisk, RouteResult

GROUNDED = {
    "routes": [
        {
            "id": "route-1",
            "explanation": (
                "route-1 passes through Dallas and Houston. "
                "Drive time is 10.5 hours, with a possible delay of 2 hours, "
                "for 12.5 hours total. Hazard risk is 0.4 and news risk is 0.2. "
                "The deadline margin is 8 hours, so the deadline may still hold. "
                "Elevated risk is possible near Houston bayou flood. "
                'A related headline is "Houston port strike vote".'
            ),
        }
    ],
    "recommendation": (
        "route-1 has the lowest total score at 14.5. "
        "It is a reasonable choice, with possible delay if conditions worsen."
    ),
}


def test_prompt_contains_only_instructions_and_facts() -> None:
    prompt = build_prompt(_facts())
    assert "Use only the provided facts." in prompt
    assert 'never claim a disruption will definitely happen' in prompt
    assert '"cities"' in prompt
    assert "Dallas" in prompt
    assert "Houston bayou flood" in prompt
    assert "Houston port strike vote" in prompt
    assert "Memphis" not in prompt
    assert "article text" not in prompt.casefold()


def test_fake_model_is_accepted_on_the_first_try() -> None:
    calls = {"n": 0}

    def generate(prompt: str) -> str:
        calls["n"] += 1
        assert "Dallas" in prompt
        return json.dumps(GROUNDED)

    result = explain_routes([_route()], generate=generate)
    assert calls["n"] == 1
    assert result.source == "model"
    assert result.routes[0].explanation.startswith("route-1 passes through Dallas")
    assert validation_problems(result.routes[0].explanation + result.recommendation, _facts()) == []


def test_invalid_reply_retries_once_then_keeps_the_correction() -> None:
    calls = {"n": 0}

    def generate(_prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "routes": [
                        {
                            "id": "route-1",
                            "explanation": "Memphis will flood and add 99 hours.",
                        }
                    ],
                    "recommendation": "Take Memphis.",
                }
            )
        return json.dumps(GROUNDED)

    result = explain_routes([_route()], generate=generate)
    assert calls["n"] == 2
    assert result.source == "model"
    assert "Memphis" not in result.recommendation


def test_second_failure_uses_the_template() -> None:
    calls = {"n": 0}

    def generate(_prompt: str) -> str:
        calls["n"] += 1
        return "not json"

    result = explain_routes([_route()], generate=generate)
    assert calls["n"] == 2
    assert result.source == "template"
    assert "possible delay" in result.routes[0].explanation
    assert "Elevated risk" in result.routes[0].explanation
    assert validation_problems(
        "\n".join(item.explanation for item in result.routes) + "\n" + result.recommendation,
        _facts(),
    ) == []


def test_model_outage_uses_the_template_without_a_retry() -> None:
    calls = {"n": 0}

    def generate(_prompt: str) -> str:
        calls["n"] += 1
        raise RuntimeError("connection refused")

    result = explain_routes([_route()], generate=generate)
    assert calls["n"] == 1
    assert result.source == "template"


def test_validator_rejects_unknown_cities_and_numbers() -> None:
    problems = validation_problems("Memphis adds 99 hours near Dallas.", _facts())
    assert "city not in input: Memphis" in problems
    assert "number not in input: 99" in problems


def _facts() -> dict[str, object]:
    from explain import build_facts

    return build_facts([_route()])


def _route() -> RouteResult:
    dallas = City(id="dallas-tx", name="Dallas", state="TX", lat=32.78, lon=-96.8)
    houston = City(id="houston-tx", name="Houston", state="TX", lat=29.76, lon=-95.37)
    return RouteResult(
        id="route-1",
        cities=[dallas, houston],
        city_risks=[
            CityRisk(
                city_id=dallas.id,
                name=dallas.name,
                state=dallas.state,
                hazard_risk=0.4,
                news_risk=0.2,
                factors=[],
                events=["Houston bayou flood"],
                headlines=["Houston port strike vote"],
            ),
            CityRisk(
                city_id=houston.id,
                name=houston.name,
                state=houston.state,
                hazard_risk=0.4,
                news_risk=0.2,
                factors=[],
            ),
        ],
        edge_risks=[],
        drive_hours=10.5,
        hazard_risk_max=0.4,
        hazard_risk_avg=0.4,
        news_risk_max=0.2,
        news_risk_avg=0.2,
        delay_hours_estimate=2,
        total_hours=12.5,
        total_score=14.5,
        meets_deadline=True,
        deadline_margin_hours=8,
        extra_drive_hours=1,
        note="",
    )
