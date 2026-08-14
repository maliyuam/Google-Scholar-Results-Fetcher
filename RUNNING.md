# Running the app

The notebook still works as-is. This is the same logic lifted into a tested
package with a command-line entry point and a graphical interface.

Setup, API-key handling, CLI options, and the output column reference all live in
[README.md](README.md). This file covers only what changed and what is still missing.

## Quick start

```sh
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e ".[gui]"

cp .env.example .env        # then edit .env and paste your SerpAPI key
```

```sh
python -m scholar_fetcher --query "large language models" --num 50 --format bib
streamlit run streamlit_app.py
pytest -q
```

## What changed from the notebook

- Runs anywhere (key from `.env`/environment, not `google.colab.userdata`).
- **Failures are visible.** SerpAPI reports an invalid key, an exhausted quota, and a rate
  limit as HTTP 200 with an `error` field, so none of them ever raised. They were
  indistinguishable from "no more results", and the run returned a short list that looked
  complete. Now the error is classified: rate limits retry with backoff, terminal failures
  raise `FetchError`, and only a genuinely exhausted query stops the loop quietly.
- **Every fetch returns a `FetchReport`** carrying `requested`, `collected`, `pages_failed`,
  and `complete`, so a truncated corpus cannot be reported as a finished one. The CLI exits
  `3` when any page was lost.
- **Nothing is imputed.** A missing citation count is empty with a `Citations_source` flag,
  not a fabricated `0` that sorts in with genuinely uncited papers.
- **Deduplication actually works.** The old DOI-first key put a DOI-bearing copy and a
  DOI-less copy of the same work into different namespaces, so real duplicates never
  collapsed, while every non-Latin title normalized to the same empty key and unrelated
  papers merged into one row. Optional, reports rows dropped, and never collapses a row
  whose title is unusable as a key.
- **The exports are valid.** BibTeX values are LaTeX-escaped (a bare `%` used to comment out
  the rest of the line, closing brace included) and RIS values have their newlines collapsed
  (one embedded newline used to split a record in two).
- Cite keys are derived from the work rather than its rank, so re-running a query no longer
  renumbers every entry and breaks existing `\cite` commands.
- The API key is redacted from anything printed. It travels in the request query string,
  and `requests` puts the full URL in its exception messages.
- Export to CSV / BibTeX / RIS in addition to Excel, plus a `.manifest.json` beside every
  export recording the query, counts, and environment.
- A command line and a graphical form instead of `input()` prompts.

## Tests

`pytest -q` — 85 tests covering processing, deduplication, citation and year parsing, the
fetch retry and error-classification paths, API-key loading, all four export formats, and
the CLI end to end. No API key and no network are needed.

Two caveats worth knowing:

- `tests/fixtures/sample_results.json` is hand-authored, but it has now been **validated
  against a live SerpAPI payload** (20 results, 2026-08-14) and corrected to match it: real
  `publication_info.summary` strings, `result_id`, and `position`. Every field the code
  reads was present 20/20 on the live payload — except `inline_links.doi`, which was
  present 0/20. The fixture keeps one synthetic DOI entry to exercise that path defensively;
  it does not reflect anything SerpAPI returns today.
- Only the four Excel tests in `tests/test_excel.py` need pandas and openpyxl; they skip
  when pandas is absent (verified: `81 passed, 1 skipped` in a pandas-free virtualenv).
  `streamlit_app.py` has no automated tests.

## Not yet done (next phase)

- OpenAlex as a free primary source (removes the paid-API dependency).
- Real abstracts / venue enrichment with per-value source flags. Only `Year` is parsed
  today; there is no venue or publisher, so every entry is typed as a journal article.
- Saved searches and run history.
- Automated tests for the Streamlit GUI.
- **Use `result_id` as the deduplication key.** SerpAPI returns a stable Scholar identifier
  on every result (`result_id`, present 20/20 on the live payload) which the pipeline
  currently discards. It would be a far better key than the normalized-title-plus-surname
  heuristic, which is only a heuristic because nothing better was being read.
- **Derive the DOI from the result URL** where the publisher embeds one (3/20 on the live
  payload). Needs a source flag to distinguish a derived DOI from a reported one.
