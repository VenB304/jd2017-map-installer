"""Native secure_fat.gf generator for UbiArt games.

Natively integrated from the ubiart-secure-fat library by Wukko
(https://github.com/wukko). Walks game directories, parses all .ipk
archives, extracts directory entry hashes, and compiles the global
master table secure_fat.gf.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from jd2017_installer.core.exceptions import SecureFatError

logger = logging.getLogger("jd2017.installers.secure_fat_maker")

# Platform suffixes to strip from bundle names
_PLATFORM_SUFFIXES = ["pc", "wiiu", "wii", "nx", "x360", "durango", "scarlett", "ps3", "orbis", "prospero", "ggp"]

# Bundles to ignore (patch IPKs are not indexed)
_IGNORE_BUNDLES = ["patch"]

# IPK extension
_BUNDLE_EXT = ".ipk"


def _name_only(name: str) -> str:
    """Extract the clean bundle name from a path, stripping platform suffixes."""
    name = name.replace("\\", "/").split("/")[-1]
    for suffix in _PLATFORM_SUFFIXES:
        name = name.replace(_BUNDLE_EXT, "").replace("_" + suffix, "")
    return name


def _hash_list(ipk_path: str) -> List[bytes]:
    """Extract file entry hashes from an IPK archive header."""
    hashes = []
    try:
        with open(ipk_path, "rb") as f:
            f.read(16)
            filecount = int.from_bytes(f.read(4), "big")
            f.read(28)

            counter = 0
            while counter != filecount:
                f.read(28)
                name_size = int.from_bytes(f.read(4), "big")
                f.read(name_size)
                path_size = int.from_bytes(f.read(4), "big")
                f.read(path_size)
                hashes.append(f.read(4))
                f.read(4)
                counter += 1
    except Exception as exc:
        logger.warning("Failed to read hashes from %s: %s", ipk_path, exc)

    return hashes


def generate_secure_fat(game_dir: str | Path, output_path: str | Path | None = None) -> Path:
    """Generate the secure_fat.gf index file for all IPK bundles.

    Args:
        game_dir: Root game installation directory.
        output_path: Output path for secure_fat.gf. Defaults to
                     ``game_dir/secure_fat.gf``.

    Returns:
        Path to the generated secure_fat.gf file.

    Raises:
        SecureFatError: If generation fails.
    """
    game_dir = Path(game_dir)
    if output_path is None:
        output_path = game_dir / "secure_fat.gf"
    else:
        output_path = Path(output_path)

    if not game_dir.exists():
        raise SecureFatError(f"Game directory not found: {game_dir}")

    try:
        bundle_list: list[str] = []
        for root, _, file_names in os.walk(str(game_dir)):
            for fname in file_names:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, str(game_dir))
                if rel_path.lower().endswith(_BUNDLE_EXT):
                    bundle_list.append(rel_path)

        bundle_list = [
            b for b in bundle_list
            if _name_only(b) not in _IGNORE_BUNDLES
        ]
        bundle_list.sort()

        if not bundle_list:
            logger.warning("No IPK bundles found in %s", game_dir)

        bundle_count = 0
        hashes_count = 0
        body = b''
        footer = b''

        for bundle_rel in bundle_list:
            full_path = os.path.join(str(game_dir), bundle_rel)
            ipk_hashes = _hash_list(full_path)
            hashes_count += len(ipk_hashes)
            ipk_name = _name_only(bundle_rel).encode()

            for h in ipk_hashes:
                body += h + b'\x00\x00\x00\x01' + bundle_count.to_bytes(1, "big")

            footer += (
                bundle_count.to_bytes(1, "big")
                + len(ipk_name).to_bytes(4, "big")
                + ipk_name
            )
            bundle_count += 1

        header = (
            b'\x55\x53\x46\x54'  # "USFT" magic
            b'\x1F\x5E\xE4\x2F'  # version
            b'\x00\x00\x00\x01'  # flags
            + hashes_count.to_bytes(4, "big")
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(header)
            f.write(body)
            f.write(bundle_count.to_bytes(4, "big"))
            f.write(footer)

        logger.info(
            "Generated secure_fat.gf: %d bundles, %d hashes -> %s",
            bundle_count, hashes_count, output_path,
        )
        return output_path

    except SecureFatError:
        raise
    except Exception as exc:
        raise SecureFatError(f"Failed to generate secure_fat.gf: {exc}") from exc
