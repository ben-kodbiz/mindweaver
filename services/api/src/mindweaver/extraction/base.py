"""Document processor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from mindweaver.document_model import CanonicalDocument


class ExtractionError(Exception):
    """Fatal failure while extracting a document."""


@dataclass
class ExtractionResult:
    document: CanonicalDocument
    warnings: list[str] = field(default_factory=list)
    requires_ocr: bool = False


class DocumentProcessor(ABC):
    """Converts a source file into the project-owned canonical format."""

    name: str

    @abstractmethod
    def extract(self, path: Path, *, document_id: str, filename: str) -> ExtractionResult:
        """Extract ``path`` into a :class:`CanonicalDocument`.

        Raises :class:`ExtractionError` when the document cannot be processed
        (corrupt, password-protected, unsupported).
        """
