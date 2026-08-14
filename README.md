# Scholar Fetcher

[![CI](https://github.com/maliyuam/scholar-fetcher/actions/workflows/ci.yml/badge.svg)](https://github.com/maliyuam/scholar-fetcher/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/maliyuam/scholar-fetcher/blob/main/scholar_fetcher.ipynb)

Searches scholarly literature, merges duplicate records across sources, ranks by citation
count, and exports to **Excel, CSV, BibTeX, or RIS**. Every run writes a machine-readable
search record so the corpus can be traced and cited.

Started as a Google Scholar scraper. It still does that, but Scholar is no longer the
default, for reasons worth knowing before you pick a source.

| | |
|---|---|
| **Command line** | `python -m scholar_fetcher --query "..." --num 50` — reproducible, writes a search record |
| **Web GUI** | `streamlit run streamlit_app.py` — form, sortable table, four export buttons |
| **Library** | `from scholar_fetcher.sources import search` |

## Sources

| | OpenAlex (default) | Google Scholar (via SerpAPI) |
|---|---|---|
| Cost | Free | Paid, per search |
| DOI | **20/20 on a live test** | **0/20 on a live test** |
| Venue | 16/20 | Never |
| Abstract | Full, 20/20 | Truncated snippet only |
| Reproducible | Documented API, stable results | Ranking is neither documented nor stable |
| Access | Public API | Third-party scraper |

**Use OpenAlex unless you specifically need Scholar's citation counts or its grey-literature
coverage.** Two reasons:

1. Google Scholar's ranking is not transparent or reproducible: the same query at two times
   returns different sets in different orders. That conflicts with the reproducible-search
   requirement in PRISMA, and it is why guidance consistently says not to use Scholar as the
   primary source for a systematic review.
2. Google sued SerpAPI in December 2025 over automated scraping of its search results. That
   litigation is unresolved. If you depend on the Scholar path, understand that its
   availability is outside your control and outside this project's control.

Searching both is supported and is often the right answer: Scholar contributes citation
counts and coverage, OpenAlex contributes the DOI, venue, and abstract, and deduplication
merges them into one row that names both sources in the `Source` column.

## Requirements

- **Python 3.10 or newer.** A hard floor: the code uses `str | None` annotations evaluated
  at import time.
- A SerpAPI key only if you use the Scholar source. OpenAlex needs none.

## Install

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -e ".[gui]"      # or ".[excel]" for CLI + Excel without Streamlit
```

To reproduce the exact environment the suite was verified against, use the pinned
`requirements.txt` instead:

```bash
pip install -r requirements.txt
```

> Do **not** run `pip install serpapi`. That is a different PyPI distribution which claims
> the same `serpapi` import name and will shadow the one this project needs
> (`google-search-results`). An older version of this README told you to install both; that
> was wrong, and whichever won the race is what received your API key.

## Set your API key (Scholar only)

```bash
cp .env.example .env
```

```
SERPAPI_API_KEY=your_real_key_here
```

`.env` is gitignored, and CI fails the build if it ever becomes tracked. An environment
variable of the same name takes precedence. The unedited placeholder is rejected with an
explicit message rather than being sent to the API.

The Scholar source is also hidden from the **web interface** unless you switch it on,
even with a valid key present. It is the only paid source and the web app has no
authentication, so exposing it takes two deliberate settings rather than one:

```
SERPAPI_API_KEY=your_real_key
SCHOLAR_ENABLED=1
```

The CLI and library ignore the flag: whoever runs those already owns the key.

For OpenAlex, set a contact address to join the polite pool (higher rate limits):

```bash
export OPENALEX_MAILTO="you@university.edu"   # or pass --mailto
```

## Command line

```bash
python -m scholar_fetcher --query "large language models evaluation" --num 50 --format bib
python -m scholar_fetcher --query "..." --source scholar --source openalex
```

| Option | Default | Meaning |
|---|---|---|
| `--query` | *required* | The search query |
| `--num` | `50` | Results to deliver, requested from each source |
| `--source` | `openalex` | Repeatable: `openalex`, `scholar` |
| `--search-field` | `title-abstract` | Where to match terms in OpenAlex. `fulltext` has higher recall and much lower precision |
| `--mailto` | — | Contact address for OpenAlex's polite pool |
| `--format` | `xlsx` | `xlsx`, `csv`, `bib`, `ris` |
| `--out` | derived from query | Output path |
| `--sleep` | `2` | Seconds between pages, and the retry backoff unit |
| `--retries` | `3` | Attempts per page before it is recorded as failed |
| `--no-dedup` | off | Keep duplicate works |
| `--no-manifest` | off | Skip the search record |

It reports the count at every stage:

```
query:      large language models evaluation
sources:    openalex
  openalex  requested 25, returned 25, pages ok 1, failed 0
identified: 25
duplicates: 0
after dedup:  25
written:    25 -> Google_Scholar_Search_large_language_mod_a1b2c3d4.bib
record:     Google_Scholar_Search_large_language_mod_a1b2c3d4.bib.search-record.json
```

**Exit codes:** `0` complete, `1` no results, `2` search failed outright,
`3` results written but **at least one page was lost**, so the corpus is incomplete. Check
for `3` in scripts: a short result set is otherwise indistinguishable from a short query.

## The search record

Every run writes `<output>.search-record.json` next to the export, containing the verbatim
query, the search field, UTC timestamps, per-source counts, the deduplication keys used, the
count at each stage, and the environment. It also contains a `methods_paragraph` you can
paste into a manuscript:

> On 14 August 2026, openalex was searched for "large language models evaluation" (matching
> on title-abstract), requesting 25 records per source (openalex returned 25). 25 records
> were identified. After deduplication on source record id, DOI, and normalized title with
> first-author surname, 0 duplicate record(s) were removed, leaving 25. 25 record(s) were
> retained for screening. Retrieval and deduplication were performed with scholar-fetcher
> 0.3.0; the machine-readable search record accompanies this file.

**This covers the identification stage only.** Screening, eligibility assessment, and
inclusion happen outside this tool and must be reported separately. The record says so
explicitly rather than implying a complete PRISMA flow.

## Web GUI

```bash
streamlit run streamlit_app.py
```

Pick sources, enter a query, search. All four export buttons work from a single search:
downloading one format does not re-run the query.

## Library

```python
from scholar_fetcher.sources import search
from scholar_fetcher.process import dedup_results
from scholar_fetcher.export import save

rows, reports = search("large language models", 50, ("openalex", "scholar"))
for report in reports:
    print(report.source, report.collected, report.complete)

rows, dropped = dedup_results(rows)
save(rows, "results.bib", fmt="bib")
```

Each source returns a `FetchReport`, not a bare list, so you can always tell a complete
result set from a truncated one. A failure that retrying cannot fix raises `FetchError`,
with the rows collected so far attached as `.report`.

## Output columns

| Column | Notes |
|---|---|
| `Title` | Markup stripped. Publisher metadata really does contain `<b>` tags |
| `Authors` | Comma-separated. Entries containing no letters (footnote markers like `†`, which sources occasionally report as the whole author list) are dropped rather than credited as people. Empty means the authors are unknown |
| `Year` | OpenAlex reports it; for Scholar it is parsed from the summary line |
| `Venue` | Journal or repository. **OpenAlex only** — see below |
| `Citations` | **Empty when no count was recorded** — never silently zero |
| `Citations_source` | `observed`, `missing`, or `unparseable` |
| `URL` | For OpenAlex, prefers an open-access PDF the reader can actually open |
| `Snippet` | OpenAlex: the real abstract. Scholar: a truncated search snippet, not an abstract |
| `DOI` | See below |
| `DOI_source` | `reported` (the API returned it), `derived` (parsed from the URL), or `missing` |
| `Source` | Which database. A merged row names both, e.g. `openalex+scholar` |
| `Record_id` | The source's own stable identifier |
| `Merged_fields` | Which fields were filled from a duplicate that dedup dropped |

Nothing is imputed. A blank citation count means "not recorded", and `Citations_source`
says which. A DOI parsed out of a URL is flagged `derived` and never passes for one the API
reported.

### Why `Venue` is empty for Scholar

Scholar's only venue data is a free-text summary like
`"A Vaswani, N Shazeer - Advances in neural ..., 2017 - papers.nips.cc"`. Slicing a journal
name out of that is guesswork, and an unflagged guess in research data is worse than a gap.
OpenAlex reports the venue properly.

### Why `DOI` is usually empty for Scholar

A live Scholar fetch of 20 results returned **no DOI on any of them**. SerpAPI's Scholar
engine does not appear to supply them. Where the publisher embeds a DOI in the result URL
(`dl.acm.org/doi/abs/10.1145/3641289`) it is recovered and flagged `derived`; that covered 3
of those 20. OpenAlex reported a DOI for 20 of 20.

## Deduplication

Optional, on by default. Rows are matched on three keys, in descending confidence:

1. **`(Source, Record_id)`** — the source's own id. Exact, but only within that source: a
   Scholar id and an OpenAlex id are different namespaces.
2. **DOI** — exact, across sources. This is what merges a Scholar row and an OpenAlex row
   for the same paper.
3. **Normalized title + first-author surname** — the fallback, used only when the two rows
   do not carry conflicting DOIs.

The best-attested copy survives and inherits any field the others had and it lacked; each
such fill is listed in `Merged_fields`, and a donated DOI brings its `DOI_source` with it.
Rows whose title is unusable as a key (`N/A`, or nothing but punctuation) are never
collapsed on key 3. Rows dropped is always reported.

## Tests

```bash
pytest -q
```

128 tests covering both sources' fetch, retry, and error classification; citation and year
parsing; DOI derivation; deduplication including cross-source merges; API-key loading; every
export format; and the CLI end to end. **No API key and no network are needed** — each
source takes an injected client and the CLI takes an injected searcher.

124 of the 128 run on the standard library alone. The four Excel tests live in
`tests/test_excel.py`, need pandas and openpyxl, and skip when pandas is absent. CI asserts
they skip rather than silently disappear.

## Limitations

- SerpAPI's Scholar engine returns **20 results per page**; there is no way to raise it.
  OpenAlex returns up to 200.
- OpenAlex moved to usage-based pricing for high-volume calls in February 2026. Single-record
  lookups remain free; set `--mailto` for the polite pool.
- Every BibTeX entry is typed `@article` and every RIS record `TY  - JOUR`, which is wrong
  for the books, theses, and preprints both sources index. Fix the type after import.
- Scholar's citation counts and ordering drift between calls, so two Scholar runs of one
  query are not guaranteed identical. The search record timestamps every run.
- The GUI has no automated tests; the CLI and library layers do.

## Deploying and sharing

See [DEPLOY.md](DEPLOY.md) for hosting the GUI on Streamlit Community Cloud, publishing to
PyPI, and cutting a release. The short version: OpenAlex needs no key, so a public deploy
works with **zero secrets configured** — and you should keep it that way, because a
SerpAPI key on a public app means every visitor spends your quota.

## License

MIT. See [LICENSE](LICENSE).
