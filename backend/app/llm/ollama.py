"""HTTP client for a local Ollama server."""


def generate(prompt: str, *, base_url: str, model: str) -> str:
    """POST /api/generate and return the model text."""
    raise NotImplementedError
