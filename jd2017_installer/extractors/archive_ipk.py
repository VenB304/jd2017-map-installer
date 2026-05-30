"""IPK archive extractor and native packer.

Extracts .ipk files (Ubisoft's proprietary archive format) and can also
PACK directories into uncompressed big-endian IPK archives natively in
pure Python — no external tools required.

Based on the UbiArt IPK format specifications from ubiart-archive-tools
by PartyService (https://github.com/PartyService).
"""

from __future__ import annotations

import logging
import os
import re
import struct
import zlib
import lzma
from pathlib import Path
from typing import Iterator, Optional

from jd2017_installer.core.exceptions import IPKExtractionError
from jd2017_installer.extractors.base import BaseExtractor

logger = logging.getLogger("jd2017.extractors.archive_ipk")

# Big-endian for IPK format
_ENDIAN = ">"
_STRUCT_SIGNS = {1: "c", 2: "H", 4: "I", 8: "Q"}

_IPK_MAGIC = b"\x50\xEC\x12\xBA"

# Guard against corrupted headers that claim absurd file counts.
_MAX_IPK_FILE_COUNT = 100_000

# Streaming thresholds for decompression.
_STREAMING_CHUNK = 256 * 1024       # 256 KB read chunk
_STREAMING_THRESHOLD = 4 * 1024 * 1024  # Switch to streaming above 4 MB


def validate_ipk_magic(target_file: str | Path) -> None:
    """Validate IPK magic bytes before expensive extraction work.

    Raises:
        IPKExtractionError: If the file is missing or does not start with IPK magic.
    """
    target_path = Path(target_file)
    if not target_path.exists():
        raise IPKExtractionError(f"IPK file not found: {target_path}")

    with open(target_path, "rb") as f:
        magic = f.read(4)
    if magic != _IPK_MAGIC:
        raise IPKExtractionError("Not a valid IPK file (bad magic bytes)")


def _unpack(data: bytes) -> int:
    """Unpack a big-endian integer of 1/2/4/8 bytes."""
    return struct.unpack(_ENDIAN + _STRUCT_SIGNS[len(data)], data)[0]


def _read_header_fields(f, template: dict) -> dict:
    """Read header fields from file into dict with 'value' keys."""
    result = {k: dict(v) for k, v in template.items()}
    for v in result.values():
        v["value"] = f.read(v["size"])
    return result


_IPK_HEADER_TEMPLATE = {
    "magic": {"size": 4},
    "version": {"size": 4},
    "platformsupported": {"size": 4},
    "base_offset": {"size": 4},
    "num_files": {"size": 4},
    "compressed": {"size": 4},
    "binaryscene": {"size": 4},
    "binarylogic": {"size": 4},
    "datasignature": {"size": 4},
    "enginesignature": {"size": 4},
    "engineversion": {"size": 4},
    "num_files2": {"size": 4},
}


def _get_file_header() -> dict:
    return {
        "numOffset": {"size": 4},
        "size": {"size": 4},
        "compressed_size": {"size": 4},
        "time_stamp": {"size": 8},
        "offset": {"size": 8},
        "name_size": {"size": 4},
        "file_name": {"size": 0},   # resolved at read-time from name_size
        "path_size": {"size": 4},
        "path_name": {"size": 4},   # resolved at read-time from path_size
        "checksum": {"size": 4},
        "flag": {"size": 4},
    }


def _iter_file_headers(f, num_files: int) -> Iterator[dict]:
    """Lazily yield file-entry header dicts from an open IPK stream."""
    for _ in range(num_files):
        fheader = _get_file_header()
        for v in fheader:
            size = fheader[v]["size"]
            if v == "path_name":
                size = _unpack(fheader["path_size"]["value"])
            if v == "file_name":
                size = _unpack(fheader["name_size"]["value"])
            fheader[v]["value"] = f.read(size)
        yield fheader


def _sniff_compression(probe: bytes) -> str:
    """Identify the compression codec from the leading bytes of a payload."""
    if len(probe) >= 2 and probe[0] == 0x78 and probe[1] in (0x9C, 0x01, 0xDA, 0x5E):
        return "zlib"
    if len(probe) >= 6 and probe[:6] == b"\xfd7zXZ\x00":
        return "lzma"
    if len(probe) >= 2 and probe[:2] == b"]\x00":
        return "lzma"
    return "raw"


def _decompress_to_file(f_in, f_out, data_size: int) -> None:
    """Read ``data_size`` bytes from ``f_in``, decompress, and write to ``f_out``."""
    if data_size < _STREAMING_THRESHOLD:
        raw = f_in.read(data_size)
        try:
            f_out.write(zlib.decompress(raw))
            return
        except zlib.error:
            pass
        try:
            f_out.write(lzma.decompress(raw))
            return
        except lzma.LZMAError:
            pass
        f_out.write(raw)
        return

    probe = f_in.read(min(16, data_size))
    remaining = data_size - len(probe)
    codec = _sniff_compression(probe)

    if codec == "zlib":
        try:
            dobj = zlib.decompressobj()
            f_out.write(dobj.decompress(probe))
            while remaining > 0:
                n = min(_STREAMING_CHUNK, remaining)
                f_out.write(dobj.decompress(f_in.read(n)))
                remaining -= n
            f_out.write(dobj.flush())
            return
        except zlib.error:
            logger.debug(
                "Streaming zlib decompression failed for %d-byte payload; "
                "skipping remaining %d bytes.",
                data_size, remaining,
            )
            if remaining > 0:
                f_in.read(remaining)
            return

    tail = f_in.read(remaining)
    full = probe + tail

    if codec == "lzma":
        try:
            f_out.write(lzma.decompress(full))
            return
        except lzma.LZMAError:
            pass

    offset = 0
    while offset < len(full):
        end = min(offset + _STREAMING_CHUNK, len(full))
        f_out.write(full[offset:end])
        offset = end


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_ipk(
    target_file: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[Path, list[str]]:
    """Extract an IPK archive to the given output directory.

    Returns:
        ``(output_path, codenames)`` — the extraction directory and the
        sorted list of map codenames discovered in the file-entry headers.
    """
    target_file = Path(target_file)
    output_path = Path(output_dir) if output_dir is not None else Path(target_file.stem)

    validate_ipk_magic(target_file)

    try:
        output_path.mkdir(exist_ok=True)

        with open(target_file, "rb") as f:
            ipk_header = _read_header_fields(f, _IPK_HEADER_TEMPLATE)

            num_files = _unpack(ipk_header["num_files"]["value"])
            if num_files > _MAX_IPK_FILE_COUNT:
                raise IPKExtractionError(
                    f"Suspicious file count in IPK header: {num_files:,}. "
                    "The archive may be corrupted or non-standard."
                )
            logger.debug("IPK: Found %d files...", num_files)

            file_chunks = list(_iter_file_headers(f, num_files))

            base_offset = _unpack(ipk_header["base_offset"]["value"])
            created_dirs: set[Path] = set()
            codenames_found: set[str] = set()
            extracted_files = 0

            for k, chunk in enumerate(file_chunks):
                path_ori = chunk["path_name"]["value"].decode().lower().replace('\\', '/')
                if "world/maps/" in path_ori:
                    after_maps = path_ori.split("world/maps/")[1]
                    parts = after_maps.split("/")
                    if parts and parts[0]:
                        codenames_found.add(parts[0])

                if k % 100 == 0:
                    status = f"file {k + 1}/{num_files}"
                    if codenames_found:
                        status += f" (maps: {', '.join(sorted(codenames_found))})"
                    logger.debug("IPK: Extracting %s...", status)

                offset = _unpack(chunk["offset"]["value"])
                uncompressed_size = _unpack(chunk["size"]["value"])
                compressed_size = _unpack(chunk["compressed_size"]["value"])
                disk_size = compressed_size if compressed_size > 0 else uncompressed_size

                path_ori_raw = chunk["path_name"]["value"].decode()
                file_ori_raw = chunk["file_name"]["value"].decode()

                # Check if fields are swapped
                if ("/" in file_ori_raw or "\\" in file_ori_raw) and not ("/" in path_ori_raw or "\\" in path_ori_raw):
                    file_path = output_path / file_ori_raw
                    file_name = path_ori_raw
                else:
                    file_path = output_path / path_ori_raw
                    file_name = file_ori_raw

                # Path traversal protection
                resolved = os.path.normpath(os.path.join(str(file_path), file_name))
                if not resolved.startswith(str(output_path)):
                    logger.debug("Skipping path-traversal entry: %s", resolved)
                    continue

                if os.path.abspath(resolved) == os.path.abspath(target_file):
                    logger.debug("Skipping self-referential entry: %s", resolved)
                    continue

                f.seek(offset + base_offset)
                if file_path not in created_dirs:
                    file_path.mkdir(parents=True, exist_ok=True)
                    created_dirs.add(file_path)

                with open(file_path / file_name, "wb") as ff:
                    _decompress_to_file(f, ff, disk_size)
                extracted_files += 1

        logger.info(
            "IPK: Extracted %d/%d files to %s",
            extracted_files, num_files, output_path,
        )
        return output_path, sorted(codenames_found)

    except IPKExtractionError:
        raise
    except Exception as exc:
        raise IPKExtractionError(f"Failed to extract IPK ({type(exc).__name__}): {exc}") from exc


def inspect_ipk(target_file: str | Path) -> list[str]:
    """Fast scan of the IPK to discover top-level map directories.

    Reads only file-entry headers without decompressing any data.
    """
    target_file = Path(target_file)
    if not target_file.exists():
        return []

    try:
        with open(target_file, "rb") as f:
            ipk_header = _read_header_fields(f, _IPK_HEADER_TEMPLATE)
            if ipk_header["magic"]["value"] != _IPK_MAGIC:
                return []

            num_files = _unpack(ipk_header["num_files"]["value"])
            if num_files > _MAX_IPK_FILE_COUNT:
                return []

            root_dirs: set[str] = set()

            for chunk in _iter_file_headers(f, num_files):
                raw_path = chunk["path_name"]["value"].decode(errors="ignore").replace('\\', '/')
                raw_file = chunk["file_name"]["value"].decode(errors="ignore").replace('\\', '/')

                candidates = []
                if "/" in raw_path:
                    candidates.append(raw_path)
                if "/" in raw_file:
                    candidates.append(raw_file)
                if not candidates:
                    candidates = [raw_path, raw_file]

                for candidate in candidates:
                    path_ori = candidate.lower()
                    if "world/maps/" in path_ori:
                        after_maps = path_ori.split("world/maps/")[1]
                        parts = [p for p in after_maps.split("/") if p]
                        if parts:
                            root_dirs.add(parts[0])

            ignore_list = {
                "cache", "common", "etc", "enginedata",
                "audio", "videoscoach", "localization",
            }
            return sorted(
                {d for d in root_dirs if d and not d.startswith(".") and d.lower() not in ignore_list}
            )

    except Exception as exc:
        logger.debug("Fast inspect failed for IPK %s: %s", target_file, exc)
        return []


# ---------------------------------------------------------------------------
# Native IPK Packer
# ---------------------------------------------------------------------------

def pack_folder_to_ipk(source_dir: Path, output_ipk: Path) -> None:
    """Pack a directory of files natively into a big-endian uncompressed UbiArt IPK.

    Compatible with Just Dance 2017 PC. Uses IPK version 5 with no compression.

    Based on the UbiArt IPK format from ubiart-archive-tools by PartyService.
    """
    source_dir = Path(source_dir).resolve()
    files_list = []
    for root, _, files in os.walk(source_dir):
        for file in sorted(files):
            full_path = Path(root) / file
            rel_path = full_path.relative_to(source_dir).as_posix()
            files_list.append((full_path, rel_path))

    num_files = len(files_list)
    if num_files == 0:
        logger.warning("pack_folder_to_ipk: No files found in %s", source_dir)
        return

    # Build entry metadata
    entries_meta = []
    entries_size = 0

    for full_path, rel_path in files_list:
        file_name = full_path.name
        path_name = os.path.dirname(rel_path)
        if path_name:
            path_name += "/"

        file_name_bytes = file_name.encode('utf-8')
        path_name_bytes = path_name.encode('utf-8')

        # Entry: 4 (numOffset) + 4 (size) + 4 (compressed_size)
        #      + 8 (timestamp) + 8 (offset)
        #      + 4 (name_size) + len(name) + 4 (path_size) + len(path)
        #      + 4 (checksum) + 4 (flag) = 44 + name + path
        entry_len = 44 + len(file_name_bytes) + len(path_name_bytes)
        entries_size += entry_len

        entries_meta.append({
            'full_path': full_path,
            'file_name_bytes': file_name_bytes,
            'path_name_bytes': path_name_bytes,
            'size': full_path.stat().st_size,
        })

    header_size = 48  # IPK global header
    base_offset = header_size + entries_size

    # Build global header (version 5 for JD17)
    header_buf = struct.pack(
        ">4sIIIIIIIIIII",
        _IPK_MAGIC,
        5,                  # version
        0,                  # platform PC
        base_offset,        # base offset where raw file data starts
        num_files,          # num files
        0,                  # compressed flag (0 = uncompressed)
        0, 0, 0, 0, 0,     # binaryscene, binarylogic, datasig, enginesig, enginever
        num_files,          # num files repeated
    )

    # Build per-file entry headers
    entries_buf = bytearray()
    current_data_offset = 0

    for meta in entries_meta:
        mtime = int(os.path.getmtime(meta['full_path']))

        entry = struct.pack(
            ">IIIQQIIII",
            0,                          # numOffset
            meta['size'],               # uncompressed size
            0,                          # compressed size (0 for raw)
            mtime,                      # timestamp
            current_data_offset,        # relative data offset
            len(meta['file_name_bytes']),  # name_size
            len(meta['path_name_bytes']),  # path_size
            0,                          # checksum
            0,                          # flags
        )
        entries_buf.extend(entry)
        entries_buf.extend(meta['file_name_bytes'])
        entries_buf.extend(meta['path_name_bytes'])

        current_data_offset += meta['size']

    # Write output
    output_ipk.parent.mkdir(parents=True, exist_ok=True)
    with open(output_ipk, "wb") as f_out:
        f_out.write(header_buf)
        f_out.write(entries_buf)

        for meta in entries_meta:
            with open(meta['full_path'], "rb") as f_in:
                f_out.write(f_in.read())

    logger.info("IPK: Packed %d files -> %s", num_files, output_ipk)


# ---------------------------------------------------------------------------
# Directory scanning helpers
# ---------------------------------------------------------------------------

def _detect_maps_in_dir(directory: Path) -> list[str]:
    """Scan a directory for map codenames using the UbiArt structure."""
    codenames: set[str] = set()

    maps_dirs = list(directory.rglob("world/maps"))
    for maps_dir in maps_dirs:
        if maps_dir.is_dir():
            for entry in maps_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith('.'):
                    codenames.add(entry.name)

    ignore_list = {"cache", "common", "etc", "enginedata", "audio", "videoscoach", "localization"}
    return sorted({c for c in codenames if c and c.lower() not in ignore_list})


def find_bundle_ipks(
    folder: Path,
    exclude: Optional[Path] = None,
) -> tuple[Optional[Path], Optional[Path]]:
    """Locate bundle and bundlelogic IPKs within a folder.

    Returns (bundle_ipk, bundlelogic_ipk); any entry can be None.
    """
    if not folder.exists() or not folder.is_dir():
        return None, None

    exclude_resolved = exclude.resolve() if exclude else None
    ipks = sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".ipk"],
        key=lambda p: p.name.lower(),
    )

    bundle_ipk: Optional[Path] = None
    bundlelogic_ipk: Optional[Path] = None
    for path in ipks:
        if exclude_resolved and path.resolve() == exclude_resolved:
            continue
        name = path.name.lower()
        if "bundlelogic" in name:
            if bundlelogic_ipk is None:
                bundlelogic_ipk = path
            continue
        if "bundle" in name:
            is_chunk = bool(re.search(r"bundle_\d+(_|\.ipk)", name))
            if bundle_ipk is None:
                bundle_ipk = path
            elif not is_chunk:
                existing_name = bundle_ipk.name.lower()
                existing_is_chunk = bool(re.search(r"bundle_\d+(_|\.ipk)", existing_name))
                if existing_is_chunk:
                    bundle_ipk = path

    return bundle_ipk, bundlelogic_ipk


def get_next_bundle_index(game_dir: Path) -> int:
    """Determine the next available bundle index for a new map IPK.

    Scans for existing bundle_N_pc.ipk files and returns N+1.
    """
    cache_dir = game_dir / "patch_pc" / "cache" / "itf_cooked" / "pc"
    if not cache_dir.exists():
        cache_dir = game_dir

    max_index = -1
    pattern = re.compile(r"bundle_(\d+)_pc\.ipk", re.IGNORECASE)

    for search_dir in [game_dir, cache_dir]:
        if not search_dir.exists():
            continue
        for f in search_dir.iterdir():
            if f.is_file():
                m = pattern.match(f.name)
                if m:
                    idx = int(m.group(1))
                    max_index = max(max_index, idx)

    return max_index + 1


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------

class ArchiveIPKExtractor(BaseExtractor):
    """Extractor for IPK archive files."""

    def __init__(self, ipk_path: str | Path, desired_codename: str | None = None) -> None:
        self._ipk_path = Path(ipk_path)
        self._codename: Optional[str] = None
        self._desired_codename = desired_codename.strip() if desired_codename else None
        self.bundle_maps: list[str] = []

    def extract(self, output_dir: Path) -> Path:
        result, header_codenames = extract_ipk(self._ipk_path, output_dir)

        actual_maps = _detect_maps_in_dir(result)
        discovered = sorted(set(actual_maps) | set(header_codenames))
        self.bundle_maps = discovered

        if len(discovered) == 1:
            self._codename = discovered[0]
            logger.info("Inferred codename from IPK: %s", self._codename)
        elif len(discovered) > 1:
            logger.info("Multiple maps discovered in IPK: %s", ", ".join(discovered))
            if self._desired_codename:
                target_matches = [m for m in discovered if m.lower() == self._desired_codename.lower()]
                if target_matches:
                    self._codename = target_matches[0]
                    return result

            base = self._ipk_path.stem
            stem = re.sub(
                r"_(x360|durango|scarlett|nx|orbis|prospero|pc|ps3|wiiu)$",
                "", base, flags=re.IGNORECASE,
            )
            matches = [m for m in discovered if m.lower() == stem.lower()]
            if matches:
                self._codename = matches[0]
            else:
                self._codename = discovered[0]
        else:
            base = self._ipk_path.stem
            stem = re.sub(
                r"_(x360|durango|scarlett|nx|orbis|prospero|pc|ps3|wiiu)$",
                "", base, flags=re.IGNORECASE,
            )
            self._codename = stem
            logger.debug("No maps in structure, using fallback: %s", self._codename)

        return result

    def get_codename(self) -> Optional[str]:
        return self._codename

    def get_ipk_path(self) -> Path:
        return self._ipk_path

    def get_source_dir(self) -> Path:
        """Return the folder that contains the selected .ipk file."""
        return self._ipk_path.parent
