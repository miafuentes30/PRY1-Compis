from __future__ import annotations

from antlr4 import CommonTokenStream, InputStream
from antlr4.Token import Token

from compiscript_keywords import COMPISCRIPT_KEYWORDS
from error_listener import AnalysisError, SpanishErrorListener
from generated.CompiscriptLexer import CompiscriptLexer
from generated.CompiscriptParser import CompiscriptParser


TYPO_CODE = "SYN_RESERVED_WORD_TYPO"


def find_reserved_word_typos(source: str, original_error_count: int) -> list[AnalysisError]:
    if original_error_count <= 0:
        return []

    tokens = _tokenize(source)
    candidates: list[tuple[int, str, object]] = []
    for token in tokens.tokens:
        if token.type != CompiscriptLexer.Identifier or token.channel != Token.DEFAULT_CHANNEL:
            continue
        matches = _keyword_candidates(token.text or "")
        for keyword in matches:
            candidates.append((_parse_error_count(_replace_token(source, token, keyword)), keyword, token))

    diagnostics: list[AnalysisError] = []
    seen_positions: set[tuple[int, int, str]] = set()
    for corrected_count, keyword, token in sorted(candidates, key=lambda item: item[0]):
        if corrected_count >= original_error_count:
            continue
        key = (token.line, token.column, token.text or "")
        if key in seen_positions:
            continue
        seen_positions.add(key)
        diagnostics.append(_build_typo_error(source, token, keyword))
    return diagnostics


def suppress_consequential_syntax_errors(
    syntactic_errors: list[AnalysisError],
    typo_errors: list[AnalysisError],
    token_stream: CommonTokenStream,
) -> list[AnalysisError]:
    if not typo_errors:
        return syntactic_errors

    spans = [_statement_span(err.token_index, token_stream) for err in typo_errors if err.token_index is not None]
    result: list[AnalysisError] = []
    for error in syntactic_errors:
        if error.code == TYPO_CODE:
            result.append(error)
            continue
        if error.token_index is not None and any(start <= error.token_index <= end for start, end in spans):
            continue
        result.append(error)
    return result


def _keyword_candidates(text: str) -> list[str]:
    if text in COMPISCRIPT_KEYWORDS:
        return []
    return sorted(keyword for keyword in COMPISCRIPT_KEYWORDS if _is_one_edit_away(text, keyword))


def _is_one_edit_away(source: str, target: str) -> bool:
    if source == target or abs(len(source) - len(target)) > 1:
        return False

    if len(source) == len(target):
        diffs = [i for i, (left, right) in enumerate(zip(source, target)) if left != right]
        if len(diffs) == 1:
            return True
        return (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and source[diffs[0]] == target[diffs[1]]
            and source[diffs[1]] == target[diffs[0]]
        )

    shorter, longer = (source, target) if len(source) < len(target) else (target, source)
    i = j = differences = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            differences += 1
            if differences > 1:
                return False
            j += 1
    return True


def _tokenize(source: str) -> CommonTokenStream:
    lexer = CompiscriptLexer(InputStream(source))
    lexer.removeErrorListeners()
    tokens = CommonTokenStream(lexer)
    tokens.fill()
    return tokens


def _parse_error_count(source: str) -> int:
    tokens = _tokenize(source)
    parser = CompiscriptParser(tokens)
    listener = SpanishErrorListener("Sintáctico", source)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    parser.program()
    return len(listener.errors)


def _replace_token(source: str, token, replacement: str) -> str:
    return source[: token.start] + replacement + source[token.stop + 1 :]


def _build_typo_error(source: str, token, keyword: str) -> AnalysisError:
    line = max(1, int(token.line or 1))
    internal_column = max(0, int(token.column or 0))
    display_column = internal_column + 1
    symbol = f"«{token.text}»"
    return AnalysisError(
        error_type="Sintáctico",
        line=line,
        column=display_column,
        symbol=symbol,
        description=f"Palabra reservada mal escrita: {symbol}. Se esperaba «{keyword}».",
        suggestion=f"Reemplaza {symbol} por «{keyword}».",
        source_excerpt=_source_excerpt(source, line, internal_column),
        code=TYPO_CODE,
        token_index=token.tokenIndex,
    )


def _source_excerpt(source: str, line: int, column: int) -> str:
    lines = source.splitlines()
    if not (1 <= line <= len(lines)):
        return ""
    text = lines[line - 1].rstrip("\r\n")
    caret_column = min(max(column, 0), len(text))
    return f"{text}\n{' ' * caret_column}^"


def _statement_span(token_index: int | None, token_stream: CommonTokenStream) -> tuple[int, int]:
    if token_index is None:
        return (-1, -1)

    tokens = [token for token in token_stream.tokens if token.channel == Token.DEFAULT_CHANNEL]
    default_indexes = [token.tokenIndex for token in tokens]
    start = token_index
    end = token_index
    opening_braces = 0
    for token in tokens:
        if token.tokenIndex < token_index:
            continue
        end = token.tokenIndex
        if token.text == "{":
            opening_braces += 1
        elif token.text == "}":
            if opening_braces == 0:
                break
            opening_braces -= 1
            if opening_braces == 0:
                break
        elif token.text == ";" and opening_braces == 0:
            break
    if start not in default_indexes:
        return (start, end)
    return (start, end)
