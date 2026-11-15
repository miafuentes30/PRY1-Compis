"""Compilador Compiscript en modo consola (complemento del IDE).

Ejemplos:
    python compilar_cli.py programa.cps                         # muestra el TAC
    python compilar_cli.py programa.cps --asm programa.asm      # genera MIPS
    python compilar_cli.py programa.cps --ejecutar --arbol      # ejecuta y muestra el árbol de activación
    python compilar_cli.py programa.cps --ejecutar --mars --spim  # compara con simuladores reales
    python compilar_cli.py programa.cps --reporte               # getReg, registros de activación y mirilla
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bootstrap import ensure_generated


def main() -> int:
    cli = argparse.ArgumentParser(description="Compilador Compiscript -> TAC -> MIPS")
    cli.add_argument("archivo", type=Path, help="Archivo fuente .cps")
    cli.add_argument("--salida", "-o", type=Path, help="Archivo .tac (se crea solo si no hay errores)")
    cli.add_argument("--asm", "-a", type=Path, help="Archivo .asm con el código MIPS (MARS / SPIM / QtSpim)")
    cli.add_argument("--ejecutar", "-e", action="store_true", help="Ejecuta el MIPS en el simulador integrado")
    cli.add_argument("--arbol", action="store_true", help="Muestra el árbol de activación de la ejecución")
    cli.add_argument("--reporte", action="store_true", help="Muestra getReg, registros de activación y mirilla")
    cli.add_argument("--sin-optimizar", action="store_true", help="Desactiva la optimización por mirilla")
    cli.add_argument("--mars", action="store_true", help="Ejecuta también en MARS (herramientas/Mars4_5.jar)")
    cli.add_argument("--spim", action="store_true", help="Ejecuta también en SPIM (si está instalado)")
    args = cli.parse_args()
    ensure_generated()
    from analyzer import CompiscriptAnalyzer
    try:
        result = CompiscriptAnalyzer(optimize_mips=not args.sin_optimizar).analyze_full_file(args.archivo)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if result.errors:
        for error in result.errors:
            print(f"{error.error_type} [{error.code}] L{error.line}:C{error.column} {error.description}", file=sys.stderr)
        for path in (args.salida, args.asm):
            if path and path.exists():
                print(f"AVISO: {path} permanece intacto; no se generó código nuevo.", file=sys.stderr)
        return 1

    wants_mips = args.asm or args.ejecutar or args.arbol or args.reporte or args.mars or args.spim
    if args.salida:
        args.salida.write_text(result.tac.render(numbered=True) + "\n", encoding="utf-8")
        print(f"{len(result.tac.instructions)} instrucciones TAC guardadas en {args.salida}")
    elif not wants_mips:
        print(result.tac.render(numbered=True))
        return 0

    mips = result.mips
    if args.asm:
        args.asm.write_text(mips.asm, encoding="latin-1", errors="replace")
        print(f"{mips.program.instruction_count()} instrucciones MIPS guardadas en {args.asm}")
    if args.reporte:
        print(mips.allocation_text())
        print()
        print("REGISTROS DE ACTIVACIÓN")
        print(mips.frames_text())
        print(mips.report.summary())
    exit_code = 0
    if args.ejecutar or args.arbol or args.mars or args.spim:
        run = mips.run()
        print("---- salida del programa (simulador integrado) ----")
        print(run.output, end="" if run.output.endswith("\n") or not run.output else "\n")
        print("---------------------------------------------------")
        if run.error:
            print(f"ERROR del simulador: {run.error}", file=sys.stderr)
            exit_code = 3
        else:
            exit_code = run.exit_code
            print(f"código de salida {run.exit_code} · {run.steps:,} instrucciones · {run.calls} llamadas · "
                  f"profundidad máxima {run.max_depth}")
        if args.arbol:
            print()
            print("ÁRBOL DE ACTIVACIÓN")
            print(run.tree_text())
        from mips_external import run_external, same_output
        for flag, name in ((args.mars, "MARS"), (args.spim, "SPIM")):
            if not flag:
                continue
            external = run_external(name, mips.asm)
            if external.error:
                print(f"{name}: {external.error}")
            elif same_output(external.output, run.output):
                print(f"{name}: salida idéntica a la del simulador integrado (código {external.returncode})")
            else:
                print(f"{name}: SALIDA DISTINTA\n{external.output}")
                exit_code = exit_code or 4
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
