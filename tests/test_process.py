"""Tests for the processing layer. Pure stdlib — no pandas or serpapi needed."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scholar_fetcher.process import process_results, dedup_results

FIXTURE = Path(__file__).parent / "fixtures" / "sample_results.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_process_preserves_row_count_and_columns():
    """Faithful: one row per raw result, with the notebook's six columns."""
    papers = process_results(_load())
    assert len(papers) == 4
    assert set(papers[0]) == {"Title", "Authors", "Citations", "URL", "Abstract", "DOI"}


def test_authors_are_joined_and_citations_are_int():
    papers = process_results(_load())
    deep = next(p for p in papers if p["Title"] == "Deep learning")
    assert deep["Authors"] == "Y LeCun, Y Bengio"
    assert deep["Citations"] == 50000
    assert isinstance(deep["Citations"], int)


def test_missing_citations_becomes_zero():
    papers = process_results(_load())
    empty = next(p for p in papers if p["Title"] == "A paper with no citations")
    assert empty["Citations"] == 0
    assert empty["DOI"] == "N/A"


def test_dedup_drops_duplicate_title_keeping_highest_citations():
    """'Deep learning' and 'Deep Learning' collapse; the 50000 copy wins."""
    papers = process_results(_load())
    deduped, dropped = dedup_results(papers)
    assert dropped == 1
    assert len(deduped) == 3
    deep = next(p for p in deduped if p["Title"].lower() == "deep learning")
    assert deep["Citations"] == 50000  # kept the higher-cited copy, not the 49000 reprint
