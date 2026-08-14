"""Tests for the processing layer. Pure stdlib — no pandas or serpapi needed."""

import json
from pathlib import Path

from scholar_fetcher.process import (
    process_results,
    dedup_results,
    _parse_citations,
    CITATIONS_OBSERVED,
    CITATIONS_MISSING,
    CITATIONS_UNPARSEABLE,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_results.json"

COLUMNS = {
    "Title",
    "Authors",
    "Year",
    "Citations",
    "Citations_source",
    "URL",
    "Snippet",
    "DOI",
    "Merged_fields",
}


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _raw(title, authors=(), total=None, doi=None, link="http://example.com/x", snippet="s"):
    """Build a raw SerpAPI-shaped result."""
    inline = {}
    if total is not None:
        inline["cited_by"] = {"total": total}
    if doi is not None:
        inline["doi"] = doi
    return {
        "title": title,
        "publication_info": {"authors": [{"name": n} for n in authors]},
        "inline_links": inline,
        "link": link,
        "snippet": snippet,
    }


# --- process_results -------------------------------------------------------


def test_process_preserves_row_count_and_columns():
    """One row per raw result, with the documented column set."""
    papers = process_results(_load())
    assert len(papers) == 5
    assert set(papers[0]) == COLUMNS


def test_authors_are_joined_and_citations_are_int():
    papers = process_results(_load())
    deep = next(p for p in papers if p["Title"] == "Deep learning")
    assert deep["Authors"] == "Y LeCun, Y Bengio"
    assert deep["Citations"] == 50000
    assert deep["Citations_source"] == CITATIONS_OBSERVED


def test_absent_citations_are_none_and_flagged_not_imputed_to_zero():
    """A missing count must stay distinguishable from an observed zero."""
    papers = process_results(_load())
    empty = next(p for p in papers if p["Title"] == "A paper with no citations")
    assert empty["Citations"] is None
    assert empty["Citations_source"] == CITATIONS_MISSING
    assert empty["DOI"] == "N/A"


def test_thousands_separated_count_is_parsed_not_zeroed():
    assert _parse_citations("1,234") == (1234, CITATIONS_OBSERVED)
    assert _parse_citations(1234) == (1234, CITATIONS_OBSERVED)


def test_unparseable_count_is_flagged_never_fabricated_as_zero():
    for value in ("2.5k", "many", "12 citations"):
        count, source = _parse_citations(value)
        assert count is None, f"{value!r} must not become a number"
        assert source == CITATIONS_UNPARSEABLE


def test_observed_zero_is_distinguishable_from_missing():
    assert _parse_citations(0) == (0, CITATIONS_OBSERVED)
    assert _parse_citations(None) == (None, CITATIONS_MISSING)


def test_json_null_blocks_do_not_destroy_the_batch():
    """A null publication_info/inline_links used to raise and lose every row."""
    raw = [
        {"title": "T", "publication_info": None, "inline_links": None,
         "link": None, "snippet": None},
        _raw("Survivor", ["A One"], total=3),
    ]
    papers = process_results(raw)
    assert len(papers) == 2
    assert papers[0]["Authors"] == ""
    assert papers[0]["URL"] == "N/A"
    assert papers[1]["Title"] == "Survivor"


def test_author_without_a_name_is_dropped_not_named_na():
    raw = [{"title": "T", "publication_info": {"authors": [{"nome": "typo"}, {"name": "R Real"}]},
            "inline_links": {}, "link": "u", "snippet": "s"}]
    assert process_results(raw)[0]["Authors"] == "R Real"


# --- dedup_results ---------------------------------------------------------


def test_dedup_collapses_case_variant_title_keeping_highest_citations():
    papers = process_results(_load())
    deduped, dropped = dedup_results(papers)
    deep = next(p for p in deduped if p["Title"].lower() == "deep learning")
    assert deep["Citations"] == 50000  # kept the higher-cited copy, not the 49000 reprint
    assert dropped == 2
    assert len(deduped) == 3


def test_dedup_collapses_when_only_one_copy_carries_a_doi():
    """Regression: the DOI-first key put these in different namespaces and never merged them."""
    papers = process_results(_load())
    deduped, _ = dedup_results(papers)
    attention = [p for p in deduped if "attention" in p["Title"].lower()]
    assert len(attention) == 1, "the doi-bearing and doi-less copies must collapse"
    assert attention[0]["Citations"] == 80000


def test_dedup_carries_the_doi_over_from_the_dropped_copy():
    """The survivor is the doi-less copy; the DOI must not be lost with the loser."""
    papers = process_results([
        _raw("Same work", ["J Smith"], total=100),
        _raw("Same work", ["J Smith"], total=90, doi="10.1000/real"),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 1
    assert deduped[0]["Citations"] == 100
    assert deduped[0]["DOI"] == "10.1000/real"
    assert "DOI" in deduped[0]["Merged_fields"]


def test_dedup_keeps_distinct_works_that_merely_share_a_title():
    """Different authors, same generic title — collapsing these deletes a real record."""
    papers = process_results([
        _raw("Introduction", ["A One"], total=10),
        _raw("Introduction", ["B Two"], total=3),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 0
    assert len(deduped) == 2


def test_dedup_keeps_distinct_works_with_conflicting_dois():
    papers = process_results([
        _raw("Same title", ["J Smith"], total=10, doi="10.1000/aaa"),
        _raw("Same title", ["J Smith"], total=3, doi="10.1000/bbb"),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 0
    assert len(deduped) == 2


def test_dedup_does_not_merge_non_latin_titles_into_one_row():
    """[^a-z0-9] normalized every CJK/Cyrillic title to the same empty key."""
    papers = process_results([
        _raw("深度学习", ["A One"], total=10),
        _raw("Глубокое обучение", ["B Two"], total=8),
        _raw("التعلم العميق", ["C Three"], total=6),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 0
    assert len(deduped) == 3


def test_dedup_collapses_a_non_latin_title_with_itself():
    papers = process_results([
        _raw("深度学习", ["A One"], total=10),
        _raw("深度学习", ["A One"], total=12),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 1
    assert deduped[0]["Citations"] == 12


def test_dedup_never_merges_rows_whose_title_is_unusable():
    """Title 'N/A' or all-punctuation must not become one shared key."""
    papers = process_results([
        _raw("N/A", ["A One"], total=1),
        _raw("N/A", ["B Two"], total=2),
        _raw("!!!", ["C Three"], total=3),
        _raw("???", ["D Four"], total=4),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 0
    assert len(deduped) == 4


def test_dedup_preserves_first_appearance_order():
    papers = process_results([
        _raw("Zebra", ["A One"], total=1),
        _raw("Apple", ["B Two"], total=99),
        _raw("Zebra", ["A One"], total=5),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 1
    assert [p["Title"] for p in deduped] == ["Zebra", "Apple"]


def test_dedup_prefers_an_observed_count_over_a_missing_one():
    """A row whose count is missing must never win the tie-break against an observed one."""
    papers = process_results([
        _raw("Shared work", ["J Smith"]),                 # no cited_by at all
        _raw("Shared work", ["J Smith"], total=7),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 1
    assert deduped[0]["Citations"] == 7
