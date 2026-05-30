"""Abstract base class for all extractors.

Each extractor is responsible for fetching raw map data from a specific
source (web, IPK archive, etc.) and placing it into a temporary directory
for the normalizer to process.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("jd2017.extractors.base")


@dataclass
class ExtractionProgress:
    """Unified progress event emitted by extractors and the download pipeline.

    Attributes:
        phase:   Short label for the current activity ('downloading',
                 'extracting', 'decoding', ...).
        current: Number of completed units (files, bytes, steps ...).
        total:   Total expected units for the current phase.
        detail:  Optional human-readable detail (filename, codename, etc.).
    """

    phase: str
    current: int
    total: int
    detail: str = field(default="")


#: Type alias for progress callbacks accepted by extractors and downloaders.
ProgressCallback = Callable[[ExtractionProgress], None]


class BaseExtractor(ABC):
    """Abstract interface for map data extractors.

    Subclasses implement :meth:`extract` which populates a directory
    with raw CKD files and media assets.  The normalizer then processes
    this directory into a ``NormalizedMapData``.
    """

    @abstractmethod
    def extract(self, output_dir: Path) -> Path:
        """Extract map data into ``output_dir``.

        Args:
            output_dir: Directory to write extracted files into.

        Returns:
            Path to the directory containing extracted files
            (may be ``output_dir`` itself or a subdirectory).

        Raises:
            ExtractionError: If extraction fails.
        """
        ...

    @abstractmethod
    def get_codename(self) -> Optional[str]:
        """Return the map codename if known, else ``None``."""
        ...

    def get_source_dir(self) -> Optional[Path]:
        """Return the directory that was the primary data source, if meaningful."""
        return None

    def get_warnings(self) -> list[str]:
        """Return non-fatal warnings collected during extraction."""
        return []
