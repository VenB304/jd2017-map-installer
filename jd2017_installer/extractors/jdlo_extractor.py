"""Extractor for downloading Just Dance maps from the JDLO server.

JDLO (Just Dance Legacy Online) provides a custom server implementation
where map assets (JSON metadata, video/audio, textures) can be downloaded.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests

from jd2017_installer.core.exceptions import DownloadError, ExtractionError
from jd2017_installer.extractors.base import BaseExtractor, ExtractionProgress, ProgressCallback

logger = logging.getLogger("jd2017.extractors.jdlo_extractor")


class JDLOExtractor(BaseExtractor):
    """Extractor for fetching map data from the JDLO CDN."""

    def __init__(
        self,
        map_name: str,
        server_url: str = "https://cdn.jdlo.ovosimpatico.com/",
        sku: str = "jd2017-pc-all",
        progress_cb: Optional[ProgressCallback] = None,
    ) -> None:
        """Initialize the JDLO extractor.

        Args:
            map_name: Map codename to download (e.g. 'dontwannaknow').
            server_url: Base URL of the JDLO server.
            sku: SKU identifier for the targeted version (e.g., jd2017-pc-all).
            progress_cb: Optional callback for download progress.
        """
        self.map_name = map_name.lower().strip()
        self.server_url = server_url
        self.sku = sku
        self.progress_cb = progress_cb
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "JD2017-Map-Installer/1.0",
        })

    def _emit_progress(self, phase: str, current: int, total: int, detail: str = "") -> None:
        """Emit a progress update if a callback is registered."""
        if self.progress_cb:
            self.progress_cb(ExtractionProgress(phase=phase, current=current, total=total, detail=detail))

    def _download_file(self, url: str, output_path: Path) -> None:
        """Download a single file with progress tracking."""
        try:
            resp = self.session.get(url, stream=True, timeout=30)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self._emit_progress("downloading", downloaded, total_size, output_path.name)
            
            logger.debug("Downloaded %s to %s", url, output_path.name)
        except requests.RequestException as e:
            http_code = getattr(e.response, "status_code", 0) if hasattr(e, "response") else 0
            logger.error("Download failed for %s: %s", url, e)
            raise DownloadError(f"Failed to download {url}: {e}", url=url, http_code=http_code)

    def extract(self, output_dir: Path) -> Path:
        """Download map files from JDLO and place them in the output directory."""
        logger.info("Starting JDLO extraction for map: %s", self.map_name)
        
        map_dir = output_dir / self.map_name
        map_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine paths based on JD2017 structure (e.g. JSON metadata, audio, video)
        # Note: A real JDLO extractor would query an index/manifest or try specific paths.
        # This implementation represents a simplified download logic structure.
        
        base_asset_url = urljoin(self.server_url, f"packages/{self.map_name}/")
        
        # Core metadata files
        metadata_files = [
            f"{self.map_name}.json",
            f"{self.map_name}_songdesc.tpl.ckd",
            f"{self.map_name}_musictrack.tpl.ckd",
        ]
        
        # Audio and Video
        media_files = [
            f"{self.map_name}.ogg",
            f"{self.map_name}.webm",
        ]
        
        # Texture files
        texture_files = [
            f"{self.map_name}_cover_generic.tga.ckd",
            f"{self.map_name}_cover_online.tga.ckd",
            f"{self.map_name}_coach_1.tga.ckd",
        ]
        
        all_files = metadata_files + media_files + texture_files
        total_files = len(all_files)
        
        for idx, filename in enumerate(all_files):
            url = urljoin(base_asset_url, filename)
            dest_path = map_dir / filename
            self._emit_progress("fetching_assets", idx, total_files, filename)
            try:
                self._download_file(url, dest_path)
            except DownloadError as e:
                # 404s might be okay for optional files (like extra coaches), 
                # but we'll raise an error if it's the primary JSON metadata.
                if filename.endswith(".json") and e.http_code == 404:
                    raise ExtractionError(f"Map '{self.map_name}' not found on JDLO server.")
                logger.warning("Optional file missing: %s", filename)
        
        self._emit_progress("fetching_assets", total_files, total_files, "Done")
        logger.info("JDLO extraction complete for %s", self.map_name)
        
        return map_dir

    def get_codename(self) -> Optional[str]:
        return self.map_name
