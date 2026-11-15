"""Optimización por mirilla sobre el ensamblador MIPS generado (Proyecto 3).

Recorre el código con una ventana pequeña de instrucciones consecutivas y
sustituye patrones ineficientes por equivalentes más cortos o más rápidos. Se
repite hasta que ninguna regla aplica (una transformación suele habilitar
otras). Cada cambio queda registrado para mostrarlo en el IDE.

Transformaciones implementadas
    1.  ``codigo_inalcanzable``      instrucciones tras ``j``/``jr`` hasta la siguiente etiqueta
    2.  ``salto_al_siguiente``       ``j L`` / salto condicional cuyo destino es la línea siguiente
    3.  ``salto_sobre_salto``        ``beq a,b,L1; j L2; L1:``  =>  ``bne a,b,L2; L1:``
    4.  ``salto_encadenado``         salto a una etiqueta que solo contiene ``j M``  =>  salto a ``M``
    5.  ``carga_tras_almacenar``     ``sw r,M; lw r2,M``  =>  se elimina la carga (o ``move r2,r``)
    6.  ``movimiento_redundante``    ``move r,r`` y ``move a,b; move b,a``
    7.  ``identidad_algebraica``     ``x+0``, ``x-0``, ``x*1``, ``x*0``, desplazamiento de 0 bits
    8.  ``reduccion_de_fuerza``      multiplicación por potencia de 2  =>  ``sll``
    9.  ``propagacion_de_copia``     ``move t,s; op t,t,x``  =>  ``op t,s,x``
    10. ``resultado_directo``        ``op t,...; move $v0,t; (retorno)``  =>  ``op $v0,...``
    11. ``etiqueta_sin_uso``         etiquetas locales que ya nadie referencia

Invariantes del generador en que se apoyan las reglas: ``$t8``/``$t9`` son
auxiliares que nunca permanecen vivos de una instrucción TAC a la siguiente, y
ningún ``$t`` está vivo al llegar al epílogo de una función.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mips_ir import Asm

UNCONDITIONAL = {"j", "b"}
CONDITIONAL = {"beq", "bne", "blt", "ble", "bgt", "bge", "beqz", "bnez", "bltz", "blez", "bgtz", "bgez"}
INVERSE = {"beq": "bne", "bne": "beq", "blt": "bge", "bge": "blt", "ble": "bgt", "bgt": "ble",
           "beqz": "bnez", "bnez": "beqz", "bltz": "bgez", "bgez": "bltz", "blez": "bgtz", "bgtz": "blez"}
THREE_REG = {"addu", "subu", "mul", "slt", "sltu", "xor", "and", "or", "nor"}
WITH_IMM = {"addiu", "slti", "sltiu", "xori", "andi", "ori", "sll", "srl", "sra"}
LOADS = {"lw", "lb", "lbu"}
PURE = THREE_REG | WITH_IMM | LOADS | {"move", "li", "la", "mflo", "mfhi"}   # solo escriben args[0]
TEMP_REGS = {f"$t{i}" for i in range(8)}

RULE_TITLES = {
    "codigo_inalcanzable": "Eliminación de código inalcanzable",
    "salto_al_siguiente": "Eliminación de salto a la instrucción siguiente",
    "salto_sobre_salto": "Inversión de salto condicional sobre salto",
    "salto_encadenado": "Encadenamiento de saltos (jump threading)",
    "carga_tras_almacenar": "Carga redundante después de almacenar",
    "movimiento_redundante": "Eliminación de movimiento redundante",
    "identidad_algebraica": "Simplificación algebraica (identidades)",
    "reduccion_de_fuerza": "Reducción de fuerza (multiplicación → desplazamiento)",
    "propagacion_de_copia": "Propagación de copia",
    "resultado_directo": "Resultado calculado directamente en $v0",
    "etiqueta_sin_uso": "Eliminación de etiquetas sin uso",
}


@dataclass
class PeepholeChange:
    rule: str
    before: list[str]
    after: list[str]

    @property
    def title(self) -> str:
        return RULE_TITLES[self.rule]


@dataclass
class PeepholeReport:
    changes: list[PeepholeChange] = field(default_factory=list)
    instructions_before: int = 0
    instructions_after: int = 0
    passes: int = 0

    def counts(self) -> dict[str, int]:
        result = {rule: 0 for rule in RULE_TITLES}
        for change in self.changes:
            result[change.rule] += 1
        return result

    @property
    def rules_applied(self) -> int:
        return sum(1 for count in self.counts().values() if count)

    def summary(self) -> str:
        saved = self.instructions_before - self.instructions_after
        percent = (100.0 * saved / self.instructions_before) if self.instructions_before else 0.0
        lines = [
            "OPTIMIZACIÓN POR MIRILLA",
            f"Instrucciones antes: {self.instructions_before}   después: {self.instructions_after}   "
            f"eliminadas: {saved} ({percent:.1f} %)   pasadas: {self.passes}",
            "",
            f"{'Veces':>6}  Transformación",
            "-" * 64,
        ]
        for number, (rule, count) in enumerate(self.counts().items(), 1):
            lines.append(f"{count:>6}  {number:>2}. {RULE_TITLES[rule]}")
        lines.append("-" * 64)
        lines.append(f"{len(self.changes):>6}  Total ({self.rules_applied} transformaciones distintas aplicadas)")
        return "\n".join(lines)

    def detail(self, limit: int = 400) -> str:
        lines: list[str] = []
        for number, change in enumerate(self.changes[:limit], 1):
            lines.append(f"[{number}] {change.title}")
            lines.extend(f"    - {text}" for text in change.before)
            lines.extend(f"    + {text}" for text in change.after)
            if not change.after:
                lines.append("    + (eliminado)")
            lines.append("")
        if len(self.changes) > limit:
            lines.append(f"… {len(self.changes) - limit} transformaciones más")
        return "\n".join(lines)


def _memory_base(operand: str) -> str | None:
    if operand.endswith(")") and "(" in operand:
        return operand[operand.index("(") + 1:-1]
    return None


def _is_power_of_two(value: int) -> bool:
    return value >= 2 and value & (value - 1) == 0


class PeepholeOptimizer:
    MAX_PASSES = 25

    def __init__(self, text: list[Asm], local_labels=(), return_labels=()) -> None:
        self.items = [Asm(line.op, tuple(line.args), line.comment) for line in text]
        self.local_labels = set(local_labels)       # etiquetas que pueden eliminarse
        self.return_labels = set(return_labels)     # etiquetas de epílogo
        self.report = PeepholeReport()
        self.report.instructions_before = sum(1 for line in self.items if line.is_instruction)

    # ------------------------------------------------------------------ utilidades
    def _log(self, rule: str, before: list[Asm], after: list[Asm]) -> None:
        self.report.changes.append(PeepholeChange(
            rule, [line.render().strip() for line in before], [line.render().strip() for line in after]))

    def _next_code(self, index: int) -> int | None:
        """Índice de la siguiente línea que no es comentario (etiqueta o instrucción)."""
        k = index + 1
        while k < len(self.items) and self.items[k].is_comment:
            k += 1
        return k if k < len(self.items) else None

    def _next_instruction(self, index: int) -> int | None:
        """Siguiente instrucción solo si no hay una etiqueta de por medio."""
        k = self._next_code(index)
        if k is None or not self.items[k].is_instruction:
            return None
        return k

    def _labels_after(self, index: int) -> set[str]:
        """Etiquetas que siguen inmediatamente a ``index``."""
        labels: set[str] = set()
        k = self._next_code(index)
        while k is not None and self.items[k].is_label:
            labels.add(self.items[k].args[0])
            k = self._next_code(k)
        return labels

    @staticmethod
    def _is_jump(line: Asm) -> bool:
        return line.op in UNCONDITIONAL or line.op in CONDITIONAL

    def _replace(self, index: int, count: int, new: list[Asm], rule: str) -> None:
        old = self.items[index:index + count]
        if new and not new[0].comment:
            new[0].comment = next((line.comment for line in old if line.comment), "")
        self._log(rule, [line for line in old if not line.is_comment], new)
        self.items[index:index + count] = new

    # ------------------------------------------------------------------ reglas
    def rule_codigo_inalcanzable(self) -> bool:
        changed = False
        i = 0
        while i < len(self.items):
            line = self.items[i]
            ends = line.op in UNCONDITIONAL or line.op == "jr"
            if ends:
                k = i + 1
                dead = []
                while k < len(self.items) and not self.items[k].is_label:
                    if self.items[k].is_instruction:
                        dead.append(k)
                    elif self.items[k].is_comment and self.items[k].comment.startswith("----"):
                        break
                    k += 1
                if dead:
                    removed = [self.items[d] for d in dead]
                    self._log("codigo_inalcanzable", removed, [])
                    for d in reversed(dead):
                        del self.items[d]
                    changed = True
            i += 1
        return changed

    def rule_salto_al_siguiente(self) -> bool:
        changed = False
        i = 0
        while i < len(self.items):
            line = self.items[i]
            if self._is_jump(line) and line.args[-1] in self._labels_after(i):
                self._replace(i, 1, [], "salto_al_siguiente")
                changed = True
                continue
            i += 1
        return changed

    def rule_salto_sobre_salto(self) -> bool:
        changed = False
        for i, line in enumerate(self.items):
            if line.op not in CONDITIONAL:
                continue
            j = self._next_instruction(i)
            if j is None or self.items[j].op not in UNCONDITIONAL:
                continue
            if line.args[-1] not in self._labels_after(j):
                continue
            inverted = Asm(INVERSE[line.op], (*line.args[:-1], self.items[j].args[0]), line.comment)
            self._log("salto_sobre_salto", [line, self.items[j]], [inverted])
            self.items[i] = inverted
            del self.items[j]
            return True or changed
        return changed

    def rule_salto_encadenado(self) -> bool:
        first_after: dict[str, Asm] = {}
        for i, line in enumerate(self.items):
            if line.is_label:
                k = self._next_code(i)
                while k is not None and self.items[k].is_label:
                    k = self._next_code(k)
                if k is not None:
                    first_after[line.args[0]] = self.items[k]
        changed = False
        for i, line in enumerate(self.items):
            if not self._is_jump(line):
                continue
            target = line.args[-1]
            seen = {target}
            final = target
            while final in first_after and first_after[final].op in UNCONDITIONAL:
                nxt = first_after[final].args[0]
                if nxt in seen:
                    break
                seen.add(nxt)
                final = nxt
            if final != target and first_after.get(target) is not line:
                new = Asm(line.op, (*line.args[:-1], final), line.comment)
                self._log("salto_encadenado", [line], [new])
                self.items[i] = new
                changed = True
        return changed

    def rule_carga_tras_almacenar(self) -> bool:
        changed = False
        i = 0
        while i < len(self.items):
            line = self.items[i]
            j = self._next_instruction(i) if line.op == "sw" else None
            if j is not None and self.items[j].op == "lw" and self.items[j].args[1] == line.args[1]:
                load = self.items[j]
                if load.args[0] == line.args[0]:
                    self._replace(j, 1, [], "carga_tras_almacenar")
                else:
                    self._replace(j, 1, [Asm("move", (load.args[0], line.args[0]), load.comment)],
                                  "carga_tras_almacenar")
                changed = True
            i += 1
        return changed

    def rule_movimiento_redundante(self) -> bool:
        changed = False
        i = 0
        while i < len(self.items):
            line = self.items[i]
            if line.op == "move":
                if line.args[0] == line.args[1]:
                    self._replace(i, 1, [], "movimiento_redundante")
                    changed = True
                    continue
                j = self._next_instruction(i)
                if j is not None and self.items[j].op == "move" and \
                        self.items[j].args == (line.args[1], line.args[0]):
                    self._replace(j, 1, [], "movimiento_redundante")
                    changed = True
            i += 1
        return changed

    def rule_identidad_algebraica(self) -> bool:
        changed = False
        i = 0
        while i < len(self.items):
            line = self.items[i]
            new = None
            if line.op in {"addiu", "sll", "srl", "sra", "xori", "ori"} and line.args[2] == "0":
                new = [] if line.args[0] == line.args[1] else [Asm("move", (line.args[0], line.args[1]))]
            elif line.op in {"addu", "or", "xor"} and "$zero" in line.args[1:]:
                other = line.args[1] if line.args[2] == "$zero" else line.args[2]
                new = [] if line.args[0] == other else [Asm("move", (line.args[0], other))]
            elif line.op == "subu" and line.args[2] == "$zero":
                new = [] if line.args[0] == line.args[1] else [Asm("move", (line.args[0], line.args[1]))]
            elif line.op == "mul" and "$zero" in line.args[1:]:
                new = [Asm("li", (line.args[0], "0"))]
            if new is not None:
                self._replace(i, 1, new, "identidad_algebraica")
                changed = True
                if not new:
                    continue
            elif line.op == "li" and line.args[0] == "$t9" and line.args[1] in {"0", "1"}:
                j = self._next_instruction(i)
                if j is not None and self.items[j].op == "mul" and self.items[j].args[1:].count("$t9") == 1:
                    mul = self.items[j]
                    other = mul.args[1] if mul.args[2] == "$t9" else mul.args[2]
                    if line.args[1] == "1":
                        new = [] if mul.args[0] == other else [Asm("move", (mul.args[0], other))]
                    else:
                        new = [Asm("li", (mul.args[0], "0"))]
                    self._replace(i, j - i + 1, new, "identidad_algebraica")
                    changed = True
                    if not new:
                        continue
            i += 1
        return changed

    def rule_reduccion_de_fuerza(self) -> bool:
        changed = False
        for i, line in enumerate(self.items):
            if line.op != "li" or line.args[0] != "$t9":
                continue
            try:
                value = int(line.args[1])
            except ValueError:
                continue
            j = self._next_instruction(i)
            if j is None or not _is_power_of_two(value):
                continue
            mul = self.items[j]
            if mul.op != "mul" or mul.args[1:].count("$t9") != 1:
                continue
            other = mul.args[1] if mul.args[2] == "$t9" else mul.args[2]
            shift = Asm("sll", (mul.args[0], other, str(value.bit_length() - 1)))
            self._replace(i, j - i + 1, [shift], "reduccion_de_fuerza")
            return True
        return changed

    def rule_propagacion_de_copia(self) -> bool:
        for i, line in enumerate(self.items):
            if line.op != "move" or line.args[0] == line.args[1] or line.args[0] not in TEMP_REGS:
                continue
            copy, source = line.args
            j = self._next_instruction(i)
            if j is None:
                continue
            nxt = self.items[j]
            if nxt.op not in THREE_REG | WITH_IMM | LOADS | {"move"} or nxt.args[0] != copy:
                continue
            if nxt.op in LOADS:
                if _memory_base(nxt.args[1]) != copy:
                    continue
                args = (nxt.args[0], nxt.args[1].replace(f"({copy})", f"({source})"))
            else:
                if copy not in nxt.args[1:]:
                    continue
                args = (nxt.args[0], *(source if arg == copy else arg for arg in nxt.args[1:]))
            new = Asm(nxt.op, args, nxt.comment or line.comment)
            self._log("propagacion_de_copia", [line, nxt], [new])
            self.items[j] = new
            del self.items[i]
            return True
        return False

    def rule_resultado_directo(self) -> bool:
        for i, line in enumerate(self.items):
            if line.op not in PURE or line.args[0] not in TEMP_REGS:
                continue
            j = self._next_instruction(i)
            if j is None:
                continue
            move = self.items[j]
            if move.op != "move" or move.args != ("$v0", line.args[0]):
                continue
            k = self._next_instruction(j)
            returns = (k is not None and self.items[k].op in UNCONDITIONAL
                       and self.items[k].args[0] in self.return_labels) \
                or bool(self._labels_after(j) & self.return_labels)
            if not returns:
                continue
            new = Asm(line.op, ("$v0", *line.args[1:]), line.comment or move.comment)
            self._log("resultado_directo", [line, move], [new])
            self.items[i] = new
            del self.items[j]
            return True
        return False

    def rule_etiqueta_sin_uso(self) -> bool:
        referenced: set[str] = set()
        for line in self.items:
            if line.is_instruction:
                referenced.update(line.args)
        removed = [i for i, line in enumerate(self.items)
                   if line.is_label and line.args[0] in self.local_labels and line.args[0] not in referenced]
        for i in reversed(removed):
            self._log("etiqueta_sin_uso", [self.items[i]], [])
            del self.items[i]
        return bool(removed)

    # ------------------------------------------------------------------ ciclo
    def run(self) -> list[Asm]:
        rules = [
            self.rule_codigo_inalcanzable,
            self.rule_salto_sobre_salto,
            self.rule_salto_encadenado,
            self.rule_salto_al_siguiente,
            self.rule_etiqueta_sin_uso,
            self.rule_carga_tras_almacenar,
            self.rule_movimiento_redundante,
            self.rule_identidad_algebraica,
            self.rule_reduccion_de_fuerza,
            self.rule_propagacion_de_copia,
            self.rule_resultado_directo,
        ]
        for _ in range(self.MAX_PASSES):
            self.report.passes += 1
            changed = False
            for rule in rules:
                while rule():
                    changed = True
            if not changed:
                break
        self.report.instructions_after = sum(1 for line in self.items if line.is_instruction)
        return self.items


def optimize(text: list[Asm], local_labels=(), return_labels=()) -> tuple[list[Asm], PeepholeReport]:
    optimizer = PeepholeOptimizer(text, local_labels, return_labels)
    return optimizer.run(), optimizer.report
