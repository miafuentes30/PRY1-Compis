from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from antlr4.Token import Token
from antlr4.error.ErrorListener import ErrorListener


@dataclass(frozen=True)
class AnalysisError:
    error_type: str
    line: int
    column: int
    symbol: str
    description: str
    suggestion: str
    source_excerpt: str
    code: str = ""


class SpanishErrorListener(ErrorListener):
    """Convierte los diagnósticos internos de ANTLR a mensajes útiles en español."""

    TOKEN_LABELS = {
        "<EOF>": "el final del archivo",
        "EOF": "el final del archivo",
        "<EPSILON>": "una entrada vacía",
        "Identifier": "un identificador",
        "Literal": "un número entero o una cadena de texto",
        "IntegerLiteral": "un número entero",
        "StringLiteral": "una cadena de texto entre comillas dobles",
        "FloatLiteral": "un número decimal",
        "'let'": "la palabra reservada «let»",
        "'var'": "la palabra reservada «var»",
        "'const'": "la palabra reservada «const»",
        "'function'": "la palabra reservada «function»",
        "'class'": "la palabra reservada «class»",
        "'if'": "la palabra reservada «if»",
        "'else'": "la palabra reservada «else»",
        "'while'": "la palabra reservada «while»",
        "'do'": "la palabra reservada «do»",
        "'for'": "la palabra reservada «for»",
        "'foreach'": "la palabra reservada «foreach»",
        "'in'": "la palabra reservada «in»",
        "'try'": "la palabra reservada «try»",
        "'catch'": "la palabra reservada «catch»",
        "'switch'": "la palabra reservada «switch»",
        "'case'": "la palabra reservada «case»",
        "'default'": "la palabra reservada «default»",
        "'break'": "la palabra reservada «break»",
        "'continue'": "la palabra reservada «continue»",
        "'return'": "la palabra reservada «return»",
        "'print'": "la función «print»",
        "'new'": "la palabra reservada «new»",
        "'this'": "la palabra reservada «this»",
        "'null'": "el valor «null»",
        "'true'": "el valor booleano «true»",
        "'false'": "el valor booleano «false»",
        "'boolean'": "el tipo «boolean»",
        "'integer'": "el tipo «integer»",
        "'float'": "el tipo «float»",
        "'string'": "el tipo «string»",
        "';'": "un punto y coma «;»",
        "':'": "dos puntos «:»",
        "','": "una coma «,»",
        "'.'": "un punto «.»",
        "'='": "el operador de asignación «=»",
        "'('": "un paréntesis de apertura «(»",
        "')'": "un paréntesis de cierre «)»",
        "'{'": "una llave de apertura «{»",
        "'}'": "una llave de cierre «}»",
        "'['": "un corchete de apertura «[»",
        "']'": "un corchete de cierre «]»",
        "'?'": "el operador condicional «?»",
        "'||'": "el operador lógico «||»",
        "'&&'": "el operador lógico «&&»",
        "'=='": "el operador de igualdad «==»",
        "'!='": "el operador de diferencia «!=»",
        "'<'": "el operador «<»",
        "'<='": "el operador «<=»",
        "'>'": "el operador «>»",
        "'>='": "el operador «>=»",
        "'+'": "el operador «+»",
        "'-'": "el operador «-»",
        "'*'": "el operador «*»",
        "'/'": "el operador «/»",
        "'%'": "el operador «%»",
        "'!'": "el operador lógico «!»",
    }

    PUNCTUATION_SUGGESTIONS = {
        "';'": "Agrega un punto y coma «;» para finalizar la instrucción.",
        "')'": "Agrega el paréntesis de cierre «)» en esta posición.",
        "'('": "Agrega el paréntesis de apertura «(» antes de esta parte.",
        "'}'": "Agrega la llave de cierre «}» para terminar el bloque.",
        "'{'": "Agrega la llave de apertura «{» para iniciar el bloque.",
        "']'": "Agrega el corchete de cierre «]» para terminar el acceso o arreglo.",
        "'['": "Agrega el corchete de apertura «[» en esta posición.",
        "':'": "Agrega dos puntos «:» en esta posición.",
        "','": "Agrega una coma «,» para separar los elementos.",
        "'='": "Agrega el operador de asignación «=» antes del valor.",
        "'in'": "En un foreach debe escribirse «in» entre la variable y la colección.",
    }

    EXPRESSION_STARTS = {
        "Identifier",
        "Literal",
        "'null'",
        "'true'",
        "'false'",
        "'new'",
        "'this'",
        "'('",
        "'['",
        "'-'",
        "'!'",
    }

    def __init__(self, error_type: str, source: str = "") -> None:
        super().__init__()
        self.error_type = error_type
        self.source = source
        self.source_lines = source.splitlines()
        self.errors: list[AnalysisError] = []
        self._seen: set[tuple[str, int, int, str, str]] = set()

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        safe_line = max(1, int(line or 1))
        internal_column = max(0, int(column or 0))
        display_column = internal_column + 1
        symbol = self._extract_symbol(recognizer, offendingSymbol, msg)
        expected_raw = self._expected_token_names(recognizer)

        if self.error_type == "Léxico":
            description, suggestion = self._lexical_message(symbol, msg)
        else:
            description, suggestion = self._syntactic_message(
                symbol=symbol,
                raw_message=msg or "",
                expected_raw=expected_raw,
            )

        excerpt = self._source_excerpt(safe_line, internal_column)
        key = (self.error_type, safe_line, display_column, symbol, description)
        if key in self._seen:
            return
        self._seen.add(key)
        self.errors.append(
            AnalysisError(
                error_type=self.error_type,
                line=safe_line,
                column=display_column,
                symbol=symbol,
                description=description,
                suggestion=suggestion,
                source_excerpt=excerpt,
            )
        )

    def _source_excerpt(self, line: int, column: int) -> str:
        if not (1 <= line <= len(self.source_lines)):
            return ""
        text = self.source_lines[line - 1].rstrip("\r\n")
        caret_column = min(max(column, 0), len(text))
        return f"{text}\n{' ' * caret_column}^"

    @classmethod
    def _extract_symbol(cls, recognizer, offending_symbol, message: str) -> str:
        if offending_symbol is not None:
            text = getattr(offending_symbol, "text", None)
            if text == "<EOF>":
                return "fin del archivo"
            if text is not None:
                return cls._visible(text)

        # Los errores léxicos normalmente no incluyen offendingSymbol.
        match = re.search(r"token recognition error at:\s*'(.*)'", message or "", re.DOTALL)
        if match:
            raw = match.group(1)
            raw = raw.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
            return cls._visible(raw)
        try:
            stream = recognizer._input
            codepoint = stream.LA(1)
            if codepoint == Token.EOF:
                return "fin del archivo"
            return cls._visible(chr(codepoint))
        except Exception:
            return "símbolo desconocido"

    @staticmethod
    def _visible(text: str) -> str:
        replacements = {"\n": "salto de línea", "\r": "retorno de carro", "\t": "tabulación"}
        if text in replacements:
            return replacements[text]
        if text == "":
            return "entrada vacía"
        compact = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        if len(compact) > 40:
            compact = compact[:37] + "..."
        return f"«{compact}»"

    @classmethod
    def _expected_token_names(cls, recognizer) -> list[str]:
        try:
            token_set = recognizer.getExpectedTokens()
            literal_names = getattr(recognizer, "literalNames", [])
            symbolic_names = getattr(recognizer, "symbolicNames", [])
            names: list[str] = []
            for token_type in token_set:
                if token_type == Token.EOF:
                    raw = "<EOF>"
                elif 0 <= token_type < len(literal_names) and literal_names[token_type] not in (None, "<INVALID>"):
                    raw = literal_names[token_type]
                elif 0 <= token_type < len(symbolic_names) and symbolic_names[token_type] not in (None, "<INVALID>"):
                    raw = symbolic_names[token_type]
                else:
                    continue
                if raw not in names:
                    names.append(raw)
            return names
        except Exception:
            return []

    @classmethod
    def _labels(cls, raw_names: Iterable[str]) -> list[str]:
        labels: list[str] = []
        for raw in raw_names:
            label = cls.TOKEN_LABELS.get(raw, cls._fallback_token_label(raw))
            if label not in labels:
                labels.append(label)
        return labels

    @staticmethod
    def _fallback_token_label(raw: str) -> str:
        if raw.startswith("'") and raw.endswith("'"):
            return f"el símbolo «{raw[1:-1]}»"
        clean = raw.replace("<", "").replace(">", "")
        return f"un elemento de tipo «{clean}»"

    @classmethod
    def _join_expected(cls, raw_names: list[str]) -> str:
        labels = cls._labels(raw_names)
        if not labels:
            return "una estructura válida de Compiscript"
        if len(labels) > 6:
            return ", ".join(labels[:5]) + " u otra expresión o instrucción válida"
        if len(labels) == 1:
            return labels[0]
        return ", ".join(labels[:-1]) + " o " + labels[-1]

    @classmethod
    def _lexical_message(cls, symbol: str, raw_message: str) -> tuple[str, str]:
        lower = (raw_message or "").lower()
        plain = symbol.strip("«»")

        if plain.startswith('"') or "unterminated string" in lower:
            return (
                f"La cadena de texto que comienza con {symbol} no está cerrada correctamente.",
                "Cierra la cadena con comillas dobles «\"» antes de terminar la línea.",
            )
        if plain.startswith("/*") or "unterminated comment" in lower:
            return (
                "El comentario de bloque no tiene un cierre válido.",
                "Cierra el comentario utilizando «*/».",
            )
        return (
            f"El carácter o lexema {symbol} no pertenece al vocabulario reconocido por Compiscript.",
            "Elimina el símbolo o sustitúyelo por un operador, identificador o literal permitido.",
        )

    @classmethod
    def _syntactic_message(
        cls,
        symbol: str,
        raw_message: str,
        expected_raw: list[str],
    ) -> tuple[str, str]:
        message = raw_message or ""
        expected_text = cls._join_expected(expected_raw)
        first_expected = expected_raw[0] if len(expected_raw) == 1 else None
        lower = message.lower()

        if symbol == "fin del archivo":
            if "'}'" in expected_raw:
                return (
                    "El archivo terminó antes de cerrar un bloque de instrucciones.",
                    "Agrega una llave de cierre «}» al final del bloque que quedó abierto.",
                )
            if "')'" in expected_raw:
                return (
                    "El archivo terminó antes de cerrar un paréntesis.",
                    "Agrega el paréntesis de cierre «)» que falta.",
                )
            if "';'" in expected_raw:
                return (
                    "El archivo terminó y la última instrucción quedó sin punto y coma.",
                    "Agrega «;» al final de la última instrucción.",
                )
            return (
                f"El archivo terminó de forma inesperada; se esperaba {expected_text}.",
                "Completa la estructura que quedó abierta antes del final del archivo.",
            )

        if "missing" in lower:
            missing_raw = first_expected or cls._raw_missing_token(message)
            missing_label = cls.TOKEN_LABELS.get(missing_raw, expected_text)
            suggestion = cls.PUNCTUATION_SUGGESTIONS.get(
                missing_raw,
                f"Agrega {missing_label} antes de {symbol}.",
            )
            return (f"Falta {missing_label} antes de {symbol}.", suggestion)

        if "extraneous input" in lower:
            return (
                f"El elemento {symbol} aparece en una posición donde no corresponde; se esperaba {expected_text}.",
                f"Elimina {symbol} o reemplázalo por {expected_text}.",
            )

        if "mismatched input" in lower:
            if symbol == "«;»" and cls.EXPRESSION_STARTS.intersection(expected_raw):
                return (
                    "La instrucción contiene un punto y coma, pero antes falta una expresión o valor.",
                    "Escribe una expresión válida antes del punto y coma.",
                )
            if symbol == "«}»" and cls.EXPRESSION_STARTS.intersection(expected_raw):
                return (
                    "La expresión quedó incompleta antes de cerrar el bloque.",
                    "Completa la expresión y termina la instrucción con «;» antes de la llave «}».",
                )
            suggestion = cls.PUNCTUATION_SUGGESTIONS.get(
                first_expected or "",
                f"Reemplaza {symbol} por {expected_text} o corrige la estructura que lo contiene.",
            )
            return (
                f"Se encontró {symbol}, pero en esta posición se esperaba {expected_text}.",
                suggestion,
            )

        if "no viable alternative" in lower:
            return (
                f"La secuencia que contiene {symbol} no forma una instrucción o expresión válida de Compiscript.",
                "Revisa el orden de los elementos y verifica paréntesis, llaves, operadores y puntos y coma cercanos.",
            )

        if "failed predicate" in lower:
            return (
                f"La estructura cercana a {symbol} no cumple la forma requerida por la gramática.",
                "Revisa la sintaxis de la instrucción completa y compárala con una construcción válida de Compiscript.",
            )

        # Mensaje de respaldo sin exponer la excepción interna en inglés.
        return (
            f"La entrada {symbol} no es válida en esta posición; se esperaba {expected_text}.",
            "Corrige la instrucción indicada y vuelve a ejecutar el análisis.",
        )

    @staticmethod
    def _raw_missing_token(message: str) -> str:
        match = re.search(r"missing\s+(.+?)\s+at\s+", message or "")
        return match.group(1).strip() if match else ""
