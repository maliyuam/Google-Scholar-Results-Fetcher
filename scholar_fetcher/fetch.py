"""Fetching layer — cell 4 of the notebook, made honest about failure.

The notebook, and the first version of this module, collapsed every outcome into
"stop paginating": a network error, an exhausted API quota, an invalid key and a
genuinely empty last page all produced the same short list, with no way for the
caller to tell a complete corpus from a truncated one.

SerpAPI reports most failures as HTTP 200 with an `error` key in the JSON body,
so they never raised and were never retried. Here the error string is classified:

  * end of results  -> stop quietly, the corpus is complete
  * retryable       -> retry with backoff (rate limits, throttling, 5xx)
  * terminal        -> raise FetchError (bad key, exhausted plan) — never truncate
  * unrecognised    -> treated as terminal, because guessing "end of results"
                       is what silently lost rows in the first place

Every call returns a FetchReport, so the caller can always say how many results
were requested, how many arrived, and how many pages were lost.
"""

import re
import time
from typing import Callable

from .config import get_api_key, PAGE_SIZE, DEFAULT_SLEEP, DEFAULT_RETRIES
from .process import blank_row, clean_text, _parse_citations, parse_doi, MISSING
from .report import FetchReport, FetchError  # re-exported: callers import them from here

SOURCE_NAME = "scholar"

# SerpAPI puts venue and year in publication_info.summary, e.g.
# "Y LeCun, Y Bengio, G Hinton - nature, 2015 - nature.com".
_YEAR = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")

# SerpAPI's own wording for "your query simply has no more hits".
_END_OF_RESULTS = re.compile(
    r"(hasn't|has not) returned any results|no results found", re.I
)
_RETRYABLE = re.compile(
    r"rate limit|too many requests|throttl|timed? ?out|temporarily|"
    r"try again|\b(429|500|502|503|504)\b",
    re.I,
)
_API_KEY_IN_URL = re.compile(r"(api_key=)[^&\s]+")


def normalize_scholar_results(results: list[dict]) -> list[dict]:
    """Flatten raw SerpAPI Google Scholar results into rows, one row per result."""
    rows = []
    for result in results:
        # `or {}` rather than .get(k, {}): SerpAPI sends JSON null for an absent
        # block, and null would sail past a default and blow up on .get below.
        publication_info = result.get("publication_info") or {}
        inline_links = result.get("inline_links") or {}
        cited_by = inline_links.get("cited_by") or {}

        row = blank_row()
        row["Source"] = SOURCE_NAME
        row["Record_id"] = result.get("result_id") or MISSING
        row["Title"] = clean_text(result.get("title")) or MISSING

        authors = publication_info.get("authors") or []
        names = (clean_text(a.get("name")) for a in authors if isinstance(a, dict))
        row["Authors"] = ", ".join(name for name in names if name)

        year = _YEAR.search(publication_info.get("summary") or "")
        row["Year"] = year.group(1) if year else MISSING

        # Venue is left unset on purpose. Scholar only gives a free-text summary
        # ("A Vaswani... - Advances in neural ..., 2017 - papers.nips.cc"), and
        # slicing a journal name out of that is guesswork. OpenAlex reports it
        # properly; guessing here would put an unflagged inference in the data.

        row["Citations"], row["Citations_source"] = _parse_citations(cited_by.get("total"))
        row["URL"] = result.get("link") or MISSING
        row["Snippet"] = result.get("snippet") or MISSING
        # Scholar has never been observed to return a doi field; the derived
        # branch of parse_doi is what actually populates this column.
        row["DOI"], row["DOI_source"] = parse_doi(inline_links.get("doi"), result.get("link"))

        rows.append(row)
    return rows


def _redact(text: str, key: str | None) -> str:
    """Strip the API key out of anything that might be printed or logged.

    The key travels in the request query string, and requests/urllib3 put the
    full URL in their exception messages.
    """
    text = _API_KEY_IN_URL.sub(r"\1***", text)
    return text.replace(key, "***") if key else text


def fetch_google_scholar_results(
    query: str,
    num_results: int,
    *,
    sleep_interval: int = DEFAULT_SLEEP,
    retries: int = DEFAULT_RETRIES,
    page_size: int = PAGE_SIZE,
    api_key: str | None = None,
    progress: Callable[[int, int], None] | None = None,
    search_factory: Callable[[dict], object] | None = None,
    **_ignored,
) -> FetchReport:
    """Fetch at least `num_results` Google Scholar results via SerpAPI.

    Pages are collected whole and returned whole — the surplus past `num_results`
    is deliberately NOT truncated here, so a caller that deduplicates can backfill
    from rows already fetched instead of paying for them again. Truncate last.

    Args:
        query: the search query.
        num_results: how many results to collect before stopping.
        sleep_interval: seconds between pages (rate-limit courtesy); also the
            backoff unit between retries.
        retries: attempts per page before that page is recorded as failed.
        page_size: results per page (SerpAPI caps Google Scholar at 20).
        api_key: override; otherwise loaded from env/.env.
        progress: optional callback(collected, target) for UIs.
        search_factory: injection point for tests; defaults to serpapi's GoogleSearch.
        **_ignored: options meant for another source. `sources.search` hands one
            kwarg set to every source, so each must tolerate the others' options.

    Returns:
        FetchReport with the raw result dicts and the run's counts.

    Raises:
        FetchError: on a failure that retrying cannot fix. The partial results
            are attached as `.report`.
    """
    if search_factory is None:
        from serpapi.google_search import GoogleSearch  # here so tests need no serpapi

        search_factory = GoogleSearch

    key = api_key or get_api_key()
    report = FetchReport(requested=num_results, source=SOURCE_NAME)
    start = 0

    while report.collected < num_results:
        params = {
            "engine": "google_scholar",
            "q": query,
            "api_key": key,
            "start": start,
            "num": page_size,
        }

        organic = _fetch_page(search_factory, params, retries, sleep_interval, key, report)
        if organic is None:          # page lost or end of results; both already recorded
            break

        report.results.extend(organic)
        report.pages_ok += 1
        if progress:
            progress(min(report.collected, num_results), num_results)

        if len(organic) < page_size:
            break                    # last page reached

        start += page_size
        time.sleep(sleep_interval)

    return report


def _fetch_page(search_factory, params, retries, sleep_interval, key, report):
    """Fetch one page. Returns its organic_results, or None to stop paginating.

    Records a lost page on `report`; raises FetchError for terminal failures.
    """
    start = params["start"]

    for attempt in range(1, retries + 1):
        try:
            results = search_factory(params).get_dict()
        except Exception as exc:
            if attempt == retries:
                print(
                    f"Page starting at {start} failed after {retries} attempts: "
                    f"{type(exc).__name__}: {_redact(str(exc), key)}"
                )
                report.pages_failed += 1
                report.failed_offsets.append(start)
                return None
            time.sleep(sleep_interval * attempt)
            continue

        error = results.get("error")
        if not error:
            return results.get("organic_results") or []

        if _END_OF_RESULTS.search(error):
            return None                      # a complete corpus, not a failure

        if _RETRYABLE.search(error):
            if attempt == retries:
                print(
                    f"Page starting at {start} still rate-limited after {retries} "
                    f"attempts: {_redact(error, key)}"
                )
                report.pages_failed += 1
                report.failed_offsets.append(start)
                return None
            time.sleep(sleep_interval * attempt)
            continue

        # Unrecognised errors are terminal on purpose: assuming "end of results"
        # is exactly how an exhausted quota used to pass for a finished search.
        raise FetchError(
            f"SerpAPI returned an error at offset {start}: {_redact(error, key)}", report
        )

    return None
