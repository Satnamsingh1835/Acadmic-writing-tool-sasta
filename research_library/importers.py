from __future__ import annotations

from typing import Any

from research_library.store import ResearchLibrary


def csl_to_work(item: dict[str, Any], *, source: str = "zotero_csl_json") -> dict[str, Any]:
    title = item.get("title") or ""
    authors = []
    for author in item.get("author") or item.get("authors") or []:
        if isinstance(author, str):
            authors.append(author)
        elif isinstance(author, dict):
            name = author.get("literal") or " ".join(
                part for part in (author.get("given"), author.get("family")) if part
            )
            if name:
                authors.append(name)
    year = None
    issued = item.get("issued", {})
    if isinstance(issued, dict):
        parts = (issued.get("date-parts") or [[None]])[0]
        if parts:
            year = parts[0]
    year = year or item.get("year")
    doi = item.get("DOI") or item.get("doi") or ""
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        "item_type": item.get("type") or item.get("itemType") or "article",
        "publication": item.get("container-title") or item.get("publicationTitle") or "",
        "abstract": item.get("abstract") or item.get("abstractNote") or "",
        "url": item.get("URL") or item.get("url") or "",
        "source": source,
        "zotero_key": item.get("key") or item.get("itemKey") or "",
        "tags": [
            tag.get("tag", "") if isinstance(tag, dict) else str(tag)
            for tag in item.get("tags", [])
        ],
        "subjects": item.get("subjects") or [],
        "raw": item,
        "access_status": "metadata_only",
        "metadata_verified": False,
    }


def import_csl_records(
    library: ResearchLibrary, records: list[dict[str, Any]]
) -> dict[str, int]:
    if not isinstance(records, list) or not records:
        raise ValueError("Provide a non-empty list of CSL JSON records.")
    if len(records) > 1000:
        raise ValueError("Import is limited to 1,000 records per batch.")
    imported = duplicates = skipped = 0
    for item in records:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            skipped += 1
            continue
        result = library.add_work(csl_to_work(item))
        if result["created"]:
            imported += 1
        else:
            duplicates += 1
    return {"imported": imported, "duplicates": duplicates, "skipped": skipped}
