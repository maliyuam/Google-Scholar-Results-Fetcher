"""Source registry and multi-source search.

A source is a pair: something that fetches raw payloads and reports what it did,
and something that turns those payloads into rows of the shared schema. Keeping
those two together per source is what lets deduplication stay source-agnostic.

Searching more than one source is the point. A Scholar row has a citation count
and no DOI; an OpenAlex row has a DOI, a venue and a real abstract. Deduplication
merges them on DOI into one row that has all of it, and records in `Source` and
`Merged_fields` where each part came from.
"""

from dataclasses import dataclass
from typing import Callable

from .report import FetchReport, FetchError


@dataclass(frozen=True)
class Source:
    """One searchable database."""

    name: str
    fetch: Callable[..., FetchReport]
    normalize: Callable[[list[dict]], list[dict]]
    needs_api_key: bool
    description: str


def _scholar() -> Source:
    from .fetch import fetch_google_scholar_results, normalize_scholar_results, SOURCE_NAME

    return Source(
        name=SOURCE_NAME,
        fetch=fetch_google_scholar_results,
        normalize=normalize_scholar_results,
        needs_api_key=True,
        description="Google Scholar via SerpAPI. Broad coverage and citation "
                    "counts, but no DOI or venue, and its ranking is not reproducible.",
    )


def _openalex() -> Source:
    from .openalex import fetch_openalex_results, normalize_openalex_results, SOURCE_NAME

    return Source(
        name=SOURCE_NAME,
        fetch=fetch_openalex_results,
        normalize=normalize_openalex_results,
        needs_api_key=False,
        description="OpenAlex. Free and CC0, reports DOI, venue, year, and "
                    "open-access status, and the same query returns the same set.",
    )


# Loaded lazily so importing the package pulls in neither serpapi nor a network stack.
_BUILDERS = {"scholar": _scholar, "openalex": _openalex}

SOURCE_NAMES = tuple(_BUILDERS)
DEFAULT_SOURCES = ("openalex",)


def get_source(name: str) -> Source:
    """Look up one source by name."""
    try:
        return _BUILDERS[name]()
    except KeyError:
        raise ValueError(
            f"Unknown source {name!r}. Available: {', '.join(SOURCE_NAMES)}"
        ) from None


def describe_sources() -> str:
    return "\n".join(f"  {name:9s} {get_source(name).description}" for name in SOURCE_NAMES)


def search(
    query: str,
    num_results: int,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    *,
    on_error: str = "continue",
    **kwargs,
) -> tuple[list[dict], list[FetchReport]]:
    """Search every named source and return (rows, one report per source).

    Rows are normalized but NOT deduplicated or truncated: the caller does that,
    so it can report how many rows each step removed.

    Args:
        query: the search string, passed to every source unchanged.
        num_results: how many results to request from each source.
        sources: source names, in order.
        on_error: 'continue' keeps going when one source fails terminally, which
            is usually right for a multi-source search (losing Scholar should not
            lose an OpenAlex corpus). 'raise' propagates instead.
        **kwargs: forwarded to each source's fetch. Sources ignore what they do
            not use, so mailto= and api_key= can be passed together.

    Returns:
        (rows, reports). A source that failed terminally still contributes a
        report, so a caller can say which source came up short and why.
    """
    rows: list[dict] = []
    reports: list[FetchReport] = []

    for name in sources:
        source = get_source(name)
        try:
            report = source.fetch(query, num_results, **kwargs)
        except FetchError as exc:
            if on_error == "raise":
                raise
            # Keep whatever that source managed before failing, and keep the
            # report so the shortfall is visible rather than inferred.
            report = exc.report
            report.source = name
            print(f"{name}: {exc}")

        report.source = name
        reports.append(report)
        rows.extend(source.normalize(report.results))

    return rows, reports
