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
    tac_name: str = ""
    storage_class: str = ""
    offset: int | None = None
    size: int = 0
    frame_name: str = ""

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
        self.activation_records: dict[str, dict[str, Any]] = {}

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
                        "tac_name": symbol.tac_name,
                        "storage_class": symbol.storage_class,
                        "offset": symbol.offset,
                        "frame_name": symbol.frame_name,
                    }
                )
        return rows

    def plan_storage(self, classes=None) -> dict[str, dict[str, Any]]:
        """Planifica slots abstractos (8 bytes) por registro de activación.

        Direcciones relativas, no direcciones reales ni ejecución. Los ámbitos
        de bloques comparten el frame de su función contenedora; cada llamada
        tiene una nueva instancia de ese frame (incluida la recursión).
        """
        frames: dict[str, dict[str, Any]] = {'<global>': {'parameters': 0, 'locals': 0, 'bytes': 0}}
        class_offsets = {}
        if classes:
            def layout(cls_name):
                if cls_name in class_offsets: return class_offsets[cls_name]
                info = classes[cls_name]
                parent_count = layout(info.parent) if info.parent in classes else 0
                for idx, symbol in enumerate(info.attributes.values(), parent_count):
                    symbol.offset = idx * 8
                    symbol.size = 8
                    symbol.storage_class = 'field'
                class_offsets[cls_name] = parent_count + len(info.attributes)
                return class_offsets[cls_name]
            for cls_name in classes: layout(cls_name)
        for scope_id in sorted(self.scopes):
            scope = self.scopes[scope_id]
            ancestor = scope
            while ancestor.parent_id is not None and ancestor.kind not in {'function', 'method'}:
                ancestor = self.scopes[ancestor.parent_id]
            if ancestor.kind in {'function', 'method'}:
                enclosing = self.lookup(ancestor.name.split('_', 1)[1], ancestor.parent_id)
                frame = f'{enclosing.tac_name if enclosing else ancestor.name}@s{ancestor.id}'
            else:
                frame = '<global>' 
            frame_data = frames.setdefault(frame, {'parameters': 0, 'locals': 0, 'bytes': 0})
            for symbol in scope.symbols.values():
                symbol.frame_name = frame
                if symbol.kind in {'function', 'method'}:
                    symbol.tac_name = (f'{symbol.owner_class}.{symbol.name}' if symbol.owner_class
                                       else f'{symbol.name}@s{scope.id}')
                    symbol.storage_class, symbol.offset, symbol.size = 'code', None, 0
                elif symbol.kind == 'class':
                    symbol.tac_name = symbol.name
                    symbol.storage_class, symbol.offset, symbol.size = 'type', None, 0
                elif scope.kind == 'class' or symbol.kind == 'attribute':
                    symbol.tac_name = f'{symbol.owner_class or scope.name.removeprefix("class_")}.{symbol.name}'
                    symbol.storage_class, symbol.size = 'field', 8
                    if classes and symbol.owner_class in classes and symbol.name in classes[symbol.owner_class].attributes:
                        symbol.offset = classes[symbol.owner_class].attributes[symbol.name].offset
                elif symbol.kind == 'parameter':
                    frame_data['parameters'] += 1
                    symbol.tac_name = f'{symbol.name}@s{scope.id}'
                    symbol.storage_class, symbol.offset, symbol.size = 'parameter', 16 + 8 * (frame_data['parameters'] - 1), 8
                else:
                    frame_data['locals'] += 1
                    symbol.tac_name = f'{symbol.name}@s{scope.id}'
                    symbol.storage_class = 'global' if frame == '<global>' else 'local'
                    symbol.offset = -8 * frame_data['locals'] if frame != '<global>' else 8 * (frame_data['locals'] - 1)
                    symbol.size = 8
            frame_data['bytes'] = frame_data['locals'] * 8
        self.activation_records = frames
        return frames
