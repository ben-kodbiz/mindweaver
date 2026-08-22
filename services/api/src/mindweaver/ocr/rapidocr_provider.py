"""RapidOCR provider (optional ``[ocr]`` extra).

Renders are passed in as PNG bytes; rapidocr is initialised lazily with the
torch inference engine so it works without onnxruntime.
"""

from __future__ import annotations

import statistics
from io import BytesIO
from typing import Any

from mindweaver.config import Settings
from mindweaver.ocr.base import OCREngineError, OCRPageResult, OCRProvider, OCRWord

_ENGINE_PARAMS = {
    "Det.engine_type": "torch",
    "Rec.engine_type": "torch",
    "Cls.engine_type": "torch",
}


class RapidOCRProvider(OCRProvider):
    name = "rapidocr"

    def __init__(self, settings: Settings) -> None:
        import rapidocr  # noqa: F401  (fail early if the OCR extra is missing)

        self._settings = settings
        self._engine: Any = None

    def _ensure_engine(self) -> Any:
        if self._engine is None:
            from rapidocr.main import DEFAULT_CFG_PATH, RapidOCR
            from rapidocr.utils.parse_parameters import ParseParams

            config = ParseParams.load(DEFAULT_CFG_PATH)
            engine_type = type(config.Det.engine_type)
            params = {key: engine_type(value) for key, value in _ENGINE_PARAMS.items()}
            self._engine = RapidOCR(params=params)
        return self._engine

    def ocr_image(self, image: bytes, *, page_number: int, languages: list[str]) -> OCRPageResult:
        import numpy as np
        from PIL import Image as PILImage
        from PIL import ImageOps

        try:
            pil: Any = PILImage.open(BytesIO(image))
            pil = ImageOps.exif_transpose(pil).convert("RGB")
            # Very large page images can overwhelm the detector; downscale.
            max_side = 2200
            if max(pil.size) > max_side:
                ratio = max_side / max(pil.size)
                pil = pil.resize((max(1, int(pil.width * ratio)), max(1, int(pil.height * ratio))))
            array = np.asarray(pil)
            output = self._ensure_engine()(array)
        except Exception as exc:
            raise OCREngineError(f"OCR engine failed: {exc}") from exc

        texts = list(output.txts) if output.txts is not None else []
        scores = [float(s) for s in output.scores] if output.scores is not None else []
        boxes = list(output.boxes) if output.boxes is not None else []

        words = [
            OCRWord(
                text=str(text),
                confidence=float(score),
                box=(
                    tuple(float(coord) for point in box for coord in point)
                    if box is not None
                    else None
                ),
            )
            for text, score, box in zip(texts, scores, boxes, strict=False)
        ]
        confidence = statistics.mean(scores) if scores else None
        low_confidence = confidence is None or confidence < self._settings.ocr.min_confidence

        return OCRPageResult(
            page_number=page_number,
            text="\n".join(texts),
            confidence=confidence,
            words=words,
            low_confidence=low_confidence,
        )
