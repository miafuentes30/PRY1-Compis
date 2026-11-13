"""Asignación de registros para MIPS: descriptores y ``getReg`` (Proyecto 3).

Dos clases de registros, cada una con su política:

``$s0``–``$s7`` (preservados por el llamado)
    Asignación global por función. ``ProgramLayout`` entrega a las variables y
    parámetros más usados un registro fijo durante toda la función; se guardan
    en el prólogo y se restauran en el epílogo, por eso sobreviven a llamadas.

``$t0``–``$t7`` (no preservados)
    Asignación local por bloque básico con el algoritmo clásico de
    descriptores:

    * *descriptor de registro*: qué nombres contiene cada registro;
    * *descriptor de dirección*: en qué registros está cada nombre y si su
      copia en memoria está actualizada (``dirty``).

    ``getReg`` devuelve un registro libre y, si no hay, elige una víctima:
    primero la que no necesita guardarse (valor muerto o ya en memoria) y,
    entre las que sí, la de siguiente uso más lejano; la víctima se derrama
    (*spill*) a su celda del registro de activación.

Los temporales vivos se guardan en memoria al final de cada bloque, antes de
cada llamada (son *caller-saved*) y antes de una operación que puede lanzar
una excepción hacia un ``catch`` que los necesita. Las variables con hogar en
memoria se escriben de inmediato (*write-through*) y quedan en registro como
caché de lectura.

``$t8`` y ``$t9`` quedan reservados como auxiliares del generador (cálculo de
direcciones, constantes y saltos indirectos); ``$a0``–``$a3`` y ``$v0``–``$v1``
se usan solo para el paso de argumentos y resultados.
"""
from __future__ import annotations

from mips_analysis import INFINITE, is_temp

TEMP_REGS = [f"$t{i}" for i in range(8)]


class RegisterAllocator:
    def __init__(self, host) -> None:
        self.host = host
        self.stats = {
            "getreg": 0,            # registros entregados por getReg
            "reutilizados": 0,      # destino que reutiliza el registro de un operando muerto
            "derrames": 0,          # víctimas guardadas en memoria por falta de registros
            "guardados_llamada": 0,  # temporales salvados antes de una llamada
            "guardados_bloque": 0,  # temporales vivos guardados al final de un bloque
            "cargas": 0,            # lecturas desde memoria hacia registro
            "max_temporales": 0,    # máximo de $t ocupados a la vez
        }
        self.unit = None
        self.frame = None
        self.contents: dict[str, set[str]] = {}
        self.where: dict[str, set[str]] = {}
        self.dirty: set[str] = set()
        self.locked: set[str] = set()
        self.position = 0
        self.live_now: set[str] = set()
        self.current_uses: set[str] = set()
        self.operand_regs: set[str] = set()

    # ------------------------------------------------------------------ estado
    def begin_unit(self, unit, frame) -> None:
        self.unit, self.frame = unit, frame
        self.clear()

    def clear(self) -> None:
        """Estado al inicio de un bloque: solo las variables con registro ``$s`` fijo."""
        self.contents = {reg: set() for reg in TEMP_REGS}
        self.where = {}
        for name, reg in self.frame.sreg.items():
            self.contents[reg] = {name}
            self.where[name] = {reg}
        self.dirty = set()
        self.locked = set()

    def set_position(self, index: int, live_now: set[str], uses: set[str]) -> None:
        self.position = index
        self.live_now = live_now
        self.current_uses = uses
        self.locked = set()
        self.operand_regs = set()

    def unlock(self) -> None:
        self.locked = set()

    def home_register(self, name: str) -> str | None:
        return self.frame.sreg.get(name)

    def find(self, name: str) -> str | None:
        """Registro que contiene el valor actual de ``name`` (o ``None``)."""
        regs = self.where.get(name)
        if not regs:
            return None
        home = self.home_register(name)
        if home in regs:
            return home
        return sorted(regs)[0]

    # ------------------------------------------------------------------ getReg
    def getreg(self) -> str:
        """Entrega un registro ``$t`` disponible, derramando una víctima si es necesario."""
        self.stats["getreg"] += 1
        for reg in TEMP_REGS:
            if not self.contents[reg] and reg not in self.locked:
                return self._take(reg)
        best, best_key = None, None
        for reg in TEMP_REGS:
            if reg in self.locked:
                continue
            cost = sum(1 for name in self.contents[reg] if self._needs_store(name, reg))
            nearest = min((self._next_use(name) for name in self.contents[reg]), default=INFINITE)
            key = (cost, -nearest)
            if best_key is None or key < best_key:
                best, best_key = reg, key
        if best is None:
            raise RuntimeError("getReg: no hay registros temporales disponibles")
        self.spill(best)
        return self._take(best)

    def _take(self, reg: str) -> str:
        self.locked.add(reg)
        in_use = sum(1 for r in TEMP_REGS if self.contents[r] or r in self.locked)
        self.stats["max_temporales"] = max(self.stats["max_temporales"], in_use)
        return reg

    def _is_live(self, name: str) -> bool:
        if not self.host.tracked(name):
            return True
        return name in self.live_now

    def _next_use(self, name: str) -> int:
        if not self.host.tracked(name):
            return INFINITE
        if name in self.current_uses:
            return self.position
        return self.unit.next_use[self.position].get(name, INFINITE)

    def _needs_store(self, name: str, reg: str) -> bool:
        return (name in self.dirty and self._is_live(name)
                and not (self.where.get(name, set()) - {reg}))

    def spill(self, reg: str) -> None:
        """Vacía ``reg``; guarda en memoria los valores vivos que solo estaban ahí."""
        for name in sorted(self.contents[reg]):
            if self._needs_store(name, reg):
                self.host.store(reg, name, "derrame (spill)")
                self.dirty.discard(name)
                self.stats["derrames"] += 1
            if name in self.where:
                self.where[name].discard(reg)
                if not self.where[name]:
                    del self.where[name]
        self.contents[reg] = set()

    # ------------------------------------------------------------------ uso
    def load(self, name: str) -> str:
        """Registro con el valor de ``name``; lo carga desde memoria si hace falta."""
        reg = self.find(name)
        if reg is None:
            reg = self.getreg()
            self.host.load(reg, name)
            self.stats["cargas"] += 1
            self.contents[reg] = {name}
            self.where[name] = {reg}
        self.locked.add(reg)
        self.operand_regs.add(reg)
        return reg

    def dest(self, name: str) -> str:
        """Registro donde debe calcularse el nuevo valor de ``name``."""
        home = self.home_register(name)
        if home is not None:
            self._detach_aliases(home, name)
            return home
        for reg in sorted(self.where.get(name, ())):
            if reg in TEMP_REGS and self.contents[reg] == {name}:
                self.locked.add(reg)
                return reg
        for reg in sorted(self.operand_regs):
            if reg in TEMP_REGS and not self.contents[reg]:
                # El operando murió en esta instrucción: el destino hereda su registro.
                self.stats["reutilizados"] += 1
                return reg
        return self.getreg()

    def define(self, name: str, reg: str) -> None:
        """Registra que ``reg`` contiene ahora el valor recién calculado de ``name``."""
        if self.home_register(name) is not None:
            return
        self._drop(name)
        self.contents[reg] = {name}
        self.where[name] = {reg}
        self._after_write(name, reg)

    def alias(self, name: str, reg: str) -> None:
        """Copia ``name = <valor en reg>`` sin emitir código: comparten el registro."""
        self._drop(name)
        self.contents[reg].add(name)
        self.where[name] = {reg}
        self._after_write(name, reg)

    def _after_write(self, name: str, reg: str) -> None:
        if is_temp(name):
            self.dirty.add(name)
        else:
            self.host.store(reg, name)          # variable con hogar en memoria: write-through

    def _drop(self, name: str) -> None:
        home = self.home_register(name)
        for reg in list(self.where.get(name, ())):
            if reg != home:
                self.contents[reg].discard(name)
        if home is not None:
            self.where[name] = {home}
        else:
            self.where.pop(name, None)
        self.dirty.discard(name)

    def forget(self, name: str) -> None:
        self._drop(name)

    def _detach_aliases(self, home: str, owner: str) -> None:
        """Antes de modificar una variable en ``$s``, reubica los temporales que la copiaban."""
        for alias in sorted(self.contents[home] - {owner}):
            needed = (alias in self.dirty and alias in self.unit.live_after[self.position]
                      and self.where.get(alias) == {home})
            if needed:
                reg = self.getreg()
                self.host.emit("move", reg, home, comment=f"conserva {alias} antes de modificar {owner}")
                self.contents[reg] = {alias}
                self.where[alias] = {reg}
            else:
                self.where.get(alias, set()).discard(home)
                if not self.where.get(alias):
                    self.where.pop(alias, None)
                    self.dirty.discard(alias)
            self.contents[home].discard(alias)

    def release_dead(self, names, live_after: set[str]) -> None:
        """Libera los registros de nombres que ya no se usarán."""
        for name in names:
            if self.host.tracked(name) and name not in live_after:
                self._drop(name)        # su registro sigue bloqueado hasta terminar la instrucción

    # ------------------------------------------------------------------ guardados
    def _save(self, name: str, reason: str, counter: str) -> None:
        reg = self.find(name)
        if reg is None:
            return
        self.host.store(reg, name, reason)
        self.dirty.discard(name)
        self.stats[counter] += 1

    def _survives_call(self, name: str) -> bool:
        """Un temporal que comparte un registro ``$s`` sobrevive a la llamada sin guardarse."""
        return any(reg not in TEMP_REGS for reg in self.where.get(name, ()))

    def save_before_call(self, live_after: set[str], dest: str | None, keep=(), handler_live=()) -> None:
        """Los ``$t`` no sobreviven a una llamada: guarda los temporales aún vivos."""
        for name in sorted(self.dirty):
            if name == dest:
                continue
            if name in handler_live or name in keep:
                self._save(name, "visible desde catch" if name in handler_live else "se necesita tras la llamada",
                           "guardados_llamada")
            elif name in live_after and not self._survives_call(name):
                self._save(name, "caller-saved: vivo tras la llamada", "guardados_llamada")

    def save_for_handlers(self, block) -> None:
        """Antes de una operación que puede fallar: lo que el ``catch`` necesita va a memoria."""
        for name in sorted(self.dirty & block.handler_live):
            self._save(name, "visible desde catch", "guardados_bloque")

    def flush(self, block) -> None:
        """Fin de bloque: los temporales vivos a la salida se guardan en su celda."""
        for name in sorted(self.dirty & block.live_out):
            self._save(name, "vivo al salir del bloque", "guardados_bloque")

    def invalidate_temporaries(self) -> None:
        """Tras una llamada los ``$t`` dejan de ser válidos; los ``$s`` se conservan.

        También se descartan las copias en registro de variables con hogar en
        memoria: la función llamada pudo modificarlas (globales o capturadas).
        """
        for reg, names in self.contents.items():
            home_owner = next((n for n in names if self.home_register(n) == reg), None)
            for name in list(names):
                if name == home_owner or (reg not in TEMP_REGS and is_temp(name)):
                    continue
                names.discard(name)
                regs = self.where.get(name)
                if regs is not None:
                    regs.discard(reg)
                    if not regs:
                        del self.where[name]
                        self.dirty.discard(name)
        self.locked = set()

    def snapshot(self) -> dict[str, list[str]]:
        return {reg: sorted(names) for reg, names in self.contents.items() if names}
