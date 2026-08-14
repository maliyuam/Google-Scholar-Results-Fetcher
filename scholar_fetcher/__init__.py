"""scholar_fetcher — the Google Scholar Fetcher notebook, lifted into a tested package.

Public surface:
    process_results, dedup_results, FIELDNAMES   (scholar_fetcher.process)
    generate_file_name, to_excel, to_csv, to_bibtex, to_ris, save  (scholar_fetcher.export)
    fetch_google_scholar_results, FetchReport, FetchError          (scholar_fetcher.fetch)

`fetch` is imported lazily so that `process`/`export` work without the serpapi
dependency installed (they are pure-stdlib apart from the optional pandas Excel path).
"""

from .process import process_results, dedup_results, FIELDNAMES
from .export import generate_file_name, to_excel, to_csv, to_bibtex, to_ris, save

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "process_results",
    "dedup_results",
    "FIELDNAMES",
    "generate_file_name",
    "to_excel",
    "to_csv",
    "to_bibtex",
    "to_ris",
    "save",
    "fetch_google_scholar_results",
    "FetchReport",
    "FetchError",
]


def fetch_google_scholar_results(*args, **kwargs):
    """Lazy proxy so importing the package doesn't require the serpapi dependency."""
    from .fetch import fetch_google_scholar_results as _fetch
    return _fetch(*args, **kwargs)


def __getattr__(name):
    """Expose the fetch layer's types without importing serpapi at package import."""
    if name in ("FetchReport", "FetchError"):
        from . import fetch
        return getattr(fetch, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
