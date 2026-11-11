"""Registros de activación, almacenamiento y diseño de clases para MIPS (Proyecto 3).

Decide, antes de generar código, dónde vive cada nombre del TAC:

* ``$s0``–``$s7``: variables locales y parámetros más usados de cada función
  (registros preservados por el llamado; sobreviven a las llamadas);
* marco de pila (desplazamiento respecto a ``$fp``): variables capturadas por
  funciones anidadas, variables vivas en un ``catch``, las que no alcanzaron
  registro y los temporales derramados;
* segmento ``.data``: variables globales (del programa principal) que usan las
  funciones o que no obtuvieron registro.

También calcula el enlace de acceso (static link) de las funciones anidadas y
el diseño de objetos y tablas de métodos virtuales para clases y herencia.

Forma del registro de activación (la pila crece hacia direcciones bajas)::

        ...                       argumentos 5.º en adelante   4*(i-4)($fp)
    $fp ->  ------------------------------------------------   (= $sp del llamador)
            dirección de retorno ($ra)                         -4($fp)
            $fp del llamador (enlace de control)               -8($fp)
            enlace de acceso (solo funciones anidadas)        -12($fp)
            registros $s preservados
            variables locales y parámetros en memoria
            registros de manejadores try/catch (16 bytes c/u)
            temporales derramados
    $sp ->  ------------------------------------------------
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mips_analysis import Unit, is_temp, is_variable, scope_of, uses_defs

SAVED_REGS = [f"$s{i}" for i in range(8)]
ARG_REGS = ["$a0", "$a1", "$a2", "$a3"]
WORD = 4
HANDLER_RECORD_WORDS = 4      # anterior, dirección del manejador, $sp, $fp


class CodegenError(Exception):
    """Construcción que el backend MIPS no puede traducir."""


@dataclass
class ClassLayout:
    name: str
    parent: str | None
    fields: list[tuple[str, str]] = field(default_factory=list)       # (campo, clase que lo declara)
    field_offset: dict[str, int] = field(default_factory=dict)
    methods: list[tuple[str, str]] = field(default_factory=list)      # (método, etiqueta TAC que lo implementa)
    method_offset: dict[str, int] = field(default_factory=dict)
    init_chain: list[str] = field(default_factory=list)               # Clase.$fields de raíz a hoja

    @property
    def size(self) -> int:
        return WORD * (1 + len(self.fields))


def build_class_layouts(classes, functions) -> dict[str, ClassLayout]:
    """Diseño de objetos (vtable + campos heredados primero) y de las vtables.

    Un método sobrescrito conserva la posición del método del padre: así una
    llamada compilada contra la clase base ejecuta la versión de la hija.
    """
    layouts: dict[str, ClassLayout] = {}

    def build(name: str) -> ClassLayout:
        if name in layouts:
            return layouts[name]
        info = classes[name]
        parent = build(info.parent) if info.parent in classes else None
        layout = ClassLayout(name, info.parent if parent else None)
        if parent:
            layout.fields = list(parent.fields)
            layout.field_offset = dict(parent.field_offset)
            layout.methods = list(parent.methods)
            layout.method_offset = dict(parent.method_offset)
            layout.init_chain = list(parent.init_chain)
        for attr in info.attributes:
            layout.fields.append((attr, name))
            layout.field_offset[attr] = WORD * len(layout.fields)          # 0 = puntero a vtable
        for method in info.methods:
            label = f"{name}.{method}"
            if label not in functions:
                continue
            if method in layout.method_offset:
                slot = layout.method_offset[method] // WORD - 1
                layout.methods[slot] = (method, label)
            else:
                layout.methods.append((method, label))
                layout.method_offset[method] = WORD * len(layout.methods)  # 0 = nombre de la clase
        if f"{name}.$fields" in functions:
            layout.init_chain.append(f"{name}.$fields")
        layouts[name] = layout
        return layout

    for class_name in classes:
        build(class_name)
    return layouts


@dataclass
class Frame:
    """Registro de activación de una unidad de código."""
    label: str
    kind: str
    depth: int
    has_link: bool = False
    params: list[str] = field(default_factory=list)            # incluye ``this`` en métodos
    sreg: dict[str, str] = field(default_factory=dict)         # nombre -> $sN
    slots: dict[str, int] = field(default_factory=dict)        # nombre -> desplazamiento($fp)
    globals: dict[str, str] = field(default_factory=dict)      # nombre -> etiqueta .data
    try_records: dict[str, int] = field(default_factory=dict)  # etiqueta catch -> desplazamiento
    temp_slots: dict[str, int] = field(default_factory=dict)
    saved: list[str] = field(default_factory=list)             # $s a preservar
    saved_offsets: dict[str, int] = field(default_factory=dict)
    next_offset: int = -2 * WORD                               # último desplazamiento ocupado
    captured: set[str] = field(default_factory=set)
    weights: dict[str, int] = field(default_factory=dict)

    LINK_OFFSET = -3 * WORD

    def reserve(self, words: int = 1) -> int:
        self.next_offset -= WORD * words
        return self.next_offset

    def temp_slot(self, name: str) -> int:
        if name not in self.temp_slots:
            self.temp_slots[name] = self.reserve()
        return self.temp_slots[name]

    @property
    def size(self) -> int:
        size = -self.next_offset
        return (size + 7) // 8 * 8

    def describe(self) -> list[tuple[str, str, str]]:
        """Filas (ubicación, contenido, nota) para mostrar el marco en el IDE."""
        rows: list[tuple[str, str, str]] = []
        for i, name in enumerate(self.params):
            origin = ARG_REGS[i] if i < 4 else f"{WORD * (i - 4)}($fp)"
            rows.append((origin, f"parámetro {name}", "entrada"))
        rows.append(("-4($fp)", "dirección de retorno $ra", "enlace"))
        rows.append(("-8($fp)", "$fp del llamador", "enlace de control"))
        if self.has_link:
            rows.append((f"{self.LINK_OFFSET}($fp)", "enlace de acceso (marco de la función contenedora)", "enlace"))
        for reg in self.saved:
            rows.append((f"{self.saved_offsets[reg]}($fp)", f"{reg} preservado", "callee-saved"))
        for name, offset in sorted(self.slots.items(), key=lambda kv: -kv[1]):
            note = "capturada por función anidada" if name in self.captured else "variable en memoria"
            rows.append((f"{offset}($fp)", name, note))
        for handler, offset in sorted(self.try_records.items(), key=lambda kv: -kv[1]):
            rows.append((f"{offset}($fp)", f"registro try/catch → {handler}", "16 bytes"))
        for name, offset in sorted(self.temp_slots.items(), key=lambda kv: -kv[1]):
            rows.append((f"{offset}($fp)", f"temporal {name}", "derrame / caller-saved"))
        for name, reg in sorted(self.sreg.items(), key=lambda kv: kv[1]):
            rows.append((reg, name, "variable en registro"))
        for name, label in sorted(self.globals.items()):
            rows.append((label, name, "global en .data"))
        return rows


class ProgramLayout:
    """Propiedad de variables, capturas, enlaces de acceso y marcos."""

    def __init__(self, program, symbols, classes, units: list[Unit]) -> None:
        self.program = program
        self.symbols = symbols
        self.units = {unit.label: unit for unit in units}
        self.order = [unit.label for unit in units]
        self.class_layouts = build_class_layouts(classes, program.functions)
        self.function_scope = {
            info.scope_id: label for label, info in program.functions.items()
            if info.kind in {"function", "method"}
        }
        self.parent: dict[str, str | None] = {}
        self.depth: dict[str, int] = {}
        for label in self.order:
            info = program.functions[label]
            self.parent[label] = None if info.kind == "main" else self.owner_of_scope(info.parent_scope)
        for label in self.order:
            self.depth[label] = len(self.ancestors(label))
        self.frames: dict[str, Frame] = {}
        self._owner_cache: dict[tuple[str, str], str] = {}

    # -- propiedad -------------------------------------------------------
    def owner_of_scope(self, scope_id: int) -> str:
        current: int | None = scope_id
        while current is not None:
            if current in self.function_scope:
                return self.function_scope[current]
            current = self.symbols.scopes[current].parent_id
        return "main"

    def ancestors(self, label: str) -> list[str]:
        chain: list[str] = []
        current = self.parent.get(label)
        while current is not None:
            chain.append(current)
            current = self.parent.get(current)
        return chain

    def owner(self, name: str, unit_label: str) -> str:
        """Unidad en cuyo registro de activación vive ``name`` visto desde ``unit_label``."""
        key = (name, unit_label)
        if key in self._owner_cache:
            return self._owner_cache[key]
        if is_temp(name):
            result = unit_label
        elif name == "this":
            result = next((u for u in [unit_label, *self.ancestors(unit_label)]
                           if self.program.functions[u].has_this), None)
            if result is None:
                raise CodegenError("uso de this fuera de un método")
        else:
            result = self.owner_of_scope(scope_of(name))
        self._owner_cache[key] = result
        return result

    def has_link(self, label: str) -> bool:
        """Solo las funciones anidadas en otra función reciben enlace de acceso."""
        info = self.program.functions[label]
        return info.kind == "function" and self.parent[label] not in {None, "main"}

    def hops(self, from_label: str, to_label: str) -> int:
        """Número de enlaces de acceso a seguir desde ``from_label`` hasta ``to_label``."""
        count, current = 0, from_label
        while current != to_label:
            if current is None or not self.has_link(current):
                raise CodegenError(
                    f"la unidad {from_label} no puede alcanzar el marco de {to_label} "
                    "(una clase declarada dentro de una función no puede capturar sus variables)")
            current = self.parent[current]
            count += 1
        return count

    # -- almacenamiento ----------------------------------------------------
    def plan(self) -> None:
        captured: dict[str, set[str]] = {label: set() for label in self.order}
        weights: dict[str, dict[str, int]] = {label: {} for label in self.order}
        for label in self.order:
            unit = self.units[label]
            for i, ins in enumerate(unit.code):
                uses, defs = uses_defs(ins, unit.call_args.get(i, ()))
                weight = 10 ** min(unit.loop_depth[i], 3)
                for name in uses + defs:
                    if not is_variable(name):
                        continue
                    owner = self.owner(name, label)
                    if owner != label:
                        captured[owner].add(name)
                        if owner != "main":
                            self.hops(label, owner)      # valida que el marco sea alcanzable
                    else:
                        weights[label][name] = weights[label].get(name, 0) + weight

        for label in self.order:
            unit, info = self.units[label], self.program.functions[label]
            frame = Frame(label, info.kind, self.depth[label], has_link=self.has_link(label))
            frame.params = (["this"] if info.has_this else []) + list(info.params)
            frame.captured = captured[label]
            frame.weights = weights[label]
            if frame.has_link:
                frame.reserve()                                   # -12($fp)
            locals_ = set(weights[label]) | {p for p in frame.params if p in captured[label]}

            protected: set[str] = set()                           # vivas al entrar a un catch
            for block in unit.blocks:
                protected |= block.handler_live
            candidates = sorted(
                (n for n in locals_ if n not in captured[label] and n not in protected),
                key=lambda n: (-weights[label].get(n, 0), n))
            for name, reg in zip(candidates, SAVED_REGS):
                frame.sreg[name] = reg
            if info.kind != "main":
                frame.saved = sorted(frame.sreg.values())
                for reg in frame.saved:
                    frame.saved_offsets[reg] = frame.reserve()

            for name in sorted(locals_ - set(frame.sreg)):
                if label == "main":
                    scope = scope_of(name)
                    base = name.rsplit("@s", 1)[0]
                    frame.globals[name] = f"g_{base}" if scope == 0 else f"gs{scope}_{base}"
                elif name in frame.params and frame.params.index(name) >= 4:
                    frame.slots[name] = WORD * (frame.params.index(name) - 4)
                else:
                    frame.slots[name] = frame.reserve()
            for handler in unit.try_labels:
                frame.try_records[handler] = frame.reserve(HANDLER_RECORD_WORDS)
            self.frames[label] = frame
