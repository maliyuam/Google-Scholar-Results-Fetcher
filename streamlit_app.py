"""Streamlit GUI for the scholar fetcher.

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
import traceback

import pandas as pd
import streamlit as st

from scholar_fetcher.config import get_api_key, scholar_enabled, DEFAULT_SLEEP
from scholar_fetcher.process import dedup_results, FIELDNAMES
from scholar_fetcher.report import FetchError
from scholar_fetcher.sources import SOURCE_NAMES, get_source, search
from scholar_fetcher.export import (
    generate_file_name,
    to_excel,
    to_csv,
    to_bibtex,
    to_ris,
)

st.set_page_config(page_title="Scholar Fetcher", page_icon="📖", layout="wide")
st.title("📖 Scholar Fetcher")
st.caption("Search scholarly literature, deduplicate across sources, export a citable corpus.")

# Scholar is opt-in for the web interface. This app has no authentication and no
# rate limiting, so a hosted copy holding a SerpAPI key would let every visitor
# spend the owner's quota. SCHOLAR_ENABLED must be set on purpose.
scholar_on = scholar_enabled()
available = [name for name in SOURCE_NAMES if name != "scholar" or scholar_on]

# Only the Scholar source needs a key, so a missing key is a warning about one
# source rather than a reason to disable the whole form.
try:
    get_api_key()
    key_ok = True
    key_problem = ""
except ValueError as exc:
    key_ok = False
    key_problem = str(exc)

with st.form("search"):
    chosen = st.multiselect(
        "Sources",
        options=available,
        default=["openalex"],
        help="\n\n".join(f"**{n}** — {get_source(n).description}" for n in available),
    )

    col1, col2, col3 = st.columns([3, 1, 1])
    query = col1.text_input("Search query",
                            placeholder='e.g. "large language models" AND evaluation')
    num_results = col2.number_input("Results", min_value=1, max_value=1000, value=50, step=10)
    # min 1s: a zero delay against a rate-limited API also flattens the retry
    # backoff, which is sleep_interval * attempt.
    sleep_interval = col3.number_input("Delay (s)", min_value=1, max_value=30, value=DEFAULT_SLEEP)

    col4, col5 = st.columns(2)
    search_field = col4.selectbox(
        "Match terms in", options=["title-abstract", "fulltext"], index=0,
        help="title-abstract is what bibliographic databases search by default. "
             "fulltext has higher recall and much lower precision.",
    )
    mailto = col5.text_input("Contact email (OpenAlex polite pool)", placeholder="you@uni.edu")

    remove_dupes = st.checkbox(
        "Remove duplicate works (matches on record id, DOI, then title and first author)",
        value=True,
    )
    submitted = st.form_submit_button("Search")

if not scholar_on:
    st.info(
        "**OpenAlex is ready to use — it needs no key.** Google Scholar is switched off "
        "here: it is a paid source, and this app has no authentication in front of it, so "
        "a hosted copy would let any visitor spend the owner's quota. To enable it on a "
        "machine you control, set `SCHOLAR_ENABLED=1` alongside your `SERPAPI_API_KEY`."
    )
elif not key_ok:
    st.warning(
        f"Google Scholar is enabled but has no API key, so it cannot be used. {key_problem}"
    )

if submitted:
    if not query.strip():
        st.warning("Enter a search query first.")
        st.stop()
    if not chosen:
        st.warning("Pick at least one source.")
        st.stop()
    if "scholar" in chosen and not key_ok:
        st.error("Google Scholar is selected but no API key is set. Remove it or add a key.")
        st.stop()

    bar = st.progress(0.0, text="Searching…")

    def _progress(collected, target):
        bar.progress(min(collected / target, 1.0), text=f"Fetched {collected} of {target}…")

    try:
        with st.spinner("Searching…"):
            rows, reports = search(
                query, int(num_results), tuple(chosen),
                sleep_interval=int(sleep_interval), progress=_progress,
                mailto=mailto or None, search_field=search_field,
            )
    except FetchError as exc:
        st.error(f"Search stopped early: {exc}")
        st.stop()
    except Exception as exc:  # noqa: BLE001 — never render a traceback to the browser
        # Hidden from the browser, but it has to land somewhere: swallowing it
        # entirely left a real TypeError with no trace anywhere to find it.
        traceback.print_exc()
        st.error(f"Search failed: {type(exc).__name__}. See the server log for details.")
        st.stop()
    finally:
        bar.empty()

    identified = len(rows)
    dropped = 0
    if remove_dupes:
        rows, dropped = dedup_results(rows)
    after_dedup = len(rows)

    # Truncate only now, after dedup, so surplus rows already fetched can fill
    # the gap left by removed duplicates instead of being paid for twice.
    rows = sorted(
        rows,
        key=lambda p: (p.get("Citations") is not None, p.get("Citations") or 0),
        reverse=True,
    )[: int(num_results)]

    st.session_state["result"] = {
        "query": query,
        "rows": rows,
        "identified": identified,
        "dropped": dropped,
        "after_dedup": after_dedup,
        "deduped": remove_dupes,
        "requested": int(num_results),
        "reports": [
            {"source": r.source, "requested": r.requested, "returned": r.collected,
             "pages_failed": r.pages_failed, "failed_offsets": r.failed_offsets,
             "complete": r.complete}
            for r in reports
        ],
    }

# --- render from session state, so a download never triggers a re-search -----
result = st.session_state.get("result")

if result and not result["rows"]:
    st.warning("No results found. Try a broader query or a different source.")
elif result:
    rows = result["rows"]

    st.success(
        f"Identified {result['identified']}"
        + (f" · removed {result['dropped']} duplicate(s)" if result["deduped"]
           else " · duplicates not removed")
        + f" · showing {len(rows)} of {result['requested']} requested"
    )

    with st.expander("Per-source detail"):
        st.dataframe(pd.DataFrame(result["reports"]), width="stretch", hide_index=True)

    for report in result["reports"]:
        if not report["complete"]:
            st.warning(
                f"{report['source']} lost {report['pages_failed']} page(s) at "
                f"{report['failed_offsets']}. This result set is incomplete: treat the "
                f"counts above as a floor, not a total."
            )

    st.dataframe(pd.DataFrame(rows, columns=FIELDNAMES), width="stretch", hide_index=True)

    st.subheader("Export")
    e1, e2, e3, e4 = st.columns(4)
    name = lambda ext: generate_file_name(result["query"], ext)  # noqa: E731

    e1.download_button("Excel (.xlsx)", to_excel(rows, io.BytesIO()).getvalue(),
                       file_name=name("xlsx"),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    e2.download_button("CSV (.csv)", to_csv(rows),
                       file_name=name("csv"), mime="text/csv")
    e3.download_button("BibTeX (.bib)", to_bibtex(rows),
                       file_name=name("bib"), mime="application/x-bibtex")
    e4.download_button("RIS (.ris)", to_ris(rows),
                       file_name=name("ris"), mime="application/x-research-info-systems")
