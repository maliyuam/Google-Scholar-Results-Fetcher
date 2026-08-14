# Google Scholar Results Fetcher

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maliyuam/Google-Scholar-Results-Fetcher/blob/main/Google_Scholar_Results_Fetcher.ipynb)

Fetches Google Scholar search results through [SerpAPI](https://serpapi.com), ranks them by
citation count, and exports them to **Excel, CSV, BibTeX, or RIS** (BibTeX and RIS import
straight into Zotero, Mendeley, and EndNote).

There are three ways to use it:

| | |
|---|---|
| **Command line** | `python -m scholar_fetcher --query "..." --num 50` — reproducible, writes a run manifest |
| **Web GUI** | `streamlit run streamlit_app.py` — a form, a sortable table, four download buttons |
| **Library** | `from scholar_fetcher import fetch_google_scholar_results, process_results, save` |

The original notebook, `Google_Scholar_Results_Fetcher.ipynb`, still works and still runs in
Colab. Everything below describes the packaged version, which is the same logic with the
silent failure modes removed.

## Requirements

- **Python 3.10 or newer.** This is a hard floor, not a preference — the code uses
  `str | None` annotations that are evaluated at import time.
- A SerpAPI account and API key.

### Getting a SerpAPI key

1. Sign up at [serpapi.com](https://serpapi.com) and verify your email.
2. Open [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key).
3. Copy the key.

SerpAPI is a paid service with a monthly search quota. **One page of 20 results costs one
search**, so `--num 200` costs 10 searches. Budget accordingly.

## Install

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -e ".[gui]"      # or ".[excel]" for CLI + Excel without Streamlit
```

To reproduce the exact environment the test suite was verified against, use the pinned
`requirements.txt` instead:

```bash
pip install -r requirements.txt
```

> Do **not** run `pip install serpapi`. That is a different PyPI distribution which claims
> the same `serpapi` import name and will shadow the one this project needs
> (`google-search-results`). The old version of this README told you to install both; that
> was wrong, and whichever won the race is what received your API key.

## Set your API key

Copy the example file and paste your key into it:

```bash
cp .env.example .env
```

```
SERPAPI_API_KEY=your_real_key_here
```

`.env` is gitignored. An environment variable of the same name takes precedence, so
`export SERPAPI_API_KEY=...` works too. The unedited placeholder is rejected with an
explicit message rather than being sent to the API.

## Command line

```bash
python -m scholar_fetcher --query "large language models" --num 50 --format bib
```

| Option | Default | Meaning |
|---|---|---|
| `--query` | *required* | The Scholar search query |
| `--num` | `50` | How many results to deliver |
| `--format` | `xlsx` | `xlsx`, `csv`, `bib`, or `ris` |
| `--out` | derived from the query | Output path |
| `--sleep` | `2` | Seconds between pages, and the retry backoff unit |
| `--retries` | `3` | Attempts per page before that page is recorded as failed |
| `--no-dedup` | off | Keep duplicate works instead of collapsing them |
| `--no-manifest` | off | Skip the `.manifest.json` run record |

It prints the counts for every step and writes a manifest beside the export:

```
query:     large language models
requested: 50
fetched:   60
dropped:   7 duplicate(s)
written:   50 -> Google_Scholar_Search_large_language_mod_a1b2c3d4.bib
manifest:  Google_Scholar_Search_large_language_mod_a1b2c3d4.bib.manifest.json
```

**Exit codes:** `0` complete, `1` no results, `2` fetch failed with nothing collected,
`3` results written but **at least one page was lost**, so the corpus is incomplete. Check
for `3` in scripts — a short result set is otherwise indistinguishable from a short query.

## Web GUI

```bash
streamlit run streamlit_app.py
```

Enter a query, choose how many results, fetch. The table is sortable and all four export
buttons work from a single fetch — downloading one format does not re-run the search.

## Library

```python
from scholar_fetcher import process_results, dedup_results, save
from scholar_fetcher.fetch import fetch_google_scholar_results

report = fetch_google_scholar_results("large language models", 50)
print(report.requested, report.collected, report.pages_failed, report.complete)

papers = process_results(report.results)
papers, dropped = dedup_results(papers)     # optional; reports rows dropped
save(papers, "results.bib", fmt="bib")
```

`fetch_google_scholar_results` returns a `FetchReport`, not a bare list, so you can always
tell a complete result set from a truncated one. It raises `FetchError` on a failure that
retrying cannot fix (invalid key, exhausted quota), with the rows collected so far attached
as `.report`.

## Output columns

| Column | Notes |
|---|---|
| `Title` | |
| `Authors` | Comma-separated, as Scholar reports them |
| `Year` | Parsed from `publication_info.summary`; `N/A` when absent |
| `Citations` | **Empty when Scholar recorded no count** — never silently zero |
| `Citations_source` | `observed`, `missing`, or `unparseable` |
| `URL` | |
| `Snippet` | Scholar's **search snippet, not the abstract.** It is truncated by Scholar. Exported to the RIS `AB` tag because that is the closest available tag |
| `DOI` | `N/A` when Scholar did not supply one |
| `Merged_fields` | Which fields were filled from a duplicate that dedup dropped |

Missing values are `N/A` for text fields and empty for `Citations`. Nothing is imputed:
a blank citation count means "not recorded", and `Citations_source` says which.

## Deduplication

Optional, and on by default in the GUI. Two rows are treated as the same work if they share
a DOI, or if they share both a normalized title and a first-author surname without carrying
conflicting DOIs. The best-attested copy survives and inherits any field the others had and
it lacked; every such fill is listed in `Merged_fields`. The number of rows dropped is always
reported.

Rows whose title is unusable as a key (`N/A`, or nothing but punctuation) are never
collapsed, because an empty key would merge unrelated papers.

## Tests

```bash
pytest -q
```

82 tests covering processing, deduplication, citation parsing, the fetch retry and error
classification, API-key loading, every export format, and the CLI end to end. No API key
and no network are needed — the fetch layer takes an injected client and the CLI takes an
injected fetcher.

78 of the 82 run on the standard library alone. The four Excel tests live in
`tests/test_excel.py`, need pandas and openpyxl, and skip automatically when pandas is
absent — verified in a pandas-free virtualenv: `78 passed, 1 skipped`.

## Limitations

- SerpAPI's Google Scholar engine returns **20 results per page**. Larger requests are
  paginated with the `start` offset; there is no way to raise the page size.
- No venue, publisher, or full abstract — SerpAPI does not return them. Every BibTeX entry
  is typed `@article` and every RIS record `TY  - JOUR`, which is wrong for the books,
  theses, and preprints Scholar also indexes. Fix the type by hand after import.
- Scholar's citation counts and result ordering drift between calls, so two runs of the
  same query are not guaranteed to be identical. The manifest records when each run happened.
- The GUI has no automated tests; the CLI and library layers do.
