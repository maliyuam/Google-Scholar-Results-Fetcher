"""Export layer — cells 6 & 7 of the notebook, plus reference-manager formats.

Excel (the original output) is preserved. CSV, BibTeX, and RIS are added so
results can go straight into Zotero / Mendeley / EndNote.

Papers are sorted by citation count (most to least) before writing, matching the
notebook's Excel behavior.
"""

import csv
import re
from io import StringIO

FIELDNAMES = ["Title", "Authors", "Citations", "URL", "Abstract", "DOI"]


def generate_file_name(query: str, ext: str = "xlsx") -> str:
    """Sanitized, truncated file name from the query. Matches the notebook."""
    sanitized_query = re.sub(r"[^\w\s]", "", query)
    truncated_query = sanitized_query[:20].strip()
    final_query = re.sub(r"\s+", "_", truncated_query)
    return f"Google_Scholar_Search_{final_query}.{ext}"


def _sorted_by_citations(papers: list[dict]) -> list[dict]:
    return sorted(papers, key=lambda p: p.get("Citations", 0), reverse=True)


def to_excel(papers: list[dict], path: str) -> str:
    """Write papers to an .xlsx file (requires pandas + openpyxl). Returns the path."""
    import pandas as pd  # lazy: only the Excel path needs pandas
    df = pd.DataFrame(_sorted_by_citations(papers), columns=FIELDNAMES)
    df.to_excel(path, index=False)
    return path


def to_csv(papers: list[dict], path: str | None = None) -> str:
    """Write CSV to `path`, or return it as a string if path is None."""
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_sorted_by_citations(papers))
    text = buffer.getvalue()
    if path:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path
    return text


def _cite_key(paper: dict, index: int) -> str:
    """Build a BibTeX cite key from first author surname + first title word."""
    authors = paper.get("Authors", "") or ""
    first_author = authors.split(",")[0].strip()
    surname = first_author.split()[-1] if first_author else "anon"
    title_word = ""
    for word in re.sub(r"[^\w\s]", "", paper.get("Title", "")).split():
        title_word = word
        break
    stem = re.sub(r"[^A-Za-z0-9]", "", f"{surname}{title_word}") or "ref"
    return f"{stem}{index}"


def to_bibtex(papers: list[dict]) -> str:
    """Render papers as a BibTeX string (@article entries)."""
    entries = []
    for i, paper in enumerate(_sorted_by_citations(papers), start=1):
        authors = " and ".join(
            a.strip() for a in (paper.get("Authors", "") or "").split(",") if a.strip()
        )
        fields = [f'  title = {{{paper.get("Title", "")}}}']
        if authors:
            fields.append(f"  author = {{{authors}}}")
        if paper.get("URL", "N/A") not in ("", "N/A"):
            fields.append(f'  url = {{{paper.get("URL")}}}')
        if paper.get("DOI", "N/A") not in ("", "N/A"):
            fields.append(f'  doi = {{{paper.get("DOI")}}}')
        fields.append(f'  note = {{Cited by {paper.get("Citations", 0)}}}')
        entries.append(f"@article{{{_cite_key(paper, i)},\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def to_ris(papers: list[dict]) -> str:
    """Render papers as an RIS string (TY - JOUR records)."""
    records = []
    for paper in _sorted_by_citations(papers):
        lines = ["TY  - JOUR", f'TI  - {paper.get("Title", "")}']
        for author in (paper.get("Authors", "") or "").split(","):
            author = author.strip()
            if author:
                lines.append(f"AU  - {author}")
        if paper.get("URL", "N/A") not in ("", "N/A"):
            lines.append(f'UR  - {paper.get("URL")}')
        if paper.get("DOI", "N/A") not in ("", "N/A"):
            lines.append(f'DO  - {paper.get("DOI")}')
        if paper.get("Abstract", "N/A") not in ("", "N/A"):
            lines.append(f'AB  - {paper.get("Abstract")}')
        lines.append(f'N1  - Cited by {paper.get("Citations", 0)}')
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
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(to_bibtex(papers))
        return path
    if fmt == "ris":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(to_ris(papers))
        return path
    raise ValueError(f"Unknown format: {fmt!r} (expected xlsx, csv, bib, or ris)")
