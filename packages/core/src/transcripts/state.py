"""State management for tracking transcription job progress.

This module provides persistence and resume capability for transcription jobs.
Jobs are tracked through stages and can be resumed from their last checkpoint
if interrupted.

Note: This module now delegates to the storage abstraction layer.
Direct use of StateManager is supported for backward compatibility,
but new code should use `from transcripts.storage import get_storage`.
"""

from typing import List, Optional

from transcripts.models import Job, Stage
from transcripts.storage import get_storage, StorageBackend
from transcripts.storage.base import extract_video_id, YOUTUBE_PATTERNS

# Re-export for backward compatibility
__all__ = [
    "StateManager",
    "extract_video_id",
    "YOUTUBE_PATTERNS",
]


class StateManager:
    """Manages persistence of transcription job state.

    This class now delegates to a StorageBackend implementation.
    It maintains the same API for backward compatibility.
    """

    def __init__(self, state_file: str = None, backend: str = None):
        """Initialize StateManager.

        Args:
            state_file: Deprecated. Use STORAGE_PATH env var instead.
            backend: Storage backend ("sqlite" or "json"). If not provided,
                    uses STORAGE_BACKEND env var, defaulting to "sqlite".
        """
        # Get storage backend
        self._storage: StorageBackend = get_storage(backend)

        # If a specific state_file was provided (legacy usage), handle it
        if state_file is not None:
            # For backward compatibility, if someone passes a state_file,
            # we assume they want JSON storage with that file
            from transcripts.storage.json import JSONStorage
            self._storage = JSONStorage(state_file=state_file)

    def get_job(self, video_id: str) -> Optional[Job]:
        """Get a job by video ID."""
        return self._storage.get_job(video_id)

    def get_job_by_url(self, url: str) -> Optional[Job]:
        """Get a job by URL."""
        return self._storage.get_job_by_url(url)

    def create_job(
        self, url: str, keep_video: bool = True, keep_audio: bool = True
    ) -> Job:
        """Create a new job or return existing one.

        Args:
            url: YouTube video URL
            keep_video: Whether to retain video file after transcription (default: True)
            keep_audio: Whether to retain audio file after transcription (default: True)

        Returns:
            Job object (new or existing)
        """
        job = self._storage.create_job(url)
        # Update retention preferences for new jobs
        if job.stage == Stage.PENDING:
            job.keep_video = keep_video
            job.keep_audio = keep_audio
            self._storage.update_job(job)
        return job

    def update_job(self, job: Job) -> None:
        """Update an existing job."""
        return self._storage.update_job(job)

    def set_stage(
        self, job_id: str, stage: Stage, error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job stage."""
        return self._storage.set_stage(job_id, stage, error)

    def list_jobs(self, filter_stage: Optional[Stage] = None) -> List[Job]:
        """List all jobs, optionally filtered by stage."""
        return self._storage.list_jobs(filter_stage)

    def get_failed_jobs(self) -> List[Job]:
        """Get all failed jobs."""
        return self._storage.get_failed_jobs()

    def delete_job(self, job_id: str) -> bool:
        """Delete a single job by ID."""
        return self._storage.delete_job(job_id)

    def clear_jobs(self, filter_stage: Optional[Stage] = None) -> int:
        """Clear jobs from state."""
        return self._storage.clear_jobs(filter_stage)

    def verify_stage_files(self, job: Job) -> Stage:
        """Verify intermediate files exist and return adjusted stage."""
        return self._storage.verify_stage_files(job)
