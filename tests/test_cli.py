"""End-to-end CLI tests with an injected searcher. No network, no API key.

This is the "reproducible by rerunning one named command" path, so it is tested
whole: rows in, file and search record out, counts reported at every stage.
"""

import json

import pytest

from scholar_fetcher.cli import main
from scholar_fetcher.process import blank_row
from scholar_fetcher.report import FetchReport


def _row(title, authors="J Smith", cites=1, doi="N/A", source="openalex",
         record_id=None, venue="N/A", year="2020"):
    row = blank_row()
    row.update({
        "Title": title, "Authors": authors, "Year": year, "Venue": venue,
        "Citations": cites, "Citations_source": "observed",
        "URL": f"http://example.com/{title.replace(' ', '-')}",
        "Snippet": "s", "DOI": doi,
        "DOI_source": "reported" if doi != "N/A" else "missing",
        "Source": source, "Record_id": record_id or f"id-{title}",
    })
    return row


def _searcher(rows, reports=None):
    """Stand in for sources.search."""
    def search(query, num, sources, **kwargs):
        made = reports or [
            FetchReport(results=[{}] * len(rows), requested=num, pages_ok=1, source=name)
            for name in sources
        ]
        return list(rows), made
    return search


def _record(tmp_path, name="out.csv"):
    return json.loads((tmp_path / f"{name}.search-record.json").read_text(encoding="utf-8"))


# --- the happy path --------------------------------------------------------


def test_writes_the_export_and_a_search_record(tmp_path, capsys):
    out = tmp_path / "out.bib"
    code = main(
        ["--query", "deep learning", "--num", "2", "--format", "bib", "--out", str(out)],
        searcher=_searcher([_row("Alpha", cites=10), _row("Beta", cites=5)]),
    )
    assert code == 0
    assert "@article{" in out.read_text(encoding="utf-8")

    record = _record(tmp_path, "out.bib")
    assert record["schema"] == "scholar-fetcher/search-record/1"
    assert record["prisma_stage"] == "identification"
    assert record["query"] == "deep learning"
    assert record["counts"]["records_identified"] == 2
    assert record["counts"]["records_written"] == 2
    assert record["complete"] is True
    assert record["environment"]["scholar_fetcher_version"]

    printed = capsys.readouterr().out
    assert "identified: 2" in printed
    assert "written:    2" in printed


def test_methods_paragraph_states_what_actually_ran(tmp_path):
    out = tmp_path / "out.csv"
    main(["--query", "llm eval", "--num", "5", "--format", "csv", "--out", str(out)],
         searcher=_searcher([_row("Alpha"), _row("Alpha")]))
    paragraph = _record(tmp_path)["methods_paragraph"]
    assert "llm eval" in paragraph
    assert "openalex" in paragraph
    assert "scholar-fetcher" in paragraph
    assert "duplicate" in paragraph


def test_record_says_it_covers_identification_only(tmp_path):
    """Overclaiming a full PRISMA flow would be worse than saying nothing."""
    out = tmp_path / "out.csv"
    main(["--query", "q", "--num", "5", "--format", "csv", "--out", str(out)],
         searcher=_searcher([_row("Alpha")]))
    note = _record(tmp_path)["prisma_note"]
    assert "Screening" in note and "not performed by this tool" in note


# --- counts at every stage -------------------------------------------------


def test_reports_duplicates_dropped(tmp_path):
    out = tmp_path / "out.csv"
    main(["--query", "q", "--num", "10", "--format", "csv", "--out", str(out)],
         searcher=_searcher([_row("Same work", cites=10, record_id="a"),
                             _row("Same work", cites=4, record_id="b")]))
    counts = _record(tmp_path)["counts"]
    assert counts["records_identified"] == 2
    assert counts["duplicates_removed"] == 1
    assert counts["records_after_deduplication"] == 1
    assert counts["records_written"] == 1


def test_truncation_beyond_num_is_counted_not_hidden(tmp_path):
    out = tmp_path / "out.csv"
    main(["--query", "q", "--num", "2", "--format", "csv", "--out", str(out)],
         searcher=_searcher([_row(f"P{i}", cites=i) for i in range(5)]))
    counts = _record(tmp_path)["counts"]
    assert counts["records_after_deduplication"] == 5
    assert counts["records_truncated_to_limit"] == 3
    assert counts["records_written"] == 2


def test_no_dedup_flag_keeps_every_row(tmp_path):
    out = tmp_path / "out.csv"
    main(["--query", "q", "--num", "10", "--format", "csv", "--out", str(out), "--no-dedup"],
         searcher=_searcher([_row("Same", record_id="a"), _row("Same", record_id="b")]))
    record = _record(tmp_path)
    assert record["counts"]["records_written"] == 2
    assert record["deduplication"]["enabled"] is False


def test_cross_source_rows_merge_and_the_record_shows_it(tmp_path):
    """A Scholar row and an OpenAlex row for one paper become one row."""
    out = tmp_path / "out.csv"
    scholar = _row("Deep learning", cites=50000, doi="10.1038/nature14539",
                   source="scholar", record_id="s1")
    openalex = _row("Deep Learning", cites=51000, doi="10.1038/nature14539",
                    source="openalex", record_id="W1", venue="Nature")
    main(["--query", "q", "--num", "10", "--format", "csv", "--out", str(out),
          "--source", "scholar", "--source", "openalex"],
         searcher=_searcher([scholar, openalex]))
    counts = _record(tmp_path)["counts"]
    assert counts["records_identified"] == 2
    assert counts["duplicates_removed"] == 1
    assert "Nature" in out.read_text(encoding="utf-8")


# --- failure reporting -----------------------------------------------------


def test_incomplete_run_exits_nonzero_and_says_so(tmp_path, capsys):
    out = tmp_path / "out.csv"
    broken = [FetchReport(requested=50, pages_ok=1, pages_failed=1,
                          failed_offsets=[2], source="openalex")]
    code = main(["--query", "q", "--num", "50", "--format", "csv", "--out", str(out)],
                searcher=_searcher([_row("Alpha")], reports=broken))
    assert code == 3, "a knowingly incomplete corpus must not exit 0"
    assert "incomplete" in capsys.readouterr().err

    record = _record(tmp_path)
    assert record["complete"] is False
    assert record["sources"][0]["failed_offsets"] == [2]
    assert "incomplete" in record["methods_paragraph"]


def test_empty_result_set_writes_nothing(tmp_path):
    out = tmp_path / "out.csv"
    code = main(["--query", "q", "--num", "5", "--format", "csv", "--out", str(out)],
                searcher=_searcher([]))
    assert code == 1
    assert not out.exists(), "an empty run must not create or truncate a file"


# --- arguments -------------------------------------------------------------


def test_default_source_is_openalex(tmp_path):
    out = tmp_path / "out.csv"
    seen = {}

    def searcher(query, num, sources, **kw):
        seen["sources"] = sources
        seen["search_field"] = kw.get("search_field")
        return [_row("Alpha")], [FetchReport(requested=num, pages_ok=1, source=sources[0])]

    main(["--query", "q", "--num", "5", "--format", "csv", "--out", str(out)],
         searcher=searcher)
    assert seen["sources"] == ("openalex",)
    assert seen["search_field"] == "title-abstract"


def test_sources_are_repeatable(tmp_path):
    out = tmp_path / "out.csv"
    seen = {}

    def searcher(query, num, sources, **kw):
        seen["sources"] = sources
        return [_row("Alpha")], [FetchReport(requested=num, pages_ok=1, source="scholar")]

    main(["--query", "q", "--num", "5", "--format", "csv", "--out", str(out),
          "--source", "scholar", "--source", "openalex"], searcher=searcher)
    assert seen["sources"] == ("scholar", "openalex")


def test_default_output_name_is_derived_from_the_query(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["--query", "pull requests", "--num", "5", "--format", "csv"],
         searcher=_searcher([_row("Alpha")]))
    written = [p.name for p in tmp_path.iterdir() if p.suffix == ".csv"]
    assert len(written) == 1
    assert written[0].startswith("Google_Scholar_Search_pull_requests_")


def test_query_is_required():
    with pytest.raises(SystemExit):
        main(["--num", "5"], searcher=_searcher([]))


def test_unknown_source_is_rejected():
    with pytest.raises(SystemExit):
        main(["--query", "q", "--source", "scopus"], searcher=_searcher([]))
