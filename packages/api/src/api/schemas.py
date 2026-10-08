"""Pydantic schemas for API requests and responses."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Request body for creating a new job."""
    url: str = Field(..., description="YouTube video or X/Twitter post URL")
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
    video_available: bool = False
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
    duration: Optional[float] = None
    video_available: bool = False
    transcript_text: str
    words: List[WordResponse] = []
    utterances: List[UtteranceResponse] = []


class PassageResponse(BaseModel):
    """A passage grounded in source utterances, with millisecond timings."""
    id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    utterance_start: int = Field(ge=0)
    utterance_end: int = Field(ge=0)
    word_start: Optional[int] = Field(default=None, ge=0)
    word_end: Optional[int] = Field(default=None, ge=0)
    match_start: Optional[int] = Field(default=None, ge=0)
    match_end: Optional[int] = Field(default=None, ge=0)


class NavigationNodeResponse(BaseModel):
    """A chronological section or a topic with recurring source passages."""
    id: str
    title: str
    summary: str = ""
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    children: List["NavigationNodeResponse"] = Field(default_factory=list)
    occurrences: List[PassageResponse] = Field(default_factory=list)


class InferenceRequest(BaseModel):
    provider: Optional[Literal["kimi", "fireworks"]] = None
    model: Optional[str] = Field(default=None, min_length=1, max_length=300)


class SavedAnalysisCreate(InferenceRequest):
    """Create a named analysis without replacing another saved result."""
    name: str = Field(min_length=1, max_length=200)
    view: Literal["timeline", "topics"]
    prompt: str = Field(default="", max_length=10000)


class SavedAnalysisRegenerate(InferenceRequest):
    """Optional settings for a new version of an existing analysis."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    view: Optional[Literal["timeline", "topics"]] = None
    prompt: Optional[str] = Field(default=None, max_length=10000)


class SavedAnalysisResponse(BaseModel):
    """A named, independently saved summary and visualization."""
    id: str
    job_id: str
    name: str
    view: Optional[Literal["timeline", "topics"]] = None
    prompt: str = ""
    status: str
    summary: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    nodes: List[NavigationNodeResponse] = Field(default_factory=list)
    model: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class InferenceModelResponse(BaseModel):
    id: str
    name: str
    context_length: Optional[int] = None


class InferenceProviderResponse(BaseModel):
    id: Literal["kimi", "fireworks"]
    label: str
    configured: bool
    default_model: str
    models: List[InferenceModelResponse] = Field(default_factory=list)
    catalog_status: Literal["ready", "stale", "error", "unconfigured"]
    catalog_updated_at: Optional[str] = None
    catalog_error: Optional[str] = None


class InferenceOptionsResponse(BaseModel):
    default_provider: Literal["kimi", "fireworks"]
    default_model: str
    providers: List[InferenceProviderResponse]


class PassageSearchRequest(InferenceRequest):
    query: str = Field(min_length=1, max_length=500)
    mode: Literal["exact", "semantic"] = "exact"


class PassageSearchResponse(BaseModel):
    query: str
    mode: Literal["exact", "semantic"]
    results: List[PassageResponse] = Field(default_factory=list)
    error: Optional[str] = None


class JobDetailResponse(BaseModel):
    """Job with transcript details."""
    job: JobResponse
    transcript: Optional[TranscriptResponse] = None
    analyses: List[SavedAnalysisResponse] = Field(default_factory=list)


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
