from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "generated"
ANTLR_VERSION = "4.9.3"  # Compatible con Java 8; se usa solo para generar el analizador.
JAR_NAME = f"antlr-{ANTLR_VERSION}-complete.jar"
JAR_PATH = BASE_DIR / JAR_NAME
JAR_URLS = (
    f"https://www.antlr.org/download/{JAR_NAME}",
    f"https://repo1.maven.org/maven2/org/antlr/antlr4/{ANTLR_VERSION}/antlr4-{ANTLR_VERSION}-complete.jar",
)
GRAMMAR_PATH = BASE_DIR / "Compiscript.g4"
STAMP_PATH = GENERATED_DIR / ".grammar.sha256"


def _generated_files_exist() -> bool:
    return all(
        (GENERATED_DIR / filename).is_file()
        for filename in ("CompiscriptLexer.py", "CompiscriptParser.py", "CompiscriptVisitor.py")
    )


def _grammar_hash() -> str:
    return hashlib.sha256(GRAMMAR_PATH.read_bytes()).hexdigest()


def _generated_files_current() -> bool:
    if not _generated_files_exist() or not STAMP_PATH.is_file() or not GRAMMAR_PATH.is_file():
        return False
    try:
        return STAMP_PATH.read_text(encoding="utf-8").strip() == _grammar_hash()
    except OSError:
        return False


def _clear_generated_artifacts() -> None:
    GENERATED_DIR.mkdir(exist_ok=True)
    for path in GENERATED_DIR.iterdir():
        if path.name == "__init__.py":
            continue
        if path.is_file() and (
            path.name.startswith("Compiscript")
            or path.suffix in {".tokens", ".interp"}
            or path.name == STAMP_PATH.name
        ):
            path.unlink(missing_ok=True)


def _java_major(java_command: str) -> int | None:
    try:
        result = subprocess.run(
            [java_command, "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        output = (result.stderr or result.stdout or "").splitlines()[0]
        match = re.search(r'version\s+"([0-9]+)(?:\.([0-9]+))?', output)
        if not match:
            return None
        major = int(match.group(1))
        if major == 1 and match.group(2):
            return int(match.group(2))
        return major
    except Exception:
        return None


def _download_antlr() -> None:
    errors: list[str] = []
    temporary = JAR_PATH.with_suffix(".tmp")
    for url in JAR_URLS:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Compiscript-Lab01/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            if temporary.stat().st_size < 1_000_000:
                raise RuntimeError("La descarga está incompleta.")
            temporary.replace(JAR_PATH)
            return
        except Exception as exc:
            errors.append(str(exc))
            temporary.unlink(missing_ok=True)
    raise RuntimeError(
        "No fue posible descargar el generador ANTLR. Comprueba tu conexión a Internet "
        "y vuelve a ejecutar «python main.py».\n\nDetalle: " + " | ".join(errors)
    )


def ensure_generated() -> None:
    """Genera el lexer y parser solamente cuando todavía no existen."""
    if _generated_files_current():
        return

    java = shutil.which("java")
    if java is None:
        raise RuntimeError(
            "No se encontró Java. Instala Java 8 o una versión posterior, cierra PowerShell "
            "y vuelve a ejecutar «python main.py»."
        )

    major = _java_major(java)
    if major is not None and major < 8:
        raise RuntimeError(
            f"La versión instalada de Java ({major}) es demasiado antigua. Se requiere Java 8 o posterior."
        )

    if not GRAMMAR_PATH.is_file():
        raise RuntimeError(f"No se encontró la gramática «{GRAMMAR_PATH.name}».")

    GENERATED_DIR.mkdir(exist_ok=True)
    (GENERATED_DIR / "__init__.py").touch(exist_ok=True)
    _clear_generated_artifacts()

    if not JAR_PATH.is_file():
        _download_antlr()

    command = [
        java,
        "-jar",
        str(JAR_PATH),
        "-Dlanguage=Python3",
        "-visitor",
        "-no-listener",
        "-o",
        str(GENERATED_DIR),
        GRAMMAR_PATH.name,
    ]
    completed = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not _generated_files_exist():
        details = (completed.stderr or completed.stdout or "Error desconocido").strip()
        raise RuntimeError(
            "ANTLR no pudo generar el analizador. Verifica que Java funcione con «java -version».\n\n"
            f"Detalle técnico:\n{details}"
        )

    STAMP_PATH.write_text(_grammar_hash(), encoding="utf-8")


if __name__ == "__main__":
    try:
        ensure_generated()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
