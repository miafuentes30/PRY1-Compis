"""Biblioteca de tiempo de ejecución en MIPS que acompaña a cada programa (Proyecto 3).

Convención: argumentos en ``$a0``–``$a3`` y resultado en ``$v0``. Las rutinas
solo modifican ``$a0``–``$a3``, ``$v0``, ``$v1``, ``$t8`` y ``$t9``; preservan
``$t0``–``$t7`` y ``$s0``–``$s7``, de modo que el código generado no necesita
guardar temporales antes de llamarlas.

Servicios del sistema usados (compatibles con MARS, SPIM y QtSpim):
1 = imprimir entero, 4 = imprimir cadena, 9 = sbrk, 10 = salir,
11 = imprimir carácter, 17 = salir con código.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Códigos de clase de valor para rt_print_any / rt_print_value.
KIND_INT, KIND_BOOL, KIND_STRING, KIND_OBJECT, KIND_DYNAMIC = 0, 1, 2, 3, 4

RUNTIME_LABELS = [
    "rt_print_int", "rt_print_str", "rt_print_bool", "rt_print_any", "rt_print_value",
    "rt_int_to_str", "rt_bool_to_str", "rt_to_str", "rt_concat", "rt_add_dyn",
    "rt_str_eq", "rt_str_cmp", "rt_alloc", "rt_new_array", "rt_new_object",
    "rt_err_index", "rt_err_null", "rt_err_div", "rt_throw", "rt_uncaught",
]

RUNTIME_WORDS = r"""
rt_eh_top:      .word 0          # tope de la pila de manejadores try/catch
"""

RUNTIME_STRINGS = r"""
rt_s_true:      .asciiz "true"
rt_s_false:     .asciiz "false"
rt_s_null:      .asciiz "null"
rt_s_sep:       .asciiz ", "
rt_s_obj:       .asciiz "<objeto "
rt_s_obj_end:   .asciiz ">"
rt_m_index:     .asciiz "indice de arreglo fuera de rango"
rt_m_null:      .asciiz "referencia nula"
rt_m_div:       .asciiz "division entre cero"
rt_m_uncaught:  .asciiz "Error en tiempo de ejecucion no capturado: "
"""

_RUNTIME_SOURCE = r"""
# =====================================================================
# Biblioteca de runtime de Compiscript
# Argumentos en $a0-$a3, resultado en $v0.
# Solo modifica $a0-$a3, $v0, $v1, $t8 y $t9 (preserva $t0-$t7 y $s0-$s7).
# =====================================================================

# ---- print(integer) ----
rt_print_int:
    li      $v0, 1
    syscall
    li      $a0, 10
    li      $v0, 11
    syscall
    jr      $ra

# ---- print(string); null imprime "null" ----
rt_print_str:
    bnez    $a0, rt_print_str_1
    la      $a0, rt_s_null
rt_print_str_1:
    li      $v0, 4
    syscall
    li      $a0, 10
    li      $v0, 11
    syscall
    jr      $ra

# ---- print(boolean) ----
rt_print_bool:
    la      $t8, rt_s_false
    beqz    $a0, rt_print_bool_1
    la      $t8, rt_s_true
rt_print_bool_1:
    move    $a0, $t8
    j       rt_print_str_1

# ---- print de arreglos, objetos y valores de tipo desconocido ----
# $a0 = valor, $a1 = clase de valor (0 int, 1 bool, 2 string, 3 objeto, 4 dinamico),
# $a2 = numero de dimensiones de arreglo
rt_print_any:
    addiu   $sp, $sp, -4
    sw      $ra, 0($sp)
    jal     rt_print_value
    li      $a0, 10
    li      $v0, 11
    syscall
    lw      $ra, 0($sp)
    addiu   $sp, $sp, 4
    jr      $ra

rt_print_value:
    bnez    $a2, rt_pv_array
    li      $t8, 1
    beq     $a1, $t8, rt_pv_bool
    li      $t8, 2
    beq     $a1, $t8, rt_pv_str
    li      $t8, 3
    beq     $a1, $t8, rt_pv_obj
    li      $t8, 4
    beq     $a1, $t8, rt_pv_dyn
rt_pv_int:
    li      $v0, 1
    syscall
    jr      $ra
rt_pv_bool:
    la      $t8, rt_s_false
    beqz    $a0, rt_pv_bool_1
    la      $t8, rt_s_true
rt_pv_bool_1:
    move    $a0, $t8
    li      $v0, 4
    syscall
    jr      $ra
rt_pv_str:
    bnez    $a0, rt_pv_str_1
    la      $a0, rt_s_null
rt_pv_str_1:
    li      $v0, 4
    syscall
    jr      $ra
rt_pv_dyn:
    srl     $t8, $a0, 28             # las cadenas viven en 0x1xxxxxxx (.data / heap)
    li      $t9, 1
    beq     $t8, $t9, rt_pv_str_1
    j       rt_pv_int
rt_pv_obj:
    beqz    $a0, rt_pv_str
    lw      $t9, 0($a0)              # tabla de metodos
    lw      $t9, 0($t9)              # nombre de la clase
    la      $a0, rt_s_obj
    li      $v0, 4
    syscall
    move    $a0, $t9
    li      $v0, 4
    syscall
    la      $a0, rt_s_obj_end
    li      $v0, 4
    syscall
    jr      $ra
rt_pv_array:
    beqz    $a0, rt_pv_str
    addiu   $sp, $sp, -20
    sw      $ra, 16($sp)
    sw      $s0, 12($sp)
    sw      $s1, 8($sp)
    sw      $s2, 4($sp)
    sw      $s3, 0($sp)
    move    $s0, $a0                 # arreglo
    move    $s1, $a1                 # clase de los elementos
    addiu   $s2, $a2, -1             # dimensiones restantes
    li      $s3, 0                   # indice
    li      $a0, 91                  # '['
    li      $v0, 11
    syscall
rt_pv_array_loop:
    lw      $t8, 0($s0)
    slt     $t9, $s3, $t8
    beqz    $t9, rt_pv_array_end
    beqz    $s3, rt_pv_array_item
    la      $a0, rt_s_sep
    li      $v0, 4
    syscall
rt_pv_array_item:
    sll     $t8, $s3, 2
    addu    $t8, $t8, $s0
    lw      $a0, 4($t8)
    move    $a1, $s1
    move    $a2, $s2
    jal     rt_print_value
    addiu   $s3, $s3, 1
    j       rt_pv_array_loop
rt_pv_array_end:
    li      $a0, 93                  # ']'
    li      $v0, 11
    syscall
    lw      $ra, 16($sp)
    lw      $s0, 12($sp)
    lw      $s1, 8($sp)
    lw      $s2, 4($sp)
    lw      $s3, 0($sp)
    addiu   $sp, $sp, 20
    jr      $ra

# ---- entero -> cadena nueva en el heap (preserva $a1-$a3) ----
rt_int_to_str:
    move    $t8, $a0
    li      $a0, 12
    li      $v0, 9
    syscall                          # $v0 = buffer de 12 bytes
    addiu   $v1, $v0, 11
    sb      $zero, 0($v1)
    slt     $a0, $t8, $zero          # $a0 = 1 si es negativo
    bnez    $a0, rt_its_loop
    subu    $t8, $zero, $t8          # se trabaja con el valor negativo (cubre -2^31)
rt_its_loop:
    li      $t9, 10
    div     $t8, $t9
    mfhi    $t9                      # residuo en -9..0
    mflo    $t8
    subu    $t9, $zero, $t9
    addiu   $t9, $t9, 48
    addiu   $v1, $v1, -1
    sb      $t9, 0($v1)
    bnez    $t8, rt_its_loop
    beqz    $a0, rt_its_done
    addiu   $v1, $v1, -1
    li      $t9, 45                  # '-'
    sb      $t9, 0($v1)
rt_its_done:
    move    $v0, $v1
    jr      $ra

# ---- boolean -> "true" / "false" ----
rt_bool_to_str:
    la      $v0, rt_s_false
    beqz    $a0, rt_bts_done
    la      $v0, rt_s_true
rt_bts_done:
    jr      $ra

# ---- valor de tipo desconocido -> cadena ----
rt_to_str:
    srl     $t8, $a0, 28
    li      $t9, 1
    bne     $t8, $t9, rt_int_to_str
    move    $v0, $a0
    jr      $ra

# ---- concatenacion: $v0 = $a0 + $a1 (cadena nueva en el heap) ----
rt_concat:
    bnez    $a0, rt_concat_1
    la      $a0, rt_s_null
rt_concat_1:
    bnez    $a1, rt_concat_2
    la      $a1, rt_s_null
rt_concat_2:
    move    $a2, $a0
    move    $a3, $a1
    li      $t8, 0                   # longitud total
    move    $t9, $a2
rt_concat_len1:
    lbu     $v1, 0($t9)
    beqz    $v1, rt_concat_len1_end
    addiu   $t9, $t9, 1
    addiu   $t8, $t8, 1
    j       rt_concat_len1
rt_concat_len1_end:
    move    $t9, $a3
rt_concat_len2:
    lbu     $v1, 0($t9)
    beqz    $v1, rt_concat_len2_end
    addiu   $t9, $t9, 1
    addiu   $t8, $t8, 1
    j       rt_concat_len2
rt_concat_len2_end:
    addiu   $a0, $t8, 4              # +1 del terminador, redondeado a multiplo de 4
    srl     $a0, $a0, 2
    sll     $a0, $a0, 2
    li      $v0, 9
    syscall                          # $v0 = cadena destino
    move    $t8, $v0
rt_concat_copy1:
    lbu     $v1, 0($a2)
    beqz    $v1, rt_concat_copy2
    sb      $v1, 0($t8)
    addiu   $a2, $a2, 1
    addiu   $t8, $t8, 1
    j       rt_concat_copy1
rt_concat_copy2:
    lbu     $v1, 0($a3)
    sb      $v1, 0($t8)
    beqz    $v1, rt_concat_done
    addiu   $a3, $a3, 1
    addiu   $t8, $t8, 1
    j       rt_concat_copy2
rt_concat_done:
    jr      $ra

# ---- '+' con tipos desconocidos: suma entera o concatenacion ----
rt_add_dyn:
    srl     $t8, $a0, 28
    li      $t9, 1
    beq     $t8, $t9, rt_add_dyn_str
    srl     $t8, $a1, 28
    beq     $t8, $t9, rt_add_dyn_str
    addu    $v0, $a0, $a1
    jr      $ra
rt_add_dyn_str:
    addiu   $sp, $sp, -12
    sw      $ra, 8($sp)
    sw      $a0, 4($sp)
    move    $a0, $a1
    jal     rt_to_str
    sw      $v0, 0($sp)
    lw      $a0, 4($sp)
    jal     rt_to_str
    move    $a0, $v0
    lw      $a1, 0($sp)
    jal     rt_concat
    lw      $ra, 8($sp)
    addiu   $sp, $sp, 12
    jr      $ra

# ---- igualdad de cadenas por contenido: $v0 = 1 si son iguales ----
rt_str_eq:
    beq     $a0, $a1, rt_str_eq_true
    beqz    $a0, rt_str_eq_false
    beqz    $a1, rt_str_eq_false
rt_str_eq_loop:
    lbu     $t8, 0($a0)
    lbu     $t9, 0($a1)
    bne     $t8, $t9, rt_str_eq_false
    beqz    $t8, rt_str_eq_true
    addiu   $a0, $a0, 1
    addiu   $a1, $a1, 1
    j       rt_str_eq_loop
rt_str_eq_true:
    li      $v0, 1
    jr      $ra
rt_str_eq_false:
    li      $v0, 0
    jr      $ra

# ---- comparacion lexicografica: $v0 < 0, = 0 o > 0 ----
rt_str_cmp:
    bnez    $a0, rt_str_cmp_1
    la      $a0, rt_s_null
rt_str_cmp_1:
    bnez    $a1, rt_str_cmp_loop
    la      $a1, rt_s_null
rt_str_cmp_loop:
    lbu     $t8, 0($a0)
    lbu     $t9, 0($a1)
    bne     $t8, $t9, rt_str_cmp_diff
    beqz    $t8, rt_str_cmp_diff
    addiu   $a0, $a0, 1
    addiu   $a1, $a1, 1
    j       rt_str_cmp_loop
rt_str_cmp_diff:
    subu    $v0, $t8, $t9
    jr      $ra

# ---- reserva $a0 bytes (multiplo de 4) inicializados en cero ----
rt_alloc:
    move    $t8, $a0
    li      $v0, 9
    syscall
    move    $t9, $v0
    addu    $t8, $t9, $t8
rt_alloc_zero:
    beq     $t9, $t8, rt_alloc_done
    sw      $zero, 0($t9)
    addiu   $t9, $t9, 4
    j       rt_alloc_zero
rt_alloc_done:
    jr      $ra

# ---- arreglo de $a0 elementos: [longitud][e0][e1]... ----
rt_new_array:
    move    $v1, $a0
    move    $a3, $ra
    addiu   $a0, $a0, 1
    sll     $a0, $a0, 2
    jal     rt_alloc
    sw      $v1, 0($v0)
    jr      $a3

# ---- objeto: $a0 = tabla de metodos, $a1 = bytes; [vtable][campo0]... ----
rt_new_object:
    move    $v1, $a0
    move    $a3, $ra
    move    $a0, $a1
    jal     rt_alloc
    sw      $v1, 0($v0)
    jr      $a3

# ---- errores en tiempo de ejecucion: lanzan una excepcion con su mensaje ----
rt_err_index:
    la      $a0, rt_m_index
    j       rt_throw
rt_err_null:
    la      $a0, rt_m_null
    j       rt_throw
rt_err_div:
    la      $a0, rt_m_div
    j       rt_throw

# ---- lanza la excepcion $a0: restaura $sp/$fp del try mas reciente y salta a su catch ----
rt_throw:
    lw      $t8, rt_eh_top
    beqz    $t8, rt_uncaught
    lw      $t9, 0($t8)              # manejador anterior
    sw      $t9, rt_eh_top
    lw      $sp, 8($t8)
    lw      $fp, 12($t8)
    lw      $t9, 4($t8)              # direccion del catch
    move    $v0, $a0                 # valor de la excepcion
    jr      $t9
rt_uncaught:
    move    $t8, $a0
    la      $a0, rt_m_uncaught
    li      $v0, 4
    syscall
    move    $a0, $t8
    li      $v0, 4
    syscall
    li      $a0, 10
    li      $v0, 11
    syscall
    li      $a0, 1
    li      $v0, 17
    syscall
"""


_LABEL = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*):")
_SYMBOL = re.compile(r"(?<![$A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)")


def _split_runtime_blocks(source: str) -> dict[str, list[str]]:
    """Divide el runtime en bloques encabezados por sus rutinas de primer nivel."""
    blocks = {label: [] for label in RUNTIME_LABELS}
    current: str | None = None
    pending: list[str] = []
    for line in source.strip("\n").split("\n"):
        match = _LABEL.match(line)
        if match and match.group(1) in blocks:
            current = match.group(1)
            blocks[current].extend(pending)
            pending = []
            blocks[current].append(line)
        elif current is None:
            continue
        elif not line.strip() or line.lstrip().startswith("#"):
            pending.append(line)
        else:
            blocks[current].extend(pending)
            pending = []
            blocks[current].append(line)
    return blocks


def _labels_by_block(blocks: dict[str, list[str]]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for block, lines in blocks.items():
        for line in lines:
            match = _LABEL.match(line)
            if match:
                owners[match.group(1)] = block
    return owners


def _references(source: str) -> set[str]:
    """Extrae símbolos usados como operandos de instrucciones MIPS."""
    references: set[str] = set()
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(".") or _LABEL.fullmatch(line):
            continue
        _, separator, operands = line.partition(" ")
        if separator:
            references.update(_SYMBOL.findall(operands))
    return references


def _data_entries(source: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in source.strip("\n").split("\n"):
        match = _LABEL.match(line)
        if match:
            entries[match.group(1)] = line
    return entries


RUNTIME_BLOCKS = _split_runtime_blocks(_RUNTIME_SOURCE)
_RUNTIME_LABEL_OWNERS = _labels_by_block(RUNTIME_BLOCKS)
_RUNTIME_WORD_ENTRIES = _data_entries(RUNTIME_WORDS)
_RUNTIME_STRING_ENTRIES = _data_entries(RUNTIME_STRINGS)


@dataclass(frozen=True)
class RuntimeSelection:
    text: list[str]
    words: list[str]
    strings: list[str]


def select_runtime(program_text: str) -> RuntimeSelection:
    """Selecciona transitivamente las rutinas y datos referenciados por ``program_text``."""
    pending = set(_references(program_text))
    selected: set[str] = set()
    while pending:
        reference = pending.pop()
        block = _RUNTIME_LABEL_OWNERS.get(reference)
        if block is None or block in selected:
            continue
        selected.add(block)
        pending.update(_references("\n".join(RUNTIME_BLOCKS[block])))

    runtime_lines = ["# Biblioteca de runtime"]
    selected_source: list[str] = []
    for block in RUNTIME_LABELS:
        if block not in selected:
            continue
        lines = RUNTIME_BLOCKS[block]
        runtime_lines.append("")
        runtime_lines.extend(lines)
        selected_source.extend(lines)

    data_references = _references(program_text + "\n" + "\n".join(selected_source))
    words = [line for label, line in _RUNTIME_WORD_ENTRIES.items() if label in data_references]
    strings = [line for label, line in _RUNTIME_STRING_ENTRIES.items() if label in data_references]
    return RuntimeSelection(runtime_lines, words, strings)
