"""Supported sources and retained media playback through the API."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api import routes
from api.main import app
from transcripts.models import Stage, Transcript, Word
from transcripts.processor import TranscriptProcessor
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage


X_URL = "https://x.com/example/status/1234567890123456789"
X_ID = "x-1234567890123456789"


class VideoAPITestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.video_directory = self.root / "downloads" / "videos"
        self.video_directory.mkdir(parents=True)
        self.storage = SQLiteStorage(str(self.root / "test.db"))
        self.state = StateManager.__new__(StateManager)
        self.state._storage = self.storage
        self.state_patch = patch.object(routes, "get_state_manager", return_value=self.state)
        self.video_patch = patch.object(routes, "VIDEO_DIRECTORY", self.video_directory)
        self.state_patch.start()
        self.video_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.video_patch.stop()
        self.state_patch.stop()
        self.directory.cleanup()

    def completed_job(self, duration=None, url=X_URL):
        job = self.storage.create_job(url)
        video = self.video_directory / "twitter-123.mp4"
        video.write_bytes(b"0123456789abcdef")
        job.video_file = str(video)
        job.stage = Stage.COMPLETED
        self.storage.update_job(job)
        self.storage.save_transcript(job.id, Transcript(
            video_url=job.url, title="Example X video", transcript_text="Hello world",
            duration=duration,
            words=[Word("Hello", 1000, 1500), Word("world", 1500, 2000)],
        ))
        return job, video

    def test_creates_x_job_and_passes_retention_preferences(self):
        with patch.object(routes, "process_job") as process:
            response = self.client.post("/api/jobs", json={
                "url": X_URL, "keep_video": False, "keep_audio": False,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], X_ID)
        self.assertFalse(response.json()["video_available"])
        process.assert_called_once_with(X_ID, X_URL, False, False)

    def test_rejects_unsupported_or_spoofed_url_before_processing(self):
        invalid_urls = [
            "https://x.com.evil.test/example/status/123",
            "https://evil.test/?url=https://x.com/example/status/123",
            "https://youtube.com.evil.test/watch?v=abcdefghijk",
            "https://x.com/example/status/123/video/0",
            "https://x.com/example/status/123/video/2/extra",
            "https://x.com/example", "file:///downloads/videos/test.mp4",
        ]
        with patch.object(routes, "process_job") as process:
            for url in invalid_urls:
                with self.subTest(url=url):
                    response = self.client.post("/api/jobs", json={"url": url})
                    self.assertEqual(response.status_code, 400)
        process.assert_not_called()
        self.assertEqual(self.storage.list_jobs(), [])

    def test_completed_alias_returns_existing_job_without_processing(self):
        job, _ = self.completed_job()
        with patch.object(routes, "process_job") as process:
            response = self.client.post("/api/jobs", json={
                "url": "https://twitter.com/example/status/1234567890123456789?s=20",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], job.id)
        process.assert_not_called()

    def test_x_pipeline_saves_timestamped_transcript_and_retained_video(self):
        video = self.video_directory / "x-video.mp4"
        video.write_bytes(b"video")
        audio = self.root / "audio.mp3"
        audio.write_bytes(b"audio")
        transcriber = Mock()
        transcriber.transcribe_file.return_value = Transcript(
            video_url="", title="", transcript_text="Hello",
            words=[Word("Hello", 1000, 1500)],
        )
        with patch("transcripts.processor.create_transcriber", return_value=transcriber):
            processor = TranscriptProcessor(
                download_dir=str(self.root / "downloads"),
                transcripts_dir=str(self.root / "transcripts"),
                provider="deepgram", api_key="test", output_format="none",
                state_manager=self.state,
            )
        with patch.object(processor.downloader, "download_video", return_value=(
            str(video), str(audio), {"title": "X video", "duration": 2.984},
        )):
            processor.process_video(X_URL)
        transcriber.transcribe_file.assert_called_once_with(str(audio))
        response = self.client.get(f"/api/jobs/{X_ID}")
        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["job"]["stage"], "completed")
        self.assertTrue(detail["job"]["video_available"])
        self.assertTrue(detail["transcript"]["video_available"])
        self.assertEqual(detail["transcript"]["duration"], 2.984)
        self.assertEqual(detail["transcript"]["words"][0]["start"], 1000)
        self.assertEqual(self.client.get(f"/api/jobs/{X_ID}/video").content, b"video")

    def test_completed_job_detail_preserves_fractional_integer_and_unknown_durations(self):
        cases = [
            (X_URL, 2281.984),
            ("https://youtu.be/abcdefghijk", 2281),
            ("https://youtu.be/lmnopqrstuv", None),
        ]
        for url, duration in cases:
            with self.subTest(url=url, duration=duration):
                job, _ = self.completed_job(duration=duration, url=url)
                stored = self.storage.get_transcript(job.id)
                self.assertEqual(stored.duration, duration)
                self.assertEqual(Transcript.from_dict(stored.to_dict()).duration, duration)
                response = self.client.get(f"/api/jobs/{job.id}")
                self.assertEqual(response.status_code, 200)
                detail = response.json()
                self.assertEqual(detail["job"]["stage"], "completed")
                self.assertEqual(detail["transcript"]["duration"], duration)

    def test_serves_video_and_byte_ranges_for_seeking(self):
        job, _ = self.completed_job()
        url = f"/api/jobs/{job.id}/video"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"0123456789abcdef")
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertTrue(response.headers["content-disposition"].startswith("inline"))
        partial = self.client.get(url, headers={"Range": "bytes=4-7"})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, b"4567")
        self.assertEqual(partial.headers["content-range"], "bytes 4-7/16")
        self.assertEqual(self.client.get(url, headers={"Range": "bytes=-3"}).content, b"def")
        self.assertEqual(self.client.get(url, headers={"Range": "bytes=50-60"}).status_code, 416)
        self.assertEqual(self.client.head(url).content, b"")

    def test_availability_changes_when_video_removed_or_not_retained(self):
        job, video = self.completed_job()
        detail = self.client.get(f"/api/jobs/{job.id}").json()
        self.assertTrue(detail["job"]["video_available"])
        self.assertTrue(detail["transcript"]["video_available"])
        video.unlink()
        detail = self.client.get(f"/api/jobs/{job.id}").json()
        self.assertFalse(detail["job"]["video_available"])
        self.assertFalse(detail["transcript"]["video_available"])
        self.assertIsNotNone(detail["transcript"])
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/video").status_code, 404)
        video.write_bytes(b"temporary video")
        job.keep_video = False
        self.storage.update_job(job)
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/video").status_code, 404)

    def test_missing_and_unfinished_jobs_have_no_video_endpoint(self):
        self.assertEqual(self.client.get("/api/jobs/missing/video").status_code, 404)
        job, _ = self.completed_job()
        job.stage = Stage.TRANSCRIBING
        self.storage.update_job(job)
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/video").status_code, 404)

    def test_video_cannot_escape_download_directory(self):
        job, _ = self.completed_job()
        outside = self.root / "private.mp4"
        outside.write_bytes(b"private")
        job.video_file = str(outside)
        self.storage.update_job(job)
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/video").status_code, 404)
        link = self.video_directory / "link.mp4"
        link.symlink_to(outside)
        job.video_file = str(link)
        self.storage.update_job(job)
        self.assertEqual(self.client.get(f"/api/jobs/{job.id}/video").status_code, 404)

    def test_symlinked_video_directory_is_supported(self):
        job, _ = self.completed_job()
        link = self.root / "video-directory-link"
        link.symlink_to(self.video_directory, target_is_directory=True)
        with patch.object(routes, "VIDEO_DIRECTORY", link):
            self.assertEqual(self.client.get(f"/api/jobs/{job.id}/video").status_code, 200)

    def test_retry_preserves_retention_preferences(self):
        job = self.storage.create_job(X_URL)
        job.stage = Stage.FAILED
        job.keep_video = False
        job.keep_audio = False
        self.storage.update_job(job)
        with patch.object(routes, "process_job") as process:
            response = self.client.post(f"/api/jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 200)
        process.assert_called_once_with(job.id, job.url, False, False)


if __name__ == "__main__":
    unittest.main()
