"""Processing layer — cell 5 of the notebook, kept faithful, plus opt-in dedup.

process_results produces exactly the six columns the notebook produced, from the
same fields, so a lifted run reproduces the notebook's output 1:1.

dedup_results is provided separately and is NOT applied automatically: Scholar
repeats entries across paginated pages, but collapsing them changes the row
count, so the caller decides (and reports rows dropped).
"""

import re


def _to_int(value) -> int:
    """Coerce a citation count to int; anything missing/non-numeric becomes 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def process_results(results: list[dict]) -> list[dict]:
    """Flatten raw SerpAPI results into rows. Faithful to the notebook."""
    papers = []
    for result in results:
        title = result.get("title", "N/A")
        authors = result.get("publication_info", {}).get("authors", [])
        citation = result.get("inline_links", {}).get("cited_by", {}).get("total", "N/A")
        url = result.get("link", "N/A")
        abstract = result.get("snippet", "N/A")   # NOTE: this is Scholar's snippet, not the full abstract
        doi = result.get("inline_links", {}).get("doi", "N/A")

        authors_str = ", ".join(author.get("name", "N/A") for author in authors)

        papers.append({
            "Title": title,
            "Authors": authors_str,
            "Citations": _to_int(citation) if citation != "N/A" else 0,
            "URL": url,
            "Abstract": abstract,
            "DOI": doi,
        })
    return papers


def _dedup_key(paper: dict) -> str:
    """Prefer a real DOI; else a normalized title (lowercased, alnum only)."""
    doi = paper.get("DOI", "N/A")
    if doi and doi != "N/A":
        return f"doi:{doi.strip().lower()}"
    title = paper.get("Title", "") or ""
    return "title:" + re.sub(r"[^a-z0-9]", "", title.lower())


def dedup_results(papers: list[dict]) -> tuple[list[dict], int]:
    """Collapse duplicate works, keeping the copy with the highest citation count.

    Returns (deduped_papers, n_dropped) so the caller can report rows dropped.
    Order of first appearance is preserved.
    """
    best: dict[str, dict] = {}
    order: list[str] = []
    for paper in papers:
        key = _dedup_key(paper)
        if key not in best:
            best[key] = paper
            order.append(key)
        elif paper.get("Citations", 0) > best[key].get("Citations", 0):
            best[key] = paper

    deduped = [best[k] for k in order]
    return deduped, len(papers) - len(deduped)
