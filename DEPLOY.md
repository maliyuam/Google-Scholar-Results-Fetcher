# Deploying, testing, and sharing this

Three separate things, in increasing order of commitment. You can do any one without
the others.

| Goal | Route | Cost | Reversible? |
|---|---|---|---|
| Someone runs it in a browser, no install | Streamlit Community Cloud | Free | Yes, delete the app |
| Someone installs it: `pip install scholar-fetcher` | PyPI | Free | **No** — a version number can never be reused |
| Someone reads what changed | GitHub Release | Free | Yes, delete the release |

**The thing that makes all of this easy:** OpenAlex needs no API key. A public deploy with
zero secrets configured is fully functional. Verified: a clean `git clone` with no `.env`
runs a 50-result search and exports it.

---

## 1. Host the GUI (Streamlit Community Cloud)

Free, and the fastest way to let someone try it without installing anything.

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → pick `maliyuam/scholar-fetcher`, branch `main`,
   main file `streamlit_app.py`.
3. Under **Advanced settings**, set Python version to **3.11** or newer. The package
   requires 3.10+ and will fail to import below that.
4. Deploy.

### Do not add your SerpAPI key to the deployed app

This is the one decision that matters. If you put `SERPAPI_API_KEY` into the app's
secrets, **every visitor spends your paid quota**, and there is no rate limiting or
authentication in front of it. A single person looping searches could drain the plan.

Leave secrets empty. The app runs on OpenAlex, which needs no key.

There is a second lock on this. The Google Scholar source is hidden from the web
interface unless `SCHOLAR_ENABLED` is explicitly set, **even when a valid key is
present**. So a key alone is not enough to expose the paid source: you would have to set
two things on purpose. Locally, add both to your `.env`:

```
SERPAPI_API_KEY=your_real_key
SCHOLAR_ENABLED=1
```

The CLI and the library ignore the flag. Whoever runs those already owns the key.

### Optional: a contact address for OpenAlex

Set this in the app's secrets to join OpenAlex's polite pool (higher rate limits). It is
an email address, not a credential:

```toml
OPENALEX_MAILTO = "you@example.edu"
```

---

## 2. Publish to PyPI

After this, anyone can run:

```bash
pip install scholar-fetcher
scholar-fetch --query "large language models" --num 50 --format bib
```

The name `scholar-fetcher` was free as of 2026-08-14.

**PyPI publishing is permanent.** You cannot re-upload a version number, and you cannot
fully delete a release. Get it right the first time.

### One-time setup: Trusted Publishing

This repo's `.github/workflows/publish.yml` uses PyPI Trusted Publishing (OIDC), so **no
API token is stored anywhere**. Nothing to leak, nothing to rotate.

1. Create an account at [pypi.org](https://pypi.org) if you have none.
2. Go to [Publishing settings](https://pypi.org/manage/account/publishing/) →
   **Add a new pending publisher**:

   | Field | Value |
   |---|---|
   | PyPI project name | `scholar-fetcher` |
   | Owner | `maliyuam` |
   | Repository name | `scholar-fetcher` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. In GitHub → Settings → Environments, create an environment named `pypi`. Add yourself
   as a required reviewer if you want a manual approval gate before each upload.

### Releasing

```bash
# 1. bump the version in scholar_fetcher/__init__.py
# 2. move the CHANGELOG [Unreleased] entries under the new version
git commit -am "Release v0.3.1"
git tag -a v0.3.1 -m "v0.3.1"
git push origin main v0.3.1
```

The tag push runs the workflow, which refuses to publish if the tests fail **or if the tag
does not match `__version__`**. A version number that lies about its own contents is worse
than no release.

### Try it first on TestPyPI

If you want a dry run, register the same trusted publisher at
[test.pypi.org](https://test.pypi.org) and add `repository-url:
https://test.pypi.org/legacy/` to the publish step. TestPyPI accepts throwaway versions.

---

## 3. Cut a GitHub Release

Makes the `v0.3.0` tag a proper release page with notes, and gives people a download.

```bash
gh release create v0.3.0 --title "v0.3.0" --notes-file CHANGELOG.md --verify-tag
```

Or write shorter notes by hand; the changelog is long.

---

## 4. How other people test it

Everything below runs with **no API key and no network**.

```bash
git clone https://github.com/maliyuam/scholar-fetcher.git
cd scholar-fetcher
pip install -e ".[dev,excel]"
pytest -q            # 128 tests
```

CI already runs this on every push and pull request across Python 3.10–3.14, plus a
packaging job and a check that no API key is ever committed. The badge in the README shows
the current state, so a stranger can see it is green without running anything.

To try the tool for real without any credentials:

```bash
python -m scholar_fetcher --query "crispr gene editing ethics" --num 20 --format bib
```

That hits OpenAlex, needs no key, and writes both the `.bib` and a `.search-record.json`
next to it.

---

## What is deliberately not automated

- **Publishing on every push.** Only a version tag publishes, and only after the tests pass.
- **A key in the public app.** See above. This is a cost and abuse decision, not a
  technical one.
- **Deleting anything.** Neither workflow removes a release, a tag, or a deployed app.
