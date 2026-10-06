"""Supported URL identities are stable and cannot be spoofed by other hosts."""

import tempfile
import unittest
from pathlib import Path

from transcripts.sources import parse_video_source
from transcripts.storage.base import extract_video_id
from transcripts.storage.json import JSONStorage
from transcripts.storage.sqlite import SQLiteStorage


class TestVideoSources(unittest.TestCase):
    def test_youtube_ids_keep_existing_storage_keys(self):
        urls = [
            "https://youtube.com/watch?v=abcdefghijk&t=30&list=PL123",
            "https://www.youtube.com/watch?v=abcdefghijk",
            "https://m.youtube.com/watch?v=abcdefghijk",
            "https://music.youtube.com/watch?v=abcdefghijk",
            "http://youtu.be/abcdefghijk?si=shared",
            "https://youtu.be/abcdefghijk/",
            "https://www.youtube.com/embed/abcdefghijk",
            "https://www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com/live/abcdefghijk",
            "https://www.youtube.com/v/abcdefghijk",
            "https://www.youtube-nocookie.com/embed/abcdefghijk",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(extract_video_id(url), "abcdefghijk")
                source = parse_video_source(url)
                self.assertEqual(source.provider, "youtube")
                self.assertEqual(source.canonical_url, "https://www.youtube.com/watch?v=abcdefghijk")

    def test_x_and_twitter_host_variants_deduplicate_the_same_status(self):
        for domain in ("x.com", "twitter.com"):
            for prefix in ("", "www.", "mobile.", "m."):
                for path in ("someone/status/1234567890123456789", "i/web/status/1234567890123456789", "i/status/1234567890123456789"):
                    url = f"https://{prefix}{domain}/{path}?s=20&t=tracking#ignored"
                    with self.subTest(url=url):
                        source = parse_video_source(url)
                        self.assertEqual(extract_video_id(url), "x-1234567890123456789")
                        self.assertEqual(source.provider, "x")
                        self.assertEqual(source.canonical_url, "https://x.com/i/status/1234567890123456789")
                        self.assertIsNone(source.video_index)

    def test_explicit_x_attachment_identity_and_index_are_preserved(self):
        for index in (1, 2, 4):
            source = parse_video_source(f"https://twitter.com/someone/status/123/video/{index}/?s=20")
            self.assertEqual(source.video_id, f"x-123-video-{index}")
            self.assertEqual(source.video_index, index)
            self.assertEqual(source.canonical_url, f"https://x.com/i/status/123/video/{index}")
        self.assertNotEqual(extract_video_id("https://x.com/someone/status/123"),
                            extract_video_id("https://x.com/someone/status/123/video/1"))

    def test_invalid_urls_and_spoofed_hosts_are_rejected(self):
        urls = [
            None, "", "abcdefghijk", "x.com/someone/status/123",
            "ftp://x.com/someone/status/123",
            "https://example.com/watch?v=abcdefghijk",
            "https://youtube.com.evil.test/watch?v=abcdefghijk",
            "https://notyoutube.com/watch?v=abcdefghijk",
            "https://x.com.evil.test/someone/status/123",
            "https://evil.test/?url=https://x.com/someone/status/123",
            "https://x.com@evil.test/someone/status/123",
            "https://evil.test@x.com/someone/status/123",
            "https://x.com:9999/someone/status/123",
            "https://x.com:wrong/someone/status/123",
            "https://x.com/someone/status/123\n",
            "https://x.com/someone/status/123/photo/1",
            "https://x.com/someone/status/123/video/0",
            "https://x.com/someone/status/123/video/-1",
            "https://x.com/someone/status/123/video/01",
            "https://x.com/someone/status/123/video/two",
            "https://x.com/someone/status/123/video/2/extra",
            "https://x.com/someone/status/123abc",
            "https://x.com/someone/status/0",
            "https://x.com/someone/status/１２３",
            "https://x.com/i/spaces/123",
            "https://x.com/someone",
            "https://youtube.com/watch?v=abcdefghijkl",
            "https://youtube.com/watch?v=abcdefghijk&v=lmnopqrstuv",
            "https://youtu.be/abcdefghijk/extra",
            "https://youtube.com/playlist?list=PL123",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertIsNone(extract_video_id(url))


class TestSourceStorage(unittest.TestCase):
    def test_both_backends_deduplicate_aliases_and_keep_selected_videos_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            backends = [JSONStorage(str(Path(directory) / "state.json")),
                        SQLiteStorage(str(Path(directory) / "state.db"))]
            for storage in backends:
                with self.subTest(storage=type(storage).__name__):
                    youtube = storage.create_job("https://youtu.be/abcdefghijk")
                    self.assertEqual(youtube.id, "abcdefghijk")
                    self.assertEqual(storage.create_job("https://youtube.com/watch?v=abcdefghijk").id, youtube.id)
                    bare = storage.create_job("https://x.com/someone/status/123")
                    self.assertEqual(bare.id, "x-123")
                    self.assertEqual(storage.create_job("https://mobile.twitter.com/i/web/status/123?s=20").to_dict(), bare.to_dict())
                    first = storage.create_job("https://x.com/someone/status/123/video/1")
                    second = storage.create_job("https://x.com/someone/status/123/video/2")
                    self.assertEqual(first.id, "x-123-video-1")
                    self.assertEqual(second.id, "x-123-video-2")
                    self.assertEqual(storage.get_job_by_url("https://twitter.com/new_name/status/123/video/2").id, second.id)
                    self.assertEqual(len(storage.list_jobs()), 4)
                    self.assertIsNone(storage.get_job_by_url("https://example.com/someone/status/123"))
                    with self.assertRaisesRegex(ValueError, "Unsupported video URL"):
                        storage.create_job("https://x.com.evil.test/someone/status/123")


if __name__ == "__main__":
    unittest.main()
