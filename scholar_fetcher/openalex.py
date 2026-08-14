"""OpenAlex source.

OpenAlex is a free, CC0-licensed catalogue of scholarly works. It matters here
for three reasons Google Scholar cannot match:

  * It reports DOI, venue, year, and open-access status. Scholar returns none of
    these (a live Scholar fetch of 20 results carried zero DOIs), which is why a
    Scholar-only BibTeX entry is an undated `@article` with no journal.
  * Its API is documented and stable, so the same query returns the same set.
    Scholar's ranking is neither, which is the reason it is not accepted as a
    primary source for a reproducible search.
  * It is not a scraper, so it carries none of the access risk that comes with
    routing Scholar through a third party.

Uses urllib from the standard library on purpose: the package stays installable
without a HTTP dependency, and the test suite keeps running with no network.

Rate limits: the free tier is generous but asks that you identify yourself. Pass
`mailto=` (or set OPENALEX_MAILTO) to join the polite pool. As of February 2026
high-volume use moved to usage-based pricing; single-record lookups stay free.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .process import (
    blank_row, clean_text, is_person_name, _parse_citations, parse_doi, MISSING,
)
from .report import FetchReport, FetchError

SOURCE_NAME = "openalex"

API_ROOT = "https://api.openalex.org/works"
MAX_PER_PAGE = 200          # OpenAlex caps per-page at 200
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Where to look for the query terms.
#   title-abstract: the field pair every bibliographic database searches by
#     default (PubMed's [tiab], Scopus's TITLE-ABS). Precise.
#   fulltext: OpenAlex's generic `search`, which also matches indexed full text.
#     Recall is higher and precision is much lower: searching
#     "large language models evaluation" this way returns "R: A Language and
#     Environment for Statistical Computing" as the top hit, because the words
#     match separately somewhere in the text.
SEARCH_FIELDS = ("title-abstract", "fulltext")
DEFAULT_SEARCH_FIELD = "title-abstract"
USER_AGENT = "scholar-fetcher (https://github.com/maliyuam/scholar-fetcher)"

# Status codes worth another attempt. 403 is terminal: OpenAlex uses it for a
# blocked or over-quota client, and hammering it makes that worse.
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _default_http(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, bytes]:
    """Return (status, body). An HTTP error status is data, not an exception.

    Only a transport failure (DNS, refused, timeout) raises, which is what the
    retry loop treats as transient.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _build_url(query: str, per_page: int, cursor: str, mailto: str | None,
               search_field: str = DEFAULT_SEARCH_FIELD) -> str:
    params = {"per-page": str(per_page), "cursor": cursor}

    if search_field == "fulltext":
        params["search"] = query
    else:
        # A .search filter makes OpenAlex sort by relevance automatically.
        params["filter"] = f"title_and_abstract.search:{query}"

    if mailto:
        params["mailto"] = mailto
    return f"{API_ROOT}?{urllib.parse.urlencode(params)}"


def fetch_openalex_results(
    query: str,
    num_results: int,
    *,
    per_page: int = MAX_PER_PAGE,
    retries: int = DEFAULT_RETRIES,
    sleep_interval: int = 0,
    mailto: str | None = None,
    search_field: str = DEFAULT_SEARCH_FIELD,
    progress: Callable[[int, int], None] | None = None,
    http: Callable[[str], tuple[int, bytes]] | None = None,
    **_ignored,
) -> FetchReport:
    """Fetch at least `num_results` works from OpenAlex.

    Pages are collected whole and returned whole; truncation happens downstream,
    after deduplication, so already-fetched rows can backfill what dedup removes.

    Args:
        query: free-text search, passed to OpenAlex's `search` parameter.
        num_results: how many works to collect before stopping.
        per_page: results per request (OpenAlex caps at 200).
        retries: attempts per page before that page is recorded as failed.
        sleep_interval: seconds between pages, and the retry backoff unit.
        mailto: contact address for the polite pool. Falls back to OPENALEX_MAILTO.
        search_field: 'title-abstract' (default, precise) or 'fulltext' (higher
            recall, much lower precision).
        progress: optional callback(collected, target) for UIs.
        http: injection point for tests; defaults to urllib.

    Returns:
        FetchReport with the raw work dicts and the run's counts.

    Raises:
        FetchError: on a failure retrying cannot fix. Partial results attached.
    """
    http = http or _default_http
    mailto = mailto or os.getenv("OPENALEX_MAILTO") or None
    per_page = max(1, min(per_page, MAX_PER_PAGE))
    if search_field not in SEARCH_FIELDS:
        raise ValueError(
            f"search_field must be one of {SEARCH_FIELDS}, got {search_field!r}"
        )

    report = FetchReport(requested=num_results, source=SOURCE_NAME)
    cursor = "*"
    page_index = 0

    while report.collected < num_results and cursor:
        url = _build_url(query, min(per_page, num_results - report.collected), cursor,
                         mailto, search_field)
        payload = _fetch_page(http, url, retries, sleep_interval, page_index, report)
        if payload is None:
            break

        works = payload.get("results") or []
        if not works:
            break

        report.results.extend(works)
        report.pages_ok += 1
        if progress:
            progress(min(report.collected, num_results), num_results)

        cursor = (payload.get("meta") or {}).get("next_cursor")
        page_index += 1
        if cursor and report.collected < num_results:
            time.sleep(sleep_interval)

    return report


def _fetch_page(http, url, retries, sleep_interval, page_index, report):
    """Fetch one page. Returns the decoded payload, or None to stop paginating."""
    for attempt in range(1, retries + 1):
        try:
            status, body = http(url)
        except Exception as exc:                      # transport-level failure
            if attempt == retries:
                print(f"OpenAlex page {page_index} failed after {retries} attempts: "
                      f"{type(exc).__name__}: {exc}")
                report.pages_failed += 1
                report.failed_offsets.append(page_index)
                return None
            time.sleep(sleep_interval * attempt)
            continue

        if status == 200:
            try:
                return json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                # A 200 that is not JSON is a proxy or outage page, not data.
                if attempt == retries:
                    print(f"OpenAlex page {page_index} returned unreadable JSON: {exc}")
                    report.pages_failed += 1
                    report.failed_offsets.append(page_index)
                    return None
                time.sleep(sleep_interval * attempt)
                continue

        if status in _RETRYABLE_STATUS:
            if attempt == retries:
                print(f"OpenAlex page {page_index} still failing with HTTP {status} "
                      f"after {retries} attempts")
                report.pages_failed += 1
                report.failed_offsets.append(page_index)
                return None
            time.sleep(sleep_interval * attempt)
            continue

        # Anything else (400 bad query, 401, 403 blocked) will not fix itself.
        raise FetchError(
            f"OpenAlex returned HTTP {status} for page {page_index}. "
            f"{_hint_for_status(status)}",
            report,
        )

    return None


def _hint_for_status(status: int) -> str:
    return {
        400: "The query was rejected; check the search syntax.",
        401: "Authentication was rejected.",
        403: "Blocked or over quota. Set a mailto= address to join the polite pool.",
        404: "Endpoint not found.",
    }.get(status, "This is not a transient error, so it was not retried.")


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild an abstract from OpenAlex's inverted index.

    OpenAlex stores abstracts as {word: [positions]} rather than as text, for
    licensing reasons. Inverting it back is lossy in punctuation but gives a real
    abstract, which is strictly more than Scholar's truncated snippet.
    """
    if not inverted_index:
        return None

    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for position in positions or []:
            positioned.append((position, word))

    if not positioned:
        return None

    positioned.sort(key=lambda pair: pair[0])
    return " ".join(word for _, word in positioned)


def normalize_openalex_results(results: list[dict]) -> list[dict]:
    """Flatten raw OpenAlex works into rows, one row per work."""
    rows = []
    for work in results:
        row = blank_row()
        row["Source"] = SOURCE_NAME

        # OpenAlex ids are full URLs (https://openalex.org/W123). Keep the short
        # form: it is what people paste into the API and into papers.
        work_id = work.get("id") or ""
        row["Record_id"] = work_id.rsplit("/", 1)[-1] if work_id else MISSING

        # Publisher metadata carries markup: a live fetch returned the title
        # "Fitting Linear Mixed-Effects Models Using <b>lme4</b>".
        row["Title"] = clean_text(work.get("title") or work.get("display_name")) or MISSING

        authorships = work.get("authorships") or []
        names = []
        for authorship in authorships:
            author = (authorship or {}).get("author") or {}
            name = clean_text(author.get("display_name"))
            # OpenAlex occasionally reports a footnote marker as the whole author
            # list; "†" must not become an author in a citation record.
            if name and is_person_name(name):
                names.append(name)
        row["Authors"] = ", ".join(names)

        year = work.get("publication_year")
        row["Year"] = str(year) if year else MISSING

        location = work.get("primary_location") or {}
        venue = (location.get("source") or {}).get("display_name")
        row["Venue"] = clean_text(venue) or MISSING

        row["Citations"], row["Citations_source"] = _parse_citations(work.get("cited_by_count"))

        # Prefer an open-access link the reader can actually open.
        open_access = work.get("open_access") or {}
        best = work.get("best_oa_location") or {}
        row["URL"] = (
            best.get("pdf_url")
            or open_access.get("oa_url")
            or location.get("landing_page_url")
            or work.get("doi")
            or MISSING
        )

        abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
        row["Snippet"] = clean_text(abstract) or MISSING

        # OpenAlex reports the DOI as a URL; parse_doi strips it back to bare form.
        row["DOI"], row["DOI_source"] = parse_doi(work.get("doi"), row["URL"])

        rows.append(row)
    return rows
