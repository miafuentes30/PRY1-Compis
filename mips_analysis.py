"""Análisis del TAC previo a la generación de MIPS (Proyecto 3).

Este módulo no emite código. Prepara la información que necesitan el
asignador de registros y el generador:

* separa el TAC en unidades de código (``main``, funciones, métodos e
  inicializadores de campos);
* clasifica operandos (temporal, variable, constante);
* construye bloques básicos y el grafo de flujo de control, incluidas las
  aristas excepcionales hacia los manejadores ``catch``;
* calcula variables vivas por bloque y por instrucción (análisis de flujo de
  datos hacia atrás) y el siguiente uso de cada nombre;
* fusiona ``t = <operación>; x = t`` cuando ``t`` muere, para que el resultado
  se calcule directamente en el destino final.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tac_ir import FunctionInfo, Instruction, TACProgram

TEMP_RE = re.compile(r"t\d+$")
INFINITE = 10 ** 9

# Instrucciones que pueden lanzar un error en tiempo de ejecución (y por lo
# tanto transferir el control a un manejador ``catch``).
THROWING = {
    "ARRAY_GET", "ARRAY_SET", "ARRAY_LEN", "GET_FIELD", "SET_FIELD",
    "CALL", "CALL_METHOD", "INIT_FIELDS",
}
BLOCK_ENDERS = {"GOTO", "IF_FALSE", "IF_TRUE", "RETURN"}
NO_CODE = {"CLASS", "ENDCLASS", "FIELD", "CLOSURE", "PARAM"}


def is_string_literal(text: str) -> bool:
    return text.startswith('"')


def is_temp(text: str) -> bool:
    return bool(TEMP_RE.match(text))


def is_variable(text: str) -> bool:
    if is_string_literal(text):
        return False
    return text == "this" or "@s" in text


def is_name(text: str) -> bool:
    return is_temp(text) or is_variable(text)


def is_const(text: str) -> bool:
    return not is_name(text)


def const_int(text: str) -> int | None:
    """Valor entero de una constante escalar; ``None`` si es una cadena."""
    if text in {"false", "null"}:
        return 0
    if text == "true":
        return 1
    try:
        return int(text)
    except ValueError:
        return None


def scope_of(name: str) -> int:
    return int(name.rsplit("@s", 1)[1])


def can_throw(ins: Instruction) -> bool:
    if ins.opcode in THROWING:
        return not (ins.opcode == "ARRAY_SET" and ins.note == "literal")
    return ins.opcode == "BIN" and ins.args[2] in {"/", "%"}


def receiver_of(ins: Instruction) -> tuple[str, str]:
    """Receptor y método de ``CALL_METHOD dest, obj.metodo, n``."""
    receiver, method = ins.args[1].rsplit(".", 1)
    return receiver, method


def uses_defs(ins: Instruction, call_args: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """Nombres leídos y escritos por una instrucción TAC."""
    op, a = ins.opcode, ins.args
    uses: list[str] = []
    defs: list[str] = []
    if op == "MOVE":
        defs, uses = [a[0]], [a[1]]
    elif op == "DECLARE":
        defs = [a[0]]
    elif op == "BIN":
        defs, uses = [a[0]], [a[1], a[3]]
    elif op == "UNARY":
        defs, uses = [a[0]], [a[2]]
    elif op in {"IF_FALSE", "IF_TRUE"}:
        uses = [a[0]]
    elif op == "CALL":
        defs, uses = [a[0]], list(call_args)
    elif op == "CALL_METHOD":
        defs, uses = [a[0]], [receiver_of(ins)[0], *call_args]
    elif op == "RETURN":
        uses = list(a[:1])
    elif op == "PRINT":
        uses = [a[0]]
    elif op in {"NEW_ARRAY", "NEW"}:
        defs = [a[0]]
    elif op == "ARRAY_GET":
        defs, uses = [a[0]], [a[1], a[2]]
    elif op == "ARRAY_SET":
        uses = [a[0], a[1], a[2]]
    elif op == "ARRAY_LEN":
        defs, uses = [a[0]], [a[1]]
    elif op == "INIT_FIELDS":
        uses = [a[0]]
    elif op == "GET_FIELD":
        defs, uses = [a[0]], [a[1]]
    elif op == "SET_FIELD":
        uses = [a[0], a[2]]
    elif op == "CATCH":
        defs = [a[0]]
    return [u for u in uses if is_name(u)], [d for d in defs if is_name(d)]


@dataclass
class Block:
    index: int
    start: int
    end: int                                   # intervalo [start, end) en unit.code
    successors: list[int] = field(default_factory=list)
    handlers: list[int] = field(default_factory=list)   # bloques catch alcanzables por excepción
    use: set[str] = field(default_factory=set)
    define: set[str] = field(default_factory=set)
    live_in: set[str] = field(default_factory=set)
    live_out: set[str] = field(default_factory=set)
    handler_live: set[str] = field(default_factory=set)  # vivos al entrar a sus manejadores


@dataclass
class Unit:
    """Unidad de código: ``main``, una función, un método o ``Clase.$fields``."""
    info: FunctionInfo
    code: list[Instruction]
    blocks: list[Block] = field(default_factory=list)
    block_of: list[int] = field(default_factory=list)
    call_args: dict[int, tuple[str, ...]] = field(default_factory=dict)
    live_after: list[set[str]] = field(default_factory=list)
    next_use: list[dict[str, int]] = field(default_factory=list)
    loop_depth: list[int] = field(default_factory=list)
    try_labels: list[str] = field(default_factory=list)
    coalesced: int = 0

    @property
    def label(self) -> str:
        return self.info.label


def split_units(program: TACProgram) -> list[Unit]:
    """Divide el TAC lineal en unidades. ``main`` es todo lo anterior al primer ``func``."""
    units: list[Unit] = []
    current: list[Instruction] = []
    current_info = program.functions["main"]
    for ins in program.instructions:
        if ins.opcode == "FUNC":
            units.append(Unit(current_info, current))
            current_info = program.functions[ins.args[0]]
            current = []
        elif ins.opcode == "ENDFUNC":
            continue
        elif ins.opcode == "LABEL" and ins.args[0] == "main" and current_info.kind == "main" and not current:
            continue
        else:
            current.append(ins)
    units.append(Unit(current_info, current))
    return units


class UnitAnalyzer:
    """Bloques básicos, flujo de control y análisis de vida de una unidad."""

    def __init__(self, unit: Unit, tracked) -> None:
        self.unit = unit
        self.tracked = tracked          # predicado: ¿el nombre pertenece al marco de esta unidad?

    # -- preparación -----------------------------------------------------
    def run(self) -> Unit:
        self._bind_call_arguments()
        self._analyze()
        if self._coalesce_copies():
            self._bind_call_arguments()
            self._analyze()
        return self.unit

    def _bind_call_arguments(self) -> None:
        """Asocia a cada llamada los ``param`` contiguos que la preceden."""
        code = self.unit.code
        self.unit.call_args = {}
        for i, ins in enumerate(code):
            if ins.opcode in {"CALL", "CALL_METHOD"}:
                count = int(ins.args[2])
                params = code[i - count:i] if count else []
                if len(params) != count or any(p.opcode != "PARAM" for p in params):
                    raise ValueError(f"llamada sin sus {count} parámetros contiguos: {ins}")
                self.unit.call_args[i] = tuple(p.args[0] for p in params)

    def _uses_defs(self, i: int) -> tuple[list[str], list[str]]:
        uses, defs = uses_defs(self.unit.code[i], self.unit.call_args.get(i, ()))
        return [u for u in uses if self.tracked(u)], [d for d in defs if self.tracked(d)]

    # -- bloques y CFG ---------------------------------------------------
    def _analyze(self) -> None:
        unit, code = self.unit, self.unit.code
        n = len(code)
        leaders = {0} if n else set()
        for i, ins in enumerate(code):
            if ins.opcode == "LABEL":
                leaders.add(i)
            if ins.opcode in BLOCK_ENDERS and i + 1 < n:
                leaders.add(i + 1)
        starts = sorted(leaders)
        unit.blocks = [Block(k, s, starts[k + 1] if k + 1 < len(starts) else n) for k, s in enumerate(starts)]
        unit.block_of = [0] * n
        for block in unit.blocks:
            for i in range(block.start, block.end):
                unit.block_of[i] = block.index
        label_index = {ins.args[0]: i for i, ins in enumerate(code) if ins.opcode == "LABEL"}

        for block in unit.blocks:
            last = code[block.end - 1]
            if last.opcode == "GOTO":
                block.successors = [unit.block_of[label_index[last.args[0]]]]
            elif last.opcode in {"IF_FALSE", "IF_TRUE"}:
                block.successors = [unit.block_of[label_index[last.args[1]]]]
                if block.end < n:
                    block.successors.append(unit.block_of[block.end])
            elif last.opcode != "RETURN" and block.end < n:
                block.successors = [unit.block_of[block.end]]

        # Regiones protegidas: todo bloque entre ``push_handler L`` y ``L:`` puede
        # saltar al manejador ``L`` si ocurre un error en tiempo de ejecución.
        unit.try_labels = []
        for i, ins in enumerate(code):
            if ins.opcode == "TRY":
                handler = ins.args[0]
                unit.try_labels.append(handler)
                target = unit.block_of[label_index[handler]]
                for b in range(unit.block_of[i], target):
                    if target not in unit.blocks[b].handlers:
                        unit.blocks[b].handlers.append(target)

        # Profundidad de ciclo: cada salto hacia atrás encierra un ciclo.
        unit.loop_depth = [0] * n
        for i, ins in enumerate(code):
            target = None
            if ins.opcode == "GOTO":
                target = label_index[ins.args[0]]
            elif ins.opcode in {"IF_FALSE", "IF_TRUE"}:
                target = label_index[ins.args[1]]
            if target is not None and target <= i:
                for k in range(target, i + 1):
                    unit.loop_depth[k] += 1

        self._liveness()

    def _liveness(self) -> None:
        unit = self.unit
        for block in unit.blocks:
            block.use, block.define = set(), set()
            for i in range(block.start, block.end):
                uses, defs = self._uses_defs(i)
                block.use.update(u for u in uses if u not in block.define)
                block.define.update(defs)
            block.live_in, block.live_out = set(), set()
        changed = True
        while changed:
            changed = False
            for block in reversed(unit.blocks):
                out: set[str] = set()
                for s in block.successors + block.handlers:
                    out |= unit.blocks[s].live_in
                new_in = block.use | (out - block.define)
                # Una excepción puede ocurrir a mitad del bloque: lo que el
                # manejador necesita debe considerarse vivo en todo el bloque.
                for h in block.handlers:
                    new_in |= unit.blocks[h].live_in
                if out != block.live_out or new_in != block.live_in:
                    block.live_out, block.live_in = out, new_in
                    changed = True
        n = len(unit.code)
        unit.live_after = [set() for _ in range(n)]
        unit.next_use = [{} for _ in range(n)]
        for block in unit.blocks:
            block.handler_live = set()
            for h in block.handlers:
                block.handler_live |= unit.blocks[h].live_in
            live = set(block.live_out)
            upcoming: dict[str, int] = {name: INFINITE for name in live}
            for i in range(block.end - 1, block.start - 1, -1):
                unit.live_after[i] = set(live) | block.handler_live
                unit.next_use[i] = dict(upcoming)
                uses, defs = self._uses_defs(i)
                for d in defs:
                    live.discard(d)
                    upcoming.pop(d, None)
                for u in uses:
                    live.add(u)
                    upcoming[u] = i

    # -- fusión de copias ---------------------------------------------------
    COALESCABLE = {"BIN", "UNARY", "CALL", "CALL_METHOD", "ARRAY_GET", "ARRAY_LEN", "GET_FIELD"}

    def _coalesce_copies(self) -> int:
        """``t = op ...; x = t`` con ``t`` muerto después  =>  ``x = op ...``."""
        unit, code = self.unit, self.unit.code
        removed: set[int] = set()
        for i in range(len(code) - 1):
            ins, nxt = code[i], code[i + 1]
            if ins.opcode not in self.COALESCABLE or nxt.opcode != "MOVE":
                continue
            temp = ins.args[0]
            if not is_temp(temp) or nxt.args[1] != temp or not is_name(nxt.args[0]):
                continue
            if unit.block_of[i] != unit.block_of[i + 1] or temp in unit.live_after[i + 1]:
                continue
            if nxt.args[0] == temp:
                continue
            code[i] = Instruction(ins.opcode, (nxt.args[0], *ins.args[1:]), ins.source_line or nxt.source_line,
                                  ins.types, ins.note)
            removed.add(i + 1)
        if removed:
            unit.code = [ins for k, ins in enumerate(code) if k not in removed]
            unit.coalesced += len(removed)
        return len(removed)
