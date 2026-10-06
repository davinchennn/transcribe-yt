"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from typing import List, Optional

from transcripts.models import Job, Stage
from transcripts.sources import extract_video_id


# Regex patterns for extracting YouTube video IDs
YOUTUBE_PATTERNS = [
    r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
    r"(?:embed/)([a-zA-Z0-9_-]{11})",
    r"(?:shorts/)([a-zA-Z0-9_-]{11})",
]


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    All storage implementations (SQLite, JSON, etc.) must implement
    these methods to provide job persistence.
    """

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by video ID.

        Args:
            job_id: Stable source video ID

        Returns:
            Job if found, None otherwise
        """
        ...

    @abstractmethod
    def get_job_by_url(self, url: str) -> Optional[Job]:
        """Get a job by URL.

        Args:
            url: YouTube video or X post URL

        Returns:
            Job if found, None otherwise
        """
        ...

    @abstractmethod
    def create_job(self, url: str) -> Job:
        """Create a new job or return existing one.

        Args:
            url: YouTube video or X post URL

        Returns:
            New or existing Job

        Raises:
            ValueError: If video ID cannot be extracted from URL
        """
        ...

    @abstractmethod
    def update_job(self, job: Job) -> None:
        """Update an existing job.

        Args:
            job: Job to update
        """
        ...

    @abstractmethod
    def set_stage(
        self, job_id: str, stage: Stage, error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job stage.

        Args:
            job_id: Video ID of the job
            stage: New stage
            error: Error message if stage is FAILED

        Returns:
            Updated Job, or None if not found
        """
        ...

    @abstractmethod
    def list_jobs(self, filter_stage: Optional[Stage] = None) -> List[Job]:
        """List all jobs, optionally filtered by stage.

        Args:
            filter_stage: Only return jobs in this stage (optional)

        Returns:
            List of jobs, sorted by updated_at descending
        """
        ...

    @abstractmethod
    def get_failed_jobs(self) -> List[Job]:
        """Get all failed jobs.

        Returns:
            List of failed jobs
        """
        ...

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a single job by ID.

        Args:
            job_id: ID of the job to delete

        Returns:
            True if job was deleted, False if not found
        """
        ...

    @abstractmethod
    def clear_jobs(self, filter_stage: Optional[Stage] = None) -> int:
        """Clear jobs from state.

        Args:
            filter_stage: Only clear jobs in this stage, or all if None

        Returns:
            Number of jobs cleared
        """
        ...

    @abstractmethod
    def verify_stage_files(self, job: Job) -> Stage:
        """Verify intermediate files exist and return adjusted stage.

        If files are missing, returns the stage that should be restarted from.

        Args:
            job: Job to verify

        Returns:
            Adjusted stage based on file existence
        """
        ...
