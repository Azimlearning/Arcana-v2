import pytest

from api.ingestion.chunk import chunk
from api.ingestion.types import PageText


def pages(*texts: str) -> list[PageText]:
    return [PageText(page=i + 1, text=t) for i, t in enumerate(texts)]


def test_empty_and_whitespace_input_gives_no_chunks():
    assert chunk([], doc_id="d") == []
    assert chunk(pages("   \n\n  "), doc_id="d") == []


def test_short_text_is_one_chunk():
    result = chunk(pages("Just a short page."), doc_id="d")
    assert len(result) == 1 and result[0].text == "Just a short page." and result[0].page == 1


def test_window_size_and_overlap_hold():
    text = "x" * 3000  # no boundaries anywhere: hard cuts at exactly 1200 with 200 carried over
    result = chunk(pages(text), doc_id="d")
    assert [len(c.text) for c in result] == [1200, 1200, 1000]  # starts at 0, 1000, 2000
    assert [c.ordinal for c in result] == [0, 1, 2]


def test_prefers_a_paragraph_boundary_near_the_window_end():
    text = ("a" * 1100) + "\n\n" + ("b" * 1100)
    first = chunk(pages(text), doc_id="d")[0]
    assert first.text == "a" * 1100


def test_chunk_records_the_page_it_starts_on():
    result = chunk(pages("p" * 900, "q" * 900, "r" * 900), doc_id="d")
    pages_seen = {c.page for c in result if c.page is not None}
    assert result[0].page == 1 and pages_seen <= {1, 2, 3}
    assert max(pages_seen) >= 2  # later chunks start on later pages


def test_ids_are_deterministic_per_document_and_distinct_per_position():
    a = chunk(pages("same " * 600), doc_id="d1")
    b = chunk(pages("same " * 600), doc_id="d1")
    other = chunk(pages("same " * 600), doc_id="d2")
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)
    assert not set(c.id for c in a) & set(c.id for c in other)


@pytest.mark.parametrize(("target", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_window_settings_are_rejected(target: int, overlap: int):
    with pytest.raises(ValueError):
        chunk(pages("text"), doc_id="d", target_chars=target, overlap_chars=overlap)
