"""Tests for the Excel writer — the one export path that needs pandas.

Kept in its own module so that a pandas-free environment skips exactly these
tests and still runs the rest of the suite. A module-level importorskip inside
test_export.py would skip the pure-stdlib BibTeX/RIS/CSV tests along with them.
"""

import io

import pytest

pandas = pytest.importorskip("pandas", reason="Excel export needs pandas + openpyxl")

from scholar_fetcher.export import to_excel          # noqa: E402
from scholar_fetcher.process import FIELDNAMES       # noqa: E402

PAPERS = [
    {"Title": "Attention is all you need", "Authors": "A Vaswani, N Shazeer", "Year": "2017",
     "Citations": 80000, "Citations_source": "observed", "URL": "http://example.com/attention",
     "Snippet": "The dominant models...", "DOI": "10.5555/attention", "Merged_fields": ""},
    {"Title": "Deep learning", "Authors": "Y LeCun, Y Bengio", "Year": "N/A",
     "Citations": 50000, "Citations_source": "observed", "URL": "http://example.com/deep",
     "Snippet": "N/A", "DOI": "N/A", "Merged_fields": ""},
]


def test_to_excel_writes_every_column_sorted_by_citations(tmp_path):
    target = tmp_path / "out.xlsx"
    to_excel(PAPERS, str(target))

    df = pandas.read_excel(target)
    assert list(df.columns) == FIELDNAMES
    assert df["Title"].tolist() == ["Attention is all you need", "Deep learning"]


def test_to_excel_accepts_a_buffer_so_the_gui_need_not_reimplement_it():
    assert to_excel(PAPERS, io.BytesIO()).getvalue()[:2] == b"PK"  # xlsx is a zip


def test_to_excel_refuses_an_empty_result_set(tmp_path):
    target = tmp_path / "existing.xlsx"
    to_excel(PAPERS, str(target))
    before = target.read_bytes()

    with pytest.raises(ValueError):
        to_excel([], str(target))
    assert target.read_bytes() == before


def test_missing_citation_reaches_excel_as_blank_with_its_flag(tmp_path):
    target = tmp_path / "out.xlsx"
    to_excel(
        [{"Title": "unknown", "Authors": "J Smith", "Year": "N/A", "Citations": None,
          "Citations_source": "missing", "URL": "N/A", "Snippet": "N/A",
          "DOI": "N/A", "Merged_fields": ""}],
        str(target),
    )

    df = pandas.read_excel(target)
    assert pandas.isna(df["Citations"].iloc[0]), "a missing count must not arrive as 0"
    assert df["Citations_source"].iloc[0] == "missing"
