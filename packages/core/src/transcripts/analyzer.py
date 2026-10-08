"""Transcript summary analysis using the selected inference provider."""

import json
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

def with_focus_prompt(system_prompt: str, prompt: str = "") -> str:
    """Supplement analysis instructions while preserving mandatory formats."""
    if not prompt.strip():
        return system_prompt
    return system_prompt + "\n\nUser-requested analysis focus:\n" + json.dumps(prompt.strip(), ensure_ascii=False) + """
Use this focus to shape emphasis, organization, labels, and summaries where supported
by the source. All required output schemas, factual grounding, source references,
summary limits, and coverage rules above remain mandatory. A chronological timeline
must still cover the entire source, including passages outside the requested focus.
"""


def analyze_transcript(transcript_text: str, job_id: str, api_key: Optional[str] = None,
                       *, provider: Optional[str] = None, model: Optional[str] = None,
                       prompt: str = "") -> Analysis:
    analysis = Analysis(job_id=job_id, status=AnalysisStatus.PROCESSING)
    try:
        selection = resolve_inference(provider, model)
        analysis.provider, analysis.model = selection.provider, selection.model
        result = request_json(with_focus_prompt(SYSTEM_PROMPT, prompt), transcript_text, api_key,
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
