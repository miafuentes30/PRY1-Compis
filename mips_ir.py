"""Representación del ensamblador MIPS generado (Proyecto 3).

Las instrucciones se guardan estructuradas (mnemónico + operandos) para que el
optimizador de mirilla pueda reconocer patrones sin analizar texto.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

LABEL = "label"
COMMENT = "#"


def ascii_only(text: str) -> str:
    """Los comentarios del .asm van en ASCII puro para cualquier simulador."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch if ord(ch) < 128 else "?" for ch in normalized if not unicodedata.combining(ch))


@dataclass
class Asm:
    op: str
    args: tuple[str, ...] = ()
    comment: str = ""

    @property
    def is_label(self) -> bool:
        return self.op == LABEL

    @property
    def is_comment(self) -> bool:
        return self.op == COMMENT

    @property
    def is_instruction(self) -> bool:
        return self.op not in {LABEL, COMMENT}

    def render(self) -> str:
        if self.is_label:
            text = f"{self.args[0]}:"
        elif self.is_comment:
            return f"    # {ascii_only(self.comment)}" if self.comment else ""
        else:
            text = f"    {self.op:<7}{', '.join(self.args)}".rstrip()
        if self.comment:
            text = f"{text:<38}# {ascii_only(self.comment)}"
        return text


@dataclass
class FunctionMeta:
    """Datos de una función para el simulador (árbol de activación) y el IDE."""
    asm_label: str
    name: str                                   # nombre visible: factorial, Animal.hablar, main
    kind: str
    params: list[tuple[str, str]] = field(default_factory=list)   # (nombre, tipo); incluye this
    return_type: str = "void"
    frame_size: int = 0
    epilogue_label: str = ""


@dataclass
class MIPSProgram:
    header: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    text: list[Asm] = field(default_factory=list)
    runtime: list[str] = field(default_factory=list)
    functions: list[FunctionMeta] = field(default_factory=list)
    handler_labels: list[str] = field(default_factory=list)
    local_labels: set[str] = field(default_factory=set)      # etiquetas de control (eliminables)
    return_labels: set[str] = field(default_factory=set)     # etiquetas de epílogo
    frames: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    def instruction_count(self) -> int:
        return sum(1 for line in self.text if line.is_instruction)

    def render(self) -> str:
        lines = list(self.header)
        lines.append("        .data")
        lines.extend(self.data)
        lines.append("")
        lines.append("        .text")
        lines.append("        .globl main")
        lines.extend(line.render() for line in self.text)
        lines.append("")
        lines.extend(self.runtime)
        return "\n".join(lines) + "\n"
