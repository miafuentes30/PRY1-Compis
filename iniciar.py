from __future__ import annotations

import importlib.metadata
import runpy
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REQUIRED_RUNTIME = "4.9.3"


def ensure_runtime() -> None:
    try:
        installed = importlib.metadata.version("antlr4-python3-runtime")
    except importlib.metadata.PackageNotFoundError:
        installed = None

    if installed == REQUIRED_RUNTIME:
        return

    print(f"Preparando antlr4-python3-runtime {REQUIRED_RUNTIME}...")
    command = [sys.executable, "-m", "pip", "install", "--user", "-r", str(BASE_DIR / "requirements.txt")]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "No se pudo instalar la dependencia de ANTLR. Ejecuta manualmente:\n"
            "python -m pip install -r requirements.txt"
        )


def main() -> None:
    ensure_runtime()
    # Ejecuta main.py en un proceso nuevo para que Python cargue la versión recién instalada.
    completed = subprocess.run([sys.executable, str(BASE_DIR / "main.py")], cwd=BASE_DIR, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
