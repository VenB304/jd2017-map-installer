"""Native pure Python UbiArt IPK Packer and Unpacker for JD2017 PC.

Handles both packing directories into big-endian uncompressed IPK archives
and unpacking existing IPK archives into directory trees.

The entry format (version 5) per file is:
  - 28 bytes fixed fields (7 × u32)
  - u32 name_size
  - name_size bytes filename
  - u32 path_size
  - path_size bytes path (with trailing slash)
  - 4 bytes CRC/hash
  - u32 flags

Credits:
- PartyService (https://github.com/PartyService): UbiArt archive format specifications
"""

from __future__ import annotations

import logging
import os
import struct
import zlib
from pathlib import Path

logger = logging.getLogger("jd2017.installers.ipk_packer")

# IPK format constants
_IPK_MAGIC = b"\x50\xEC\x12\xBA"
_IPK_VERSION = 5  # JD17 uses version 5
_IPK_PLATFORM_PC = 8


def _crc32_bytes(data: bytes) -> bytes:
    """Compute CRC32 and return as 4 big-endian bytes."""
    return (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "big")


def pack_folder_to_ipk(source_dir: Path, output_ipk: Path) -> None:
    """Pack a directory of files natively into a big-endian uncompressed UbiArt IPK.

    Compatible with Just Dance 2017 PC (version 5, platform 8).

    Args:
        source_dir: Root directory containing files to pack.
        output_ipk: Output path for the .ipk file.
    """
    source_dir = Path(source_dir).resolve()
    logger.info("Packing %s -> %s", source_dir, output_ipk)

    # 1. Walk directory and collect all files with relative paths
    files_list: list[tuple[Path, str]] = []
    for root, _, files in os.walk(source_dir):
        for file in sorted(files):
            full_path = Path(root) / file
            rel_path = full_path.relative_to(source_dir).as_posix()
            files_list.append((full_path, rel_path))

    num_files = len(files_list)
    logger.info("Collected %d files to pack", num_files)

    # 2. Build entry metadata and read file data
    entries_meta: list[dict] = []
    file_data_list: list[bytes] = []

    for full_path, rel_path in files_list:
        file_name = full_path.name
        path_name = os.path.dirname(rel_path)
        if path_name:
            path_name += "/"

        file_name_bytes = file_name.encode("utf-8")
        path_name_bytes = path_name.encode("utf-8")
        file_bytes = full_path.read_bytes()

        entries_meta.append({
            "file_name_bytes": file_name_bytes,
            "path_name_bytes": path_name_bytes,
            "size": len(file_bytes),
            "crc": _crc32_bytes(file_bytes),
        })
        file_data_list.append(file_bytes)

    # 3. Calculate entry table size
    # Header: 48 bytes (12 × u32)
    # Entry: 28 fixed + 4 name_size + name + 4 path_size + path + 4 hash + 4 flags
    header_size = 48
    entries_size = 0
    for meta in entries_meta:
        entries_size += 28 + 4 + len(meta["file_name_bytes"]) + 4 + len(meta["path_name_bytes"]) + 4 + 4
    base_offset = header_size + entries_size

    # 4. Compile header (48 bytes = 12 × u32)
    header_buf = struct.pack(
        ">4sIIIII",
        _IPK_MAGIC,
        _IPK_VERSION,
        _IPK_PLATFORM_PC,
        base_offset,
        num_files,
        0,  # compressed = 0
    )
    # Remaining 6 × u32 (reserved + numFiles repeated)
    header_buf += struct.pack(">IIIIII", 0, 0, 0, 0, 0, num_files)

    # 5. Compile entry table
    entries_buf = bytearray()
    current_data_offset = 0

    for meta in entries_meta:
        # 28 bytes fixed fields: (u32 × 3) + (u32 × 2 as 8-byte offset) + (u32 × 2)
        # Field layout matching real IPK v5:
        #   u32 numOffset (entry index, 1-based seen in real files)
        #   u32 uncompressed_size
        #   u32 compressed_size (0)
        #   u32 data_offset_high (0 for small files)
        #   u32 data_offset_low
        #   u32 timestamp (0)
        #   u32 reserved (0)
        entry_fixed = struct.pack(
            ">IIIIIII",
            1,                      # numOffset
            meta["size"],           # uncompressed size
            0,                      # compressed size
            0,                      # data offset high
            current_data_offset,    # data offset low
            0,                      # timestamp
            0,                      # reserved
        )
        entries_buf.extend(entry_fixed)

        # name_size + name
        entries_buf.extend(struct.pack(">I", len(meta["file_name_bytes"])))
        entries_buf.extend(meta["file_name_bytes"])

        # path_size + path
        entries_buf.extend(struct.pack(">I", len(meta["path_name_bytes"])))
        entries_buf.extend(meta["path_name_bytes"])

        # CRC hash + flags
        entries_buf.extend(meta["crc"])
        entries_buf.extend(struct.pack(">I", 2))  # flags=2 (seen in real IPKs)

        current_data_offset += meta["size"]

    # 6. Write output
    output_ipk.parent.mkdir(parents=True, exist_ok=True)
    with open(output_ipk, "wb") as f_out:
        f_out.write(header_buf)
        f_out.write(entries_buf)
        for file_bytes in file_data_list:
            f_out.write(file_bytes)

    logger.info("Packed IPK: %s (%d files, %d bytes)",
                output_ipk.name, num_files, output_ipk.stat().st_size)


def unpack_ipk_to_folder(ipk_path: Path, output_dir: Path) -> list[str]:
    """Unpack a UbiArt IPK archive natively into a directory tree.

    Args:
        ipk_path: Path to the .ipk archive.
        output_dir: Output directory for extracted files.

    Returns:
        List of extracted relative file paths.
    """
    logger.info("Unpacking %s -> %s", ipk_path, output_dir)
    extracted_files: list[str] = []

    with open(ipk_path, "rb") as f:
        # Read header (first 24 bytes)
        magic = f.read(4)
        if magic != _IPK_MAGIC:
            raise ValueError(f"Invalid IPK magic: {magic!r}")

        version = struct.unpack(">I", f.read(4))[0]
        _platform = struct.unpack(">I", f.read(4))[0]
        base_offset = struct.unpack(">I", f.read(4))[0]
        num_files = struct.unpack(">I", f.read(4))[0]
        _compressed = struct.unpack(">I", f.read(4))[0]

        # Skip remaining header (24 bytes: 6 × u32)
        f.read(24)

        logger.debug("IPK v%d: %d files, base_offset=%d", version, num_files, base_offset)

        # Read entries
        entries: list[dict] = []
        for _ in range(num_files):
            # 28 bytes fixed fields
            fixed = f.read(28)
            vals = struct.unpack(">IIIIIII", fixed)
            _num_offset = vals[0]
            size = vals[1]
            _compressed_size = vals[2]
            data_offset_high = vals[3]
            data_offset_low = vals[4]
            data_offset = (data_offset_high << 32) | data_offset_low

            # name
            name_len = struct.unpack(">I", f.read(4))[0]
            file_name = f.read(name_len).decode("utf-8", errors="replace")

            # path
            path_len = struct.unpack(">I", f.read(4))[0]
            file_path = f.read(path_len).decode("utf-8", errors="replace")

            # hash + flags
            _crc = f.read(4)
            _flags = f.read(4)

            entries.append({
                "name": file_name,
                "path": file_path,
                "size": size,
                "data_offset": data_offset,
            })

        # Extract files
        for entry in entries:
            rel_path = entry["path"] + entry["name"]
            out_file = output_dir / rel_path

            out_file.parent.mkdir(parents=True, exist_ok=True)

            f.seek(base_offset + entry["data_offset"])
            data = f.read(entry["size"])

            with open(out_file, "wb") as out:
                out.write(data)

            extracted_files.append(rel_path)

    logger.info("Extracted %d files from %s", len(extracted_files), ipk_path.name)
    return extracted_files
