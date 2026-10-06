"""Download selection and file resolution without network or transcription calls."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yt_dlp
from yt_dlp.extractor.twitter import TwitterIE

from transcripts.downloader import YouTubeDownloader


class TestDownloader(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.downloader = YouTubeDownloader(self.directory.name)
        self.ydl = MagicMock()
        self.ydl.__enter__.return_value = self.ydl
        self.options = None
        self.downloaded = []

    def youtube_dl(self, options):
        self.options = options
        return self.ydl

    def create_video(self, name):
        path = self.downloader.video_dir / name
        path.write_bytes(b"video")
        return str(path)

    def test_bare_x_post_downloads_only_first_video_and_unwraps_its_metadata(self):
        def extract(url, download):
            self.assertTrue(download)
            self.assertEqual(url, "https://x.com/i/status/123")
            self.assertEqual(self.options["playlist_items"], "1")
            self.assertTrue(self.options["noplaylist"])
            path = self.create_video("Twitter-987 - first.mp4")
            self.downloaded.append("987")
            self.options["post_hooks"][0](path)
            return {"_type": "playlist", "title": "Parent post", "entries": [None, {
                "id": "987", "title": "First video", "duration": 12.5,
                "filepath": path, "uploader": "Author",
            }]}

        self.ydl.extract_info.side_effect = extract
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl), patch.dict(os.environ, {}, clear=True):
            video, audio, metadata = self.downloader.download_video("https://twitter.com/author/status/123?s=20", extract_audio=False)
        self.assertEqual(video, str(self.downloader.video_dir / "Twitter-987 - first.mp4"))
        self.assertIsNone(audio)
        self.assertEqual(metadata["title"], "First video")
        self.assertEqual(metadata["duration"], 12.5)
        self.assertEqual(metadata["source"], "x")
        self.assertEqual(self.downloaded, ["987"])
        self.assertIn("%(extractor)s-%(id)s", self.options["outtmpl"])
        self.assertIn("x-123-", self.options["outtmpl"])
        self.assertEqual(self.options["merge_output_format"], "mp4")
        self.assertNotIn("cookiefile", self.options)
        self.assertNotIn("cookiesfrombrowser", self.options)

    def test_selected_attachment_url_is_passed_to_the_extractor(self):
        path = self.create_video("Twitter-988 - selected.mp4")
        self.ydl.extract_info.return_value = {"id": "988", "title": "Second video", "filepath": path}
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl), patch.object(self.downloader, "extract_audio_from_video", return_value="selected.mp3") as extract_audio:
            video, audio, metadata = self.downloader.download_video("https://mobile.twitter.com/author/status/123/video/2?s=20")
        self.ydl.extract_info.assert_called_once_with("https://x.com/i/status/123/video/2", download=True)
        extract_audio.assert_called_once_with(path)
        self.assertEqual(video, path)
        self.assertEqual(audio, "selected.mp3")
        self.assertEqual(metadata["source_video_id"], "x-123-video-2")
        self.assertEqual(metadata["video_index"], 2)

    def test_real_twitter_extractor_selects_first_video_or_explicit_media_index(self):
        # Use the installed extractor and playlist machinery. Only fetching the
        # post and downloading bytes are mocked, so no network is involved.
        real_youtube_dl = yt_dlp.YoutubeDL
        status = {
            "full_text": "A post containing a photo and two videos",
            "user": {"name": "Author", "screen_name": "author"},
            "extended_entities": {"media": [
                {"id": 986, "id_str": "986", "type": "photo"},
                {"id": 987, "id_str": "987", "type": "video", "video_info": {
                    "duration_millis": 12000,
                    "variants": [{"url": "https://video.twimg.com/test/first.mp4", "bitrate": 100000}],
                }},
                {"id": 988, "id_str": "988", "type": "video", "video_info": {
                    "duration_millis": 18000,
                    "variants": [{"url": "https://video.twimg.com/test/second.mp4", "bitrate": 100000}],
                }},
            ]},
        }
        downloaded_ids = []

        def make_ydl(options):
            options.update({"quiet": True, "no_warnings": True, "fixup": "never"})
            ydl = real_youtube_dl(options, auto_init=False)
            ydl.add_info_extractor(TwitterIE())
            return ydl

        def download(ydl, filename, info, subtitle=False):
            downloaded_ids.append(info["id"])
            Path(filename).write_bytes(b"video")
            return True, True

        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=make_ydl), patch.object(TwitterIE, "_extract_status", return_value=status), patch.object(real_youtube_dl, "dl", download), patch.dict(os.environ, {}, clear=True):
            first, _, first_metadata = self.downloader.download_video("https://x.com/author/status/123", extract_audio=False)
            second, _, second_metadata = self.downloader.download_video("https://x.com/author/status/123/video/3", extract_audio=False)
            with self.assertRaisesRegex(RuntimeError, "not a video"):
                self.downloader.download_video("https://x.com/author/status/123/video/1", extract_audio=False)
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                self.downloader.download_video("https://x.com/author/status/123/video/4", extract_audio=False)
        self.assertEqual(downloaded_ids, ["987", "988"])
        self.assertEqual(first_metadata["duration"], 12)
        self.assertEqual(second_metadata["duration"], 18)
        self.assertIn("x-123-twitter-987", first)
        self.assertIn("x-123-video-3-twitter-988", second)
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(second).is_file())

    def test_final_postprocess_path_wins_over_premerge_or_requested_stream_path(self):
        merged = self.create_video("Twitter-987 - merged.mp4")
        stream = self.create_video("Twitter-987 - merged.f137.mp4")

        def extract(url, download):
            self.options["post_hooks"][0](merged)
            return {"id": "987", "title": "Merged", "filepath": "no-longer-existing.webm",
                    "requested_downloads": [{"filepath": stream}]}

        self.ydl.extract_info.side_effect = extract
        self.ydl.prepare_filename.return_value = "wrong-extension.webm"
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl), patch.object(self.downloader, "extract_audio_from_video", return_value="merged.mp3") as extract_audio:
            video, _, _ = self.downloader.download_video("https://x.com/author/status/123")
        self.assertEqual(video, merged)
        extract_audio.assert_called_once_with(merged)
        self.ydl.prepare_filename.assert_not_called()

    def test_info_filepath_and_single_requested_download_are_valid_fallbacks(self):
        path = self.create_video("YouTube-abcdefghijk - result.mp4")
        for fields in ({"filepath": path}, {"requested_downloads": [{"filepath": path}]}):
            with self.subTest(fields=fields):
                self.ydl.extract_info.return_value = {"id": "abcdefghijk", "title": "Result", **fields}
                with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl):
                    video, _, metadata = self.downloader.download_video("https://youtu.be/abcdefghijk?si=tracking", extract_audio=False)
                self.assertEqual(video, path)
                self.assertEqual(metadata["source"], "youtube")

    def test_missing_video_and_empty_playlists_fail_without_extracting_audio(self):
        for result in (None, {}, {"_type": "playlist", "entries": []}, {"entries": [None]}, {"_type": "url", "url": "https://example.com"}):
            with self.subTest(result=result):
                self.ydl.extract_info.return_value = result
                with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl), patch.object(self.downloader, "extract_audio_from_video") as extract_audio:
                    with self.assertRaisesRegex(RuntimeError, "No downloadable video"):
                        self.downloader.download_video("https://x.com/author/status/123")
                extract_audio.assert_not_called()

    def test_prepared_filename_fallback_must_exist(self):
        path = self.create_video("YouTube-abcdefghijk - old-version.mp4")
        self.ydl.extract_info.return_value = {"id": "abcdefghijk", "title": "Result"}
        self.ydl.prepare_filename.return_value = path
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl):
            video, _, _ = self.downloader.download_video("https://youtu.be/abcdefghijk", extract_audio=False)
        self.assertEqual(video, path)
        self.ydl.prepare_filename.return_value = "not-a-downloaded-file.mp4"
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl):
            with self.assertRaisesRegex(RuntimeError, "could not be found after processing"):
                self.downloader.download_video("https://youtu.be/abcdefghijk", extract_audio=False)

    def test_optional_cookies_file_is_explicit_and_expands_home(self):
        path = self.create_video("Twitter-987 - authenticated.mp4")
        self.ydl.extract_info.return_value = {"id": "987", "title": "Result", "filepath": path}
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl), patch.dict(os.environ, {"TRANSCRIPTS_COOKIES_FILE": "~/cookies.txt"}):
            self.downloader.download_video("https://x.com/author/status/123", extract_audio=False)
        self.assertEqual(self.options["cookiefile"], str(Path("~/cookies.txt").expanduser()))
        self.assertNotIn("cookiesfrombrowser", self.options)

    def test_unsupported_url_is_rejected_before_invoking_yt_dlp(self):
        with patch("transcripts.downloader.yt_dlp.YoutubeDL") as downloader:
            with self.assertRaisesRegex(ValueError, "Unsupported video URL"):
                self.downloader.download_video("https://x.com.evil.test/author/status/123")
        downloader.assert_not_called()

    def test_processed_playlist_entries_use_watch_pages_instead_of_stream_urls(self):
        playlist_url = "https://www.youtube.com/playlist?list=PL123"
        video_url = "https://www.youtube.com/watch?v=abcdefghijk"
        path = self.create_video("YouTube-abcdefghijk - playlist.mp4")
        entry_variants = [
            {"webpage_url": video_url},
            {"original_url": "https://youtu.be/abcdefghijk"},
            {},  # A valid YouTube video ID is sufficient as the last fallback.
        ]
        for variant in entry_variants:
            with self.subTest(variant=variant):
                entry = {"id": "abcdefghijk", "title": "Playlist video",
                         "url": "https://rr1.googlevideo.com/videoplayback?signature=media", **variant}
                requested_urls = []

                def extract(url, download):
                    requested_urls.append((url, download))
                    if url == playlist_url:
                        return {"_type": "playlist", "entries": [None, entry]}
                    self.assertEqual(url, video_url)
                    return {"id": "abcdefghijk", "title": "Playlist video", "filepath": path}

                self.ydl.extract_info.side_effect = extract
                with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl):
                    results = self.downloader.download_playlist(playlist_url, extract_audio=False)
                self.assertEqual(requested_urls, [(playlist_url, False), (video_url, True)])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["video_file"], path)
                self.assertEqual(results[0]["url"], video_url)

    def test_playlist_entries_without_a_supported_source_fail_clearly(self):
        self.ydl.extract_info.return_value = {"entries": [{
            "id": "not-a-youtube-id", "url": "https://example.com/media.mp4",
        }]}
        with patch("transcripts.downloader.yt_dlp.YoutubeDL", side_effect=self.youtube_dl):
            with self.assertRaisesRegex(RuntimeError, "Playlist entry has no supported video URL"):
                self.downloader.download_playlist("https://www.youtube.com/playlist?list=PL123", extract_audio=False)


if __name__ == "__main__":
    unittest.main()
