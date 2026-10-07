"""Small shared JSON client for the selected inference provider and model."""

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from transcripts.inference import PROVIDERS, inference_api_key, resolve_inference
from transcripts.config import get_kimi_code_api_key


class LLMError(RuntimeError):
    """An LLM request failed or did not return a JSON object."""


def request_json(
    system_prompt: str, user_prompt: str, api_key: Optional[str] = None,
    *, provider: Optional[str] = None, model: Optional[str] = None
) -> Dict[str, Any]:
    """Request one JSON object, without exposing credentials in failures."""
    try:
        selection = resolve_inference(provider, model)
        config = PROVIDERS[selection.provider]
        label = config["label"]
        key = get_kimi_code_api_key(api_key) if selection.provider == "kimi" else inference_api_key(selection, api_key)
    except ValueError as exc:
        raise LLMError(str(exc)) from exc

    payload = json.dumps({
        "model": selection.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 1,
        "max_tokens": 16384,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{config['base_url']}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "transcripts/0.1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").replace(key, "[redacted]")[:2000]
        raise LLMError(f"{label} API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Network error: {exc.reason}") from exc
    except (OSError, ValueError, UnicodeError) as exc:
        raise LLMError(f"{label} request failed: {exc}") from exc

    try:
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError(f"{label} response exceeded its output limit; try a shorter transcript.")
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty response content")
        content = content.strip()
        fence = re.fullmatch(r"```(?:json)?\s*\n?([\s\S]*?)\s*```", content, re.IGNORECASE)
        if fence:
            content = fence.group(1)
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("response must be a JSON object")
        return result
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f"Failed to parse {label} JSON response: {exc}") from exc
