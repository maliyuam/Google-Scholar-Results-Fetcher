"""Command-line entry point — one named script that reproduces a whole run.

The notebook had a main(); lifting it into a package dropped it and left only a
GUI, so no run could be reproduced by rerunning anything. This restores that, and
writes a manifest beside every export recording the query, the counts, and the
environment, so an output file can be traced back to the run that produced it.

    python -m scholar_fetcher --query "large language models" --num 50 --format bib
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .export import generate_file_name, save
from .fetch import fetch_google_scholar_results, FetchError
from .process import process_results, dedup_results

FORMATS = ("xlsx", "csv", "bib", "ris")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scholar-fetch",
        description="Fetch Google Scholar results via SerpAPI and export them.",
    )
    parser.add_argument("--query", required=True, help="the search query")
    parser.add_argument("--num", type=int, default=50, help="results to fetch (default: 50)")
    parser.add_argument("--format", choices=FORMATS, default="xlsx",
                        help="output format (default: xlsx)")
    parser.add_argument("--out", help="output path (default: derived from the query)")
    parser.add_argument("--sleep", type=int, default=2, help="seconds between pages (default: 2)")
    parser.add_argument("--retries", type=int, default=3, help="attempts per page (default: 3)")
    parser.add_argument("--no-dedup", action="store_true",
                        help="keep duplicate works instead of collapsing them")
    parser.add_argument("--no-manifest", action="store_true",
                        help="do not write the .manifest.json run record")
    return parser


def _sort_key(paper):
    """Most-cited first, with unrecorded counts last rather than tied with zero."""
    return (paper.get("Citations") is not None, paper.get("Citations") or 0)


def main(argv=None, fetcher=fetch_google_scholar_results) -> int:
    """Run one fetch-process-export cycle. Returns the process exit code.

    `fetcher` is injected so the whole pipeline is testable without a network
    or an API key.
    """
    args = build_parser().parse_args(argv)
    started = datetime.now(timezone.utc)

    try:
        report = fetcher(
            args.query, args.num, sleep_interval=args.sleep, retries=args.retries
        )
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        report = exc.report
        if not report.results:
            return 2
        print(f"keeping the {report.collected} result(s) fetched before the failure.",
              file=sys.stderr)

    papers = process_results(report.results)
    collected = len(papers)

    dropped = 0
    if not args.no_dedup:
        papers, dropped = dedup_results(papers)

    # Truncate last, so surplus rows can backfill what dedup removed.
    papers = sorted(papers, key=_sort_key, reverse=True)[: args.num]

    if not papers:
        print("No results found. Nothing written.", file=sys.stderr)
        return 1

    path = args.out or generate_file_name(args.query, args.format)
    save(papers, path, fmt=args.format)

    # rows requested / collected / dropped / delivered — every step reported.
    print(f"query:     {args.query}")
    print(f"requested: {args.num}")
    print(f"fetched:   {collected}")
    print(f"dropped:   {dropped} duplicate(s)" if not args.no_dedup else "dropped:   0 (dedup off)")
    print(f"written:   {len(papers)} -> {path}")

    if report.pages_failed:
        print(f"WARNING: {report.pages_failed} page(s) failed at offset(s) "
              f"{report.failed_offsets}; this result set is incomplete.", file=sys.stderr)

    if not args.no_manifest:
        manifest = _manifest(args, report, collected, dropped, papers, path, started)
        manifest_path = f"{path}.manifest.json"
        Path(manifest_path).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"manifest:  {manifest_path}")

    # Non-zero when the corpus is knowingly incomplete, so a script can react.
    return 3 if report.pages_failed else 0


def _manifest(args, report, collected, dropped, papers, path, started) -> dict:
    return {
        "query": args.query,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "requested": args.num,
        "fetched": collected,
        "duplicates_dropped": dropped,
        "written": len(papers),
        "dedup_enabled": not args.no_dedup,
        "pages_ok": report.pages_ok,
        "pages_failed": report.pages_failed,
        "failed_offsets": report.failed_offsets,
        "complete": report.complete,
        "format": args.format,
        "output": str(path),
        "scholar_fetcher_version": __version__,
        "python": sys.version.split()[0],
    }


if __name__ == "__main__":
    raise SystemExit(main())
