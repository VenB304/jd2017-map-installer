"""Binary CKD format reader for JD2017 PC cooked assets.

Handles reading and extracting data from UbiArt .ckd files, including:
- Texture CKD (.tga.ckd): 44-byte header + DDS payload
- JSON CKD (.tpl.ckd, .stape.ckd, etc.): plain UTF-8 JSON
- XML CKD (.isc.ckd): plain UTF-8/Latin-1 XML

Credits:
- BLDS (Just Dance Tools 1.9.0): CKD header format analysis
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("jd2017.parsers.binary_ckd")

# UbiArt CKD texture header size (always 44 bytes for PC)
_CKD_HEADER_SIZE = 44

# DDS magic bytes
_DDS_MAGIC = b"DDS "


def read_json_ckd(ckd_path: Path) -> dict[str, Any]:
    """Read a JSON-encoded CKD file (.tpl.ckd, .stape.ckd, .tape.ckd, etc.).

    Args:
        ckd_path: Path to the CKD file.

    Returns:
        Parsed JSON content as a dictionary.
    """
    content = ckd_path.read_bytes()

    # Some CKD files may have a BOM or leading null bytes
    text = content.lstrip(b"\x00\xef\xbb\xbf").decode("utf-8", errors="replace")

    return json.loads(text)


def read_xml_ckd(ckd_path: Path) -> str:
    """Read an XML-encoded CKD file (.isc.ckd).

    Args:
        ckd_path: Path to the CKD file.

    Returns:
        XML content as a string.
    """
    content = ckd_path.read_bytes()
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def strip_ckd_header(ckd_path: Path, output_path: Path | None = None) -> bytes:
    """Strip the 44-byte UbiArt CKD header from a texture file, returning raw DDS.

    Args:
        ckd_path: Path to a .tga.ckd or similar cooked texture file.
        output_path: Optional output path for the raw DDS file. If provided,
                     the DDS content is written to this path.

    Returns:
        Raw DDS content bytes (including the DDS magic header).

    Raises:
        ValueError: If the file doesn't contain valid DDS data after header stripping.
    """
    content = ckd_path.read_bytes()

    if len(content) <= _CKD_HEADER_SIZE:
        raise ValueError(f"CKD file too small ({len(content)} bytes): {ckd_path}")

    dds_data = content[_CKD_HEADER_SIZE:]

    if not dds_data.startswith(_DDS_MAGIC):
        logger.warning("No DDS magic found after stripping CKD header in %s", ckd_path.name)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(dds_data)
        logger.debug("Stripped CKD header: %s -> %s", ckd_path.name, output_path.name)

    return dds_data


def wrap_with_ckd_header(dds_data: bytes, width: int, height: int,
                          output_path: Path | None = None) -> bytes:
    """Wrap raw DDS data with a 44-byte UbiArt CKD texture header.

    This delegates to the texture_encoder module for the actual header generation.

    Args:
        dds_data: Raw DDS file content (with DDS magic).
        width: Texture width in pixels (unused for static header).
        height: Texture height in pixels (unused for static header).
        output_path: Optional output path. If provided, the CKD is written.

    Returns:
        Complete CKD content (header + DDS data).
    """
    from jd2017_installer.installers.texture_encoder import wrap_dds_to_tga_ckd

    ckd_data = wrap_dds_to_tga_ckd(dds_data)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(ckd_data)
        logger.debug("Wrapped DDS with CKD header: %s", output_path.name)

    return ckd_data


def is_json_ckd(ckd_path: Path) -> bool:
    """Check if a CKD file contains JSON content (vs binary/XML)."""
    try:
        head = ckd_path.read_bytes(256) if hasattr(ckd_path, 'read_bytes') else b""
        head = ckd_path.read_bytes()[:256]
        stripped = head.lstrip(b"\x00\xef\xbb\xbf")
        return stripped.startswith(b"{") or stripped.startswith(b"[")
    except Exception:
        return False


def is_xml_ckd(ckd_path: Path) -> bool:
    """Check if a CKD file contains XML content."""
    try:
        head = ckd_path.read_bytes()[:256]
        stripped = head.lstrip(b"\x00\xef\xbb\xbf")
        return stripped.startswith(b"<?xml") or stripped.startswith(b"<root")
    except Exception:
        return False
