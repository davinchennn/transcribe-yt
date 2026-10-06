"""Kimi Code transcript analysis client."""

import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional

from transcripts.config import get_kimi_code_api_key
from transcripts.models import Analysis, AnalysisStatus

KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_MODEL = "k3"

SYSTEM_PROMPT = """You are a transcript analyst. Given a transcript, provide a concise analysis.

You MUST respond with valid JSON in this exact format:
{"summary": "A 2-3 sentence summary of the transcript content.", "key_points": ["Point 1", "Point 2", "Point 3"]}

Rules:
- summary: 2-3 sentences capturing the main topic and conclusions
- key_points: 3-7 bullet points covering the most important ideas discussed
- Respond ONLY with JSON, no markdown fences or extra text"""


def analyze_transcript(transcript_text: str, job_id: str, api_key: Optional[str] = None) -> Analysis:
    """Analyze a transcript using Kimi API.

    Args:
        transcript_text: Full transcript text to analyze
        job_id: Job ID to associate the analysis with
        api_key: Optional Kimi Code API key (reads from env if not provided)

    Returns:
        Analysis object with results or error
    """
    now = datetime.utcnow().isoformat()
    analysis = Analysis(
        job_id=job_id,
        status=AnalysisStatus.PROCESSING,
        model=KIMI_MODEL,
        created_at=now,
        updated_at=now,
    )

    try:
        key = get_kimi_code_api_key(api_key)
    except ValueError as e:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = str(e)
        return analysis

    payload = json.dumps({
        "model": KIMI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
        "temperature": 1,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{KIMI_BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "transcripts/0.1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        analysis.status = AnalysisStatus.FAILED
        analysis.error = f"Kimi API error {e.code}: {body}"
        return analysis
    except urllib.error.URLError as e:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = f"Network error: {e.reason}"
        return analysis
    except Exception as e:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = f"Request failed: {e}"
        return analysis

    try:
        content = data["choices"][0]["message"]["content"]
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            # Remove opening fence (```json or ```)
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        result = json.loads(content)
        analysis.summary = result.get("summary", "")
        analysis.key_points = result.get("key_points", [])
        analysis.status = AnalysisStatus.COMPLETED
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = f"Failed to parse Kimi response: {e}"

    return analysis
