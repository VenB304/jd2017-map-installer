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


class InstallWorker(QRunnable):
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
            # In real implementation, read the normalized data. Here we pass dummy for num_coach.
            generate_all_scenes(build_dir, codename, num_coach=1)
            
            # Phase 4: IPK Packing
            self._log(logging.INFO, "[Phase 4] Packing bundle IPK...")
            bundle_idx = next_bundle_index(game_dir)
            bundle_name = f"bundle_{bundle_idx}_pc.ipk"
            bundle_path = game_dir / bundle_name
            
            self.signals.progress.emit("ipk_packing", 0, 1, f"Building {bundle_name}")
            pack_folder_to_ipk(build_dir, bundle_path)
            self._log(logging.INFO, f"Packed map data to {bundle_path.name}")
            
            # Phase 5: Global Registration
            self._log(logging.INFO, "[Phase 5] Registering map globally...")
            
            self.signals.progress.emit("registration", 0, 2, "Patching SkuScenes")
            patch_sku_scenes(game_dir, codename)
            
            if self.config.generate_secure_fat_on_install:
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
