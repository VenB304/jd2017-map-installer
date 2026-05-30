"""Logic to generate patch_pc.ipk from scratch if missing."""

import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QMessageBox

from jd2017_installer.installers.ipk_packer import unpack_ipk_to_folder, pack_folder_to_ipk

logger = logging.getLogger("jd2017.installers.patch_pc_builder")

_SKU_FILES = [
    "cache/itf_cooked/pc/world/skuscenes/skuscene_maps_pc_all.isc.ckd",
    "cache/itf_cooked/pc/world/skuscenes/skuscene_maps_pc_ww.isc.ckd",
]

def check_and_create_patch_pc(parent_widget, game_dir: Path) -> None:
    if not game_dir or not game_dir.is_dir():
        return
        
    patch_ipk = game_dir / "patch_pc.ipk"
    if patch_ipk.exists():
        return

    # Find bundle_x_pc.ipk (x >= 0)
    bundle_files = []
    for f in game_dir.iterdir():
        if f.is_file() and re.match(r"^bundle_\d+_pc\.ipk$", f.name.lower()):
            bundle_files.append(f)

    if not bundle_files:
        # No mod bundles exist, but patch_pc is missing. Just create a blank one from bundle_pc.ipk
        _create_patch_pc_from_base(game_dir, patch_ipk)
        return

    reply = QMessageBox.question(
        parent_widget,
        "patch_pc.ipk Not Detected",
        f"No patch_pc.ipk was detected, but {len(bundle_files)} existing bundle(s) were found.\n\n"
        "Do you want to DELETE these bundle files and generate a fresh patch_pc.ipk? "
        "(patch_pc.ipk will determine what maps are shown in-game.)",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )

    if reply == QMessageBox.StandardButton.Yes:
        for b in bundle_files:
            try:
                b.unlink()
            except Exception as e:
                logger.error("Failed to delete %s: %s", b.name, e)
        _create_patch_pc_from_base(game_dir, patch_ipk)
        QMessageBox.information(parent_widget, "Success", "Deleted bundle files and created fresh patch_pc.ipk.")
    else:
        reply2 = QMessageBox.question(
            parent_widget,
            "Merge Bundle Maps?",
            "You chose not to delete the bundle files.\n\n"
            "Do you want to extract their registered maps and add them to the new patch_pc.ipk's SkuScene (skuscene_maps_pc_all.isc)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply2 == QMessageBox.StandardButton.Yes:
            _create_patch_pc_with_merge(game_dir, patch_ipk, bundle_files)
            QMessageBox.information(parent_widget, "Success", "Created patch_pc.ipk and merged all bundle maps.")
        else:
            _create_patch_pc_from_base(game_dir, patch_ipk)
            QMessageBox.information(parent_widget, "Success", "Created a fresh patch_pc.ipk without merging bundle maps.")

def _create_patch_pc_from_base(game_dir: Path, patch_ipk: Path) -> None:
    bundle_pc = game_dir / "bundle_pc.ipk"
    if not bundle_pc.exists():
        logger.warning("bundle_pc.ipk not found! Cannot create base patch_pc.ipk.")
        return
        
    with tempfile.TemporaryDirectory(prefix="jd17_patch_init_") as tmp:
        tmp_dir = Path(tmp)
        unpack_ipk_to_folder(bundle_pc, tmp_dir, filter_paths=_SKU_FILES)
        
        # Verify something was extracted
        has_skus = False
        for sku in _SKU_FILES:
            if (tmp_dir / sku).exists():
                has_skus = True
                
        if has_skus:
            pack_folder_to_ipk(tmp_dir, patch_ipk)
            logger.info("Successfully initialized new patch_pc.ipk")
        else:
            logger.error("Failed to extract any SkuScene from bundle_pc.ipk")

def _create_patch_pc_with_merge(game_dir: Path, patch_ipk: Path, bundle_files: list[Path]) -> None:
    bundle_pc = game_dir / "bundle_pc.ipk"
    if not bundle_pc.exists():
        logger.warning("bundle_pc.ipk not found! Cannot create base patch_pc.ipk.")
        return

    with tempfile.TemporaryDirectory(prefix="jd17_patch_merge_") as tmp:
        tmp_dir = Path(tmp)
        unpack_ipk_to_folder(bundle_pc, tmp_dir, filter_paths=_SKU_FILES)
        
        # Now extract SkuScenes from all bundle files into a separate location to parse
        bundles_dir = tmp_dir / "_bundles"
        for b in bundle_files:
            unpack_ipk_to_folder(b, bundles_dir, filter_paths=_SKU_FILES)
            
        # Merge logic
        for sku_rel_path in _SKU_FILES:
            base_sku = tmp_dir / sku_rel_path
            bundle_sku = bundles_dir / sku_rel_path
            
            if base_sku.exists() and bundle_sku.exists():
                _merge_actors(base_sku, bundle_sku)
            elif bundle_sku.exists():
                # If base doesn't have it but bundle does, just copy it
                base_sku.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(bundle_sku, base_sku)

        # Remove the bundles staging dir before packing
        import shutil
        shutil.rmtree(bundles_dir, ignore_errors=True)
        
        pack_folder_to_ipk(tmp_dir, patch_ipk)
        logger.info("Successfully created patch_pc.ipk with merged maps.")

def _merge_actors(base_sku: Path, bundle_sku: Path) -> None:
    try:
        base_text = base_sku.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        base_text = base_sku.read_bytes().decode("latin-1")
        
    try:
        bundle_text = bundle_sku.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        bundle_text = bundle_sku.read_bytes().decode("latin-1")

    # Extract all actors from bundle_text
    # We look for <ACTORS NAME="Actor"> ... </ACTORS>
    actor_pattern = re.compile(r'<ACTORS NAME="Actor">.*?</ACTORS>', re.DOTALL | re.IGNORECASE)
    bundle_actors = actor_pattern.findall(bundle_text)
    
    # Filter out actors that are already in base_text (by checking USERFRIENDLY="")
    new_actors = []
    for actor in bundle_actors:
        # Find codename in actor
        match = re.search(r'USERFRIENDLY="([^"]+)"', actor)
        if match:
            codename = match.group(1)
            # Check if codename is in base_text
            if not re.search(rf'USERFRIENDLY="{re.escape(codename)}"', base_text, re.IGNORECASE):
                new_actors.append(actor)
                
    if not new_actors:
        return

    # Inject new actors into base_text before <sceneConfigs>
    insert_marker = "\t\t<sceneConfigs>"
    if insert_marker not in base_text:
        insert_marker = "<sceneConfigs>"
        
    if insert_marker not in base_text:
        logger.warning("Could not find <sceneConfigs> in base SkuScene for merging.")
        return
        
    actors_str = "\n".join(new_actors)
    new_base_text = base_text.replace(insert_marker, f"{actors_str}\n{insert_marker}", 1)
    base_sku.write_bytes(new_base_text.encode("utf-8"))
