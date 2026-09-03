from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Symbol:
    name: str
    kind: str
    type_name: str = "unknown"
    scope_id: int = 0
    line: int = 0
    column: int = 0
    mutable: bool = True
    initialized: bool = False
    params: list[tuple[str, str]] = field(default_factory=list)
    return_type: str = "void"
    owner_class: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        if self.kind in {"function", "method"}:
            params = ", ".join(f"{name}: {typ}" for name, typ in self.params)
            return f"({params}) -> {self.return_type}"
        return self.type_name


@dataclass
class Scope:
    id: int
    name: str
    kind: str
    parent_id: int | None
    depth: int
    symbols: dict[str, Symbol] = field(default_factory=dict)


class SymbolTable:
    """Tabla de símbolos con alcances anidados y operaciones CRUD básicas.

    Está diseñada para que las cuatro operaciones evaluadas en la rúbrica se puedan
    demostrar directamente: insertar, recuperar, actualizar y manejar alcances.
    """

    def __init__(self) -> None:
        self.scopes: dict[int, Scope] = {
            0: Scope(id=0, name="global", kind="global", parent_id=None, depth=0)
        }
        self.current_scope_id = 0
        self._next_scope_id = 1

    @property
    def current_scope(self) -> Scope:
        return self.scopes[self.current_scope_id]

    def enter_scope(self, name: str, kind: str = "block") -> int:
        parent = self.current_scope
        scope_id = self._next_scope_id
        self._next_scope_id += 1
        self.scopes[scope_id] = Scope(
            id=scope_id,
            name=name,
            kind=kind,
            parent_id=parent.id,
            depth=parent.depth + 1,
        )
        self.current_scope_id = scope_id
        return scope_id

    def exit_scope(self) -> int:
        current = self.current_scope
        if current.parent_id is None:
            return current.id
        self.current_scope_id = current.parent_id
        return self.current_scope_id

    def insert(self, symbol: Symbol) -> bool:
        """Inserta un símbolo en el alcance actual. Retorna False si ya existe."""
        scope = self.current_scope
        if symbol.name in scope.symbols:
            return False
        symbol.scope_id = scope.id
        scope.symbols[symbol.name] = symbol
        return True

    def get_local(self, name: str, scope_id: int | None = None) -> Symbol | None:
        target = self.scopes[self.current_scope_id if scope_id is None else scope_id]
        return target.symbols.get(name)

    def lookup(self, name: str, start_scope_id: int | None = None) -> Symbol | None:
        """Recupera un símbolo respetando sombreado y la cadena de alcances."""
        scope_id = self.current_scope_id if start_scope_id is None else start_scope_id
        while scope_id is not None:
            scope = self.scopes[scope_id]
            symbol = scope.symbols.get(name)
            if symbol is not None:
                return symbol
            scope_id = scope.parent_id
        return None

    def update(self, name: str, **changes: Any) -> bool:
        """Actualiza el símbolo visible más cercano. Retorna False si no existe."""
        symbol = self.lookup(name)
        if symbol is None:
            return False
        for key, value in changes.items():
            if not hasattr(symbol, key):
                raise AttributeError(f"Symbol no tiene el atributo {key!r}")
            setattr(symbol, key, value)
        return True

    def update_in_scope(self, name: str, scope_id: int, **changes: Any) -> bool:
        symbol = self.get_local(name, scope_id)
        if symbol is None:
            return False
        for key, value in changes.items():
            if not hasattr(symbol, key):
                raise AttributeError(f"Symbol no tiene el atributo {key!r}")
            setattr(symbol, key, value)
        return True

    def visible_symbols(self, start_scope_id: int | None = None) -> dict[str, Symbol]:
        """Devuelve la vista de símbolos visibles desde un alcance concreto."""
        result: dict[str, Symbol] = {}
        scope_id = self.current_scope_id if start_scope_id is None else start_scope_id
        while scope_id is not None:
            scope = self.scopes[scope_id]
            for name, symbol in scope.symbols.items():
                result.setdefault(name, symbol)
            scope_id = scope.parent_id
        return result

    def rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for scope_id in sorted(self.scopes):
            scope = self.scopes[scope_id]
            for symbol in scope.symbols.values():
                rows.append(
                    {
                        "scope_id": scope.id,
                        "scope": scope.name,
                        "scope_kind": scope.kind,
                        "depth": scope.depth,
                        "name": symbol.name,
                        "kind": symbol.kind,
                        "type": symbol.type_name,
                        "signature": symbol.signature,
                        "mutable": symbol.mutable,
                        "initialized": symbol.initialized,
                        "line": symbol.line,
                        "column": symbol.column,
                        "owner_class": symbol.owner_class or "",
                    }
                )
        return rows
