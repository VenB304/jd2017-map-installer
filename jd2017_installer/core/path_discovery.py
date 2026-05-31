"""Tools for discovering and verifying the JD2017 installation directory."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jd2017.core.path_discovery")

# Folders to skip during a deep recursive scan to save time
_SCAN_SKIP_DIRS = {
    ".git", "__pycache__", "logs", "downloads", "cache",
    "main_scene_extracted", "ipk_extracted", "tools", "xtx_extractor"
}

# JD2017 PC uses cooked binary ISC files in patch_pc
_TARGET_FILE = "skuscene_maps_pc_all.isc.ckd"
_TARGET_SUBPATH = ("cache", "itf_cooked", "pc", "world", "skuscenes", _TARGET_FILE)
_DEEP_SCAN_CACHE_TTL_S = 600.0
_DEEP_SCAN_CACHE: dict[Path, tuple[float, Optional[Path]]] = {}

# Expected game directory markers for JD2017 PC
_GAME_MARKERS = ("bundle_pc.ipk", "bundlelogic_pc.ipk")


def clear_deep_scan_cache(search_root: Optional[Path] = None) -> None:
    """Clear cached deep-scan results."""
    if search_root is None:
        _DEEP_SCAN_CACHE.clear()
        return
    _DEEP_SCAN_CACHE.pop(search_root.resolve(), None)


def is_valid_game_dir(candidate: Path) -> bool:
    """Verifies a folder contains the essential JD2017 PC game files.

    Checks for the existence of bundle_pc.ipk and bundle_logic.ipk.
    """
    if not candidate or not candidate.is_dir():
        return False
    return all((candidate / marker).is_file() for marker in _GAME_MARKERS)


def has_patch_pc(game_dir: Path) -> bool:
    """Check if patch_pc.ipk exists in the game directory."""
    return (game_dir / "patch_pc.ipk").is_file()


def count_bundle_ipks(game_dir: Path) -> int:
    """Count existing numbered bundle_*_pc.ipk files in the game directory.

    Returns the highest bundle number found, or 0 if none exist.
    """
    max_num = 0
    pattern = re.compile(r"^bundle_(\d+)_pc\.ipk$", re.IGNORECASE)
    try:
        for entry in game_dir.iterdir():
            m = pattern.match(entry.name)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
    except OSError:
        pass
    return max_num


def next_bundle_index(game_dir: Path) -> int:
    """Return the next available bundle index number."""
    return count_bundle_ipks(game_dir) + 1


def resolve_game_paths(search_root: Path) -> Optional[Path]:
    """Fast heuristics to locate the JD2017 Game directory.

    Checks:
    1. search_root/  (User pointed directly to the root)
    2. Common subdirectory patterns

    Returns:
        The valid Game Root Path or None if not found via heuristics.
    """
    logger.debug("Running quick heuristics for JD2017 game directory starting at: %s", search_root)

    # 1. Direct reference
    if is_valid_game_dir(search_root):
        logger.debug("Found JD2017 layout directly at: %s", search_root)
        return search_root

    # 2. Common Steam/SteamRIP patterns
    for subdir_name in ("Just Dance 2017", "jd2017", "JD2017"):
        candidate = search_root / subdir_name
        if is_valid_game_dir(candidate):
            logger.debug("Found JD2017 layout at: %s", candidate)
            return candidate

    # 3. Up one folder
    for subdir_name in ("Just Dance 2017", "jd2017", "JD2017"):
        candidate = search_root.parent / subdir_name
        if is_valid_game_dir(candidate):
            logger.debug("Found JD2017 layout via parent: %s", candidate)
            return candidate

    logger.debug("Quick heuristics failed.")
    return None


def deep_scan_for_game_dir(search_root: Path) -> Optional[Path]:
    """Perform a recursive walk to find the game directory structure.

    Returns:
        The confirmed Game Root Path, or None if not found.
    """
    cache_key = search_root.resolve()
    now = time.monotonic()
    cached = _DEEP_SCAN_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _DEEP_SCAN_CACHE_TTL_S:
        logger.debug("Using cached deep-scan result for %s", search_root)
        return cached[1]

    logger.debug("Starting deep scan for JD2017 game directory in %s", search_root)

    try:
        for root, dirs, files in os.walk(search_root):
            # Prune skipped dirs to speed up walk
            dirs[:] = [d for d in dirs if d not in _SCAN_SKIP_DIRS]

            if "bundle_pc.ipk" in files and "bundlelogic_pc.ipk" in files:
                game_dir = Path(root)
                logger.debug("Deep scan found JD2017 game directory at: %s", game_dir)
                _DEEP_SCAN_CACHE[cache_key] = (now, game_dir)
                return game_dir
    except (OSError, PermissionError) as e:
        logger.debug("Deep scan interrupted by permissions or IO error: %s", e)

    logger.debug("Deep scan complete. No JD2017 game directory found.")
    _DEEP_SCAN_CACHE[cache_key] = (now, None)
    return None


def infer_codename(path: Path) -> str:
    """Infer a map codename from a file or directory path, cleaning platform suffixes."""
    base = path.stem if path.is_file() else path.name
    cleaned = re.sub(r"(_(x360|durango|scarlett|nx|orbis|prospero|pc))+$", "", base, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\((\d+)\)$", "", cleaned)
    logger.debug("Inferred codename '%s' from path: %s", cleaned, path)
    return cleaned
