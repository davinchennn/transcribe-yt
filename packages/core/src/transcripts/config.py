"""Configuration management for transcripts package."""

import os
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv


def load_config() -> None:
    """Load environment variables from .env file."""
    # Walk up from config.py to find .env at project root
    # packages/core/src/transcripts/config.py -> project root (5 levels up)
    env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)


def get_api_key(api_key: Optional[str] = None) -> str:
    """
    Get AssemblyAI API key from parameter, environment variable, or .env file.

    Args:
        api_key: Optional API key to use directly

    Returns:
        AssemblyAI API key

    Raises:
        ValueError: If API key is not found
    """
    load_config()

    if api_key:
        return api_key

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError(
            "AssemblyAI API key not found. "
            "Set ASSEMBLYAI_API_KEY environment variable or create a .env file."
        )

    return api_key


def get_deepgram_api_key(api_key: Optional[str] = None) -> str:
    """
    Get Deepgram API key from parameter, environment variable, or .env file.

    Args:
        api_key: Optional API key to use directly

    Returns:
        Deepgram API key

    Raises:
        ValueError: If API key is not found
    """
    load_config()

    if api_key:
        return api_key

    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError(
            "Deepgram API key not found. "
            "Set DEEPGRAM_API_KEY environment variable or create a .env file."
        )

    return api_key


def get_transcription_provider(provider: Optional[str] = None) -> Literal["assemblyai", "deepgram"]:
    """
    Get transcription provider from parameter, environment variable, or .env file.
    
    Priority:
    1. Explicit parameter
    2. TRANSCRIPTION_PROVIDER environment variable
    3. Default to "deepgram"
    
    Args:
        provider: Optional provider name to use directly ("assemblyai" or "deepgram")
    
    Returns:
        Transcription provider name ("assemblyai" or "deepgram")
    """
    load_config()
    
    if provider:
        provider = provider.lower()
        if provider not in ("assemblyai", "deepgram"):
            raise ValueError(
                f"Invalid provider: {provider}. Must be 'assemblyai' or 'deepgram'"
            )
        return provider
    
    env_provider = os.getenv("TRANSCRIPTION_PROVIDER")
    if env_provider:
        env_provider = env_provider.lower()
        if env_provider not in ("assemblyai", "deepgram"):
            raise ValueError(
                f"Invalid TRANSCRIPTION_PROVIDER: {env_provider}. "
                "Must be 'assemblyai' or 'deepgram'"
            )
        return env_provider
    
    # Default to deepgram
    return "deepgram"


def get_storage_backend(backend: Optional[str] = None) -> Literal["sqlite", "json"]:
    """
    Get storage backend from parameter, environment variable, or default.

    Priority:
    1. Explicit parameter
    2. STORAGE_BACKEND environment variable
    3. Default to "sqlite"

    Args:
        backend: Optional backend name ("sqlite" or "json")

    Returns:
        Storage backend name ("sqlite" or "json")
    """
    load_config()

    if backend:
        backend = backend.lower()
        if backend not in ("sqlite", "json"):
            raise ValueError(
                f"Invalid storage backend: {backend}. Must be 'sqlite' or 'json'"
            )
        return backend

    env_backend = os.getenv("STORAGE_BACKEND")
    if env_backend:
        env_backend = env_backend.lower()
        if env_backend not in ("sqlite", "json"):
            raise ValueError(
                f"Invalid STORAGE_BACKEND: {env_backend}. "
                "Must be 'sqlite' or 'json'"
            )
        return env_backend

    # Default to sqlite
    return "sqlite"


def get_storage_path(backend: Optional[str] = None, *, create_directory: bool = True) -> str:
    """
    Get storage file path based on backend type.

    Priority:
    1. STORAGE_PATH environment variable (if set)
    2. Default path based on backend type (in data/ folder)

    Args:
        backend: Storage backend type ("sqlite" or "json")
        create_directory: Create the default data directory for normal storage use.
            Set to False for read-only discovery.

    Returns:
        Path to storage file
    """
    load_config()

    # Check for custom path
    custom_path = os.getenv("STORAGE_PATH")
    if custom_path:
        return custom_path

    # Determine backend if not provided
    if backend is None:
        backend = get_storage_backend()

    data_dir = Path("data")
    if create_directory:
        data_dir.mkdir(exist_ok=True)

    # Return default path based on backend
    if backend == "json":
        return str(data_dir / "state.json")
    else:
        return str(data_dir / "transcripts.db")
