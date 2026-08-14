"""Export layer — cells 6 & 7 of the notebook, plus reference-manager formats.

Excel (the original output) is preserved. CSV, BibTeX, and RIS are added so
results can go straight into Zotero / Mendeley / EndNote.

The formats are text formats with rules, and the first version ignored them:
BibTeX values went out unescaped (a bare `%` comments out the rest of the line,
taking the closing brace with it), RIS values went out with their newlines intact
(splitting one record into several), and a None field was written as the literal
string "None" — or raised, aborting the whole export. All three are handled here.

Papers are sorted by citation count (most to least) before writing, matching the
notebook, except that a *missing* count now sorts last instead of tying with 0.
"""

import csv
import hashlib
import re
from io import StringIO

from .process import FIELDNAMES, MISSING

# Characters that are syntax rather than text in a BibTeX/LaTeX value.
_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Leading characters that make a spreadsheet treat a cell as a formula.
_FORMULA_LEAD = ("=", "+", "-", "@")

_UNSET = ("", MISSING, None)


def _text(value) -> str:
    """Any field value as a string. None becomes empty, never the word 'None'."""
    return "" if value is None else str(value)


def _has(paper: dict, field: str) -> bool:
    return paper.get(field) not in _UNSET


def generate_file_name(query: str, ext: str = "xlsx") -> str:
    """Sanitized file name from the query, with a short digest of the full query.

    The notebook truncated to 20 characters and stopped there, so two searches
    sharing a prefix produced one filename and the second export overwrote the
    first. The digest is taken from the untruncated query, so distinct searches
    get distinct files while the same search stays reproducible.
    """
    sanitized = re.sub(r"[^\w\s]", "", query or "")
    truncated = sanitized[:20].strip()
    stem = re.sub(r"\s+", "_", truncated)
    digest = hashlib.sha1((query or "").encode("utf-8")).hexdigest()[:8]
    return f"Google_Scholar_Search_{stem}_{digest}.{ext}" if stem else \
           f"Google_Scholar_Search_{digest}.{ext}"


def _sorted_by_citations(papers: list[dict]) -> list[dict]:
    """Most-cited first; rows with no observed count go last, not in with the zeros."""
    return sorted(
        papers,
        key=lambda p: (p.get("Citations") is not None, p.get("Citations") or 0),
        reverse=True,
    )


def _require_papers(papers: list[dict]) -> list[dict]:
    """Refuse to write nothing. Opening an output file for an empty result set
    truncated a previous export to zero bytes and reported success."""
    if not papers:
        raise ValueError("No papers to write — refusing to create or truncate a file.")
    return _sorted_by_citations(papers)


def to_excel(papers: list[dict], target):
    """Write papers as .xlsx to a path or a binary buffer (needs pandas + openpyxl).

    Returns whatever it was given, so the GUI can hand it a BytesIO instead of
    reimplementing the Excel path.
    """
    import pandas as pd  # lazy: only the Excel path needs pandas

    df = pd.DataFrame(_require_papers(papers), columns=FIELDNAMES)
    df.to_excel(target, index=False)
    return target


def _csv_cell(value) -> str:
    """Neutralize a value a spreadsheet would otherwise evaluate as a formula."""
    text = _text(value)
    return "'" + text if text[:1] in _FORMULA_LEAD else text


def to_csv(papers: list[dict], path: str | None = None) -> str:
    """Write CSV to `path`, or return it as a string if path is None."""
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for paper in _require_papers(papers):
        writer.writerow({field: _csv_cell(paper.get(field)) for field in FIELDNAMES})
    text = buffer.getvalue()

    if path:
        # utf-8-sig: without the BOM, Excel on Windows mis-decodes non-ASCII names.
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(text)
        return path
    return text


def _escape_latex(value) -> str:
    """Escape BibTeX/LaTeX syntax characters. Iterates the source once, so the
    backslash replacement cannot re-escape the backslashes it just inserted."""
    return "".join(_LATEX_SPECIALS.get(ch, ch) for ch in _text(value))


def _authors(paper: dict) -> list[str]:
    return [a.strip() for a in _text(paper.get("Authors")).split(",") if a.strip()]


def _cite_key(paper: dict) -> str:
    """A stable cite key derived from the work itself.

    The key used to embed the row's position in the citation ranking, so
    re-running the same query renumbered every entry and broke existing \\cite
    commands. The digest is over the DOI (or the title), so the same work always
    gets the same key and two exports can be concatenated without collisions.
    """
    authors = _authors(paper)
    surname = authors[0].split()[-1] if authors and authors[0].split() else "anon"

    title = _text(paper.get("Title"))
    words = re.sub(r"[^\w\s]", "", title).split()
    stem = re.sub(r"[^A-Za-z0-9]", "", f"{surname}{words[0] if words else ''}") or "ref"

    identity = paper.get("DOI") if _has(paper, "DOI") else title
    digest = hashlib.sha1(_text(identity).casefold().encode("utf-8")).hexdigest()[:6]

    year = _text(paper.get("Year")) if _has(paper, "Year") else ""
    return f"{stem}{year}{digest}"


def to_bibtex(papers: list[dict]) -> str:
    """Render papers as a BibTeX string (@article entries)."""
    entries = []
    for paper in _sorted_by_citations(papers):
        fields = [f"  title = {{{_escape_latex(paper.get('Title'))}}}"]

        authors = _authors(paper)
        if authors:
            fields.append(f"  author = {{{_escape_latex(' and '.join(authors))}}}")
        if _has(paper, "Year"):
            fields.append(f"  year = {{{_escape_latex(paper.get('Year'))}}}")
        if _has(paper, "URL"):
            fields.append(f"  url = {{{_escape_latex(paper.get('URL'))}}}")
        if _has(paper, "DOI"):
            fields.append(f"  doi = {{{_escape_latex(paper.get('DOI'))}}}")

        citations = paper.get("Citations")
        note = f"Cited by {citations}" if citations is not None else "Citation count not recorded"
        fields.append(f"  note = {{{_escape_latex(note)}}}")

        entries.append(f"@article{{{_cite_key(paper)},\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def _ris_value(value) -> str:
    """RIS is line-oriented: a newline inside a value would forge a new tag line."""
    return re.sub(r"\s*[\r\n]+\s*", " ", _text(value)).strip()


def to_ris(papers: list[dict]) -> str:
    """Render papers as an RIS string (TY - JOUR records)."""
    records = []
    for paper in _sorted_by_citations(papers):
        lines = ["TY  - JOUR", f"TI  - {_ris_value(paper.get('Title'))}"]
        lines += [f"AU  - {_ris_value(a)}" for a in _authors(paper)]
        if _has(paper, "Year"):
            lines.append(f"PY  - {_ris_value(paper.get('Year'))}")
        if _has(paper, "URL"):
            lines.append(f"UR  - {_ris_value(paper.get('URL'))}")
        if _has(paper, "DOI"):
            lines.append(f"DO  - {_ris_value(paper.get('DOI'))}")
        if _has(paper, "Snippet"):
            # AB is the abstract tag; this is Scholar's snippet, which is the
            # closest thing the API returns. Documented in README.md.
            lines.append(f"AB  - {_ris_value(paper.get('Snippet'))}")

        citations = paper.get("Citations")
        note = f"Cited by {citations}" if citations is not None else "Citation count not recorded"
        lines.append(f"N1  - {note}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n".join(records) + ("\n" if records else "")


def save(papers: list[dict], path: str, fmt: str = "xlsx") -> str:
    """Dispatch to the writer for `fmt` ('xlsx', 'csv', 'bib', 'ris')."""
    fmt = fmt.lower()
    if fmt in ("xlsx", "excel"):
        return to_excel(papers, path)
    if fmt == "csv":
        return to_csv(papers, path)
    if fmt in ("bib", "bibtex"):
        text = to_bibtex(_require_papers(papers))
    elif fmt == "ris":
        text = to_ris(_require_papers(papers))
    else:
        raise ValueError(f"Unknown format: {fmt!r} (expected xlsx, csv, bib, or ris)")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path
