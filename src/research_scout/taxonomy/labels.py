from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from research_scout.domain.models import Record


@dataclass
class Taxonomy:
    """An optional controlled vocabulary; labels never imply scientific entailment."""

    labels: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.labels = {self._key(x) for x in self.labels}
        self.aliases = {self._key(k): self._key(v) for k, v in self.aliases.items()}
        for alias in self.aliases:
            target = self.resolve(alias)
            if self.labels and target not in self.labels:
                raise ValueError(f"label alias {alias!r} targets unknown label {target!r}")

    @staticmethod
    def _key(label: str) -> str:
        value = " ".join(label.casefold().split())
        if not value:
            raise ValueError("labels cannot be empty")
        return value

    def resolve(self, label: str) -> str:
        current = self._key(label)
        seen = set()
        while current in self.aliases:
            if current in seen:
                raise ValueError("taxonomy aliases contain a cycle")
            seen.add(current)
            current = self.aliases[current]
        return current

    def normalize(self, labels: Iterable[str]) -> list[str]:
        result = sorted({self.resolve(label) for label in labels})
        unknown = set(result) - self.labels
        if self.labels and unknown:
            raise ValueError(f"unknown taxonomy labels: {sorted(unknown)}")
        return result

    def classify(self, record: Record, labels: Iterable[str]) -> Record:
        """Return a candidate revision. Publication still goes through Archive."""
        return record.model_copy(update={"labels": self.normalize(labels)})
