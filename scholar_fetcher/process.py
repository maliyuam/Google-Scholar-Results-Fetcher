"""Processing layer: normalize source payloads into rows, and collapse duplicates.

Row extraction for a given source lives with that source. This module owns the
row schema, the value parsers every source shares, and deduplication, which is
deliberately source-agnostic so a Scholar row and an OpenAlex row describing the
same paper collapse into one.

Three rules hold everywhere in here, because this feeds research corpora:

  * No value is ever invented. A citation count that is absent or unreadable is
    None and says which in `Citations_source`. A DOI parsed out of a publisher
    URL is marked `derived`, never passed off as one the API reported.
  * No row disappears quietly. `dedup_results` returns the number dropped, and a
    survivor records in `Merged_fields` anything it inherited from a duplicate.
  * A key that cannot identify a record is not used as one. Rows whose title
    normalizes to nothing get a unique key rather than sharing an empty one.
"""

import html
import re

FIELDNAMES = [
    "Title",
    "Authors",
    "Year",
    "Venue",
    "Citations",
    "Citations_source",
    "URL",
    "Snippet",
    "DOI",
    "DOI_source",
    "Source",
    "Record_id",
    "Merged_fields",
]

CITATIONS_OBSERVED = "observed"
CITATIONS_MISSING = "missing"
CITATIONS_UNPARSEABLE = "unparseable"

DOI_REPORTED = "reported"
DOI_DERIVED = "derived"
DOI_MISSING = "missing"

MISSING = "N/A"

# Fields worth recovering from a duplicate that dedup is about to drop, and the
# provenance column that must travel with each one.
_COALESCED = ("DOI", "Venue", "URL", "Snippet", "Authors", "Year")
_PROVENANCE = {"DOI": "DOI_source"}

# A DOI is "10." then a registrant code, then anything up to a URL delimiter.
_DOI_IN_URL = re.compile(r"(10\.\d{4,9}/[^\s\"'<>?#]+)")

# Format suffixes publishers append to a DOI inside a URL path.
_DOI_URL_SUFFIXES = (".pdf", ".full", ".abstract", ".epub", ".html", ".xml")


_HTML_TAG = re.compile(r"<[^>]+>")


def clean_text(value) -> str:
    """Strip presentation markup out of a metadata string.

    Publisher metadata carries markup that both sources pass straight through:
    a live OpenAlex fetch returned the title "Fitting Linear Mixed-Effects
    Models Using <b>lme4</b>". Unhandled, that lands verbatim in a .bib file.

    This removes tags and resolves entities. It does not alter the words, so it
    is a formatting fix rather than an inference, and needs no source flag.
    """
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = _HTML_TAG.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def is_person_name(value: str) -> bool:
    """Whether a string can be a name at all.

    Sources sometimes parse a footnote marker as the entire author list. The 2015
    Lancet RTS,S malaria vaccine trial comes back from OpenAlex with exactly one
    authorship whose display_name is "†". Written out, that becomes
    `author = {†}` in a .bib file and a fabricated author in someone's reference
    manager, which is worse than admitting the authors are unknown.

    A name contains at least one letter. str.isalpha is Unicode-aware, so names
    in any script pass, as do corporate authors and names with apostrophes.
    """
    return any(character.isalpha() for character in value)


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


def _clean_doi(doi: str) -> str:
    """Strip URL and punctuation debris off a DOI."""
    doi = str(doi).strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = doi.rstrip(").,;:")
    lowered = doi.lower()
    for suffix in _DOI_URL_SUFFIXES:
        if lowered.endswith(suffix):
            doi = doi[: -len(suffix)]
            break
    return doi.rstrip("/")


def parse_doi(reported, url) -> tuple[str, str]:
    """Return (doi, provenance).

    A reported DOI always wins. Failing that, many publisher URLs carry the DOI
    in the path (dl.acm.org/doi/abs/10.1145/3641289), which is worth recovering
    because it is the only exact key for matching a record across sources. It is
    flagged `derived` so it never reads as something the API actually returned.
    """
    if reported and str(reported) != MISSING:
        return _clean_doi(reported), DOI_REPORTED

    match = _DOI_IN_URL.search(str(url or ""))
    if match:
        return _clean_doi(match.group(1)), DOI_DERIVED

    return MISSING, DOI_MISSING


def blank_row() -> dict:
    """A row with every column present and unset. Sources fill what they have."""
    row = dict.fromkeys(FIELDNAMES, MISSING)
    row["Citations"] = None
    row["Citations_source"] = CITATIONS_MISSING
    row["DOI_source"] = DOI_MISSING
    row["Authors"] = ""
    row["Merged_fields"] = ""
    return row


def process_results(results: list[dict]) -> list[dict]:
    """Normalize raw SerpAPI Google Scholar results into rows, one per result."""
    from .fetch import normalize_scholar_results

    return normalize_scholar_results(results)


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
    return _clean_doi(doi).casefold() if doi and doi != MISSING else None


def _record_key(paper: dict) -> tuple[str, str] | None:
    """A source's own stable id. Exact identity, but only within that source."""
    record_id = paper.get("Record_id")
    source = paper.get("Source")
    if not record_id or record_id == MISSING:
        return None
    return (str(source), str(record_id))


def _title_author_key(paper: dict) -> tuple[str, str] | None:
    stem = _normalized_title(paper)
    return (stem, _first_author_surname(paper)) if stem else None


def _rank(paper: dict) -> tuple[int, int]:
    """Survivor preference: an observed citation count always beats a missing one."""
    citations = paper.get("Citations")
    return (0, 0) if citations is None else (1, citations)


def dedup_results(papers: list[dict]) -> tuple[list[dict], int]:
    """Collapse duplicate works, keeping the best-attested copy.

    Rows are matched on three keys, in descending order of confidence:

      1. (Source, Record_id) — the source's own id. Exact, but same-source only,
         since a Scholar id and an OpenAlex id are different namespaces.
      2. DOI — exact across sources. This is what makes a Scholar row and an
         OpenAlex row for the same paper collapse.
      3. Normalized title + first-author surname — the fallback, used only when
         the two rows do not carry conflicting DOIs.

    A row can join a group by any key, so grouping is a union rather than a dict
    lookup. Rows whose title is unusable as a key ('N/A', or nothing but
    punctuation) are never collapsed on key 3.

    Fields the survivor lacks are filled from the copies being dropped, and every
    field filled that way is named in `Merged_fields`.

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

    by_record: dict[tuple[str, str], int] = {}
    by_doi: dict[str, int] = {}
    by_title_author: dict[tuple[str, str], int] = {}

    for i, paper in enumerate(papers):
        record = _record_key(paper)
        if record is not None:
            if record in by_record:
                union(by_record[record], i)
            else:
                by_record[record] = i

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
            if value in ("", MISSING, None):
                continue
            survivor[field] = value
            # A donated value brings its provenance with it, or the flag would
            # describe a value that is no longer there.
            companion = _PROVENANCE.get(field)
            if companion:
                survivor[companion] = other.get(companion, MISSING)
            filled.append(field)
            break

    # Which sources contributed to this row, so a merged record is traceable.
    sources = sorted({p.get("Source") for p in group if p.get("Source") not in (None, MISSING)})
    if sources:
        survivor["Source"] = "+".join(sources)

    survivor["Merged_fields"] = ";".join(filled)
    return survivor
