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
        
        # Ensure both SkuScenes exist
        from jd2017_installer.installers.sku_scene import _BLANK_SKUSCENE_XML
        for sku_rel_path in _SKU_FILES:
            base_sku = tmp_dir / sku_rel_path
            if not base_sku.exists():
                base_sku.parent.mkdir(parents=True, exist_ok=True)
                sku = "jd2017-pc-ww"
                base_sku.write_bytes(_BLANK_SKUSCENE_XML.format(sku=sku).encode("utf-8"))
            else:
                try:
                    text = base_sku.read_bytes().decode("utf-8")
                except UnicodeDecodeError:
                    text = base_sku.read_bytes().decode("latin-1")
                if 'SKU="jd2017-pc-all"' in text:
                    text = text.replace('SKU="jd2017-pc-all"', 'SKU="jd2017-pc-ww"')
                    base_sku.write_bytes(text.encode("utf-8"))
                
        pack_folder_to_ipk(tmp_dir, patch_ipk)
        logger.info("Successfully initialized new patch_pc.ipk")

def _create_patch_pc_with_merge(game_dir: Path, patch_ipk: Path, bundle_files: list[Path]) -> None:
    bundle_pc = game_dir / "bundle_pc.ipk"
    if not bundle_pc.exists():
        logger.warning("bundle_pc.ipk not found! Cannot create base patch_pc.ipk.")
        return

    with tempfile.TemporaryDirectory(prefix="jd17_patch_merge_") as tmp:
        tmp_dir = Path(tmp)
        unpack_ipk_to_folder(bundle_pc, tmp_dir, filter_paths=_SKU_FILES)
        
        # We don't need to verify something was extracted because we'll create blanks if missing

        from jd2017_installer.extractors.archive_ipk import inspect_ipk
        from jd2017_installer.installers.sku_scene import _inject_actor_into_isc
        
        # Find all codenames from all bundle files
        all_codenames = set()
        for b in bundle_files:
            try:
                codenames = inspect_ipk(b)
                for c in codenames:
                    all_codenames.add(c)
            except Exception as e:
                logger.warning(f"Failed to inspect bundle {b.name}: {e}")
                
        # Inject each codename into the extracted SkuScenes
        from jd2017_installer.installers.sku_scene import _BLANK_SKUSCENE_XML
        for sku_rel_path in _SKU_FILES:
            base_sku = tmp_dir / sku_rel_path
            if not base_sku.exists():
                base_sku.parent.mkdir(parents=True, exist_ok=True)
                sku = "jd2017-pc-ww"
                base_sku.write_bytes(_BLANK_SKUSCENE_XML.format(sku=sku).encode("utf-8"))
            else:
                try:
                    text = base_sku.read_bytes().decode("utf-8")
                except UnicodeDecodeError:
                    text = base_sku.read_bytes().decode("latin-1")
                if 'SKU="jd2017-pc-all"' in text:
                    text = text.replace('SKU="jd2017-pc-all"', 'SKU="jd2017-pc-ww"')
                    base_sku.write_bytes(text.encode("utf-8"))
            
            for codename in all_codenames:
                _inject_actor_into_isc(base_sku, codename)
        
        pack_folder_to_ipk(tmp_dir, patch_ipk)
        logger.info(f"Successfully created patch_pc.ipk with {len(all_codenames)} merged maps.")
