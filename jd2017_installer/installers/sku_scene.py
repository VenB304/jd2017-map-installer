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
_ACTOR_TEMPLATE = """\t\t\t<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="{codename}" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/maps/{name}/songdesc.tpl">
\t\t\t\t<COMPONENTS NAME="JD_SongDescComponent">
\t\t\t\t\t<JD_SongDescComponent />
\t\t\t\t</COMPONENTS>
\t\t\t</Actor>"""

# ISC files to patch
_SKU_FILES = [
    "cache/itf_cooked/pc/world/skuscenes/skuscene_maps_pc_all.isc.ckd",
]


def _is_codename_already_registered(isc_content: str, codename: str) -> bool:
    """Check if a codename is already registered in an ISC file."""
    pattern = rf'USERFRIENDLY="{re.escape(codename)}"'
    return bool(re.search(pattern, isc_content, re.IGNORECASE))


_BLANK_SKUSCENE_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<root>
	<Scene ENGINE_VERSION="253653" GRIDUNIT="0.500000" DEPTH_SEPARATOR="0" NEAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" FAR_SEPARATOR="1.000000 0.000000 0.000000 0.000000, 0.000000 1.000000 0.000000 0.000000, 0.000000 0.000000 1.000000 0.000000, 0.000000 0.000000 0.000000 1.000000" viewFamily="0">
		<ACTORS NAME="Actor">
			<Actor RELATIVEZ="0.000000" SCALE="1.000000 1.000000" xFLIPPED="0" USERFRIENDLY="skuscene_db" MARKER="" POS2D="0.000000 0.000000" ANGLE="0.000000" INSTANCEDATAFILE="" LUA="world/skuscenes/skuscene_base.tpl">
				<COMPONENTS NAME="JD_SongDatabaseComponent">
					<JD_SongDatabaseComponent />
				</COMPONENTS>
			</Actor>
		</ACTORS>
		<sceneConfigs>
			<SceneConfigs activeSceneConfig="0">
				<sceneConfigs NAME="JD_SongDatabaseSceneConfig">
					<JD_SongDatabaseSceneConfig name="" SKU="{sku}" Territory="NCSA" RatingUI="world/ui/screens/bootsequence/rating">
						<ENUM NAME="Pause_Level" SEL="6" />
					</JD_SongDatabaseSceneConfig>
				</sceneConfigs>
			</SceneConfigs>
		</sceneConfigs>
	</Scene>
</root>
"""

def _inject_actor_into_isc(isc_path: Path, codename: str) -> bool:
    """Inject a map Actor entry into a single ISC file.

    Returns True if the injection was performed, False if already present.
    """
    content = isc_path.read_bytes()

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
        
    if "<?xml" not in text:
        logger.info(f"File {isc_path.name} appears to be binary. Replacing with blank XML SkuScene.")
        sku = "jd2017-pc-all" if "all" in isc_path.name.lower() else "jd2017-pc-ww"
        text = _BLANK_SKUSCENE_XML.format(sku=sku)
        isc_path.write_bytes(text.encode("utf-8"))

    if _is_codename_already_registered(text, codename):
        logger.info("Codename '%s' already registered in %s", codename, isc_path.name)
        return False

    actor_block = _ACTOR_TEMPLATE.format(codename=codename, name=codename.lower())

    # Insert before the </ACTORS> closing tag
    insert_marker = "\t\t</ACTORS>"
    if insert_marker not in text:
        # Fallback: try without leading tabs
        insert_marker = "</ACTORS>"

    if insert_marker not in text:
        raise ValueError(f"Could not find </ACTORS> insertion point in {isc_path.name}")

    new_text = text.replace(insert_marker, f"{actor_block}\n{insert_marker}", 1)

    isc_path.write_bytes(new_text.encode("utf-8"))
    logger.info("Injected Actor for '%s' into %s", codename, isc_path.name)
    return True


def list_registered_maps(game_dir: Path) -> list[str]:
    """Return map codenames currently registered in patch_pc.ipk SkuScene ISC."""
    patch_ipk = game_dir / "patch_pc.ipk"
    if not patch_ipk.exists():
        return []
        
    with tempfile.TemporaryDirectory(prefix="jd17_list_") as tmp:
        tmp_dir = Path(tmp)
        try:
            unpack_ipk_to_folder(patch_ipk, tmp_dir, filter_paths=[_SKU_FILES[0]])
            isc_path = tmp_dir / _SKU_FILES[0]
            if not isc_path.exists():
                return []
                
            try:
                text = isc_path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                text = isc_path.read_bytes().decode("latin-1")
                
            # Find all USERFRIENDLY="..."
            matches = re.findall(r'USERFRIENDLY="([^"]+)"', text, re.IGNORECASE)
            
            # Deduplicate preserving order, and ignore built-in skuscene elements
            seen = set()
            result = []
            for m in matches:
                m_low = m.lower()
                if m_low in ("skuscene_db", "skuscene_map"):
                    continue
                if m_low not in seen:
                    seen.add(m_low)
                    result.append(m)
            return result
        except Exception as e:
            logger.error("Failed to list maps from patch_pc.ipk: %s", e)
            return []

def is_registered(game_dir: Path, codename: str) -> bool:
    """Check if a specific map is registered in patch_pc.ipk."""
    registered = [m.lower() for m in list_registered_maps(game_dir)]
    return codename.lower() in registered

def unregister_map(game_dir: Path, codename: str) -> None:
    """Remove a map's Actor entry from patch_pc.ipk SkuScene files."""
    if codename.lower() in ("skuscene_db", "skuscene_map"):
        logger.warning("Attempted to unregister reserved SkuScene actor: %s", codename)
        return

    patch_ipk = game_dir / "patch_pc.ipk"
    if not patch_ipk.exists():
        return

    logger.info("Unregistering map '%s' from SkuScenes", codename)

    with tempfile.TemporaryDirectory(prefix="jd17_unpatch_") as tmp:
        tmp_dir = Path(tmp)
        extract_dir = tmp_dir / "extracted"

        # 1. Unpack completely
        unpack_ipk_to_folder(patch_ipk, extract_dir)

        # 2. Remove Actor from both ISC files
        unregistered_any = False
        for sku_rel_path in _SKU_FILES:
            isc_path = extract_dir / sku_rel_path
            if isc_path.exists():
                try:
                    text = isc_path.read_bytes().decode("utf-8")
                except UnicodeDecodeError:
                    text = isc_path.read_bytes().decode("latin-1")
                    
                # Regex to match the exact actor block for this codename
                pattern = re.compile(
                    rf'\t*\<Actor[^>]*USERFRIENDLY="{re.escape(codename)}".*?\</Actor\>\r?\n?',
                    re.DOTALL | re.IGNORECASE
                )
                new_text, count = pattern.subn("", text)
                
                if count > 0:
                    isc_path.write_bytes(new_text.encode("utf-8"))
                    logger.info("Removed Actor '%s' from %s", codename, isc_path.name)
                    unregistered_any = True

        if not unregistered_any:
            logger.info("Map '%s' not found in SkuScenes", codename)
            return

        # 3. Backup and repack
        backup_path = game_dir / "patch_pc.ipk.bak"
        if not backup_path.exists():
            shutil.copy2(patch_ipk, backup_path)
            
        pack_folder_to_ipk(extract_dir, patch_ipk)
        logger.info("SkuScene unpatch complete for '%s'", codename)

def patch_sku_scenes(game_dir: Path | str, codenames: list[str] | str) -> None:
    """Patch the SkuScene files inside patch_pc.ipk to register new maps.

    This:
    1. Unpacks patch_pc.ipk to a temp directory.
    2. Injects Actor entries into both skuscene ISC files.
    3. Repacks patch_pc.ipk.

    Args:
        game_dir: JD2017 PC game root directory.
        codenames: Lowercase map codename(s) to register.
    """
    if isinstance(game_dir, str):
        game_dir = Path(game_dir)
        
    patch_ipk = game_dir / "patch_pc.ipk"
    if not patch_ipk.exists():
        raise FileNotFoundError(f"patch_pc.ipk not found in {game_dir}")

    if isinstance(codenames, str):
        codenames = [codenames]

    logger.info("Patching SkuScene files for codenames: %s", codenames)

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
                for codename in codenames:
                    if _inject_actor_into_isc(isc_path, codename):
                        injected_any = True
            else:
                logger.warning("SKU file not found: %s", sku_rel_path)

        if not injected_any:
            logger.info("No new injections needed for '%s'", codenames)
            return

        # 3. Backup original and repack
        backup_path = game_dir / "patch_pc.ipk.bak"
        if not backup_path.exists():
            shutil.copy2(patch_ipk, backup_path)
            logger.info("Backed up original patch_pc.ipk")

        pack_folder_to_ipk(extract_dir, patch_ipk)
        logger.info("SkuScene patch complete for '%s'", codenames)
