"""Processing layer — cell 5 of the notebook, with the silent failures removed.

Two deliberate divergences from the notebook, both to stop it reporting numbers
it never observed:

  * A citation count is never fabricated. Absent or unparseable counts become
    None and carry a `Citations_source` flag, so "no citations recorded" stays
    distinguishable from "we saw a zero" and from "we could not read the value".
    The notebook wrote 0 for the first case and crashed on the third.
  * The column holding Scholar's search snippet is named `Snippet`, because that
    is what SerpAPI returns. The notebook called it `Abstract`; it never was one.

dedup_results is still opt-in and still reports rows dropped: collapsing rows
changes the row count, so the caller decides.
"""

import re

FIELDNAMES = [
    "Title",
    "Authors",
    "Year",
    "Citations",
    "Citations_source",
    "URL",
    "Snippet",
    "DOI",
    "Merged_fields",
]

CITATIONS_OBSERVED = "observed"
CITATIONS_MISSING = "missing"
CITATIONS_UNPARSEABLE = "unparseable"

MISSING = "N/A"

# Fields worth recovering from a duplicate that dedup is about to drop.
_COALESCED = ("DOI", "URL", "Snippet", "Authors", "Year")

# SerpAPI puts the venue and year in publication_info.summary, e.g.
# "Y LeCun, Y Bengio, G Hinton - nature, 2015 - nature.com".
_YEAR = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")


def _parse_citations(value) -> tuple[int | None, str]:
    """Return (count, source flag). Never invents a number.

    Absent -> (None, 'missing'). Unreadable -> (None, 'unparseable'). The
    notebook's `int(citation) if citation != 'N/A' else 0` fabricated a 0 for
    the first and raised for the second.
    """
    if value is None:
        return None, CITATIONS_MISSING
    if isinstance(value, bool):
        # bool is an int subclass, but True is not a citation count.
        return None, CITATIONS_UNPARSEABLE
    if isinstance(value, int):
        return value, CITATIONS_OBSERVED

    text = str(value).strip()
    if not text or text == MISSING:
        return None, CITATIONS_MISSING
    try:
        # Tolerate thousands separators: "1,234" and "1 234" are real counts.
        return int(re.sub(r"[,\s]", "", text)), CITATIONS_OBSERVED
    except ValueError:
        return None, CITATIONS_UNPARSEABLE


def process_results(results: list[dict]) -> list[dict]:
    """Flatten raw SerpAPI results into rows, one row per result."""
    papers = []
    for result in results:
        # `or {}` rather than .get(k, {}): SerpAPI sends JSON null for an absent
        # block, and null would sail past a default and blow up on .get below.
        publication_info = result.get("publication_info") or {}
        inline_links = result.get("inline_links") or {}
        cited_by = inline_links.get("cited_by") or {}

        citations, citations_source = _parse_citations(cited_by.get("total"))

        authors = publication_info.get("authors") or []
        names = (a.get("name") for a in authors if isinstance(a, dict))
        authors_str = ", ".join(name for name in names if name)

        year = _YEAR.search(publication_info.get("summary") or "")

        papers.append({
            "Title": result.get("title") or MISSING,
            "Authors": authors_str,
            "Year": year.group(1) if year else MISSING,
            "Citations": citations,
            "Citations_source": citations_source,
            "URL": result.get("link") or MISSING,
            "Snippet": result.get("snippet") or MISSING,
            "DOI": inline_links.get("doi") or MISSING,
            "Merged_fields": "",
        })
    return papers


def _normalized_title(paper: dict) -> str:
    """Lowercased, punctuation-stripped title. Empty means 'not usable as a key'.

    \\W is Unicode-aware, so a CJK or Cyrillic title normalizes to itself. The
    old [^a-z0-9] reduced every non-Latin title to '', giving them all one key.
    """
    title = paper.get("Title") or ""
    if title == MISSING:
        return ""
    return re.sub(r"\W", "", title.casefold())


def _first_author_surname(paper: dict) -> str:
    first = (paper.get("Authors") or "").split(",")[0].strip()
    return re.sub(r"\W", "", first.split()[-1].casefold()) if first else ""


def _doi_key(paper: dict) -> str | None:
    doi = paper.get("DOI")
    return doi.strip().casefold() if doi and doi != MISSING else None


def _title_author_key(paper: dict) -> tuple[str, str] | None:
    stem = _normalized_title(paper)
    return (stem, _first_author_surname(paper)) if stem else None


def _rank(paper: dict) -> tuple[int, int]:
    """Sort key for choosing a survivor: an observed count always beats a missing one."""
    citations = paper.get("Citations")
    return (0, 0) if citations is None else (1, citations)


def dedup_results(papers: list[dict]) -> tuple[list[dict], int]:
    """Collapse duplicate works, keeping the best-attested copy.

    Two rows are the same work if they share a DOI, or if they share both a
    normalized title and a first-author surname without carrying *conflicting*
    DOIs. Two independent keys means a row can join a group by either one, so
    the grouping is a union rather than a dict lookup.

    Rows whose title is unusable as a key ('N/A', or nothing but punctuation)
    are never collapsed — an empty key would merge unrelated works.

    Fields the survivor is missing are filled from the copies being dropped, and
    every field filled that way is recorded in `Merged_fields`.

    Returns (deduped_papers, n_dropped). First-appearance order is preserved.
    """
    parent = list(range(len(papers)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)   # earliest row stays the root

    by_doi: dict[str, int] = {}
    by_title_author: dict[tuple[str, str], int] = {}

    for i, paper in enumerate(papers):
        doi = _doi_key(paper)
        if doi is not None:
            if doi in by_doi:
                union(by_doi[doi], i)
            else:
                by_doi[doi] = i

        title_author = _title_author_key(paper)
        if title_author is not None:
            seen = by_title_author.get(title_author)
            if seen is None:
                by_title_author[title_author] = i
            else:
                other = _doi_key(papers[seen])
                # Same title and author but two different DOIs: different works.
                if doi is None or other is None or doi == other:
                    union(seen, i)

    groups: dict[int, list[dict]] = {}
    order: list[int] = []
    for i, paper in enumerate(papers):
        root = find(i)
        if root not in groups:
            groups[root] = []
            order.append(root)
        groups[root].append(paper)

    deduped = [_merge(groups[root]) for root in order]
    return deduped, len(papers) - len(deduped)


def _merge(group: list[dict]) -> dict:
    """Pick the best-attested row in a group and fill its gaps from the rest."""
    if len(group) == 1:
        return group[0]

    survivor = dict(max(group, key=_rank))
    filled = []
    for field in _COALESCED:
        if survivor.get(field) not in ("", MISSING, None):
            continue
        for other in group:
            value = other.get(field)
            if value not in ("", MISSING, None):
                survivor[field] = value
                filled.append(field)
                break

    survivor["Merged_fields"] = ";".join(filled)
    return survivor
