"""Compila .cps a TAC en modo consola (extra). Nunca ejecuta el programa fuente."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from bootstrap import ensure_generated


def main() -> int:
    cli = argparse.ArgumentParser(description='Compilador Compiscript -> TAC (sin ejecución)')
    cli.add_argument('archivo', type=Path, help='Archivo fuente .cps')
    cli.add_argument('--salida', '-o', type=Path, help='Archivo .tac (se crea solo en éxito)')
    args = cli.parse_args()
    ensure_generated()
    from analyzer import CompiscriptAnalyzer
    try:
        result = CompiscriptAnalyzer().analyze_full_file(args.archivo)
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    if result.errors:
        for error in result.errors:
            print(f'{error.error_type} [{error.code}] L{error.line}:C{error.column} {error.description}', file=sys.stderr)
        if args.salida and args.salida.exists():
            print('AVISO: el archivo de salida anterior permanece intacto; no se generó TAC nuevo.', file=sys.stderr)
        return 1
    content = result.tac.render(numbered=True) + '\n'
    if args.salida:
        args.salida.write_text(content, encoding='utf-8')
        print(f'{len(result.tac.instructions)} instrucciones TAC guardadas en {args.salida}')
    else:
        print(content, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
