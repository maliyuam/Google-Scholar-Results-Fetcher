"""Streamlit GUI for the Google Scholar Fetcher.

Replaces the notebook's three input() prompts with a form, shows live progress,
renders a sortable results table, and offers one-click export to Excel, CSV,
BibTeX, and RIS. Run with:  streamlit run streamlit_app.py
"""

import io

import pandas as pd
import streamlit as st

from scholar_fetcher.config import get_api_key, DEFAULT_SLEEP
from scholar_fetcher.fetch import fetch_google_scholar_results
from scholar_fetcher.process import process_results, dedup_results
from scholar_fetcher.export import (
    generate_file_name,
    to_csv,
    to_bibtex,
    to_ris,
    FIELDNAMES,
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
    sleep_interval = col3.number_input("Delay (s)", min_value=0, max_value=30, value=DEFAULT_SLEEP)
    remove_dupes = st.checkbox(
        "Remove duplicate works (collapses repeats across pages, keeps highest citation count)",
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

    with st.spinner("Talking to Google Scholar…"):
        raw = fetch_google_scholar_results(
            query, int(num_results), sleep_interval=int(sleep_interval), progress=_progress
        )
    bar.empty()

    papers = process_results(raw)
    rows_in = len(papers)
    dropped = 0
    if remove_dupes:
        papers, dropped = dedup_results(papers)

    if not papers:
        st.warning("No results found. Try a broader query, or check your API quota.")
        st.stop()

    papers = sorted(papers, key=lambda p: p.get("Citations", 0), reverse=True)

    # rows in / out / dropped — reported, never silent
    st.success(
        f"Fetched {rows_in} rows · kept {len(papers)}"
        + (f" · dropped {dropped} duplicate(s)" if remove_dupes else " · duplicates not removed")
    )

    df = pd.DataFrame(papers, columns=FIELDNAMES)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # --- exports ---
    st.subheader("Export")
    e1, e2, e3, e4 = st.columns(4)

    xlsx_buf = io.BytesIO()
    df.to_excel(xlsx_buf, index=False)
    e1.download_button("Excel (.xlsx)", xlsx_buf.getvalue(),
                       file_name=generate_file_name(query, "xlsx"),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    e2.download_button("CSV (.csv)", to_csv(papers),
                       file_name=generate_file_name(query, "csv"), mime="text/csv")
    e3.download_button("BibTeX (.bib)", to_bibtex(papers),
                       file_name=generate_file_name(query, "bib"), mime="application/x-bibtex")
    e4.download_button("RIS (.ris)", to_ris(papers),
                       file_name=generate_file_name(query, "ris"), mime="application/x-research-info-systems")
