"""Raw source → NormalizedMapData normalizer for JD2017 PC.

Transforms raw JSON metadata from various sources (JDU, JDNext, JDLO, manual)
into the unified NormalizedMapData structure consumed by the game_writer and
media_processor modules.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("jd2017.parsers.normalizer")


def _safe_int(val: Any, default: int = 0) -> int:
    """Coerce a value to int, falling back to default."""
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Coerce a value to float, falling back to default."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _extract_songdesc(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract SongDesc fields from various JSON formats.

    Handles both JDU format (nested under 'SongDesc') and flat format.
    """
    # JDU/JDLO format: songdesc is at top level or under a component key
    if "SongDesc" in raw:
        return raw["SongDesc"]
    if "__class" in raw and raw["__class"] == "JD_SongDescTemplate":
        return raw

    # Try nested actor template format
    components = raw.get("COMPONENTS", [])
    for comp in components:
        if isinstance(comp, dict):
            if "JD_SongDescTemplate" in comp:
                return comp["JD_SongDescTemplate"]
            if comp.get("__class") == "JD_SongDescTemplate":
                return comp

    return raw


def _extract_musictrack(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract MusicTrackStructure from various JSON formats."""
    if "MusicTrackStructure" in raw:
        return raw["MusicTrackStructure"]
    if "structure" in raw:
        inner = raw["structure"]
        if isinstance(inner, dict) and "MusicTrackStructure" in inner:
            return inner["MusicTrackStructure"]
        return inner
    return raw


def _parse_color(val: Any) -> list[float] | str:
    """Parse a color value to either a [R,G,B,A] float array or hex string."""
    if isinstance(val, str) and val.startswith("0x"):
        return val
    if isinstance(val, (list, tuple)):
        return [float(c) for c in val]
    return "0xFFFFFFFF"


def normalize_songdesc(raw_songdesc: dict[str, Any], codename: str) -> dict[str, Any]:
    """Normalize a raw songdesc JSON into the fields expected by game_writer.

    Returns:
        Dictionary with normalized song description fields.
    """
    sd = _extract_songdesc(raw_songdesc)

    # DefaultColors
    dc_raw = sd.get("DefaultColors", sd.get("defaultColors", {}))
    default_colors = {
        "lyrics": _parse_color(dc_raw.get("lyrics", "0xFFFFFFFF")),
        "theme": _parse_color(dc_raw.get("theme", "0xFFFFFFFF")),
        "songcolor_1a": _parse_color(dc_raw.get("songcolor_1a", dc_raw.get("SongColor_1A", "0xFFFFFFFF"))),
        "songcolor_1b": _parse_color(dc_raw.get("songcolor_1b", dc_raw.get("SongColor_1B", "0xFFFFFFFF"))),
        "songcolor_2a": _parse_color(dc_raw.get("songcolor_2a", dc_raw.get("SongColor_2A", "0xFFFFFFFF"))),
        "songcolor_2b": _parse_color(dc_raw.get("songcolor_2b", dc_raw.get("SongColor_2B", "0xFFFFFFFF"))),
    }

    return {
        "codename": codename,
        "map_name": sd.get("MapName", codename),
        "title": sd.get("Title", "Unknown Title"),
        "artist": sd.get("Artist", "Unknown Artist"),
        "dancer_name": sd.get("DancerName", "Unknown"),
        "credits": sd.get("Credits", ""),
        "num_coach": _safe_int(sd.get("NumCoach", 1)),
        "main_coach": _safe_int(sd.get("MainCoach", -1)),
        "difficulty": _safe_int(sd.get("Difficulty", 1)),
        "sweat_difficulty": _safe_int(sd.get("SweatDifficulty", 1)),
        "energy": _safe_int(sd.get("Energy", 0)),
        "lyrics_type": _safe_int(sd.get("LyricsType", 0)),
        "background_type": _safe_int(sd.get("backgroundType", 0)),
        "status": _safe_int(sd.get("Status", 3)),
        "locale_id": _safe_int(sd.get("LocaleID", sd.get("LocId", 0))),
        "jd_version": _safe_int(sd.get("JDVersion", 2017)),
        "original_jd_version": _safe_int(sd.get("OriginalJDVersion", 2017)),
        "tags": sd.get("Tags", ["Main"]),
        "default_colors": default_colors,
    }


def normalize_musictrack(raw_mt: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw musictrack JSON into the fields expected by game_writer.

    Returns:
        Dictionary with normalized music track fields.
    """
    mt = _extract_musictrack(raw_mt)

    return {
        "start_beat": _safe_int(mt.get("startBeat", 0)),
        "end_beat": _safe_int(mt.get("endBeat", 0)),
        "video_start_time": _safe_float(mt.get("videoStartTime", 0.0)),
        "preview_entry": _safe_float(mt.get("previewEntry", 0.0)),
        "preview_loop_start": _safe_float(mt.get("previewLoopStart", 0.0)),
        "preview_loop_end": _safe_float(mt.get("previewLoopEnd", 0.0)),
        "volume": _safe_float(mt.get("volume", 0.0)),
        "fade_in_duration": _safe_int(mt.get("fadeInDuration", 0)),
        "fade_in_type": _safe_int(mt.get("fadeInType", 0)),
        "fade_out_duration": _safe_int(mt.get("fadeOutDuration", 0)),
        "fade_out_type": _safe_int(mt.get("fadeOutType", 0)),
        "markers": [m.get("VAL", m) if isinstance(m, dict) else m
                    for m in mt.get("markers", [])],
        "signatures": mt.get("signatures", []),
        "sections": mt.get("sections", []),
    }


def load_and_normalize_songdesc_file(path: Path, codename: str) -> dict[str, Any]:
    """Load a songdesc JSON/CKD file and return normalized data."""
    content = path.read_bytes()
    text = content.lstrip(b"\x00\xef\xbb\xbf").decode("utf-8", errors="replace").strip('\x00\r\n\t ')
    raw = json.loads(text)
    return normalize_songdesc(raw, codename)



def normalize(*args, **kwargs): return None
