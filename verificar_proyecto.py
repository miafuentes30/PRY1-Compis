from __future__ import annotations

import json
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
    print("BATERÍA DE PRUEBAS - PROYECTO 01 COMPISCRIPT")
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


def main() -> int:
    ensure_generated()
    p1, t1 = verify_semantic_suite()
    p2, t2 = verify_recovery_suite()
    p3, t3 = verify_symbol_table()
    print("=" * 72)
    print(f"TOTAL: {p1 + p2 + p3}/{t1 + t2 + t3} verificaciones superadas.")
    return 0 if p1 == t1 and p2 == t2 and p3 == t3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
