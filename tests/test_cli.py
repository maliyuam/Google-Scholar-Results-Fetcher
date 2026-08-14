"""End-to-end CLI tests with an injected fetcher — no network, no API key.

This is the 'reproducible by rerunning one named script' path, so it is tested
as a whole: fetch report in, file and manifest out, counts reported.
"""

import json

import pytest

from scholar_fetcher.cli import main
from scholar_fetcher.fetch import FetchReport, FetchError


def _raw(title, authors=("J Smith",), total=1, doi=None, summary="J Smith - Nature, 2015"):
    inline = {"cited_by": {"total": total}}
    if doi:
        inline["doi"] = doi
    return {
        "title": title,
        "publication_info": {"authors": [{"name": a} for a in authors], "summary": summary},
        "inline_links": inline,
        "link": f"http://example.com/{title}",
        "snippet": "s",
    }


def _fetcher(results, **report_kw):
    def fetch(query, num, **kw):
        return FetchReport(results=list(results), requested=num, pages_ok=1, **report_kw)
    return fetch


def test_writes_the_export_and_a_manifest(tmp_path, capsys):
    out = tmp_path / "out.bib"
    code = main(
        ["--query", "deep learning", "--num", "2", "--format", "bib", "--out", str(out)],
        fetcher=_fetcher([_raw("Alpha", total=10), _raw("Beta", total=5)]),
    )
    assert code == 0
    assert "@article{" in out.read_text(encoding="utf-8")

    manifest = json.loads((tmp_path / "out.bib.manifest.json").read_text(encoding="utf-8"))
    assert manifest["query"] == "deep learning"
    assert manifest["requested"] == 2
    assert manifest["fetched"] == 2
    assert manifest["written"] == 2
    assert manifest["complete"] is True
    assert manifest["dedup_enabled"] is True
    assert manifest["scholar_fetcher_version"]

    printed = capsys.readouterr().out
    assert "requested: 2" in printed and "fetched:   2" in printed


def test_reports_duplicates_dropped(tmp_path):
    out = tmp_path / "out.csv"
    main(
        ["--query", "q", "--num", "10", "--format", "csv", "--out", str(out)],
        fetcher=_fetcher([_raw("Same work", total=10), _raw("Same Work", total=4)]),
    )
    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["fetched"] == 2
    assert manifest["duplicates_dropped"] == 1
    assert manifest["written"] == 1


def test_no_dedup_flag_keeps_every_row(tmp_path):
    out = tmp_path / "out.csv"
    main(
        ["--query", "q", "--num", "10", "--format", "csv", "--out", str(out), "--no-dedup"],
        fetcher=_fetcher([_raw("Same work", total=10), _raw("Same Work", total=4)]),
    )
    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["written"] == 2
    assert manifest["dedup_enabled"] is False


def test_surplus_backfills_after_dedup(tmp_path):
    """Truncating before dedup delivered fewer rows than were already paid for."""
    out = tmp_path / "out.csv"
    main(
        ["--query", "q", "--num", "2", "--format", "csv", "--out", str(out)],
        fetcher=_fetcher([_raw("Alpha", total=10), _raw("Alpha", total=9), _raw("Beta", total=8)]),
    )
    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["written"] == 2, "the surplus row should fill the slot dedup freed"


def test_incomplete_run_exits_nonzero_and_says_so(tmp_path, capsys):
    out = tmp_path / "out.csv"
    code = main(
        ["--query", "q", "--num", "50", "--format", "csv", "--out", str(out)],
        fetcher=_fetcher([_raw("Alpha")], pages_failed=1, failed_offsets=[20]),
    )
    assert code == 3, "a knowingly incomplete corpus must not exit 0"
    assert "incomplete" in capsys.readouterr().err

    manifest = json.loads((tmp_path / "out.csv.manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is False
    assert manifest["failed_offsets"] == [20]


def test_terminal_fetch_error_keeps_partial_rows_and_reports(tmp_path, capsys):
    out = tmp_path / "out.csv"
    partial = FetchReport(results=[_raw("Alpha")], requested=50, pages_ok=1)

    def failing(query, num, **kw):
        raise FetchError("You have run out of searches", partial)

    code = main(["--query", "q", "--num", "50", "--format", "csv", "--out", str(out)],
                fetcher=failing)
    assert code == 0
    assert out.exists()
    err = capsys.readouterr().err
    assert "run out of searches" in err and "keeping the 1 result" in err


def test_empty_result_set_writes_nothing(tmp_path):
    out = tmp_path / "out.csv"
    code = main(["--query", "q", "--num", "5", "--format", "csv", "--out", str(out)],
                fetcher=_fetcher([]))
    assert code == 1
    assert not out.exists(), "an empty run must not create or truncate a file"


def test_year_reaches_the_export(tmp_path):
    out = tmp_path / "out.ris"
    main(["--query", "q", "--num", "5", "--format", "ris", "--out", str(out)],
         fetcher=_fetcher([_raw("Alpha", summary="J Smith - Nature, 2015 - nature.com")]))
    assert "PY  - 2015" in out.read_text(encoding="utf-8")


def test_default_output_name_is_derived_from_the_query(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["--query", "pull requests", "--num", "5", "--format", "csv"],
         fetcher=_fetcher([_raw("Alpha")]))
    written = [p.name for p in tmp_path.iterdir() if p.suffix == ".csv"]
    assert len(written) == 1
    assert written[0].startswith("Google_Scholar_Search_pull_requests_")


def test_query_is_required():
    with pytest.raises(SystemExit):
        main(["--num", "5"], fetcher=_fetcher([]))
