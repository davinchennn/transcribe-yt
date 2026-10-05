"""YouTube video downloader using yt-dlp."""

import os
import glob
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yt_dlp


class YouTubeDownloader:
    """Downloads YouTube videos and extracts audio using yt-dlp."""

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
            url: YouTube video URL
            extract_audio: Whether to extract audio from video (default: True)

        Returns:
            Tuple of (video_file_path, audio_file_path, metadata)
        """
        video_file = None
        audio_file = None
        metadata = {}

        # Configure yt-dlp options - always download full video first
        ydl_opts = {
            "quiet": False,
            "no_warnings": False,
            "extract_flat": False,
            # Add options to help avoid 403 errors
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(self.video_dir / "%(title)s.%(ext)s"),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info and download video
                info = ydl.extract_info(url, download=True)

                metadata = {
                    "title": info.get("title", ""),
                    "duration": info.get("duration"),
                    "uploader": info.get("uploader"),
                    "upload_date": info.get("upload_date"),
                    "view_count": info.get("view_count"),
                    "description": info.get("description"),
                }

                # Get the video filename
                video_file = ydl.prepare_filename(info)

            # Extract audio from video if requested
            if extract_audio and video_file:
                audio_file = self.extract_audio_from_video(video_file)

        except Exception as e:
            raise RuntimeError(f"Failed to download video: {str(e)}") from e

        return video_file, audio_file, metadata

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

                    video_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
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
        invalid_chars = '<>:"/\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        # Remove leading/trailing spaces and dots
        filename = filename.strip(" .")
        return filename
