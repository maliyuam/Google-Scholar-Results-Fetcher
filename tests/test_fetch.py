"""Tests for the fetching layer, driven by a fake SerpAPI client.

No network, no API key, no serpapi package: `search_factory` is injected, which
is the only reason this layer is testable at all. Previously it had no tests.
"""

import pytest

from scholar_fetcher.fetch import fetch_google_scholar_results, FetchError

KEY = "sk-secret-key-do-not-leak"


def _page(n, start=0):
    return {"organic_results": [{"title": f"paper {start + i}"} for i in range(n)]}


def scripted(*responses):
    """A search_factory that returns/raises the scripted responses in order.

    Each response is either a dict (returned by get_dict) or an exception
    instance (raised by get_dict). Records the params it was called with.
    """
    calls = []
    queue = list(responses)

    class FakeSearch:
        def __init__(self, params):
            calls.append(params)

        def get_dict(self):
            item = queue.pop(0) if queue else {"organic_results": []}
            if isinstance(item, BaseException):
                raise item
            return item

    FakeSearch.calls = calls
    return FakeSearch


def _fetch(factory, num_results=30, **kw):
    kw.setdefault("sleep_interval", 0)
    return fetch_google_scholar_results(
        "q", num_results, api_key=KEY, search_factory=factory, **kw
    )


# --- the happy path --------------------------------------------------------


def test_paginates_until_target_and_reports_counts():
    report = _fetch(scripted(_page(20), _page(20, 20)), num_results=30)
    assert report.collected == 40
    assert report.requested == 30
    assert report.pages_ok == 2
    assert report.pages_failed == 0
    assert report.complete is True


def test_surplus_is_returned_not_truncated():
    """Truncating here threw away already-paid-for rows before dedup could run."""
    report = _fetch(scripted(_page(20), _page(20, 20)), num_results=25)
    assert report.collected == 40, "rows already fetched must reach the caller"


def test_short_page_ends_pagination():
    report = _fetch(scripted(_page(20), _page(5, 20)), num_results=100)
    assert report.collected == 25
    assert report.pages_ok == 2
    assert report.complete is True


def test_end_of_results_error_is_not_a_failure():
    no_results = {"error": "Google Scholar hasn't returned any results for this query."}
    report = _fetch(scripted(_page(20), no_results), num_results=100)
    assert report.collected == 20
    assert report.pages_failed == 0
    assert report.complete is True


# --- failures must not masquerade as "no more results" ----------------------


def test_exhausted_quota_raises_instead_of_truncating_silently():
    quota = {"error": "You've run out of searches on your current plan."}
    with pytest.raises(FetchError) as excinfo:
        _fetch(scripted(_page(20), quota), num_results=100)
    assert "run out of searches" in str(excinfo.value)


def test_invalid_key_raises():
    bad_key = {"error": "Invalid API key. Your API key should be here: ..."}
    with pytest.raises(FetchError):
        _fetch(scripted(bad_key), num_results=100)


def test_terminal_error_still_hands_back_the_rows_already_paid_for():
    quota = {"error": "You've run out of searches on your current plan."}
    with pytest.raises(FetchError) as excinfo:
        _fetch(scripted(_page(20), quota), num_results=100)
    assert excinfo.value.report.collected == 20


def test_unknown_error_raises_rather_than_truncating():
    """Default to loud: an unrecognised error must never look like end-of-results."""
    with pytest.raises(FetchError):
        _fetch(scripted({"error": "something nobody has seen before"}), num_results=50)


# --- retries ---------------------------------------------------------------


def test_rate_limit_error_is_retried_then_succeeds():
    throttled = {"error": "Your account has been throttled. Too many requests."}
    report = _fetch(scripted(throttled, throttled, _page(5)), num_results=5, retries=3)
    assert report.collected == 5
    assert report.pages_failed == 0


def test_transient_exception_is_retried_then_succeeds():
    report = _fetch(scripted(ConnectionError("boom"), _page(5)), num_results=5, retries=3)
    assert report.collected == 5


def test_page_that_exhausts_retries_is_reported_not_swallowed():
    factory = scripted(_page(20), ConnectionError("x"), ConnectionError("x"), ConnectionError("x"))
    report = _fetch(factory, num_results=100, retries=3)
    assert report.collected == 20
    assert report.pages_failed == 1
    assert report.failed_offsets == [20]
    assert report.complete is False, "a truncated set must not report as complete"


def test_rate_limit_that_never_clears_is_reported_as_a_failed_page():
    throttled = {"error": "Rate limit exceeded, too many requests"}
    report = _fetch(scripted(throttled, throttled, throttled), num_results=50, retries=3)
    assert report.pages_failed == 1
    assert report.complete is False


# --- the key must never be printed -----------------------------------------


def test_api_key_is_never_printed_on_failure(capsys):
    boom = ConnectionError(
        f"HTTPSConnectionPool(host='serpapi.com', port=443): Max retries exceeded "
        f"with url: /search?engine=google_scholar&q=x&api_key={KEY}"
    )
    report = _fetch(scripted(boom, boom, boom), num_results=10, retries=3)
    assert report.pages_failed == 1
    out = capsys.readouterr().out
    assert KEY not in out, "the live API key reached stdout"
    assert "***" in out


def test_progress_callback_receives_collected_and_target():
    seen = []
    _fetch(scripted(_page(20), _page(20, 20)), num_results=30, progress=lambda c, t: seen.append((c, t)))
    assert seen == [(20, 30), (30, 30)]
