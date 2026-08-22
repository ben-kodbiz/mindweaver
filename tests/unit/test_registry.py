import pytest
from mindweaver.config import DocumentProcessorConfig, Settings
from mindweaver.extraction.pypdf_processor import PyPdfProcessor
from mindweaver.extraction.registry import UnknownProcessorError, get_processor


def _settings(backend: str) -> Settings:
    return Settings(document_processor=DocumentProcessorConfig(backend=backend))


def test_default_processor_is_pypdf():
    processor = get_processor(Settings())
    assert isinstance(processor, PyPdfProcessor)


def test_native_alias_resolves_to_pypdf():
    assert isinstance(get_processor(_settings("native")), PyPdfProcessor)


def test_unknown_backend_raises():
    config = DocumentProcessorConfig.model_construct(backend="bogus")
    settings = Settings.model_construct(document_processor=config)
    with pytest.raises(UnknownProcessorError):
        get_processor(settings)


def test_docling_backend_resolves_when_installed():
    try:
        from mindweaver.extraction.docling_processor import DoclingProcessor  # noqa: F401
    except ImportError:
        pytest.skip("docling extra not installed")
    processor = get_processor(_settings("docling"))
    assert processor.name == "docling"
