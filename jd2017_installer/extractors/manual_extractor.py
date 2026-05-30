"""Extractor for handling manually provided map files (zips or folders).

Allows users to point the installer at a local directory or ZIP archive
containing map data.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from jd2017_installer.core.exceptions import ExtractionError
from jd2017_installer.extractors.base import BaseExtractor, ExtractionProgress, ProgressCallback
from jd2017_installer.core.path_discovery import infer_codename

logger = logging.getLogger("jd2017.extractors.manual_extractor")


class ManualExtractor(BaseExtractor):
    """Extractor for manually provided local map directories or archives."""

    def __init__(
        self,
        source_path: str | Path,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> None:
        """Initialize the manual extractor.

        Args:
            source_path: Path to a local directory or .zip containing map files.
            progress_cb: Optional callback for extraction progress.
        """
        self.source_path = Path(source_path).resolve()
        self.progress_cb = progress_cb
        self._codename = infer_codename(self.source_path)

    def _emit_progress(self, phase: str, current: int, total: int, detail: str = "") -> None:
        """Emit a progress update if a callback is registered."""
        if self.progress_cb:
            self.progress_cb(ExtractionProgress(phase=phase, current=current, total=total, detail=detail))

    def extract(self, output_dir: Path) -> Path:
        """Extract or copy the local files into the output directory."""
        if not self.source_path.exists():
            raise ExtractionError(f"Source path does not exist: {self.source_path}")

        map_dir = output_dir / self._codename
        map_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Starting manual extraction from %s to %s", self.source_path, map_dir)

        if self.source_path.is_file() and self.source_path.suffix.lower() == ".zip":
            self._extract_zip(self.source_path, map_dir)
        elif self.source_path.is_dir():
            self._copy_directory(self.source_path, map_dir)
        else:
            raise ExtractionError(f"Unsupported manual source format: {self.source_path}")

        logger.info("Manual extraction complete for %s", self._codename)
        return map_dir

    def _extract_zip(self, zip_path: Path, dest_dir: Path) -> None:
        """Extract a zip archive to the destination directory."""
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.infolist()
                total = len(members)
                
                for idx, member in enumerate(members):
                    self._emit_progress("extracting", idx, total, member.filename)
                    zf.extract(member, dest_dir)
                    
                self._emit_progress("extracting", total, total, "Done")
        except zipfile.BadZipFile as e:
            raise ExtractionError(f"Invalid or corrupted ZIP archive: {e}")

    def _copy_directory(self, src_dir: Path, dest_dir: Path) -> None:
        """Copy a directory tree to the destination."""
        files = list(src_dir.rglob("*"))
        total = len(files)
        
        for idx, f in enumerate(files):
            if f.is_file():
                rel_path = f.relative_to(src_dir)
                target = dest_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                
                self._emit_progress("copying", idx, total, f.name)
                shutil.copy2(f, target)
                
        self._emit_progress("copying", total, total, "Done")

    def get_codename(self) -> Optional[str]:
        return self._codename

    def get_source_dir(self) -> Optional[Path]:
        return self.source_path if self.source_path.is_dir() else self.source_path.parent
