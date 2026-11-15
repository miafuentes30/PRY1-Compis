"""Fachada del backend MIPS (Proyecto 3): TAC -> ensamblador optimizado -> ejecución.

    resultado = compile_tac(tac, tabla_de_simbolos, clases)
    resultado.asm                 # texto .asm listo para MARS / SPIM / QtSpim
    resultado.report              # transformaciones de mirilla aplicadas
    ejecucion = resultado.run()   # simulador integrado + árbol de activación
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mips_codegen import MIPSGenerator
from mips_frames import CodegenError
from mips_ir import MIPSProgram
from mips_peephole import PeepholeReport, optimize
from mips_simulator import RunResult, run_mips

__all__ = ["MIPSResult", "CodegenError", "compile_tac"]


@dataclass
class MIPSResult:
    program: MIPSProgram                     # programa final (optimizado si se pidió)
    asm: str                                 # ensamblador final
    asm_unoptimized: str                     # ensamblador antes de la mirilla
    report: PeepholeReport = field(default_factory=PeepholeReport)
    optimized: bool = True

    @property
    def frames(self) -> dict:
        return self.program.frames

    @property
    def stats(self) -> dict:
        return self.program.stats

    def run(self, max_steps: int = 30_000_000, optimized: bool = True) -> RunResult:
        """Ejecuta el programa en el simulador integrado."""
        source = self.asm if optimized else self.asm_unoptimized
        return run_mips(source, self.program.functions, self.program.handler_labels, max_steps)

    # ---- reportes de texto para el IDE y la consola -------------------------
    def frames_text(self) -> str:
        lines: list[str] = []
        for label, frame in self.program.frames.items():
            kind = {"main": "programa principal", "function": "función", "method": "método",
                    "fields": "inicializador de campos"}[frame.kind]
            lines.append(f"{label}  —  {kind}, nivel de anidamiento {frame.depth}, "
                         f"registro de activación de {frame.size} bytes")
            lines.append(f"    {'Ubicación':<14}{'Contenido':<46}Observación")
            for where, what, note in frame.describe():
                lines.append(f"    {where:<14}{what:<46}{note}")
            lines.append("")
        return "\n".join(lines)

    def allocation_text(self) -> str:
        stats = self.program.stats.get("asignador", {})
        names = {
            "getreg": "Registros entregados por getReg()",
            "reutilizados": "Destinos que reutilizan el registro de un operando muerto",
            "derrames": "Derrames (spill) por falta de registros",
            "guardados_llamada": "Temporales guardados antes de una llamada (caller-saved)",
            "guardados_bloque": "Temporales vivos guardados al final de un bloque",
            "cargas": "Cargas desde memoria",
            "max_temporales": "Máximo de registros $t ocupados a la vez",
        }
        lines = ["ASIGNACIÓN DE REGISTROS", ""]
        for key, title in names.items():
            lines.append(f"{stats.get(key, 0):>6}  {title}")
        lines.append(f"{self.program.stats.get('copias_fusionadas', 0):>6}  "
                     "Copias TAC fusionadas antes de asignar (t = op; x = t)")
        lines.append("")
        lines.append("Variables con registro $s fijo por unidad:")
        for label, frame in self.program.frames.items():
            if frame.sreg:
                pairs = ", ".join(f"{reg}={name}" for name, reg in sorted(frame.sreg.items(), key=lambda kv: kv[1]))
            else:
                pairs = "(ninguna)"
            lines.append(f"  {label}: {pairs}")
        return "\n".join(lines)


def compile_tac(tac, symbols, classes, optimize_code: bool = True) -> MIPSResult:
    """Genera MIPS desde el TAC. Lanza :class:`CodegenError` si algo no es traducible."""
    program = MIPSGenerator(tac, symbols, classes).generate()
    unoptimized = program.render()
    report = PeepholeReport()
    report.instructions_before = report.instructions_after = program.instruction_count()
    if optimize_code:
        program.text, report = optimize(program.text, program.local_labels, program.return_labels)
    optimized = program.render()
    return MIPSResult(program, optimized, unoptimized, report, optimize_code)
