from fixtures.pdf import (
    make_mixed_pdf,
    make_pdf,
    make_scanned_pdf,
    make_structured_pdf,
)
from mindweaver.extraction.page_inspector import PageContentType, inspect_page, inspect_pages
from pypdf import PdfReader


def test_native_pdf_pages_classified_native():
    reader = PdfReader(stream=__import__("io").BytesIO(make_structured_pdf()))
    inspections = inspect_pages(reader)
    assert inspections
    assert all(
        i.content_type in (PageContentType.NATIVE, PageContentType.MIXED) for i in inspections
    )
    assert all(i.text_length > 0 for i in inspections)


def test_blank_pages_classified_empty():
    reader = PdfReader(stream=__import__("io").BytesIO(make_pdf(3)))
    inspections = inspect_pages(reader)
    assert len(inspections) == 3
    assert all(i.content_type == PageContentType.EMPTY for i in inspections)


def test_scanned_pdf_classified_scanned():
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("ocr extra not installed")
    reader = PdfReader(stream=__import__("io").BytesIO(make_scanned_pdf()))
    inspections = inspect_pages(reader)
    assert len(inspections) == 2
    assert all(i.content_type == PageContentType.SCANNED for i in inspections)
    assert all(i.has_images for i in inspections)


def test_mixed_pdf_routes_pages():
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("ocr extra not installed")
    reader = PdfReader(stream=__import__("io").BytesIO(make_mixed_pdf()))
    inspections = inspect_pages(reader)
    assert len(inspections) == 2
    assert inspections[0].content_type in (PageContentType.NATIVE, PageContentType.MIXED)
    assert inspections[1].content_type == PageContentType.SCANNED


def test_inspect_single_page():
    reader = PdfReader(stream=__import__("io").BytesIO(make_pdf(1)))
    result = inspect_page(reader.pages[0], 1)
    assert result.page_number == 1
    assert result.content_type == PageContentType.EMPTY
