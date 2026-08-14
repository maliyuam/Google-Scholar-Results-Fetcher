# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-08-14

The notebook became a tested package. This release exists because an audit found
the pipeline could lose rows, fabricate citation counts, and corrupt its own
exports without any of it being visible to the user.

### Added
- `scholar_fetcher` package with a command-line entry point
  (`python -m scholar_fetcher`, or `scholar-fetch` once installed).
- `.manifest.json` written beside every export, recording query, UTC timestamps,
  requested/fetched/dropped/written counts, dedup setting, and versions, so an
  output file can be traced back to the run that produced it.
- `FetchReport` return type carrying `requested`, `collected`, `pages_ok`,
  `pages_failed`, `failed_offsets`, and `complete`.
- `FetchError` for failures that retrying cannot fix.
- `Citations_source` column (`observed` / `missing` / `unparseable`).
- `Year` column, parsed from `publication_info.summary`.
- `Merged_fields` column recording which fields a dedup survivor inherited from
  a dropped duplicate.
- CSV, BibTeX, and RIS export alongside the original Excel output.
- `pyproject.toml`, so the package is installable and the tests need no
  `sys.path` manipulation.
- Test suite: 85 tests, from 8.

### Fixed
- **Deduplication failed on the case it existed for.** The DOI-first key put a
  DOI-bearing copy and a DOI-less copy of the same work into different
  namespaces, so real duplicates never collapsed.
- **Deduplication deleted unrelated works.** The fallback key was the title
  alone, so two different papers sharing a generic title merged and one was
  dropped.
- **Non-Latin titles all collapsed into one row.** `[^a-z0-9]` reduced every
  CJK, Cyrillic, and Arabic title to the empty string, giving them one shared key.
- **SerpAPI errors passed for a finished search.** An invalid key, an exhausted
  quota, and a rate limit are all returned as HTTP 200 with an `error` field, so
  they never raised and were never retried. A truncated corpus looked complete.
- **Missing citation counts were imputed to 0**, indistinguishable from an
  observed zero, while being the sole ranking key.
- **A JSON null in `publication_info` destroyed the entire batch.**
- **BibTeX was written unescaped.** A bare `%` in a title comments out the rest
  of the line, including the closing brace.
- **RIS was written with newlines intact**, splitting one record into several.
- **A `None` title aborted the whole BibTeX export**; `None` URLs and DOIs were
  written as the literal string `None`.
- **Cite keys embedded the row's rank**, so re-running a query renumbered every
  entry and broke existing `\cite` commands.
- **Exporting an empty result set truncated an existing file to zero bytes.**
- **The API key could be printed in cleartext**; it travels in the request query
  string and `requests` embeds the full URL in exception messages.
- **The unedited `.env.example` placeholder passed key validation**, producing a
  misleading "No results found" instead of a key error.
- Streamlit results were lost on any rerun, so downloading one export format
  discarded the table and forced a second, billed fetch.
- `to_excel` was advertised in the package docstring but never exported.
- Filenames truncated to 20 characters, so different searches collided and
  overwrote each other.

### Changed
- `Abstract` column renamed to `Snippet`. It always held Google Scholar's search
  snippet, never an abstract.
- `fetch_google_scholar_results` returns a `FetchReport` instead of a bare list.
- Truncation to `--num` now happens after deduplication, so already-fetched rows
  backfill the slots duplicates vacated.
- CSV is written `utf-8-sig` with formula-leading cells neutralized.
- README rewritten against the actual code. It had claimed 200 results per page
  (the real cap is 20), documented functions that existed nowhere, and told
  readers to install two PyPI distributions that contend for the same import name.

### Verified
- Test fixture validated against a live SerpAPI payload (20 results). Every field
  the code reads was present on all 20, except `inline_links.doi`, which was
  present on none. The DOI column is `N/A` in practice.

## [0.1.0] — 2024

Initial notebook (`Google_Scholar_Results_Fetcher.ipynb`): fetch, process, and
save Google Scholar results to Excel, run in Colab.

[Unreleased]: https://github.com/maliyuam/Google-Scholar-Results-Fetcher/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/maliyuam/Google-Scholar-Results-Fetcher/releases/tag/v0.2.0
