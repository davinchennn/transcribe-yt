"""Create and generate immutable, named analysis versions of one transcript."""

from copy import deepcopy
from typing import Optional

from transcripts.analyzer import analyze_transcript
from transcripts.inference import inference_api_key, inference_scope, resolve_inference
from transcripts.models import AnalysisStatus, SavedAnalysis, Stage, Transcript
from transcripts.navigation import analyze_navigation, source_segments


class AnalysisConflictError(RuntimeError):
    """The analysis reservation or its source changed before completion."""


def run_saved_analysis(storage, analysis: SavedAnalysis, transcript: Transcript) -> SavedAnalysis:
    """Generate one reserved version and conditionally persist its final result.

    Model failures are saved as failed versions. Deleted versions and changed
    transcripts are never recreated, and a duplicate worker sends no model calls.
    """
    current = storage.get_saved_analysis(analysis.job_id, analysis.id)
    immutable = ("job_id", "name", "view", "prompt", "provider", "model", "created_at")
    if (
        current is None
        or any(getattr(current, field) != getattr(analysis, field) for field in immutable)
        or not storage.claim_saved_analysis(analysis.job_id, analysis.id, transcript)
    ):
        raise AnalysisConflictError("Analysis was deleted, changed, or has already started")
    result = deepcopy(current)
    result.status = AnalysisStatus.PROCESSING
    try:
        if result.view not in ("timeline", "topics"):
            raise ValueError("Choose a timeline or topics visualization for this analysis")
        source_segments(transcript)  # Validate timing before the first paid request.
        selection = resolve_inference(result.provider, result.model)
        inference_api_key(selection)
        result.provider, result.model = selection.provider, selection.model
        with inference_scope(selection):
            summary = analyze_transcript(transcript.transcript_text, result.job_id, prompt=result.prompt)
            result.summary, result.key_points = summary.summary, summary.key_points
            if summary.status != AnalysisStatus.COMPLETED:
                raise RuntimeError(summary.error or "Summary generation failed")
            navigation = analyze_navigation(transcript, result.job_id, result.view, prompt=result.prompt)
            if navigation.status != AnalysisStatus.COMPLETED:
                raise RuntimeError(navigation.error or "Visualization generation failed")
            result.nodes = navigation.nodes
        result.status = AnalysisStatus.COMPLETED
    except Exception as exc:
        result.status = AnalysisStatus.FAILED
        result.error = str(exc)
    if not storage.finish_saved_analysis(result, transcript):
        raise AnalysisConflictError("Analysis was deleted or its transcript changed during generation")
    persisted = storage.get_saved_analysis(result.job_id, result.id)
    if persisted is None:
        raise AnalysisConflictError("Analysis was deleted after generation")
    return persisted


def create_and_run_analysis(
    storage, job_id: str, name: str, view: str, prompt: str = "",
    provider: Optional[str] = None, model: Optional[str] = None,
) -> SavedAnalysis:
    """Validate prerequisites before reserving or generating a new version."""
    if not all(hasattr(storage, method) for method in (
        "create_saved_analysis", "get_transcript", "claim_saved_analysis", "finish_saved_analysis",
    )):
        raise ValueError("This storage backend does not support saved analyses")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise ValueError("Analysis name must contain 1-200 characters")
    if not isinstance(prompt, str) or len(prompt.strip()) > 10000:
        raise ValueError("Analysis prompt must contain at most 10000 characters")
    if view not in ("timeline", "topics"):
        raise ValueError("Analysis visualization must be 'timeline' or 'topics'")
    job = storage.get_job(job_id)
    if not job:
        raise ValueError("Job not found")
    if job.stage != Stage.COMPLETED:
        raise ValueError("Only completed jobs can be analyzed")
    transcript = storage.get_transcript(job_id)
    if transcript is None:
        raise ValueError("No transcript found for this job")
    source_segments(transcript)
    selection = resolve_inference(provider, model)
    inference_api_key(selection)
    analysis = storage.create_saved_analysis(job_id, name, view, prompt,
                                             selection.provider, selection.model)
    return run_saved_analysis(storage, analysis, transcript)
