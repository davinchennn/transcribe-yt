"""Main processor that orchestrates download, extraction, and transcription."""

import json
from pathlib import Path
from typing import List, Optional, Literal, TYPE_CHECKING

from transcripts.downloader import YouTubeDownloader
from transcripts.models import Transcript, Job, Stage
from transcripts.transcriber import create_transcriber, BaseTranscriber
from transcripts.config import get_transcription_provider
from transcripts.converter import convert_transcript_to_text

if TYPE_CHECKING:
    from transcripts.state import StateManager


class TranscriptProcessor:
    """Orchestrates the full pipeline: download → extract → transcribe."""

    def __init__(
        self,
        download_dir: str = "downloads",
        transcripts_dir: str = "transcripts",
        api_key: Optional[str] = None,
        provider: Optional[Literal["assemblyai", "deepgram"]] = None,
        output_format: Literal["json", "txt", "both", "none"] = "both",
        txt_format: str = "conversation",
        state_manager: Optional["StateManager"] = None,
        keep_video: bool = True,
        keep_audio: bool = True,
    ):
        """
        Initialize processor.

        Args:
            download_dir: Directory for downloaded files
            transcripts_dir: Directory for transcript JSON files
            api_key: API key for the selected provider (optional)
            provider: Transcription provider ("assemblyai" or "deepgram").
                     If not provided, will use TRANSCRIPTION_PROVIDER environment variable
                     or default to "deepgram".
            output_format: Output format - "json", "txt", or "both" (default: "both")
            txt_format: Text format type when output_format includes "txt".
                       Options: "conversation", "timestamped", "markdown", "simple", "compact"
                       (default: "conversation")
            state_manager: Optional StateManager for job progress tracking
            keep_video: Whether to retain video file after transcription (default: True)
            keep_audio: Whether to retain audio file after transcription (default: True)
        """
        self.downloader = YouTubeDownloader(download_dir=download_dir)
        self.provider = get_transcription_provider(provider)
        self.transcriber = create_transcriber(provider=self.provider, api_key=api_key)
        self.transcripts_dir = Path(transcripts_dir)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.output_format = output_format
        self.txt_format = txt_format
        self.state_manager = state_manager
        self.keep_video = keep_video
        self.keep_audio = keep_audio

    def process_video(
        self,
        url: str,
        download_video: bool = True,
        extract_audio: bool = True,
    ) -> Transcript:
        """
        Process a single video: download, extract audio (optional), and transcribe.

        Supports resume: if a job exists for this URL and has intermediate files,
        processing will skip completed stages.

        Args:
            url: YouTube video or X/Twitter post URL
            download_video: Whether to download the video file
            extract_audio: Whether to extract audio first.
                          If False, video file will be uploaded directly to the transcription provider
                          (both providers support video files and extract audio automatically)

        Returns:
            Transcript object
        """
        job = None
        resume_stage = None

        # Create or get existing job if state manager is available
        if self.state_manager:
            job = self.state_manager.create_job(
                url,
                keep_video=self.keep_video,
                keep_audio=self.keep_audio,
            )

            # Set provider if not already set (for new jobs or retries)
            if not job.provider:
                job.provider = self.provider
                self.state_manager.update_job(job)

            # Check if this is a resume scenario
            if job.stage == Stage.COMPLETED:
                print(f"Job already completed: {job.title or job.id}")
                # Return a minimal transcript for completed jobs
                transcript = Transcript(video_url=url, title=job.title or "")
                transcript.video_file = job.video_file
                transcript.audio_file = job.audio_file
                return transcript

            # Verify files exist and get adjusted stage
            resume_stage = self.state_manager.verify_stage_files(job)
            if resume_stage != job.stage:
                print(f"Adjusting stage from {job.stage.value} to {resume_stage.value} (missing files)")
                job.stage = resume_stage
                self.state_manager.update_job(job)

        try:
            video_file = None
            audio_file = None
            metadata = {}

            # Check if we can skip download (resume scenario)
            skip_download = False
            if job and resume_stage and resume_stage not in (Stage.PENDING, Stage.FAILED):
                if job.video_file and Path(job.video_file).exists():
                    video_file = job.video_file
                    skip_download = True
                    print(f"Resuming: using existing video file {video_file}")

            # Download stage
            if not skip_download:
                if self.state_manager and job:
                    self.state_manager.set_stage(job.id, Stage.DOWNLOADING)

                video_file, audio_file, metadata = self.downloader.download_video(
                    url, extract_audio=extract_audio
                )

                # Update job with file paths
                if self.state_manager and job:
                    job.video_file = video_file
                    job.audio_file = audio_file
                    job.title = metadata.get("title", "")
                    self.state_manager.update_job(job)
            else:
                # Get metadata from existing files or job
                metadata = {"title": job.title} if job else {}
                # Check if audio already exists
                if job and job.audio_file and Path(job.audio_file).exists():
                    audio_file = job.audio_file
                    print(f"Resuming: using existing audio file {audio_file}")

            # Extract audio stage (if needed and not already done)
            # Note: If we have video but no audio in a resume scenario,
            # we re-download with extract_audio=True (yt-dlp handles extraction)
            if extract_audio and not audio_file:
                if self.state_manager and job:
                    self.state_manager.set_stage(job.id, Stage.EXTRACTING)

                # Re-run download with extract_audio to get audio file
                _, audio_file, dl_metadata = self.downloader.download_video(
                    url, extract_audio=True
                )
                metadata.update(dl_metadata)

                if self.state_manager and job:
                    job.audio_file = audio_file
                    self.state_manager.update_job(job)

            # Determine which file to transcribe
            file_to_transcribe = audio_file if audio_file else video_file

            if not file_to_transcribe:
                raise RuntimeError("Failed to download video or extract audio file")

            # Transcription stage
            if self.state_manager and job:
                self.state_manager.set_stage(job.id, Stage.TRANSCRIBING)

            transcript = self.transcriber.transcribe_file(file_to_transcribe)

            # Fill in metadata
            transcript.video_url = url
            transcript.title = metadata.get("title", "") or (job.title if job else "")
            transcript.duration = metadata.get("duration")
            transcript.video_file = video_file
            transcript.audio_file = audio_file
            transcript.metadata.update(metadata)

            # Saving stage
            if self.state_manager and job:
                self.state_manager.set_stage(job.id, Stage.SAVING)

            transcript_file = self._save_transcript(transcript, job_id=job.id if job else None)

            # Update job with transcript file path
            if self.state_manager and job:
                job.transcript_file = transcript_file
                self.state_manager.update_job(job)

            # Mark completed
            if self.state_manager and job:
                self.state_manager.set_stage(job.id, Stage.COMPLETED)

            # Clean up files based on retention settings (only on success)
            if job:
                self._cleanup_files(job)

            return transcript

        except Exception as e:
            # Mark job as failed - files are retained for debugging/retry
            if self.state_manager and job:
                self.state_manager.set_stage(job.id, Stage.FAILED, error=str(e))
            raise

    def process_playlist(
        self,
        url: str,
        download_video: bool = True,
        extract_audio: bool = True,
    ) -> List[Transcript]:
        """
        Process a playlist: download all videos, extract audio (optional), and transcribe.

        Args:
            url: YouTube playlist URL
            download_video: Whether to download video files
            extract_audio: Whether to extract audio first.
                          If False, video files will be uploaded directly to the transcription provider

        Returns:
            List of Transcript objects
        """

        # Download playlist
        results = self.downloader.download_playlist(url, extract_audio=extract_audio)

        transcripts = []

        for result in results:
            # Use audio file if extracted, otherwise use video file
            audio_file = result.get("audio_file")
            video_file = result.get("video_file")
            file_to_transcribe = audio_file if audio_file else video_file

            if not file_to_transcribe:
                continue

            # Transcribe (both providers support both audio and video files)
            transcript = self.transcriber.transcribe_file(file_to_transcribe)

            # Fill in metadata
            video_url = result.get("url", "")
            metadata = result.get("metadata", {})
            transcript.video_url = video_url
            transcript.title = metadata.get("title", "")
            transcript.duration = metadata.get("duration")
            transcript.video_file = result.get("video_file")
            transcript.audio_file = audio_file
            transcript.metadata.update(metadata)

            # Save transcript
            self._save_transcript(transcript)

            transcripts.append(transcript)

        return transcripts

    def process_batch(
        self,
        urls: List[str],
        download_video: bool = True,
        extract_audio: bool = True,
    ) -> List[Transcript]:
        """
        Process multiple videos from a list of URLs.

        Args:
            urls: List of YouTube video or X/Twitter post URLs
            download_video: Whether to download video files
            extract_audio: Whether to extract audio first.
                          If False, video files will be uploaded directly to the transcription provider

        Returns:
            List of Transcript objects
        """
        transcripts = []

        for url in urls:
            try:
                transcript = self.process_video(
                    url, download_video=download_video, extract_audio=extract_audio
                )
                transcripts.append(transcript)
            except Exception as e:
                print(f"Error processing {url}: {str(e)}")
                continue

        return transcripts

    def _save_transcript(self, transcript: Transcript, job_id: Optional[str] = None) -> Optional[str]:
        """
        Save transcript to database and optionally to file(s).

        Args:
            transcript: Transcript object to save
            job_id: Job ID to link transcript to in database

        Returns:
            Path to the primary transcript file (if files saved), else None
        """
        from datetime import datetime

        # Save to database if we have a job_id and state_manager
        if job_id and self.state_manager:
            try:
                # Access the storage backend directly for transcript operations
                storage = self.state_manager._storage
                if hasattr(storage, 'save_transcript'):
                    storage.save_transcript(job_id, transcript)
                    print(f"Transcript saved to database")
            except Exception as e:
                print(f"Warning: Failed to save transcript to database: {e}")

        # File output is now optional - only save if output_format is not "none"
        if self.output_format == "none":
            return None

        # Create kebab-case filename from title
        safe_title = self._to_kebab_case(transcript.title or "transcript")

        # Determine base filename (without extension)
        base_filename = safe_title
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        saved_files = []

        # Save JSON file if requested
        if self.output_format in ("json", "both"):
            json_filename = f"{base_filename}.json"
            json_filepath = self.transcripts_dir / json_filename

            # If file exists, add timestamp
            if json_filepath.exists():
                json_filename = f"{base_filename}-{timestamp}.json"
                json_filepath = self.transcripts_dir / json_filename

            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump(transcript.to_dict(), f, indent=2, ensure_ascii=False)

            saved_files.append(str(json_filepath))

        # Save TXT file if requested
        if self.output_format in ("txt", "both"):
            txt_filename = f"{base_filename}.txt"
            txt_filepath = self.transcripts_dir / txt_filename

            # If file exists, add timestamp
            if txt_filepath.exists():
                txt_filename = f"{base_filename}-{timestamp}.txt"
                txt_filepath = self.transcripts_dir / txt_filename

            # Convert transcript to text format
            text_content = convert_transcript_to_text(transcript, format_type=self.txt_format)

            with open(txt_filepath, "w", encoding="utf-8") as f:
                f.write(text_content)

            saved_files.append(str(txt_filepath))

        # Print saved files
        if saved_files:
            if len(saved_files) == 1:
                print(f"Transcript file: {saved_files[0]}")
            else:
                print("Transcript files:")
                for filepath in saved_files:
                    print(f"  - {filepath}")

        # Return primary file path (JSON preferred, else TXT)
        return saved_files[0] if saved_files else None

    @staticmethod
    def _to_kebab_case(text: str) -> str:
        """Convert text to kebab-case filename."""
        import re
        
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*()[]{}'
        for char in invalid_chars:
            text = text.replace(char, "")
        
        # Convert to lowercase
        text = text.lower()
        
        # Replace spaces, underscores, and pipes with hyphens
        text = text.replace(" ", "-").replace("_", "-").replace("|", "-")
        
        # Replace multiple consecutive hyphens with single hyphen
        text = re.sub(r'-+', '-', text)
        
        # Remove leading/trailing hyphens, dots, and spaces
        text = text.strip("- .")
        
        # Limit length
        if len(text) > 200:
            text = text[:200]
        
        return text

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize filename for filesystem compatibility (legacy method)."""
        return TranscriptProcessor._to_kebab_case(filename)

    def _cleanup_files(self, job: "Job") -> None:
        """Clean up files based on retention settings.

        Called after successful transcription (Stage.COMPLETED).
        Files are NOT deleted when transcription fails.

        Args:
            job: Job object with retention preferences and file paths
        """
        # Only clean up if job completed successfully
        if job.stage != Stage.COMPLETED:
            return

        # Delete video file if not keeping
        if not job.keep_video and job.video_file:
            try:
                video_path = Path(job.video_file)
                if video_path.exists():
                    video_path.unlink()
                    print(f"Deleted video file: {job.video_file}")
            except Exception as e:
                # Log warning but don't fail the job
                print(f"Warning: Failed to delete video file: {e}")

        # Delete audio file if not keeping
        if not job.keep_audio and job.audio_file:
            try:
                audio_path = Path(job.audio_file)
                if audio_path.exists():
                    audio_path.unlink()
                    print(f"Deleted audio file: {job.audio_file}")
            except Exception as e:
                # Log warning but don't fail the job
                print(f"Warning: Failed to delete audio file: {e}")
