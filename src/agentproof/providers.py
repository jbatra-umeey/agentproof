import asyncio
import json
import time
import httpx
from pydantic import ValidationError


class ProviderError(RuntimeError):
    pass


class TransientProviderError(ProviderError):
    pass


class Model:
    """OpenAI-compatible Chat Completions; no simulated fallback in the application."""

    def __init__(self, settings):
        self.settings = settings
        self.slots = asyncio.Semaphore(4)

    async def complete(self, system, data, schema):
        s = self.settings
        if not s.llm_key or not s.llm_model:
            raise ProviderError("Configure LLM_API_KEY and LLM_MODEL")
        prompt = (
            system
            + "\nReturn only a JSON object matching this schema:\n"
            + json.dumps(schema.model_json_schema())
        )
        start = time.perf_counter()
        async with self.slots, httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            try:
                response = await client.post(
                    s.llm_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + s.llm_key},
                    json={
                        "model": s.llm_model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": json.dumps(data)},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_tokens": 2000,
                    },
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise TransientProviderError(type(exc).__name__) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientProviderError("ProviderTemporarilyUnavailable")
        if response.status_code != 200:
            raise ProviderError("ProviderRequestRejected")
        try:
            body = response.json()
            result = schema.model_validate_json(body["choices"][0]["message"]["content"])
            usage = body.get("usage") or {}
            input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
            cost = None
            if (
                input_tokens is not None
                and output_tokens is not None
                and s.input_price is not None
                and s.output_price is not None
            ):
                cost = (input_tokens * s.input_price + output_tokens * s.output_price) / 1_000_000
            return result.model_dump(), {
                "provider": "live",
                "model": s.llm_model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_usd": cost,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ProviderError("InvalidStructuredModelResponse") from exc


class Search:
    def __init__(self, key):
        self.key = key

    async def search(self, query):
        if not self.key:
            raise ProviderError("Configure TAVILY_API_KEY")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            try:
                r = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": "Bearer " + self.key},
                    json={
                        "query": query,
                        "max_results": 5,
                        "include_raw_content": False,
                    },
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise TransientProviderError(type(exc).__name__) from exc
        if r.status_code == 429 or r.status_code >= 500:
            raise TransientProviderError("SearchTemporarilyUnavailable")
        if r.status_code != 200:
            raise ProviderError("SearchRequestRejected")
        results = r.json().get("results", [])
        # Search snippets are evidence, not instructions. URLs are never fetched by our backend.
        return [
            {
                "url": str(x["url"])[:2000],
                "title": str(x.get("title", ""))[:300],
                "content": str(x.get("content", ""))[:6000],
            }
            for x in results[:5]
        ]
