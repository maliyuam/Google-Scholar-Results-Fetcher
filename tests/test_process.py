"""Tests for the processing layer. Pure stdlib — no pandas or serpapi needed."""

import json
from pathlib import Path

from scholar_fetcher.process import (
    process_results,
    dedup_results,
    parse_doi,
    _parse_citations,
    FIELDNAMES,
    CITATIONS_OBSERVED,
    CITATIONS_MISSING,
    CITATIONS_UNPARSEABLE,
    DOI_REPORTED,
    DOI_DERIVED,
    DOI_MISSING,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_results.json"

COLUMNS = set(FIELDNAMES)


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _raw(title, authors=(), total=None, doi=None, link="http://example.com/x",
         snippet="s", result_id=None):
    """Build a raw SerpAPI-shaped result."""
    inline = {}
    if total is not None:
        inline["cited_by"] = {"total": total}
    if doi is not None:
        inline["doi"] = doi
    raw = {
        "title": title,
        "publication_info": {"authors": [{"name": n} for n in authors]},
        "inline_links": inline,
        "link": link,
        "snippet": snippet,
    }
    if result_id is not None:
        raw["result_id"] = result_id
    return raw


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


def test_year_is_parsed_from_the_publication_summary():
    """publication_info.summary is the only place SerpAPI puts the year."""
    papers = process_results(_load())
    deep = next(p for p in papers if p["Title"] == "Deep learning")
    assert deep["Year"] == "2015"


def test_year_is_na_when_there_is_no_summary():
    papers = process_results(_load())
    sparse = next(p for p in papers if p["Title"] == "A paper with no citations")
    assert sparse["Year"] == "N/A"


def test_doi_is_na_when_serpapi_omits_it():
    """Observed on a live fetch: SerpAPI returns no doi field at all (0/20)."""
    papers = process_results(_load())
    sparse = next(p for p in papers if p["Title"] == "A paper with no citations")
    assert sparse["DOI"] == "N/A"
    assert sparse["DOI_source"] == DOI_MISSING


def test_record_id_and_source_are_captured():
    papers = process_results(_load())
    deep = next(p for p in papers if p["Title"] == "Deep learning")
    assert deep["Record_id"] == "fixtureDeepLearning1"
    assert deep["Source"] == "scholar"


def test_venue_is_left_unset_rather_than_guessed_from_the_summary():
    """Slicing a journal name out of Scholar's free-text summary is guesswork."""
    papers = process_results(_load())
    assert all(p["Venue"] == "N/A" for p in papers)


# --- DOI parsing (E3) ------------------------------------------------------


def test_reported_doi_wins_and_is_flagged_reported():
    assert parse_doi("10.1145/3641289", "http://x/10.9999/other") == \
        ("10.1145/3641289", DOI_REPORTED)


def test_doi_is_derived_from_a_publisher_url():
    """3 of 20 live Scholar links carried a DOI in the path."""
    for url, expected in [
        ("https://dl.acm.org/doi/abs/10.1145/3641289", "10.1145/3641289"),
        ("https://dl.acm.org/doi/pdf/10.1145/3641289", "10.1145/3641289"),
        ("https://link.springer.com/article/10.1007/s11704-026-60308-3",
         "10.1007/s11704-026-60308-3"),
        ("https://doi.org/10.1038/nature14539", "10.1038/nature14539"),
    ]:
        assert parse_doi(None, url) == (expected, DOI_DERIVED), url


def test_derived_doi_is_never_labelled_reported():
    """A parsed DOI must not pass for one the API actually returned."""
    _, provenance = parse_doi(None, "https://dl.acm.org/doi/abs/10.1145/3641289")
    assert provenance == DOI_DERIVED


def test_url_without_a_doi_yields_missing():
    for url in ["https://arxiv.org/abs/2107.03374", "http://example.com/x", "", None]:
        assert parse_doi(None, url) == ("N/A", DOI_MISSING), url


def test_derived_doi_reaches_the_row():
    papers = process_results([
        _raw("Paper", ["J Smith"], total=5, link="https://dl.acm.org/doi/abs/10.1145/3641289")
    ])
    assert papers[0]["DOI"] == "10.1145/3641289"
    assert papers[0]["DOI_source"] == DOI_DERIVED


# --- record_id dedup (E2) --------------------------------------------------


def test_same_record_id_collapses_even_when_titles_differ():
    """The source's own id is exact; a title typo across pages should not split a work."""
    papers = process_results([
        _raw("Attention is all you need", ["A Vaswani"], total=80000, result_id="abc123"),
        _raw("Attention is all you need.", ["A Vaswani"], total=79000, result_id="abc123"),
    ])
    deduped, dropped = dedup_results(papers)
    assert dropped == 1
    assert deduped[0]["Citations"] == 80000


def test_different_record_ids_do_not_force_a_merge():
    papers = process_results([
        _raw("Alpha", ["A One"], total=5, result_id="id-1"),
        _raw("Beta", ["B Two"], total=3, result_id="id-2"),
    ])
    _, dropped = dedup_results(papers)
    assert dropped == 0


def test_record_id_does_not_merge_across_sources():
    """A Scholar id and an OpenAlex id are different namespaces."""
    a, b = process_results([_raw("Alpha", ["A One"], total=5, result_id="shared")])[0], \
           process_results([_raw("Beta", ["B Two"], total=3, result_id="shared")])[0]
    b["Source"] = "openalex"
    _, dropped = dedup_results([a, b])
    assert dropped == 0


def test_doi_collapses_rows_from_different_sources():
    """The whole point of E1+E3: one work, two sources, one row."""
    scholar = process_results([
        _raw("Deep learning", ["Y LeCun"], total=50000,
             link="https://doi.org/10.1038/nature14539", result_id="s1")
    ])[0]
    openalex = dict(scholar)
    openalex.update({"Source": "openalex", "Record_id": "W123", "Citations": 51000,
                     "Venue": "Nature", "Title": "Deep Learning"})
    deduped, dropped = dedup_results([scholar, openalex])
    assert dropped == 1
    assert deduped[0]["Source"] == "openalex+scholar", "a merged row names both sources"


def test_merged_row_inherits_venue_and_records_it():
    scholar = process_results([_raw("Alpha", ["A One"], total=10, result_id="s1")])[0]
    openalex = dict(scholar)
    openalex.update({"Source": "openalex", "Record_id": "W1", "Citations": 4,
                     "Venue": "Journal of Things"})
    deduped, dropped = dedup_results([scholar, openalex])
    assert dropped == 1
    assert deduped[0]["Citations"] == 10          # scholar wins on count
    assert deduped[0]["Venue"] == "Journal of Things"   # venue came from openalex
    assert "Venue" in deduped[0]["Merged_fields"]


def test_donated_doi_brings_its_provenance_flag_with_it():
    """Inheriting a DOI without its flag would describe a value that is not there."""
    a = process_results([_raw("Alpha", ["A One"], total=10, result_id="s1")])[0]
    b = process_results([
        _raw("Alpha", ["A One"], total=4, result_id="s2",
             link="https://dl.acm.org/doi/abs/10.1145/3641289")
    ])[0]
    deduped, dropped = dedup_results([a, b])
    assert dropped == 1
    assert deduped[0]["DOI"] == "10.1145/3641289"
    assert deduped[0]["DOI_source"] == DOI_DERIVED, "flag must follow the donated value"


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
    """Regression: the DOI-first key put these in different namespaces and never merged them.

    Defensive rather than observed: a live fetch returned no doi field on any of
    20 results, so this asymmetry cannot arise from SerpAPI data as it stands
    today. It would arise the moment a DOI is supplied from anywhere else.
    """
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
