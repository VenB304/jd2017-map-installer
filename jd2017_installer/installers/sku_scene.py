"""SkuScene ISC patcher for JD2017 PC.

Handles unpacking patch_pc.ipk, injecting Actor entries into both
skuscene_maps_pc_all.isc.ckd and skuscene_maps_pc_ww.isc.ckd,
and repacking the patch archive.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

from jd2017_installer.installers.ipk_packer import pack_folder_to_ipk, unpack_ipk_to_folder

logger = logging.getLogger("jd2017.installers.sku_scene")

# Actor XML template for SkuScene injection
_ACTOR_TEMPLATE = """\t\t<ACTORS NAME="Actor">
\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{codename}/songdesc.tpl">
\t\t\t\t<COMPONENTS NAME="JD_SongDescComponent">
\t\t\t\t\t<JD_SongDescComponent />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>
\t\t</ACTORS>"""

# ISC files to patch
_SKU_FILES = [
    "cache/itf_cooked/pc/world/skuscenes/skuscene_maps_pc_all.isc.ckd",
    "cache/itf_cooked/pc/world/skuscenes/skuscene_maps_pc_ww.isc.ckd",
]


def _is_codename_already_registered(isc_content: str, codename: str) -> bool:
    """Check if a codename is already registered in an ISC file."""
    pattern = rf'USERFRIENDLY="{re.escape(codename)}"'
    return bool(re.search(pattern, isc_content, re.IGNORECASE))


def _inject_actor_into_isc(isc_path: Path, codename: str) -> bool:
    """Inject a map Actor entry into a single ISC file.

    Returns True if the injection was performed, False if already present.
    """
    content = isc_path.read_bytes()

    # ISC.CKD files are binary-wrapped XML. The XML content starts after a short header.
    # For JD2017 PC patch_pc, the .isc.ckd files are plain XML (not binary-cooked).
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    if _is_codename_already_registered(text, codename):
        logger.info("Codename '%s' already registered in %s", codename, isc_path.name)
        return False

    actor_block = _ACTOR_TEMPLATE.format(codename=codename)

    # Insert before the <sceneConfigs> block (which sits after the actor
    # entries inside the <Scene> tag in real JD2017 ISC.CKD files).
    insert_marker = "\t\t<sceneConfigs>"
    if insert_marker not in text:
        # Fallback: try without leading tabs
        insert_marker = "<sceneConfigs>"

    if insert_marker not in text:
        raise ValueError(f"Could not find <sceneConfigs> insertion point in {isc_path.name}")

    new_text = text.replace(insert_marker, f"{actor_block}\n{insert_marker}", 1)

    isc_path.write_bytes(new_text.encode("utf-8"))
    logger.info("Injected Actor for '%s' into %s", codename, isc_path.name)
    return True


def list_registered_maps(game_dir: Path) -> list[str]:
    """Stub to satisfy JD2021 UI imports."""
    return []

def unregister_map(*args, **kwargs): pass

def patch_sku_scenes(game_dir: Path | str, codenames: list[str] | str) -> None:
    """Patch the SkuScene files inside patch_pc.ipk to register a new map.

    This:
    1. Unpacks patch_pc.ipk to a temp directory.
    2. Injects Actor entries into both skuscene ISC files.
    3. Repacks patch_pc.ipk.

    Args:
        game_dir: JD2017 PC game root directory.
        codename: Lowercase map codename to register.
    """
    patch_ipk = game_dir / "patch_pc.ipk"
    if not patch_ipk.exists():
        raise FileNotFoundError(f"patch_pc.ipk not found in {game_dir}")

    logger.info("Patching SkuScene files for codename: %s", codename)

    with tempfile.TemporaryDirectory(prefix="jd17_patch_") as tmp:
        tmp_dir = Path(tmp)
        extract_dir = tmp_dir / "extracted"

        # 1. Unpack
        unpack_ipk_to_folder(patch_ipk, extract_dir)

        # 2. Inject into both ISC files
        injected_any = False
        for sku_rel_path in _SKU_FILES:
            isc_path = extract_dir / sku_rel_path
            if isc_path.exists():
                if _inject_actor_into_isc(isc_path, codename):
                    injected_any = True
            else:
                logger.warning("SKU file not found: %s", sku_rel_path)

        if not injected_any:
            logger.info("No new injections needed for '%s'", codename)
            return

        # 3. Backup original and repack
        backup_path = game_dir / "patch_pc.ipk.bak"
        if not backup_path.exists():
            shutil.copy2(patch_ipk, backup_path)
            logger.info("Backed up original patch_pc.ipk")

        pack_folder_to_ipk(extract_dir, patch_ipk)
        logger.info("SkuScene patch complete for '%s'", codename)
