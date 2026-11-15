"""Ejecución del ensamblador generado en simuladores MIPS externos (Proyecto 3).

* **MARS 4.5** (incluido en ``herramientas/Mars4_5.jar``, licencia MIT): requiere
  Java 8+. Se ejecuta en modo consola: ``java -jar Mars4_5.jar nc programa.asm``.
* **SPIM / QtSpim**: si ``spim`` está en el PATH se usa ``spim -file programa.asm``.
  En QtSpim basta con *File → Reinitialize and Load File* y *Run*.

Los dos producen la misma salida que el simulador integrado del IDE; la batería
de pruebas lo comprueba cuando encuentra alguno instalado.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

BASE = Path(__file__).resolve().parent
MARS_JAR = BASE / "herramientas" / "Mars4_5.jar"
SPIM_BANNER_END = "exceptions.s\n"


@dataclass
class ExternalRun:
    simulator: str
    output: str
    returncode: int
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def mars_available() -> bool:
    return MARS_JAR.exists() and shutil.which("java") is not None


def spim_available() -> bool:
    return shutil.which("spim") is not None


def available_simulators() -> list[str]:
    found = []
    if mars_available():
        found.append("MARS")
    if spim_available():
        found.append("SPIM")
    return found


def _write_temp(asm: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".asm", delete=False, encoding="latin-1", errors="replace")
    with handle:
        handle.write(asm)
    return Path(handle.name)


def run_mars(asm: str, timeout: int = 120) -> ExternalRun:
    if not mars_available():
        return ExternalRun("MARS", "", -1, "MARS no disponible (se requiere Java y herramientas/Mars4_5.jar)")
    path = _write_temp(asm)
    env = dict(os.environ)
    env.pop("JAVA_TOOL_OPTIONS", None)      # se reemplaza para fijar UTF-8 en la salida de Java
    try:
        # nc = sin aviso de copyright; 1000000 = límite de instrucciones
        proc = subprocess.run(
            ["java", "-Djava.awt.headless=true", "-jar", str(MARS_JAR), "nc", "1000000", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            env={**env, "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8"})
    except subprocess.TimeoutExpired:
        return ExternalRun("MARS", "", -1, "MARS excedió el tiempo límite")
    finally:
        path.unlink(missing_ok=True)
    output = proc.stdout          # MARS añade un salto de línea final (same_output lo ignora)
    error = ""
    if "Error in " in output or "assemble: operation completed with errors" in output.lower():
        error = output.strip()
    return ExternalRun("MARS", output, proc.returncode, error)


def run_spim(asm: str, timeout: int = 60) -> ExternalRun:
    if not spim_available():
        return ExternalRun("SPIM", "", -1, "spim no está instalado")
    path = _write_temp(asm)
    try:
        proc = subprocess.run(["spim", "-file", str(path)], capture_output=True, text=True,
                              encoding="latin-1", timeout=timeout)
    except subprocess.TimeoutExpired:
        return ExternalRun("SPIM", "", -1, "SPIM excedió el tiempo límite")
    finally:
        path.unlink(missing_ok=True)
    output = proc.stdout
    if SPIM_BANNER_END in output:
        output = output.split(SPIM_BANNER_END, 1)[1]
    return ExternalRun("SPIM", output, proc.returncode)


def run_external(name: str, asm: str) -> ExternalRun:
    return run_mars(asm) if name == "MARS" else run_spim(asm)


def same_output(a: str, b: str) -> bool:
    """Compara salidas ignorando solo saltos de línea finales."""
    return a.rstrip("\n") == b.rstrip("\n")


def open_in_mars_gui() -> subprocess.Popen | None:
    """Abre la interfaz gráfica de MARS (File → Open el .asm exportado, F3 ensambla, F5 ejecuta)."""
    if not mars_available():
        return None
    env = dict(os.environ)
    env.pop("JAVA_TOOL_OPTIONS", None)
    return subprocess.Popen(["java", "-jar", str(MARS_JAR)], env=env)
