"""scholar_fetcher — the Google Scholar Fetcher notebook, lifted into a tested package.

Public surface:
    process_results, dedup_results   (scholar_fetcher.process)
    generate_file_name, to_excel, to_csv, to_bibtex, to_ris, save  (scholar_fetcher.export)
    fetch_google_scholar_results     (scholar_fetcher.fetch)

`fetch` is imported lazily so that `process`/`export` work without the serpapi
dependency installed (they are pure-stdlib apart from the optional pandas Excel path).
"""

from .process import process_results, dedup_results
from .export import generate_file_name, to_csv, to_bibtex, to_ris, save

__all__ = [
    "process_results",
    "dedup_results",
    "generate_file_name",
    "to_csv",
    "to_bibtex",
    "to_ris",
    "save",
    "fetch_google_scholar_results",
]


def fetch_google_scholar_results(*args, **kwargs):
    """Lazy proxy so importing the package doesn't require the serpapi dependency."""
    from .fetch import fetch_google_scholar_results as _fetch
    return _fetch(*args, **kwargs)
