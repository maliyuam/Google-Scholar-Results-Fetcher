"""Command-line entry point: one named command that reproduces a whole search.

The notebook had a main(); lifting it into a package dropped it and left only a
GUI, so no run could be reproduced by rerunning anything. This restores that, and
writes a search record beside every export documenting the query, the sources,
and the count at every stage, so the corpus can be traced and cited.

    python -m scholar_fetcher --query "large language models" --num 50 --format bib
    python -m scholar_fetcher --query "..." --source openalex --source scholar
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .export import generate_file_name, save
from .process import dedup_results
from .report import FetchError
from .sources import DEFAULT_SOURCES, SOURCE_NAMES, describe_sources, search

FORMATS = ("xlsx", "csv", "bib", "ris")

SEARCH_RECORD_SCHEMA = "scholar-fetcher/search-record/1"

DEDUP_KEYS = [
    "source record id (exact, within one source)",
    "DOI (exact, across sources)",
    "normalized title + first-author surname (fallback, unless DOIs conflict)",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scholar-fetch",
        description="Search scholarly literature and export a citable corpus.",
        epilog="Sources:\n" + describe_sources(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", required=True, help="the search query")
    parser.add_argument("--num", type=int, default=50,
                        help="results to deliver (requested from each source; default: 50)")
    parser.add_argument("--source", action="append", choices=SOURCE_NAMES, dest="sources",
                        help=f"repeatable; default: {', '.join(DEFAULT_SOURCES)}")
    parser.add_argument("--search-field", choices=("title-abstract", "fulltext"),
                        default="title-abstract",
                        help="where to match query terms in OpenAlex (default: title-abstract)")
    parser.add_argument("--mailto", help="contact address for OpenAlex's polite pool")
    parser.add_argument("--format", choices=FORMATS, default="xlsx",
                        help="output format (default: xlsx)")
    parser.add_argument("--out", help="output path (default: derived from the query)")
    parser.add_argument("--sleep", type=int, default=2,
                        help="seconds between pages, and the retry backoff unit (default: 2)")
    parser.add_argument("--retries", type=int, default=3,
                        help="attempts per page before it is recorded as failed (default: 3)")
    parser.add_argument("--no-dedup", action="store_true",
                        help="keep duplicate works instead of collapsing them")
    parser.add_argument("--no-manifest", action="store_true",
                        help="do not write the .search-record.json")
    return parser


def _sort_key(paper):
    """Most-cited first, with unrecorded counts last rather than tied with zero."""
    return (paper.get("Citations") is not None, paper.get("Citations") or 0)


def main(argv=None, searcher=search) -> int:
    """Run one search-process-export cycle. Returns the process exit code.

    `searcher` is injected so the whole pipeline is testable without a network
    or an API key.
    """
    args = build_parser().parse_args(argv)
    sources = tuple(args.sources or DEFAULT_SOURCES)
    started = datetime.now(timezone.utc)

    try:
        rows, reports = searcher(
            args.query, args.num, sources,
            sleep_interval=args.sleep, retries=args.retries,
            mailto=args.mailto, search_field=args.search_field,
        )
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    identified = len(rows)

    dropped = 0
    if not args.no_dedup:
        rows, dropped = dedup_results(rows)
    after_dedup = len(rows)

    # Truncate last, so surplus rows backfill what dedup removed.
    rows = sorted(rows, key=_sort_key, reverse=True)[: args.num]
    truncated = after_dedup - len(rows)

    if not rows:
        print("No results found. Nothing written.", file=sys.stderr)
        return 1

    path = args.out or generate_file_name(args.query, args.format)
    save(rows, path, fmt=args.format)

    _report(args, sources, reports, identified, dropped, after_dedup, truncated, rows, path)

    incomplete = any(not r.complete for r in reports)
    if incomplete:
        for report in reports:
            if not report.complete:
                print(f"WARNING: {report.source} lost {report.pages_failed} page(s) at "
                      f"{report.failed_offsets}; this result set is incomplete.",
                      file=sys.stderr)

    if not args.no_manifest:
        record = _search_record(args, sources, reports, identified, dropped,
                                after_dedup, truncated, rows, path, started)
        record_path = f"{path}.search-record.json"
        Path(record_path).write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"record:     {record_path}")

    # Non-zero when the corpus is knowingly incomplete, so a script can react.
    return 3 if incomplete else 0


def _report(args, sources, reports, identified, dropped, after_dedup, truncated, rows, path):
    """Rows in, rows out, rows dropped, at every stage."""
    print(f"query:      {args.query}")
    print(f"sources:    {', '.join(sources)}")
    for report in reports:
        print(f"  {report.source:9s} requested {report.requested}, "
              f"returned {report.collected}, pages ok {report.pages_ok}, "
              f"failed {report.pages_failed}")
    print(f"identified: {identified}")
    print(f"duplicates: {dropped}" if not args.no_dedup else "duplicates: 0 (dedup off)")
    print(f"after dedup:{after_dedup:>4}")
    if truncated:
        print(f"truncated:  {truncated} beyond --num {args.num}")
    print(f"written:    {len(rows)} -> {path}")


def _methods_paragraph(args, sources, reports, identified, dropped, after_dedup,
                       rows, searched_on) -> str:
    """Prose the user can paste into a methods section, stating only what ran."""
    per_source = "; ".join(
        f"{r.source} returned {r.collected}" for r in reports
    )
    dedup_sentence = (
        f"After deduplication on {DEDUP_KEYS[0].split(' (')[0]}, DOI, and normalized "
        f"title with first-author surname, {dropped} duplicate record(s) were removed, "
        f"leaving {after_dedup}."
        if not args.no_dedup else
        "Deduplication was not applied."
    )
    incomplete = [r.source for r in reports if not r.complete]
    caveat = (
        f" Retrieval from {', '.join(incomplete)} was incomplete: one or more pages "
        f"failed, so the counts above are a lower bound."
        if incomplete else ""
    )
    return (
        f"On {searched_on}, {' and '.join(sources)} was searched for "
        f'"{args.query}" (matching on {args.search_field}), requesting {args.num} '
        f"records per source ({per_source}). {identified} records were identified. "
        f"{dedup_sentence} {len(rows)} record(s) were retained for screening.{caveat} "
        f"Retrieval and deduplication were performed with scholar-fetcher "
        f"{__version__}; the machine-readable search record accompanies this file."
    )


def _search_record(args, sources, reports, identified, dropped, after_dedup,
                   truncated, rows, path, started) -> dict:
    """A PRISMA-style record of the identification stage.

    Covers identification and deduplication only. Screening, eligibility, and
    inclusion happen outside this tool, so the record says so rather than
    implying a complete PRISMA flow.
    """
    searched_on = started.strftime("%d %B %Y")
    return {
        "schema": SEARCH_RECORD_SCHEMA,
        "prisma_stage": "identification",
        "prisma_note": (
            "Covers identification and duplicate removal only. Screening, "
            "eligibility assessment, and inclusion are not performed by this tool "
            "and must be reported separately."
        ),
        "query": args.query,
        "search_field": args.search_field,
        "searched_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "name": r.source,
                "requested": r.requested,
                "returned": r.collected,
                "pages_ok": r.pages_ok,
                "pages_failed": r.pages_failed,
                "failed_offsets": r.failed_offsets,
                "complete": r.complete,
            }
            for r in reports
        ],
        "counts": {
            "records_identified": identified,
            "duplicates_removed": dropped,
            "records_after_deduplication": after_dedup,
            "records_truncated_to_limit": truncated,
            "records_written": len(rows),
        },
        "deduplication": {
            "enabled": not args.no_dedup,
            "keys": DEDUP_KEYS,
        },
        "complete": all(r.complete for r in reports),
        "output": {"file": str(path), "format": args.format},
        "environment": {
            "scholar_fetcher_version": __version__,
            "python": sys.version.split()[0],
        },
        "methods_paragraph": _methods_paragraph(
            args, sources, reports, identified, dropped, after_dedup, rows, searched_on
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
