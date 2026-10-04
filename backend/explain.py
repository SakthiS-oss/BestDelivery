"""Grounded route explanations from an open-weight model, with a template fallback.

The model instructions live in the explain-route skill
(`.agents/skills/explain-route/assets/instructions.md`), following the Agent
Skills layout. The prompt is that file plus a JSON object of cities, scores,
events, headlines, and hours. Nothing else is sent.

`EXPLAIN_PROVIDER=ollama` calls local Ollama (`OLLAMA_MODEL`, default
`llama3.2`). `EXPLAIN_PROVIDER=cloud` calls an OpenAI-compatible endpoint
(`CLOUD_MODEL_NAME`, default `meta-llama/Llama-3.1-8B-Instruct`). Both defaults
are open-weight Llama models.
"""

import csv
import json
import math
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from scoring import RouteResult
from snowflake_client import use_mock_data

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS_PATH = (
    REPO_ROOT / ".agents" / "skills" / "explain-route" / "assets" / "instructions.md"
)
CITIES_PATH = REPO_ROOT / "data" / "cities.csv"
RETRY_NOTE = (
    "The previous answer mentioned a city or number that is not in the input. "
    "Rewrite the JSON using only cities, events, headlines, and numbers from the input."
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_catalog_names: list[str] | None = None


class RouteExplanation(BaseModel):
    """Plain-English text for one route. No article body."""

    id: str
    explanation: str


class ExplanationResult(BaseModel):
    """Per-route prose, one recommendation, and whether the template was used."""

    routes: list[RouteExplanation]
    recommendation: str
    source: Literal["model", "template"]
    problems: list[str] = Field(default_factory=list)


def explain_routes(
    routes: list[RouteResult],
    *,
    generate: Callable[[str], str] | None = None,
) -> ExplanationResult:
    """Explain every route and recommend one. A failed check retries once."""
    facts = build_facts(routes)
    if generate is None and use_mock_data():
        return render_template(facts)
    generate = generate or default_generate
    prompt = build_prompt(facts)
    try:
        first = generate(prompt)
    except Exception:
        return render_template(facts)
    accepted = _accept(first, facts)
    if accepted is not None:
        return accepted
    try:
        second = generate(f"{prompt}\n\n{RETRY_NOTE}")
    except Exception:
        return render_template(facts)
    accepted = _accept(second, facts)
    if accepted is not None:
        return accepted
    fallback = render_template(facts)
    fallback.problems = validation_problems(_prose(fallback), facts)
    return fallback


def build_facts(routes: list[RouteResult]) -> dict[str, object]:
    """Cities, scores, events, headlines, and hours. Floats are rounded to 2 places."""
    payload: list[dict[str, object]] = []
    for route in routes:
        events: list[str] = []
        headlines: list[str] = []
        for city in route.city_risks:
            events.extend(city.events)
            headlines.extend(city.headlines)
        for edge in route.edge_risks:
            events.extend(edge.events)
        payload.append(
            {
                "id": route.id,
                "cities": [city.name for city in route.cities],
                "scores": {
                    "hazard_max": _num(route.hazard_risk_max),
                    "hazard_avg": _num(route.hazard_risk_avg),
                    "news_max": _num(route.news_risk_max),
                    "news_avg": _num(route.news_risk_avg),
                    "total": _num(route.total_score),
                },
                "events": _unique(events),
                "headlines": _unique(headlines),
                "hours": {
                    "drive": _num(route.drive_hours),
                    "delay": _num(route.delay_hours_estimate),
                    "total": _num(route.total_hours),
                    "deadline_margin": _num(route.deadline_margin_hours),
                    "extra_drive": _num(route.extra_drive_hours),
                },
                "meets_deadline": route.meets_deadline,
            }
        )
    return {"routes": payload}


def build_prompt(facts: dict[str, object]) -> str:
    """Skill instructions followed by the facts JSON."""
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8").rstrip()
    return f"{instructions}\n{json.dumps(facts, indent=2)}"


def validation_problems(text: str, facts: dict[str, object]) -> list[str]:
    """City names and numbers in the prose that are absent from the facts."""
    problems: list[str] = []
    allowed_cities = _cities_in_facts(facts)
    for name in _catalog_city_names():
        if _mentions(text, name) and name.casefold() not in allowed_cities:
            problems.append(f"city not in input: {name}")
    allowed_numbers = set(_NUMBER.findall(json.dumps(facts)))
    allowed_values = {float(token) for token in allowed_numbers}
    for token in _NUMBER.findall(text):
        if token in allowed_numbers:
            continue
        if any(math.isclose(float(token), value, abs_tol=1e-9) for value in allowed_values):
            continue
        problems.append(f"number not in input: {token}")
    return problems


def render_template(facts: dict[str, object]) -> ExplanationResult:
    """Explanation built only from the facts, using hedged wording."""
    routes = facts["routes"]
    if not isinstance(routes, list) or not routes:
        return ExplanationResult(
            routes=[],
            recommendation="No routes were provided, so no recommendation is available.",
            source="template",
        )
    explanations: list[RouteExplanation] = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        explanations.append(RouteExplanation(id=str(route["id"]), explanation=_route_sentence(route)))
    best = min(routes, key=lambda route: (float(route["scores"]["total"]), str(route["id"])))  # type: ignore[index]
    recommendation = (
        f"{best['id']} has the lowest total score at {best['scores']['total']}. "  # type: ignore[index]
        "It is a reasonable choice among the listed routes, with possible delay if conditions worsen."
    )
    result = ExplanationResult(routes=explanations, recommendation=recommendation, source="template")
    problems = validation_problems(_prose(result), facts)
    if problems:
        raise RuntimeError("template explanation is not grounded: " + "; ".join(problems))
    return result


def default_generate(prompt: str) -> str:
    """Call Ollama or the configured open-weight cloud model."""
    provider = os.environ.get("EXPLAIN_PROVIDER", "ollama").strip().lower()
    if provider == "cloud":
        return _cloud_generate(prompt)
    if provider == "ollama":
        return _ollama_generate(prompt)
    raise ValueError("EXPLAIN_PROVIDER must be ollama or cloud")


def _accept(text: str, facts: dict[str, object]) -> ExplanationResult | None:
    try:
        payload = _parse_json_object(text)
        raw_routes = payload["routes"]
        recommendation = payload["recommendation"]
        if not isinstance(raw_routes, list) or not isinstance(recommendation, str):
            return None
        explanations = [
            RouteExplanation(id=str(item["id"]), explanation=str(item["explanation"]))
            for item in raw_routes
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    expected = [str(route["id"]) for route in facts["routes"]]  # type: ignore[index, union-attr]
    if [item.id for item in explanations] != expected:
        return None
    result = ExplanationResult(routes=explanations, recommendation=recommendation.strip(), source="model")
    problems = validation_problems(_prose(result), facts)
    if problems:
        return None
    return result


def _route_sentence(route: dict[str, object]) -> str:
    hours = route["hours"]
    scores = route["scores"]
    assert isinstance(hours, dict)
    assert isinstance(scores, dict)
    cities = route["cities"] if isinstance(route["cities"], list) else []
    deadline = "the deadline may still hold" if route["meets_deadline"] else "the deadline may be missed"
    sentence = (
        f"{route['id']} passes through {_join_names([str(name) for name in cities])}. "
        f"Drive time is {hours['drive']} hours, with a possible delay of {hours['delay']} hours, "
        f"for {hours['total']} hours total. "
        f"Hazard risk is {scores['hazard_max']} and news risk is {scores['news_max']}. "
        f"The deadline margin is {hours['deadline_margin']} hours, so {deadline}."
    )
    events = route["events"] if isinstance(route["events"], list) else []
    headlines = route["headlines"] if isinstance(route["headlines"], list) else []
    if events:
        sentence += f" Elevated risk is possible near {events[0]}."
    if headlines:
        sentence += f" A related headline is \"{headlines[0]}\"."
    return sentence


def _join_names(names: list[str]) -> str:
    if not names:
        return "the listed stops"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _prose(result: ExplanationResult) -> str:
    parts = [item.explanation for item in result.routes]
    parts.append(result.recommendation)
    return "\n".join(parts)


def _cities_in_facts(facts: dict[str, object]) -> set[str]:
    encoded = json.dumps(facts).casefold()
    return {name.casefold() for name in _catalog_city_names() if _mentions(encoded, name)}


def _catalog_city_names() -> list[str]:
    global _catalog_names
    if _catalog_names is None:
        names: list[str] = []
        with CITIES_PATH.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                name = row["name"].strip()
                if name:
                    names.append(name)
        _catalog_names = sorted(names, key=len, reverse=True)
    return _catalog_names


def _mentions(text: str, name: str) -> bool:
    pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _ollama_generate(prompt: str) -> str:
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    response = httpx.post(
        f"{base}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
        timeout=120,
    )
    response.raise_for_status()
    text = response.json().get("response")
    if not isinstance(text, str):
        raise ValueError("Ollama returned no text")
    return text


def _cloud_generate(prompt: str) -> str:
    base = os.environ.get("CLOUD_MODEL_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("CLOUD_MODEL_BASE_URL is not set")
    model = os.environ.get("CLOUD_MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
    key = os.environ.get("CLOUD_MODEL_API_KEY", "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    response = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    if not isinstance(text, str):
        raise ValueError("cloud model returned no text")
    return text


def _parse_json_object(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value


def _num(value: float) -> int | float:
    rounded = round(float(value), 2)
    if math.isclose(rounded, round(rounded), abs_tol=1e-9):
        return int(round(rounded))
    return rounded


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for item in items:
        text = item.strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            labels.append(text)
    return labels
