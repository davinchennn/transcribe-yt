"""Pydantic schemas for API requests and responses."""

from typing import List, Optional
from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Request body for creating a new job."""
    url: str = Field(..., description="YouTube video URL")
    keep_video: bool = Field(
        default=True,
        description="Whether to retain video file after transcription"
    )
    keep_audio: bool = Field(
        default=True,
        description="Whether to retain audio file after transcription"
    )


class JobResponse(BaseModel):
    """Response for a single job."""
    id: str
    url: str
    stage: str
    title: Optional[str] = None
    error: Optional[str] = None
    provider: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class WordResponse(BaseModel):
    """Word with timing information."""
    text: str
    start: int
    end: int
    confidence: Optional[float] = None
    speaker: Optional[str] = None


class UtteranceResponse(BaseModel):
    """Speaker-labeled utterance."""
    speaker: str
    text: str
    start: int
    end: int


class TranscriptResponse(BaseModel):
    """Full transcript response."""
    video_url: str
    title: str
    duration: Optional[int] = None
    transcript_text: str
    words: List[WordResponse] = []
    utterances: List[UtteranceResponse] = []


class AnalysisResponse(BaseModel):
    """Analysis response."""
    job_id: str
    status: str
    summary: Optional[str] = None
    key_points: List[str] = []
    model: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class JobDetailResponse(BaseModel):
    """Job with transcript details."""
    job: JobResponse
    transcript: Optional[TranscriptResponse] = None
    analysis: Optional[AnalysisResponse] = None


class JobListResponse(BaseModel):
    """List of jobs response."""
    jobs: List[JobResponse]
    total: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
