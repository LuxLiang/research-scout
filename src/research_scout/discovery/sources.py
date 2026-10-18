"""Real literature adapters; responses retain source identity and coverage."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import json
import re
from urllib.parse import quote, unquote, urlparse
import xml.etree.ElementTree as ET

import httpx
from pydantic import Field

from research_scout.domain.models import Coverage, StrictModel, normalize_identifier


class SourcePaper(StrictModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None
    version: str | None = None
    aliases: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    published: date | None = None
    venue: str | None = None
    abstract: str | None = None
    text: str | None = None
    coverage: Coverage = Coverage.METADATA_ONLY
    labels: list[str] = Field(default_factory=list)
    provenance: str = "external metadata"


class InterestProfile(StrictModel):
    name: str = "default"
    arxiv_queries: list[str] = Field(default_factory=lambda: ["cat:cs.LG"])
    labels: list[str] = Field(default_factory=list)
    max_results: int = Field(default=20, ge=1, le=1000)

    @classmethod
    def load(cls, path: Path | str) -> InterestProfile:
        """JSON is also valid YAML; no optional parser needed for default profiles."""
        return cls.model_validate(json.loads(Path(path).read_text()))


def arxiv_identity(value: str) -> tuple[str, str | None] | None:
    value = unquote(value.strip())
    value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    value = re.sub(r"^https?://(?:export\.)?arxiv.org/(?:abs|pdf)/", "", value)
    value = value.removesuffix(".pdf")
    match = re.fullmatch(r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", value)
    return (match.group(1), match.group(2)) if match else None


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=45, follow_redirects=True,
                                  headers={"User-Agent": "ResearchScout/0.1 (literature research)"})


class ArxivClient:
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(self, client: httpx.Client | None = None):
        self.client = _client(client)

    def search(self, query: str, since: date | None = None,
               max_results: int = 20) -> list[SourcePaper]:
        if since:
            query = f"({query}) AND submittedDate:[{since:%Y%m%d}0000 TO 300001010000]"
        response = self.client.get(self.endpoint, params={
            "search_query": query, "max_results": max_results,
            "sortBy": "submittedDate", "sortOrder": "descending",
        })
        response.raise_for_status()
        return self._parse(response.text)

    def lookup(self, identifier: str) -> SourcePaper:
        identity = arxiv_identity(identifier)
        if not identity:
            raise ValueError(f"Invalid arXiv identifier: {identifier}")
        response = self.client.get(self.endpoint, params={"id_list": "".join(x or "" for x in identity)})
        response.raise_for_status()
        entries = self._parse(response.text)
        if not entries:
            raise LookupError(f"arXiv paper not found: {identifier}")
        return entries[0]

    @staticmethod
    def _parse(content: str) -> list[SourcePaper]:
        root = ET.fromstring(content)
        ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
        papers = []
        for entry in root.findall("a:entry", ns):
            ident = arxiv_identity(entry.findtext("a:id", "", ns))
            if not ident:
                continue
            abstract = " ".join(entry.findtext("a:summary", "", ns).split())
            doi = entry.findtext("x:doi", None, ns)
            papers.append(SourcePaper(
                title=" ".join(entry.findtext("a:title", "", ns).split()),
                authors=[a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)],
                arxiv_id=ident[0], version=ident[1] or "v1",
                doi=normalize_identifier(doi) if doi else None,
                urls=[link.attrib["href"] for link in entry.findall("a:link", ns)
                      if "href" in link.attrib],
                published=date.fromisoformat(entry.findtext("a:published", "", ns)[:10]),
                abstract=abstract or None,
                coverage=Coverage.ABSTRACT_ONLY if abstract else Coverage.METADATA_ONLY,
                labels=[c.attrib["term"] for c in entry.findall("a:category", ns)],
                provenance="arXiv Atom API",
            ))
        return papers


class OpenAlexClient:
    endpoint = "https://api.openalex.org/works"

    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None):
        self.client = _client(client)
        self.params = {"api_key": api_key} if api_key else {}

    def lookup(self, identifier: str) -> SourcePaper:
        if "openalex.org/" in identifier:
            lookup = identifier.rstrip("/").rsplit("/", 1)[-1]
        else:
            lookup = "https://doi.org/" + normalize_identifier(identifier)
        response = self.client.get(f"{self.endpoint}/{quote(lookup, safe='')}", params=self.params)
        response.raise_for_status()
        return self._parse(response.json())

    def expand_citations(self, identifier: str, max_results: int = 20) -> list[SourcePaper]:
        """Retrieve citing works using OpenAlex's documented cites filter."""
        if "openalex.org/" in identifier:
            work_id = identifier.rstrip("/").rsplit("/", 1)[-1]
        else:
            response = self.client.get(
                f"{self.endpoint}/{quote('https://doi.org/' + normalize_identifier(identifier), safe='')}",
                params=self.params,
            )
            response.raise_for_status()
            work_id = response.json()["id"].rsplit("/", 1)[-1]
        response = self.client.get(self.endpoint, params={
            **self.params, "filter": f"cites:{work_id}", "per-page": min(max_results, 200),
        })
        response.raise_for_status()
        return [self._parse(item) for item in response.json().get("results", [])]

    @staticmethod
    def _parse(data: dict) -> SourcePaper:
        abstract = None
        inverted = data.get("abstract_inverted_index")
        if inverted:
            words = {position: word for word, positions in inverted.items() for position in positions}
            abstract = " ".join(words[position] for position in sorted(words))
        urls = [data["id"]]
        arxiv_id, version = None, None
        for location in data.get("locations", []):
            for key in ("landing_page_url", "pdf_url"):
                value = location.get(key)
                if value:
                    urls.append(value)
                    ident = arxiv_identity(value)
                    if ident:
                        arxiv_id, version = ident
        primary = data.get("primary_location") or {}
        source = primary.get("source") or {}
        doi = data.get("doi")
        return SourcePaper(
            title=data.get("title") or data.get("display_name") or "Untitled work",
            authors=[a.get("author", {}).get("display_name", "") for a in data.get("authorships", [])],
            doi=normalize_identifier(doi) if doi else None, arxiv_id=arxiv_id, version=version,
            aliases=[data["id"]], urls=list(dict.fromkeys(urls)), abstract=abstract,
            coverage=Coverage.ABSTRACT_ONLY if abstract else Coverage.METADATA_ONLY,
            published=date.fromisoformat(data["publication_date"]) if data.get("publication_date") else None,
            venue=source.get("display_name"),
            labels=[topic.get("display_name", "") for topic in data.get("topics", [])],
            provenance="OpenAlex Works API",
        )


def is_doi(value: str) -> bool:
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", normalize_identifier(value)))


def canonical_url(value: str) -> str:
    parsed = urlparse(value)
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), fragment="").geturl()
