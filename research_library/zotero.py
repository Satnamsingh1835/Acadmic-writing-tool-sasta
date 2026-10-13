from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

from research_library.importers import csl_to_work
from research_library.store import ResearchLibrary


class ZoteroConnectionError(RuntimeError):
    """Readable Zotero connectivity or configuration failure."""


def _headers(api_key: str = "") -> dict[str, str]:
    headers = {
        "Zotero-API-Version": "3",
        "User-Agent": "ScholarFlow/0.1 (local researcher-controlled client)",
        "Accept": "application/json",
    }
    if api_key:
        headers["Zotero-API-Key"] = api_key
    return headers


def fetch_zotero_items(
    *,
    source: str = "local",
    collection_key: str | None = None,
    limit: int = 100,
    max_pages: int = 20,
    user_id: str | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict[str, Any]]:
    """Read Zotero items through its documented local or Web API (never writes)."""
    if source not in {"local", "web"}:
        raise ValueError("Source must be 'local' or 'web'.")
    page_size = max(1, min(int(limit), 100))
    if source == "local":
        base = "http://127.0.0.1:23119/api"
        library_path = "users/0"
        api_key = ""
    else:
        user_id = user_id or os.getenv("ZOTERO_USER_ID", "").strip()
        api_key = api_key or os.getenv("ZOTERO_API_KEY", "").strip()
        if not user_id:
            raise ZoteroConnectionError(
                "Set ZOTERO_USER_ID before importing a private Zotero Web library."
            )
        if not user_id.isdigit():
            raise ZoteroConnectionError("ZOTERO_USER_ID must be the numeric Zotero user ID.")
        base = "https://api.zotero.org"
        library_path = "users/" + user_id
        if not api_key:
            raise ZoteroConnectionError(
                "Set ZOTERO_API_KEY for a private Zotero Web library. Keep it outside Git."
            )
    endpoint = (
        library_path + "/collections/" + quote(collection_key, safe="") + "/items"
        if collection_key
        else library_path + "/items"
    )
    found: list[dict[str, Any]] = []
    try:
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(10.0, connect=4.0),
            headers=_headers(api_key or ""),
        ) as client:
            for page in range(max(1, min(max_pages, 20))):
                response = client.get(
                    base + "/" + endpoint,
                    params={"format": "json", "limit": page_size, "start": page * page_size},
                )
                if response.status_code == 403:
                    raise ZoteroConnectionError(
                        "Zotero returned 403. For the local API, enable Settings → Advanced → "
                        "'Allow other applications on this computer to communicate with Zotero'."
                    )
                if response.status_code in (401, 404):
                    raise ZoteroConnectionError(
                        "Zotero library was not found or the Web API credentials were rejected."
                    )
                response.raise_for_status()
                batch = response.json()
                if not isinstance(batch, list):
                    raise ZoteroConnectionError("Zotero returned an unexpected response format.")
                found.extend(batch)
                # The Web API provides Total-Results; some compatible local API versions may not.
                # If the header is absent, continue while the page is full, up to max_pages.
                total_header = response.headers.get("Total-Results")
                if total_header is not None:
                    try:
                        if len(found) >= int(total_header):
                            break
                    except ValueError:
                        pass
                if len(batch) < page_size:
                    break
    except ZoteroConnectionError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise ZoteroConnectionError(
            "Could not read Zotero. Check that Zotero Desktop is open with its local API enabled, "
            "or check the configured Web API access. No library contents were logged."
        ) from exc
    return found


def _zotero_record(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    item_type = str(data.get("itemType") or "").casefold()
    if item_type in {"attachment", "note", "annotation", "highlight"}:
        return None
    record = csl_to_work(
        {
            "title": data.get("title"),
            "author": [
                {"given": creator.get("firstName", ""), "family": creator.get("lastName", "")}
                for creator in data.get("creators", [])
                if isinstance(creator, dict)
                and (creator.get("firstName") or creator.get("lastName"))
            ],
            "year": (str(data.get("date") or "")[:4] or None),
            "DOI": data.get("DOI"),
            "type": item_type or "article",
            "container-title": data.get("publicationTitle") or data.get("bookTitle") or "",
            "abstract": data.get("abstractNote") or "",
            "URL": data.get("url") or "",
            "key": item.get("key") or data.get("key") or "",
            "tags": data.get("tags") or [],
        },
        source="zotero_" + source,
    )
    return record if record["title"].strip() else None


def import_zotero_items(
    library: ResearchLibrary,
    *,
    source: str = "local",
    collection_key: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    items = fetch_zotero_items(source=source, collection_key=collection_key, limit=limit)
    imported = duplicates = skipped = 0
    for item in items:
        record = _zotero_record(item, source)
        if record is None:
            skipped += 1
            continue
        result = library.add_work(record)
        if result["created"]:
            imported += 1
        else:
            duplicates += 1
    return {
        "source": source,
        "collection_key": collection_key,
        "items_read": len(items),
        "imported": imported,
        "duplicates": duplicates,
        "skipped": skipped,
        "mode": "read_only",
    }
