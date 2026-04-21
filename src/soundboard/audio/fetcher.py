from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

Downloader = Callable[[str, float | None, float | None, Path], Path]


def parse_timecode(value: str) -> float:
    """Parse ``SS``, ``MM:SS``, ``H:MM:SS`` (fractional seconds allowed) into seconds."""
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3 or any(not p for p in parts):
        raise ValueError(f"invalid timecode: {value!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"invalid timecode: {value!r}") from e
    if any(n < 0 for n in nums):
        raise ValueError(f"invalid timecode: {value!r}")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def ytdlp_download(
    url: str, start: float | None, end: float | None, dest_dir: Path
) -> Path:
    import yt_dlp
    from yt_dlp.utils import download_range_func

    dest_dir.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if start is not None and end is not None:
        options["download_ranges"] = download_range_func(None, [(start, end)])
        options["force_keyframes_at_cuts"] = True

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
    video_id = info["id"]
    final = dest_dir / f"{video_id}.mp3"
    if not final.is_file():
        raise RuntimeError(f"yt-dlp finished but {final} is missing")
    return final
