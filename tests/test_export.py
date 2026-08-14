"""Tests for the export layer (BibTeX / RIS / CSV / filename). Pure stdlib."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scholar_fetcher.export import (
    generate_file_name,
    to_bibtex,
    to_ris,
    to_csv,
)

PAPERS = [
    {"Title": "Attention is all you need", "Authors": "A Vaswani, N Shazeer",
     "Citations": 80000, "URL": "http://example.com/attention",
     "Abstract": "The dominant models...", "DOI": "10.5555/attention"},
    {"Title": "Deep learning", "Authors": "Y LeCun, Y Bengio",
     "Citations": 50000, "URL": "http://example.com/deep", "Abstract": "N/A", "DOI": "N/A"},
]


def test_generate_file_name_sanitizes_and_truncates():
    name = generate_file_name('("pull request") AND impact', ext="csv")
    assert name.startswith("Google_Scholar_Search_")
    assert name.endswith(".csv")
    assert "(" not in name and '"' not in name and " " not in name


def test_bibtex_sorted_by_citations_and_includes_doi():
    bib = to_bibtex(PAPERS)
    assert bib.index("Attention is all you need") < bib.index("Deep learning")  # higher cites first
    assert "author = {A Vaswani and N Shazeer}" in bib
    assert "doi = {10.5555/attention}" in bib
    assert "note = {Cited by 80000}" in bib
    # the N/A DOI paper must not emit a doi field
    assert bib.count("doi = ") == 1


def test_ris_has_one_record_per_paper_with_author_lines():
    ris = to_ris(PAPERS)
    assert ris.count("TY  - JOUR") == 2
    assert ris.count("ER  - ") == 2
    assert "AU  - A Vaswani" in ris and "AU  - N Shazeer" in ris
    assert "DO  - 10.5555/attention" in ris


def test_csv_string_has_header_and_rows():
    text = to_csv(PAPERS)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("Title,Authors,Citations")
    assert len(lines) == 3  # header + 2 papers
