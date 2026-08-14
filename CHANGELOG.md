# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] — 2026-08-14

First release published to PyPI: `pip install scholar-fetcher`.

### Added
- `DEPLOY.md`: hosting the GUI on Streamlit Community Cloud, publishing to PyPI, and
  cutting a release, with cost and reversibility for each.
- `.github/workflows/publish.yml`: publishes to PyPI on a version tag using Trusted
  Publishing (OIDC), so no API token is stored in the repo. Runs the full suite first and
  refuses to publish when the tag does not match `__version__`.
- **`SCHOLAR_ENABLED` spend guard.** The Google Scholar source is now hidden from the web
  interface unless the flag is explicitly set, *even when a valid API key is present*.
  Scholar is the only paid source and the app has no authentication or rate limiting, so a
  hosted copy carrying a key would let every visitor spend the owner's quota. Exposing it
  now takes two deliberate settings instead of one. The CLI and library are ungated.

### Changed
- The keyless notice in the GUI leads with the fact that OpenAlex works without a key,
  rather than opening with what is unavailable.
- Renamed the repository to `scholar-fetcher`, matching the PyPI distribution and the
  Python package. GitHub redirects the old repository URL, so existing clones and links
  keep working.
- Renamed the notebook to `scholar_fetcher.ipynb` and repointed the Colab badge in both
  the README and the notebook itself. **GitHub redirects repositories, not file paths**,
  so any previously shared link to the old notebook filename now 404s.

### Fixed
- The publish workflow's tag-versus-version check compared the *branch* name when the
  workflow was started manually, failing with a misleading message on exactly the path
  you would use to retry a failed publish. It now refuses a non-tag ref explicitly.

## [0.3.0] — 2026-08-14

Adds a second data source and makes the output citable. Google Scholar is no
longer the only source, or the default.

### Added
- **OpenAlex source** (`scholar_fetcher/openalex.py`), free and needing no key.
  Reports DOI, venue, year, open-access status, and full abstracts reconstructed
  from OpenAlex's inverted index. On a live 20-result comparison Scholar returned
  0 DOIs and OpenAlex returned 20. Uses `urllib` from the standard library, so the
  package still installs without an HTTP dependency.
- **Source registry** (`scholar_fetcher/sources.py`). `search()` runs one or more
  sources and returns normalized rows plus one report per source. Searching both
  merges Scholar's citation counts with OpenAlex's bibliographic detail.
- **Search record** written beside every export (`<output>.search-record.json`):
  verbatim query, search field, UTC timestamps, per-source counts, deduplication
  keys, the count at every stage, and a `methods_paragraph` that can be pasted
  into a manuscript. Covers the identification stage only, and says so.
- `--source`, `--search-field`, and `--mailto` on the CLI; source selection in the GUI.
- `Venue`, `DOI_source`, `Source`, and `Record_id` columns.
- LICENSE (MIT), CONTRIBUTING.md, CHANGELOG.md, `.gitattributes`, `.mailmap`, and
  a CI workflow covering Python 3.10 through 3.14, packaging, and a check that no
  API key is ever committed.

### Fixed
- **Deduplication now uses Scholar's own `result_id`**, present on 20/20 of a live
  payload and previously discarded. Exact identity replaces a title-and-surname guess.
- **DOIs are recovered from publisher URLs** where they are embedded (3 of 20 live
  Scholar links), flagged `derived`. This is the key that merges a Scholar row with
  an OpenAlex row for the same paper.
- **Publisher markup no longer reaches exports.** A live OpenAlex fetch returned the
  title `Fitting Linear Mixed-Effects Models Using <b>lme4</b>`, which would have gone
  verbatim into a `.bib` file.
- **OpenAlex defaults to searching title and abstract, not full text.** The generic
  `search` parameter returned *R: A Language and Environment for Statistical Computing*
  as the top hit for "large language models evaluation". Title+abstract returned five
  relevant results out of five.
- **Selecting two sources at once raised `TypeError`.** `sources.search` hands one
  keyword set to every source and Scholar's fetch had no catch-all. Both now tolerate
  the others' options, with a test per source.
- The GUI's catch-all error handler hid the traceback from the browser and also from
  the server log, leaving a real `TypeError` with no trace anywhere. It now logs
  server-side while still not rendering internals to the browser.

### Changed
- Default source is OpenAlex. Google Scholar remains available and is documented with
  its two problems: its ranking is not reproducible, which conflicts with PRISMA, and
  Google sued SerpAPI in December 2025 over the scraping this path depends on.
- `fetch_google_scholar_results` and the CLI moved from `.manifest.json` to the richer
  `.search-record.json`.
- `FetchReport` and `FetchError` moved to `scholar_fetcher/report.py` and are shared by
  both sources. Still importable from `scholar_fetcher.fetch`.
- `process_results` remains the Scholar normalizer; row extraction now lives with each source.

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

Initial notebook (then named `Google_Scholar_Results_Fetcher.ipynb`, now
`scholar_fetcher.ipynb`): fetch, process, and
save Google Scholar results to Excel, run in Colab.

[Unreleased]: https://github.com/maliyuam/scholar-fetcher/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/maliyuam/scholar-fetcher/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/maliyuam/scholar-fetcher/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/maliyuam/scholar-fetcher/releases/tag/v0.2.0
