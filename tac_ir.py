"""IR de tres direcciones (Proyecto 2). El Proyecto 3 lo consume para generar MIPS.

Cada instrucción conserva, además de sus argumentos, los tipos estáticos que el
backend necesita (``types``) y una nota opcional (``note``). Ninguno de los dos
cambia la forma textual del TAC.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Instruction:
    opcode: str
    args: tuple[str, ...] = ()
    source_line: int = 0
    # Tipos estáticos de los operandos relevantes (p. ej. BIN: izq, der, resultado;
    # PRINT: valor; GET_FIELD/SET_FIELD/CALL_METHOD: clase estática del receptor).
    types: tuple[str, ...] = ()
    # Marca auxiliar para el backend ("literal" = escritura de un literal de arreglo).
    note: str = ''

    def __str__(self) -> str:
        op, a = self.opcode, self.args
        if op == 'LABEL': return f'{a[0]}:'
        if op == 'FUNC': return f'func {a[0]}({a[1]}):'
        if op == 'ENDFUNC': return f'endfunc {a[0]}'
        if op == 'CLASS': return f'class {a[0]}' + (f' extends {a[1]}' if a[1] else '')
        if op == 'ENDCLASS': return f'endclass {a[0]}'
        if op == 'DECLARE': return f'declare {a[0]}'
        if op == 'INIT_FIELDS': return f'init_fields {a[0]}, {a[1]}'
        if op == 'FIELD': return f'field {a[0]}.{a[1]}' + (f' = {a[2]}' if len(a)>2 else '')
        if op == 'MOVE': return f'{a[0]} = {a[1]}'
        if op == 'BIN': return f'{a[0]} = {a[1]} {a[2]} {a[3]}'
        if op == 'UNARY': return f'{a[0]} = {a[1]}{a[2]}'
        if op == 'GOTO': return f'goto {a[0]}'
        if op == 'IF_FALSE': return f'ifFalse {a[0]} goto {a[1]}'
        if op == 'IF_TRUE': return f'if {a[0]} goto {a[1]}'
        if op == 'PARAM': return f'param {a[0]}'
        if op == 'CALL': return f'{a[0]} = call {a[1]}, {a[2]}' if a[0]!='_' else f'call {a[1]}, {a[2]}'
        if op == 'CALL_METHOD': return f'{a[0]} = callmethod {a[1]}, {a[2]}'
        if op == 'RETURN': return f'return {a[0]}' if a else 'return'
        if op == 'PRINT': return f'print {a[0]}'
        if op == 'NEW_ARRAY': return f'{a[0]} = new_array {a[1]}'
        if op == 'ARRAY_GET': return f'{a[0]} = {a[1]}[{a[2]}]'
        if op == 'ARRAY_SET': return f'{a[0]}[{a[1]}] = {a[2]}'
        if op == 'ARRAY_LEN': return f'{a[0]} = length {a[1]}'
        if op == 'NEW': return f'{a[0]} = new {a[1]}'
        if op == 'GET_FIELD': return f'{a[0]} = {a[1]}.{a[2]}'
        if op == 'SET_FIELD': return f'{a[0]}.{a[1]} = {a[2]}'
        if op == 'TRY': return f'push_handler {a[0]}'
        if op == 'END_TRY': return 'pop_handler'
        if op == 'CATCH': return f'catch {a[0]}'
        if op == 'CLOSURE': return f'{a[0]} = closure {a[1]} env {a[2]}'
        return f'{op.lower()} ' + ', '.join(a)


@dataclass
class FunctionInfo:
    """Metadatos de una unidad de código (main, función, método o inicializador)."""
    label: str                      # etiqueta TAC: main, f@s0, Clase.metodo, Clase.$fields
    kind: str                       # main | function | method | fields
    scope_id: int                   # ámbito propio de la función en la tabla de símbolos
    parent_scope: int = 0           # ámbito donde fue declarada
    owner_class: str | None = None
    params: tuple[str, ...] = ()    # nombres TAC de los parámetros (sin this)
    return_type: str = 'void'
    line: int = 0

    @property
    def has_this(self) -> bool:
        return self.kind in {'method', 'fields'}


@dataclass
class TACProgram:
    instructions: list[Instruction] = field(default_factory=list)
    peak_temporaries: int = 0
    allocated_temporaries: int = 0
    reused_temporaries: int = 0
    frame_temporaries: dict[str, int] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)

    def render(self, numbered: bool = False) -> str:
        if not numbered:
            return '\n'.join(str(i) for i in self.instructions)
        return '\n'.join(f'{n:04d}  {i}' for n, i in enumerate(self.instructions, 1))


class TemporaryPool:
    """Liberación explícita por último uso; cada función mantiene su propio pool."""
    def __init__(self):
        self.next_id = 0
        self.free: list[str] = []
        self.active: set[str] = set()
        self.peak = 0
        self.reused = 0

    def acquire(self) -> str:
        if self.free:
            name = self.free.pop()
            self.reused += 1
        else:
            name = f't{self.next_id}'
            self.next_id += 1
        self.active.add(name)
        self.peak = max(self.peak, len(self.active))
        return name

    def release(self, name: str) -> None:
        if name in self.active:
            self.active.remove(name)
            self.free.append(name)
