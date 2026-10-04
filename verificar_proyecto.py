from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from bootstrap import ensure_generated

BASE = Path(__file__).resolve().parent
TEST_DIR = BASE / "pruebas_semanticas"
MANIFEST = TEST_DIR / "manifest.json"
RECOVERY_DIR = BASE / "pruebas_recuperacion"
RECOVERY_MANIFEST = RECOVERY_DIR / "manifest.json"


def verify_semantic_suite() -> tuple[int, int]:
    from analyzer import CompiscriptAnalyzer

    analyzer = CompiscriptAnalyzer()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    passed = 0
    print("=" * 126)
    print("BATERÍA DE PRUEBAS - COMPISCRIPT PROYECTOS 1 Y 2")
    print("=" * 126)
    print(f"{'Archivo':42} {'Esperado':>16} {'Léx':>4} {'Sint':>5} {'Sem':>4}  Resultado")
    print("-" * 126)

    for entry in entries:
        path = TEST_DIR / entry["archivo"]
        result = analyzer.analyze_full_file(path)
        lex = len(result.lexical_errors)
        syn = len(result.syntactic_errors)
        sem = len(result.semantic_errors)
        codes = {e.code for e in result.semantic_errors}
        expected = entry["esperado"]
        objective = entry.get("codigo_objetivo", "")
        expected_codes = set(entry.get("codigos_esperados", []))

        if expected == "VÁLIDO":
            ok = not result.errors
        elif expected == "ERROR SINTÁCTICO":
            ok = syn >= 1
        elif expected == "3 ERRORES":
            ok = expected_codes.issubset(codes) and sem >= 3
        else:
            ok = sem >= 1 and (objective in codes if objective else True)

        passed += int(ok)
        print(f"{entry['archivo'][:42]:42} {expected:>16} {lex:>4} {syn:>5} {sem:>4}  {'CUMPLE' if ok else 'REVISAR'}")
        if not ok:
            for err in result.errors:
                print(f"    - {err.error_type:<10} {err.code:<28} L{err.line}:C{err.column} {err.description}")

    print("-" * 126)
    print(f"Resultado semántico: {passed}/{len(entries)} pruebas cumplen.")
    return passed, len(entries)


def verify_recovery_suite() -> tuple[int, int]:
    """Valida que lexer y parser acumulen varios errores sin abortar el análisis."""
    from analyzer import CompiscriptAnalyzer

    analyzer = CompiscriptAnalyzer()
    entries = json.loads(RECOVERY_MANIFEST.read_text(encoding="utf-8"))
    passed = 0

    print("\nRECUPERACIÓN LÉXICA Y SINTÁCTICA")
    print("-" * 106)
    print(f"{'Archivo':38} {'Léx':>5} {'Sint':>5} {'Mín. léx':>9} {'Mín. sint':>10}  Resultado")
    print("-" * 106)

    for entry in entries:
        path = RECOVERY_DIR / entry["archivo"]
        result = analyzer.analyze_full_file(path)
        lex = len(result.lexical_errors)
        syn = len(result.syntactic_errors)
        min_lex = int(entry.get("lexicos_minimos", 0))
        min_syn = int(entry.get("sintacticos_minimos", 0))

        ok = lex >= min_lex and syn >= min_syn
        passed += int(ok)
        print(
            f"{entry['archivo'][:38]:38} {lex:>5} {syn:>5} "
            f"{min_lex:>9} {min_syn:>10}  {'CUMPLE' if ok else 'REVISAR'}"
        )
        if not ok:
            for err in result.errors:
                print(
                    f"    - {err.error_type:<10} L{err.line}:C{err.column} "
                    f"{err.description}"
                )

    print("-" * 106)
    print(f"Resultado recuperación: {passed}/{len(entries)} pruebas cumplen.")
    return passed, len(entries)


def verify_symbol_table() -> tuple[int, int]:
    from symbol_table import Symbol, SymbolTable

    checks: list[tuple[str, bool]] = []
    table = SymbolTable()
    checks.append(("insertar", table.insert(Symbol("x", "variable", "integer", initialized=True))))
    checks.append(("recuperar", table.lookup("x") is not None and table.lookup("x").type_name == "integer"))
    checks.append(("actualizar", table.update("x", type_name="float") and table.lookup("x").type_name == "float"))

    table.enter_scope("bloque_demo", "block")
    inherited = table.lookup("x") is not None and table.lookup("x").type_name == "float"
    local_insert = table.insert(Symbol("x", "variable", "string", initialized=True))
    shadow = table.lookup("x") is not None and table.lookup("x").type_name == "string"
    table.exit_scope()
    restore = table.lookup("x") is not None and table.lookup("x").type_name == "float"
    checks.append(("manejo de alcances", inherited and local_insert and shadow and restore))

    print("\nTABLA DE SÍMBOLOS")
    print("-" * 72)
    for name, ok in checks:
        print(f"{name:28} {'CUMPLE' if ok else 'REVISAR'}")
    return sum(ok for _, ok in checks), len(checks)


def verify_tac_suite() -> tuple[int, int]:
    """Batería independiente del Proyecto 2, incluye entradas que NO deben generar TAC."""
    from analyzer import CompiscriptAnalyzer
    entries = json.loads((BASE / "pruebas_tac" / "manifest.json").read_text(encoding="utf-8"))
    analyzer = CompiscriptAnalyzer()
    passed = 0
    print("\nPROYECTO 2: CÓDIGO INTERMEDIO TAC")
    print("-" * 100)
    for entry in entries:
        result = analyzer.analyze_full_file(BASE / "pruebas_tac" / entry["archivo"])
        if entry["valido"]:
            missing = [part for part in entry["contiene"] if part not in result.tac_text]
            ok = not result.errors and result.tac is not None and not missing
        else:
            missing = []
            ok = bool(result.errors) and result.tac is None and not result.tac_text
        if not ok:
            print(f"  DIAGNÓSTICOS: {[(e.code, e.description) for e in result.errors]}")
            print(f"  FRAGMENTOS AUSENTES: {missing}")
        passed += int(ok)
        print(f"{entry['archivo']:42} {'VÁLIDO' if entry['valido'] else 'ERROR':>8}  {'CUMPLE' if ok else 'REVISAR'}")
    print(f"Resultado TAC: {passed}/{len(entries)} pruebas cumplen.")
    return passed, len(entries)


def verify_tac_invariants() -> tuple[int, int]:
    from analyzer import CompiscriptAnalyzer
    analyzer = CompiscriptAnalyzer()
    checks = []
    result = analyzer.analyze_full_file(BASE / 'pruebas_tac' / '12_foreach.cps')
    program = result.tac
    if program is not None:
        labels = [i.args[0] for i in program.instructions if i.opcode == 'LABEL']
        targets = [i.args[-1] for i in program.instructions if i.opcode in {'GOTO', 'IF_FALSE', 'IF_TRUE'}]
        checks.append(('etiquetas y saltos', len(labels) == len(set(labels)) and set(targets) <= set(labels)))
    else:
        checks.append(('etiquetas y saltos', False))
    recycled = analyzer.analyze_full_file(BASE / 'pruebas_tac' / '21_operacion_reciclaje.cps')
    checks.append(('reciclaje de temporales', recycled.tac is not None and recycled.tac.reused_temporaries >= 1))
    code = "function f(x:integer):integer { let y:integer=x+1; return y; } let z:integer=f(2);"
    analyzed = analyzer.analyze_full_text(code)
    if analyzed.symbol_table and analyzed.tac:
        rows = analyzed.symbol_table.rows()
        param = next((x for x in rows if x['name']=='x'), {})
        local = next((x for x in rows if x['name']=='y'), {})
        glob = next((x for x in rows if x['name']=='z'), {})
        checks.append(('parámetros, locales y globales',
                       param.get('storage_class')=='parameter' and param.get('offset', 0)>=16
                       and local.get('storage_class')=='local' and local.get('offset', 0)<0
                       and glob.get('storage_class')=='global'
                       and local.get('frame_name')==param.get('frame_name')))
    else:
        checks.append(('parámetros, locales y globales', False))
    analyzed = analyzer.analyze_full_text('class P {let a:integer;} class H:P {let b:integer;} let h:H=new H();')
    if analyzed.symbol_table and analyzed.tac:
        rows = analyzed.symbol_table.rows()
        parent = next((x for x in rows if x['name']=='a' and x['scope']=='class_P'), {})
        child = next((x for x in rows if x['name']=='b' and x['scope']=='class_H'), {})
        checks.append(('offsets de herencia', parent.get('offset')==0 and child.get('offset')==8))
    else:
        checks.append(('offsets de herencia', False))
    print('\nINVARIANTES DE TAC Y REGISTROS DE ACTIVACIÓN')
    for name, ok in checks:
        print(f"{name:36} {'CUMPLE' if ok else 'REVISAR'}")
    return sum(ok for _, ok in checks), len(checks)


def verify_regressions() -> tuple[int, int]:
    """Regresiones independientes (incluye los tres defectos de la revisión)."""
    from verificar_regresiones import TACRegression
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TACRegression)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"REGRESIONES: {passed}/{result.testsRun} verificaciones superadas.")
    return passed, result.testsRun


def main() -> int:
    ensure_generated()
    p1, t1 = verify_semantic_suite()
    p2, t2 = verify_recovery_suite()
    p3, t3 = verify_symbol_table()
    p4, t4 = verify_tac_suite()
    p5, t5 = verify_tac_invariants()
    p6, t6 = verify_regressions()
    print("=" * 72)
    print(f"TOTAL: {p1 + p2 + p3 + p4 + p5 + p6}/{t1 + t2 + t3 + t4 + t5 + t6} verificaciones superadas.")
    return 0 if all(p == t for p, t in [(p1,t1),(p2,t2),(p3,t3),(p4,t4),(p5,t5),(p6,t6)]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
