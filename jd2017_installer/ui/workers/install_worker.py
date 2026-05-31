"""Installation worker thread for orchestrating the map install pipeline."""

from __future__ import annotations

import logging
import time
import traceback
import os
import shutil
import json
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

from jd2017_installer.core.config import AppConfig
from jd2017_installer.core.exceptions import JDInstallerError
from jd2017_installer.core.path_discovery import next_bundle_index
from jd2017_installer.extractors.base import BaseExtractor, ExtractionProgress
from jd2017_installer.installers.game_writer import generate_all_scenes
from jd2017_installer.installers.ipk_packer import pack_folder_to_ipk
from jd2017_installer.installers.secure_fat_maker import generate_secure_fat
from jd2017_installer.installers.sku_scene import patch_sku_scenes
from jd2017_installer.parsers.normalizer import load_and_normalize_songdesc_file

logger = logging.getLogger("jd2017.ui.workers.install_worker")


class InstallWorkerSignals(QObject):
    """Signals emitted by the InstallWorker."""
    progress = pyqtSignal(str, int, int, str)  # phase, current, total, detail
    log = pyqtSignal(int, str)  # level, message
    finished = pyqtSignal(bool, str)  # success, message/error
    codename_inferred = pyqtSignal(str)


class InstallWorker(QObject):
    """Background worker that orchestrates the entire map installation pipeline.

    Phases:
    1. Extraction (download/unpack)
    2. Normalization & Transcoding (audio/video/textures)
    3. Scene Generation (CKD packing)
    4. IPK Packing (bundle creation)
    5. Global Registration (SkuScene patch + FAT rebuild)
    """

    def __init__(
        self,
        extractor: BaseExtractor,
        config: AppConfig,
        project_root: Path,
    ) -> None:
        super().__init__()
        self.extractor = extractor
        self.config = config
        self.project_root = project_root
        self.signals = InstallWorkerSignals()

        # Wire extractor progress to our signals
        self.extractor.progress_cb = self._on_extractor_progress

    def _on_extractor_progress(self, progress: ExtractionProgress) -> None:
        self.signals.progress.emit(progress.phase, progress.current, progress.total, progress.detail)

    def _log(self, level: int, message: str) -> None:
        self.signals.log.emit(level, message)

    @pyqtSlot()
    def run(self) -> None:
        """Execute the installation pipeline."""
        start_time = time.time()
        success = False
        message = ""
        
        # Temp directories
        temp_dir = self.project_root / self.config.temp_directory
        extract_dir = temp_dir / "extracted"
        build_dir = temp_dir / "build"
        
        # Clear temp directories from previous installs
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        if build_dir.exists():
            shutil.rmtree(build_dir)
            
        extract_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if not self.config.game_directory:
                raise ValueError("Game directory is not configured.")
            game_dir = Path(self.config.game_directory)

            self._log(logging.INFO, "Starting installation pipeline...")
            
            # Phase 1: Extraction
            self._log(logging.INFO, "[Phase 1] Extracting map data...")
            extracted_path = self.extractor.extract(extract_dir)
            codename = self.extractor.get_codename()
            
            if not codename:
                raise ValueError("Could not infer map codename from extraction.")
            
            self.signals.codename_inferred.emit(codename)
            self._log(logging.INFO, f"Map codename identified as: {codename}")

            # Phase 2: Normalization (simplified for now, assumes extraction gave us what we need)
            # In a full implementation, we'd transcode media here using media_processor.
            self._log(logging.INFO, "[Phase 2] Normalizing assets and metadata...")
            self.signals.progress.emit("normalization", 0, 1, "Transcoding media (stub)")
            
            # Phase 3: Scene Generation
            self._log(logging.INFO, "[Phase 3] Generating PC scenes and CKD files...")
            self.signals.progress.emit("scene_generation", 0, 1, "Writing CKD files")
            
            # Read normalized data to get num_coach
            from jd2017_installer.parsers.normalizer import load_and_normalize_songdesc_file
            
            # Find the songdesc.tpl.ckd in extracted dir
            extracted_world = extracted_path / "cache" / "itf_cooked" / "pc" / "world" / "maps" / codename.lower()
            if not extracted_world.exists():
                matches = list(extracted_path.rglob("songdesc.tpl.ckd"))
                if matches:
                    extracted_world = matches[0].parent
                else:
                    raise ValueError("Could not find extracted map data (songdesc.tpl.ckd).")
                    
            songdesc_path = extracted_world / "songdesc.tpl.ckd"
            if songdesc_path.exists():
                norm_data = load_and_normalize_songdesc_file(songdesc_path, codename)
                num_coach = norm_data.get("num_coach", 1)
                
                self._log(logging.INFO, "Patching songdesc.tpl.ckd...")
                sd_content = songdesc_path.read_bytes()
                sd_text = sd_content.lstrip(b"\x00\xef\xbb\xbf").decode("utf-8", errors="replace").strip('\x00\r\n\t ')
                sd_json = json.loads(sd_text)
            else:
                self._log(logging.INFO, "songdesc.tpl.ckd not found. Synthesizing from jdlo_metadata.json...")
                jdlo_meta_path = extracted_path / "jdlo_metadata.json"
                if not jdlo_meta_path.exists():
                    raise ValueError(f"Missing songdesc.tpl.ckd and no fallback metadata found in {extracted_path}")
                jdlo_meta = json.loads(jdlo_meta_path.read_text(encoding="utf-8"))
                num_coach = jdlo_meta.get("coachCount", 1)
                
                sd_json = {
                    "__class": "Actor_Template",
                    "WIP": 0,
                    "LOWPATH": "",
                    "COMPONENTS": [{
                        "__class": "JD_SongDescTemplate",
                        "MapName": jdlo_meta.get("mapName", codename),
                        "JDVersion": 2017,
                        "OriginalJDVersion": jdlo_meta.get("originalJDVersion", 2021),
                        "Title": jdlo_meta.get("title", "Unknown"),
                        "Artist": jdlo_meta.get("artist", "Unknown"),
                        "NumCoach": num_coach,
                        "Difficulty": jdlo_meta.get("difficulty", 1),
                        "SweatDifficulty": jdlo_meta.get("sweatDifficulty", 1),
                        "Status": jdlo_meta.get("status", 3),
                        "DefaultColors": jdlo_meta.get("songColors", {})
                    }]
                }
            
            paths = generate_all_scenes(build_dir, codename, num_coach=num_coach)
            
            # Extract original version before patching
            original_jd_version = 2017  # fallback
            if songdesc_path.exists():
                # Read from existing songdesc
                components = sd_json.get("COMPONENTS", [{}])
                for comp in components:
                    if isinstance(comp, dict):
                        v = comp.get("OriginalJDVersion") or comp.get("JDVersion")
                        if v and int(v) != 0:
                            original_jd_version = int(v)
                            break
            elif jdlo_meta_path.exists():
                original_jd_version = jdlo_meta.get("originalJDVersion", 2021)

            def patch_song_desc_versions(obj, original_jd_version: int):
                if isinstance(obj, dict):
                    if "JDVersion" in obj:
                        obj["OriginalJDVersion"] = original_jd_version
                        obj["JDVersion"] = 2017
                    for v in obj.values():
                        patch_song_desc_versions(v, original_jd_version)
                elif isinstance(obj, list):
                    for item in obj:
                        patch_song_desc_versions(item, original_jd_version)
            
            patch_song_desc_versions(sd_json, original_jd_version)
            build_songdesc = paths["cache_root"] / "songdesc.tpl.ckd"
            build_songdesc.parent.mkdir(parents=True, exist_ok=True)
            build_songdesc.write_text(json.dumps(sd_json, ensure_ascii=True), encoding="utf-8")
            
            # 2. Copy timeline and autodance from extracted based STRICTLY on guide.md
            self._log(logging.INFO, "Copying timeline and autodance based on guide.md...")
            
            # Guide Line 44: merge the unpacked main scene's world/maps/[codename] autodance and timeline folders
            src_uncooked_world = extracted_path / "world" / "maps" / codename.lower()
            dst_uncooked_world = paths["world_root"]
            if (src_uncooked_world / "timeline").exists():
                shutil.copytree(src_uncooked_world / "timeline", dst_uncooked_world / "timeline", dirs_exist_ok=True)
            if (src_uncooked_world / "autodance").exists():
                shutil.copytree(src_uncooked_world / "autodance", dst_uncooked_world / "autodance", dirs_exist_ok=True)
            
            # Guide Line 65: copy pictos folder, dtape.ckd, ktape.ckd from cache/.../timeline/
            src_timeline = extracted_world / "timeline"
            dst_timeline = paths["cache_timeline"]
            
            if (src_timeline / "pictos").exists():
                shutil.copytree(src_timeline / "pictos", dst_timeline / "pictos", dirs_exist_ok=True)
                
            dtape_src = src_timeline / f"{codename.lower()}_tml_dance.dtape.ckd"
            if dtape_src.exists():
                shutil.copy2(dtape_src, dst_timeline / f"{codename.lower()}_tml_dance.dtape.ckd")
            else:
                # Handle alternative naming
                dtape_src_dot = src_timeline / f"{codename.lower()}_tml.dance.dtape.ckd"
                if dtape_src_dot.exists():
                    shutil.copy2(dtape_src_dot, dst_timeline / f"{codename.lower()}_tml_dance.dtape.ckd")
                    
            ktape_src = src_timeline / f"{codename.lower()}_tml_karaoke.ktape.ckd"
            if ktape_src.exists():
                shutil.copy2(ktape_src, dst_timeline / f"{codename.lower()}_tml_karaoke.ktape.ckd")
            else:
                ktape_src_dot = src_timeline / f"{codename.lower()}_tml.karaoke.ktape.ckd"
                if ktape_src_dot.exists():
                    shutil.copy2(ktape_src_dot, dst_timeline / f"{codename.lower()}_tml_karaoke.ktape.ckd")
                
            self._log(logging.INFO, "Normalizing textures (lossless CKD conversion)...")
            from jd2017_installer.installers.texture_encoder import convert_texture_lossless, TextureEncodingError
            
            # 5. Convert any textures from Orbis/Switch to PC
            for root, _, files in os.walk(str(build_dir)):
                for f in files:
                    # Rename .png.ckd to .tga.ckd first
                    file_path = Path(root) / f
                    if f.endswith(".png.ckd"):
                        new_name = f.replace(".png.ckd", ".tga.ckd")
                        new_path = Path(root) / new_name
                        file_path.replace(new_path)
                        file_path = new_path
                        f = new_name

                    # Convert .tga.ckd
                    if f.endswith(".tga.ckd"):
                        try:
                            data = file_path.read_bytes()
                            # Check if it needs conversion (i.e. not already standard DDS)
                            if len(data) > 44 and b"DDS " not in data[44:48]:
                                new_data = convert_texture_lossless(data)
                                file_path.write_bytes(new_data)
                        except TextureEncodingError as e:
                            self._log(logging.WARNING, f"Failed to convert texture {file_path.name}: {e}")
                        
            menuart_dir = paths["cache_menuart_textures"]
            for ext_file in extracted_path.glob("*.tga.ckd"):
                try:
                    raw = ext_file.read_bytes()
                    converted = convert_texture_lossless(raw)
                    # Keep single 'b' for expand background as per guide.md
                    target_name = ext_file.name
                    (menuart_dir / target_name).write_bytes(converted)
                except Exception as e:
                    self._log(logging.WARNING, f"Failed to convert menuart {ext_file.name}: {e}")
                    
            # Uncooked phone assets belong in world/maps/[codename]/menuart/textures/ as per guide.md (Lines 50-60)
            world_menuart_dir = paths["world_menuart_textures"]
            for ext_img in extracted_path.glob("*_phone.*"):
                if ext_img.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    try:
                        shutil.copy2(ext_img, world_menuart_dir / ext_img.name)
                        self._log(logging.INFO, f"Copied phone image {ext_img.name} to uncooked menuart textures")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to copy phone image {ext_img.name}: {e}")
                        
            # Phase 1 Fallback: banner_bkg generation
            banner_dst = menuart_dir / f"{codename.lower()}_banner_bkg.tga.ckd"
            if not banner_dst.exists():
                map_bkg_src = self.extractor.media_context.map_bkg_path if hasattr(self, "extractor") and hasattr(self.extractor, "media_context") else None
                if not map_bkg_src or not map_bkg_src.exists():
                    for ext in (".png", ".tga", ".jpg"):
                        candidate = menuart_dir / f"{codename.lower()}_map_bkg{ext}"
                        if candidate.exists():
                            map_bkg_src = candidate
                            break
                if map_bkg_src and map_bkg_src.exists():
                    try:
                        from jd2017_installer.installers.texture_encoder import create_banner_background_ckd
                        create_banner_background_ckd(map_bkg_src, banner_dst)
                        self._log(logging.INFO, f"Generated banner_bkg from map_bkg for '{codename}'")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to generate banner_bkg for '{codename}': {e}")
                
            # 3. Modify dtape `.png` to `.tga`
            dtape_candidates = list(dst_timeline.glob("*.dtape.ckd"))
            for dtape_file in dtape_candidates:
                if "dance" in dtape_file.name.lower():
                    try:
                        dtape_text = dtape_file.read_text(encoding="utf-8", errors="replace")
                        if ".png" in dtape_text:
                            dtape_text = dtape_text.replace(".png", ".tga")
                            dtape_file.write_text(dtape_text, encoding="utf-8")
                            self._log(logging.INFO, f"Patched picto paths in {dtape_file.name}")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to patch dtape '{dtape_file.name}': {e}")
                
            # 4. Modify musictrack `.wav` to `.ogg`
            src_musictrack = extracted_world / "audio" / f"{codename.lower()}_musictrack.tpl.ckd"
            dst_musictrack = paths["cache_audio"] / f"{codename.lower()}_musictrack.tpl.ckd"
            if src_musictrack.exists():
                mt_text = src_musictrack.read_text(encoding="utf-8", errors="replace")
                mt_text = mt_text.replace(".wav", ".ogg")
                dst_musictrack.parent.mkdir(parents=True, exist_ok=True)
                dst_musictrack.write_text(mt_text, encoding="utf-8")
            else:
                self._log(logging.WARNING, f"musictrack.tpl.ckd not found for '{codename}', audio sequencing may be incomplete")
                
            # 5. Copy media assets to world directories
            self._log(logging.INFO, "Copying media assets (audio/video)...")
            audio_dst = paths["world_audio"] / f"{codename.lower()}.ogg"
            video_dst = paths["world_videoscoach"] / f"{codename.lower()}.vp8"
            
            ogg_candidates = list(extracted_path.glob("*.ogg"))
            if ogg_candidates:
                shutil.copy2(ogg_candidates[0], audio_dst)
            else:
                self._log(logging.WARNING, f"No .ogg audio file found in {extracted_path.name}")
                
            webm_candidates = list(extracted_path.glob("*.webm"))
            if webm_candidates:
                shutil.copy2(webm_candidates[0], video_dst)
            else:
                self._log(logging.WARNING, f"No .webm video file found in {extracted_path.name}")
            
            # Phase 4: IPK Packing
            self._log(logging.INFO, "[Phase 4] Packing bundle IPK...")
            existing_bundles = list(game_dir.glob("bundle_*_pc.ipk"))
            max_num = 0
            for b in existing_bundles:
                try:
                    num = int(b.name.split("_")[1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    pass
            next_num = max_num + 1
            bundle_name = f"bundle_{next_num:02d}_pc.ipk"
            bundle_path = game_dir / bundle_name
            
            self.signals.progress.emit("ipk_packing", 0, 1, f"Building {bundle_name}")
            pack_folder_to_ipk(build_dir, bundle_path)
            self._log(logging.INFO, f"Packed map data to {bundle_path.name}")
            
            # Phase 5: Global Registration
            self._log(logging.INFO, "[Phase 5] Registering map globally...")
            
            self.signals.progress.emit("registration", 0, 2, "Patching SkuScenes")
            patch_sku_scenes(game_dir, codename)
            
            # JD2017 always requires rebuilding secure_fat.gf after map modifications
            self.signals.progress.emit("registration", 1, 2, "Rebuilding secure_fat.gf")
            generate_secure_fat(game_dir)
            
            self.signals.progress.emit("completed", 1, 1, "Done")
            duration = time.time() - start_time
            message = f"Successfully installed '{codename}' in {duration:.1f}s"
            self._log(logging.INFO, message)
            success = True

        except JDInstallerError as e:
            message = f"Installation failed: {e}"
            self._log(logging.ERROR, message)
        except Exception as e:
            trace = traceback.format_exc()
            message = f"Unexpected error during installation:\n{trace}"
            self._log(logging.ERROR, message)
        finally:
            self.signals.finished.emit(success, message)
