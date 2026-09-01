from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from error_listener import AnalysisError
from symbol_table import SymbolTable


@dataclass
class FullAnalysisResult:
    source: str
    errors: list[AnalysisError] = field(default_factory=list)
    parse_tree: Any | None = None
    parser: Any | None = None
    token_stream: Any | None = None
    symbol_table: SymbolTable | None = None
    classes: dict[str, Any] = field(default_factory=dict)

    @property
    def lexical_errors(self) -> list[AnalysisError]:
        return [e for e in self.errors if e.error_type == "Léxico"]

    @property
    def syntactic_errors(self) -> list[AnalysisError]:
        return [e for e in self.errors if e.error_type == "Sintáctico"]

    @property
    def semantic_errors(self) -> list[AnalysisError]:
        return [e for e in self.errors if e.error_type == "Semántico"]

    @property
    def is_valid(self) -> bool:
        return not self.errors
