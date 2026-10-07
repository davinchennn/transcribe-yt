"""Provider model discovery with a credential-isolated, process-local cache."""

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

CATALOG_TTL_SECONDS = 15 * 60
FAILURE_RETRY_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 10
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
FIREWORKS_CATALOG_URL = "https://api.fireworks.ai/v1/accounts/fireworks/models"


class _CatalogError(Exception):
    """An intentionally safe error message, without upstream response details."""


@dataclass
class _CacheEntry:
    condition: threading.Condition = field(default_factory=threading.Condition)
    refreshing: bool = False
    models: Optional[list] = None
    updated_at: Optional[str] = None
    expires_at: float = 0
    retry_after: float = 0
    error: Optional[str] = None


_cache: Dict[Tuple[str, str, str], _CacheEntry] = {}
_cache_lock = threading.Lock()


def _snapshot(entry: _CacheEntry) -> dict:
    return {
        "models": [dict(model) for model in entry.models or []],
        "catalog_status": "stale" if entry.error and entry.models is not None else
                          "error" if entry.error else "ready",
        "catalog_updated_at": entry.updated_at,
        "catalog_error": entry.error,
    }


def model_catalog(provider: str, api_key: Optional[str], base_url: str, *, force_refresh: bool = False) -> dict:
    """Discover available models, keeping the last complete catalog on failure.

    Calls sharing an endpoint and credential reuse the catalog for 15 minutes.
    Concurrent refreshes join the existing request, including forced refreshes.
    A failed automatic refresh waits 30 seconds before retrying; a manual refresh
    can retry immediately. Keys are never stored in the cache or error messages.
    """
    key = (api_key or "").strip()
    if not key or key == "your_api_key_here":
        return {"models": [], "catalog_status": "unconfigured",
                "catalog_updated_at": None, "catalog_error": None}
    endpoint = base_url.rstrip("/") + "/models" if provider == "kimi" else FIREWORKS_CATALOG_URL
    identity = (provider, endpoint, hashlib.sha256(key.encode()).hexdigest())
    with _cache_lock:
        entry = _cache.setdefault(identity, _CacheEntry())
    with entry.condition:
        if entry.refreshing:
            entry.condition.wait_for(lambda: not entry.refreshing)
            return _snapshot(entry)
        now = time.monotonic()
        if not force_refresh and (now < entry.retry_after or
                                  (entry.error is None and entry.models is not None and now < entry.expires_at)):
            return _snapshot(entry)
        entry.refreshing = True

    try:
        models = _fetch_models(provider, key, endpoint)
    except Exception as error:
        if isinstance(error, urllib.error.HTTPError):
            error.close()
        with entry.condition:
            entry.error = _safe_error(error)
            entry.retry_after = time.monotonic() + FAILURE_RETRY_SECONDS
    else:
        with entry.condition:
            entry.models = models
            entry.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            entry.expires_at = time.monotonic() + CATALOG_TTL_SECONDS
            entry.retry_after = 0
            entry.error = None
    finally:
        with entry.condition:
            entry.refreshing = False
            entry.condition.notify_all()
    with entry.condition:
        return _snapshot(entry)


def _safe_error(error: Exception) -> str:
    if isinstance(error, _CatalogError):
        return str(error)
    if isinstance(error, urllib.error.HTTPError):
        return f"Model catalog request failed (HTTP {error.code})."
    if isinstance(error, TimeoutError) or (isinstance(error, urllib.error.URLError) and
                                          isinstance(error.reason, TimeoutError)):
        return "Model catalog request timed out."
    if isinstance(error, urllib.error.URLError):
        return "Could not connect to the model catalog."
    if isinstance(error, (ValueError, UnicodeError)):
        return "The model catalog returned an invalid response."
    return "Could not load the model catalog."


def _request_json(url: str, api_key: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}",
                                                 "Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise _CatalogError("The model catalog response was too large.")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise _CatalogError("The model catalog returned an invalid response.")
    return payload


def _normalize_model(raw: dict, *, fireworks: bool) -> Optional[dict]:
    model_id = raw.get("name" if fireworks else "id")
    if not isinstance(model_id, str):
        return None
    model_id = model_id.strip()
    if not model_id or len(model_id) > 300 or any(char.isspace() for char in model_id):
        return None
    display_name = raw.get("displayName" if fireworks else "display_name")
    name = display_name.strip() if isinstance(display_name, str) and display_name.strip() else model_id
    context_length = raw.get("contextLength" if fireworks else "context_length")
    if type(context_length) is not int or context_length <= 0:
        context_length = None
    return {"id": model_id, "name": name, "context_length": context_length}


def _fireworks_chat_model(raw: dict) -> bool:
    # GetModel documents conversationConfig as enabling Chat Completions and
    # supportsServerless as having a serverless deployment. Avoid assuming that
    # every uploaded model, or every serverless model, is usable for analysis.
    if raw.get("state") != "READY" or raw.get("supportsServerless") is not True:
        return False
    if not isinstance(raw.get("conversationConfig"), dict):
        return False
    details = raw.get("baseModelDetails")
    model_type = details.get("modelType", "") if isinstance(details, dict) else ""
    metadata = " ".join(value for value in (raw.get("kind"), raw.get("name"), model_type)
                        if isinstance(value, str)).lower()
    if "whisper" in metadata:
        return False
    tokens = set(re.split(r"[^a-z0-9]+", metadata))
    return not tokens.intersection({"embed", "embedding", "embeddings", "rerank", "reranker",
                                    "reranking", "audio", "speech", "tts", "asr"})


def _fetch_models(provider: str, api_key: str, endpoint: str) -> List[dict]:
    models = {}
    if provider == "kimi":
        payload = _request_json(endpoint, api_key)
        records = payload.get("data")
        if not isinstance(records, list):
            raise _CatalogError("The model catalog returned an invalid response.")
        for raw in records:
            if isinstance(raw, dict) and (model := _normalize_model(raw, fireworks=False)):
                models.setdefault(model["id"], model)
    elif provider == "fireworks":
        token = ""
        seen_tokens = set()
        for _ in range(MAX_PAGES):
            query = {"pageSize": 200}
            if token:
                query["pageToken"] = token
            payload = _request_json(endpoint + "?" + urllib.parse.urlencode(query), api_key)
            records = payload.get("models")
            if not isinstance(records, list):
                raise _CatalogError("The model catalog returned an invalid response.")
            for raw in records:
                if isinstance(raw, dict) and _fireworks_chat_model(raw):
                    model = _normalize_model(raw, fireworks=True)
                    if model:
                        models.setdefault(model["id"], model)
            token = payload.get("nextPageToken", "")
            if not isinstance(token, str):
                raise _CatalogError("The model catalog returned an invalid response.")
            if not token:
                break
            if token in seen_tokens:
                raise _CatalogError("The model catalog returned repeated pagination tokens.")
            seen_tokens.add(token)
        else:
            raise _CatalogError("The model catalog exceeded the pagination limit.")
    else:
        raise _CatalogError("This provider does not support model discovery.")
    return sorted(models.values(), key=lambda model: (model["name"].casefold(), model["id"]))
