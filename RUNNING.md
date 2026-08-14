# Running the app

The notebook still works as-is. This is the same idea rebuilt as a tested package with a
command-line entry point, a graphical interface, and a second data source.

Setup, sources, CLI options, and the output column reference live in [README.md](README.md).
This file covers what changed and what is still missing.

## Quick start

```sh
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e ".[gui]"

cp .env.example .env        # only if you want the Google Scholar source
```

```sh
python -m scholar_fetcher --query "large language models evaluation" --num 50 --format bib
streamlit run streamlit_app.py
pytest -q
```

## What changed from the notebook

**Sources.** Google Scholar via SerpAPI is no longer the only option, or the default.
OpenAlex is free, reports DOI, venue, year, open-access status, and real abstracts, and
returns the same set for the same query. On a live 20-result comparison Scholar returned
zero DOIs and OpenAlex returned twenty. Searching both merges the two into one row per work.

**Failures are visible.** SerpAPI reports an invalid key, an exhausted quota, and a rate
limit as HTTP 200 with an `error` field, so none of them ever raised. They were
indistinguishable from "no more results", and the run returned a short list that looked
complete. Errors are now classified: rate limits retry with backoff, terminal failures raise
`FetchError`, and only a genuinely exhausted query stops the loop quietly.

**Every search returns a FetchReport** carrying `requested`, `collected`, `pages_failed`,
and `complete`, so a truncated corpus cannot be reported as a finished one. The CLI exits
`3` when any page was lost.

**Nothing is imputed.** A missing citation count is empty with a `Citations_source` flag,
not a fabricated `0` that sorts in with genuinely uncited papers. A DOI parsed out of a URL
is flagged `derived`.

**Deduplication actually works.** The old DOI-first key put a DOI-bearing copy and a
DOI-less copy of the same work into different namespaces, so real duplicates never
collapsed, while every non-Latin title normalized to the same empty key and unrelated papers
merged into one row. It now matches on record id, then DOI, then title with first author.

**The exports are valid.** BibTeX values are LaTeX-escaped (a bare `%` used to comment out
the rest of the line, closing brace included), RIS values have their newlines collapsed, and
publisher markup is stripped from titles: a live OpenAlex fetch returned
`Fitting Linear Mixed-Effects Models Using <b>lme4</b>`.

**Cite keys are derived from the work**, not its rank, so re-running a query no longer
renumbers every entry and breaks existing `\cite` commands.

**The API key is redacted** from anything printed. It travels in the request query string,
and `requests` puts the full URL in its exception messages.

**A search record** accompanies every export, recording the query, per-source counts, the
deduplication keys, the count at each stage, and a pasteable methods paragraph.

## Verification notes

Two things in here were found by running the code, not by reading it, and both are worth
knowing about:

- **The default OpenAlex search field is `title-abstract`, not fulltext.** OpenAlex's generic
  `search` parameter also matches indexed full text, and searching
  `"large language models evaluation"` that way returned *R: A Language and Environment for
  Statistical Computing* as the top hit. `title-abstract` is what PubMed and Scopus search by
  default and returned five on-topic results out of five.
- **Every source must tolerate options meant for another source.** `sources.search` hands one
  keyword set to every source, and Scholar's fetch originally had no catch-all, so selecting
  both sources in the GUI raised `TypeError`. Both sources now accept and ignore the others'
  options, and there is a test per source pinning that.

## Tests

`pytest -q` — 128 tests covering both sources, retry and error classification, citation and
year parsing, DOI derivation, deduplication including cross-source merges, API-key loading,
all four export formats, and the CLI end to end. No API key and no network are needed.

Two caveats worth knowing:

- `tests/fixtures/sample_results.json` is hand-authored, but **validated against a live
  SerpAPI payload** (20 results, 2026-08-14) and corrected to match it. Every field the code
  reads was present 20/20, except `inline_links.doi`, present 0/20. The fixture keeps one
  synthetic DOI entry to exercise that path defensively; it does not reflect anything SerpAPI
  returns today. The OpenAlex source was likewise validated against the live API.
- Only the four Excel tests in `tests/test_excel.py` need pandas and openpyxl; they skip when
  pandas is absent, and CI asserts they skip rather than disappear. `streamlit_app.py` has no
  automated tests.

## Not yet done (next phase)

- **Scopus or Web of Science** through institutional access, which would give a third source
  with controlled vocabulary and proper field searching.
- Crossref for DOI enrichment of rows that still lack one.
- Correct entry types. Everything is currently `@article` / `TY  - JOUR`, which mislabels
  books, theses, and preprints.
- Saved searches and run history.
- Automated tests for the Streamlit GUI.
- A PRISMA flow diagram covering screening, which needs counts this tool does not see.
