"""Tests for the OpenAlex source. No network: `http` is injected."""

import json

import pytest

from scholar_fetcher.openalex import (
    fetch_openalex_results,
    normalize_openalex_results,
    reconstruct_abstract,
)
from scholar_fetcher.report import FetchError


def _work(idx, doi="10.1000/x", venue="Journal of Things", year=2020, cites=10):
    return {
        "id": f"https://openalex.org/W{idx}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": f"Work {idx}",
        "publication_year": year,
        "cited_by_count": cites,
        "authorships": [{"author": {"display_name": "J Smith"}},
                        {"author": {"display_name": "A Jones"}}],
        "primary_location": {"source": {"display_name": venue},
                             "landing_page_url": f"http://example.com/{idx}"},
        "open_access": {"is_oa": True, "oa_url": f"http://example.com/{idx}.pdf"},
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
    }


def _page(works, next_cursor=None):
    return json.dumps({
        "meta": {"count": len(works), "next_cursor": next_cursor},
        "results": works,
    }).encode("utf-8")


def scripted(*responses):
    """An `http` callable returning scripted (status, body) pairs, or raising."""
    queue = list(responses)
    calls = []

    def http(url, timeout=30):
        calls.append(url)
        item = queue.pop(0) if queue else (200, _page([]))
        if isinstance(item, BaseException):
            raise item
        return item

    http.calls = calls
    return http


# --- pagination and reporting ----------------------------------------------


def test_collects_across_pages_and_reports_counts():
    http = scripted(
        (200, _page([_work(i) for i in range(200)], next_cursor="c2")),
        (200, _page([_work(i) for i in range(200, 250)])),
    )
    report = fetch_openalex_results("q", 250, http=http, sleep_interval=0)
    assert report.collected == 250
    assert report.requested == 250
    assert report.pages_ok == 2
    assert report.complete is True
    assert report.source == "openalex"


def test_stops_when_the_cursor_runs_out():
    http = scripted((200, _page([_work(1), _work(2)], next_cursor=None)))
    report = fetch_openalex_results("q", 100, http=http, sleep_interval=0)
    assert report.collected == 2
    assert report.complete is True


def test_empty_result_set_is_not_a_failure():
    report = fetch_openalex_results("q", 50, http=scripted((200, _page([]))), sleep_interval=0)
    assert report.collected == 0
    assert report.pages_failed == 0


def test_polite_pool_mailto_is_sent_when_given():
    http = scripted((200, _page([_work(1)])))
    fetch_openalex_results("q", 1, http=http, mailto="me@uni.edu", sleep_interval=0)
    assert "mailto=me%40uni.edu" in http.calls[0]


# --- search field ----------------------------------------------------------


def test_default_search_is_title_and_abstract_not_fulltext():
    """Generic fulltext search returned 'R: A Language and Environment for
    Statistical Computing' as the top hit for 'large language models
    evaluation'. Title+abstract is what bibliographic databases search."""
    http = scripted((200, _page([_work(1)])))
    fetch_openalex_results("large language models", 1, http=http, sleep_interval=0)
    assert "title_and_abstract.search" in http.calls[0]
    assert "search=large" not in http.calls[0]


def test_fulltext_search_field_uses_the_generic_search_param():
    http = scripted((200, _page([_work(1)])))
    fetch_openalex_results("q", 1, http=http, search_field="fulltext", sleep_interval=0)
    assert "search=q" in http.calls[0]
    assert "title_and_abstract" not in http.calls[0]


def test_tolerates_options_meant_for_another_source():
    """The mirror of the Scholar test: one kwarg set reaches every source."""
    http = scripted((200, _page([_work(1)])))
    report = fetch_openalex_results("q", 1, http=http, sleep_interval=0,
                                    api_key="serpapi-key", page_size=20)
    assert report.collected == 1


def test_unknown_search_field_is_rejected_loudly():
    with pytest.raises(ValueError, match="search_field"):
        fetch_openalex_results("q", 1, http=scripted((200, _page([]))),
                               search_field="everywhere")


def test_per_page_is_capped_at_the_api_maximum():
    http = scripted((200, _page([_work(1)])))
    fetch_openalex_results("q", 5000, http=http, per_page=100_000, sleep_interval=0)
    assert "per-page=200" in http.calls[0]


# --- failures --------------------------------------------------------------


def test_rate_limit_is_retried_then_succeeds():
    http = scripted((429, b""), (429, b""), (200, _page([_work(1)])))
    report = fetch_openalex_results("q", 1, http=http, retries=3, sleep_interval=0)
    assert report.collected == 1
    assert report.pages_failed == 0


def test_persistent_rate_limit_is_reported_not_swallowed():
    http = scripted((429, b""), (429, b""), (429, b""))
    report = fetch_openalex_results("q", 50, http=http, retries=3, sleep_interval=0)
    assert report.pages_failed == 1
    assert report.complete is False, "a truncated corpus must not report as complete"


def test_transport_error_is_retried_then_succeeds():
    http = scripted(ConnectionError("dns"), (200, _page([_work(1)])))
    report = fetch_openalex_results("q", 1, http=http, retries=3, sleep_interval=0)
    assert report.collected == 1


def test_blocked_client_raises_rather_than_looking_like_no_results():
    with pytest.raises(FetchError) as excinfo:
        fetch_openalex_results("q", 50, http=scripted((403, b"")), sleep_interval=0)
    assert "403" in str(excinfo.value)
    assert "polite pool" in str(excinfo.value)


def test_bad_query_raises_and_carries_partial_results():
    http = scripted((200, _page([_work(1)], next_cursor="c2")), (400, b""))
    with pytest.raises(FetchError) as excinfo:
        fetch_openalex_results("q", 500, http=http, sleep_interval=0)
    assert excinfo.value.report.collected == 1


def test_two_hundred_that_is_not_json_is_treated_as_a_failed_page():
    """An outage or proxy page returns 200 with HTML. That is not data."""
    html = b"<html>maintenance</html>"
    report = fetch_openalex_results("q", 50, http=scripted((200, html), (200, html), (200, html)),
                                    retries=3, sleep_interval=0)
    assert report.pages_failed == 1
    assert report.complete is False


# --- abstract reconstruction -----------------------------------------------


def test_reconstructs_an_abstract_from_the_inverted_index():
    inverted = {"Deep": [0], "learning": [1], "is": [2], "useful": [3]}
    assert reconstruct_abstract(inverted) == "Deep learning is useful"


def test_reconstructs_repeated_words_at_every_position():
    inverted = {"the": [0, 2], "cat": [1], "hat": [3]}
    assert reconstruct_abstract(inverted) == "the cat the hat"


def test_absent_abstract_is_none_not_empty_string():
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


# --- normalization ---------------------------------------------------------


def test_normalize_populates_the_fields_scholar_cannot():
    row = normalize_openalex_results([_work(1, doi="10.1038/nature14539",
                                            venue="Nature", year=2015, cites=50000)])[0]
    assert row["Source"] == "openalex"
    assert row["Record_id"] == "W1"
    assert row["Title"] == "Work 1"
    assert row["Authors"] == "J Smith, A Jones"
    assert row["Year"] == "2015"
    assert row["Venue"] == "Nature"
    assert row["Citations"] == 50000
    assert row["Citations_source"] == "observed"
    assert row["Snippet"] == "Hello world"


def test_doi_url_is_stored_bare_and_flagged_reported():
    row = normalize_openalex_results([_work(1, doi="10.1038/nature14539")])[0]
    assert row["DOI"] == "10.1038/nature14539"
    assert row["DOI_source"] == "reported"


def test_missing_optional_blocks_do_not_raise():
    """OpenAlex omits whole blocks for sparse records."""
    sparse = {"id": "https://openalex.org/W9", "title": "Sparse",
              "publication_year": None, "cited_by_count": None,
              "authorships": None, "primary_location": None,
              "open_access": None, "abstract_inverted_index": None, "doi": None}
    row = normalize_openalex_results([sparse])[0]
    assert row["Title"] == "Sparse"
    assert row["Authors"] == ""
    assert row["Year"] == "N/A"
    assert row["Venue"] == "N/A"
    assert row["Citations"] is None
    assert row["Citations_source"] == "missing"
    assert row["DOI"] == "N/A"


def test_zero_citations_is_observed_not_missing():
    row = normalize_openalex_results([_work(1, cites=0)])[0]
    assert row["Citations"] == 0
    assert row["Citations_source"] == "observed"


def test_prefers_an_open_access_link_the_reader_can_open():
    row = normalize_openalex_results([_work(7)])[0]
    assert row["URL"] == "http://example.com/7.pdf"


def test_markup_in_publisher_metadata_is_stripped():
    """Observed live: 'Fitting Linear Mixed-Effects Models Using <b>lme4</b>'."""
    work = _work(1)
    work["title"] = "Fitting Linear Mixed-Effects Models Using <b>lme4</b>"
    work["primary_location"]["source"]["display_name"] = "Journal of <i>Stats</i>"
    row = normalize_openalex_results([work])[0]
    assert row["Title"] == "Fitting Linear Mixed-Effects Models Using lme4"
    assert row["Venue"] == "Journal of Stats"


def test_html_entities_are_resolved():
    work = _work(1)
    work["title"] = "Tea &amp; Coffee: a review of &lt;5 studies"
    row = normalize_openalex_results([work])[0]
    assert row["Title"] == "Tea & Coffee: a review of <5 studies"
