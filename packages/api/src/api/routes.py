"""API routes for job management."""

import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from transcripts.state import StateManager
from transcripts.processor import TranscriptProcessor
from transcripts.models import Stage
from transcripts.navigation import source_segments
from transcripts.analyses import AnalysisConflictError, run_saved_analysis
from transcripts.search import search_transcript
from transcripts.llm import LLMError
from transcripts.inference import (
    InferenceSelection, resolve_inference, inference_scope, inference_options, inference_api_key,
)
from transcripts.sources import parse_video_source
from transcripts.storage.base import extract_video_id

from api.schemas import (
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
    PassageSearchRequest,
    PassageSearchResponse,
    SavedAnalysisCreate,
    SavedAnalysisRegenerate,
    SavedAnalysisResponse,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Shared state manager instance
_state_manager: Optional[StateManager] = None
VIDEO_DIRECTORY = Path("downloads/videos")


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

    return JobDetailResponse(
        job=job_to_response(job),
        transcript=transcript_response,
        analyses=[saved_analysis_to_response(result) for result in storage.list_saved_analyses(job_id)]
        if hasattr(storage, "list_saved_analyses") else [],
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

    # Delete transcript and saved analyses first
    storage = state._storage
    if hasattr(storage, 'delete_transcript'):
        storage.delete_transcript(job_id)

    if hasattr(storage, 'list_saved_analyses') and hasattr(storage, 'delete_saved_analysis'):
        for analysis in storage.list_saved_analyses(job_id):
            storage.delete_saved_analysis(job_id, analysis.id)

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


def completed_transcript(job_id: str):
    """Require an existing, completed job with a stored transcript."""
    state = get_state_manager()
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.stage != Stage.COMPLETED:
        raise HTTPException(400, "Only completed transcripts support analysis and search")
    storage = state._storage
    if not hasattr(storage, "get_transcript"):
        raise HTTPException(400, "This storage backend does not support transcripts")
    transcript = storage.get_transcript(job_id)
    if not transcript:
        raise HTTPException(404, "Transcript not found")
    return state, storage, transcript


def saved_analysis_to_response(analysis) -> SavedAnalysisResponse:
    return SavedAnalysisResponse(**analysis.to_dict())


def saved_analysis_storage(job_id: str):
    """Read saved versions without requiring a generation-capable transcript."""
    state = get_state_manager()
    if not state.get_job(job_id):
        raise HTTPException(404, "Job not found")
    storage = state._storage
    if not all(hasattr(storage, method) for method in (
        "create_saved_analysis", "list_saved_analyses", "get_saved_analysis", "delete_saved_analysis",
    )):
        raise HTTPException(400, "This storage backend does not support saved analyses")
    return storage


def require_saved_analysis(storage, job_id: str, analysis_id: str):
    analysis = storage.get_saved_analysis(job_id, analysis_id)
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis


def start_saved_analysis(job_id: str, body: SavedAnalysisCreate, background_tasks: BackgroundTasks):
    """Validate before reserving a new version or dispatching generation."""
    _, storage, transcript = completed_transcript(job_id)
    saved_analysis_storage(job_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Enter an analysis name")
    try:
        source_segments(transcript)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    selection = selected_inference(body)
    require_inference_key(selection)
    try:
        analysis = storage.create_saved_analysis(
            job_id, name, body.view, prompt=body.prompt.strip(),
            provider=selection.provider, model=selection.model,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    background_tasks.add_task(generate_saved_analysis, storage, analysis, transcript)
    return saved_analysis_to_response(analysis)


def generate_saved_analysis(storage, analysis, transcript):
    """Run a reserved version; deletion or a replaced transcript cancels saving."""
    try:
        run_saved_analysis(storage, analysis, transcript)
    except AnalysisConflictError:
        logger.info("Analysis %s for %s changed before generation finished", analysis.id, analysis.job_id)


@router.get("/jobs/{job_id}/analyses", response_model=List[SavedAnalysisResponse])
async def list_saved_analyses(job_id: str):
    storage = saved_analysis_storage(job_id)
    return [saved_analysis_to_response(analysis) for analysis in storage.list_saved_analyses(job_id)]


@router.post("/jobs/{job_id}/analyses", response_model=SavedAnalysisResponse, status_code=202)
async def create_saved_analysis(job_id: str, body: SavedAnalysisCreate, background_tasks: BackgroundTasks):
    """Start an independent version, including when its settings match an older one."""
    return start_saved_analysis(job_id, body, background_tasks)


@router.get("/jobs/{job_id}/analyses/{analysis_id}", response_model=SavedAnalysisResponse)
async def get_saved_analysis(job_id: str, analysis_id: str):
    storage = saved_analysis_storage(job_id)
    return saved_analysis_to_response(require_saved_analysis(storage, job_id, analysis_id))


@router.delete("/jobs/{job_id}/analyses/{analysis_id}")
async def delete_saved_analysis(job_id: str, analysis_id: str):
    storage = saved_analysis_storage(job_id)
    require_saved_analysis(storage, job_id, analysis_id)
    storage.delete_saved_analysis(job_id, analysis_id)
    return {"deleted": True}


@router.post(
    "/jobs/{job_id}/analyses/{analysis_id}/regenerate",
    response_model=SavedAnalysisResponse, status_code=202,
)
async def regenerate_saved_analysis(
    job_id: str, analysis_id: str, background_tasks: BackgroundTasks,
    body: Optional[SavedAnalysisRegenerate] = None,
):
    """Create a new version using inherited settings plus explicit changes."""
    storage = saved_analysis_storage(job_id)
    previous = require_saved_analysis(storage, job_id, analysis_id)
    if not previous.view and (body is None or body.view is None):
        raise HTTPException(400, "Choose Timeline or Topics to regenerate this legacy summary")
    provider = body.provider if body and body.provider is not None else previous.provider
    model = body.model if body and body.model is not None else (
        previous.model if not body or body.provider is None or body.provider == previous.provider else None
    )
    settings = SavedAnalysisCreate(
        name=body.name if body and body.name is not None else previous.name,
        view=body.view if body and body.view is not None else previous.view,
        prompt=body.prompt if body and body.prompt is not None else previous.prompt,
        provider=provider, model=model,
    )
    return start_saved_analysis(job_id, settings, background_tasks)


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
