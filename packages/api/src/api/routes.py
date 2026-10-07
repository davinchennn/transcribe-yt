"""API routes for job management."""

import asyncio
import logging
from pathlib import Path
from typing import Literal, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from transcripts.state import StateManager
from transcripts.processor import TranscriptProcessor
from transcripts.models import Stage, Analysis, AnalysisStatus, NavigationAnalysis
from transcripts.analyzer import analyze_transcript
from transcripts.navigation import (
    analyze_navigation,
    needs_subtopic_summaries,
    summarize_subtopics,
)
from transcripts.search import search_transcript
from transcripts.llm import LLMError
from transcripts.inference import (
    InferenceSelection, resolve_inference, inference_scope, inference_options, inference_api_key,
)
from transcripts.sources import parse_video_source
from transcripts.storage.base import extract_video_id

from api.schemas import (
    AnalysisResponse,
    InferenceRequest,
    InferenceOptionsResponse,
    JobCreate,
    JobResponse,
    JobDetailResponse,
    JobListResponse,
    TranscriptResponse,
    WordResponse,
    UtteranceResponse,
    HealthResponse,
    NavigationResponse,
    PassageSearchRequest,
    PassageSearchResponse,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Shared state manager instance
_state_manager: Optional[StateManager] = None
VIDEO_DIRECTORY = Path("downloads/videos")
_summary_updates = {}


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
        video_available=video_file_path(job) is not None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def is_valid_video_url(url: str) -> bool:
    """Accept supported YouTube video and X/Twitter post URLs."""
    return extract_video_id(url) is not None


def is_valid_youtube_url(url: str) -> bool:
    """Keep the existing YouTube-only helper available to callers."""
    source = parse_video_source(url)
    return source is not None and source.provider == "youtube"


def video_file_path(job) -> Optional[Path]:
    """Find a completed job's retained video inside the download directory.

    Resolving the directory first also supports moving downloads with a symlink.
    Individual file paths cannot escape that directory.
    """
    if job.stage != Stage.COMPLETED or not job.keep_video or not job.video_file:
        return None
    try:
        path = Path(job.video_file).resolve()
        path.relative_to(VIDEO_DIRECTORY.resolve())
        return path if path.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


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
    if not is_valid_video_url(body.url):
        raise HTTPException(400, "Enter a valid YouTube video or X/Twitter post URL")

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

    storage = state._storage
    transcript_response = None
    if job.stage == Stage.COMPLETED:
        if hasattr(storage, 'get_transcript'):
            transcript = storage.get_transcript(job_id)
            if transcript:
                transcript_response = TranscriptResponse(
                    video_url=transcript.video_url,
                    title=transcript.title,
                    duration=transcript.duration,
                    video_available=video_file_path(job) is not None,
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
                provider=analysis.provider,
                error=analysis.error,
                created_at=analysis.created_at,
                updated_at=analysis.updated_at,
            )

    navigation = {}
    if hasattr(storage, 'get_navigation'):
        for view in ("timeline", "topics"):
            result = storage.get_navigation(job_id, view)
            navigation[view] = navigation_to_response(result) if result else None

    return JobDetailResponse(
        job=job_to_response(job),
        transcript=transcript_response,
        analysis=analysis_response,
        navigation=navigation,
    )


@router.api_route("/jobs/{job_id}/video", methods=["GET", "HEAD"])
async def get_job_video(job_id: str):
    """Serve retained video, including byte ranges for native-player seeking."""
    job = get_state_manager().get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    path = video_file_path(job)
    if path is None:
        raise HTTPException(404, "Retained video is unavailable")
    return FileResponse(path, filename=path.name, content_disposition_type="inline")


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
    background_tasks.add_task(
        process_job, job.id, job.url, job.keep_video, job.keep_audio
    )

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
    if hasattr(storage, 'delete_navigation'):
        storage.delete_navigation(job_id)

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


@router.get("/inference/providers", response_model=InferenceOptionsResponse)
async def get_inference_providers():
    """Read catalogs, fetching configured providers when their cache expires."""
    try:
        return await run_in_threadpool(inference_options)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/inference/providers/refresh", response_model=InferenceOptionsResponse)
async def refresh_inference_providers():
    """Refresh catalogs without making inference requests or changing selection."""
    try:
        return await run_in_threadpool(inference_options, force_refresh=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def selected_inference(body: Optional[InferenceRequest]) -> InferenceSelection:
    try:
        return resolve_inference(body.provider if body else None, body.model if body else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def require_inference_key(selection: InferenceSelection):
    try:
        inference_api_key(selection)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def run_selected(selection: InferenceSelection, function, *args):
    with inference_scope(selection):
        return function(*args)


@router.post("/jobs/{job_id}/analyze", response_model=AnalysisResponse)
async def analyze_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    body: Optional[InferenceRequest] = None,
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

    selection = selected_inference(body)
    # Check for existing analysis
    existing = storage.get_analysis(job_id)
    matches_selection = existing and (
        (existing.provider or "kimi", existing.model) == (selection.provider, selection.model)
    )
    if existing and (
        existing.status in (AnalysisStatus.PENDING, AnalysisStatus.PROCESSING)
        or (existing.status == AnalysisStatus.COMPLETED and (body is None or matches_selection))
    ):
        return AnalysisResponse(
            job_id=existing.job_id,
            status=existing.status.value,
            summary=existing.summary,
            key_points=existing.key_points,
            model=existing.model,
            provider=existing.provider,
            error=existing.error,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    require_inference_key(selection)
    # Create pending analysis
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    analysis = Analysis(
        job_id=job_id,
        status=AnalysisStatus.PENDING,
        provider=selection.provider, model=selection.model,
        created_at=now,
        updated_at=now,
    )
    storage.save_analysis(analysis)

    # Start background analysis
    background_tasks.add_task(run_analysis, job_id, selection)

    return AnalysisResponse(
        job_id=analysis.job_id,
        status=analysis.status.value,
        summary=analysis.summary,
        key_points=analysis.key_points,
        model=analysis.model,
        provider=analysis.provider,
        error=analysis.error,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


def run_analysis(job_id: str, selection: Optional[InferenceSelection] = None):
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
            provider=selection.provider if selection else None,
            model=selection.model if selection else None,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        storage.save_analysis(analysis)
        return

    # Run analysis
    analysis = run_selected(selection or resolve_inference(), analyze_transcript, transcript.transcript_text, job_id)
    storage.save_analysis(analysis)


def navigation_to_response(analysis: NavigationAnalysis) -> NavigationResponse:
    return NavigationResponse(**analysis.to_dict())


def completed_transcript(job_id: str):
    """Require an existing, completed job with a stored transcript."""
    state = get_state_manager()
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.stage != Stage.COMPLETED:
        raise HTTPException(400, "Only completed transcripts support navigation and search")
    storage = state._storage
    if not hasattr(storage, "get_transcript"):
        raise HTTPException(400, "This storage backend does not support transcripts")
    transcript = storage.get_transcript(job_id)
    if not transcript:
        raise HTTPException(404, "Transcript not found")
    return state, storage, transcript


@router.get("/jobs/{job_id}/navigation/{view}", response_model=Optional[NavigationResponse])
async def get_navigation(job_id: str, view: Literal["timeline", "topics"]):
    """Read a saved view without starting analysis."""
    state = get_state_manager()
    if not state.get_job(job_id):
        raise HTTPException(404, "Job not found")
    storage = state._storage
    if not hasattr(storage, "get_navigation"):
        raise HTTPException(400, "This storage backend does not support navigation")
    analysis = storage.get_navigation(job_id, view)
    return navigation_to_response(analysis) if analysis else None


@router.post("/jobs/{job_id}/navigation/{view}", response_model=NavigationResponse)
async def create_navigation(
    job_id: str, view: Literal["timeline", "topics"], response: Response,
    body: Optional[InferenceRequest] = None,
):
    """Await creation of exactly the selected view while keeping the API responsive."""
    state, storage, transcript = completed_transcript(job_id)
    if not all(hasattr(storage, name) for name in ("get_navigation", "save_navigation", "claim_navigation")):
        raise HTTPException(400, "This storage backend does not support navigation")

    selection = selected_inference(body)
    existing = storage.get_navigation(job_id, view)
    changed_selection = existing and (
        (existing.provider or "kimi", existing.model) != (selection.provider, selection.model)
    )
    if (
        not existing or existing.status == AnalysisStatus.FAILED
        or (body is not None and existing.status == AnalysisStatus.COMPLETED and changed_selection)
    ):
        require_inference_key(selection)
    if not storage.claim_navigation(
        job_id, view, selection.provider, selection.model, replace_completed=body is not None,
    ):
        existing = storage.get_navigation(job_id, view)
        if not existing:
            raise HTTPException(409, "Navigation changed while it was being requested; retry")
        if existing.status in (AnalysisStatus.PENDING, AnalysisStatus.PROCESSING):
            response.status_code = 202
        return navigation_to_response(existing)

    reservation = storage.get_navigation(job_id, view)
    finished = asyncio.Event()
    heartbeat = asyncio.create_task(keep_navigation_alive(storage, job_id, view, finished))
    try:
        try:
            analysis = await run_in_threadpool(run_selected, selection, analyze_navigation, transcript, job_id, view)
        except Exception:
            # Unexpected failures must release the reservation so retry remains possible.
            logger.exception("Navigation creation failed for %s/%s", job_id, view)
            analysis = NavigationAnalysis(
                job_id=job_id, view=view, status=AnalysisStatus.FAILED,
                error="Navigation creation failed. Please retry.",
                provider=selection.provider, model=selection.model,
            )
    finally:
        finished.set()
        await heartbeat
    if not state.get_job(job_id):
        storage.delete_navigation(job_id)
        raise HTTPException(404, "Job was deleted while navigation was being created")
    current_transcript = storage.get_transcript(job_id)
    if (
        not current_transcript
        or current_transcript.transcript_text != transcript.transcript_text
        or current_transcript.words != transcript.words
        or current_transcript.utterances != transcript.utterances
    ):
        storage.delete_navigation(job_id)
        raise HTTPException(409, "Transcript changed while navigation was being created. Create this view again.")
    if reservation:
        analysis.created_at = reservation.created_at
    storage.save_navigation(analysis)
    return navigation_to_response(analysis)


async def keep_navigation_alive(storage, job_id: str, view: str, finished: asyncio.Event):
    """Keep a long multi-call analysis reserved without blocking other requests."""
    if not hasattr(storage, "lease_navigation"):
        return
    while not finished.is_set():
        try:
            await asyncio.wait_for(finished.wait(), timeout=30)
        except asyncio.TimeoutError:
            try:
                if not storage.lease_navigation(job_id, view):
                    return
            except Exception:
                logger.exception("Could not refresh navigation reservation for %s/%s", job_id, view)
                return


async def update_subtopic_summaries(storage, transcript, analysis, selection):
    """Rewrite summaries while preserving a saved view and its source passages."""
    try:
        updated = await run_in_threadpool(run_selected, selection, summarize_subtopics, transcript, analysis)
    except (ValueError, LLMError) as exc:
        raise HTTPException(502, str(exc)) from exc

    if not storage.save_navigation_if_current(updated, analysis, transcript):
        raise HTTPException(409, "Navigation or transcript changed while updating summaries; try again")
    return navigation_to_response(updated)


@router.post("/jobs/{job_id}/navigation/{view}/summaries", response_model=NavigationResponse)
async def refresh_subtopic_summaries(
    job_id: str, view: Literal["timeline", "topics"], body: Optional[InferenceRequest] = None,
):
    """Update existing subtopic summaries without recreating topic navigation."""
    _, storage, transcript = completed_transcript(job_id)
    if not all(hasattr(storage, method) for method in ("get_navigation", "save_navigation_if_current")):
        raise HTTPException(400, "This storage backend does not support navigation")
    analysis = storage.get_navigation(job_id, view)
    if not analysis or analysis.status != AnalysisStatus.COMPLETED:
        raise HTTPException(400, "Create this view before updating its subtopic summaries")
    if not needs_subtopic_summaries(analysis):
        return navigation_to_response(analysis)

    selection = selected_inference(body)
    require_inference_key(selection)
    # Concurrent requests share the same work instead of making duplicate calls.
    key = (job_id, view)
    task = _summary_updates.get(key)
    if task is None:
        task = asyncio.create_task(update_subtopic_summaries(storage, transcript, analysis, selection))
        _summary_updates[key] = task

        def release(completed):
            if _summary_updates.get(key) is completed:
                _summary_updates.pop(key, None)
            # Retrieve failures even when the client disconnected during the call.
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(release)
    return await asyncio.shield(task)


@router.post("/jobs/{job_id}/search", response_model=PassageSearchResponse)
async def search_passages(job_id: str, body: PassageSearchRequest):
    """Find exact phrases locally, or retrieve related passages using the LLM."""
    _, _, transcript = completed_transcript(job_id)
    query = body.query.strip()
    if not query:
        raise HTTPException(400, "Enter a phrase or idea to search for")
    try:
        selection = selected_inference(body)
        if body.mode == "semantic":
            require_inference_key(selection)
        results = await run_in_threadpool(run_selected, selection, search_transcript, transcript, query, body.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    return PassageSearchResponse(query=query, mode=body.mode, results=results)
