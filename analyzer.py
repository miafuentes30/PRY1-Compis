from __future__ import annotations

from pathlib import Path

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorStrategy import DefaultErrorStrategy

from analysis_result import FullAnalysisResult
from error_listener import AnalysisError, SpanishErrorListener
from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser
from semantic_analyzer import SemanticAnalyzer


class RecoveringErrorStrategy(DefaultErrorStrategy):
    """Estrategia estándar de ANTLR: inserta/elimina tokens y continúa el parseo."""


class CompiscriptAnalyzer:
    """Pipeline léxico + sintáctico + semántico de Compiscript."""

    MAX_ERRORS = 300

    def analyze_full_text(self, source: str) -> FullAnalysisResult:
        input_stream = InputStream(source)

        lexer = CompiscriptLexer(input_stream)
        lexical_listener = SpanishErrorListener("Léxico", source)
        lexer.removeErrorListeners()
        lexer.addErrorListener(lexical_listener)

        tokens = CommonTokenStream(lexer)
        # Recorre el lexer completo para conservar recuperación tras caracteres inválidos.
        tokens.fill()
        tokens.seek(0)

        parser = CompiscriptParser(tokens)
        syntactic_listener = SpanishErrorListener("Sintáctico", source)
        parser.removeErrorListeners()
        parser.addErrorListener(syntactic_listener)
        parser._errHandler = RecoveringErrorStrategy()

        tree = parser.program()
        lexical = lexical_listener.errors
        syntactic = syntactic_listener.errors

        semantic_errors: list[AnalysisError] = []
        symbol_table = None
        classes = {}

        # Evita cascadas semánticas cuando el árbol se construyó mediante recuperación
        # sintáctica. Con código sintácticamente válido, el visitor recorre TODO el árbol
        # y continúa después de cada error semántico.
        if not lexical and not syntactic:
            semantic = SemanticAnalyzer(source).analyze(tree)
            semantic_errors = semantic.errors
            symbol_table = semantic.symbol_table
            classes = semantic.classes

        errors = self._remove_redundant_errors(lexical + syntactic + semantic_errors)
        errors = sorted(errors, key=lambda err: (err.line, err.column, err.error_type, err.code))[: self.MAX_ERRORS]
        return FullAnalysisResult(
            source=source,
            errors=errors,
            parse_tree=tree,
            parser=parser,
            token_stream=tokens,
            symbol_table=symbol_table,
            classes=classes,
        )

    def analyze_text(self, source: str) -> list[AnalysisError]:
        """Compatibilidad con el laboratorio anterior: devuelve solo la lista de errores."""
        return self.analyze_full_text(source).errors

    @staticmethod
    def _remove_redundant_errors(errors: list[AnalysisError]) -> list[AnalysisError]:
        result: list[AnalysisError] = []
        seen: set[tuple[str, int, int, str, str]] = set()
        for error in errors:
            key = (error.error_type, error.line, error.column, error.code, error.description)
            if key in seen:
                continue
            seen.add(key)
            result.append(error)
        return result

    def analyze_full_file(self, path: str | Path) -> FullAnalysisResult:
        file_path = Path(path)
        if file_path.suffix.lower() != ".cps":
            raise ValueError("El archivo seleccionado debe tener extensión .cps.")
        try:
            source = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = file_path.read_text(encoding="latin-1")
        return self.analyze_full_text(source)

    def analyze_file(self, path: str | Path) -> list[AnalysisError]:
        return self.analyze_full_file(path).errors
