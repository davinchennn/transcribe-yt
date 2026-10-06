"""YouTube and X video downloader using yt-dlp."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yt_dlp

from transcripts.sources import parse_video_source


class YouTubeDownloader:
    """Downloads supported videos and extracts audio using yt-dlp.

    The existing class name is retained for compatibility with callers.
    """

    def __init__(
        self,
        download_dir: str = "downloads",
        video_dir: str = "videos",
        audio_dir: str = "audio",
    ):
        """
        Initialize downloader.

        Args:
            download_dir: Base directory for downloads
            video_dir: Subdirectory for video files
            audio_dir: Subdirectory for audio files
        """
        self.download_dir = Path(download_dir)
        self.video_dir = self.download_dir / video_dir
        self.audio_dir = self.download_dir / audio_dir

        # Create directories if they don't exist
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def download_video(
        self, url: str, extract_audio: bool = True
    ) -> Tuple[Optional[str], Optional[str], Dict]:
        """
        Download video and extract audio.

        Always downloads the full video first, then extracts audio from it.
        This ensures both video and audio files are available.

        Args:
            url: YouTube video or X post URL (optionally /video/N)
            extract_audio: Whether to extract audio from video (default: True)

        Returns:
            Tuple of (video_file_path, audio_file_path, metadata)
        """
        video_file = None
        audio_file = None
        metadata = {}
        source = parse_video_source(url)
        if source is None:
            raise ValueError("Unsupported video URL. Use a YouTube video or X post URL.")
        downloaded_files = []

        # Configure yt-dlp options - always download full video first
        ydl_opts = {
            "quiet": False,
            "no_warnings": False,
            "extract_flat": False,
            "noplaylist": True,
            # A bare X post can still produce a playlist. Download its first
            # video only; an explicit /video/N is selected by the extractor.
            "playlist_items": "1",
            # Add options to help avoid 403 errors
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(
                self.video_dir
                / f"{source.video_id}-%(extractor)s-%(id)s - %(title).150B.%(ext)s"
            ),
            # Post hooks receive the final path after merging and moving.
            "post_hooks": [downloaded_files.append],
        }
        cookies_file = os.getenv("TRANSCRIPTS_COOKIES_FILE")
        if cookies_file:
            ydl_opts["cookiefile"] = str(Path(cookies_file).expanduser())

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info and download video
                info = self._single_video_info(
                    ydl.extract_info(source.canonical_url, download=True)
                )

                metadata = {
                    "title": info.get("title", ""),
                    "duration": info.get("duration"),
                    "uploader": info.get("uploader"),
                    "upload_date": info.get("upload_date"),
                    "view_count": info.get("view_count"),
                    "description": info.get("description"),
                    "source": source.provider,
                    "source_video_id": source.video_id,
                    "video_index": source.video_index,
                }

                video_file = self._downloaded_filename(ydl, info, downloaded_files)

            # Extract audio from video if requested
            if extract_audio and video_file:
                audio_file = self.extract_audio_from_video(video_file)

        except Exception as e:
            raise RuntimeError(f"Failed to download video: {str(e)}") from e

        return video_file, audio_file, metadata

    @staticmethod
    def _single_video_info(info: Optional[Dict]) -> Dict:
        """Unwrap yt-dlp's selected playlist result without using its metadata."""
        for _ in range(10):
            if not isinstance(info, dict) or not info:
                break
            if "entries" not in info:
                if info.get("_type", "video") == "video":
                    return info
                break
            info = next(
                (
                    entry
                    for entry in (info.get("entries") or [])
                    if isinstance(entry, dict) and entry
                ),
                None,
            )
        raise ValueError("No downloadable video found in this URL.")

    @staticmethod
    def _downloaded_filename(ydl, info: Dict, downloaded_files: List[str]) -> str:
        """Resolve the file that survived merging/postprocessing, not a stream."""
        candidates = list(reversed(downloaded_files))
        candidates.append(info.get("filepath"))
        # requested_downloads holds the finished path for a single-format
        # download. Separate audio/video streams must not be returned here.
        downloads = info.get("requested_downloads") or []
        if len(downloads) == 1:
            candidates.append(downloads[0].get("filepath"))
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(candidate)
        filename = ydl.prepare_filename(info)
        if filename and Path(filename).is_file():
            return str(filename)
        raise ValueError("The downloaded video file could not be found after processing.")

    def extract_audio_from_video(self, video_path: str) -> Optional[str]:
        """
        Extract audio from a video file using yt-dlp/FFmpeg.

        Args:
            video_path: Path to the video file

        Returns:
            Path to the extracted audio file, or None if extraction failed
        """
        video_path = Path(video_path)
        if not video_path.exists():
            return None

        # Output audio file in audio directory with same name but .mp3 extension
        audio_filename = video_path.stem + ".mp3"
        audio_path = self.audio_dir / audio_filename

        # Use yt-dlp to extract audio (it handles FFmpeg internally)
        ydl_opts = {
            "quiet": False,
            "no_warnings": False,
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(self.audio_dir / "%(title)s.%(ext)s"),
        }

        try:
            # Use ffmpeg directly for extraction from local file
            import subprocess
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(video_path),
                    "-vn", "-acodec", "libmp3lame", "-ab", "192k",
                    str(audio_path)
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and audio_path.exists():
                return str(audio_path)
            else:
                print(f"FFmpeg extraction failed: {result.stderr}")
                return None
        except FileNotFoundError:
            print("FFmpeg not found, audio extraction skipped")
            return None
        except Exception as e:
            print(f"Audio extraction failed: {e}")
            return None

    def download_playlist(self, url: str, extract_audio: bool = True) -> List[Dict]:
        """
        Download all videos from a playlist.

        Args:
            url: YouTube playlist URL
            extract_audio: Whether to extract audio from videos

        Returns:
            List of dictionaries with video_file, audio_file, and metadata for each video
        """
        results = []

        ydl_opts = {
            "quiet": False,
            "no_warnings": False,
            "extract_flat": False,
        }

        if extract_audio:
            ydl_opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                    "outtmpl": str(self.audio_dir / "%(playlist_index)s - %(title)s.%(ext)s"),
                }
            )
        else:
            ydl_opts.update(
                {
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "outtmpl": str(self.video_dir / "%(playlist_index)s - %(title)s.%(ext)s"),
                }
            )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract playlist info
                info = ydl.extract_info(url, download=False)

                if "entries" not in info:
                    raise ValueError("URL does not appear to be a playlist")

                # Download each video
                for entry in info["entries"]:
                    if entry is None:
                        continue

                    # A processed yt-dlp entry's `url` is often the selected
                    # googlevideo stream rather than the YouTube watch page.
                    # Recover a supported source URL before downloading it.
                    source = None
                    for key in ("webpage_url", "original_url", "url"):
                        source = parse_video_source(entry.get(key))
                        if source is not None:
                            break
                    if source is None:
                        source = parse_video_source(
                            f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                        )
                    if source is None:
                        raise ValueError("Playlist entry has no supported video URL")
                    video_url = source.canonical_url
                    video_file, audio_file, metadata = self.download_video(
                        video_url, extract_audio
                    )

                    results.append(
                        {
                            "video_file": video_file,
                            "audio_file": audio_file,
                            "metadata": metadata,
                            "url": video_url,
                        }
                    )

        except Exception as e:
            raise RuntimeError(f"Failed to download playlist: {str(e)}") from e

        return results

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize filename for filesystem compatibility."""
        # Remove or replace invalid characters
        invalid_chars = r'<>:"/\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        # Remove leading/trailing spaces and dots
        filename = filename.strip(" .")
        return filename
