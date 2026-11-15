"""Simulador MIPS integrado y traza del árbol de activación (Proyecto 3).

Ejecuta el ensamblador que produce el compilador sin depender de programas
externos, para que el IDE y la batería de pruebas puedan correr los programas
y mostrar el **árbol de activación** real de cada ejecución. El mismo archivo
``.asm`` corre sin cambios en MARS, SPIM y QtSpim (ver ``mips_external.py``);
este simulador implementa el subconjunto de instrucciones, pseudoinstrucciones,
directivas y servicios del sistema que el compilador emite.

Mapa de memoria (igual al de MARS): texto en ``0x00400000``, datos en
``0x10010000``, heap en ``0x10040000`` y pila descendente desde ``0x7fffeffc``.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

TEXT_BASE = 0x00400000
DATA_BASE = 0x10010000
HEAP_BASE = 0x10040000
STACK_TOP = 0x7FFFF000
INITIAL_SP = 0x7FFFEFFC
STACK_BYTES = 4 * 1024 * 1024
HEAP_LIMIT = 64 * 1024 * 1024
MAX_OUTPUT_CHARS = 400_000
WORD_STRUCT = struct.Struct("<i")

REGISTER_NAMES = [
    "$zero", "$at", "$v0", "$v1", "$a0", "$a1", "$a2", "$a3",
    "$t0", "$t1", "$t2", "$t3", "$t4", "$t5", "$t6", "$t7",
    "$s0", "$s1", "$s2", "$s3", "$s4", "$s5", "$s6", "$s7",
    "$t8", "$t9", "$k0", "$k1", "$gp", "$sp", "$fp", "$ra",
]
REGISTERS = {name: i for i, name in enumerate(REGISTER_NAMES)}
REGISTERS.update({f"${i}": i for i in range(32)})
REGISTERS["$s8"] = 30
V0, V1, A0, SP, FP, RA = 2, 3, 4, 29, 30, 31


class MipsError(Exception):
    """Error de ensamblado o de ejecución del programa MIPS."""


class _Exit(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


def s32(value: int) -> int:
    return ((value + 0x80000000) & 0xFFFFFFFF) - 0x80000000


def u32(value: int) -> int:
    return value & 0xFFFFFFFF


@dataclass
class ActivationNode:
    """Una activación (llamada) de una función: nodo del árbol de activación."""
    name: str
    arguments: str = ""
    depth: int = 0
    result: str = ""
    status: str = "activa"            # activa | retornó | excepción
    frame_size: int = 0
    frame_pointer: int = 0
    children: list["ActivationNode"] = field(default_factory=list)
    entry_sp: int = 0
    order: int = 0

    def label(self) -> str:
        text = f"{self.name}({self.arguments})"
        if self.status == "retornó" and self.result:
            text += f" → {self.result}"
        elif self.status == "excepción":
            text += "  ✗ terminada por una excepción"
        elif self.status == "activa":
            text += "  (activa al terminar el programa)"
        return text

    def render(self, indent: str = "", last: bool = True, root: bool = True) -> list[str]:
        if root:
            lines = [self.label()]
            child_indent = ""
        else:
            lines = [f"{indent}{'└── ' if last else '├── '}{self.label()}"]
            child_indent = indent + ("    " if last else "│   ")
        for k, child in enumerate(self.children):
            lines.extend(child.render(child_indent, k == len(self.children) - 1, False))
        return lines


@dataclass
class RunResult:
    output: str = ""
    exit_code: int = 0
    steps: int = 0
    error: str = ""
    finished: bool = False
    tree: ActivationNode | None = None
    calls: int = 0
    max_depth: int = 0
    max_stack_bytes: int = 0
    heap_bytes: int = 0
    tree_truncated: bool = False
    calls_by_function: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.finished and not self.error

    def tree_text(self) -> str:
        if self.tree is None:
            return ""
        lines = self.tree.render()
        if self.tree_truncated:
            lines.append("… (árbol truncado: demasiadas activaciones para mostrarlas todas)")
        return "\n".join(lines)


class _Tracer:
    """Construye el árbol de activación observando ``jal``/``jalr``/``jr $ra``."""

    MAX_NODES = 4000

    def __init__(self, sim: "MipsSimulator") -> None:
        self.sim = sim
        self.root = ActivationNode("main", entry_sp=INITIAL_SP + 4)
        self.stack: list[ActivationNode | None] = [self.root]
        self.metas: list = [None]
        self.nodes = 1
        self.calls = 0
        self.max_depth = 0
        self.truncated = False
        self.by_function: dict[str, int] = {}

    def enter(self, meta) -> None:
        sim = self.sim
        self.calls += 1
        self.by_function[meta.name] = self.by_function.get(meta.name, 0) + 1
        depth = len(self.stack)
        self.max_depth = max(self.max_depth, depth)
        node = None
        parent = self.stack[-1]
        if self.nodes < self.MAX_NODES and parent is not None:
            sp = sim.R[SP]
            shown = []
            for k, (name, type_name) in enumerate(meta.params):
                raw = sim.R[A0 + k] if k < 4 else sim.read_word(sp + 4 * (k - 4))
                if name == "this":
                    shown.append(f"this=<{type_name}>")
                else:
                    shown.append(f"{name}={sim.format_value(raw, type_name)}")
            node = ActivationNode(meta.name, ", ".join(shown), depth, frame_size=meta.frame_size,
                                  frame_pointer=sp, entry_sp=sp, order=self.calls)
            parent.children.append(node)
            self.nodes += 1
        else:
            self.truncated = True
        # Si el árbol ya está lleno se registra None: la activación existe pero no se dibuja.
        self.stack.append(node)
        self.metas.append((meta, sim.R[SP]))

    def leave(self) -> None:
        if len(self.stack) <= 1:
            return
        node = self.stack.pop()
        meta, _ = self.metas.pop()
        if node is not None:
            node.status = "retornó"
            if meta.return_type not in {"void", ""}:
                node.result = self.sim.format_value(self.sim.R[V0], meta.return_type)

    def unwind(self) -> None:
        """Una excepción descartó marcos: se cierran las activaciones por encima del catch."""
        sp = self.sim.R[SP]
        while len(self.stack) > 1 and self.metas[-1][1] <= sp:
            node = self.stack.pop()
            self.metas.pop()
            if node is not None:
                node.status = "excepción"

    def finish(self) -> None:
        if self.root.status == "activa":
            self.root.status = "retornó"


class MipsSimulator:
    def __init__(self, source: str, functions=(), handler_labels=(), max_steps: int = 30_000_000) -> None:
        self.source = source
        self.max_steps = max_steps
        self.R = [0] * 32
        self.hi = 0
        self.lo = 0
        self.data = bytearray(HEAP_BASE - DATA_BASE)
        self.stack = bytearray(STACK_BYTES)
        self.stack_base = STACK_TOP - STACK_BYTES
        self.heap_top = HEAP_BASE
        self.labels: dict[str, int] = {}
        self.output: list[str] = []
        self.output_chars = 0
        self.code: list = []
        self.lines: list[tuple[str, list[str], int]] = []
        self.stop_requested = False
        self.min_sp = INITIAL_SP
        self._functions = {meta.asm_label: meta for meta in functions}
        self._handler_labels = set(handler_labels)
        self.tracer = _Tracer(self)
        self._assemble()

    # ================================================================== memoria
    def _offset(self, address: int, size: int):
        if address >= self.stack_base:
            off = address - self.stack_base
            if off + size <= STACK_BYTES:
                return self.stack, off
        elif address >= DATA_BASE:
            off = address - DATA_BASE
            if off + size <= len(self.data):
                return self.data, off
        if 0 <= address < 0x1000:
            raise MipsError(f"acceso a memoria con referencia nula (dirección 0x{u32(address):08x})")
        if HEAP_BASE <= address < self.stack_base:
            raise MipsError("desbordamiento de pila o de heap "
                            f"(dirección 0x{u32(address):08x}); ¿recursión sin caso base?")
        raise MipsError(f"dirección de memoria inválida 0x{u32(address):08x}")

    def read_word(self, address: int) -> int:
        if address & 3:
            raise MipsError(f"lectura de palabra en dirección no alineada 0x{u32(address):08x}")
        buf, off = self._offset(address, 4)
        return WORD_STRUCT.unpack_from(buf, off)[0]

    def write_word(self, address: int, value: int) -> None:
        if address & 3:
            raise MipsError(f"escritura de palabra en dirección no alineada 0x{u32(address):08x}")
        buf, off = self._offset(address, 4)
        WORD_STRUCT.pack_into(buf, off, value)

    def read_byte(self, address: int) -> int:
        buf, off = self._offset(address, 1)
        return buf[off]

    def write_byte(self, address: int, value: int) -> None:
        buf, off = self._offset(address, 1)
        buf[off] = value & 0xFF

    def read_string(self, address: int, limit: int = 100_000) -> str:
        chars = bytearray()
        while len(chars) < limit:
            byte = self.read_byte(address + len(chars))
            if byte == 0:
                break
            chars.append(byte)
        return chars.decode("latin-1")

    def format_value(self, raw: int, type_name: str) -> str:
        """Texto legible de un valor según su tipo estático (para el árbol de activación)."""
        try:
            if type_name == "integer":
                return str(raw)
            if type_name == "boolean":
                return "true" if raw else "false"
            if raw == 0 and type_name not in {"unknown", ""}:
                return "null"
            if type_name == "string":
                text = self.read_string(raw, 40)
                return '"' + (text[:28] + "…" if len(text) > 28 else text) + '"'
            if type_name.endswith("[]"):
                length = self.read_word(raw)
                element = type_name[:-2]
                if element in {"integer", "boolean", "string"} and length <= 6:
                    items = [self.format_value(self.read_word(raw + 4 * (k + 1)), element) for k in range(length)]
                    return "[" + ", ".join(items) + "]"
                return f"[arreglo de {length}]"
            if type_name in {"unknown", "", "null"}:
                return str(raw)
            return f"<{type_name}>"
        except MipsError:
            return str(raw)

    # ================================================================== ensamblado
    @staticmethod
    def _strip_comment(line: str) -> str:
        in_string = False
        k = 0
        while k < len(line):
            ch = line[k]
            if ch == "\\" and in_string:
                k += 2
                continue
            if ch == '"':
                in_string = not in_string
            elif ch == "#" and not in_string:
                return line[:k]
            k += 1
        return line

    @staticmethod
    def _unescape(text: str) -> bytes:
        out = bytearray()
        k = 0
        table = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34, "'": 39}
        while k < len(text):
            ch = text[k]
            if ch == "\\" and k + 1 < len(text) and text[k + 1] in table:
                out.append(table[text[k + 1]])
                k += 2
            else:
                out.extend(ch.encode("latin-1", "replace"))
                k += 1
        return bytes(out)

    def _assemble(self) -> None:
        section = "text"
        address = DATA_BASE
        fixups: list[tuple[int, str, int]] = []
        pending: list[str] = []            # etiquetas de datos aún sin directiva
        label_re = re.compile(r"^\s*([A-Za-z_.$][\w.$]*)\s*:")
        for number, raw in enumerate(self.source.split("\n"), 1):
            line = self._strip_comment(raw).strip()
            while True:
                match = label_re.match(line)
                if not match:
                    break
                name = match.group(1)
                if name in self.labels:
                    raise MipsError(f"línea {number}: etiqueta duplicada {name}")
                if section == "data":
                    self.labels[name] = address
                    pending.append(name)
                else:
                    self.labels[name] = TEXT_BASE + 4 * len(self.lines)
                line = line[match.end():].strip()
            if not line:
                continue
            parts = line.split(None, 1)
            head = parts[0]
            rest = parts[1].strip() if len(parts) > 1 else ""
            if head.startswith("."):
                if head == ".data":
                    section = "data"
                elif head == ".text":
                    section = "text"
                elif head in {".globl", ".global", ".extern", ".ent", ".end", ".set"}:
                    pass
                elif section != "data":
                    raise MipsError(f"línea {number}: directiva {head} fuera de .data")
                elif head == ".word":
                    aligned = (address + 3) & ~3
                    for name in pending:               # .word se alinea a 4 bytes
                        self.labels[name] = aligned
                    address = aligned
                    for item in self._split_operands(rest):
                        try:
                            self._poke_word(address, int(item, 0))
                        except ValueError:
                            fixups.append((address, item, number))
                        address += 4
                elif head in {".asciiz", ".ascii"}:
                    match = re.match(r'^"(.*)"$', rest, re.S)
                    if not match:
                        raise MipsError(f"línea {number}: cadena mal formada")
                    data = self._unescape(match.group(1)) + (b"\0" if head == ".asciiz" else b"")
                    self._poke_bytes(address, data)
                    address += len(data)
                elif head == ".byte":
                    data = bytes(int(item, 0) & 0xFF for item in self._split_operands(rest))
                    self._poke_bytes(address, data)
                    address += len(data)
                elif head == ".space":
                    address += int(rest, 0)
                elif head == ".align":
                    size = 1 << int(rest, 0)
                    address = (address + size - 1) & ~(size - 1)
                    for name in pending:
                        self.labels[name] = address
                else:
                    raise MipsError(f"línea {number}: directiva no soportada {head}")
                if head not in {".data", ".text", ".globl", ".global", ".align"}:
                    pending = []
                continue
            if section != "text":
                raise MipsError(f"línea {number}: instrucción dentro de .data: {line}")
            self.lines.append((head.lower(), self._split_operands(rest), number))
        if address > HEAP_BASE:
            raise MipsError("el segmento de datos excede el espacio disponible")
        for where, name, number in fixups:
            if name not in self.labels:
                raise MipsError(f"línea {number}: etiqueta no definida {name}")
            self._poke_word(where, s32(self.labels[name]))

        self.entries = {}
        for label, meta in self._functions.items():
            if label in self.labels and meta.kind != "main":
                self.entries[(self.labels[label] - TEXT_BASE) // 4] = meta
        self.return_points: set[int] = set()
        for meta in self._functions.values():
            if meta.kind != "main" and meta.epilogue_label in self.labels:
                k = (self.labels[meta.epilogue_label] - TEXT_BASE) // 4
                while k < len(self.lines) and self.lines[k][0] != "jr":
                    k += 1
                self.return_points.add(k)
        handler_points = {(self.labels[h] - TEXT_BASE) // 4 for h in self._handler_labels if h in self.labels}

        self.code = []
        for index, (op, args, number) in enumerate(self.lines):
            try:
                step = self._compile(index, op, args)
            except MipsError as exc:
                raise MipsError(f"línea {number}: {exc}") from None
            except (KeyError, ValueError, IndexError) as exc:
                raise MipsError(f"línea {number}: instrucción mal formada «{op} {', '.join(args)}» ({exc})") from None
            if index in handler_points:
                step = self._with_unwind(step)
            self.code.append(step)

        def fell_off():
            raise _Exit(0)
        self.code.append(fell_off)

    def _with_unwind(self, step):
        tracer = self.tracer

        def hooked():
            tracer.unwind()
            return step()
        return hooked

    def _poke_word(self, address: int, value: int) -> None:
        WORD_STRUCT.pack_into(self.data, address - DATA_BASE, s32(value))

    def _poke_bytes(self, address: int, data: bytes) -> None:
        off = address - DATA_BASE
        if off + len(data) > len(self.data):
            raise MipsError("el segmento de datos excede el espacio disponible")
        self.data[off:off + len(data)] = data

    @staticmethod
    def _split_operands(text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()] if text else []

    # -- operandos ---------------------------------------------------------
    def _reg(self, text: str) -> int:
        if text not in REGISTERS:
            raise MipsError(f"registro desconocido {text}")
        return REGISTERS[text]

    def _value(self, text: str) -> int:
        """Entero inmediato o dirección de una etiqueta (admite ``etiqueta+n``)."""
        try:
            return int(text, 0)
        except ValueError:
            pass
        match = re.match(r"^([A-Za-z_.$][\w.$]*)\s*([+-]\s*\d+)?$", text)
        if not match or match.group(1) not in self.labels:
            raise MipsError(f"etiqueta no definida {text}")
        return self.labels[match.group(1)] + (int(match.group(2).replace(" ", "")) if match.group(2) else 0)

    def _target(self, text: str) -> int:
        address = self._value(text)
        index = (address - TEXT_BASE) // 4
        if not 0 <= index <= len(self.lines):
            raise MipsError(f"destino de salto fuera del código: {text}")
        return index

    def _memory(self, text: str) -> tuple[int, int]:
        match = re.match(r"^(.*)\(\s*(\$\w+)\s*\)$", text)
        if match:
            offset = self._value(match.group(1).strip()) if match.group(1).strip() else 0
            return offset, self._reg(match.group(2))
        return self._value(text), 0

    # -- compilación a cierres ------------------------------------------------
    def _compile(self, index: int, op: str, a: list[str]):
        R = self.R
        sim = self
        reg, value, target = self._reg, self._value, self._target

        def three(fn):
            rd, rs, rt = reg(a[0]), reg(a[1]), reg(a[2])
            if rd == 0:
                return lambda: None
            def step():
                R[rd] = fn(R[rs], R[rt])
            return step

        def with_imm(fn):
            rd, rs, imm = reg(a[0]), reg(a[1]), value(a[2])
            if rd == 0:
                return lambda: None
            def step():
                R[rd] = fn(R[rs], imm)
            return step

        def branch2(test):
            rs, rt, dest = reg(a[0]), a[1], target(a[2])
            if rt.startswith("$"):
                rt = reg(rt)
                def step():
                    return dest if test(R[rs], R[rt]) else None
            else:
                imm = value(rt)
                def step():
                    return dest if test(R[rs], imm) else None
            return step

        def branch1(test):
            rs, dest = reg(a[0]), target(a[1])
            def step():
                return dest if test(R[rs]) else None
            return step

        if op in {"addu", "add"}:
            if len(a) == 3 and not a[2].startswith("$"):
                return with_imm(lambda x, y: s32(x + y))
            return three(lambda x, y: s32(x + y))
        if op in {"addiu", "addi"}:
            return with_imm(lambda x, y: s32(x + y))
        if op in {"subu", "sub"}:
            return three(lambda x, y: s32(x - y))
        if op == "mul":
            if not a[2].startswith("$"):
                return with_imm(lambda x, y: s32(x * y))
            return three(lambda x, y: s32(x * y))
        if op == "and":
            return three(lambda x, y: x & y)
        if op == "or":
            return three(lambda x, y: x | y)
        if op == "xor":
            return three(lambda x, y: x ^ y)
        if op == "nor":
            return three(lambda x, y: ~(x | y))
        if op == "andi":
            return with_imm(lambda x, y: s32(u32(x) & (y & 0xFFFF)))
        if op == "ori":
            return with_imm(lambda x, y: s32(u32(x) | (y & 0xFFFF)))
        if op == "xori":
            return with_imm(lambda x, y: s32(u32(x) ^ (y & 0xFFFF)))
        if op == "slt":
            return three(lambda x, y: int(x < y))
        if op == "sltu":
            return three(lambda x, y: int(u32(x) < u32(y)))
        if op == "slti":
            return with_imm(lambda x, y: int(x < y))
        if op == "sltiu":
            return with_imm(lambda x, y: int(u32(x) < u32(y)))
        if op == "sll":
            return with_imm(lambda x, y: s32(u32(x) << (y & 31)))
        if op == "srl":
            return with_imm(lambda x, y: s32(u32(x) >> (y & 31)))
        if op == "sra":
            return with_imm(lambda x, y: x >> (y & 31))
        if op == "li":
            rd, imm = reg(a[0]), s32(value(a[1]))
            def step():
                R[rd] = imm
            return step if rd else (lambda: None)
        if op == "la":
            rd = reg(a[0])
            offset, base = self._memory(a[1])
            def step():
                R[rd] = s32(offset + R[base])
            return step if rd else (lambda: None)
        if op == "lui":
            rd, imm = reg(a[0]), s32((value(a[1]) & 0xFFFF) << 16)
            def step():
                R[rd] = imm
            return step
        if op == "move":
            rd, rs = reg(a[0]), reg(a[1])
            def step():
                R[rd] = R[rs]
            return step if rd else (lambda: None)
        if op in {"neg", "negu"}:
            rd, rs = reg(a[0]), reg(a[1])
            def step():
                R[rd] = s32(-R[rs])
            return step
        if op == "not":
            rd, rs = reg(a[0]), reg(a[1])
            def step():
                R[rd] = ~R[rs]
            return step
        if op == "lw":
            rd = reg(a[0])
            offset, base = self._memory(a[1])
            read = self.read_word
            def step():
                R[rd] = read(offset + R[base])
            return step
        if op == "sw":
            rs = reg(a[0])
            offset, base = self._memory(a[1])
            write = self.write_word
            def step():
                write(offset + R[base], R[rs])
            return step
        if op in {"lb", "lbu"}:
            rd = reg(a[0])
            offset, base = self._memory(a[1])
            signed = op == "lb"
            def step():
                byte = sim.read_byte(offset + R[base])
                R[rd] = byte - 256 if signed and byte > 127 else byte
            return step
        if op == "sb":
            rs = reg(a[0])
            offset, base = self._memory(a[1])
            def step():
                sim.write_byte(offset + R[base], R[rs])
            return step
        if op == "div":
            if len(a) == 3:
                rd, rs, rt = reg(a[0]), reg(a[1]), reg(a[2])
                def step():
                    if R[rt] == 0:
                        raise MipsError("división entre cero (instrucción div)")
                    R[rd] = s32(sim._trunc_div(R[rs], R[rt]))
                return step
            rs, rt = reg(a[0]), reg(a[1])
            def step():
                x, y = R[rs], R[rt]
                if y != 0:
                    q = sim._trunc_div(x, y)
                    sim.lo, sim.hi = s32(q), s32(x - q * y)
            return step
        if op == "mflo":
            rd = reg(a[0])
            def step():
                R[rd] = sim.lo
            return step
        if op == "mfhi":
            rd = reg(a[0])
            def step():
                R[rd] = sim.hi
            return step
        if op == "beq":
            return branch2(lambda x, y: x == y)
        if op == "bne":
            return branch2(lambda x, y: x != y)
        if op == "blt":
            return branch2(lambda x, y: x < y)
        if op == "ble":
            return branch2(lambda x, y: x <= y)
        if op == "bgt":
            return branch2(lambda x, y: x > y)
        if op == "bge":
            return branch2(lambda x, y: x >= y)
        if op == "beqz":
            return branch1(lambda x: x == 0)
        if op == "bnez":
            return branch1(lambda x: x != 0)
        if op == "bltz":
            return branch1(lambda x: x < 0)
        if op == "blez":
            return branch1(lambda x: x <= 0)
        if op == "bgtz":
            return branch1(lambda x: x > 0)
        if op == "bgez":
            return branch1(lambda x: x >= 0)
        if op in {"j", "b"}:
            dest = target(a[0])
            return lambda: dest
        if op == "jal":
            dest = target(a[0])
            link = TEXT_BASE + 4 * (index + 1)
            meta = self.entries.get(dest)
            if meta is None:
                def step():
                    R[RA] = link
                    return dest
            else:
                tracer = self.tracer
                def step():
                    R[RA] = link
                    if R[SP] < sim.min_sp:
                        sim.min_sp = R[SP]
                    tracer.enter(meta)
                    return dest
            return step
        if op == "jalr":
            rs = reg(a[-1])
            link = TEXT_BASE + 4 * (index + 1)
            entries, tracer, limit = self.entries, self.tracer, len(self.lines)
            def step():
                dest = (R[rs] - TEXT_BASE) >> 2
                if R[rs] & 3 or not 0 <= dest < limit:
                    raise MipsError(f"salto indirecto a una dirección inválida 0x{u32(R[rs]):08x}")
                R[RA] = link
                meta = entries.get(dest)
                if meta is not None:
                    if R[SP] < sim.min_sp:
                        sim.min_sp = R[SP]
                    tracer.enter(meta)
                return dest
            return step
        if op == "jr":
            rs = reg(a[0])
            limit = len(self.lines)
            traced = index in self.return_points
            tracer = self.tracer
            def step():
                dest = (R[rs] - TEXT_BASE) >> 2
                if R[rs] & 3 or not 0 <= dest <= limit:
                    raise MipsError(f"retorno a una dirección inválida 0x{u32(R[rs]):08x}")
                if traced:
                    tracer.leave()
                return dest
            return step
        if op == "syscall":
            return self._syscall
        if op == "nop":
            return lambda: None
        raise MipsError(f"instrucción no soportada por el simulador integrado: {op}")

    @staticmethod
    def _trunc_div(x: int, y: int) -> int:
        q = abs(x) // abs(y)
        return -q if (x < 0) != (y < 0) else q

    # ================================================================== servicios
    def _write(self, text: str) -> None:
        self.output_chars += len(text)
        if self.output_chars > MAX_OUTPUT_CHARS:
            raise MipsError("la salida del programa excede el límite (¿ciclo infinito con print?)")
        self.output.append(text)

    def _syscall(self):
        R = self.R
        service = R[V0]
        if service == 1:
            self._write(str(R[A0]))
        elif service == 4:
            self._write(self.read_string(R[A0]))
        elif service == 11:
            self._write(chr(R[A0] & 0xFF))
        elif service == 9:
            amount = R[A0]
            if amount < 0:
                raise MipsError("sbrk con cantidad negativa")
            result = self.heap_top
            self.heap_top = (self.heap_top + amount + 3) & ~3
            needed = self.heap_top - DATA_BASE
            if self.heap_top - HEAP_BASE > HEAP_LIMIT:
                raise MipsError("memoria dinámica agotada (límite del heap del simulador)")
            if needed > len(self.data):
                self.data.extend(bytes(max(needed - len(self.data), 1 << 16)))
            R[V0] = s32(result)
        elif service == 10:
            raise _Exit(0)
        elif service == 17:
            raise _Exit(R[A0])
        else:
            raise MipsError(f"servicio del sistema no soportado: {service}")
        return None

    # ================================================================== ejecución
    def request_stop(self) -> None:
        self.stop_requested = True

    def run(self) -> RunResult:
        result = RunResult()
        R = self.R
        R[SP] = INITIAL_SP
        R[RA] = TEXT_BASE + 4 * len(self.lines)
        pc = (self.labels["main"] - TEXT_BASE) // 4 if "main" in self.labels else 0
        code = self.code
        steps = 0
        limit = self.max_steps
        try:
            while True:
                chunk = min(50_000, limit - steps)
                if chunk <= 0:
                    raise MipsError(
                        f"se alcanzó el límite de {limit:,} instrucciones (¿ciclo o recursión infinita?)")
                if self.stop_requested:
                    raise MipsError("ejecución detenida por el usuario")
                for _ in range(chunk):
                    nxt = code[pc]()
                    steps += 1
                    pc = pc + 1 if nxt is None else nxt
        except _Exit as exit_:
            result.finished = True
            result.exit_code = exit_.code
        except MipsError as exc:
            result.error = str(exc)
        except IndexError:
            result.error = "el contador de programa salió del segmento de código"
        except RecursionError:
            result.error = "error interno del simulador (recursión)"
        if result.finished:
            self.tracer.finish()
        result.steps = steps
        result.output = "".join(self.output)
        result.tree = self.tracer.root
        result.calls = self.tracer.calls
        result.max_depth = self.tracer.max_depth
        result.tree_truncated = self.tracer.truncated
        result.calls_by_function = dict(self.tracer.by_function)
        result.max_stack_bytes = INITIAL_SP - min(self.min_sp, R[SP])
        result.heap_bytes = self.heap_top - HEAP_BASE
        return result


def run_mips(source: str, functions=(), handler_labels=(), max_steps: int = 30_000_000) -> RunResult:
    """Ensambla y ejecuta ``source``; nunca lanza: los errores quedan en ``RunResult.error``."""
    try:
        simulator = MipsSimulator(source, functions, handler_labels, max_steps)
    except MipsError as exc:
        return RunResult(error=f"error de ensamblado: {exc}")
    return simulator.run()
