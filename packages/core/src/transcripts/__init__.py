"""Transcripts package."""

__version__ = "0.1.0"

from transcripts.downloader import YouTubeDownloader
from transcripts.models import Transcript, Word, Utterance
from transcripts.processor import TranscriptProcessor
from transcripts.transcriber import (
    Transcriber,
    AssemblyAITranscriber,
    DeepgramTranscriber,
    create_transcriber,
    BaseTranscriber,
)
from transcripts.converter import (
    convert_transcript_to_text,
    convert_dict_to_text,
    get_available_formats,
)

__all__ = [
    "YouTubeDownloader",
    "Transcriber",  # Backward compatibility - defaults to AssemblyAI
    "AssemblyAITranscriber",
    "DeepgramTranscriber",
    "create_transcriber",
    "BaseTranscriber",
    "TranscriptProcessor",
    "Transcript",
    "Word",
    "Utterance",
    "convert_transcript_to_text",
    "convert_dict_to_text",
    "get_available_formats",
]

