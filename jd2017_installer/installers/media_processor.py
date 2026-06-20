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

import wave
import re

def _write_silent_stereo_wav(path: Path, duration_s: float = 0.25) -> None:
    frames = max(1, int(round(48000 * duration_s)))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(b"\x00\x00\x00\x00" * frames)

def _write_silent_ogg(path: Path, config=None) -> bool:
    tmp_wav = path.with_suffix(".tmp_silence.wav")
    try:
        _write_silent_stereo_wav(tmp_wav, duration_s=0.25)
        _run_subprocess([
            getattr(config, "ffmpeg_path", "ffmpeg") if config else "ffmpeg",
            "-y", "-i", str(tmp_wav), "-c:a", "libvorbis", str(path)
        ], "Write silent OGG")
        return path.exists()
    except Exception as exc:
        logger.debug("Silent OGG generation failed for %s: %s", path.name, exc)
        return False
    finally:
        if tmp_wav.exists():
            tmp_wav.unlink()

def extract_ckd_audio_v1(
    ckd_path: str | Path,
    output_dir: str | Path,
    config=None,
) -> Path | None:
    ckd_path = Path(ckd_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = ckd_path.read_bytes()
    except OSError:
        return None

    if len(data) <= 44:
        return None

    base = ckd_path.stem
    if base.lower().endswith(".wav") or base.lower().endswith(".ogg"):
        base = base[:-4]

    payload = data[44:]
    if b"OggS" in payload[:256]:
        ext = ".ogg"
    elif b"RIFF" in payload[:256] and b"WAVE" in payload[:256]:
        ext = ".wav"
    else:
        ext = ".raw"

    out_path = output_dir / f"{base}_extracted{ext}"
    out_path.write_bytes(payload)
    
    if ext == ".raw":
        # Attempt vgmstream
        wav_out = output_dir / f"{base}_vgm.wav"
        try:
            decode_vgmstream_audio(
                out_path,
                wav_out,
                vgmstream_path=getattr(config, "vgmstream_path", None) if config else None,
            )
            if wav_out.exists():
                return wav_out
        except Exception as e:
            logger.debug("vgmstream failed on raw CKD payload: %s", e)

    return out_path

def convert_audio(
    audio_path: str | Path,
    map_name: str,
    target_dir: str | Path,
    a_offset: float = 0.0,
    config=None,
) -> None:
    audio_path = Path(audio_path)
    target_dir = Path(target_dir)
    ogg_out = target_dir / "audio" / f"{map_name}.ogg"
    ogg_out.parent.mkdir(parents=True, exist_ok=True)

    effective_audio = audio_path
    temp_dir = target_dir / "_temp_audio"
    if audio_path.suffix.lower() == ".ckd":
        temp_dir.mkdir(parents=True, exist_ok=True)
        extracted = extract_ckd_audio_v1(audio_path, temp_dir, config=config)
        if extracted:
            effective_audio = Path(extracted)
        else:
            _write_silent_ogg(ogg_out, config=config)
            return

    try:
        ffmpeg_path = getattr(config, "ffmpeg_path", "ffmpeg") if config else "ffmpeg"
        args = [ffmpeg_path, "-y", "-i", str(effective_audio)]
        
        if a_offset < 0:
            trim_s = abs(a_offset)
            args.extend(["-ss", f"{trim_s:.6f}", "-af", "volume=2.5,alimiter=limit=-0.1dB"])
        elif a_offset > 0:
            delay_ms = int(a_offset * 1000)
            af_filter = f"adelay={delay_ms}|{delay_ms},asetpts=PTS-STARTPTS,volume=2.5,alimiter=limit=-0.1dB"
            args.extend(["-af", af_filter])
        else:
            args.extend(["-af", "volume=2.5,alimiter=limit=-0.1dB"])
            
        args.extend(["-c:a", "libvorbis", "-q:a", "6", "-ar", "48000", str(ogg_out)])
        _run_subprocess(args, "convert_audio to ogg")
    finally:
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

def generate_intro_amb(
    ogg_path: str | Path,
    map_name: str,
    target_dir: str | Path,
    a_offset: float,
    v_override: float | None = None,
    marker_preroll_ms: float | None = None,
    attempt_enabled: bool = True,
    config=None,
) -> None:
    ogg_path = Path(ogg_path)
    target_dir = Path(target_dir)
    map_lower = map_name.lower()
    amb_candidates = [
        target_dir / "Audio" / "AMB",
        target_dir / "audio" / "AMB",
        target_dir / "Audio" / "amb",
        target_dir / "audio" / "amb",
    ]
    amb_dir = next((p for p in amb_candidates if p.exists()), amb_candidates[0])

    if not attempt_enabled:
        amb_dir.mkdir(parents=True, exist_ok=True)
        intro_wavs = list(amb_dir.glob("*_intro.wav"))
        if not intro_wavs:
            intro_wavs = [amb_dir / f"amb_{map_lower}_intro.wav"]
        for wav in intro_wavs:
            _write_silent_stereo_wav(wav)
        return

    if a_offset >= 0 and (v_override is None or v_override >= 0):
        if amb_dir.exists():
            for wav in amb_dir.glob("*_intro.wav"):
                _write_silent_stereo_wav(wav)
        return

    amb_dir.mkdir(parents=True, exist_ok=True)

    # JD2017: the intro AMB covers exactly the marker preroll duration.
    # No silence padding — the engine handles video/audio sync via videoStartTime.
    if marker_preroll_ms is not None:
        audio_content_dur = marker_preroll_ms / 1000.0
    elif a_offset < 0:
        audio_content_dur = abs(a_offset)
    else:
        audio_content_dur = abs(v_override) if v_override is not None and v_override < 0 else 1.0
    trim_front_s = 0.0
    audio_delay = 0.0

    intro_tpls = list(amb_dir.glob("*_intro.tpl"))
    intro_wavs = list(amb_dir.glob("*_intro.wav"))

    if intro_tpls:
        intro_name = intro_tpls[0].stem
        intro_wav = intro_wavs[0] if intro_wavs else amb_dir / f"{intro_name}.wav"
    else:
        if intro_wavs:
            intro_wav = intro_wavs[0]
            intro_name = intro_wav.stem
        else:
            intro_name = f"amb_{map_lower}_intro"
            intro_wav = amb_dir / f"{intro_name}.wav"

        wav_rel_path = f"world/maps/{map_lower}/audio/amb/{intro_name}.wav"
        ilu_content = f'''DESCRIPTOR =
{{
\t{{
\t\tNAME = "SoundDescriptor_Template",
\t\tSoundDescriptor_Template =
\t\t{{
\t\t\tname = "{intro_name}",
\t\t\tvolume = 0,
\t\t\tcategory = "AMB",
\t\t\tlimitCategory = "",
\t\t\tlimitMode = 0,
\t\t\tmaxInstances = 4294967295,
\t\t\tfiles =
\t\t\t{{
\t\t\t\t{{
\t\t\t\t\tVAL = "{wav_rel_path}",
\t\t\t\t}},
\t\t\t}},
\t\t\tserialPlayingMode = 0,
\t\t\tserialStoppingMode = 0,
\t\t\tparams =
\t\t\t{{
\t\t\t\tNAME = "SoundParams",
\t\t\t\tSoundParams =
\t\t\t\t{{
\t\t\t\t\tloop = 0,
\t\t\t\t\tplayMode = 1,
\t\t\t\t\tplayModeInput = "",
\t\t\t\t\trandomVolMin = 0,
\t\t\t\t\trandomVolMax = 0,
\t\t\t\t\tdelay = 0,
\t\t\t\t\trandomDelay = 0,
\t\t\t\t\trandomPitchMin = 1,
\t\t\t\t\trandomPitchMax = 1,
\t\t\t\t\tfadeInTime = 0,
\t\t\t\t\tfadeOutTime = 0,
\t\t\t\t\tfilterFrequency = 0,
\t\t\t\t\tfilterType = 2,
\t\t\t\t\ttransitionSampleOffset = 0,
\t\t\t\t}},
\t\t\t}},
\t\t\tpauseInsensitiveFlags = 0,
\t\t\toutDevices = 4294967295,
\t\t\tsoundPlayAfterdestroy = 0,
\t\t}},
\t}},
}}
appendTable(component.SoundComponent_Template.soundList,DESCRIPTOR)'''

        tpl_content = f'''params=
{{
\tNAME="Actor_Template",
\tActor_Template=
\t{{
\t\tCOMPONENTS=
\t\t{{
\t\t}}
\t}}
}}
includeReference("EngineData/Misc/Components/SoundComponent.ilu")
includeReference("world/maps/{map_lower}/audio/amb/{intro_name}.ilu")'''

        (amb_dir / f"{intro_name}.ilu").write_text(ilu_content, encoding="utf-8")
        (amb_dir / f"{intro_name}.tpl").write_text(tpl_content, encoding="utf-8")

    delay_ms = int(audio_delay * 1000)
    af_filter = f"adelay={delay_ms}|{delay_ms},asetpts=PTS-STARTPTS" if delay_ms > 0 else ""

    ffmpeg_path = getattr(config, "ffmpeg_path", "ffmpeg") if config else "ffmpeg"
    ffmpeg_args = [ffmpeg_path, "-y"]
    if trim_front_s > 0:
        ffmpeg_args += ["-ss", f"{trim_front_s:.3f}"]
    ffmpeg_args += ["-t", f"{audio_content_dur:.3f}", "-i", str(ogg_path)]
    if af_filter:
        ffmpeg_args += ["-af", af_filter]
    # Output as PCM WAV — JD2017 engine requires WAV for AMB sounds
    ffmpeg_args += ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(intro_wav)]

    _run_subprocess(ffmpeg_args, "Generate intro AMB WAV")

def extract_amb_clips(
    cinematic_tape,
    audio_path: Path,
    target_dir: Path,
    codename: str,
    config=None,
) -> int:
    if not cinematic_tape or not audio_path.exists():
        return 0

    count = 0
    map_lower = codename.lower()
    amb_dir = target_dir / "audio" / "amb"
    amb_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_path = getattr(config, "ffmpeg_path", "ffmpeg") if config else "ffmpeg"

    for clip in cinematic_tape.clips:
        if not hasattr(clip, "sound_set_path"):
            continue

        clip_name = clip.sound_set_path.split("/")[-1].split(".")[0]
        if f"amb_{map_lower}_intro" in clip_name:
            continue

        # In JD2017, AMB uses OGG instead of WAV
        output_ogg = amb_dir / f"{clip_name}.ogg"
        if output_ogg.exists() and output_ogg.stat().st_size > 10240:
            continue

        start_s = max(0.0, clip.start_time / 1000.0)
        duration_s = clip.duration / 1000.0
        fade_start = max(0, duration_s - 0.200)

        ffmpeg_args = [ffmpeg_path, "-y"]
        if start_s > 0:
            ffmpeg_args += ["-ss", f"{start_s:.6f}"]
        ffmpeg_args += [
            "-i", str(audio_path),
            "-t", f"{duration_s:.6f}",
            "-af", f"afade=t=out:st={fade_start:.6f}:d=0.200",
            "-c:a", "libvorbis", "-q:a", "6", "-ar", "48000", str(output_ogg),
        ]
        _run_subprocess(ffmpeg_args, f"Extract AMB clip {clip_name}")
        count += 1

    return count


def copy_video(
    src_path: str | Path,
    dst_path: str | Path,
    config=None,
) -> Path:
    """Copy a video file to the destination, creating dirs as needed."""
    src = Path(src_path)
    dst = Path(dst_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")

    shutil.copy2(src, dst)
    logger.debug("Copied video: %s -> %s", src.name, dst)
    return dst


def apply_audio_gain(
    audio_path: str | Path,
    gain_db: float,
    config=None,
) -> Path:
    """Apply FFmpeg gain to a single audio file in-place."""
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    tmp = src.with_name(src.stem + ".gain_tmp" + src.suffix)
    ffmpeg_path = getattr(config, "ffmpeg_path", "ffmpeg") if config else "ffmpeg"

    _run_subprocess(
        [ffmpeg_path, "-y", "-i", str(src), "-af", f"volume={gain_db}dB", str(tmp)],
        "apply_audio_gain",
    )

    tmp.replace(src)
    logger.debug("Applied %+0.1fdB gain: %s", gain_db, src.name)
    return src


def copy_moves(
    moves_src_dir: str | Path,
    target_dir: str | Path,
    *,
    skip_gestures: bool = False,
) -> int:
    """Copy move files from source to target directory."""
    import os

    src_root = Path(moves_src_dir)
    if not src_root.is_dir():
        return 0

    moves_target_root = Path(target_dir) / "timeline" / "moves"
    durango_moves_dir = moves_target_root / "durango"
    pc_moves_dir = moves_target_root / "pc"
    total_copied = 0

    for plat_dir in src_root.iterdir():
        if not plat_dir.is_dir():
            continue

        for move_file in plat_dir.rglob("*"):
            if not move_file.is_file():
                continue
            ext_low = move_file.suffix.lower()
            if ext_low not in (".gesture", ".msm"):
                continue
            if skip_gestures and ext_low == ".gesture":
                continue

            dest = durango_moves_dir / move_file.name
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(move_file, dest)
                total_copied += 1

            if ext_low == ".gesture":
                pc_dest = pc_moves_dir / move_file.name
                if not pc_dest.exists():
                    pc_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(move_file, pc_dest)

    return total_copied


def process_menu_art(target_dir: str | Path, codename: str) -> int:
    """Post-process menu art files (no-op placeholder for compatibility)."""
    return 0
