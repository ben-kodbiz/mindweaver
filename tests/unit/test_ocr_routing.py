import pytest
from fixtures.pdf import make_image_only_pdf, make_structured_pdf
from mindweaver.config import DocumentProcessorConfig, Settings
from mindweaver.document_model import BlockType
from mindweaver.extraction.pypdf_processor import PyPdfProcessor
from mindweaver.extraction.registry import get_processor
from mindweaver.models import Document
from mindweaver.ocr.base import OCRPageResult, OCRProvider, OCRWord


class FakeOCRProvider(OCRProvider):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def ocr_image(self, image: bytes, *, page_number: int, languages: list[str]) -> OCRPageResult:
        self.calls.append(page_number)
        return OCRPageResult(
            page_number=page_number,
            text=f"recognised text for page {page_number}",
            confidence=0.92,
            words=[OCRWord(text=f"recognised text for page {page_number}", confidence=0.92)],
            low_confidence=False,
        )


def _settings() -> Settings:
    return Settings(document_processor=DocumentProcessorConfig(backend="pypdf"))


def _pdfium_available() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


def test_native_pdf_without_ocr_requires_nothing(tmp_path):
    path = tmp_path / "native.pdf"
    path.write_bytes(make_structured_pdf())
    result = PyPdfProcessor().extract(path, document_id="d1", filename="native.pdf")
    assert result.requires_ocr is False
    assert result.document.pages[0].extraction_method == "native"


def test_scanned_pdf_without_ocr_sets_requires_ocr(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_image_only_pdf(2))
    result = PyPdfProcessor().extract(path, document_id="d1", filename="scan.pdf")
    assert result.requires_ocr is True
    assert result.document.pages[0].extraction_method == "ocr"
    assert result.document.pages[0].low_confidence is True
    assert result.document.metadata["page_inspections"][0]["content_type"] == "scanned"


def test_scanned_pdf_with_ocr_produces_blocks(tmp_path, app_settings):
    if not _pdfium_available():
        pytest.skip("ocr extra not installed")
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_image_only_pdf(2))

    from mindweaver.database import build_engine, init_database, make_session_factory, session_scope

    hybrid = app_settings.model_copy(
        update={"document_processor": DocumentProcessorConfig(backend="hybrid")}
    )
    engine = build_engine(app_settings)
    init_database(engine)
    factory = make_session_factory(engine)
    fake = FakeOCRProvider()
    with session_scope(factory) as session:
        session.add(
            Document(
                id="d1",
                title="scan",
                original_filename="scan.pdf",
                sha256="a" * 64,
                file_size=1,
            )
        )
        session.flush()
        processor = get_processor(hybrid, session=session, ocr_provider=fake, ocr_enabled=True)
        assert isinstance(processor, PyPdfProcessor)
        result = processor.extract(path, document_id="d1", filename="scan.pdf")

    assert result.requires_ocr is False
    assert fake.calls == [1, 2]  # both pages OCR'd, in order
    ocr_blocks = [b for b in result.document.blocks if b.block_type == BlockType.PARAGRAPH]
    assert len(ocr_blocks) == 2
    assert ocr_blocks[0].page_number == 1
    assert ocr_blocks[0].source_confidence == 0.92
    assert result.document.pages[0].extraction_method == "ocr"
    assert result.document.pages[0].confidence == 0.92
    assert result.document.pages[0].low_confidence is False


def test_hybrid_backend_without_ocr_raises(tmp_path, app_settings, monkeypatch):
    from mindweaver.database import build_engine, init_database, make_session_factory
    from mindweaver.extraction import registry as registry_module
    from mindweaver.extraction.registry import UnknownProcessorError
    from mindweaver.ocr.registry import UnknownOCRProviderError

    def _no_ocr(*_args, **_kwargs):
        raise UnknownOCRProviderError("no OCR provider available")

    monkeypatch.setattr(registry_module, "get_ocr_provider", _no_ocr)

    settings = app_settings.model_copy(
        update={"document_processor": DocumentProcessorConfig(backend="hybrid")}
    )
    engine = build_engine(app_settings)
    init_database(engine)
    with make_session_factory(engine)() as session:
        with pytest.raises(UnknownProcessorError) as exc_info:
            get_processor(settings, session=session, ocr_enabled=True)
        assert "OCR" in str(exc_info.value)


def test_ocr_cache_reuses_results(tmp_path, app_settings):
    if not _pdfium_available():
        pytest.skip("ocr extra not installed")
    from mindweaver.database import build_engine, init_database, make_session_factory, session_scope

    path = tmp_path / "scan.pdf"
    path.write_bytes(make_image_only_pdf(1))

    engine = build_engine(app_settings)
    init_database(engine)
    factory = make_session_factory(engine)

    hybrid = app_settings.model_copy(
        update={"document_processor": DocumentProcessorConfig(backend="hybrid")}
    )
    fake = FakeOCRProvider()
    with session_scope(factory) as session:
        session.add(
            Document(
                id="d1",
                title="scan",
                original_filename="scan.pdf",
                sha256="a" * 64,
                file_size=1,
            )
        )
        session.flush()
        processor = get_processor(hybrid, session=session, ocr_provider=fake, ocr_enabled=True)
        processor.extract(path, document_id="d1", filename="scan.pdf")

    # Second run uses the cache: provider must not be called again.
    fake2 = FakeOCRProvider()
    with session_scope(factory) as session:
        processor = get_processor(hybrid, session=session, ocr_provider=fake2, ocr_enabled=True)
        result = processor.extract(path, document_id="d1", filename="scan.pdf")

    assert fake.calls == [1]
    assert fake2.calls == []
    assert result.requires_ocr is False
    assert any(b.text.startswith("recognised") for b in result.document.blocks)
