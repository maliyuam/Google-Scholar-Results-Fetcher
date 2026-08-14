"""Fetching layer — cell 4 of the notebook, made resilient.

Changes from the notebook:
  * page size and sleep are configurable (defaults match the notebook)
  * each page is retried with backoff, so one transient failure no longer
    silently truncates the whole result set
  * an optional progress callback lets a GUI show live progress
"""

import time
from typing import Callable

from .config import get_api_key, PAGE_SIZE, DEFAULT_SLEEP, DEFAULT_RETRIES


def fetch_google_scholar_results(
    query: str,
    num_results: int,
    *,
    sleep_interval: int = DEFAULT_SLEEP,
    retries: int = DEFAULT_RETRIES,
    page_size: int = PAGE_SIZE,
    api_key: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Fetch up to `num_results` Google Scholar results via SerpAPI.

    Args:
        query: the search query.
        num_results: how many results to collect.
        sleep_interval: seconds to wait between pages (rate-limit courtesy).
        retries: attempts per page before giving up on that page.
        page_size: results per page (SerpAPI caps Google Scholar at 20).
        api_key: override; otherwise loaded from env/.env.
        progress: optional callback(collected, target) for UIs.

    Returns:
        A list of raw result dicts (organic_results), at most `num_results` long.
    """
    from serpapi.google_search import GoogleSearch  # imported here so tests need no serpapi

    key = api_key or get_api_key()
    papers: list[dict] = []
    start = 0

    while len(papers) < num_results:
        params = {
            "engine": "google_scholar",
            "q": query,
            "api_key": key,
            "start": start,
            "num": page_size,
        }

        page = _fetch_page_with_retry(GoogleSearch, params, retries, sleep_interval)
        organic = page.get("organic_results") if page else None
        if not organic:
            break

        papers.extend(organic)
        if progress:
            progress(min(len(papers), num_results), num_results)

        if len(organic) < page_size:
            break  # last page reached

        start += page_size
        time.sleep(sleep_interval)

    return papers[:num_results]


def _fetch_page_with_retry(GoogleSearch, params, retries, sleep_interval) -> dict | None:
    """Fetch one page, retrying transient failures with linear backoff.

    Returns the result dict, or None if every attempt failed.
    """
    for attempt in range(1, retries + 1):
        try:
            results = GoogleSearch(params).get_dict()
        except Exception as exc:  # network / client errors are transient enough to retry
            if attempt == retries:
                print(f"Page starting at {params['start']} failed after {retries} attempts: {exc}")
                return None
            time.sleep(sleep_interval * attempt)
            continue

        if "error" in results:
            # SerpAPI reports "haven't returned any results" as a normal terminal state.
            return results if "organic_results" in results else None
        return results
    return None
