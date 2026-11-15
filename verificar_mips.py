"""Batería de pruebas del Proyecto 3: generación de código MIPS.

Comprueba, para cada programa de ``pruebas_mips/``:

* casos exitosos: compila, genera MIPS, lo ejecuta en el simulador integrado
  (con y sin optimización por mirilla) y compara la salida con la esperada;
* casos fallidos: errores de compilación (no se genera MIPS), errores del
  backend (diagnóstico MIPS_UNSUPPORTED) y errores en tiempo de ejecución
  (mensaje y código de salida 1);
* opcionalmente (``--externo``), la misma salida en MARS 4.5 y SPIM reales.

Además incluye pruebas unitarias de la secuencia de llamada/retorno, de
``getReg``, del árbol de activación, de las tablas de métodos y de cada una de
las transformaciones de mirilla.

Uso:  python verificar_mips.py [--externo] [--solo-manifiesto]
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

from bootstrap import ensure_generated

BASE = Path(__file__).resolve().parent
TEST_DIR = BASE / "pruebas_mips"
MANIFEST = TEST_DIR / "manifest.json"
MAX_STEPS = 5_000_000

_cache: dict[str, object] = {}


def analyze(name: str):
    from analyzer import CompiscriptAnalyzer
    if name not in _cache:
        _cache[name] = CompiscriptAnalyzer().analyze_full_file(TEST_DIR / name)
    return _cache[name]


def output_lines(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if text.endswith("\n") else lines


# ---------------------------------------------------------------------------
# Batería de programas (manifest)
# ---------------------------------------------------------------------------

def check_entry(entry: dict, external: list[str]) -> tuple[bool, list[str]]:
    result = analyze(entry["archivo"])
    notes: list[str] = []
    expected = entry["esperado"]
    if expected == "ERROR_COMPILACION":
        types = {e.error_type for e in result.errors}
        codes = {e.code for e in result.errors}
        ok = (bool(result.errors) and result.tac is None and result.mips is None
              and set(entry.get("codigos_esperados", [])) <= codes
              and set(entry.get("tipos_esperados", [])) <= types)
        notes.append(f"{len(result.errors)} diagnóstico(s); sin TAC ni MIPS" if ok else "se esperaban errores y ningún MIPS")
        return ok, notes
    if expected == "ERROR_GENERACION":
        codes = {e.code for e in result.errors}
        ok = result.mips is None and "MIPS_UNSUPPORTED" in codes and result.tac is not None
        notes.append("diagnóstico MIPS_UNSUPPORTED; no se generó .asm" if ok else "se esperaba MIPS_UNSUPPORTED")
        return ok, notes
    if result.errors or result.mips is None:
        return False, [f"no compiló: {[e.description for e in result.errors][:2]}"]

    ok = True
    wanted = entry["salida"]
    for label, optimized in (("optimizado", True), ("sin optimizar", False)):
        run = result.mips.run(MAX_STEPS, optimized=optimized)
        got = output_lines(run.output)
        if not run.finished or run.exit_code != entry.get("codigo_salida", 0) or got != wanted:
            ok = False
            notes.append(f"{label}: salida distinta (error={run.error!r}, código={run.exit_code})")
            for k, (a, b) in enumerate(zip(got, wanted)):
                if a != b:
                    notes.append(f"    línea {k + 1}: obtenido {a!r}, esperado {b!r}")
                    break
    if "min_derrames" in entry:
        spills = result.mips.stats["asignador"]["derrames"]
        if spills < entry["min_derrames"]:
            ok = False
            notes.append(f"se esperaban derrames de getReg(); hubo {spills}")
        else:
            notes.append(f"getReg derramó {spills} valor(es)")
    if "arbol_esperado" in entry:
        tree = result.mips.run(MAX_STEPS).tree_text().split("\n")
        if tree != entry["arbol_esperado"]:
            ok = False
            notes.append("árbol de activación distinto al esperado")
    if ok:
        report = result.mips.report
        notes.append(f"{len(wanted)} línea(s) de salida; mirilla {report.instructions_before}→{report.instructions_after} instr.")
    from mips_external import run_external, same_output
    for simulator in external:
        run = run_external(simulator, result.mips.asm)
        if not same_output(run.output, "\n".join(wanted) + "\n") or run.error:
            ok = False
            notes.append(f"{simulator}: salida distinta {run.error}")
        else:
            notes.append(f"{simulator}: idéntica")
    return ok, notes


def verify_mips_suite(external: list[str] | None = None) -> tuple[int, int]:
    external = external or []
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("=" * 110)
    print("BATERÍA MIPS - PROYECTO 3" + (f"  (simuladores externos: {', '.join(external)})" if external else ""))
    print("=" * 110)
    print(f"{'Archivo':40} {'Categoría':26} {'Esperado':18} Resultado")
    print("-" * 110)
    passed = 0
    for entry in entries:
        ok, notes = check_entry(entry, external)
        passed += int(ok)
        print(f"{entry['archivo'][:40]:40} {entry['categoria'][:26]:26} {entry['esperado']:18} {'CUMPLE' if ok else 'REVISAR'}")
        if not ok or "--detalle" in sys.argv:
            for note in notes:
                print(f"    · {note}")
    print("-" * 110)
    print(f"Resultado MIPS: {passed}/{len(entries)} programas cumplen.")
    return passed, len(entries)


# ---------------------------------------------------------------------------
# Pruebas unitarias del backend
# ---------------------------------------------------------------------------

class CallingSequenceTests(unittest.TestCase):
    """Secuencias de llamada y retorno, registros de activación."""

    def test_prologo_y_epilogo_balanceados(self):
        asm = analyze("13_recursion.cps").mips.asm
        for name in ("fn_factorial", "fn_fibonacci", "fn_hanoi", "fn_ackermann"):
            body = asm.split(f"\n{name}:\n", 1)[1].split(f"\n{name}_fin:\n", 1)
            reserve = re.search(r"addiu\s+\$sp, \$sp, -(\d+)", body[0]).group(1)
            epilogue = body[1].split("jr ", 1)[0]
            self.assertIn(f"addiu  $sp, $sp, {reserve}", epilogue)
            self.assertIn("lw     $ra", epilogue)
            self.assertIn("lw     $fp", epilogue)
            for reg in re.findall(r"sw\s+(\$s\d), -\d+\(\$fp\)\s+# preserva", body[0]):
                self.assertIn(f"lw     {reg}", epilogue, f"{name} no restaura {reg}")

    def test_parametros_en_pila(self):
        result = analyze("12_funciones_parametros.cps")
        self.assertIn("argumentos en la pila", result.mips.asm)
        prologue = result.mips.asm.split("\nfn_seis:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("lw     $s4, 0($fp)", prologue)      # 5.º argumento: llegó en la pila del llamador
        self.assertIn("lw     $s5, 4($fp)", prologue)      # 6.º argumento
        self.assertIn("move   $s0, $a0", prologue)         # 1.º argumento: llegó en $a0

    def test_recursion_crea_un_registro_por_llamada(self):
        run = analyze("13_recursion.cps").mips.run(MAX_STEPS)
        self.assertTrue(run.ok)
        self.assertGreaterEqual(run.max_depth, 10)        # factorial(10)
        self.assertGreater(run.max_stack_bytes, 10 * 8)
        self.assertEqual(run.calls_by_function["factorial"], 15)

    def test_enlace_de_acceso_en_funciones_anidadas(self):
        result = analyze("14_closures.cps")
        asm = result.mips.asm
        self.assertIn("enlace de acceso", asm)
        frames = result.mips.frames
        self.assertTrue(frames["nivel3@s12"].has_link)
        self.assertTrue(frames["nivel2@s10"].has_link)
        self.assertFalse(frames["nivel1@s0"].has_link)
        captured = [name for name in frames["nivel1@s0"].slots if name.startswith("x@")]
        self.assertTrue(captured)                                     # capturada -> vive en memoria
        self.assertIn("lw     $t8, -12($t8)", asm)                    # nivel3 sigue dos enlaces
        self.assertIn("global@s0", result.mips.frames["main"].globals)

    def test_arbol_de_activacion(self):
        run = analyze("19_arbol_activacion.cps").mips.run(MAX_STEPS)
        self.assertEqual(run.calls_by_function, {"fib": 9, "compuesto": 1, "doble": 2})
        self.assertIn("fib(n=4) → 3", run.tree_text())

    def test_excepcion_cierra_activaciones(self):
        run = analyze("17_try_catch.cps").mips.run(MAX_STEPS)
        self.assertIn("terminada por una excepción", run.tree_text())


class RegisterAllocationTests(unittest.TestCase):
    """Algoritmo de selección de registros (getReg)."""

    def test_getreg_derrama_bajo_presion(self):
        result = analyze("18_presion_registros.cps")
        stats = result.mips.stats["asignador"]
        self.assertGreater(stats["derrames"], 0)
        self.assertEqual(stats["max_temporales"], 8)
        self.assertIn("derrame (spill)", result.mips.asm_unoptimized)

    def test_temporales_se_guardan_antes_de_llamadas(self):
        result = analyze("18_presion_registros.cps")
        self.assertGreater(result.mips.stats["asignador"]["guardados_llamada"], 0)
        self.assertIn("caller-saved", result.mips.asm_unoptimized)

    def test_variables_en_registros_s(self):
        frames = analyze("13_recursion.cps").mips.frames
        self.assertEqual(frames["factorial@s0"].sreg.get("n@s1"), "$s0")
        self.assertIn("$s0", frames["factorial@s0"].saved)

    def test_reutiliza_registro_de_operando_muerto(self):
        self.assertGreater(analyze("18_presion_registros.cps").mips.stats["asignador"]["reutilizados"], 0)

    def test_solo_registros_validos(self):
        allowed = {f"${n}" for n in ["zero", "v0", "v1", "fp", "sp", "ra"]
                   + [f"a{i}" for i in range(4)] + [f"t{i}" for i in range(10)] + [f"s{i}" for i in range(8)]}
        for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
            result = analyze(entry["archivo"])
            if result.mips is None:
                continue
            code = result.mips.asm.split("# Biblioteca de runtime")[0]
            code = "\n".join(line.split("#", 1)[0] for line in code.split("\n"))   # sin comentarios
            used = set(re.findall(r"\$[a-z]+\d?", code))
            self.assertLessEqual(used, allowed, entry["archivo"])


class ObjectModelTests(unittest.TestCase):
    """Clases, herencia y despacho dinámico."""

    def test_vtable_conserva_posicion_de_metodos_sobrescritos(self):
        layouts = analyze("16_herencia.cps").mips.program.frames  # fuerza compilación
        from mips_frames import build_class_layouts
        result = analyze("16_herencia.cps")
        layouts = build_class_layouts(result.classes, result.tac.functions)
        base, child = layouts["Animal"], layouts["Cachorro"]
        self.assertEqual(base.method_offset["hablar"], child.method_offset["hablar"])
        self.assertEqual(dict(child.methods)["hablar"], "Cachorro.hablar")
        self.assertEqual(dict(child.methods)["presentar"], "Animal.presentar")
        self.assertEqual(child.field_offset["nombre"], base.field_offset["nombre"])
        self.assertEqual(child.init_chain, ["Animal.$fields", "Perro.$fields"])

    def test_despacho_dinamico_con_jalr(self):
        asm = analyze("16_herencia.cps").mips.asm
        self.assertIn("jalr", asm)
        self.assertIn("vt_Cachorro: .word cls_Cachorro", asm)


class PeepholeTests(unittest.TestCase):
    """Cada transformación de mirilla, aislada sobre un fragmento de MIPS."""

    @staticmethod
    def optimize(lines, local=(), returns=()):
        from mips_ir import Asm, LABEL
        from mips_peephole import optimize
        code = []
        for text in lines:
            if text.endswith(":"):
                code.append(Asm(LABEL, (text[:-1],)))
            else:
                op, _, rest = text.partition(" ")
                code.append(Asm(op, tuple(a.strip() for a in rest.split(",")) if rest else ()))
        out, report = optimize(code, set(local), set(returns))
        return [line.render().split("#")[0].strip() for line in out if not line.is_comment], report.counts()

    def assertRule(self, rule, before, after, local=(), returns=()):
        result, counts = self.optimize(before, local, returns)
        normalized = [re.sub(r"\s+", " ", line) for line in result]
        self.assertEqual(normalized, after)
        self.assertGreater(counts[rule], 0)

    def test_codigo_inalcanzable(self):
        # tras quitar lo inalcanzable, el salto queda apuntando a la siguiente línea y también se elimina
        self.assertRule("codigo_inalcanzable", ["j fin", "li $t0, 1", "fin:", "jr $ra"], ["fin:", "jr $ra"])
        self.assertRule("codigo_inalcanzable", ["jr $ra", "li $t0, 1", "move $t1, $t0"], ["jr $ra"])

    def test_salto_al_siguiente(self):
        self.assertRule("salto_al_siguiente", ["li $t0, 1", "j L1", "L1:", "jr $ra"], ["li $t0, 1", "L1:", "jr $ra"])

    def test_salto_sobre_salto(self):
        self.assertRule("salto_sobre_salto",
                        ["beq $t0, $t1, L1", "j L2", "L1:", "li $t2, 1", "L2:", "jr $ra"],
                        ["bne $t0, $t1, L2", "L1:", "li $t2, 1", "L2:", "jr $ra"])

    def test_salto_encadenado(self):
        self.assertRule("salto_encadenado",
                        ["beqz $t0, L1", "li $t1, 1", "L1:", "j L2", "li $t3, 3", "L2:", "jr $ra"],
                        ["beqz $t0, L2", "li $t1, 1", "L1:", "L2:", "jr $ra"])

    def test_carga_tras_almacenar(self):
        self.assertRule("carga_tras_almacenar", ["sw $t0, -12($fp)", "lw $t0, -12($fp)", "jr $ra"],
                        ["sw $t0, -12($fp)", "jr $ra"])
        self.assertRule("carga_tras_almacenar", ["sw $t0, -12($fp)", "lw $t1, -12($fp)", "jr $ra"],
                        ["sw $t0, -12($fp)", "move $t1, $t0", "jr $ra"])

    def test_movimiento_redundante(self):
        self.assertRule("movimiento_redundante", ["move $t0, $t0", "move $t1, $t2", "move $t2, $t1", "jr $ra"],
                        ["move $t1, $t2", "jr $ra"])

    def test_identidad_algebraica(self):
        self.assertRule("identidad_algebraica", ["addiu $t0, $t0, 0", "addu $t1, $t2, $zero", "jr $ra"],
                        ["move $t1, $t2", "jr $ra"])
        self.assertRule("identidad_algebraica", ["li $t9, 1", "mul $t1, $t2, $t9", "jr $ra"],
                        ["move $t1, $t2", "jr $ra"])

    def test_reduccion_de_fuerza(self):
        self.assertRule("reduccion_de_fuerza", ["li $t9, 8", "mul $t1, $t2, $t9", "jr $ra"],
                        ["sll $t1, $t2, 3", "jr $ra"])

    def test_propagacion_de_copia(self):
        self.assertRule("propagacion_de_copia", ["move $t0, $s1", "addiu $t0, $t0, 4", "jr $ra"],
                        ["addiu $t0, $s1, 4", "jr $ra"])

    def test_resultado_directo(self):
        self.assertRule("resultado_directo", ["addu $t0, $s0, $s1", "move $v0, $t0", "f_fin:", "jr $ra"],
                        ["addu $v0, $s0, $s1", "f_fin:", "jr $ra"], returns=("f_fin",))

    def test_etiqueta_sin_uso(self):
        self.assertRule("etiqueta_sin_uso", ["li $t0, 1", "L9:", "jr $ra"], ["li $t0, 1", "jr $ra"], local=("L9",))

    def test_al_menos_seis_transformaciones_en_la_bateria(self):
        applied = set()
        for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
            result = analyze(entry["archivo"])
            if result.mips is not None:
                applied |= {rule for rule, n in result.mips.report.counts().items() if n}
        self.assertGreaterEqual(len(applied), 6, applied)

    def test_mirilla_reduce_instrucciones(self):
        report = analyze("00_programa_ejemplo.cps").mips.report
        self.assertLess(report.instructions_after, report.instructions_before)


class SimulatorTests(unittest.TestCase):
    """El simulador integrado reproduce el comportamiento de MARS/SPIM."""

    def test_division_y_modulo_truncados(self):
        from mips_simulator import run_mips
        asm = (".data\n.text\nmain:\n li $t0, -17\n li $t1, 5\n div $t0, $t1\n mflo $a0\n li $v0, 1\n syscall\n"
               " li $a0, 32\n li $v0, 11\n syscall\n mfhi $a0\n li $v0, 1\n syscall\n li $v0, 10\n syscall\n")
        self.assertEqual(run_mips(asm).output, "-3 -2")

    def test_limite_de_instrucciones(self):
        from mips_simulator import run_mips
        run = run_mips(".text\nmain:\n j main\n", max_steps=1000)
        self.assertFalse(run.ok)
        self.assertIn("límite", run.error)

    def test_recursion_infinita_desborda_la_pila(self):
        from analyzer import CompiscriptAnalyzer
        source = "function f(n: integer): integer { return f(n + 1); }\nprint(f(0));\n"
        result = CompiscriptAnalyzer().analyze_full_text(source)
        run = result.mips.run(MAX_STEPS)
        self.assertFalse(run.ok)


def run_unit_tests() -> tuple[int, int]:
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for case in (CallingSequenceTests, RegisterAllocationTests, ObjectModelTests, PeepholeTests, SimulatorTests):
        suite.addTests(loader.loadTestsFromTestCase(case))
    print()
    print("PRUEBAS UNITARIAS DEL BACKEND MIPS")
    result = unittest.TextTestRunner(verbosity=1, stream=sys.stdout).run(suite)
    failed = len(result.failures) + len(result.errors)
    return result.testsRun - failed, result.testsRun


def main() -> int:
    ensure_generated()
    external: list[str] = []
    if "--externo" in sys.argv:
        from mips_external import available_simulators
        external = available_simulators()
        if not external:
            print("AVISO: no se encontró MARS (Java) ni SPIM; se omite la comparación externa.")
    passed, total = verify_mips_suite(external)
    if "--solo-manifiesto" not in sys.argv:
        unit_passed, unit_total = run_unit_tests()
        passed += unit_passed
        total += unit_total
    print("=" * 110)
    print(f"TOTAL MIPS: {passed}/{total} verificaciones superadas.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
