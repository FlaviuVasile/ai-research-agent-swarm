"""Real OpenAlex results with bounded retries and no generated citation metadata."""
import asyncio
import re
from urllib.parse import quote
from dataclasses import dataclass
import httpx

class OpenAlexError(RuntimeError):
    pass

@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    authors: tuple[str, ...]
    year: int | None
    doi: str | None

class OpenAlexClient:
    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def search(self, query: str, limit: int) -> list[Paper]:
        params: dict[str, str | int] = {
            "search": query[:300], "per-page": limit,
            "select": "id,title,authorships,publication_year,doi",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        async with httpx.AsyncClient(timeout=25) as client:
            for attempt in range(3):
                try:
                    response = await client.get("https://api.openalex.org/works", params=params)
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                        raise ValueError("Missing results array")
                    papers: list[Paper] = []
                    seen: set[str] = set()
                    for item in payload["results"]:
                        if not isinstance(item, dict):
                            raise ValueError("Invalid work record")
                        identifier = item.get("id", "")
                        title = item.get("title")
                        if (not isinstance(identifier, str) or not re.fullmatch(r"https://openalex\.org/W\d+", identifier)
                                or not isinstance(title, str) or not title.strip() or identifier in seen):
                            continue
                        seen.add(identifier)
                        doi = item.get("doi")
                        if not isinstance(doi, str) or not doi.startswith("https://doi.org/"):
                            doi = None
                        elif doi:
                            doi = quote(doi, safe=":/.-_")
                        authorships = item.get("authorships") or []
                        if not isinstance(authorships, list):
                            raise ValueError("Invalid authorships")
                        authors = tuple(a["author"]["display_name"] for a in authorships
                                        if isinstance(a, dict) and isinstance(a.get("author"), dict)
                                        and isinstance(a["author"].get("display_name"), str)
                                        and a["author"]["display_name"].strip())
                        year = item.get("publication_year")
                        if type(year) is not int or not 1000 <= year <= 9999:
                            year = None
                        papers.append(Paper(identifier, title, authors, year, doi))
                    return papers[:limit]
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise OpenAlexError("OpenAlex could not be reached after three attempts.") from None
                except (httpx.HTTPStatusError, ValueError, TypeError, KeyError):
                    # Do not include request URLs: query parameters can contain the API key.
                    raise OpenAlexError("OpenAlex rejected the request or returned invalid data. "
                                        "Check its service status, API key, and quota.") from None
        raise OpenAlexError("OpenAlex search failed.")
