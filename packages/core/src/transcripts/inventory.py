"""Read saved video inventories without initializing storage or changing records."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from transcripts.config import get_storage_backend, get_storage_path
from transcripts.sources import parse_video_source
from transcripts.models import Word, derive_utterances


def _transcript_content(data: Dict[str, Any]) -> Dict[str, Any]:
    words = [Word(**word) for word in data.get("words") or []]
    utterances = derive_utterances(words)
    return {
        **data,
        "utterances": [vars(utterance) for utterance in utterances] if words else data.get("utterances") or [],
    }


def _json_array(value: Optional[str]) -> List[Any]:
    result = json.loads(value) if value else []
    if not isinstance(result, list):
        raise ValueError("Expected a JSON array in saved transcript or analysis data")
    return result


def _file_info(value: Optional[str]) -> Dict[str, Any]:
    path = Path(value).expanduser().resolve() if value else None
    return {
        "path": value,
        "resolved_path": str(path) if path else None,
        "exists": bool(path and path.is_file()),
    }


def _transcript_info(data: Optional[Dict[str, Any]], location: str = "database") -> Dict[str, Any]:
    words = (data.get("words") or []) if data is not None else []
    if not isinstance(words, list):
        raise ValueError("Expected a word array in saved transcript data")
    return {
        "available": data is not None,
        "storage": location if data is not None else None,
        "duration_seconds": data.get("duration") if data is not None else None,
        "word_count": len(words),
        "timings_available": bool(words) and all(
            isinstance(word, dict)
            and isinstance(word.get("start"), (int, float))
            and isinstance(word.get("end"), (int, float))
            and 0 <= word["start"] <= word["end"]
            for word in words
        ),
    }


def _analysis_info(data: Optional[Dict[str, Any]], supported: bool = True) -> Dict[str, Any]:
    return {
        "status": data.get("status") if data is not None else "not_created" if supported else "not_supported",
        "model": data.get("model") if data is not None else None,
        "provider": data.get("provider", "kimi") if data is not None else None,
        "created_at": data.get("created_at") if data is not None else None,
        "updated_at": data.get("updated_at") if data is not None else None,
        "error": data.get("error") if data is not None else None,
    }


def _navigation_info(data: Optional[Dict[str, Any]], supported: bool = True) -> Dict[str, Any]:
    info = _analysis_info(data, supported)
    nodes = _json_array(data.get("nodes")) if data is not None else []
    stack = [(node, 1) for node in nodes]
    node_count = 0
    depth = 0
    occurrence_count = 0
    while stack:
        node, level = stack.pop()
        node_count += 1
        depth = max(depth, level)
        occurrence_count += len(node.get("occurrences") or [])
        stack.extend((child, level + 1) for child in node.get("children") or [])
    return {**info, "node_count": node_count, "depth": depth, "occurrence_count": occurrence_count}


def _job_info(job: Dict[str, Any]) -> Dict[str, Any]:
    source = parse_video_source(job.get("url") or "")
    return {
        "id": job["id"],
        "title": job.get("title"),
        "source": source.provider if source else None,
        "url": job.get("url"),
        "canonical_url": source.canonical_url if source else None,
        "stage": job.get("stage", "pending"),
        "transcription_provider": job.get("provider"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
        "files": {
            "video": {**_file_info(job.get("video_file")), "keep": bool(job.get("keep_video", True))},
            "audio": {**_file_info(job.get("audio_file")), "keep": bool(job.get("keep_audio", True))},
            "transcript_export": _file_info(job.get("transcript_file")),
        },
    }


def _matches(job: Dict[str, Any], query: Optional[str], source: Optional[str],
             job_id: Optional[str], stage: Optional[str]) -> bool:
    parsed = parse_video_source(job.get("url") or "")
    if source and (parsed is None or parsed.provider != source):
        return False
    if job_id and job["id"] != job_id:
        return False
    if stage and job.get("stage", "pending") != stage:
        return False
    fields = (job["id"], job.get("title") or "", job.get("url") or "")
    return not query or any(query.casefold() in field.casefold() for field in fields)


def _sqlite_jobs(path: Path, query: Optional[str], source: Optional[str],
                 job_id: Optional[str], stage: Optional[str], include_content: bool = False) -> List[Dict[str, Any]]:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        # Keep all inventory fields on one snapshot if processing is concurrent.
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "jobs" not in tables:
            raise ValueError("Storage database has no jobs table")
        result = []
        for row in connection.execute("SELECT * FROM jobs ORDER BY updated_at DESC, id"):
            job = dict(row)
            if not _matches(job, query, source, job_id, stage):
                continue
            item = _job_info(job)
            transcript = None
            if "transcripts" in tables:
                row = connection.execute(
                    ("SELECT * FROM transcripts WHERE job_id = ?" if include_content else
                     "SELECT duration, words FROM transcripts WHERE job_id = ?"), (job["id"],)
                ).fetchone()
                if row is not None:
                    transcript = {"duration": row["duration"], "words": _json_array(row["words"])}
                    if include_content:
                        transcript = {**dict(row), **transcript}
                        transcript["metadata"] = json.loads(transcript.get("metadata") or "{}")
                        transcript["utterances"] = _json_array(transcript.get("utterances"))
            item["transcript"] = _transcript_info(transcript)
            if include_content:
                item["transcript"] = {**item["transcript"], **_transcript_content(transcript)} if transcript is not None else item["transcript"]
            analysis = None
            if "analyses" in tables:
                row = connection.execute("SELECT * FROM analyses WHERE job_id = ?", (job["id"],)).fetchone()
                analysis = dict(row) if row is not None else None
            item["analysis"] = {
                **_analysis_info(analysis),
                "key_point_count": len(_json_array(analysis.get("key_points"))) if analysis else 0,
            }
            views = {}
            if "navigation_analyses" in tables:
                views = {row["view"]: dict(row) for row in connection.execute(
                    "SELECT * FROM navigation_analyses WHERE job_id = ?", (job["id"],)
                )}
            item["navigation"] = {view: _navigation_info(views.get(view)) for view in ("timeline", "topics")}
            result.append(item)
        return result
    finally:
        connection.close()


def _json_jobs(path: Path, query: Optional[str], source: Optional[str],
               job_id: Optional[str], stage: Optional[str], include_content: bool = False) -> List[Dict[str, Any]]:
    state = json.loads(path.read_text(encoding="utf-8"))
    jobs = sorted(state["jobs"].values(), key=lambda job: (job.get("updated_at") or "", job["id"]), reverse=True)
    result = []
    for job in jobs:
        if not _matches(job, query, source, job_id, stage):
            continue
        item = _job_info(job)
        transcript = None
        export = item["files"]["transcript_export"]
        if export["exists"]:
            export_path = Path(export["resolved_path"])
            transcript = json.loads(export_path.read_text(encoding="utf-8")) if export_path.suffix.lower() == ".json" else {}
            if include_content and export_path.suffix.lower() != ".json":
                transcript = {"transcript_text": export_path.read_text(encoding="utf-8")}
        item["transcript"] = _transcript_info(transcript, "file")
        if include_content and transcript is not None:
            item["transcript"] = {**item["transcript"], **_transcript_content(transcript)}
        item["analysis"] = {**_analysis_info(None, supported=False), "key_point_count": 0}
        item["navigation"] = {view: _navigation_info(None, supported=False) for view in ("timeline", "topics")}
        result.append(item)
    return result


def list_inventory(query: Optional[str] = None, source: Optional[str] = None,
                   job_id: Optional[str] = None, stage: Optional[str] = None,
                   backend: Optional[str] = None, storage_path: Optional[str] = None) -> Dict[str, Any]:
    """List data availability using existing SQLite records or legacy JSON exports.

    Paths follow the same environment and working-directory rules as the app,
    but discovery never creates directories, initializes schema, or takes a
    JSON write lock. SQLite reads include committed WAL data.
    """
    backend = get_storage_backend(backend)
    path = Path(storage_path or get_storage_path(backend, create_directory=False)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Storage file not found: {path}")
    reader = _sqlite_jobs if backend == "sqlite" else _json_jobs
    jobs = reader(path, query, source, job_id, stage)
    return {
        "storage": {"backend": backend, "path": str(path)},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
        "total": len(jobs),
    }


def show_transcript(job_id: str, backend: Optional[str] = None,
                    storage_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve one exact job and its transcript without initializing storage."""
    backend = get_storage_backend(backend)
    path = Path(storage_path or get_storage_path(backend, create_directory=False)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Storage file not found: {path}")
    reader = _sqlite_jobs if backend == "sqlite" else _json_jobs
    jobs = reader(path, None, None, job_id, None, include_content=True)
    if not jobs:
        raise ValueError(f"Job not found: {job_id}")
    if not jobs[0]["transcript"]["available"]:
        raise ValueError(f"No saved transcript for job: {job_id}")
    return {"storage": {"backend": backend, "path": str(path)}, "job": jobs[0]}
