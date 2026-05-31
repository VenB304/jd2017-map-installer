"""Installation worker thread for orchestrating the map install pipeline."""

from __future__ import annotations

import logging
import time
import traceback
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
        logger.log(level, message)
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
            import shutil
            import json
            
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
                sd_text = sd_content.lstrip(b"\x00\xef\xbb\xbf").decode("utf-8", errors="replace")
                sd_json = json.loads(sd_text)
            else:
                self._log(logging.INFO, "songdesc.tpl.ckd not found. Synthesizing from jdlo_metadata.json...")
                jdlo_meta_path = extracted_path / "jdlo_metadata.json"
                if not jdlo_meta_path.exists():
                    raise ValueError(f"Missing songdesc.tpl.ckd and no fallback metadata found in {extracted_path}")
                jdlo_meta = json.loads(jdlo_meta_path.read_text(encoding="utf-8"))
                num_coach = jdlo_meta.get("coachCount", 1)
                
                sd_json = {
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
                }
            
            paths = generate_all_scenes(build_dir, codename, num_coach=num_coach)
            
            # 1. Copy songdesc.tpl.ckd and modify JDVersion
            def set_jd_version(obj):
                if isinstance(obj, dict):
                    if "JDVersion" in obj:
                        obj["OriginalJDVersion"] = obj["JDVersion"]
                        obj["JDVersion"] = 2017
                    for v in obj.values():
                        set_jd_version(v)
                elif isinstance(obj, list):
                    for item in obj:
                        set_jd_version(item)
            
            set_jd_version(sd_json)
            build_songdesc = paths["cache_root"] / "songdesc.tpl.ckd"
            build_songdesc.parent.mkdir(parents=True, exist_ok=True)
            build_songdesc.write_text(json.dumps(sd_json, ensure_ascii=True), encoding="utf-8")
            
            # 2. Copy timeline and autodance from extracted
            self._log(logging.INFO, "Copying timeline and autodance logic...")
            src_timeline = extracted_world / "timeline"
            src_autodance = extracted_world / "autodance"
            dst_timeline = paths["cache_timeline"]
            dst_autodance = paths["cache_autodance"]
            
            if src_timeline.exists():
                shutil.copytree(src_timeline, dst_timeline, dirs_exist_ok=True)
            if src_autodance.exists():
                shutil.copytree(src_autodance, dst_autodance, dirs_exist_ok=True)
                
            self._log(logging.INFO, "Normalizing textures (lossless CKD conversion)...")
            from jd2017_installer.installers.texture_encoder import convert_texture_lossless
            
            pictos_dir = dst_timeline / "pictos"
            if pictos_dir.exists():
                for picto_file in pictos_dir.glob("*.tga.ckd"):
                    try:
                        raw = picto_file.read_bytes()
                        converted = convert_texture_lossless(raw)
                        picto_file.write_bytes(converted)
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to convert picto {picto_file.name}: {e}")
                        
            menuart_dir = paths["cache_menuart_textures"]
            for ext_file in extracted_path.glob("*.tga.ckd"):
                try:
                    raw = ext_file.read_bytes()
                    converted = convert_texture_lossless(raw)
                    (menuart_dir / ext_file.name).write_bytes(converted)
                except Exception as e:
                    self._log(logging.WARNING, f"Failed to convert menuart {ext_file.name}: {e}")
                    
            for ext_img in extracted_path.glob("*_phone.*"):
                if ext_img.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    try:
                        shutil.copy2(ext_img, menuart_dir / ext_img.name)
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to copy phone image {ext_img.name}: {e}")
                
            # 3. Modify dtape `.png` to `.tga`
            dtape_file = dst_timeline / f"{codename.lower()}_tml_dance.dtape.ckd"
            if dtape_file.exists():
                dtape_text = dtape_file.read_text(encoding="utf-8", errors="replace")
                dtape_text = dtape_text.replace(".png", ".tga")
                dtape_file.write_text(dtape_text, encoding="utf-8")
                
            # 4. Modify musictrack `.wav` to `.ogg`
            extracted_cache = extracted_path / "cache" / "itf_cooked" / "pc" / "world" / "maps" / codename.lower()
            src_musictrack = extracted_cache / "audio" / f"{codename.lower()}_musictrack.tpl.ckd"
            dst_musictrack = paths["cache_audio"] / f"{codename.lower()}_musictrack.tpl.ckd"
            if src_musictrack.exists():
                mt_text = src_musictrack.read_text(encoding="utf-8", errors="replace")
                mt_text = mt_text.replace(".wav", ".ogg")
                dst_musictrack.parent.mkdir(parents=True, exist_ok=True)
                dst_musictrack.write_text(mt_text, encoding="utf-8")
                
            # 5. Copy media assets to world directories
            self._log(logging.INFO, "Copying media assets (audio/video)...")
            audio_dst = paths["world_audio"] / f"{codename.lower()}.ogg"
            video_dst = paths["world_videoscoach"] / f"{codename.lower()}.webm"
            
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
            bundle_name = f"{codename.lower()}_pc.ipk"
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
