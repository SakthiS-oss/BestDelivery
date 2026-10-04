---
name: explain-route
description: Write a grounded plain-English explanation for each Chokepoint route and one recommendation paragraph. Use when explaining a RouteResult, editing the explanation prompt, or checking that an explanation cites only the provided cities, scores, events, headlines, and hours.
license: MIT
compatibility: Python 3.11 or newer. Local Ollama or an OpenAI-compatible cloud endpoint. The model must be open-weight (Llama 3.2 locally, Llama 3.1 8B on the cloud endpoint).
metadata:
  open-weight-model: meta-llama/Llama-3.1-8B-Instruct
  ollama-model: llama3.2
  cloud-api: openai-compatible
---

# Explain a route

Explain scored routes from structured facts only. The runtime is `backend/explain.py`. It loads the model instructions from [assets/instructions.md](assets/instructions.md), appends the facts JSON, and checks the reply.

## Model

Use an open-weight model.

- Local: Ollama, `OLLAMA_MODEL` (default `llama3.2`), temperature 0.
- Cloud: `EXPLAIN_PROVIDER=cloud` and an OpenAI-compatible `CLOUD_MODEL_BASE_URL`. Default model `meta-llama/Llama-3.1-8B-Instruct`.

Do not point this skill at a closed model.

## Steps

1. Build facts from each `RouteResult`: route id, city names, rounded scores, event names, headlines, and hours.
2. Send [assets/instructions.md](assets/instructions.md) plus that JSON. Do not send article text, coordinates, or other fields.
3. Validate the reply. Every catalog city name and every number in the prose must appear in the facts.
4. If validation fails, retry once with the same facts. If it fails again, or the model is unreachable, use the templated explanation in `backend/explain.py`.
5. Return the explanations and the recommendation on `POST /plan`. The plan body is one JSON document, so the prose is not streamed separately.

## Files

- [assets/instructions.md](assets/instructions.md) — the only instructions the model sees
- `backend/explain.py` — prompt, validator, retry, template, and model clients
- `backend/tests/test_explain.py` — fake model tests
