"""API routes for job management."""

import re
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from transcripts.state import StateManager
from transcripts.processor import TranscriptProcessor
from transcripts.models import Stage, Analysis, AnalysisStatus
from transcripts.analyzer import analyze_transcript

from api.schemas import (
    AnalysisResponse,
    JobCreate,
    JobResponse,
    JobDetailResponse,
    JobListResponse,
    TranscriptResponse,
    WordResponse,
    UtteranceResponse,
    HealthResponse,
)

router = APIRouter(prefix="/api")

# Shared state manager instance
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get or create the state manager singleton."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


def job_to_response(job) -> JobResponse:
    """Convert Job model to response schema."""
    return JobResponse(
        id=job.id,
        url=job.url,
        stage=job.stage.value,
        title=job.title,
        error=job.error,
        provider=job.provider,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def is_valid_youtube_url(url: str) -> bool:
    """Check if URL is a valid YouTube URL."""
    patterns = [
        r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]{11}',
        r'^https?://youtu\.be/[\w-]{11}',
        r'^https?://(www\.)?youtube\.com/shorts/[\w-]{11}',
    ]
    return any(re.match(p, url) for p in patterns)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    stage: Optional[str] = Query(None, description="Filter by stage")
):
    """List all jobs, optionally filtered by stage."""
    state = get_state_manager()

    filter_stage = None
    if stage:
        try:
            filter_stage = Stage(stage)
        except ValueError:
            raise HTTPException(400, f"Invalid stage: {stage}")

    jobs = state.list_jobs(filter_stage=filter_stage)
    return JobListResponse(
        jobs=[job_to_response(j) for j in jobs],
        total=len(jobs),
    )


@router.post("/jobs", response_model=JobResponse)
async def create_job(
    body: JobCreate,
    background_tasks: BackgroundTasks,
):
    """Create a new transcription job."""
    if not is_valid_youtube_url(body.url):
        raise HTTPException(400, "Invalid YouTube URL")

    state = get_state_manager()
    job = state.create_job(
        body.url,
        keep_video=body.keep_video,
        keep_audio=body.keep_audio,
    )

    # If job already completed, return it
    if job.stage == Stage.COMPLETED:
        return job_to_response(job)

    # Start processing in background
    background_tasks.add_task(
        process_job, job.id, body.url, body.keep_video, body.keep_audio
    )

    return job_to_response(job)


def process_job(job_id: str, url: str, keep_video: bool = True, keep_audio: bool = True):
    """Background task to process a job."""
    state = get_state_manager()
    processor = TranscriptProcessor(
        output_format="none",  # Database only
        state_manager=state,
        keep_video=keep_video,
        keep_audio=keep_audio,
    )
    try:
        processor.process_video(url)
    except Exception as e:
        # Error is already recorded by processor
        print(f"Job {job_id} failed: {e}")


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str):
    """Get job details including transcript if available."""
    state = get_state_manager()
    job = state.get_job(job_id)

    if not job:
        raise HTTPException(404, "Job not found")

    transcript_response = None
    if job.stage == Stage.COMPLETED:
        storage = state._storage
        if hasattr(storage, 'get_transcript'):
            transcript = storage.get_transcript(job_id)
            if transcript:
                transcript_response = TranscriptResponse(
                    video_url=transcript.video_url,
                    title=transcript.title,
                    duration=transcript.duration,
                    transcript_text=transcript.transcript_text,
                    words=[
                        WordResponse(
                            text=w.text,
                            start=w.start,
                            end=w.end,
                            confidence=w.confidence,
                            speaker=w.speaker,
                        )
                        for w in transcript.words
                    ],
                    utterances=[
                        UtteranceResponse(
                            speaker=u.speaker,
                            text=u.text,
                            start=u.start,
                            end=u.end,
                        )
                        for u in transcript.utterances
                    ],
                )

    # Include analysis if available
    analysis_response = None
    if hasattr(storage, 'get_analysis'):
        analysis = storage.get_analysis(job_id)
        if analysis:
            analysis_response = AnalysisResponse(
                job_id=analysis.job_id,
                status=analysis.status.value,
                summary=analysis.summary,
                key_points=analysis.key_points,
                model=analysis.model,
                error=analysis.error,
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
            )

    return JobDetailResponse(
        job=job_to_response(job),
        transcript=transcript_response,
        analysis=analysis_response,
    )


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
):
    """Retry a failed job."""
    state = get_state_manager()
    job = state.get_job(job_id)

    if not job:
        raise HTTPException(404, "Job not found")

    if job.stage != Stage.FAILED:
        raise HTTPException(400, "Only failed jobs can be retried")

    # Reset job to pending
    job.stage = Stage.PENDING
    job.error = None
    state.update_job(job)

    # Start processing in background
    background_tasks.add_task(process_job, job.id, job.url)

    return job_to_response(job)


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job."""
    state = get_state_manager()
    job = state.get_job(job_id)

    if not job:
        raise HTTPException(404, "Job not found")

    # Delete transcript and analysis first
    storage = state._storage
    if hasattr(storage, 'delete_transcript'):
        storage.delete_transcript(job_id)
    if hasattr(storage, 'delete_analysis'):
        storage.delete_analysis(job_id)

    # Delete the specific job
    state.delete_job(job_id)

    return {"deleted": True}


@router.delete("/jobs")
async def clear_jobs(
    stage: Optional[str] = Query(None, description="Only clear jobs with this stage")
):
    """Clear all jobs or jobs with specific stage."""
    state = get_state_manager()

    filter_stage = None
    if stage:
        try:
            filter_stage = Stage(stage)
        except ValueError:
            raise HTTPException(400, f"Invalid stage: {stage}")

    count = state.clear_jobs(filter_stage=filter_stage)
    return {"cleared": count}


@router.post("/jobs/{job_id}/analyze", response_model=AnalysisResponse)
async def analyze_job(
    job_id: str,
    background_tasks: BackgroundTasks,
):
    """Trigger analysis for a completed job."""
    state = get_state_manager()
    job = state.get_job(job_id)

    if not job:
        raise HTTPException(404, "Job not found")

    if job.stage != Stage.COMPLETED:
        raise HTTPException(400, "Only completed jobs can be analyzed")

    storage = state._storage
    if not hasattr(storage, 'get_analysis'):
        raise HTTPException(500, "Storage backend does not support analysis")

    # Check for existing analysis
    existing = storage.get_analysis(job_id)
    if existing and existing.status in (AnalysisStatus.PROCESSING, AnalysisStatus.COMPLETED):
        return AnalysisResponse(
            job_id=existing.job_id,
            status=existing.status.value,
            summary=existing.summary,
            key_points=existing.key_points,
            model=existing.model,
            error=existing.error,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    # Create pending analysis
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    analysis = Analysis(
        job_id=job_id,
        status=AnalysisStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    storage.save_analysis(analysis)

    # Start background analysis
    background_tasks.add_task(run_analysis, job_id)

    return AnalysisResponse(
        job_id=analysis.job_id,
        status=analysis.status.value,
        summary=analysis.summary,
        key_points=analysis.key_points,
        model=analysis.model,
        error=analysis.error,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


def run_analysis(job_id: str):
    """Background task to run transcript analysis."""
    state = get_state_manager()
    storage = state._storage

    # Get transcript text
    transcript = storage.get_transcript(job_id) if hasattr(storage, 'get_transcript') else None
    if not transcript:
        from datetime import datetime
        analysis = Analysis(
            job_id=job_id,
            status=AnalysisStatus.FAILED,
            error="No transcript found for this job",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        storage.save_analysis(analysis)
        return

    # Run analysis
    analysis = analyze_transcript(transcript.transcript_text, job_id)
    storage.save_analysis(analysis)
