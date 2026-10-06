"""Validate supported video URLs and provide stable storage identities."""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlsplit


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_YOUTUBE_HOSTS = {"youtu.be", "www.youtu.be"}
_EMBED_YOUTUBE_HOSTS = {"youtube-nocookie.com", "www.youtube-nocookie.com"}
_X_HOSTS = {
    "x.com", "www.x.com", "m.x.com", "mobile.x.com",
    "twitter.com", "www.twitter.com", "m.twitter.com", "mobile.twitter.com",
}
_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_X_STATUS_PATH = re.compile(
    r"/(?:[A-Za-z0-9_]+/status|i/web/status|statuses)/"
    r"(?P<status_id>[1-9][0-9]{0,19})"
    r"(?:/video/(?P<video_index>[1-9][0-9]{0,8}))?/?"
)


@dataclass(frozen=True)
class VideoSource:
    provider: str
    video_id: str
    canonical_url: str
    video_index: Optional[int] = None


def parse_video_source(url: str) -> Optional[VideoSource]:
    """Parse an HTTP(S) YouTube video or X post URL on an exact supported host.

    YouTube IDs remain unchanged for existing records. X jobs use ``x-<id>``
    and an explicit attachment has ``-video-<index>`` appended. The bare X URL
    selects its first video, while /video/N follows X's media attachment index.
    """
    if not isinstance(url, str) or any(ord(char) < 32 or ord(char) == 127 for char in url):
        return None
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if parsed.port not in (None, 80, 443):
            return None
        host = parsed.hostname.lower()
    except ValueError:
        return None

    if host in _X_HOSTS:
        match = _X_STATUS_PATH.fullmatch(parsed.path)
        if not match:
            return None
        status_id = match.group("status_id")
        index = match.group("video_index")
        video_id = f"x-{status_id}"
        canonical_url = f"https://x.com/i/status/{status_id}"
        if index is not None:
            video_id += f"-video-{index}"
            canonical_url += f"/video/{index}"
        return VideoSource("x", video_id, canonical_url, int(index) if index else None)

    video_id = None
    path = parsed.path.rstrip("/")
    if host in _SHORT_YOUTUBE_HOSTS:
        video_id = path[1:]
    elif host in _YOUTUBE_HOSTS:
        if path == "/watch":
            values = parse_qs(parsed.query).get("v", [])
            if len(values) == 1:
                video_id = values[0]
        else:
            match = re.fullmatch(r"/(?:embed|shorts|live|v)/([A-Za-z0-9_-]{11})", path)
            if match:
                video_id = match.group(1)
    elif host in _EMBED_YOUTUBE_HOSTS:
        match = re.fullmatch(r"/embed/([A-Za-z0-9_-]{11})", path)
        if match:
            video_id = match.group(1)

    if video_id and _YOUTUBE_ID.fullmatch(video_id):
        return VideoSource("youtube", video_id, f"https://www.youtube.com/watch?v={video_id}")
    return None


def extract_video_id(url: str) -> Optional[str]:
    """Return a stable job ID for a supported URL, or None for invalid URLs."""
    source = parse_video_source(url)
    return source.video_id if source else None
