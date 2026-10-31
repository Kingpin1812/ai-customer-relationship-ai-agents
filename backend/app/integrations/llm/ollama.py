from typing import Protocol

import httpx


class LlmUnavailable(Exception):
    pass


class LlmClient(Protocol):
    """Swap in a hosted provider by implementing this one method."""

    def generate_json(self, system: str, user: str, schema: dict) -> str: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def generate_json(self, system: str, user: str, schema: dict) -> str:
        try:
            response = self.http.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "options": {"temperature": 0},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LlmUnavailable(type(exc).__name__) from exc
