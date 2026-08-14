"""Streamlit GUI for the Google Scholar Fetcher.

Replaces the notebook's input() prompts with a form, shows live progress, renders
a sortable results table, and offers one-click export to Excel, CSV, BibTeX, and
RIS. Run with:  streamlit run streamlit_app.py

Results are held in st.session_state. Streamlit re-runs the whole script on every
widget interaction, and a download button is a widget: with the results in local
variables inside `if submitted:`, clicking one export wiped the table and the
other three buttons, so getting a second format meant paying for a second fetch
that could return a different result set.
"""

import io

import pandas as pd
import streamlit as st

from scholar_fetcher.config import get_api_key, DEFAULT_SLEEP
from scholar_fetcher.fetch import fetch_google_scholar_results, FetchError
from scholar_fetcher.process import process_results, dedup_results, FIELDNAMES
from scholar_fetcher.export import (
    generate_file_name,
    to_excel,
    to_csv,
    to_bibtex,
    to_ris,
)

st.set_page_config(page_title="Scholar Fetcher", page_icon="📖", layout="wide")
st.title("📖 Google Scholar Fetcher")
st.caption("Search Google Scholar, rank by citations, export to your reference manager.")

# --- key check up front, with an actionable message instead of a stack trace ---
try:
    get_api_key()
    key_ok = True
except ValueError as exc:
    key_ok = False
    st.error(str(exc))

with st.form("search"):
    col1, col2, col3 = st.columns([3, 1, 1])
    query = col1.text_input("Search query", placeholder='e.g. "large language models" AND evaluation')
    num_results = col2.number_input("Results", min_value=1, max_value=1000, value=50, step=10)
    # min 1s: a zero delay against a rate-limited API also flattens the retry
    # backoff, which is sleep_interval * attempt.
    sleep_interval = col3.number_input("Delay (s)", min_value=1, max_value=30, value=DEFAULT_SLEEP)
    remove_dupes = st.checkbox(
        "Remove duplicate works (collapses repeats across pages, keeps the best-attested copy)",
        value=True,
    )
    submitted = st.form_submit_button("Fetch results", disabled=not key_ok)

if submitted:
    if not query.strip():
        st.warning("Enter a search query first.")
        st.stop()

    bar = st.progress(0.0, text="Fetching…")

    def _progress(collected, target):
        bar.progress(min(collected / target, 1.0), text=f"Fetched {collected} of {target}…")

    report = None
    try:
        with st.spinner("Talking to Google Scholar…"):
            report = fetch_google_scholar_results(
                query, int(num_results), sleep_interval=int(sleep_interval), progress=_progress
            )
    except FetchError as exc:
        # Terminal SerpAPI failure (bad key, exhausted quota). Keep whatever was
        # already paid for, but never present it as a finished search.
        report = exc.report
        st.error(f"Fetch stopped early: {exc}")
    except Exception as exc:  # noqa: BLE001 — never render a traceback to the browser
        st.error(f"Fetch failed: {type(exc).__name__}. See the server log for details.")
        st.stop()
    finally:
        bar.empty()

    papers = process_results(report.results)
    collected = len(papers)

    dropped = 0
    if remove_dupes:
        papers, dropped = dedup_results(papers)

    # Truncate only now, after dedup, so surplus rows already fetched can fill
    # the gap left by removed duplicates instead of being paid for twice.
    papers = sorted(
        papers,
        key=lambda p: (p.get("Citations") is not None, p.get("Citations") or 0),
        reverse=True,
    )[: int(num_results)]

    st.session_state["result"] = {
        "query": query,
        "papers": papers,
        "requested": report.requested,
        "collected": collected,
        "dropped": dropped,
        "deduped": remove_dupes,
        "pages_failed": report.pages_failed,
        "failed_offsets": report.failed_offsets,
    }

# --- render from session state, so a download never triggers a re-fetch -------
result = st.session_state.get("result")

if result and not result["papers"]:
    st.warning("No results found. Try a broader query, or check your API quota.")
elif result:
    papers = result["papers"]

    # rows requested / collected / dropped / delivered — reported, never silent.
    st.success(
        f"Requested {result['requested']} · fetched {result['collected']}"
        + (f" · dropped {result['dropped']} duplicate(s)" if result["deduped"]
           else " · duplicates not removed")
        + f" · showing {len(papers)}"
    )
    if result["pages_failed"]:
        st.warning(
            f"{result['pages_failed']} page(s) failed at offset(s) "
            f"{result['failed_offsets']}. This result set is incomplete — treat the "
            f"counts above as a floor, not a total."
        )
    if len(papers) < result["requested"] and not result["pages_failed"]:
        st.info(
            f"Google Scholar returned fewer results than requested "
            f"({len(papers)} of {result['requested']}); the query is exhausted."
        )

    # width="stretch" rather than use_container_width, which Streamlit deprecated
    # with a removal date of 2025-12-31. Needs Streamlit >= 1.49 (pinned in pyproject).
    st.dataframe(pd.DataFrame(papers, columns=FIELDNAMES), width="stretch",
                 hide_index=True)

    st.subheader("Export")
    e1, e2, e3, e4 = st.columns(4)
    name = lambda ext: generate_file_name(result["query"], ext)  # noqa: E731

    e1.download_button("Excel (.xlsx)", to_excel(papers, io.BytesIO()).getvalue(),
                       file_name=name("xlsx"),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    e2.download_button("CSV (.csv)", to_csv(papers),
                       file_name=name("csv"), mime="text/csv")
    e3.download_button("BibTeX (.bib)", to_bibtex(papers),
                       file_name=name("bib"), mime="application/x-bibtex")
    e4.download_button("RIS (.ris)", to_ris(papers),
                       file_name=name("ris"), mime="application/x-research-info-systems")
