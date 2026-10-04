# Chokepoint build plan

Status: step 0 is done. The next session implements step 1 only, then stops.

Each later step replaces `raise NotImplementedError` in the modules named there and adds tests for those functions. Leave the following steps untouched.

## Rules that stay in force

- Python computes every distance, hour, and score. The model receives a finished structure and writes prose that cites it.
- `USE_MOCK_DATA=true` serves disasters, news, and the explanation from local files and a template. The process can run with Snowflake and Ollama both absent.
- `POST /api/plan` returns each route's named factors: `name`, `value`, `unit`, `evidence_ids`.
- Snowflake access is one `SELECT`, with values bound by the connector. Table names come from settings, after an identifier check.
- `as_of` is required on the plan request and on every source, score, route-generation, and explanation call. Records later than `as_of` stay out, which is how a past day is replayed.
- Files stay small. One module, one job. Short docstrings.

Pure geometry (`haversine_miles`, `road_miles`, `drive_hours`) has no clock, so those three signatures omit `as_of`.

## Scoring contract

Constants live in settings (`AVG_SPEED_MPH`, `ROAD_FACTOR`, `HAZARD_WEIGHT_HOURS`, `NEWS_WEIGHT_HOURS`, `NEWS_LOOKBACK_DAYS`).

- Road miles ≈ great-circle miles × `road_factor`.
- `travel_hours` = total road miles / `avg_speed_mph`. Continuous driving; hours-of-service rules are out of scope.
- A hop is kept when road miles are between `min_hop_miles` and `max_hop_miles` (default 150 and 350). A start and end closer than the minimum still produce one direct hop.
- `hazard_risk` is in `[0, 1]`: sum, over disasters near the route, of `severity × proximity`, then cap at 1. Proximity is 1 at the city or hop and falls to 0 at 100 miles.
- `delay_hours` is the sum of `severity × 6 × proximity` for those same disasters.
- `news_risk` is in `[0, 1]`: average news `severity` for items tied to route cities with `published_at` in `(as_of - lookback, as_of]`, capped at 1. No items means 0.
- `eta` = `as_of + travel_hours + delay_hours`.
- `meets_deadline` is `eta <= deadline`.
- `deadline_slack_hours` = hours from `eta` to the deadline (negative when late).
- `travel_cost_hours` = `travel_hours`.
- `risk_cost_hours` = `delay_hours + hazard_weight_hours * hazard_risk + news_weight_hours * news_risk`.
- `total_cost_hours` = `travel_cost_hours + risk_cost_hours`.
- Rank ascending by `total_cost_hours`. Equal costs keep generation order.

The request carries exactly one of `deadline_at` or `deadline_days`. Day counts are measured from `as_of`. Timestamps are timezone-aware UTC.

## Replay and mock shapes

Disasters count when `start_time <= as_of` and (`end_time` is null or `end_time >= as_of`). News counts when `published_at <= as_of` and inside the lookback.

`data/mock/cities.csv` columns: `id,name,state,lat,lon`.

`data/mock/disasters.json` is an array of `DisasterEvent` objects. `data/mock/news.json` is an array of `NewsItem` objects. Times are ISO-8601 with a timezone.

## Explanations

`build_citations` lists the only cities, numbers, and record ids the prose may use.

Mock mode fills a short template from those citations. Live mode sends the citation JSON to Ollama (`OLLAMA_MODEL`, `OLLAMA_BASE_URL`) and then runs `assert_explanation_grounded`. A failed check is replaced by the same template, so a wandering model cannot change the numbers on screen.

## Modules

| Module | Job |
| --- | --- |
| `app/config.py` | `Settings` and `get_settings` |
| `app/domain/models.py` | Cities, routes, events, factors, scores, citations |
| `app/routing/distance.py` | Miles and drive hours |
| `app/routing/cities.py` | Load the catalog and resolve a typed city name |
| `app/routing/graph.py` | City graph inside the hop window |
| `app/routing/candidates.py` | Two or three paths for an `as_of` |
| `app/sources/mock_loader.py` | CSV and JSON readers |
| `app/sources/queries.py` | Parameterized `SELECT` text |
| `app/sources/snowflake_client.py` | Connect, reject non-`SELECT`, fetch bound rows |
| `app/sources/disasters.py` | Hazards inside a box at `as_of` |
| `app/sources/news.py` | News for the route cities at `as_of` |
| `app/scoring/factors.py` | Factor rows and `risk_cost_hours` |
| `app/scoring/deadline.py` | Deadline, ETA, slack |
| `app/scoring/risk.py` | Full `RouteScore` for one route |
| `app/scoring/rank.py` | Sort by `total_cost_hours` |
| `app/llm/ollama.py` | `POST /api/generate` |
| `app/llm/explain.py` | Citations, prose, grounding check |
| `app/pipeline.py` | `build_plan` |
| `app/api/schemas.py` | `PlanRequest`, `PlanResponse`, `HealthResponse` |
| `app/api/routes.py` | `GET /api/health`, `POST /api/plan` |
| `app/main.py` | FastAPI app, router mounted at `/api` |
| `frontend/src/api` | Wire types and the HTTP client |
| `frontend/src/components` | Form, list, Leaflet map, explanation |

## Steps

### 0. Skeleton

Done. Folders, docs, env example, Makefile, and importable stubs. Feature bodies still raise `NotImplementedError`. Mock data files are empty.

### 1. Settings loader

Implement `get_settings`. Resolve mock paths from the repo root, independent of the process working directory. Cache the result for the process.

Done when a test reads `.env.example` values, and a missing Snowflake password still loads while `use_mock_data` is true.

### 2. Distance

Implement `haversine_miles`, `road_miles`, and `drive_hours`.

Done when a known pair (for example Chicago to a point due east) matches a hand-computed mile value within a mile, and drive hours follow the configured speed.

### 3. City catalog

Fill `data/mock/cities.csv` with major US cities dense enough for 150–350 mile hops on the interstate network. Implement `load_cities` and `resolve_city` (case-insensitive `"City, ST"` and unique city name).

Done when `"Denver, CO"` and `"denver"` resolve, and an unknown or ambiguous name fails with a clear error.

### 4. Hop graph

Implement `build_graph`.

Done when every edge falls inside the mile window, short pairs are absent, and a few known mid-range pairs (on the order of Dallas–Oklahoma City) are present.

### 5. Candidate routes

Implement `generate_routes`. Search the graph for simple paths. After each path, raise the cost of its edges so the next path prefers a different corridor. Always pass `as_of` through the call. Allow one direct hop when the endpoints are closer than `min_hop_miles`.

Done when two different city pairs each yield 2–3 routes, every hop is inside the window (or is the short-haul exception), and the routes share less than the full path.

### 6. Mock loaders and sample rows

Implement `load_csv` and `load_json`. Add a handful of disaster and news rows to the mock files, including at least one event after a chosen `as_of` and one event before it. Implement `fetch_disasters` and `fetch_news` for the mock branch, including the bounding box, state list, and lookback.

Done when a fixture `as_of` keeps the earlier event, drops the later one, and ignores a disaster outside the box.

### 7. Scores, deadline, rank

Implement `factors`, `deadline`, `risk`, and `rank` to the formula above. Attach `evidence_ids` (event ids, article ids, or hop ids) on each factor.

Done when a fixture route reproduces hand-computed factor values, a late ETA sets `meets_deadline` false, and rank order follows `total_cost_hours`.

### 8. Mock explanations

Implement `build_citations`, the template branch of `explain_route`, and `assert_explanation_grounded`. The template mentions the deadline flag, the largest risk factor, and the cited record ids. Numbers in the sentences are copied from the score.

Done when the template passes the grounding check, and a sentence with an extra city or an extra digit fails it.

### 9. Pipeline

Implement `build_plan`: resolve cities, generate routes, fetch events once for the combined corridor, score, explain, rank.

Done when one fixture request returns 2–3 `ExplainedRoute` rows ordered by total cost, with `as_of` echoed on the response.

### 10. HTTP API

Implement `health` and `plan`. Validate that exactly one deadline field is set and that datetimes are timezone-aware. Map unknown cities and empty route sets to HTTP 400 with a short message.

Done when `TestClient` covers health, a happy-path plan, a missing city, and a naive `as_of`.

### 11. Snowflake

Implement `assert_select_only`, `connect`, `fetch_all`, `disasters_sql`, and `news_sql`. Wire them into the existing fetch functions when `use_mock_data` is false. Bind `as_of`, the box, states, and the lookback. Confirm the SQL text contains a single `SELECT` and the bound names.

Done when a unit test rejects `INSERT`/`UPDATE`/`DELETE` and a second test shows the mock branch still runs with Snowflake unconfigured. A live query runs only if credentials are present; skip it otherwise.

### 12. Ollama

Implement `generate`. When mock mode is off, `explain_route` calls Ollama with the citation JSON and keeps the reply only after `assert_explanation_grounded`. Otherwise it uses the step 8 template.

Done when a fake HTTP response that adds a new number is discarded for the template, and a grounded fake response is kept.

### 13. Frontend

Implement the client, form, ranked list, factor table, deadline badge, explanation, and a Leaflet map of the selected route. The form collects start, end, deadline (timestamp or day count), and `as_of`. Colors on the map follow `total_cost_hours`.

Done when a mock-backend plan can be submitted in the browser, the three routes render, selecting one updates the map and the explanation, and a deadline miss is visible on the card.

### 14. Mock walkthrough

Run backend and frontend with `USE_MOCK_DATA=true`. Submit one corridor and one `as_of` that cuts a disaster out of the window, then the same corridor with an earlier `as_of` that includes it. Confirm the factor values and the deadline flag change in the way the fixtures predict.

Done when that pair of replays is written up in a short note at the bottom of this file.
