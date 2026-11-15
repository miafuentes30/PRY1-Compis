"""Generación de código MIPS a partir del TAC (Proyecto 3).

Recorre cada unidad de código (``main``, funciones, métodos e inicializadores
de campos) bloque por bloque y traduce cada instrucción TAC, pidiendo
registros a :class:`mips_regalloc.RegisterAllocator` y ubicaciones a
:class:`mips_frames.ProgramLayout`.

Secuencia de llamada (lado del llamador)
    1. guarda en el marco los temporales ``$t`` que siguen vivos;
    2. apila los argumentos 5.º en adelante y coloca los cuatro primeros en
       ``$a0``–``$a3`` (en métodos ``$a0`` es ``this``);
    3. pasa en ``$v1`` el enlace de acceso si el destino es una función anidada;
    4. ``jal`` (o ``jalr`` a través de la tabla de métodos virtuales);
    5. retira los argumentos apilados y toma el resultado de ``$v0``.

Secuencia de retorno (lado del llamado)
    prólogo: reserva el marco, guarda ``$ra``, ``$fp`` y los ``$s`` que usará,
    fija ``$fp`` y recibe los parámetros; epílogo: deja el resultado en ``$v0``,
    restaura ``$s``, ``$ra`` y ``$fp``, libera el marco y ejecuta ``jr $ra``.
"""
from __future__ import annotations

from mips_analysis import (
    BLOCK_ENDERS, Unit, UnitAnalyzer, const_int, is_const, is_string_literal, is_temp,
    is_variable, receiver_of, split_units, uses_defs,
)
from mips_frames import ARG_REGS, WORD, CodegenError, Frame, ProgramLayout
from mips_ir import COMMENT, LABEL, Asm, FunctionMeta, MIPSProgram, ascii_only
from mips_regalloc import RegisterAllocator
from mips_runtime import (
    KIND_BOOL, KIND_DYNAMIC, KIND_INT, KIND_OBJECT, KIND_STRING, RUNTIME_LABELS,
)

COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}
BRANCH_IF_TRUE = {"<": "blt", "<=": "ble", ">": "bgt", ">=": "bge", "==": "beq", "!=": "bne"}
BRANCH_IF_FALSE = {"<": "bge", "<=": "bgt", ">": "ble", ">=": "blt", "==": "bne", "!=": "beq"}
ZERO_BRANCH_IF_TRUE = {"<": "bltz", "<=": "blez", ">": "bgtz", ">=": "bgez"}
ZERO_BRANCH_IF_FALSE = {"<": "bgez", "<=": "bgtz", ">": "blez", ">=": "bltz"}
INT_LIKE = {"integer", "boolean"}
PRIMITIVES = {"integer", "boolean", "string", "null", "unknown", "void", "function"}


def wrap32(value: int) -> int:
    return ((value + 0x80000000) & 0xFFFFFFFF) - 0x80000000


def fits16(value: int) -> bool:
    return -32768 <= value <= 32767


def fold(op: str, a: int, b: int) -> int | None:
    """Plegado de constantes con aritmética entera de 32 bits (como MIPS)."""
    if op == "+":
        return wrap32(a + b)
    if op == "-":
        return wrap32(a - b)
    if op == "*":
        return wrap32(a * b)
    if op in {"/", "%"}:
        if b == 0:
            return None                      # se deja al runtime: lanza la excepción
        quotient = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            quotient = -quotient
        return wrap32(quotient) if op == "/" else wrap32(a - quotient * b)
    return int({"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op])


class MIPSGenerator:
    def __init__(self, program, symbols, classes) -> None:
        self.program = program
        self.symbols = symbols
        self.classes = classes
        self.units: list[Unit] = split_units(program)
        self.layout = ProgramLayout(program, symbols, classes, self.units)
        for unit in self.units:
            UnitAnalyzer(unit, lambda name, label=unit.label: self._tracked(name, label)).run()
        self.layout.plan()
        self.alloc = RegisterAllocator(self)
        self.out: list[Asm] = []
        self.unit: Unit | None = None
        self.frame: Frame | None = None
        self.pending_comment = ""
        self.strings: dict[str, str] = {}
        self.labels: dict[str, str] = {}
        self.used_labels: set[str] = set(RUNTIME_LABELS) | {"main"}
        self.unit_stats: dict[str, dict] = {}
        self.local_labels: set[str] = set()
        for label in self.layout.order:
            self.asm_label(label, self._unit_label_proposal(label))
        self.vtables = {name: self.asm_label(f"vtable:{name}", f"vt_{name}") for name in self.layout.class_layouts}
        self.class_names = {name: self.asm_label(f"classname:{name}", f"cls_{name}") for name in self.layout.class_layouts}

    # ================================================================== nombres
    def _tracked(self, name: str, label: str) -> bool:
        if is_temp(name):
            return True
        return is_variable(name) and self.layout.owner(name, label) == label

    def tracked(self, name: str) -> bool:
        return self._tracked(name, self.unit.label)

    @staticmethod
    def _unit_label_proposal(label: str) -> str:
        if label == "main":
            return "main"
        if "@s" in label:
            base, scope = label.rsplit("@s", 1)
            return f"fn_{base}" if scope == "0" else f"fn_{base}_s{scope}"
        owner, method = label.split(".", 1)
        return f"{owner}_init_campos" if method == "$fields" else f"{owner}_{method}"

    def asm_label(self, key: str, proposal: str | None = None) -> str:
        if key in self.labels:
            return self.labels[key]
        if key == "main":
            self.labels[key] = "main"
            return "main"
        base = proposal or f"L_{key}"
        candidate, n = base, 2
        while candidate in self.used_labels:
            candidate, n = f"{base}_{n}", n + 1
        self.used_labels.add(candidate)
        self.labels[key] = candidate
        return candidate

    def string_label(self, literal: str) -> str:
        content = literal[1:-1]
        if content not in self.strings:
            self.strings[content] = self.asm_label(f"string:{len(self.strings)}", f"str_{len(self.strings)}")
        return self.strings[content]

    # ================================================================== emisión
    def emit(self, op: str, *args, comment: str = "") -> None:
        if self.pending_comment:
            comment = f"{self.pending_comment}  [{comment}]" if comment else self.pending_comment
            self.pending_comment = ""
        self.out.append(Asm(op, tuple(str(a) for a in args), comment))

    def emit_label(self, name: str) -> None:
        self.out.append(Asm(LABEL, (name,)))

    # ================================================================== almacenamiento
    def storage(self, name: str):
        unit = self.unit.label
        owner = self.layout.owner(name, unit)
        frame = self.layout.frames[owner]
        if owner == unit:
            if name in frame.sreg:
                return ("sreg", frame.sreg[name])
            if is_temp(name):
                return ("frame", frame.temp_slot(name))
        if name in frame.globals:
            return ("global", frame.globals[name])
        if name in frame.slots:
            if owner == unit:
                return ("frame", frame.slots[name])
            return ("outer", self.layout.hops(unit, owner), frame.slots[name])
        raise CodegenError(f"no hay almacenamiento asignado para {name} en {unit}")

    def mem_ref(self, name: str) -> str:
        """Operando de memoria de ``name``; sigue los enlaces de acceso si es de otra función."""
        kind = self.storage(name)
        if kind[0] == "frame":
            return f"{kind[1]}($fp)"
        if kind[0] == "global":
            return kind[1]
        if kind[0] == "outer":
            self.emit("lw", "$t8", f"{Frame.LINK_OFFSET}($fp)", comment="enlace de acceso")
            for _ in range(kind[1] - 1):
                self.emit("lw", "$t8", f"{Frame.LINK_OFFSET}($t8)", comment="enlace de acceso")
            return f"{kind[2]}($t8)"
        raise CodegenError(f"{name} vive en un registro y no tiene direccion")

    def store(self, reg: str, name: str, comment: str = "") -> None:
        self.emit("sw", reg, self.mem_ref(name), comment=comment)

    def load(self, reg: str, name: str) -> None:
        self.emit("lw", reg, self.mem_ref(name))

    def load_const(self, reg: str, operand: str) -> None:
        if is_string_literal(operand):
            self.emit("la", reg, self.string_label(operand))
        else:
            value = const_int(operand)
            if value is None:
                raise CodegenError(f"operando no reconocido en el TAC: {operand}")
            self.emit("li", reg, wrap32(value))

    def put_in(self, target: str, operand: str) -> None:
        """Deja el valor de ``operand`` en un registro concreto (argumentos y retornos)."""
        if is_const(operand):
            self.load_const(target, operand)
            return
        reg = self.alloc.find(operand)
        if reg is None:
            self.emit("lw", target, self.mem_ref(operand))
        elif reg != target:
            self.emit("move", target, reg)

    def reg_of(self, operand: str, scratch: str = "$t9") -> str:
        """Registro con el valor del operando; las constantes usan un auxiliar."""
        if is_const(operand):
            if not is_string_literal(operand) and const_int(operand) == 0:
                return "$zero"
            self.load_const(scratch, operand)
            return scratch
        return self.alloc.load(operand)

    def result_reg(self, i: int, dest: str, used) -> str:
        """Libera los operandos que mueren en la instrucción y elige el registro destino."""
        self.alloc.release_dead([u for u in used if is_const(u) is False], self.unit.live_after[i])
        return self.alloc.dest(dest)

    def guard(self, block) -> None:
        """Antes de una operación que puede lanzar una excepción dentro de un try."""
        if block.handlers:
            self.alloc.save_for_handlers(block)

    # ================================================================== programa
    def generate(self) -> MIPSProgram:
        text: list[Asm] = []
        metas: list[FunctionMeta] = []
        handler_labels: list[str] = []
        for unit in self.units:
            body = self._generate_unit(unit)
            frame = self.layout.frames[unit.label]
            text.extend(self._prologue(unit, frame))
            text.extend(body)
            text.extend(self._epilogue(unit, frame))
            metas.append(self._function_meta(unit, frame))
            handler_labels.extend(self.asm_label(h) for h in unit.try_labels)

        result = MIPSProgram()
        result.header = []
        result.data = self._data_section()
        result.text = text
        result.functions = metas
        result.handler_labels = handler_labels
        result.local_labels = set(self.local_labels)
        result.return_labels = {meta.epilogue_label for meta in metas}
        result.frames = self.layout.frames
        result.stats = {
            "asignador": dict(self.alloc.stats),
            "unidades": self.unit_stats,
            "copias_fusionadas": sum(unit.coalesced for unit in self.units),
        }
        return result

    def _function_meta(self, unit: Unit, frame: Frame) -> FunctionMeta:
        info = unit.info
        params: list[tuple[str, str]] = []
        for name in frame.params:
            if name == "this":
                params.append(("this", info.owner_class or "unknown"))
                continue
            base, scope = name.rsplit("@s", 1)
            symbol = self.symbols.scopes[int(scope)].symbols.get(base)
            params.append((base, getattr(symbol, "type_name", "unknown")))
        if info.kind == "main":
            shown = "main"
        elif info.kind == "fields":
            shown = f"{info.owner_class}.<inicializar campos>"
        elif info.kind == "method":
            shown = info.label
        else:
            shown = info.label.rsplit("@s", 1)[0]
        return FunctionMeta(self.asm_label(unit.label), shown, info.kind, params, info.return_type,
                            frame.size, self._epilogue_label(unit))

    def _epilogue_label(self, unit: Unit) -> str:
        return self.asm_label(f"epilogue:{unit.label}", f"{self.asm_label(unit.label)}_fin")

    # ------------------------------------------------------------------ datos
    @staticmethod
    def _string_directive(label: str, content: str) -> str:
        """Directiva de datos para una cadena; lo no ASCII se emite como bytes Latin-1."""
        chars: list[str] = []
        k = 0
        while k < len(content):
            ch = content[k]
            if ch == "\\" and k + 1 < len(content) and content[k + 1] in "nt\\\"":
                chars.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}[content[k + 1]])
                k += 2
            else:
                chars.append(ch)
                k += 1
        if all(32 <= ord(c) < 127 or c in "\n\t" for c in chars):
            escaped = "".join({"\n": "\\n", "\t": "\\t", "\\": "\\\\", '"': '\\"'}.get(c, c) for c in chars)
            return f'{label}: .asciiz "{escaped}"'
        codes = [ord(c) if ord(c) < 256 else ord("?") for c in chars]
        data = [str(code - 256 if code > 127 else code) for code in codes] + ["0"]   # bytes con signo
        return f"{label}: .byte {', '.join(data)}    # \"{ascii_only(content)}\""

    def _data_section(self) -> list[str]:
        lines: list[str] = []
        main_frame = self.layout.frames["main"]
        if main_frame.globals:
            lines.append("# ---- variables globales ----")
            for name, label in sorted(main_frame.globals.items(), key=lambda kv: kv[1]):
                lines.append(f"{label}: .word 0")
        if self.layout.class_layouts:
            lines.append("# ---- tablas de metodos virtuales: nombre de la clase y metodos ----")
            for name, layout in self.layout.class_layouts.items():
                entries = [self.class_names[name]] + [self.asm_label(impl) for _, impl in layout.methods]
                slots = ", ".join(f"{m}" for m, _ in layout.methods) or "sin metodos"
                lines.append(f"{self.vtables[name]}: .word {', '.join(entries)}    # {ascii_only(slots)}")
        if self.layout.class_layouts or self.strings:
            lines.append("# ---- cadenas ----")
            for name in self.layout.class_layouts:
                lines.append(self._string_directive(self.class_names[name], name))
            for content, label in self.strings.items():
                lines.append(self._string_directive(label, content))
        return lines

    # ------------------------------------------------------------------ prólogo / epílogo
    def _prologue(self, unit: Unit, frame: Frame) -> list[Asm]:
        size = frame.size
        info = unit.info
        title = {"main": "programa principal", "function": "funcion", "method": "metodo",
                 "fields": "inicializador de campos"}[info.kind]
        lines = [Asm(COMMENT, (), ""),
                 Asm(COMMENT, (), f"---- {title} {info.label}: registro de activacion de {size} bytes ----"),
                 Asm(LABEL, (self.asm_label(unit.label),))]
        add = lambda op, *args, comment="": lines.append(Asm(op, tuple(str(a) for a in args), comment))
        add("addiu", "$sp", "$sp", -size, comment="prologo: reserva el registro de activacion")
        add("sw", "$ra", f"{size - 4}($sp)", comment="direccion de retorno")
        add("sw", "$fp", f"{size - 8}($sp)", comment="enlace de control ($fp del llamador)")
        add("addiu", "$fp", "$sp", size, comment="$fp = base del registro de activacion")
        if frame.has_link:
            add("sw", "$v1", f"{Frame.LINK_OFFSET}($fp)", comment="enlace de acceso (marco de la funcion contenedora)")
        for reg in frame.saved:
            add("sw", reg, f"{frame.saved_offsets[reg]}($fp)", comment=f"preserva {reg} (callee-saved)")
        for index, name in enumerate(frame.params):
            source = ARG_REGS[index] if index < 4 else None
            if name in frame.sreg:
                if source:
                    add("move", frame.sreg[name], source, comment=f"parametro {name}")
                else:
                    add("lw", frame.sreg[name], f"{WORD * (index - 4)}($fp)", comment=f"parametro {name} (pila)")
            elif name in frame.slots and source:
                add("sw", source, f"{frame.slots[name]}($fp)", comment=f"parametro {name}")
        return lines

    def _epilogue(self, unit: Unit, frame: Frame) -> list[Asm]:
        if unit.info.kind == "main":
            return []
        size = frame.size
        lines = [Asm(LABEL, (self._epilogue_label(unit),))]
        add = lambda op, *args, comment="": lines.append(Asm(op, tuple(str(a) for a in args), comment))
        first = "epilogo: restaura registros preservados"
        for reg in frame.saved:
            add("lw", reg, f"{frame.saved_offsets[reg]}($fp)", comment=first)
            first = ""
        add("lw", "$ra", f"{size - 4}($sp)", comment="epilogo: direccion de retorno")
        add("lw", "$fp", f"{size - 8}($sp)", comment="restaura $fp del llamador")
        add("addiu", "$sp", "$sp", size, comment="libera el registro de activacion")
        add("jr", "$ra", comment="retorno al llamador")
        return lines

    # ------------------------------------------------------------------ unidad
    def _generate_unit(self, unit: Unit) -> list[Asm]:
        self.unit, self.frame = unit, self.layout.frames[unit.label]
        self.out = []
        self.alloc.begin_unit(unit, self.frame)
        before = dict(self.alloc.stats)
        code = unit.code
        for block in unit.blocks:
            self.alloc.clear()
            i = block.start
            while i < block.end:
                ins = code[i]
                uses, _ = uses_defs(ins, unit.call_args.get(i, ()))
                tracked_uses = {u for u in uses if self.tracked(u)}
                self.alloc.set_position(i, unit.live_after[i] | tracked_uses, tracked_uses)
                self.pending_comment = str(ins) if ins.opcode not in {"LABEL", "PARAM"} else ""
                handler = getattr(self, f"op_{ins.opcode}", None)
                if handler is None:
                    raise CodegenError(f"instruccion TAC sin traduccion a MIPS: {ins.opcode}")
                consumed = handler(i, ins, block) or 1
                self.pending_comment = ""
                i += consumed
            if code[block.end - 1].opcode not in BLOCK_ENDERS:
                self.alloc.flush(block)
        after = self.alloc.stats
        self.unit_stats[unit.label] = {k: after[k] - before[k] for k in after if k != "max_temporales"}
        return self.out

    # ================================================================== traducción
    def _no_code(self, i, ins, block):
        return 1

    op_CLASS = op_ENDCLASS = op_FIELD = op_CLOSURE = op_PARAM = _no_code

    def op_LABEL(self, i, ins, block):
        label = self.asm_label(ins.args[0])
        self.local_labels.add(label)
        self.emit_label(label)

    def op_DECLARE(self, i, ins, block):
        name = ins.args[0]
        home = self.alloc.home_register(name)
        if home:
            self.alloc.dest(name)
            self.emit("li", home, 0)
        else:
            self.alloc.forget(name)
            self.emit("sw", "$zero", self.mem_ref(name))

    def op_MOVE(self, i, ins, block):
        dest, source = ins.args
        home = self.alloc.home_register(dest)
        if is_const(source):
            if home:
                self.alloc.dest(dest)
                self.load_const(home, source)
            else:
                reg = self.alloc.dest(dest)
                self.load_const(reg, source)
                self.alloc.define(dest, reg)
            return
        reg = self.alloc.load(source)
        if home:
            self.alloc.dest(dest)
            if reg != home:
                self.emit("move", home, reg)
        else:
            self.alloc.alias(dest, reg)
        self.alloc.release_dead([source], self.unit.live_after[i])

    # ------------------------------------------------------------------ operaciones
    def _fused_branch(self, i, dest, block):
        """``t = a < b; ifFalse t goto L`` con ``t`` muerto: un solo salto condicional."""
        code = self.unit.code
        if i + 1 >= block.end or not is_temp(dest):
            return None
        nxt = code[i + 1]
        if nxt.opcode in {"IF_FALSE", "IF_TRUE"} and nxt.args[0] == dest and dest not in self.unit.live_after[i + 1]:
            return nxt
        return None

    def op_BIN(self, i, ins, block):
        dest, a, op, b = ins.args
        left_type, right_type = (ins.types + ("integer", "integer"))[:2] if ins.types else ("integer", "integer")
        if op in COMPARISONS:
            if "string" in (left_type, right_type) and {left_type, right_type} <= {"string", "unknown"}:
                return self._string_compare(i, ins, block)
            return self._compare(i, ins, block)
        if op == "+":
            if "string" in (left_type, right_type):
                return self._concat(i, ins, left_type, right_type)
            if not {left_type, right_type} <= INT_LIKE:
                return self._dynamic_add(i, ins)
        return self._arithmetic(i, ins, block)

    def _arithmetic(self, i, ins, block):
        dest, a, op, b = ins.args
        ca = const_int(a) if is_const(a) else None
        cb = const_int(b) if is_const(b) else None
        if ca is not None and cb is not None:
            value = fold(op, ca, cb)
            if value is not None:
                reg = self.alloc.dest(dest)
                self.emit("li", reg, value, comment="constante plegada en compilacion")
                self.alloc.define(dest, reg)
                return
        if op in {"/", "%"}:
            ra = self.alloc.load(a) if ca is None else None
            rb = self.alloc.load(b) if cb is None else None
            if ra is None:
                ra = self._const_reg("$t8", ca)
            if rb is None:
                rb = self._const_reg("$t9", cb)
            if cb is None or cb == 0:
                self.guard(block)
                self.emit("beqz", rb, "rt_err_div", comment="division entre cero")
            rd = self.result_reg(i, dest, (a, b))
            self.emit("div", ra, rb)
            self.emit("mflo" if op == "/" else "mfhi", rd)
            self.alloc.define(dest, rd)
            return
        if op == "+" and ca is not None:
            a, b, ca, cb = b, a, cb, ca          # conmutativa: la constante a la derecha
        ra = self.reg_of(a, "$t9")
        if op == "+" and cb is not None and fits16(cb):
            rd = self.result_reg(i, dest, (a,))
            self.emit("addiu", rd, ra, cb)
        elif op == "-" and cb is not None and fits16(-cb):
            rd = self.result_reg(i, dest, (a,))
            self.emit("addiu", rd, ra, -cb)
        else:
            rb = self.reg_of(b, "$t9")
            rd = self.result_reg(i, dest, (a, b))
            self.emit({"+": "addu", "-": "subu", "*": "mul"}[op], rd, ra, rb)
        self.alloc.define(dest, rd)

    def _const_reg(self, scratch: str, value: int) -> str:
        self.emit("li", scratch, wrap32(value))
        return scratch

    def _compare(self, i, ins, block):
        dest, a, op, b = ins.args
        ca = const_int(a) if is_const(a) else None
        cb = const_int(b) if is_const(b) else None
        if ca is not None and cb is not None:
            reg = self.alloc.dest(dest)
            self.emit("li", reg, fold(op, ca, cb), comment="constante plegada en compilacion")
            self.alloc.define(dest, reg)
            return
        branch = self._fused_branch(i, dest, block)
        if branch is not None:
            self.pending_comment = f"{ins}; {branch}"
        ra = self.reg_of(a, "$t9")
        if branch is not None:
            rb = self.reg_of(b, "$t9")
            table = BRANCH_IF_TRUE if branch.opcode == "IF_TRUE" else BRANCH_IF_FALSE
            self.alloc.release_dead([a, b], self.unit.live_after[i + 1])
            self.alloc.flush(block)
            self.emit(table[op], ra, rb, self.asm_label(branch.args[1]))
            return 2
        if op in {"<", ">="} and cb is not None and fits16(cb):
            rd = self.result_reg(i, dest, (a,))
            self.emit("slti", rd, ra, cb)
        else:
            rb = self.reg_of(b, "$t9")
            rd = self.result_reg(i, dest, (a, b))
            if op in {"<", ">="}:
                self.emit("slt", rd, ra, rb)
            elif op in {">", "<="}:
                self.emit("slt", rd, rb, ra)
            elif op == "==":
                self.emit("xor", rd, ra, rb)
                self.emit("sltiu", rd, rd, 1)
            else:
                self.emit("xor", rd, ra, rb)
                self.emit("sltu", rd, "$zero", rd)
        if op in {"<=", ">="}:
            self.emit("xori", rd, rd, 1)
        self.alloc.define(dest, rd)

    def _string_compare(self, i, ins, block):
        dest, a, op, b = ins.args
        branch = self._fused_branch(i, dest, block)
        if branch is not None:
            self.pending_comment = f"{ins}; {branch}"
        self.put_in("$a0", a)
        self.put_in("$a1", b)
        equality = op in {"==", "!="}
        self.emit("jal", "rt_str_eq" if equality else "rt_str_cmp")
        if branch is not None:
            taken_when_true = branch.opcode == "IF_TRUE"
            self.alloc.release_dead([a, b], self.unit.live_after[i + 1])
            self.alloc.flush(block)
            if equality:
                jump_if_nonzero = (op == "==") == taken_when_true
                mnemonic = "bnez" if jump_if_nonzero else "beqz"
            else:
                mnemonic = (ZERO_BRANCH_IF_TRUE if taken_when_true else ZERO_BRANCH_IF_FALSE)[op]
            self.emit(mnemonic, "$v0", self.asm_label(branch.args[1]))
            return 2
        rd = self.result_reg(i, dest, (a, b))
        if op == "==":
            self.emit("move", rd, "$v0")
        elif op == "!=":
            self.emit("xori", rd, "$v0", 1)
        elif op == "<":
            self.emit("slt", rd, "$v0", "$zero")
        elif op == ">":
            self.emit("slt", rd, "$zero", "$v0")
        elif op == "<=":
            self.emit("slti", rd, "$v0", 1)
        else:
            self.emit("slt", rd, "$v0", "$zero")
            self.emit("xori", rd, rd, 1)
        self.alloc.define(dest, rd)

    @staticmethod
    def _to_string_routine(type_name: str) -> str | None:
        if type_name in {"string", "null"}:
            return None
        if type_name == "integer":
            return "rt_int_to_str"
        if type_name == "boolean":
            return "rt_bool_to_str"
        return "rt_to_str"

    def _concat(self, i, ins, left_type, right_type):
        dest, a, _, b = ins.args
        left, right = self._to_string_routine(left_type), self._to_string_routine(right_type)
        if right:
            self.put_in("$a0", b)
            self.emit("jal", right, comment=f"{right_type} -> string")
            self.emit("move", "$a1", "$v0")
        if left:
            self.put_in("$a0", a)
            self.emit("jal", left, comment=f"{left_type} -> string")
            self.emit("move", "$a0", "$v0")
        else:
            self.put_in("$a0", a)
        if not right:
            self.put_in("$a1", b)
        self.emit("jal", "rt_concat")
        rd = self.result_reg(i, dest, (a, b))
        self.emit("move", rd, "$v0")
        self.alloc.define(dest, rd)

    def _dynamic_add(self, i, ins):
        dest, a, _, b = ins.args
        self.put_in("$a0", a)
        self.put_in("$a1", b)
        self.emit("jal", "rt_add_dyn", comment="tipos resueltos en ejecucion")
        rd = self.result_reg(i, dest, (a, b))
        self.emit("move", rd, "$v0")
        self.alloc.define(dest, rd)

    def op_UNARY(self, i, ins, block):
        dest, op, a = ins.args
        if is_const(a):
            value = const_int(a) or 0
            reg = self.alloc.dest(dest)
            self.emit("li", reg, wrap32(-value) if op == "-" else int(value == 0),
                      comment="constante plegada en compilacion")
            self.alloc.define(dest, reg)
            return
        ra = self.alloc.load(a)
        rd = self.result_reg(i, dest, (a,))
        if op == "-":
            self.emit("subu", rd, "$zero", ra)
        else:
            self.emit("sltiu", rd, ra, 1)
        self.alloc.define(dest, rd)

    # ------------------------------------------------------------------ control
    def op_GOTO(self, i, ins, block):
        self.alloc.flush(block)
        self.emit("j", self.asm_label(ins.args[0]))

    def _conditional(self, i, ins, block, jump_when_true: bool):
        condition, target = ins.args
        if is_const(condition):
            truth = bool(const_int(condition))
            self.alloc.flush(block)
            if truth == jump_when_true:
                self.emit("j", self.asm_label(target))
            return
        reg = self.alloc.load(condition)
        self.alloc.release_dead([condition], self.unit.live_after[i])
        self.alloc.flush(block)
        self.emit("bnez" if jump_when_true else "beqz", reg, self.asm_label(target))

    def op_IF_FALSE(self, i, ins, block):
        self._conditional(i, ins, block, False)

    def op_IF_TRUE(self, i, ins, block):
        self._conditional(i, ins, block, True)

    def op_RETURN(self, i, ins, block):
        if self.unit.info.kind == "main":
            self.emit("li", "$v0", 10, comment="fin del programa")
            self.emit("syscall")
            return
        if ins.args:
            self.put_in("$v0", ins.args[0])
        self.emit("j", self._epilogue_label(self.unit))

    # ------------------------------------------------------------------ llamadas
    def _static_link(self, callee: str) -> None:
        if not self.layout.has_link(callee):
            return
        hops = self.layout.hops(self.unit.label, self.layout.parent[callee])
        if hops == 0:
            self.emit("move", "$v1", "$fp", comment="enlace de acceso: mi propio marco")
        else:
            self.emit("lw", "$v1", f"{Frame.LINK_OFFSET}($fp)", comment="enlace de acceso")
            for _ in range(hops - 1):
                self.emit("lw", "$v1", f"{Frame.LINK_OFFSET}($v1)", comment="enlace de acceso")

    def _pass_arguments(self, args) -> int:
        stacked = args[4:]
        if stacked:
            self.emit("addiu", "$sp", "$sp", -WORD * len(stacked), comment="argumentos en la pila")
            for k, arg in enumerate(stacked):
                if is_const(arg):
                    reg = self.reg_of(arg, "$t9")
                else:
                    reg = self.alloc.find(arg)
                    if reg is None:
                        reg = "$t9"
                        self.emit("lw", reg, self.mem_ref(arg))
                self.emit("sw", reg, f"{WORD * k}($sp)")
        for k, arg in enumerate(args[:4]):
            self.put_in(ARG_REGS[k], arg)
        return len(stacked)

    def _finish_call(self, i, dest, stacked: int) -> None:
        if stacked:
            self.emit("addiu", "$sp", "$sp", WORD * stacked, comment="retira los argumentos de la pila")
        self.alloc.invalidate_temporaries()
        if dest != "_" and (not is_temp(dest) or dest in self.unit.live_after[i]):
            rd = self.alloc.dest(dest)
            self.emit("move", rd, "$v0", comment="valor de retorno")
            self.alloc.define(dest, rd)

    def op_CALL(self, i, ins, block):
        dest, callee, _ = ins.args
        if callee not in self.program.functions:
            raise CodegenError(f"llamada a una funcion sin codigo: {callee}")
        args = list(self.unit.call_args.get(i, ()))
        self.alloc.save_before_call(self.unit.live_after[i], dest, handler_live=block.handler_live)
        stacked = self._pass_arguments(args)
        self._static_link(callee)
        self.emit("jal", self.asm_label(callee))
        self._finish_call(i, dest, stacked)

    def op_CALL_METHOD(self, i, ins, block):
        dest = ins.args[0]
        receiver, method = receiver_of(ins)
        offset = self._method_offset(ins.types[0] if ins.types else "unknown", method)
        args = [receiver, *self.unit.call_args.get(i, ())]
        self.alloc.save_before_call(self.unit.live_after[i], dest, handler_live=block.handler_live)
        stacked = self._pass_arguments(args)
        if receiver != "this":
            self.emit("beqz", "$a0", "rt_err_null", comment="receptor nulo")
        self.emit("lw", "$t8", "0($a0)", comment="tabla de metodos del objeto")
        self.emit("lw", "$t9", f"{offset}($t8)", comment=f"despacho dinamico de {method}")
        self.emit("jalr", "$t9")
        self._finish_call(i, dest, stacked)

    def op_INIT_FIELDS(self, i, ins, block):
        obj, class_name = ins.args
        chain = self.layout.class_layouts[class_name].init_chain
        for label in chain:
            self.alloc.save_before_call(self.unit.live_after[i], None, keep=(obj,), handler_live=block.handler_live)
            self.put_in("$a0", obj)
            self.emit("jal", self.asm_label(label), comment=f"inicializa campos de {label.split('.')[0]}")
            self.alloc.invalidate_temporaries()

    # ------------------------------------------------------------------ salida
    def op_PRINT(self, i, ins, block):
        value = ins.args[0]
        type_name = ins.types[0] if ins.types else "unknown"
        self.put_in("$a0", value)
        if type_name == "integer":
            self.emit("jal", "rt_print_int")
        elif type_name == "boolean":
            self.emit("jal", "rt_print_bool")
        elif type_name in {"string", "null"}:
            self.emit("jal", "rt_print_str")
        else:
            base, dims = type_name, 0
            while base.endswith("[]"):
                base, dims = base[:-2], dims + 1
            kind = {"integer": KIND_INT, "boolean": KIND_BOOL, "string": KIND_STRING}.get(
                base, KIND_OBJECT if base in self.layout.class_layouts else KIND_DYNAMIC)
            self.emit("li", "$a1", kind)
            self.emit("li", "$a2", dims)
            self.emit("jal", "rt_print_any")
        self.alloc.release_dead([value], self.unit.live_after[i])

    # ------------------------------------------------------------------ arreglos
    def op_NEW_ARRAY(self, i, ins, block):
        dest, count = ins.args
        self.emit("li", "$a0", count)
        self.emit("jal", "rt_new_array")
        rd = self.alloc.dest(dest)
        self.emit("move", rd, "$v0")
        self.alloc.define(dest, rd)

    def _element(self, block, base_reg: str, index: str, checked: bool = True) -> str:
        """Dirección del elemento ``base[index]`` con verificación de nulo y de límites."""
        constant = const_int(index) if is_const(index) else None
        if constant is not None and 0 <= constant < 8000:
            if checked:
                self.guard(block)
                self.emit("beqz", base_reg, "rt_err_null")
                self.emit("lw", "$t8", f"0({base_reg})", comment="longitud del arreglo")
                self.emit("sltiu", "$t8", "$t8", constant + 1)
                self.emit("bnez", "$t8", "rt_err_index", comment="indice fuera de rango")
            return f"{WORD * (constant + 1)}({base_reg})"
        index_reg = self.reg_of(index, "$t9") if constant is None else self._const_reg("$t9", constant)
        if checked:
            self.guard(block)
            self.emit("beqz", base_reg, "rt_err_null")
            self.emit("lw", "$t8", f"0({base_reg})", comment="longitud del arreglo")
            self.emit("sltu", "$t8", index_reg, "$t8", comment="0 <= indice < longitud")
            self.emit("beqz", "$t8", "rt_err_index", comment="indice fuera de rango")
        self.emit("sll", "$t8", index_reg, 2)
        self.emit("addu", "$t8", "$t8", base_reg)
        return "4($t8)"

    def op_ARRAY_GET(self, i, ins, block):
        dest, base, index = ins.args
        base_reg = self.alloc.load(base)
        if not is_const(index):
            self.alloc.load(index)
        address = self._element(block, base_reg, index)
        rd = self.result_reg(i, dest, (base, index))
        self.emit("lw", rd, address)
        self.alloc.define(dest, rd)

    def op_ARRAY_SET(self, i, ins, block):
        base, index, value = ins.args
        base_reg = self.alloc.load(base)
        if not is_const(index):
            self.alloc.load(index)
        value_reg = self.alloc.load(value) if not is_const(value) else None
        address = self._element(block, base_reg, index, checked=ins.note != "literal")
        if value_reg is None:
            if not is_string_literal(value) and const_int(value) == 0:
                value_reg = "$zero"
            else:
                value_reg = "$t9"
                self.load_const(value_reg, value)
        self.emit("sw", value_reg, address)
        self.alloc.release_dead([base, index, value], self.unit.live_after[i])

    def op_ARRAY_LEN(self, i, ins, block):
        dest, base = ins.args
        base_reg = self.alloc.load(base)
        self.guard(block)
        self.emit("beqz", base_reg, "rt_err_null")
        rd = self.result_reg(i, dest, (base,))
        self.emit("lw", rd, f"0({base_reg})", comment="longitud del arreglo")
        self.alloc.define(dest, rd)

    # ------------------------------------------------------------------ objetos
    def _lookup(self, static_type: str, member: str, table: str, what: str) -> int:
        layouts = self.layout.class_layouts
        layout = layouts.get(static_type)
        if layout is not None and member in getattr(layout, table):
            return getattr(layout, table)[member]
        offsets = {getattr(l, table)[member] for l in layouts.values() if member in getattr(l, table)}
        if len(offsets) == 1:
            return offsets.pop()
        raise CodegenError(
            f"no se puede resolver {what} «{member}» sobre un valor de tipo {static_type}; "
            "declara el tipo de la variable o del parámetro")

    def _field_offset(self, static_type: str, name: str) -> int:
        return self._lookup(static_type, name, "field_offset", "el campo")

    def _method_offset(self, static_type: str, name: str) -> int:
        return self._lookup(static_type, name, "method_offset", "el método")

    def op_NEW(self, i, ins, block):
        dest, class_name = ins.args
        layout = self.layout.class_layouts[class_name]
        self.emit("la", "$a0", self.vtables[class_name])
        self.emit("li", "$a1", layout.size, comment=f"tamano de {class_name}: vtable + {len(layout.fields)} campos")
        self.emit("jal", "rt_new_object")
        rd = self.alloc.dest(dest)
        self.emit("move", rd, "$v0")
        self.alloc.define(dest, rd)

    def op_GET_FIELD(self, i, ins, block):
        dest, obj, name = ins.args
        offset = self._field_offset(ins.types[0] if ins.types else "unknown", name)
        obj_reg = self.alloc.load(obj)
        if obj != "this":
            self.guard(block)
            self.emit("beqz", obj_reg, "rt_err_null", comment="referencia nula")
        rd = self.result_reg(i, dest, (obj,))
        self.emit("lw", rd, f"{offset}({obj_reg})")
        self.alloc.define(dest, rd)

    def op_SET_FIELD(self, i, ins, block):
        obj, name, value = ins.args
        offset = self._field_offset(ins.types[0] if ins.types else "unknown", name)
        obj_reg = self.alloc.load(obj)
        value_reg = self.reg_of(value, "$t9")
        if obj != "this":
            self.guard(block)
            self.emit("beqz", obj_reg, "rt_err_null", comment="referencia nula")
        self.emit("sw", value_reg, f"{offset}({obj_reg})")
        self.alloc.release_dead([obj, value], self.unit.live_after[i])

    # ------------------------------------------------------------------ excepciones
    def op_TRY(self, i, ins, block):
        handler = ins.args[0]
        record = self.frame.try_records[handler]
        self.emit("la", "$t8", self.asm_label(handler), comment="direccion del catch")
        self.emit("sw", "$t8", f"{record + 4}($fp)")
        self.emit("sw", "$sp", f"{record + 8}($fp)", comment="estado de la pila a restaurar")
        self.emit("sw", "$fp", f"{record + 12}($fp)")
        self.emit("lw", "$t8", "rt_eh_top")
        self.emit("sw", "$t8", f"{record}($fp)", comment="manejador anterior")
        self.emit("addiu", "$t8", "$fp", record)
        self.emit("sw", "$t8", "rt_eh_top", comment="este registro es el manejador activo")

    def op_END_TRY(self, i, ins, block):
        self.emit("lw", "$t8", "rt_eh_top")
        self.emit("lw", "$t8", "0($t8)")
        self.emit("sw", "$t8", "rt_eh_top", comment="restaura el manejador anterior")

    def op_CATCH(self, i, ins, block):
        name = ins.args[0]
        rd = self.alloc.dest(name)
        self.emit("move", rd, "$v0", comment="mensaje de la excepcion")
        self.alloc.define(name, rd)


def generate_mips(program, symbols, classes) -> MIPSProgram:
    return MIPSGenerator(program, symbols, classes).generate()
