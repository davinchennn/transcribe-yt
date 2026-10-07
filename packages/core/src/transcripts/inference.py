"""Provider configuration and request-local selection for analysis workflows."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from transcripts import config as app_config
from transcripts.model_catalog import model_catalog

KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_MODEL = "k3"
PROVIDERS = {
    "kimi": {"label": "Kimi Code", "base_url": KIMI_BASE_URL,
             "key_env": "KIMI_CODE_API_KEY", "model_env": "KIMI_MODEL", "default_model": KIMI_MODEL},
    "fireworks": {"label": "Fireworks AI", "base_url": "https://api.fireworks.ai/inference/v1",
                  "key_env": "FIREWORKS_API_KEY", "model_env": "FIREWORKS_MODEL",
                  "default_model": "accounts/fireworks/models/kimi-k3"},
}


@dataclass(frozen=True)
class InferenceSelection:
    provider: str
    model: str


_selection: ContextVar[Optional[InferenceSelection]] = ContextVar("inference_selection", default=None)


def resolve_inference(provider: Optional[str] = None, model: Optional[str] = None) -> InferenceSelection:
    app_config.load_config()
    current = _selection.get()
    provider = (provider or (current.provider if current else os.getenv("ANALYSIS_PROVIDER", "kimi"))).strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("Analysis provider must be 'kimi' or 'fireworks'")
    config = PROVIDERS[provider]
    if model is None:
        model = current.model if current and current.provider == provider else os.getenv(config["model_env"], config["default_model"])
    model = model.strip()
    if not model or len(model) > 300 or any(char.isspace() for char in model):
        raise ValueError("Enter a model ID of at most 300 characters without whitespace")
    return InferenceSelection(provider, model)


def inference_api_key(selection: InferenceSelection, api_key: Optional[str] = None) -> str:
    app_config.load_config()
    config = PROVIDERS[selection.provider]
    key = api_key or os.getenv(config["key_env"])
    if not key or key == "your_api_key_here":
        raise ValueError(f"{config['label']} API key not found. Set {config['key_env']} environment variable or create a .env file.")
    return key


@contextmanager
def inference_scope(selection: InferenceSelection):
    """Keep every chunk/repair call on the same selection, isolated across requests."""
    token = _selection.set(selection)
    try:
        yield
    finally:
        _selection.reset(token)


def inference_options(*, force_refresh: bool = False):
    default = resolve_inference()
    providers = []
    for provider, config in PROVIDERS.items():
        selected = resolve_inference(provider)
        key = os.getenv(config["key_env"])
        providers.append({"id": provider, "label": config["label"],
                          "configured": bool(key and key.strip() and key.strip() != "your_api_key_here"),
                          "default_model": selected.model,
                          **model_catalog(provider, key, config["base_url"], force_refresh=force_refresh)})
    return {"default_provider": default.provider, "default_model": default.model, "providers": providers}
