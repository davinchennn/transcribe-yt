"""Transcript summary analysis using the selected inference provider."""

from typing import Optional
from transcripts.inference import resolve_inference
from transcripts.llm import request_json
from transcripts.models import Analysis, AnalysisStatus

SYSTEM_PROMPT = """You are a transcript analyst. Given a transcript, provide a concise analysis.

You MUST respond with valid JSON in this exact format:
{"summary": "A 2-3 sentence summary of the transcript content.", "key_points": ["Point 1", "Point 2", "Point 3"]}

Rules:
- summary: 2-3 sentences capturing the main topic and conclusions
- key_points: 3-7 bullet points covering the most important ideas discussed
- Respond ONLY with JSON, no markdown fences or extra text"""



def analyze_transcript(transcript_text: str, job_id: str, api_key: Optional[str] = None,
                       *, provider: Optional[str] = None, model: Optional[str] = None) -> Analysis:
    analysis = Analysis(job_id=job_id, status=AnalysisStatus.PROCESSING)
    try:
        selection = resolve_inference(provider, model)
        analysis.provider, analysis.model = selection.provider, selection.model
        result = request_json(SYSTEM_PROMPT, transcript_text, api_key,
                              provider=selection.provider, model=selection.model)
        summary, points = result.get("summary"), result.get("key_points")
        if not isinstance(summary, str) or not summary.strip() or not isinstance(points, list) or any(not isinstance(p, str) for p in points):
            raise ValueError("Analysis response must contain a summary and a list of key points")
        analysis.summary, analysis.key_points = summary, points
        analysis.status = AnalysisStatus.COMPLETED
    except Exception as exc:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = str(exc)
    return analysis
