# Running the app

The notebook still works as-is. This is the same logic lifted into a tested
package with a graphical interface.

## Setup

```sh
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env and paste your SerpAPI key
```

## Launch the GUI

```sh
streamlit run streamlit_app.py
```

Enter a query, choose how many results, and fetch. Results are ranked by
citation count and exportable to **Excel, CSV, BibTeX, or RIS** (BibTeX/RIS
import straight into Zotero, Mendeley, or EndNote).

## Use the library directly

```python
from scholar_fetcher import fetch_google_scholar_results, process_results, dedup_results, save

raw = fetch_google_scholar_results("large language models", 50)
papers = process_results(raw)
papers, dropped = dedup_results(papers)   # optional; reports rows dropped
save(papers, "results.bib", fmt="bib")
```

## Tests

```sh
pytest -q
```

The tests cover processing, deduplication, and all export formats using a
recorded fixture — they run on the standard library alone (no API key, no
network, no pandas needed).

## What changed from the notebook

- Runs anywhere (key from `.env`/environment, not `google.colab.userdata`).
- Per-page retry with backoff, so a transient failure no longer silently
  truncates the result set.
- Optional deduplication that reports how many rows it dropped.
- Export to CSV / BibTeX / RIS in addition to Excel.
- A graphical form and results table instead of `input()` prompts.

## Not yet done (next phase)

- OpenAlex as a free primary source (removes the paid-API dependency).
- Real abstracts / venue / year enrichment with per-value source flags.
- Saved searches and run history.
