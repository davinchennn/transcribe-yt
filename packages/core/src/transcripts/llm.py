"""Small shared JSON client for the configured Kimi Code model."""

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from transcripts.analyzer import KIMI_BASE_URL, KIMI_MODEL
from transcripts.config import get_kimi_code_api_key


class LLMError(RuntimeError):
    """An LLM request failed or did not return a JSON object."""


def request_json(
    system_prompt: str, user_prompt: str, api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Request one JSON object, without exposing credentials in failures."""
    try:
        key = get_kimi_code_api_key(api_key)
    except ValueError as exc:
        raise LLMError(str(exc)) from exc

    payload = json.dumps({
        "model": KIMI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 1,
        "max_tokens": 16384,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{KIMI_BASE_URL}/chat/completions",
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
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        raise LLMError(f"Kimi API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Network error: {exc.reason}") from exc
    except (OSError, ValueError, UnicodeError) as exc:
        raise LLMError(f"Kimi request failed: {exc}") from exc

    try:
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError("Kimi response exceeded its output limit; try a shorter transcript.")
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
        raise LLMError(f"Failed to parse Kimi JSON response: {exc}") from exc
