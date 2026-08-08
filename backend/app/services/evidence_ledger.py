"""Provenance-aware ledger for verified quoted source evidence."""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass(frozen=True)
class EvidenceRecord:
    source_id: str
    text: str
    tool_name: str = ""


class EvidenceLedger:
    def __init__(self):
        self._records: list[EvidenceRecord] = []

    def record(self, text: str, *, source_id: str = "", tool_name: str = "") -> None:
        if text:
            self._records.append(EvidenceRecord(source_id or f"source-{len(self._records) + 1}", text, tool_name))

    @staticmethod
    def canonical(text: str) -> str:
        lines = []
        for line in str(text).replace("\r\n", "\n").split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                continue
            if stripped.startswith(">"):
                stripped = stripped[1:].lstrip()
            lines.append(stripped)
        return re.sub(r"\s+", " ", " ".join(lines)).strip()

    def match(self, candidate: str) -> Optional[EvidenceRecord]:
        if not candidate:
            return None
        normalized = self.canonical(candidate)
        for record in self._records:
            if candidate in record.text or normalized in self.canonical(record.text):
                return record
        return None

    def __len__(self) -> int:
        return len(self._records)
