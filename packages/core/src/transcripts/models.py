"""Data models for transcripts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Stage(Enum):
    """Represents the current step in the transcription pipeline."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a single transcription task with progress tracking."""

    id: str  # YouTube video ID
    url: str  # Original YouTube URL
    stage: Stage = Stage.PENDING
    title: Optional[str] = None
    error: Optional[str] = None
    provider: Optional[str] = None  # Transcription provider (deepgram, assemblyai)
    video_file: Optional[str] = None
    audio_file: Optional[str] = None
    transcript_file: Optional[str] = None
    keep_video: bool = True  # Whether to retain video file after transcription
    keep_audio: bool = True  # Whether to retain audio file after transcription
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "url": self.url,
            "stage": self.stage.value,
            "title": self.title,
            "error": self.error,
            "provider": self.provider,
            "video_file": self.video_file,
            "audio_file": self.audio_file,
            "transcript_file": self.transcript_file,
            "keep_video": self.keep_video,
            "keep_audio": self.keep_audio,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Create Job from dictionary."""
        return cls(
            id=data["id"],
            url=data["url"],
            stage=Stage(data.get("stage", "pending")),
            title=data.get("title"),
            error=data.get("error"),
            provider=data.get("provider"),
            video_file=data.get("video_file"),
            audio_file=data.get("audio_file"),
            transcript_file=data.get("transcript_file"),
            keep_video=data.get("keep_video", True),
            keep_audio=data.get("keep_audio", True),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
        )


@dataclass
class Word:
    """Represents a word in the transcript with timing information."""

    text: str
    start: int  # Start time in milliseconds
    end: int  # End time in milliseconds
    confidence: Optional[float] = None
    speaker: Optional[str] = None  # Speaker label (e.g., "A", "B") if diarization enabled


@dataclass
class Utterance:
    """Represents a spoken segment by a specific speaker."""

    speaker: str  # Speaker label (e.g., "A", "B")
    text: str  # Spoken text
    start: int  # Start time in milliseconds
    end: int  # End time in milliseconds
    confidence: Optional[float] = None


class AnalysisStatus(Enum):
    """Status of a transcript analysis."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Analysis:
    """Represents an AI-generated analysis of a transcript."""

    job_id: str
    status: AnalysisStatus = AnalysisStatus.PENDING
    summary: Optional[str] = None
    key_points: List[str] = field(default_factory=list)
    model: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert analysis to dictionary for JSON serialization."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "summary": self.summary,
            "key_points": self.key_points,
            "model": self.model,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Analysis":
        """Create Analysis from dictionary."""
        return cls(
            job_id=data["job_id"],
            status=AnalysisStatus(data.get("status", "pending")),
            summary=data.get("summary"),
            key_points=data.get("key_points", []),
            model=data.get("model"),
            error=data.get("error"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
        )


def derive_utterances(words: List["Word"], pause_threshold_ms: int = 1000) -> List[Utterance]:
    """
    Group words into utterances by speaker and pauses.

    Utterances are created when:
    - Speaker changes between consecutive words
    - Pause between words exceeds the threshold

    Args:
        words: List of Word objects with timing and optional speaker labels
        pause_threshold_ms: Pause duration (ms) that triggers a new utterance

    Returns:
        List of Utterance objects grouped by speaker/pauses
    """
    if not words:
        return []

    utterances = []
    current_speaker = words[0].speaker
    current_words = [words[0]]

    for word in words[1:]:
        # Calculate pause between this word and previous
        pause = word.start - current_words[-1].end

        # New utterance if speaker changes or pause exceeds threshold
        if word.speaker != current_speaker or pause > pause_threshold_ms:
            # Finish current utterance
            utterances.append(Utterance(
                speaker=current_speaker or "SPEAKER",
                text=" ".join(w.text for w in current_words),
                start=current_words[0].start,
                end=current_words[-1].end,
            ))
            # Start new utterance
            current_speaker = word.speaker
            current_words = [word]
        else:
            current_words.append(word)

    # Don't forget the last utterance
    if current_words:
        utterances.append(Utterance(
            speaker=current_speaker or "SPEAKER",
            text=" ".join(w.text for w in current_words),
            start=current_words[0].start,
            end=current_words[-1].end,
        ))

    return utterances


@dataclass
class Transcript:
    """Represents a complete transcript with metadata."""

    video_url: str
    title: str
    duration: Optional[int] = None  # Duration in seconds
    audio_file: Optional[str] = None
    video_file: Optional[str] = None
    transcript_text: str = ""
    words: List[Word] = field(default_factory=list)
    utterances: List[Utterance] = field(default_factory=list)  # Speaker-segmented utterances
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert transcript to dictionary for JSON serialization."""
        return {
            "video_url": self.video_url,
            "title": self.title,
            "duration": self.duration,
            "audio_file": self.audio_file,
            "video_file": self.video_file,
            "transcript_text": self.transcript_text,
            "words": [
                {
                    "text": word.text,
                    "start": word.start,
                    "end": word.end,
                    "confidence": word.confidence,
                    "speaker": word.speaker,
                }
                for word in self.words
            ],
            "utterances": [
                {
                    "speaker": utterance.speaker,
                    "text": utterance.text,
                    "start": utterance.start,
                    "end": utterance.end,
                    "confidence": utterance.confidence,
                }
                for utterance in self.utterances
            ],
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transcript":
        """Create Transcript from dictionary."""
        words = [
            Word(
                text=w["text"],
                start=w["start"],
                end=w["end"],
                confidence=w.get("confidence"),
                speaker=w.get("speaker"),
            )
            for w in data.get("words", [])
        ]
        utterances = [
            Utterance(
                speaker=u["speaker"],
                text=u["text"],
                start=u["start"],
                end=u["end"],
                confidence=u.get("confidence"),
            )
            for u in data.get("utterances", [])
        ]
        return cls(
            video_url=data["video_url"],
            title=data["title"],
            duration=data.get("duration"),
            audio_file=data.get("audio_file"),
            video_file=data.get("video_file"),
            transcript_text=data.get("transcript_text", ""),
            words=words,
            utterances=utterances,
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            metadata=data.get("metadata", {}),
        )

