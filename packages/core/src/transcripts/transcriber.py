"""Transcription integration for multiple providers (AssemblyAI, Deepgram)."""

import time
from pathlib import Path
from typing import Dict, List, Optional, Literal
from abc import ABC, abstractmethod

import assemblyai as aai

from transcripts.config import get_api_key, get_deepgram_api_key
from transcripts.models import Transcript, Word, Utterance


class BaseTranscriber(ABC):
    """Base class for transcription providers."""

    @abstractmethod
    def transcribe_file(self, audio_file: str) -> Transcript:
        """Transcribe an audio or video file."""
        pass

    @abstractmethod
    def transcribe_url(self, audio_url: str) -> Transcript:
        """Transcribe an audio file from a URL."""
        pass


class AssemblyAITranscriber(BaseTranscriber):
    """Handles transcription using AssemblyAI."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize transcriber.

        Args:
            api_key: AssemblyAI API key (optional, will use config if not provided)
        """
        self.api_key = get_api_key(api_key)
        aai.settings.api_key = self.api_key
        self.transcriber = aai.Transcriber()

    def _extract_words(self, result) -> List[Word]:
        """Extract words from AssemblyAI result."""
        words = []
        if result.words:
            for word_data in result.words:
                words.append(
                    Word(
                        text=word_data.text,
                        start=word_data.start,
                        end=word_data.end,
                        confidence=word_data.confidence,
                        speaker=getattr(word_data, "speaker", None),
                    )
                )
        return words

    def _extract_utterances(self, result) -> List[Utterance]:
        """Extract utterances from AssemblyAI result."""
        utterances = []
        if result.utterances:
            for utterance_data in result.utterances:
                utterances.append(
                    Utterance(
                        speaker=utterance_data.speaker,
                        text=utterance_data.text,
                        start=utterance_data.start,
                        end=utterance_data.end,
                        confidence=getattr(utterance_data, "confidence", None),
                    )
                )
        return utterances

    def _build_transcript(self, result, source: str) -> Transcript:
        """Build Transcript from AssemblyAI result."""
        return Transcript(
            video_url="",  # Will be set by processor
            title="",  # Will be set by processor
            audio_file=source,
            transcript_text=result.text or "",
            words=self._extract_words(result),
            utterances=self._extract_utterances(result),
            metadata={
                "transcription_id": result.id,
                "status": result.status.value,
                "language_code": result.json_response.get("language_code"),
            },
        )

    def transcribe_file(
        self, audio_file: str, config: Optional[aai.TranscriptionConfig] = None
    ) -> Transcript:
        """
        Transcribe an audio or video file.

        Note: AssemblyAI supports both audio and video files directly.
        For video files, AssemblyAI automatically extracts the audio.

        Args:
            audio_file: Path to audio or video file
            config: Optional transcription configuration

        Returns:
            Transcript object with transcription results
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise FileNotFoundError(f"File not found: {audio_file}")

        try:
            if config is None:
                config = aai.TranscriptionConfig(speaker_labels=True)

            result = self.transcriber.transcribe(audio_file, config=config)

            if result.status == aai.TranscriptStatus.error:
                raise RuntimeError(f"Transcription failed: {result.error}")

            return self._build_transcript(result, audio_file)

        except Exception as e:
            raise RuntimeError(f"Failed to transcribe audio: {str(e)}") from e

    def transcribe_url(
        self, audio_url: str, config: Optional[aai.TranscriptionConfig] = None
    ) -> Transcript:
        """
        Transcribe an audio file from a URL.

        Args:
            audio_url: URL to audio file
            config: Optional transcription configuration

        Returns:
            Transcript object with transcription results
        """
        try:
            if config is None:
                config = aai.TranscriptionConfig(speaker_labels=True)

            result = self.transcriber.transcribe(audio_url, config=config)

            if result.status == aai.TranscriptStatus.error:
                raise RuntimeError(f"Transcription failed: {result.error}")

            return self._build_transcript(result, audio_url)

        except Exception as e:
            raise RuntimeError(f"Failed to transcribe audio URL: {str(e)}") from e


class DeepgramTranscriber(BaseTranscriber):
    """Handles transcription using Deepgram."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize transcriber.

        Args:
            api_key: Deepgram API key (optional, will use config if not provided)
        """
        try:
            from deepgram import DeepgramClient
            self.DeepgramClient = DeepgramClient
        except ImportError:
            raise ImportError(
                "Deepgram SDK not installed. Install it with: pip install deepgram-sdk"
            )

        self.api_key = get_deepgram_api_key(api_key)
        self.client = DeepgramClient(api_key=self.api_key)

    def _extract_words(self, alternative) -> List[Word]:
        """Extract words from Deepgram alternative (handles ms conversion)."""
        words = []
        if alternative.words:
            for word_data in alternative.words:
                start_ms = int(word_data.start * 1000) if word_data.start else 0
                end_ms = int(word_data.end * 1000) if word_data.end else 0
                speaker = None
                if hasattr(word_data, "speaker") and word_data.speaker is not None:
                    speaker = str(word_data.speaker)
                words.append(
                    Word(
                        text=word_data.word,
                        start=start_ms,
                        end=end_ms,
                        confidence=getattr(word_data, "confidence", None),
                        speaker=speaker,
                    )
                )
        return words

    def _extract_utterances(self, result) -> List[Utterance]:
        """Extract utterances from Deepgram result."""
        utterances = []
        if hasattr(result, "utterances") and result.utterances:
            for utterance_data in result.utterances:
                start_ms = int(utterance_data.start * 1000) if utterance_data.start else 0
                end_ms = int(utterance_data.end * 1000) if utterance_data.end else 0
                utterances.append(
                    Utterance(
                        speaker=str(utterance_data.speaker) if utterance_data.speaker is not None else "UNKNOWN",
                        text=utterance_data.transcript or "",
                        start=start_ms,
                        end=end_ms,
                        confidence=getattr(utterance_data, "confidence", None),
                    )
                )
        return utterances

    def _build_transcript(self, response, source: str, model: str, language: str, include_metadata: bool = False) -> Transcript:
        """Build Transcript from Deepgram response."""
        result = response.results
        if not result:
            raise RuntimeError("Transcription returned empty results")

        channel = result.channels[0]
        alternative = channel.alternatives[0]

        metadata = {
            "transcription_provider": "deepgram",
            "model": model,
            "language": language,
            "request_id": getattr(response, "request_id", None),
        }
        if include_metadata and hasattr(result, "metadata"):
            metadata["metadata"] = result.metadata.model_dump()

        return Transcript(
            video_url="",  # Will be set by processor
            title="",  # Will be set by processor
            audio_file=source,
            transcript_text=alternative.transcript or "",
            words=self._extract_words(alternative),
            utterances=self._extract_utterances(result),
            metadata=metadata,
        )

    def transcribe_file(self, audio_file: str, **kwargs) -> Transcript:
        """
        Transcribe an audio or video file.

        Note: Deepgram supports both audio and video files directly.
        For video files, Deepgram automatically extracts the audio.

        Args:
            audio_file: Path to audio or video file
            **kwargs: Additional options (model, language, etc.)

        Returns:
            Transcript object with transcription results
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise FileNotFoundError(f"File not found: {audio_file}")

        try:
            model = kwargs.get("model", "nova-2")
            language = kwargs.get("language", "en")
            smart_format = kwargs.get("smart_format", True)
            # SDK 5.3 exposes newer API parameters through request_options.
            # Do not send legacy diarize together with diarize_model.
            diarization_options = {}
            if kwargs.get("diarize", True):
                diarization_options["diarize_model"] = kwargs.get("diarize_model", "v2")
            utterances = kwargs.get("utterances", True)

            def file_chunks():
                with open(audio_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk

            response = self.client.listen.v1.media.transcribe_file(
                request=file_chunks(),
                model=model,
                language=language,
                smart_format=smart_format,
                request_options={"additional_query_parameters": diarization_options},
                utterances=utterances,
            )

            return self._build_transcript(response, audio_file, model, language, include_metadata=True)

        except Exception as e:
            raise RuntimeError(f"Failed to transcribe audio with Deepgram: {str(e)}") from e

    def transcribe_url(self, audio_url: str, **kwargs) -> Transcript:
        """
        Transcribe an audio file from a URL.

        Args:
            audio_url: URL to audio file
            **kwargs: Additional options (model, language, etc.)

        Returns:
            Transcript object with transcription results
        """
        try:
            model = kwargs.get("model", "nova-2")
            language = kwargs.get("language", "en")
            smart_format = kwargs.get("smart_format", True)
            # SDK 5.3 exposes newer API parameters through request_options.
            # Do not send legacy diarize together with diarize_model.
            diarization_options = {}
            if kwargs.get("diarize", True):
                diarization_options["diarize_model"] = kwargs.get("diarize_model", "v2")
            utterances = kwargs.get("utterances", True)

            response = self.client.listen.v1.media.transcribe_url(
                url=audio_url,
                model=model,
                language=language,
                smart_format=smart_format,
                request_options={"additional_query_parameters": diarization_options},
                utterances=utterances,
            )

            return self._build_transcript(response, audio_url, model, language)

        except Exception as e:
            raise RuntimeError(f"Failed to transcribe audio URL with Deepgram: {str(e)}") from e


# Maintain backward compatibility: Transcriber defaults to Deepgram
Transcriber = DeepgramTranscriber


def create_transcriber(
    provider: Literal["assemblyai", "deepgram"] = "assemblyai",
    api_key: Optional[str] = None,
) -> BaseTranscriber:
    """
    Factory function to create a transcriber instance.

    Args:
        provider: Transcription provider ("assemblyai" or "deepgram")
        api_key: Optional API key (will use config if not provided)

    Returns:
        Transcriber instance (AssemblyAITranscriber or DeepgramTranscriber)

    Example:
        >>> transcriber = create_transcriber("deepgram")
        >>> transcript = transcriber.transcribe_file("audio.mp3")
    """
    if provider == "assemblyai":
        return AssemblyAITranscriber(api_key=api_key)
    elif provider == "deepgram":
        return DeepgramTranscriber(api_key=api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}. Choose 'assemblyai' or 'deepgram'")
