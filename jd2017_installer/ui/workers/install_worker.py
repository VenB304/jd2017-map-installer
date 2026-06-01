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
            
            # Find the cache world root
            extracted_world = extracted_path / "cache" / "itf_cooked" / "pc" / "world" / "maps" / codename.lower()
            if not extracted_world.exists():
                matches = list(extracted_path.rglob(f"{codename.lower()}_tml_dance.dtape.ckd"))
                if matches:
                    extracted_world = matches[0].parent.parent
                else:
                    self._log(logging.WARNING, "Could not reliably locate map cache root; assuming standard path.")
                    
            songdesc_path = extracted_world / "songdesc.tpl.ckd"
            if songdesc_path.exists():
                norm_data = load_and_normalize_songdesc_file(songdesc_path, codename)
                num_coach = norm_data.get("num_coach", 1)
                
                self._log(logging.INFO, "Patching songdesc.tpl.ckd...")
                sd_content = songdesc_path.read_bytes()
                sd_text = sd_content.lstrip(b"\x00\xef\xbb\xbf").decode("utf-8", errors="replace").strip('\x00\r\n\t ')
                sd_json = json.loads(sd_text)
            else:
                self._log(logging.INFO, "songdesc.tpl.ckd not found. Synthesizing metadata...")
                jdlo_meta_path = extracted_path / "jdlo_metadata.json"
                if not jdlo_meta_path.exists():
                    import re
                    coach_files = (
                        list(extracted_path.rglob(f"{codename.lower()}_coach_*.tga.ckd")) + 
                        list(extracted_path.rglob(f"{codename.lower()}_coach_*.png.ckd")) +
                        list(extracted_path.rglob(f"{codename.lower()}_coach_*.png")) +
                        list(extracted_path.rglob(f"{codename.lower()}_coach_*.jpg"))
                    )
                    inferred_coach = 1
                    for cf in coach_files:
                        m = re.search(r"coach_(\d+)", cf.name.lower())
                        if m: inferred_coach = max(inferred_coach, int(m.group(1)))
                    self._log(logging.INFO, f"Inferred {inferred_coach} coaches from textures.")
                    jdlo_meta = {"coachCount": inferred_coach}
                else:
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
            
            # JD2017 PC engine crashes on boot if texture paths are missing from JSON songdesc
            for comp in sd_json.get("COMPONENTS", []):
                if comp.get("__class") == "JD_SongDescTemplate":
                    name_lower = codename.lower()
                    base_path = f"world/maps/{name_lower}/menuart/textures/{name_lower}"
                    if "Cover" not in comp: comp["Cover"] = f"{base_path}_cover_generic.tga"
                    if "CoverOnline" not in comp: comp["CoverOnline"] = f"{base_path}_cover_online.tga"
                    if "AlbumCoach" not in comp: comp["AlbumCoach"] = f"{base_path}_cover_albumcoach.tga"
                    if "AlbumBkg" not in comp: comp["AlbumBkg"] = f"{base_path}_cover_albumbkg.tga"
                    if "BannerBkg" not in comp: comp["BannerBkg"] = f"{base_path}_banner_bkg.tga"
                    for i in range(1, 5):
                        coach_key = f"Coach{i}"
                        if coach_key not in comp: comp[coach_key] = f"{base_path}_coach_{i}.tga"
                    
                    # Also ensure MapName is explicitly matched to codename to avoid mismatches
                    comp["MapName"] = codename

            build_songdesc = paths["cache_root"] / "songdesc.tpl.ckd"
            build_songdesc.parent.mkdir(parents=True, exist_ok=True)
            build_songdesc.write_text(json.dumps(sd_json, ensure_ascii=True), encoding="utf-8")
            
            # 2. Copy timeline and autodance from extracted based STRICTLY on guide.md
            self._log(logging.INFO, "Copying timeline and autodance based on guide.md...")
            
            # Guide Line 44: merge the unpacked main scene's world/maps/[codename] autodance and timeline folders
            src_uncooked_world = extracted_path / "world" / "maps" / codename.lower()
            dst_uncooked_world = paths["world_root"]
            platform_ignore = shutil.ignore_patterns("durango", "nx", "orbis", "wiiu", "scarlett", "prospero")
            if (src_uncooked_world / "timeline").exists():
                shutil.copytree(src_uncooked_world / "timeline", dst_uncooked_world / "timeline", dirs_exist_ok=True, ignore=platform_ignore)
            if (src_uncooked_world / "autodance").exists():
                shutil.copytree(src_uncooked_world / "autodance", dst_uncooked_world / "autodance", dirs_exist_ok=True, ignore=platform_ignore)
            
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
                    # Rename .png.ckd to .tga.ckd first, EXCEPT for pictos
                    file_path = Path(root) / f
                    if f.endswith(".png.ckd") and "pictos" not in file_path.parts:
                        new_name = f.replace(".png.ckd", ".tga.ckd")
                        new_path = Path(root) / new_name
                        file_path.replace(new_path)
                        file_path = new_path
                        f = new_name

                    # Convert texture if it's .tga.ckd or .png.ckd
                    if f.endswith(".tga.ckd") or f.endswith(".png.ckd"):
                        try:
                            data = file_path.read_bytes()
                            # Check if it needs conversion (i.e. not already standard DDS)
                            if len(data) > 44 and b"DDS " not in data[44:48]:
                                new_data = convert_texture_lossless(data, file_path)
                                if isinstance(new_data, str):
                                    shutil.copy2(new_data, file_path)
                                else:
                                    file_path.write_bytes(new_data)
                        except TextureEncodingError as e:
                            self._log(logging.WARNING, f"Failed to convert texture {file_path.name}: {e}")
                        
            menuart_dir = paths["cache_menuart_textures"]
            from jd2017_installer.installers.texture_encoder import convert_texture_lossless, compile_image_to_tga_ckd
            
            # Process pre-compiled .tga.ckd files
            for ext_file in extracted_path.rglob("*.tga.ckd"):
                if "pictos" in ext_file.parts or "timeline" in ext_file.parts:
                    continue # Skip timeline/pictos, handled elsewhere
                try:
                    # Keep single 'b' for expand background as per guide.md
                    target_name = ext_file.name.lower()
                    # Check if it needs conversion to PC native
                    try:
                        pc_ckd = convert_texture_lossless(ext_file.read_bytes(), ext_file)
                        if isinstance(pc_ckd, str):
                            # It's already PC native, copy the original file
                            shutil.copy2(pc_ckd, menuart_dir / target_name)
                        else:
                            # It was converted, write the bytes
                            (menuart_dir / target_name).write_bytes(pc_ckd)
                        self._log(logging.INFO, f"Copied and converted {ext_file.name} to menuart")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to convert menuart {ext_file.name}: {e}")
                except Exception as e:
                    self._log(logging.WARNING, f"Failed to convert menuart {ext_file.name}: {e}")
            
            # Process raw .png and .jpg files (HTML JDU maps)
            for ext in ("*.png", "*.jpg", "*.jpeg"):
                for ext_file in extracted_path.rglob(ext):
                    if "phone" in ext_file.name.lower():
                        continue # Phones go uncooked, handled below
                    if "pictos" in ext_file.parts or "timeline" in ext_file.parts:
                        continue # Skip timeline/pictos
                    try:
                        target_name = f"{ext_file.stem.lower()}{ext_file.suffix.lower()}"
                        if "albumbbkg" in target_name:
                            target_name = target_name.replace("albumbbkg", "albumbkg")
                        
                        # Compile to .tga.ckd for the cooked menuart directory (fix for 'X' indicator)
                        ckd_name = f"{ext_file.stem.lower()}.tga.ckd"
                        if "albumbbkg" in ckd_name:
                            ckd_name = ckd_name.replace("albumbbkg", "albumbkg")
                        ckd_path = menuart_dir / ckd_name
                        if not ckd_path.exists():
                            try:
                                compile_image_to_tga_ckd(ext_file, ckd_path)
                                self._log(logging.INFO, f"Compiled {ext_file.name} to {ckd_name} for menuart")
                            except Exception as compile_e:
                                self._log(logging.WARNING, f"Failed to compile {ext_file.name} to CKD: {compile_e}")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to process raw image {ext_file.name}: {e}")
                    
            # If a custom banner_bkg.dds is provided as per guide.md, wrap it to PC tga.ckd
            from jd2017_installer.installers.texture_encoder import wrap_dds_to_tga_ckd
            for dds_file in extracted_path.glob("*.dds"):
                if "banner_bkg" in dds_file.name.lower():
                    try:
                        dds_data = dds_file.read_bytes()
                        wrapped = wrap_dds_to_tga_ckd(dds_data)
                        target_name = f"{codename.lower()}_banner_bkg.tga.ckd"
                        (menuart_dir / target_name).write_bytes(wrapped)
                        self._log(logging.INFO, f"Successfully wrapped custom DDS banner {dds_file.name} to tga.ckd")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to wrap custom DDS banner {dds_file.name}: {e}")
            
            # Patch SongDesc.tpl.ckd to point to .png instead of .tga for UI textures if they exist as .png
            songdesc_path = paths["cache_root"] / "songdesc.tpl.ckd"
            if songdesc_path.exists():
                try:
                    songdesc_bytes = songdesc_path.read_bytes()
                    # Only replace .tga with .png for phone images
                    for png_file in extracted_path.rglob("*_phone.*"):
                        if png_file.suffix.lower() not in (".png", ".jpg", ".jpeg"): continue
                        tga_name = png_file.name.replace(png_file.suffix, ".tga").encode("utf-8")
                        png_name = png_file.name.encode("utf-8")
                        songdesc_bytes = songdesc_bytes.replace(tga_name, png_name)
                        # try uppercase TGA
                        tga_name_upper = png_file.name.replace(png_file.suffix, ".TGA").encode("utf-8")
                        songdesc_bytes = songdesc_bytes.replace(tga_name_upper, png_name)
                    songdesc_path.write_bytes(songdesc_bytes)
                    self._log(logging.INFO, "Patched songdesc.tpl.ckd to use .png MenuArt textures natively.")
                except Exception as e:
                    self._log(logging.WARNING, f"Failed to patch songdesc.tpl.ckd: {e}")
                        
            # Uncooked phone assets belong in patch_pc.ipk: world/maps/[codename]/menuart/textures/ as per guide.md (Lines 50-60)
            patch_staging = temp_dir / "patch_staging"
            patch_world_menuart_dir = patch_staging / "world" / "maps" / codename.lower() / "menuart" / "textures"
            patch_world_menuart_dir.mkdir(parents=True, exist_ok=True)
            for ext_img in extracted_path.rglob("*_phone.*"):
                if ext_img.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    try:
                        shutil.copy2(ext_img, patch_world_menuart_dir / ext_img.name.lower())
                        self._log(logging.INFO, f"Copied phone image {ext_img.name.lower()} to patch_pc staging")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to copy phone image {ext_img.name}: {e}")
                        
            # Phase 1 Fallback: banner_bkg generation
            banner_png = menuart_dir / f"{codename.lower()}_banner_bkg.png"
            banner_ckd = menuart_dir / f"{codename.lower()}_banner_bkg.tga.ckd"
            
            if not banner_png.exists() and not banner_ckd.exists():
                map_bkg_src = self.extractor.media_context.map_bkg_path if hasattr(self, "extractor") and hasattr(self.extractor, "media_context") else None
                if not map_bkg_src or not map_bkg_src.exists():
                    for search_dir in (extracted_path, menuart_dir):
                        if map_bkg_src and map_bkg_src.exists():
                            break
                        for ext in (".png", ".tga", ".jpg", ".png.ckd", ".tga.ckd", ".jpg.ckd"):
                            # Check original casing and lowercase casing
                            for name in (f"{codename}_map_bkg{ext}", f"{codename.lower()}_map_bkg{ext}"):
                                candidate = search_dir / name
                                if candidate.exists():
                                    map_bkg_src = candidate
                                    break
                            if map_bkg_src and map_bkg_src.exists():
                                break
                                
                generated = False
                if map_bkg_src and map_bkg_src.exists():
                    if map_bkg_src.name.endswith(".tga.ckd"):
                        # If the source is a CKD, we cannot use PIL, so we just duplicate it
                        shutil.copy2(map_bkg_src, banner_ckd)
                        self._log(logging.INFO, f"Used {map_bkg_src.name} as duplicate for banner_bkg (CKD)")
                        generated = True
                    else:
                        try:
                            from PIL import Image, ImageChops, ImageOps
                            bg_img = Image.open(map_bkg_src).convert("RGBA")
                            bg_w, bg_h = bg_img.size
                            scale = max(2048 / bg_w, 1024 / bg_h)
                            new_w, new_h = int(bg_w * scale), int(bg_h * scale)
                            bg_img = bg_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                            offset_x = (new_w - 2048) // 2
                            offset_y = (new_h - 1024) // 2
                            bg_img = bg_img.crop((offset_x, offset_y, offset_x + 2048, offset_y + 1024))
                            greyscale = ImageOps.grayscale(bg_img).convert("RGBA")
                            blue_layer = Image.new("RGBA", (2048, 1024), (0, 0, 255, 255))
                            result = ImageChops.difference(greyscale, blue_layer)
                            result.save(banner_png, "PNG")
                            self._log(logging.INFO, f"Generated banner_bkg natively as PNG for '{codename}'")
                            generated = True
                        except Exception as e:
                            self._log(logging.WARNING, f"Failed to generate banner_bkg for '{codename}': {e}")
                
                # Ultimate fallback: just duplicate a background texture to prevent engine crash
                if not generated:
                    for fallback_name in (f"{codename.lower()}_map_bkg.png", f"{codename.lower()}_cover_albumbkg.png", f"{codename.lower()}_cover_generic.png"):
                        fallback_src = menuart_dir / fallback_name
                        if fallback_src.exists():
                            shutil.copy2(fallback_src, banner_png)
                            self._log(logging.INFO, f"Used {fallback_name} as fallback for banner_bkg.png")
                            generated = True
                            break
                            
                if not generated:
                    for fallback_name in (f"{codename.lower()}_map_bkg.tga.ckd", f"{codename.lower()}_cover_albumbkg.tga.ckd", f"{codename.lower()}_cover_generic.tga.ckd"):
                        fallback_src = menuart_dir / fallback_name
                        if fallback_src.exists():
                            shutil.copy2(fallback_src, banner_ckd)
                            self._log(logging.INFO, f"Used {fallback_name} as fallback for banner_bkg.tga.ckd")
                            generated = True
                            break
                
            # 3. Modify dtape `.png` to `.tga`
            dtape_candidates = list(dst_timeline.glob("*.dtape.ckd"))
            for dtape_file in dtape_candidates:
                if "dance" in dtape_file.name.lower():
                    try:
                        dtape_bytes = dtape_file.read_bytes()
                        has_tga = False
                        if (dst_timeline / "pictos").exists():
                            has_tga = any((dst_timeline / "pictos").rglob("*.tga.ckd"))
                            
                        if has_tga and (b".png" in dtape_bytes or b".PNG" in dtape_bytes):
                            dtape_bytes = dtape_bytes.replace(b".png", b".tga").replace(b".PNG", b".tga")
                            dtape_file.write_bytes(dtape_bytes)
                            self._log(logging.INFO, f"Patched picto paths to .tga in {dtape_file.name}")
                        elif b".tga" in dtape_bytes or b".TGA" in dtape_bytes:
                            # If we only have .png pictos but dtape expects .tga (e.g. from a JDNext extraction that pre-patched it), revert it
                            if not has_tga and any((dst_timeline / "pictos").rglob("*.png")):
                                dtape_bytes = dtape_bytes.replace(b".tga", b".png").replace(b".TGA", b".png")
                                dtape_file.write_bytes(dtape_bytes)
                                self._log(logging.INFO, f"Patched picto paths to .png in {dtape_file.name}")
                    except Exception as e:
                        self._log(logging.WARNING, f"Failed to patch dtape '{dtape_file.name}': {e}")

            # 4. Modify musictrack `.wav` to `.ogg`
            src_musictrack = extracted_world / "audio" / f"{codename.lower()}_musictrack.tpl.ckd"
            dst_musictrack = paths["cache_audio"] / f"{codename.lower()}_musictrack.tpl.ckd"
            if src_musictrack.exists():
                dst_musictrack.parent.mkdir(parents=True, exist_ok=True)
                mt_bytes = src_musictrack.read_bytes()
                mt_bytes = mt_bytes.replace(b".wav", b".ogg").replace(b".WAV", b".ogg")
                dst_musictrack.write_bytes(mt_bytes)
                self._log(logging.INFO, f"Copied and patched {src_musictrack.name} to .ogg")
            else:
                self._log(logging.WARNING, f"musictrack.tpl.ckd not found for '{codename}', audio sequencing may be incomplete")
                
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
            
            # Pass the patch_staging directory to inject phone images into patch_pc.ipk
            patch_staging = temp_dir / "patch_staging"
            if not patch_staging.exists():
                patch_staging = None
            
            self.signals.progress.emit("registration", 0, 2, "Patching SkuScenes")
            patch_sku_scenes(game_dir, codename, extra_content_dir=patch_staging)
            
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
