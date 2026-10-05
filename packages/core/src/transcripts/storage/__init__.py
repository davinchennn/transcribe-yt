"""Storage abstraction for transcripts state management.

Provides pluggable storage backends (SQLite, JSON) for job persistence.
"""

from transcripts.storage.base import StorageBackend, extract_video_id

__all__ = ["StorageBackend", "extract_video_id", "get_storage"]


def get_storage(backend: str = None) -> StorageBackend:
    """Get a storage backend instance.

    Args:
        backend: Storage backend type ("sqlite" or "json").
                 If not provided, reads from STORAGE_BACKEND env var,
                 defaulting to "sqlite".

    Returns:
        StorageBackend instance
    """
    from transcripts.config import get_storage_backend, get_storage_path

    if backend is None:
        backend = get_storage_backend()

    storage_path = get_storage_path(backend)

    if backend == "json":
        from transcripts.storage.json import JSONStorage
        return JSONStorage(state_file=storage_path)
    else:
        from transcripts.storage.sqlite import SQLiteStorage
        return SQLiteStorage(db_path=storage_path)
