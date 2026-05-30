"""Media processing pipeline for JD2017 PC.

Handles audio transcoding (to OGG Vorbis), video transcoding (to VP8 WebM),
and cover art generation using FFmpeg/FFprobe and Pillow.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("jd2017.installers.media_processor")


def _find_tool(tool_name: str, config_path: str | Path | None = None) -> str:
    """Locate an external tool on PATH or via explicit config path."""
    if config_path and Path(config_path).exists():
        return str(config_path)

    found = shutil.which(tool_name)
    if found:
        return found

    # Check common local tool directories
    for candidate in [
        f"tools/vgmstream/{tool_name}.exe",
        f"tools/{tool_name}.exe",
        f"3rdPartyTools/{tool_name}.exe",
    ]:
        if Path(candidate).exists():
            return str(Path(candidate).resolve())

    return tool_name  # Fall back to bare name; will fail at runtime


def _run_subprocess(args: list[str], description: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a subprocess with logging and error handling."""
    logger.debug("Running: %s", " ".join(args))
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("%s failed (exit %d): %s", description, result.returncode, result.stderr[:500])
        return result
    except FileNotFoundError:
        logger.error("%s: tool not found: %s", description, args[0])
        raise
    except subprocess.TimeoutExpired:
        logger.error("%s: timed out after %ds", description, timeout)
        raise


def transcode_audio_to_ogg(
    input_path: Path,
    output_path: Path,
    ffmpeg_path: str = "ffmpeg",
    sample_rate: int = 48000,
    channels: int = 2,
    quality: int = 6,
) -> Path:
    """Transcode an audio file to OGG Vorbis format for JD2017 PC.

    Args:
        input_path: Source audio file (WAV, OGG, MP3, etc.).
        output_path: Output .ogg file path.
        ffmpeg_path: Path to ffmpeg executable.
        sample_rate: Target sample rate (48000 for JD2017 PC).
        channels: Number of audio channels (2 = stereo).
        quality: Vorbis quality level (0-10, 6 is default).

    Returns:
        Path to the output OGG file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    args = [
        ffmpeg_path, "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "libvorbis",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-q:a", str(quality),
        str(output_path),
    ]

    result = _run_subprocess(args, "Audio transcode to OGG")
    if result.returncode != 0:
        raise RuntimeError(f"Audio transcode failed: {result.stderr[:300]}")

    logger.info("Transcoded audio: %s -> %s", input_path.name, output_path.name)
    return output_path


def transcode_video_to_webm(
    input_path: Path,
    output_path: Path,
    ffmpeg_path: str = "ffmpeg",
    video_bitrate: str = "8500k",
    pixel_format: str = "yuv420p",
    hwaccel: str = "auto",
) -> Path:
    """Transcode a video file to VP8 WebM format for JD2017 PC.

    Args:
        input_path: Source video file.
        output_path: Output .webm file path.
        ffmpeg_path: Path to ffmpeg executable.
        video_bitrate: Target video bitrate.
        pixel_format: Pixel format (yuv420p for VP8).
        hwaccel: Hardware acceleration mode.

    Returns:
        Path to the output WebM file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    args = [ffmpeg_path, "-y"]

    if hwaccel != "none":
        args.extend(["-hwaccel", hwaccel])

    args.extend([
        "-i", str(input_path),
        "-an",  # No audio
        "-c:v", "libvpx",
        "-b:v", video_bitrate,
        "-pix_fmt", pixel_format,
        "-quality", "good",
        "-cpu-used", "2",
        str(output_path),
    ])

    result = _run_subprocess(args, "Video transcode to WebM", timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Video transcode failed: {result.stderr[:300]}")

    logger.info("Transcoded video: %s -> %s", input_path.name, output_path.name)
    return output_path


def decode_vgmstream_audio(
    input_path: Path,
    output_path: Path,
    vgmstream_path: str | None = None,
) -> Path:
    """Decode a game audio file using vgmstream to WAV.

    Used for Xbox 360/WiiU audio formats that FFmpeg can't handle directly.

    Args:
        input_path: Source audio file (e.g., .ckd, .wem, .bck).
        output_path: Output .wav file path.
        vgmstream_path: Path to vgmstream-cli executable.

    Returns:
        Path to the decoded WAV file.
    """
    tool = _find_tool("vgmstream-cli", vgmstream_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    args = [tool, "-o", str(output_path), str(input_path)]
    result = _run_subprocess(args, "vgmstream decode")
    if result.returncode != 0:
        raise RuntimeError(f"vgmstream decode failed: {result.stderr[:300]}")

    logger.info("Decoded audio: %s -> %s", input_path.name, output_path.name)
    return output_path


def get_audio_duration(audio_path: Path, ffprobe_path: str = "ffprobe") -> float:
    """Get the duration of an audio file in seconds using ffprobe.

    Args:
        audio_path: Path to the audio file.
        ffprobe_path: Path to ffprobe executable.

    Returns:
        Duration in seconds.
    """
    args = [
        ffprobe_path,
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(audio_path),
    ]

    result = _run_subprocess(args, "ffprobe duration query")
    if result.returncode != 0:
        return 0.0

    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0
