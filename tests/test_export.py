"""Tests for the export layer (BibTeX / RIS / CSV / filename). Pure stdlib."""

import re

import pytest

from scholar_fetcher.export import (
    generate_file_name,
    to_bibtex,
    to_ris,
    to_csv,
    save,
    _cite_key,
)

PAPERS = [
    {"Title": "Attention is all you need", "Authors": "A Vaswani, N Shazeer", "Year": "2017",
     "Citations": 80000, "Citations_source": "observed", "URL": "http://example.com/attention",
     "Snippet": "The dominant models...", "DOI": "10.5555/attention", "Merged_fields": ""},
    {"Title": "Deep learning", "Authors": "Y LeCun, Y Bengio", "Year": "N/A",
     "Citations": 50000, "Citations_source": "observed", "URL": "http://example.com/deep",
     "Snippet": "N/A", "DOI": "N/A", "Merged_fields": ""},
]


def _paper(**overrides):
    base = {"Title": "T", "Authors": "J Smith", "Year": "N/A", "Citations": 1,
            "Citations_source": "observed", "URL": "N/A", "Snippet": "N/A",
            "DOI": "N/A", "Merged_fields": ""}
    base.update(overrides)
    return base


def _braces_balanced(text):
    """Balanced ignoring \\{ and \\}, which are literal characters, not structure."""
    depth = 0
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        depth += (ch == "{") - (ch == "}")
        if depth < 0:
            return False
    return depth == 0


# --- filenames -------------------------------------------------------------


def test_generate_file_name_sanitizes_and_truncates():
    name = generate_file_name('("pull request") AND impact', ext="csv")
    assert name.startswith("Google_Scholar_Search_")
    assert name.endswith(".csv")
    assert "(" not in name and '"' not in name and " " not in name


def test_generate_file_name_keeps_the_query_text():
    """The old test allowed the query to vanish entirely from the filename."""
    assert "pull_request" in generate_file_name('("pull request") AND impact')


def test_queries_sharing_a_20_char_prefix_get_distinct_names():
    """Truncation alone made these collide, and save() then overwrote the first file."""
    a = generate_file_name("machine learning applications in medicine")
    b = generate_file_name("machine learning applications in finance")
    assert a != b


def test_same_query_is_stable_across_calls():
    assert generate_file_name("reproducible") == generate_file_name("reproducible")


def test_degenerate_query_still_produces_a_usable_name():
    name = generate_file_name("???")
    assert name.startswith("Google_Scholar_Search_")
    assert not name.endswith("_.xlsx")


# --- BibTeX ----------------------------------------------------------------


def test_bibtex_sorted_by_citations_and_includes_doi():
    bib = to_bibtex(PAPERS)
    assert bib.index("Attention is all you need") < bib.index("Deep learning")
    assert "author = {A Vaswani and N Shazeer}" in bib
    assert "doi = {10.5555/attention}" in bib
    assert "note = {Cited by 80000}" in bib
    assert bib.count("doi = ") == 1  # the N/A DOI paper must not emit a doi field


def test_bibtex_emits_year_when_known_and_omits_it_when_not():
    bib = to_bibtex(PAPERS)
    assert "year = {2017}" in bib
    assert bib.count("year = ") == 1


def test_bibtex_escapes_latex_specials():
    """A raw % comments out the rest of the line, taking the closing brace with it."""
    bib = to_bibtex([_paper(Title="Cost & benefit of 100% coverage: C_max #1 $x$")])
    assert r"\&" in bib and r"\%" in bib and r"\_" in bib and r"\#" in bib and r"\$" in bib
    for special in "&%_#$":
        assert not re.search(rf"(?<!\\){re.escape(special)}", bib), \
            f"an unescaped {special!r} reached the .bib"


def test_bibtex_braces_stay_balanced_with_unbalanced_input():
    bib = to_bibtex([_paper(Title="A }{ broken { title")])
    assert _braces_balanced(bib)


def test_bibtex_survives_none_fields():
    """A None title used to raise TypeError and abort the whole export."""
    bib = to_bibtex([_paper(Title=None, URL=None, DOI=None, Authors=None)])
    assert "None" not in bib
    assert bib.startswith("@article{")


def test_cite_keys_are_stable_across_runs_and_unique_per_work():
    first = _cite_key(PAPERS[0])
    assert first == _cite_key(PAPERS[0]), "same input must give the same key"
    assert first != _cite_key(PAPERS[1])


def test_cite_key_does_not_depend_on_position_in_the_ranking():
    """Index-based keys changed on every re-run and broke existing \\cite commands."""
    forward = to_bibtex(PAPERS)
    reversed_input = to_bibtex(list(reversed(PAPERS)))
    assert forward == reversed_input


# --- RIS -------------------------------------------------------------------


def test_ris_has_one_record_per_paper_with_author_lines():
    ris = to_ris(PAPERS)
    assert ris.count("TY  - JOUR") == 2
    assert ris.count("ER  - ") == 2
    assert "AU  - A Vaswani" in ris and "AU  - N Shazeer" in ris
    assert "DO  - 10.5555/attention" in ris
    assert "PY  - 2017" in ris


def test_ris_newline_in_a_field_does_not_split_the_record():
    ris = to_ris([_paper(Title="A title\nwith a newline", Snippet="line one\r\nline two")])
    assert ris.count("TY  - JOUR") == 1
    for line in ris.splitlines():
        assert not line or line[:6] in ("TY  - ", "TI  - ", "AU  - ", "UR  - ",
                                        "DO  - ", "AB  - ", "PY  - ", "N1  - ", "ER  - ")


def test_ris_survives_none_fields():
    ris = to_ris([_paper(Title=None, URL=None, DOI=None, Snippet=None)])
    assert "None" not in ris


# --- CSV -------------------------------------------------------------------


def test_csv_string_has_header_and_rows():
    text = to_csv(PAPERS)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("Title,Authors,Year,Citations,Citations_source")
    assert len(lines) == 3


def test_csv_header_lists_every_column():
    """The old test checked three names, so silent loss of URL/Snippet/DOI passed."""
    from scholar_fetcher.process import FIELDNAMES
    assert to_csv(PAPERS).splitlines()[0].split(",") == FIELDNAMES


def test_csv_neutralizes_spreadsheet_formulas():
    text = to_csv([_paper(Title="=cmd|'/C calc'!A1")])
    assert "\n'=cmd" in text or text.splitlines()[1].startswith("'=cmd")


def test_missing_citations_sort_last_not_as_zero():
    papers = [_paper(Title="unknown", Citations=None, Citations_source="missing"),
              _paper(Title="zero", Citations=0),
              _paper(Title="ten", Citations=10)]
    order = [ln.split(",")[0] for ln in to_csv(papers).splitlines()[1:] if ln.strip()]
    assert order == ["ten", "zero", "unknown"]


# --- save ------------------------------------------------------------------


def test_save_refuses_to_write_an_empty_result_set(tmp_path):
    """Writing an empty set truncated an existing export to zero bytes."""
    target = tmp_path / "existing.bib"
    target.write_text("@article{keepme,\n  title = {Do not lose me}\n}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        save([], str(target), fmt="bib")
    assert "keepme" in target.read_text(encoding="utf-8")


def test_save_writes_bib_and_ris(tmp_path):
    bib = tmp_path / "out.bib"
    save(PAPERS, str(bib), fmt="bib")
    assert "@article{" in bib.read_text(encoding="utf-8")

    ris = tmp_path / "out.ris"
    save(PAPERS, str(ris), fmt="ris")
    assert "TY  - JOUR" in ris.read_text(encoding="utf-8")


def test_save_rejects_an_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        save(PAPERS, str(tmp_path / "x.txt"), fmt="txt")


def test_to_excel_is_importable_from_the_package():
    """__init__ advertised to_excel in its docstring but never exported it."""
    from scholar_fetcher import to_excel
    assert callable(to_excel)


# --- Excel (the one path that needs pandas) --------------------------------

pandas = pytest.importorskip("pandas", reason="Excel export needs pandas + openpyxl")


def test_to_excel_writes_every_column_sorted_by_citations(tmp_path):
    from scholar_fetcher.export import to_excel
    from scholar_fetcher.process import FIELDNAMES

    target = tmp_path / "out.xlsx"
    to_excel(PAPERS, str(target))

    df = pandas.read_excel(target)
    assert list(df.columns) == FIELDNAMES
    assert df["Title"].tolist() == ["Attention is all you need", "Deep learning"]


def test_to_excel_accepts_a_buffer_so_the_gui_need_not_reimplement_it():
    import io
    from scholar_fetcher.export import to_excel

    assert to_excel(PAPERS, io.BytesIO()).getvalue()[:2] == b"PK"  # xlsx is a zip


def test_to_excel_refuses_an_empty_result_set(tmp_path):
    from scholar_fetcher.export import to_excel

    target = tmp_path / "existing.xlsx"
    to_excel(PAPERS, str(target))
    before = target.read_bytes()

    with pytest.raises(ValueError):
        to_excel([], str(target))
    assert target.read_bytes() == before


def test_missing_citation_reaches_excel_as_blank_with_its_flag(tmp_path):
    from scholar_fetcher.export import to_excel

    target = tmp_path / "out.xlsx"
    to_excel([_paper(Title="unknown", Citations=None, Citations_source="missing")], str(target))

    df = pandas.read_excel(target)
    assert pandas.isna(df["Citations"].iloc[0]), "a missing count must not arrive as 0"
    assert df["Citations_source"].iloc[0] == "missing"
