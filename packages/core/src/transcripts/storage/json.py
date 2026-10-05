"""JSON file storage backend for job persistence."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from filelock import FileLock

from transcripts.models import Job, Stage
from transcripts.storage.base import StorageBackend, extract_video_id


class JSONStorage(StorageBackend):
    """JSON file-based storage backend.

    Uses file locking and atomic writes for safe concurrent access.
    This is the original storage method, preserved for backward compatibility.
    """

    STATE_VERSION = 1

    def __init__(self, state_file: str = ".transcripts-state.json"):
        """Initialize JSON storage.

        Args:
            state_file: Path to the state file
        """
        self.state_file = Path(state_file)
        self.lock_file = Path(f"{state_file}.lock")
        self._lock = FileLock(self.lock_file)

    def _load(self) -> Dict:
        """Load state from disk.

        Returns:
            State dictionary with version and jobs
        """
        if not self.state_file.exists():
            return {"version": self.STATE_VERSION, "jobs": {}}

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except (json.JSONDecodeError, IOError) as e:
            # Corrupted state file - log warning and recreate
            print(f"Warning: State file corrupted, recreating: {e}")
            return {"version": self.STATE_VERSION, "jobs": {}}

    def _save(self, state: Dict) -> None:
        """Save state to disk with atomic write.

        Args:
            state: State dictionary to save
        """
        # Write to temp file then rename for atomic operation
        dir_path = (
            self.state_file.parent if self.state_file.parent != Path() else Path(".")
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".tmp",
            dir=dir_path,
            delete=False,
            encoding="utf-8",
        ) as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            temp_path = f.name

        # Atomic rename
        os.replace(temp_path, self.state_file)

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by video ID."""
        with self._lock:
            state = self._load()
            job_data = state["jobs"].get(job_id)
            if job_data:
                return Job.from_dict(job_data)
            return None

    def get_job_by_url(self, url: str) -> Optional[Job]:
        """Get a job by URL."""
        video_id = extract_video_id(url)
        if video_id:
            return self.get_job(video_id)
        return None

    def create_job(self, url: str) -> Job:
        """Create a new job or return existing one."""
        video_id = extract_video_id(url)
        if not video_id:
            raise ValueError(f"Cannot extract video ID from URL: {url}")

        with self._lock:
            state = self._load()

            # Return existing job if found
            if video_id in state["jobs"]:
                return Job.from_dict(state["jobs"][video_id])

            # Create new job
            job = Job(id=video_id, url=url)
            state["jobs"][video_id] = job.to_dict()
            self._save(state)

            return job

    def update_job(self, job: Job) -> None:
        """Update an existing job."""
        job.updated_at = datetime.utcnow().isoformat()

        with self._lock:
            state = self._load()
            state["jobs"][job.id] = job.to_dict()
            self._save(state)

    def set_stage(
        self, job_id: str, stage: Stage, error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job stage."""
        with self._lock:
            state = self._load()

            if job_id not in state["jobs"]:
                return None

            job = Job.from_dict(state["jobs"][job_id])
            job.stage = stage
            job.updated_at = datetime.utcnow().isoformat()

            if stage == Stage.FAILED and error:
                job.error = error
            elif stage != Stage.FAILED:
                job.error = None

            state["jobs"][job_id] = job.to_dict()
            self._save(state)

            return job

    def list_jobs(self, filter_stage: Optional[Stage] = None) -> List[Job]:
        """List all jobs, optionally filtered by stage."""
        with self._lock:
            state = self._load()

        jobs = [Job.from_dict(data) for data in state["jobs"].values()]

        if filter_stage:
            jobs = [j for j in jobs if j.stage == filter_stage]

        # Sort by updated_at descending (most recent first)
        jobs.sort(key=lambda j: j.updated_at, reverse=True)

        return jobs

    def get_failed_jobs(self) -> List[Job]:
        """Get all failed jobs."""
        return self.list_jobs(filter_stage=Stage.FAILED)

    def delete_job(self, job_id: str) -> bool:
        """Delete a single job by ID."""
        with self._lock:
            state = self._load()
            if job_id in state["jobs"]:
                del state["jobs"][job_id]
                self._save(state)
                return True
            return False

    def clear_jobs(self, filter_stage: Optional[Stage] = None) -> int:
        """Clear jobs from state."""
        with self._lock:
            state = self._load()
            original_count = len(state["jobs"])

            if filter_stage:
                state["jobs"] = {
                    k: v
                    for k, v in state["jobs"].items()
                    if Stage(v["stage"]) != filter_stage
                }
            else:
                state["jobs"] = {}

            self._save(state)

            return original_count - len(state["jobs"])

    def verify_stage_files(self, job: Job) -> Stage:
        """Verify intermediate files exist and return adjusted stage."""
        # If job is pending or failed, no adjustment needed
        if job.stage in (Stage.PENDING, Stage.FAILED):
            return job.stage

        # Check files based on stage progression
        stage_order = [
            Stage.PENDING,
            Stage.DOWNLOADING,
            Stage.EXTRACTING,
            Stage.TRANSCRIBING,
            Stage.SAVING,
            Stage.COMPLETED,
        ]

        current_index = (
            stage_order.index(job.stage) if job.stage in stage_order else 0
        )

        # If past downloading, verify video file
        if current_index >= stage_order.index(Stage.EXTRACTING):
            if job.video_file and not Path(job.video_file).exists():
                return Stage.PENDING

        # If past extracting, verify audio file
        if current_index >= stage_order.index(Stage.TRANSCRIBING):
            if job.audio_file and not Path(job.audio_file).exists():
                # Video might still exist, restart from extracting
                if job.video_file and Path(job.video_file).exists():
                    return Stage.DOWNLOADING  # Will re-extract
                return Stage.PENDING

        # If completed, verify transcript file
        if job.stage == Stage.COMPLETED:
            if job.transcript_file and not Path(job.transcript_file).exists():
                # Audio might still exist, restart from transcribing
                if job.audio_file and Path(job.audio_file).exists():
                    return Stage.EXTRACTING
                if job.video_file and Path(job.video_file).exists():
                    return Stage.DOWNLOADING
                return Stage.PENDING

        return job.stage
