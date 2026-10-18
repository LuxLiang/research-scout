"""Version-aware source ingestion with content-addressed, configurable caches."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re

import httpx

from research_scout.discovery.sources import (
    ArxivClient, OpenAlexClient, SourcePaper, _client, arxiv_identity, canonical_url, is_doi,
)
from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import Coverage, Paper, PaperVersion, normalize_identifier, stable_id


@dataclass
class IngestionOutcome:
    paper: Paper
    version: PaperVersion
    is_new_version: bool
    affected_ids: list[str] = field(default_factory=list)


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


class PaperIngestor:
    def __init__(self, archive: ArchiveProtocol, cache_dir: str | Path,
                 http_client: httpx.Client | None = None):
        self.archive = archive
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.client = _client(http_client)
        for name in ("sources", "text", "staging"):
            (self.cache_dir / name).mkdir(parents=True, exist_ok=True)

    def ingest(self, source: str | Path | SourcePaper) -> IngestionOutcome:
        metadata, content, suffix = self._resolve(source)
        if metadata.doi:
            metadata.doi = normalize_identifier(metadata.doi)
        if metadata.arxiv_id:
            identity = arxiv_identity(metadata.arxiv_id)
            if not identity:
                raise ValueError("Invalid arXiv identity in source metadata")
            metadata.arxiv_id, supplied_version = identity
            metadata.version = metadata.version or supplied_version
        text = metadata.text or metadata.abstract or ""
        payload = content if content is not None else text.encode()
        # Metadata-only versions are reproducible and do not all share the hash of empty bytes.
        if not payload:
            payload = metadata.model_dump_json(exclude={"text"}).encode()
        digest = sha256(payload).hexdigest()
        aliases = list(metadata.aliases)
        aliases.extend(canonical_url(url) for url in metadata.urls)
        if not metadata.doi and not metadata.arxiv_id:
            aliases.append(f"sha256:{digest}")
        if metadata.doi:
            aliases.extend([metadata.doi, f"doi:{metadata.doi}", f"https://doi.org/{metadata.doi}"])
        if metadata.arxiv_id:
            aliases.extend([metadata.arxiv_id, f"arxiv:{metadata.arxiv_id}"])
        aliases = list(dict.fromkeys(aliases))
        candidates = []
        for existing in self.archive.list("paper"):
            identifiers = set(existing.aliases + [existing.id])
            if existing.doi:
                identifiers.update([existing.doi, f"doi:{existing.doi}"])
            if existing.arxiv_id:
                identifiers.update([existing.arxiv_id, f"arxiv:{existing.arxiv_id}"])
            hashes = [self.archive.get(version_id).content_hash for version_id in existing.version_ids]
            may_match_content = (not metadata.doi and not metadata.arxiv_id) or (
                not existing.doi and not existing.arxiv_id)
            if identifiers.intersection(aliases) or (may_match_content and digest in hashes):
                candidates.append(existing)
        if len(candidates) > 1:
            raise ValueError("Source bridges multiple existing papers; explicitly merge identities first")
        if candidates:
            matched = candidates[0]
            if metadata.doi and matched.doi and metadata.doi != matched.doi:
                raise ValueError("Conflicting DOI identities require an explicit reviewed merge")
            if metadata.arxiv_id and matched.arxiv_id and metadata.arxiv_id != matched.arxiv_id:
                raise ValueError("Conflicting arXiv identities require an explicit reviewed merge")
        paper = candidates[0] if candidates else Paper(
            id=stable_id("paper", metadata.doi or metadata.arxiv_id or f"sha256:{digest}"),
            title=metadata.title, doi=metadata.doi, arxiv_id=metadata.arxiv_id,
            authors=metadata.authors, venue=metadata.venue, published=metadata.published,
            aliases=aliases, labels=metadata.labels, provenance=metadata.provenance,
        )
        versions = [self.archive.get(v) for v in paper.version_ids]
        for previous in versions:
            # An explicit arXiv v2 remains distinct even when the abstract is unchanged.
            version_matches = not metadata.version or previous.version.split("+content-")[0] == metadata.version
            if previous.content_hash == digest and version_matches:
                merged = paper.model_copy(update={
                    "aliases": sorted(set(paper.aliases + aliases)),
                    "doi": paper.doi or metadata.doi, "arxiv_id": paper.arxiv_id or metadata.arxiv_id,
                })
                persisted = self.archive.put(merged)
                return IngestionOutcome(persisted, previous, False)
        version_name = metadata.version or f"content-{digest[:16]}"
        if any(previous.version == version_name for previous in versions):
            # Preserve source snapshots when a known scientific version changes silently
            # or abstract-only ingestion is later enriched with full text.
            version_name += f"+content-{digest[:12]}"
        # Immutable version identity includes content hash, detecting silent source edits too.
        version_id = stable_id("version", f"{paper.id}:{version_name}:{digest}")
        source_path = self.cache_dir / "sources" / f"{digest}{suffix}"
        if not source_path.exists():
            source_path.write_bytes(payload)
        text_path = self.cache_dir / "text" / f"{sha256(text.encode()).hexdigest()}.txt"
        if not text_path.exists():
            text_path.write_text(text, encoding="utf-8")
        previous = versions[-1] if versions else None
        scientific_number = self._version_number(version_name)
        historical = scientific_number is not None and previous is not None and (
            self._version_number(previous.version) or 0) > scientific_number
        if historical:
            older = [item for item in versions if (self._version_number(item.version) or 0) <= scientific_number]
            previous = older[-1] if older else None
        version = PaperVersion(
            id=version_id, title=f"{metadata.title} [{version_name}]", paper_id=paper.id,
            version=version_name, source_urls=metadata.urls, source_path=str(source_path),
            text_path=str(text_path), content_hash=digest, abstract=metadata.abstract,
            coverage=metadata.coverage, published=metadata.published,
            supersedes_version_id=previous.id if previous else None,
            provenance=metadata.provenance,
        )
        ordered_versions = versions + [version]
        if all(self._version_number(item.version) is not None for item in ordered_versions):
            # Stable sorting keeps successive content snapshots of the same scientific
            # revision together, including when v3, v2, v1 arrive in reverse order.
            ordered_versions.sort(key=lambda item: self._version_number(item.version))
        updated = paper.model_copy(update={
            "version_ids": [item.id for item in ordered_versions],
            "aliases": sorted(set(paper.aliases + aliases)),
            "doi": paper.doi or metadata.doi, "arxiv_id": paper.arxiv_id or metadata.arxiv_id,
            "labels": sorted(set(paper.labels + metadata.labels)),
            "extraction_status": paper.extraction_status if historical else "NOT_EXTRACTED",
        })
        records = self.archive.put_many([updated, version])
        paper = next(record for record in records if record.id == paper.id)
        affected = []
        if previous and not historical:
            from research_scout.evolution import flag_version_review
            changed = flag_version_review(self.archive, previous.id, version.id)
            affected = [record if isinstance(record, str) else record.id for record in (changed or [])]
        return IngestionOutcome(paper, version, True, affected)

    @staticmethod
    def _version_number(value: str) -> int | None:
        match = re.match(r"^v(\d+)(?:\+content-|$)", value)
        return int(match.group(1)) if match else None

    def _resolve(self, source: str | Path | SourcePaper) -> tuple[SourcePaper, bytes | None, str]:
        if isinstance(source, SourcePaper):
            return source.model_copy(deep=True), None, ".json" if not source.text else ".txt"
        value = str(source)
        path = Path(value).expanduser()
        if path.is_file():
            content = path.read_bytes()
            metadata = self._decode(content, path.suffix, path.stem)
            metadata.aliases.append(f"file:{path.resolve()}")
            return metadata, content, path.suffix or ".txt"
        ident = arxiv_identity(value)
        if ident:
            metadata = ArxivClient(self.client).lookup(value)
            if "/pdf/" in value:
                response = self.client.get(value)
                response.raise_for_status()
                decoded = self._decode(response.content, ".pdf", metadata.title)
                metadata.text, metadata.coverage = decoded.text, decoded.coverage
                metadata.urls = list(dict.fromkeys(metadata.urls + [value]))
                return metadata, response.content, ".pdf"
            return metadata, None, ".txt"
        if is_doi(value):
            return OpenAlexClient(self.client).lookup(value), None, ".txt"
        if re.match(r"^https?://", value):
            response = self.client.get(value)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            suffix = ".pdf" if "pdf" in content_type or response.content.startswith(b"%PDF") else ".txt"
            metadata = self._decode(response.content, suffix, value,
                                    html="html" in content_type)
            metadata.urls = [canonical_url(value)]
            return metadata, response.content, suffix
        raise ValueError(f"Expected a DOI, arXiv ID, URL, or existing PDF/text path: {value}")

    @staticmethod
    def _decode(content: bytes, suffix: str, title: str, html: bool = False) -> SourcePaper:
        if suffix.lower() == ".pdf" or content.startswith(b"%PDF"):
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError('PDF ingestion requires: pip install "research-scout[pdf]"') from exc
            reader = PdfReader(BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages)
            if not text.strip():
                raise ValueError("PDF has no extractable text; OCR is required")
            coverage = Coverage.FULL_TEXT if all(page.strip() for page in pages) else Coverage.PARTIAL_TEXT
        else:
            text = content.decode("utf-8")
            if html:
                parser = _HTMLText()
                parser.feed(text)
                text = "\n".join(parser.parts)
            coverage = Coverage.PARTIAL_TEXT
        return SourcePaper(title=title, text=text, coverage=coverage,
                           provenance="user supplied source")
