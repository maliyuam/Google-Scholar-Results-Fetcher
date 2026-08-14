# Contributing

## Setup

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -e ".[dev,excel]"
cp .env.example .env        # only needed to hit the live API
```

## Tests

```bash
pytest -q
```

The suite needs **no API key and no network**. The fetch layer takes an injected
`search_factory` and the CLI takes an injected `fetcher`, so every failure path
(quota exhausted, rate limited, page lost, key leaked to stdout) is driven by a
fake client.

Only the four tests in `tests/test_excel.py` need pandas and openpyxl. They skip
automatically when pandas is absent, and CI asserts that they *skip* rather than
silently disappear. Keep them in that file: a module-level `importorskip` in
`tests/test_export.py` once swallowed the entire export module, so a pandas-free
run reported 55 passing tests instead of 78 and nobody noticed.

## What this project is careful about

This is research tooling. A corpus that is quietly wrong is worse than one that
loudly fails. Three rules follow from that, and a change that breaks them will
not be merged:

1. **Never fabricate a value.** A missing citation count is `None` with
   `Citations_source: missing`, never `0`. If you add a derived or inferred
   field, it carries its own source flag.
2. **Never lose rows silently.** Every filtering step reports rows in, rows out,
   and rows dropped. `FetchReport.complete` is false whenever a page was lost,
   and the CLI exits `3` so a script can react.
3. **Never weaken a test to make it pass.** If an assertion looks wrong, say why
   and stop. Two test-helper bugs have already been fixed this way rather than
   by loosening the check.

## Commits

- Present tense, imperative subject under ~70 characters.
- Explain **why** in the body, not just what. If the change fixes a defect,
  describe the failure it prevents.
- One logical change per commit.
- **No AI or assistant attribution markers.** No `Co-Authored-By` trailers for
  tools, no "Generated with" footers, no assistant names in commit messages, PR
  titles, or PR bodies. History should read as the work of its authors.
- Use one identity. Set it per-repo if your global config differs:

  ```bash
  git config user.name  "Your Name"
  git config user.email "you@example.com"
  ```

## Before opening a PR

```bash
pytest -q                       # green, nothing skipped that shouldn't be
python -m build && twine check dist/*
```

Update `CHANGELOG.md` under `## [Unreleased]`. If you changed a number that
appears in `README.md` (test counts, page size, column list), change it there too
and re-verify it rather than assuming.
