"""Native pure Python texture encoder for UbiArt PC (.tga.ckd).

Implements lossless CKD texture conversion (Switch/WiiU -> PC) and
uncompressed 32-bit BGRA DDS compilation from Pillow images.

Replaces the legacy JDTools CLI (scriptDDStoCKD.bms / scriptCKDtoRAW.bms)
and TexConv2/ddsconverter external dependencies entirely.

Based on texture format research by BLDS (Just Dance Tools 1.9.0).
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Optional

from PIL import Image

from jd2017_installer.core.exceptions import TextureEncodingError

logger = logging.getLogger("jd2017.installers.texture_encoder")

# Static 44-byte UbiArt PC CKD texture header
_CKD_TEXTURE_HEADER = (
    b'\x00\x00\x00\x09'  # CKD Magic
    b'\x54\x45\x58\x00'  # "TEX\x00"
    b'\x00\x00\x00\x2C'  # Header size (44 bytes)
    b'\x00\x00\x20\x80'  # Flags / texture description
    b'\x01\x00\x01\x00'  # Width / Height placeholder markers
    b'\x00\x01\x18\x00'  # DXT format identifiers
    b'\x00\x00\x20\x80'
    b'\x00\x00\x00\x00'
    b'\x00\x01\x00\x00'
    b'\x00\x00\x00\x00'
    b'\x00\x00\xCC\xCC'  # Footer padding
)


# ---------------------------------------------------------------------------
# CKD Stripping (for lossless conversion from other platforms)
# ---------------------------------------------------------------------------

def strip_ckd_header(ckd_bytes: bytes) -> tuple[bytes, str]:
    """Strip the 44-byte CKD header and detect the format payload.

    Returns:
        (payload_bytes, format_string) where format is 'dds', 'xtx', or 'raw'.
    """
    if len(ckd_bytes) < 44:
        raise TextureEncodingError("Invalid CKD payload size (< 44 bytes)")

    magic = ckd_bytes[:4]
    tex_marker = ckd_bytes[4:7]
    if magic != b'\x00\x00\x00\x09' or tex_marker != b'TEX':
        raise TextureEncodingError("Not a valid texture CKD file")

    payload = ckd_bytes[44:]
    if payload[:4] == b'DDS ':
        return payload, 'dds'
    elif payload[:4] == b'\x44\x46\x76\x4E':  # "DFvN" (Switch XTX)
        return payload, 'xtx'

    return payload, 'raw'


def wrap_dds_to_tga_ckd(dds_bytes: bytes) -> bytes:
    """Wrap standard DDS file bytes in a UbiArt PC texture CKD header.

    Args:
        dds_bytes: Raw DDS file content (must start with b'DDS ').

    Returns:
        Complete .tga.ckd binary content ready to write to disk.
    """
    return _CKD_TEXTURE_HEADER + dds_bytes


def convert_texture_lossless(src_ckd_bytes: bytes) -> bytes:
    """Losslessly convert Switch/PC texture CKDs into a PC-compatible texture CKD.

    Handles DDS payloads directly; XTX payloads are deswizzled via xtx_extractor.
    If the file is a raw PNG or JPEG masquerading as a CKD, it will be compiled into DDS.

    Args:
        src_ckd_bytes: Raw bytes of the source .tga.ckd file.

    Returns:
        PC-compatible .tga.ckd binary content.

    Raises:
        TextureEncodingError: If the format is unsupported.
    """
    if src_ckd_bytes.startswith(b'\x89PNG') or src_ckd_bytes.startswith(b'\xff\xd8'):
        return compile_image_bytes_to_tga_ckd(src_ckd_bytes)

    payload, fmt = strip_ckd_header(src_ckd_bytes)

    if fmt == 'dds':
        return wrap_dds_to_tga_ckd(payload)

    if fmt == 'xtx':
        import subprocess
        import tempfile

        xtx_exe = Path(__file__).resolve().parent.parent.parent / "Things" / "JDTools - 1.9.0" / "bin" / "xtx_extract.exe"
        if not xtx_exe.exists():
            raise TextureEncodingError(f"Missing XTX extractor at {xtx_exe}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_xtx = Path(tmp_dir) / "temp.xtx"
            tmp_xtx.write_bytes(payload)

            result = subprocess.run([str(xtx_exe), str(tmp_xtx)], capture_output=True)
            if result.returncode != 0:
                raise TextureEncodingError(f"xtx_extract failed: {result.stderr.decode(errors='replace')}")

            tmp_dds = tmp_xtx.with_suffix(".dds")
            if not tmp_dds.exists():
                raise TextureEncodingError("xtx_extract did not produce a DDS file")
            
            dds_data = tmp_dds.read_bytes()
            return wrap_dds_to_tga_ckd(dds_data)

    raise TextureEncodingError(f"Unsupported texture format encoding: {fmt}")


# ---------------------------------------------------------------------------
# Native DDS Compilation (from PNG/JPEG images)
# ---------------------------------------------------------------------------

def _build_uncompressed_dds(img: Image.Image) -> bytes:
    """Build an uncompressed 32-bit BGRA DDS from a Pillow RGBA image.

    Returns:
        Complete DDS file bytes (128-byte header + pixel data).
    """
    w, h = img.size

    # 128-byte Standard DDS Header
    dds_header = struct.pack(
        "<4sIIIIIII44sIIIIIIIIIIII",
        b"DDS ",             # Magic bytes
        124,                 # Header Size
        0x1 | 0x2 | 0x4 | 0x1000,  # Flags: CAPS, HEIGHT, WIDTH, PIXELFORMAT
        h,                   # Height
        w,                   # Width
        w * 4,               # Pitch (bytes per scanline)
        0,                   # Depth
        1,                   # MipMap count
        b"\x00" * 44,        # Reserved
        32,                  # PixelFormat Size
        0x41,                # PixelFormat Flags (RGBA | ALPHAPIXELS)
        0,                   # FourCC (0 for uncompressed)
        32,                  # RGBBitCount
        0x00FF0000,          # RBitMask (BGRA arrangement)
        0x0000FF00,          # GBitMask
        0x000000FF,          # BBitMask
        0xFF000000,          # ABitMask
        0x1000,              # DDSCAPS_TEXTURE
        0, 0, 0, 0,          # Caps2, Caps3, Caps4, Reserved
    )

    # Convert RGBA to BGRA pixel data
    r, g, b, a = img.split()
    bgra_img = Image.merge("RGBA", (b, g, r, a))
    pixel_data = bgra_img.tobytes()

    return dds_header + pixel_data


def compile_image_to_tga_ckd(
    image_input: Path | Image.Image,
    output_ckd_path: Path,
    target_size: Optional[tuple[int, int]] = None,
) -> None:
    """Compile a PNG/JPEG image natively to uncompressed BGRA 32-bit DDS
    wrapped as a UbiArt PC .tga.ckd texture.

    Completely eliminates TexConv2 and ddsconverter external dependencies.

    Args:
        image_input: Path to source image or a Pillow Image object.
        output_ckd_path: Destination .tga.ckd file path.
        target_size: Optional (width, height) to resize before compilation.
    """
    if isinstance(image_input, Path):
        img = Image.open(image_input).convert("RGBA")
    else:
        img = image_input.convert("RGBA")

    if target_size:
        img = img.resize(target_size, Image.Resampling.LANCZOS)

    dds_bytes = _build_uncompressed_dds(img)

    output_ckd_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_ckd_path, "wb") as f:
        f.write(_CKD_TEXTURE_HEADER)
        f.write(dds_bytes)

    logger.debug("Compiled texture: %s (%dx%d)", output_ckd_path.name, img.width, img.height)


def compile_image_bytes_to_tga_ckd(image_bytes: bytes) -> bytes:
    """Compile raw image bytes (PNG/JPEG) into .tga.ckd content in memory.

    Args:
        image_bytes: Raw image file content.

    Returns:
        Complete .tga.ckd binary content.
    """
    import io
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    dds_bytes = _build_uncompressed_dds(img)
    return _CKD_TEXTURE_HEADER + dds_bytes


# ---------------------------------------------------------------------------
# Banner Background Generator
# ---------------------------------------------------------------------------

def create_banner_background_ckd(
    map_bkg_path: Path,
    output_ckd_path: Path,
) -> None:
    """Generate the map selection banner background and compile it natively.

    Scales background to 2048x1024, applies greyscale conversion,
    and overlays solid blue (#0000FF) in Difference blending mode.

    Based on the Photopea workflow described in guide.md.
    """
    from PIL import ImageChops, ImageOps

    canvas_w, canvas_h = 2048, 1024

    try:
        bg_img = Image.open(map_bkg_path).convert("RGBA")
        
        # Proportional cover resize
        bg_w, bg_h = bg_img.size
        scale = max(canvas_w / bg_w, canvas_h / bg_h)
        new_w, new_h = int(bg_w * scale), int(bg_h * scale)
        bg_img = bg_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Centering crop
        offset_x = (new_w - canvas_w) // 2
        offset_y = (new_h - canvas_h) // 2
        bg_img = bg_img.crop((offset_x, offset_y, offset_x + canvas_w, offset_y + canvas_h))

        # Convert canvas to greyscale
        greyscale = ImageOps.grayscale(bg_img).convert("RGBA")

        # Create difference layer: solid blue #0000FF canvas
        blue_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 255, 255))

        # Mix layers using Difference blending logic
        result = ImageChops.difference(greyscale, blue_layer)
        logger.info("Created banner background: %s", output_ckd_path.name)
    except Exception as e:
        logger.warning("Could not process %s for banner generation (%s). Generating generic blue fallback banner.", map_bkg_path.name, e)
        # Create a generic blue fallback layer
        result = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 255, 255))

    # Compile directly to .tga.ckd
    compile_image_to_tga_ckd(result, output_ckd_path)
