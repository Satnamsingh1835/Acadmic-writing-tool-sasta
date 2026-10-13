from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from research_library.store import ResearchLibrary


class DiscoveryError(RuntimeError):
    """A public metadata provider could not satisfy a request."""


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not isinstance(index, dict):
        return ""
    positioned: dict[int, str] = {}
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            try:
                positioned[int(position)] = word
            except (TypeError, ValueError):
                continue
    return " ".join(positioned[position] for position in sorted(positioned))


def normalize_crossref(item: dict[str, Any]) -> dict[str, Any]:
    title = (item.get("title") or [""])[0] if isinstance(item.get("title"), list) else item.get("title", "")
    authors = []
    for author in item.get("author") or []:
        if isinstance(author, dict):
            name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
            if name:
                authors.append(name)
    issued = item.get("published-print") or item.get("published-online") or item.get("issued") or {}
    date_parts = issued.get("date-parts") or [[None]]
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    return {
        "title": title or "",
        "authors": authors,
        "year": year,
        "doi": item.get("DOI") or "",
        "item_type": item.get("type") or "unknown",
        "publication": (item.get("container-title") or [""])[0],
        "abstract": re.sub(r"<[^>]+>", " ", item.get("abstract") or "").strip(),
        "url": item.get("URL") or "",
        "source": "crossref",
        "source_url": item.get("URL") or "",
        "access_status": "metadata_only",
        "metadata_verified": False,
        "raw": item,
    }


def normalize_openalex(item: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for authorship in item.get("authorships") or []:
        author = authorship.get("author") or {}
        if author.get("display_name"):
            authors.append(author["display_name"])
    doi = item.get("doi") or ""
    return {
        "title": item.get("display_name") or "",
        "authors": authors,
        "year": item.get("publication_year"),
        "doi": doi,
        "item_type": item.get("type") or "unknown",
        "publication": ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
        "abstract": _abstract_from_inverted_index(item.get("abstract_inverted_index")),
        "url": item.get("doi") or item.get("id") or "",
        "source": "openalex",
        "source_url": item.get("id") or "",
        "access_status": "metadata_only",
        "metadata_verified": False,
        "raw": item,
    }


class DiscoveryService:
    """Bounded, cached metadata discovery; full text is never implied."""

    def __init__(
        self,
        library: ResearchLibrary,
        *,
        transport: httpx.BaseTransport | None = None,
        attempts: int = 2,
        timeout: float = 8.0,
    ):
        self.library = library
        self.attempts = max(1, min(attempts, 3))
        self.client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 4.0)),
            headers={"User-Agent": "ScholarFlow/0.1 (local academic research tool)"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.client.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self.attempts:
                        try:
                            delay = min(2.0, float(response.headers.get("Retry-After", "0.5")))
                        except ValueError:
                            delay = 0.5
                        time.sleep(max(0.0, delay))
                        continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self.attempts:
                    time.sleep(0.2 * (attempt + 1))
        raise DiscoveryError(
            "Metadata provider unavailable after bounded retries. Try again later or use cached results."
        ) from last_error

    def search(
        self, provider: str, query: str, *, limit: int = 10, offline: bool = False
    ) -> dict[str, Any]:
        if provider not in {"crossref", "openalex"}:
            raise ValueError("Provider must be crossref or openalex.")
        query = query.strip()
        if len(query) < 2:
            raise ValueError("Search query must contain at least two characters.")
        limit = max(1, min(int(limit), 25))
        key = hashlib.sha256(f"{provider}\n{query.casefold()}\n{limit}".encode()).hexdigest()
        cache_key = provider + ":" + key
        cached = self.library.get_cache(cache_key, allow_stale=True)
        if offline:
            return {
                "provider": provider,
                "status": "cached_offline" if cached is not None else "offline_cache_miss",
                "results": cached or [],
            }
        if cached is not None:
            return {"provider": provider, "status": "cached", "results": cached}
        if provider == "crossref":
            payload = self._get_json(
                "https://api.crossref.org/works",
                {"query.bibliographic": query, "rows": limit},
            )
            message = payload.get("message") or {}
            results = [normalize_crossref(x) for x in message.get("items", []) if isinstance(x, dict)]
        else:
            payload = self._get_json(
                "https://api.openalex.org/works",
                {"search": query, "per-page": limit},
            )
            results = [normalize_openalex(x) for x in payload.get("results", []) if isinstance(x, dict)]
        results = [item for item in results if item.get("title")]
        self.library.put_cache(cache_key, provider, results)
        return {"provider": provider, "status": "live", "results": results}

    def verify_doi(self, doi: str) -> dict[str, Any]:
        normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.I).strip().lower()
        normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.I)
        if not normalized or len(normalized) > 300 or any(ch.isspace() for ch in normalized):
            raise ValueError("Provide a valid DOI identifier.")
        key = "crossref-doi:" + hashlib.sha256(normalized.encode()).hexdigest()
        cached = self.library.get_cache(key, allow_stale=True)
        if cached is not None:
            return cached
        payload = self._get_json("https://api.crossref.org/works/" + quote(normalized, safe=""))
        item = (payload.get("message") or {})
        result_doi = str(item.get("DOI") or "").strip().lower()
        if result_doi != normalized:
            result = {
                "status": "not_verified",
                "doi": normalized,
                "warning": "The returned metadata did not match the requested DOI exactly.",
                "record": None,
            }
        else:
            result = {
                "status": "metadata_match",
                "doi": normalized,
                "warning": (
                    "Crossref metadata matched this DOI. This does not verify that the work "
                    "supports any particular claim, nor does it mean the full text was read."
                ),
                "record": normalize_crossref(item),
            }
        self.library.put_cache(key, "crossref", result)
        return result
