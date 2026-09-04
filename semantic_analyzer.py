from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from antlr4 import ParserRuleContext
from antlr4.tree.Tree import TerminalNodeImpl

from error_listener import AnalysisError
from generated.CompiscriptParser import CompiscriptParser
from generated.CompiscriptVisitor import CompiscriptVisitor
from symbol_table import Symbol, SymbolTable


UNKNOWN = "unknown"
VOID = "void"
NULL = "null"
FUNCTION = "function"
NUMERIC_TYPES = {"integer", "float"}
PRIMITIVE_TYPES = {"integer", "float", "string", "boolean"}


@dataclass
class ExprInfo:
    type_name: str = UNKNOWN
    symbol: Symbol | None = None
    callable_symbol: Symbol | None = None
    assignable: bool = False


@dataclass
class ClassInfo:
    name: str
    parent: str | None = None
    attributes: dict[str, Symbol] = field(default_factory=dict)
    methods: dict[str, Symbol] = field(default_factory=dict)


@dataclass
class SemanticResult:
    errors: list[AnalysisError]
    symbol_table: SymbolTable
    classes: dict[str, ClassInfo]


class SemanticAnalyzer(CompiscriptVisitor):
    """Visitor semántico para Compiscript.

    El análisis es deliberadamente tolerante a errores: cada regla reporta su
    diagnóstico y devuelve un tipo `unknown` cuando no puede inferir más. Esto
    evita cascadas y permite continuar el recorrido completo del árbol.
    """

    MAX_ERRORS = 200

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source
        self.source_lines = source.splitlines()
        self.errors: list[AnalysisError] = []
        self._seen_errors: set[tuple[str, int, int, str]] = set()
        self.symbols = SymbolTable()
        self.classes: dict[str, ClassInfo] = {}
        self.declaration_symbols: dict[int, Symbol] = {}
        self.class_declarations: dict[int, ClassInfo] = {}
        self.function_stack: list[Symbol] = []
        self.class_stack: list[str] = []
        self.loop_depth = 0
        self._block_counter = 0

    # ------------------------------------------------------------------
    # Public API / helpers
    # ------------------------------------------------------------------

    def analyze(self, tree: CompiscriptParser.ProgramContext) -> SemanticResult:
        try:
            self.visit(tree)
        except Exception as exc:  # Última barrera: nunca abortar por un error semántico interno.
            self._error(
                tree,
                "SEM_INTERNAL",
                "análisis semántico",
                f"El analizador semántico encontró una situación inesperada: {type(exc).__name__}.",
                "Revisa la construcción cercana; el resto de diagnósticos anteriores siguen siendo válidos.",
            )
        return SemanticResult(self.errors[: self.MAX_ERRORS], self.symbols, self.classes)

    def _error(
        self,
        ctx_or_token,
        code: str,
        symbol: str,
        description: str,
        suggestion: str,
    ) -> None:
        if len(self.errors) >= self.MAX_ERRORS:
            return
        token = getattr(ctx_or_token, "start", None) or getattr(ctx_or_token, "symbol", None) or ctx_or_token
        line = max(1, int(getattr(token, "line", 1) or 1))
        internal_col = max(0, int(getattr(token, "column", 0) or 0))
        column = internal_col + 1
        key = (code, line, column, symbol)
        if key in self._seen_errors:
            return
        self._seen_errors.add(key)
        excerpt = self._excerpt(line, internal_col)
        visible_symbol = symbol if symbol.startswith("«") else f"«{symbol}»"
        self.errors.append(
            AnalysisError(
                error_type="Semántico",
                line=line,
                column=column,
                symbol=visible_symbol,
                description=description,
                suggestion=suggestion,
                source_excerpt=excerpt,
                code=code,
            )
        )

    def _excerpt(self, line: int, col: int) -> str:
        if not (1 <= line <= len(self.source_lines)):
            return ""
        text = self.source_lines[line - 1]
        caret = min(max(col, 0), len(text))
        return f"{text}\n{' ' * caret}^"

    @staticmethod
    def _type_text(ctx: CompiscriptParser.TypeSpecContext | None) -> str:
        if ctx is None:
            return UNKNOWN
        return ctx.getText()

    @staticmethod
    def _annotation_type(ctx) -> str:
        if ctx is None:
            return UNKNOWN
        return ctx.typeSpec().getText()

    @staticmethod
    def _is_array(type_name: str) -> bool:
        return type_name.endswith("[]")

    @staticmethod
    def _array_element(type_name: str) -> str:
        return type_name[:-2] if type_name.endswith("[]") else UNKNOWN

    @staticmethod
    def _is_numeric(type_name: str) -> bool:
        return type_name in NUMERIC_TYPES

    def _type_exists(self, type_name: str) -> bool:
        base = type_name
        while base.endswith("[]"):
            base = base[:-2]
        return base in PRIMITIVE_TYPES or base in self.classes or base in {UNKNOWN, NULL, VOID}

    def _compatible(self, expected: str, actual: str) -> bool:
        if expected == UNKNOWN or actual == UNKNOWN:
            return True
        if expected == actual:
            return True

        # Los literales de arreglo vacíos se infieren como unknown[]. Si existe
        # un tipo esperado (por ejemplo integer[]), el contexto aporta el tipo
        # de los elementos y el arreglo vacío es compatible. La comparación se
        # realiza recursivamente para soportar también arreglos multidimensionales.
        if self._is_array(expected) and self._is_array(actual):
            return self._compatible(self._array_element(expected), self._array_element(actual))

        if expected == "float" and actual == "integer":
            return True
        if actual == NULL:
            # null es aceptable para referencias y arreglos, no para primitivos numéricos/booleanos.
            return expected not in {"integer", "float", "boolean"}
        return False

    def _common_type(self, left: str, right: str) -> str:
        if left == right:
            return left
        if left == UNKNOWN:
            return right
        if right == UNKNOWN:
            return left

        # Un arreglo vacío puede combinarse con otro arreglo tipado. Esto evita
        # falsos positivos en expresiones como [[], [1, 2]].
        if self._is_array(left) and self._is_array(right):
            common_element = self._common_type(self._array_element(left), self._array_element(right))
            return f"{common_element}[]" if common_element != UNKNOWN else UNKNOWN

        if {left, right} <= NUMERIC_TYPES:
            return "float"
        if left == NULL and right not in {"integer", "float", "boolean"}:
            return right
        if right == NULL and left not in {"integer", "float", "boolean"}:
            return left
        return UNKNOWN

    def _validate_declared_type(self, ctx, type_name: str) -> None:
        if type_name != UNKNOWN and not self._type_exists(type_name):
            self._error(
                ctx,
                "SEM_UNKNOWN_TYPE",
                type_name,
                f"El tipo {type_name} no está declarado en Compiscript ni corresponde a una clase conocida.",
                "Usa integer, float, string, boolean, un arreglo válido o una clase declarada.",
            )

    def _check_assignment(self, ctx, target: ExprInfo | Symbol, actual_type: str) -> None:
        symbol = target if isinstance(target, Symbol) else target.symbol
        expected = symbol.type_name if symbol is not None else (target.type_name if isinstance(target, ExprInfo) else UNKNOWN)
        if symbol is not None and not symbol.mutable:
            self._error(
                ctx,
                "SEM_CONST_ASSIGN",
                symbol.name,
                f"No se puede asignar un nuevo valor a la constante {symbol.name}.",
                "Declara el identificador con let/var si necesita cambiar o evita reasignar la constante.",
            )
        if not self._compatible(expected, actual_type):
            name = symbol.name if symbol is not None else "destino"
            self._error(
                ctx,
                "SEM_ASSIGN_TYPE",
                name,
                f"La asignación a {name} espera {expected}, pero la expresión produce {actual_type}.",
                f"Asigna una expresión de tipo {expected} o corrige el tipo declarado.",
            )
        if symbol is not None:
            symbol.initialized = True
            if symbol.type_name == UNKNOWN and actual_type != UNKNOWN:
                symbol.type_name = actual_type

    def _safe_visit(self, node) -> ExprInfo | None:
        if node is None:
            return None
        try:
            return self.visit(node)
        except Exception as exc:
            self._error(
                node,
                "SEM_RECOVERY",
                node.getText()[:30] or "expresión",
                f"No fue posible completar esta comprobación semántica ({type(exc).__name__}).",
                "Corrige primero los errores sintácticos cercanos; el análisis continuará con las demás instrucciones.",
            )
            return ExprInfo(UNKNOWN)

    # ------------------------------------------------------------------
    # Retorno definitivo de funciones
    # ------------------------------------------------------------------

    def _statement_sequence_guarantees_return(
        self, statements: Iterable[CompiscriptParser.StatementContext]
    ) -> bool:
        """Indica si una secuencia garantiza ejecutar un ``return``.

        El análisis es deliberadamente conservador: solo se marca como retorno
        definitivo cuando todos los caminos de control conocidos terminan en
        ``return``. Esto evita aceptar funciones tipadas que podrían finalizar
        sin devolver un valor.
        """
        for stmt in statements:
            if self._statement_guarantees_return(stmt):
                return True
        return False

    def _block_guarantees_return(self, block: CompiscriptParser.BlockContext | None) -> bool:
        if block is None:
            return False
        return self._statement_sequence_guarantees_return(block.statement())

    def _statement_guarantees_return(self, stmt: CompiscriptParser.StatementContext | None) -> bool:
        if stmt is None:
            return False

        if stmt.returnStatement() is not None:
            return True

        nested_block = stmt.block()
        if nested_block is not None:
            return self._block_guarantees_return(nested_block)

        if_stmt = stmt.ifStatement()
        if if_stmt is not None:
            blocks = if_stmt.block()
            if not isinstance(blocks, list):
                blocks = [blocks] if blocks is not None else []
            # Un if sin else no garantiza retorno porque la condición puede ser falsa.
            return len(blocks) == 2 and all(self._block_guarantees_return(block) for block in blocks)

        try_stmt = stmt.tryCatchStatement()
        if try_stmt is not None:
            blocks = try_stmt.block()
            if not isinstance(blocks, list):
                blocks = [blocks] if blocks is not None else []
            # Tanto try como catch deben devolver para garantizar retorno.
            return len(blocks) == 2 and all(self._block_guarantees_return(block) for block in blocks)

        do_while = stmt.doWhileStatement()
        if do_while is not None:
            # do-while ejecuta el cuerpo al menos una vez.
            return self._block_guarantees_return(do_while.block())

        # while/for/foreach pueden no ejecutar su cuerpo. Las declaraciones de
        # funciones anidadas tampoco cuentan como retorno de la función exterior.
        return False

    # ------------------------------------------------------------------
    # Transferencia de control definitiva / código muerto
    # ------------------------------------------------------------------

    def _statement_sequence_guarantees_termination(
        self, statements: Iterable[CompiscriptParser.StatementContext]
    ) -> bool:
        """Indica si una secuencia deja de ejecutar las instrucciones siguientes.

        A diferencia de ``_statement_sequence_guarantees_return``, aquí también
        se consideran ``break`` y ``continue`` cuando son válidos en el contexto
        actual. Se usa únicamente para detectar código muerto.
        """
        for stmt in statements:
            if self._statement_guarantees_termination(stmt):
                return True
        return False

    def _block_guarantees_termination(self, block: CompiscriptParser.BlockContext | None) -> bool:
        if block is None:
            return False
        return self._statement_sequence_guarantees_termination(block.statement())

    def _statement_guarantees_termination(self, stmt: CompiscriptParser.StatementContext | None) -> bool:
        if stmt is None:
            return False

        # Solo cuentan como transferencia definitiva si son semánticamente
        # válidos en el contexto actual; así evitamos errores derivados.
        if stmt.returnStatement() is not None:
            return bool(self.function_stack)
        if stmt.breakStatement() is not None or stmt.continueStatement() is not None:
            return self.loop_depth > 0

        nested_block = stmt.block()
        if nested_block is not None:
            return self._block_guarantees_termination(nested_block)

        if_stmt = stmt.ifStatement()
        if if_stmt is not None:
            blocks = if_stmt.block()
            if not isinstance(blocks, list):
                blocks = [blocks] if blocks is not None else []
            # Solo un if con else puede garantizar que no continúa la ejecución.
            return len(blocks) == 2 and all(self._block_guarantees_termination(block) for block in blocks)

        try_stmt = stmt.tryCatchStatement()
        if try_stmt is not None:
            blocks = try_stmt.block()
            if not isinstance(blocks, list):
                blocks = [blocks] if blocks is not None else []
            return len(blocks) == 2 and all(self._block_guarantees_termination(block) for block in blocks)

        do_while = stmt.doWhileStatement()
        if do_while is not None:
            # Un return dentro de do-while sí impide continuar después del loop.
            # Un break/continue solo afecta al loop y no vuelve muerto el código
            # que aparece después del do-while.
            return self._block_guarantees_return(do_while.block())

        # while/for/foreach pueden no ejecutarse y una función anidada no altera
        # el flujo de la función exterior.
        return False

    # ------------------------------------------------------------------
    # Predeclaraciones: permiten recursión y referencias hacia adelante.
    # ------------------------------------------------------------------

    def _signature_from_function(self, ctx, *, kind: str = "function", owner: str | None = None) -> Symbol:
        name = ctx.Identifier().getText()
        params: list[tuple[str, str]] = []
        if ctx.parameters() is not None:
            for parameter in ctx.parameters().parameter():
                p_name = parameter.Identifier().getText()
                p_type = parameter.typeSpec().getText() if parameter.typeSpec() is not None else UNKNOWN
                params.append((p_name, p_type))
        return_type = ctx.typeSpec().getText() if ctx.typeSpec() is not None else VOID
        token = ctx.Identifier().getSymbol()
        return Symbol(
            name=name,
            kind=kind,
            type_name=FUNCTION,
            line=token.line,
            column=token.column + 1,
            mutable=False,
            initialized=True,
            params=params,
            return_type=return_type,
            owner_class=owner,
        )

    def _predeclare_statements(self, statements: Iterable[CompiscriptParser.StatementContext]) -> None:
        for stmt in statements:
            func = stmt.functionDeclaration()
            cls = stmt.classDeclaration()
            if func is not None:
                symbol = self._signature_from_function(func)
                if not self.symbols.insert(symbol):
                    self._error(
                        func,
                        "SEM_DUPLICATE",
                        symbol.name,
                        f"El identificador {symbol.name} ya fue declarado en este mismo ámbito.",
                        "Usa un nombre diferente o elimina una de las declaraciones duplicadas.",
                    )
                else:
                    self.declaration_symbols[id(func)] = symbol
            elif cls is not None:
                self._predeclare_class(cls)

    def _predeclare_class(self, ctx: CompiscriptParser.ClassDeclarationContext) -> None:
        identifiers = ctx.Identifier()
        name = identifiers[0].getText() if isinstance(identifiers, list) else identifiers.getText()
        parent = identifiers[1].getText() if isinstance(identifiers, list) and len(identifiers) > 1 else None
        token = identifiers[0].getSymbol() if isinstance(identifiers, list) else identifiers.getSymbol()
        symbol = Symbol(
            name=name,
            kind="class",
            type_name=name,
            line=token.line,
            column=token.column + 1,
            mutable=False,
            initialized=True,
        )
        if not self.symbols.insert(symbol):
            self._error(
                ctx,
                "SEM_DUPLICATE",
                name,
                f"El identificador {name} ya fue declarado en este mismo ámbito.",
                "Usa otro nombre para la clase o elimina la declaración duplicada.",
            )
            # Se crea una clase efímera para poder seguir analizando su cuerpo.
            info = ClassInfo(name=name, parent=parent)
        else:
            info = ClassInfo(name=name, parent=parent)
            self.classes[name] = info
            self.declaration_symbols[id(ctx)] = symbol
        self.class_declarations[id(ctx)] = info

        # Registra firmas de miembros antes de analizar cuerpos para permitir recursión
        # entre métodos y validar accesos desde objetos creados posteriormente.
        for member in ctx.classMember():
            func = member.functionDeclaration()
            var = member.variableDeclaration()
            const = member.constantDeclaration()
            if func is not None:
                method = self._signature_from_function(func, kind="method", owner=name)
                if method.name in info.methods or method.name in info.attributes:
                    self._error(
                        func,
                        "SEM_DUPLICATE_MEMBER",
                        method.name,
                        f"La clase {name} contiene más de un miembro llamado {method.name}.",
                        "Usa nombres únicos para atributos y métodos dentro de una misma clase.",
                    )
                else:
                    info.methods[method.name] = method
                    self.declaration_symbols[id(func)] = method
            elif var is not None or const is not None:
                decl = var if var is not None else const
                attr_name = decl.Identifier().getText()
                attr_type = self._annotation_type(decl.typeAnnotation()) if decl.typeAnnotation() is not None else UNKNOWN
                tok = decl.Identifier().getSymbol()
                attr = Symbol(
                    name=attr_name,
                    kind="attribute",
                    type_name=attr_type,
                    line=tok.line,
                    column=tok.column + 1,
                    mutable=var is not None,
                    initialized=(var is not None and var.initializer() is not None) or (const is not None and const.expression() is not None),
                    owner_class=name,
                )
                if attr_name in info.attributes or attr_name in info.methods:
                    self._error(
                        decl,
                        "SEM_DUPLICATE_MEMBER",
                        attr_name,
                        f"La clase {name} contiene más de un miembro llamado {attr_name}.",
                        "Usa nombres únicos para atributos y métodos dentro de una misma clase.",
                    )
                else:
                    info.attributes[attr_name] = attr

    # ------------------------------------------------------------------
    # Programa, bloques y declaraciones
    # ------------------------------------------------------------------

    def visitProgram(self, ctx: CompiscriptParser.ProgramContext):
        self._predeclare_statements(ctx.statement())
        for stmt in ctx.statement():
            self._safe_visit(stmt)
        return None

    def _visit_statement_sequence(self, statements: Iterable[CompiscriptParser.StatementContext]) -> None:
        terminated = False
        for stmt in statements:
            if terminated:
                self._error(
                    stmt,
                    "SEM_DEAD_CODE",
                    stmt.getText()[:30],
                    "Esta instrucción es código muerto porque aparece después de una transferencia de control definitiva.",
                    "Mueve o elimina la instrucción que aparece después de return, break, continue o de una estructura cuyas ramas terminan definitivamente.",
                )
            self._safe_visit(stmt)
            if self._statement_guarantees_termination(stmt):
                terminated = True

    def visitBlock(self, ctx: CompiscriptParser.BlockContext):
        self._block_counter += 1
        self.symbols.enter_scope(f"bloque_{self._block_counter}", "block")
        try:
            self._predeclare_statements(ctx.statement())
            self._visit_statement_sequence(ctx.statement())
        finally:
            self.symbols.exit_scope()
        return None

    def visitVariableDeclaration(self, ctx: CompiscriptParser.VariableDeclarationContext):
        name = ctx.Identifier().getText()
        declared = self._annotation_type(ctx.typeAnnotation()) if ctx.typeAnnotation() is not None else UNKNOWN
        self._validate_declared_type(ctx, declared)
        actual = UNKNOWN
        initialized = False
        if ctx.initializer() is not None:
            info = self._safe_visit(ctx.initializer().expression()) or ExprInfo(UNKNOWN)
            actual = info.type_name
            initialized = True
        final_type = declared if declared != UNKNOWN else actual
        tok = ctx.Identifier().getSymbol()
        symbol = Symbol(
            name=name,
            kind="variable",
            type_name=final_type,
            line=tok.line,
            column=tok.column + 1,
            mutable=True,
            initialized=initialized,
        )
        if not self.symbols.insert(symbol):
            self._error(
                ctx,
                "SEM_DUPLICATE",
                name,
                f"El identificador {name} ya fue declarado en este mismo ámbito.",
                "Cambia el nombre o reutiliza la variable existente sin volver a declararla.",
            )
            return None
        if initialized and declared != UNKNOWN and not self._compatible(declared, actual):
            self._error(
                ctx.initializer(),
                "SEM_ASSIGN_TYPE",
                name,
                f"La variable {name} fue declarada como {declared}, pero se inicializa con {actual}.",
                f"Usa una expresión de tipo {declared} o cambia la anotación de tipo.",
            )
        return None

    def visitConstantDeclaration(self, ctx: CompiscriptParser.ConstantDeclarationContext):
        name = ctx.Identifier().getText()
        declared = self._annotation_type(ctx.typeAnnotation()) if ctx.typeAnnotation() is not None else UNKNOWN
        self._validate_declared_type(ctx, declared)
        if ctx.expression() is None:
            self._error(
                ctx,
                "SEM_CONST_INIT",
                name,
                f"La constante {name} debe inicializarse en la misma declaración.",
                "Agrega = expresión antes del punto y coma.",
            )
            actual = UNKNOWN
        else:
            actual = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        final_type = declared if declared != UNKNOWN else actual
        tok = ctx.Identifier().getSymbol()
        symbol = Symbol(
            name=name,
            kind="constant",
            type_name=final_type,
            line=tok.line,
            column=tok.column + 1,
            mutable=False,
            initialized=ctx.expression() is not None,
        )
        if not self.symbols.insert(symbol):
            self._error(
                ctx,
                "SEM_DUPLICATE",
                name,
                f"El identificador {name} ya fue declarado en este mismo ámbito.",
                "Usa un nombre diferente para la constante.",
            )
            return None
        if declared != UNKNOWN and not self._compatible(declared, actual):
            self._error(
                ctx,
                "SEM_ASSIGN_TYPE",
                name,
                f"La constante {name} fue declarada como {declared}, pero se inicializa con {actual}.",
                f"Inicializa la constante con un valor de tipo {declared}.",
            )
        return None

    def visitAssignment(self, ctx: CompiscriptParser.AssignmentContext):
        expressions = ctx.expression()
        if not isinstance(expressions, list):
            expressions = [expressions]
        if len(expressions) == 1:
            name = ctx.Identifier().getText()
            symbol = self.symbols.lookup(name)
            actual = (self._safe_visit(expressions[0]) or ExprInfo(UNKNOWN)).type_name
            if symbol is None:
                self._error(
                    ctx,
                    "SEM_UNDECLARED",
                    name,
                    f"No se puede asignar a {name} porque no existe una declaración visible.",
                    "Declara la variable antes de usarla.",
                )
            else:
                self._check_assignment(ctx, symbol, actual)
            return None

        # expression '.' Identifier '=' expression ';'
        owner = self._safe_visit(expressions[0]) or ExprInfo(UNKNOWN)
        property_name = ctx.Identifier().getText()
        actual = (self._safe_visit(expressions[-1]) or ExprInfo(UNKNOWN)).type_name
        target = self._resolve_property(ctx, owner.type_name, property_name, for_assignment=True)
        if target is not None:
            self._check_assignment(ctx, target, actual)
        return None

    def visitFunctionDeclaration(self, ctx: CompiscriptParser.FunctionDeclarationContext):
        symbol = self.declaration_symbols.get(id(ctx))
        if symbol is None:
            symbol = self._signature_from_function(ctx)
            if self.symbols.get_local(symbol.name) is None:
                self.symbols.insert(symbol)
        self._analyze_function(ctx, symbol)
        return None

    def _analyze_function(self, ctx, symbol: Symbol) -> None:
        for _, p_type in symbol.params:
            self._validate_declared_type(ctx, p_type)
        self._validate_declared_type(ctx, symbol.return_type)

        # Cada función tiene su propio contexto de control. Un loop exterior no
        # habilita break/continue dentro de una función anidada.
        outer_loop_depth = self.loop_depth

        self.symbols.enter_scope(f"{symbol.kind}_{symbol.name}", symbol.kind)
        self.function_stack.append(symbol)
        self.loop_depth = 0
        try:
            seen_params: set[str] = set()
            param_contexts = ctx.parameters().parameter() if ctx.parameters() is not None else []
            for index, (name, p_type) in enumerate(symbol.params):
                pctx = param_contexts[index]
                if name in seen_params:
                    self._error(
                        pctx,
                        "SEM_DUPLICATE_PARAM",
                        name,
                        f"El parámetro {name} está declarado más de una vez en la función {symbol.name}.",
                        "Usa nombres distintos para cada parámetro.",
                    )
                    continue
                seen_params.add(name)
                tok = pctx.Identifier().getSymbol()
                self.symbols.insert(
                    Symbol(
                        name=name,
                        kind="parameter",
                        type_name=p_type,
                        line=tok.line,
                        column=tok.column + 1,
                        mutable=True,
                        initialized=True,
                    )
                )

            # El bloque crea su propio alcance, manteniendo los parámetros visibles en el padre.
            self._safe_visit(ctx.block())

            # Una función con tipo de retorno explícito debe devolver un valor en
            # todos los caminos que puedan alcanzar el final de su cuerpo.
            if symbol.return_type not in {VOID, UNKNOWN} and not self._block_guarantees_return(ctx.block()):
                self._error(
                    ctx,
                    "SEM_MISSING_RETURN",
                    symbol.name,
                    f"La función {symbol.name} declara retorno {symbol.return_type}, pero no todos los caminos devuelven un valor.",
                    f"Agrega return con una expresión de tipo {symbol.return_type} en todos los caminos de ejecución.",
                )
        finally:
            self.loop_depth = outer_loop_depth
            self.function_stack.pop()
            self.symbols.exit_scope()

    def visitClassDeclaration(self, ctx: CompiscriptParser.ClassDeclarationContext):
        info = self.class_declarations.get(id(ctx))
        if info is None:
            self._predeclare_class(ctx)
            info = self.class_declarations[id(ctx)]

        if info.parent is not None:
            if info.parent not in self.classes:
                self._error(
                    ctx,
                    "SEM_UNKNOWN_PARENT",
                    info.parent,
                    f"La clase padre {info.parent} no está declarada.",
                    "Declara la clase padre antes de usarla como base o corrige el nombre.",
                )
            elif info.parent == info.name:
                self._error(
                    ctx,
                    "SEM_INHERITANCE_CYCLE",
                    info.name,
                    "Una clase no puede heredar de sí misma.",
                    "Selecciona una clase padre diferente.",
                )

        self.symbols.enter_scope(f"class_{info.name}", "class")
        self.class_stack.append(info.name)
        try:
            # Los miembros se registran en el alcance de clase para la tabla de símbolos.
            for attr in info.attributes.values():
                copy = Symbol(**{**attr.__dict__})
                self.symbols.insert(copy)
            for method in info.methods.values():
                copy = Symbol(**{**method.__dict__})
                self.symbols.insert(copy)

            for member in ctx.classMember():
                if member.functionDeclaration() is not None:
                    func = member.functionDeclaration()
                    method = info.methods.get(func.Identifier().getText()) or self._signature_from_function(
                        func, kind="method", owner=info.name
                    )
                    self._analyze_function(func, method)
                elif member.variableDeclaration() is not None:
                    self._analyze_class_field(member.variableDeclaration(), info, is_const=False)
                elif member.constantDeclaration() is not None:
                    self._analyze_class_field(member.constantDeclaration(), info, is_const=True)
        finally:
            self.class_stack.pop()
            self.symbols.exit_scope()
        return None

    def _analyze_class_field(self, ctx, info: ClassInfo, *, is_const: bool) -> None:
        name = ctx.Identifier().getText()
        attr = info.attributes.get(name)
        if attr is None:
            return
        self._validate_declared_type(ctx, attr.type_name)
        expr = ctx.expression() if is_const else (ctx.initializer().expression() if ctx.initializer() is not None else None)
        if is_const and expr is None:
            self._error(
                ctx,
                "SEM_CONST_INIT",
                name,
                f"La constante {name} debe inicializarse en la misma declaración.",
                "Agrega = expresión antes del punto y coma.",
            )
        if expr is not None:
            actual = (self._safe_visit(expr) or ExprInfo(UNKNOWN)).type_name
            if attr.type_name == UNKNOWN:
                attr.type_name = actual
                # Actualiza la copia mostrada en el alcance de clase.
                self.symbols.update_in_scope(name, self.symbols.current_scope_id, type_name=actual, initialized=True)
            elif not self._compatible(attr.type_name, actual):
                self._error(
                    ctx,
                    "SEM_ASSIGN_TYPE",
                    name,
                    f"El atributo {name} es {attr.type_name}, pero se inicializa con {actual}.",
                    f"Usa un valor de tipo {attr.type_name}.",
                )
        return None

    # ------------------------------------------------------------------
    # Control de flujo
    # ------------------------------------------------------------------

    def _require_boolean(self, ctx, type_name: str, construct: str) -> None:
        if type_name not in {"boolean", UNKNOWN}:
            self._error(
                ctx,
                "SEM_CONDITION_BOOL",
                construct,
                f"La condición de {construct} debe ser boolean, pero se obtuvo {type_name}.",
                "Usa una comparación o una expresión lógica que produzca boolean.",
            )

    def visitIfStatement(self, ctx: CompiscriptParser.IfStatementContext):
        cond = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        self._require_boolean(ctx.expression(), cond, "if")
        blocks = ctx.block()
        if not isinstance(blocks, list):
            blocks = [blocks]
        for block in blocks:
            self._safe_visit(block)
        return None

    def visitWhileStatement(self, ctx: CompiscriptParser.WhileStatementContext):
        cond = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        self._require_boolean(ctx.expression(), cond, "while")
        self.loop_depth += 1
        try:
            self._safe_visit(ctx.block())
        finally:
            self.loop_depth -= 1
        return None

    def visitDoWhileStatement(self, ctx: CompiscriptParser.DoWhileStatementContext):
        self.loop_depth += 1
        try:
            self._safe_visit(ctx.block())
        finally:
            self.loop_depth -= 1
        cond = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        self._require_boolean(ctx.expression(), cond, "do-while")
        return None

    def visitForStatement(self, ctx: CompiscriptParser.ForStatementContext):
        self.symbols.enter_scope("for", "loop")
        self.loop_depth += 1
        try:
            if ctx.variableDeclaration() is not None:
                self._safe_visit(ctx.variableDeclaration())
            if ctx.assignment() is not None:
                self._safe_visit(ctx.assignment())
            expressions = ctx.expression()
            if not isinstance(expressions, list):
                expressions = [expressions] if expressions is not None else []
            if expressions:
                cond = (self._safe_visit(expressions[0]) or ExprInfo(UNKNOWN)).type_name
                self._require_boolean(expressions[0], cond, "for")
                for expr in expressions[1:]:
                    self._safe_visit(expr)
            self._safe_visit(ctx.block())
        finally:
            self.loop_depth -= 1
            self.symbols.exit_scope()
        return None

    def visitForeachStatement(self, ctx: CompiscriptParser.ForeachStatementContext):
        iterable = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        item_type = self._array_element(iterable)
        if iterable != UNKNOWN and not self._is_array(iterable):
            self._error(
                ctx.expression(),
                "SEM_FOREACH_ARRAY",
                iterable,
                f"foreach requiere un arreglo, pero la expresión produce {iterable}.",
                "Itera sobre una variable o expresión de tipo T[].",
            )
        self.symbols.enter_scope("foreach", "loop")
        self.loop_depth += 1
        try:
            tok = ctx.Identifier().getSymbol()
            self.symbols.insert(
                Symbol(
                    name=ctx.Identifier().getText(),
                    kind="variable",
                    type_name=item_type,
                    line=tok.line,
                    column=tok.column + 1,
                    mutable=True,
                    initialized=True,
                )
            )
            self._safe_visit(ctx.block())
        finally:
            self.loop_depth -= 1
            self.symbols.exit_scope()
        return None

    def visitBreakStatement(self, ctx: CompiscriptParser.BreakStatementContext):
        if self.loop_depth <= 0:
            self._error(
                ctx,
                "SEM_BREAK_OUTSIDE_LOOP",
                "break",
                "break solo puede utilizarse dentro de un bucle.",
                "Mueve break al interior de for, foreach, while o do-while.",
            )
        return None

    def visitContinueStatement(self, ctx: CompiscriptParser.ContinueStatementContext):
        if self.loop_depth <= 0:
            self._error(
                ctx,
                "SEM_CONTINUE_OUTSIDE_LOOP",
                "continue",
                "continue solo puede utilizarse dentro de un bucle.",
                "Mueve continue al interior de for, foreach, while o do-while.",
            )
        return None

    def visitReturnStatement(self, ctx: CompiscriptParser.ReturnStatementContext):
        if not self.function_stack:
            self._error(
                ctx,
                "SEM_RETURN_OUTSIDE_FUNCTION",
                "return",
                "return no puede utilizarse fuera del cuerpo de una función o método.",
                "Mueve return dentro de una función o elimina la instrucción.",
            )
            if ctx.expression() is not None:
                self._safe_visit(ctx.expression())
            return None

        function = self.function_stack[-1]
        actual = VOID
        if ctx.expression() is not None:
            actual = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        if function.return_type == VOID and actual != VOID:
            self._error(
                ctx,
                "SEM_RETURN_TYPE",
                function.name,
                f"La función {function.name} no declara tipo de retorno, pero return devuelve {actual}.",
                "Declara el tipo de retorno de la función o usa return sin expresión.",
            )
        elif function.return_type != VOID and actual == VOID:
            self._error(
                ctx,
                "SEM_RETURN_TYPE",
                function.name,
                f"La función {function.name} debe devolver {function.return_type}, pero este return no devuelve un valor.",
                f"Devuelve una expresión de tipo {function.return_type}.",
            )
        elif function.return_type != VOID and not self._compatible(function.return_type, actual):
            self._error(
                ctx,
                "SEM_RETURN_TYPE",
                function.name,
                f"La función {function.name} debe devolver {function.return_type}, pero devuelve {actual}.",
                f"Cambia la expresión retornada por una de tipo {function.return_type}.",
            )
        return None

    def visitTryCatchStatement(self, ctx: CompiscriptParser.TryCatchStatementContext):
        blocks = ctx.block()
        self._safe_visit(blocks[0])
        self.symbols.enter_scope("catch", "catch")
        try:
            tok = ctx.Identifier().getSymbol()
            self.symbols.insert(
                Symbol(
                    name=ctx.Identifier().getText(),
                    kind="variable",
                    type_name=UNKNOWN,
                    line=tok.line,
                    column=tok.column + 1,
                    mutable=True,
                    initialized=True,
                )
            )
            self._safe_visit(blocks[1])
        finally:
            self.symbols.exit_scope()
        return None

    def visitSwitchStatement(self, ctx: CompiscriptParser.SwitchStatementContext):
        switch_type = (self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)).type_name
        # El enunciado del proyecto exige explícitamente boolean para switch.
        self._require_boolean(ctx.expression(), switch_type, "switch")
        self.symbols.enter_scope("switch", "switch")
        try:
            for case in ctx.switchCase():
                case_type = (self._safe_visit(case.expression()) or ExprInfo(UNKNOWN)).type_name
                if not self._compatible(switch_type, case_type):
                    self._error(
                        case.expression(),
                        "SEM_SWITCH_CASE_TYPE",
                        case.expression().getText(),
                        f"El case produce {case_type}, incompatible con el switch de tipo {switch_type}.",
                        "Usa valores case del mismo tipo que la expresión de switch.",
                    )
                self._visit_statement_sequence(case.statement())
            if ctx.defaultCase() is not None:
                self._visit_statement_sequence(ctx.defaultCase().statement())
        finally:
            self.symbols.exit_scope()
        return None

    # ------------------------------------------------------------------
    # Expresiones y tipos
    # ------------------------------------------------------------------

    def visitExpression(self, ctx: CompiscriptParser.ExpressionContext):
        return self._safe_visit(ctx.assignmentExpr()) or ExprInfo(UNKNOWN)

    def visitExprNoAssign(self, ctx: CompiscriptParser.ExprNoAssignContext):
        return self._safe_visit(ctx.conditionalExpr()) or ExprInfo(UNKNOWN)

    def visitAssignExpr(self, ctx: CompiscriptParser.AssignExprContext):
        target = self._safe_visit(ctx.lhs) or ExprInfo(UNKNOWN)
        actual = (self._safe_visit(ctx.assignmentExpr()) or ExprInfo(UNKNOWN)).type_name
        if not target.assignable:
            self._error(
                ctx,
                "SEM_NOT_ASSIGNABLE",
                ctx.lhs.getText(),
                "El lado izquierdo de la asignación no representa un destino modificable.",
                "Asigna sobre una variable, atributo o elemento de arreglo válido.",
            )
        else:
            self._check_assignment(ctx, target, actual)
        return ExprInfo(actual)

    def visitPropertyAssignExpr(self, ctx: CompiscriptParser.PropertyAssignExprContext):
        owner = self._safe_visit(ctx.lhs) or ExprInfo(UNKNOWN)
        name = ctx.Identifier().getText()
        actual = (self._safe_visit(ctx.assignmentExpr()) or ExprInfo(UNKNOWN)).type_name
        target = self._resolve_property(ctx, owner.type_name, name, for_assignment=True)
        if target is not None:
            self._check_assignment(ctx, target, actual)
        return ExprInfo(actual)

    def visitTernaryExpr(self, ctx: CompiscriptParser.TernaryExprContext):
        condition = (self._safe_visit(ctx.logicalOrExpr()) or ExprInfo(UNKNOWN)).type_name
        expressions = ctx.expression()
        if not isinstance(expressions, list):
            expressions = [expressions] if expressions is not None else []
        if not expressions:
            return ExprInfo(condition)
        self._require_boolean(ctx.logicalOrExpr(), condition, "operador ternario")
        left = (self._safe_visit(expressions[0]) or ExprInfo(UNKNOWN)).type_name
        right = (self._safe_visit(expressions[1]) or ExprInfo(UNKNOWN)).type_name
        common = self._common_type(left, right)
        if common == UNKNOWN and left != UNKNOWN and right != UNKNOWN:
            self._error(
                ctx,
                "SEM_TERNARY_TYPE",
                "?:",
                f"Las ramas del operador ternario producen tipos incompatibles: {left} y {right}.",
                "Haz que ambas ramas produzcan el mismo tipo o tipos numéricos compatibles.",
            )
        return ExprInfo(common)

    @staticmethod
    def _operator_texts(ctx) -> list[str]:
        ops: list[str] = []
        for child in getattr(ctx, "children", []) or []:
            if isinstance(child, TerminalNodeImpl):
                text = child.getText()
                if text not in {"(", ")", "[", "]", ","}:
                    ops.append(text)
        return ops

    def visitLogicalOrExpr(self, ctx: CompiscriptParser.LogicalOrExprContext):
        operands = ctx.logicalAndExpr()
        infos = [(self._safe_visit(item) or ExprInfo(UNKNOWN)).type_name for item in operands]
        if len(operands) > 1:
            for typ in infos:
                if typ not in {"boolean", UNKNOWN}:
                    self._error(
                        ctx,
                        "SEM_LOGICAL_TYPE",
                        "||",
                        f"Los operandos de || deben ser boolean, pero se encontró {typ}.",
                        "Usa expresiones booleanas en ambos lados del operador lógico.",
                    )
            return ExprInfo("boolean")
        return ExprInfo(infos[0] if infos else UNKNOWN)

    def visitLogicalAndExpr(self, ctx: CompiscriptParser.LogicalAndExprContext):
        operands = ctx.equalityExpr()
        infos = [(self._safe_visit(item) or ExprInfo(UNKNOWN)).type_name for item in operands]
        if len(operands) > 1:
            for typ in infos:
                if typ not in {"boolean", UNKNOWN}:
                    self._error(
                        ctx,
                        "SEM_LOGICAL_TYPE",
                        "&&",
                        f"Los operandos de && deben ser boolean, pero se encontró {typ}.",
                        "Usa expresiones booleanas en ambos lados del operador lógico.",
                    )
            return ExprInfo("boolean")
        return ExprInfo(infos[0] if infos else UNKNOWN)

    def visitEqualityExpr(self, ctx: CompiscriptParser.EqualityExprContext):
        operands = ctx.relationalExpr()
        types = [(self._safe_visit(item) or ExprInfo(UNKNOWN)).type_name for item in operands]
        if len(types) == 1:
            return ExprInfo(types[0])
        for left, right in zip(types, types[1:]):
            if self._common_type(left, right) == UNKNOWN and left != UNKNOWN and right != UNKNOWN:
                self._error(
                    ctx,
                    "SEM_COMPARISON_TYPE",
                    "comparación",
                    f"No se pueden comparar valores de tipos incompatibles: {left} y {right}.",
                    "Compara operandos del mismo tipo o tipos numéricos compatibles.",
                )
        return ExprInfo("boolean")

    def visitRelationalExpr(self, ctx: CompiscriptParser.RelationalExprContext):
        operands = ctx.additiveExpr()
        types = [(self._safe_visit(item) or ExprInfo(UNKNOWN)).type_name for item in operands]
        if len(types) == 1:
            return ExprInfo(types[0])
        for left, right in zip(types, types[1:]):
            # <, <=, > y >= solo tienen sentido para números compatibles o
            # para dos strings (comparación lexicográfica). boolean, arreglos,
            # funciones y objetos no se aceptan como operandos relacionales.
            compatible = (
                UNKNOWN in {left, right}
                or (self._is_numeric(left) and self._is_numeric(right))
                or (left == "string" and right == "string")
            )
            if not compatible:
                self._error(
                    ctx,
                    "SEM_COMPARISON_TYPE",
                    "comparación",
                    f"La comparación relacional usa tipos no comparables: {left} y {right}.",
                    "Usa integer/float en ambos lados o dos valores string para una comparación relacional.",
                )
        return ExprInfo("boolean")

    def visitAdditiveExpr(self, ctx: CompiscriptParser.AdditiveExprContext):
        operands = ctx.multiplicativeExpr()
        types = [(self._safe_visit(item) or ExprInfo(UNKNOWN)).type_name for item in operands]
        if len(types) == 1:
            return ExprInfo(types[0])
        ops = self._operator_texts(ctx)
        result = types[0]
        for index, right in enumerate(types[1:]):
            op = ops[index] if index < len(ops) else "+"
            if op == "+" and result == "string" and right == "string":
                result = "string"
            elif self._is_numeric(result) and self._is_numeric(right):
                result = self._common_type(result, right)
            elif UNKNOWN in {result, right}:
                result = UNKNOWN
            else:
                self._error(
                    ctx,
                    "SEM_ARITHMETIC_TYPE",
                    op,
                    f"El operador {op} requiere operandos numéricos; solo + permite string + string. Se obtuvo {result} y {right}.",
                    "Usa integer/float en operaciones aritméticas o dos string para concatenación con +.",
                )
                result = UNKNOWN
        return ExprInfo(result)

    def visitMultiplicativeExpr(self, ctx: CompiscriptParser.MultiplicativeExprContext):
        operands = ctx.unaryExpr()
        types = [(self._safe_visit(item) or ExprInfo(UNKNOWN)).type_name for item in operands]
        if len(types) == 1:
            return ExprInfo(types[0])
        ops = self._operator_texts(ctx)
        result = types[0]
        for index, right in enumerate(types[1:]):
            op = ops[index] if index < len(ops) else "*"
            if self._is_numeric(result) and self._is_numeric(right):
                result = "float" if op == "/" or "float" in {result, right} else "integer"
            elif UNKNOWN in {result, right}:
                result = UNKNOWN
            else:
                self._error(
                    ctx,
                    "SEM_ARITHMETIC_TYPE",
                    op,
                    f"El operador {op} requiere integer o float, pero se obtuvo {result} y {right}.",
                    "Usa operandos numéricos en *, / y %.",
                )
                result = UNKNOWN
        return ExprInfo(result)

    def visitUnaryExpr(self, ctx: CompiscriptParser.UnaryExprContext):
        if ctx.primaryExpr() is not None:
            return self._safe_visit(ctx.primaryExpr()) or ExprInfo(UNKNOWN)
        operand = self._safe_visit(ctx.unaryExpr()) or ExprInfo(UNKNOWN)
        op = ctx.getChild(0).getText()
        if op == "!":
            if operand.type_name not in {"boolean", UNKNOWN}:
                self._error(
                    ctx,
                    "SEM_LOGICAL_TYPE",
                    "!",
                    f"El operador ! requiere boolean, pero se obtuvo {operand.type_name}.",
                    "Aplica ! únicamente a expresiones booleanas.",
                )
            return ExprInfo("boolean")
        if op == "-":
            if operand.type_name not in NUMERIC_TYPES | {UNKNOWN}:
                self._error(
                    ctx,
                    "SEM_ARITHMETIC_TYPE",
                    "-",
                    f"El operador unario - requiere integer o float, pero se obtuvo {operand.type_name}.",
                    "Aplica - a una expresión numérica.",
                )
                return ExprInfo(UNKNOWN)
            return ExprInfo(operand.type_name)
        return operand

    def visitPrimaryExpr(self, ctx: CompiscriptParser.PrimaryExprContext):
        if ctx.literalExpr() is not None:
            return self._safe_visit(ctx.literalExpr()) or ExprInfo(UNKNOWN)
        if ctx.leftHandSide() is not None:
            return self._safe_visit(ctx.leftHandSide()) or ExprInfo(UNKNOWN)
        if ctx.expression() is not None:
            return self._safe_visit(ctx.expression()) or ExprInfo(UNKNOWN)
        return ExprInfo(UNKNOWN)

    def visitLiteralExpr(self, ctx: CompiscriptParser.LiteralExprContext):
        if ctx.arrayLiteral() is not None:
            return self._safe_visit(ctx.arrayLiteral()) or ExprInfo(UNKNOWN)
        text = ctx.getText()
        if text == "true" or text == "false":
            return ExprInfo("boolean")
        if text == "null":
            return ExprInfo(NULL)
        if text.startswith('"'):
            return ExprInfo("string")
        if "." in text and text.replace(".", "", 1).isdigit():
            return ExprInfo("float")
        if text.isdigit():
            return ExprInfo("integer")
        return ExprInfo(UNKNOWN)

    def visitArrayLiteral(self, ctx: CompiscriptParser.ArrayLiteralContext):
        expressions = ctx.expression()
        if not isinstance(expressions, list):
            expressions = [expressions] if expressions is not None else []
        if not expressions:
            return ExprInfo(f"{UNKNOWN}[]")
        element_type = UNKNOWN
        for expr in expressions:
            current = (self._safe_visit(expr) or ExprInfo(UNKNOWN)).type_name
            if element_type == UNKNOWN:
                element_type = current
                continue
            common = self._common_type(element_type, current)
            if common == UNKNOWN and current != UNKNOWN:
                self._error(
                    expr,
                    "SEM_ARRAY_ELEMENT_TYPE",
                    expr.getText(),
                    f"El arreglo mezcla elementos incompatibles: {element_type} y {current}.",
                    "Usa elementos del mismo tipo o tipos numéricos compatibles.",
                )
            else:
                element_type = common
        return ExprInfo(f"{element_type}[]")

    def visitIdentifierExpr(self, ctx: CompiscriptParser.IdentifierExprContext):
        name = ctx.Identifier().getText()
        symbol = self.symbols.lookup(name)
        if symbol is None:
            self._error(
                ctx,
                "SEM_UNDECLARED",
                name,
                f"El identificador {name} se usa antes de ser declarado en un ámbito visible.",
                "Declara el identificador antes de usarlo o corrige su nombre.",
            )
            return ExprInfo(UNKNOWN)
        if symbol.kind in {"function", "method"}:
            return ExprInfo(FUNCTION, symbol=symbol, callable_symbol=symbol, assignable=False)
        if symbol.kind == "class":
            return ExprInfo(symbol.type_name, symbol=symbol, assignable=False)
        return ExprInfo(symbol.type_name, symbol=symbol, assignable=symbol.mutable)

    def visitNewExpr(self, ctx: CompiscriptParser.NewExprContext):
        class_name = ctx.Identifier().getText()
        info = self.classes.get(class_name)
        arg_types = self._argument_types(ctx.arguments())
        if info is None:
            self._error(
                ctx,
                "SEM_UNKNOWN_CLASS",
                class_name,
                f"No existe una clase declarada llamada {class_name}.",
                "Declara la clase antes de instanciarla o corrige el nombre.",
            )
            return ExprInfo(UNKNOWN)
        constructor = self._find_method(class_name, "constructor")
        if constructor is None:
            if arg_types:
                self._error(
                    ctx,
                    "SEM_CONSTRUCTOR_ARGS",
                    class_name,
                    f"La clase {class_name} no declara constructor, por lo que no acepta argumentos.",
                    "Instancia la clase sin argumentos o declara un método constructor con parámetros.",
                )
        else:
            self._validate_call(ctx, constructor, arg_types, display_name=f"constructor de {class_name}")
        return ExprInfo(class_name)

    def visitThisExpr(self, ctx: CompiscriptParser.ThisExprContext):
        if not self.class_stack:
            self._error(
                ctx,
                "SEM_THIS_OUTSIDE_CLASS",
                "this",
                "this solo puede utilizarse dentro de una clase.",
                "Usa this únicamente dentro de métodos o constructores de una clase.",
            )
            return ExprInfo(UNKNOWN)
        return ExprInfo(self.class_stack[-1])

    def visitLeftHandSide(self, ctx: CompiscriptParser.LeftHandSideContext):
        current = self._safe_visit(ctx.primaryAtom()) or ExprInfo(UNKNOWN)
        for suffix in ctx.suffixOp():
            if isinstance(suffix, CompiscriptParser.CallExprContext):
                arg_types = self._argument_types(suffix.arguments())
                if current.callable_symbol is None:
                    self._error(
                        suffix,
                        "SEM_NOT_CALLABLE",
                        ctx.getText(),
                        f"La expresión de tipo {current.type_name} no puede invocarse como función.",
                        "Invoca únicamente identificadores de función o métodos.",
                    )
                    current = ExprInfo(UNKNOWN)
                else:
                    self._validate_call(suffix, current.callable_symbol, arg_types)
                    current = ExprInfo(current.callable_symbol.return_type)
            elif isinstance(suffix, CompiscriptParser.IndexExprContext):
                index_type = (self._safe_visit(suffix.expression()) or ExprInfo(UNKNOWN)).type_name
                if index_type not in {"integer", UNKNOWN}:
                    self._error(
                        suffix.expression(),
                        "SEM_INDEX_TYPE",
                        suffix.expression().getText(),
                        f"El índice de un arreglo debe ser integer, pero se obtuvo {index_type}.",
                        "Usa una expresión de tipo integer como índice.",
                    )
                if not self._is_array(current.type_name) and current.type_name != UNKNOWN:
                    self._error(
                        suffix,
                        "SEM_INDEX_NON_ARRAY",
                        current.type_name,
                        f"No se puede indexar una expresión de tipo {current.type_name} porque no es un arreglo.",
                        "Aplica [] únicamente sobre valores de tipo T[].",
                    )
                    current = ExprInfo(UNKNOWN)
                else:
                    current = ExprInfo(self._array_element(current.type_name), assignable=True)
            elif isinstance(suffix, CompiscriptParser.PropertyAccessExprContext):
                name = suffix.Identifier().getText()
                member = self._resolve_property(suffix, current.type_name, name, for_assignment=False)
                if member is None:
                    current = ExprInfo(UNKNOWN)
                elif member.kind == "method":
                    current = ExprInfo(FUNCTION, symbol=member, callable_symbol=member, assignable=False)
                else:
                    current = ExprInfo(member.type_name, symbol=member, assignable=member.mutable)
        return current

    def _argument_types(self, arguments_ctx) -> list[str]:
        if arguments_ctx is None:
            return []
        expressions = arguments_ctx.expression()
        if not isinstance(expressions, list):
            expressions = [expressions]
        return [(self._safe_visit(expr) or ExprInfo(UNKNOWN)).type_name for expr in expressions]

    def _validate_call(self, ctx, function: Symbol, arg_types: list[str], display_name: str | None = None) -> None:
        name = display_name or function.name
        if len(arg_types) != len(function.params):
            self._error(
                ctx,
                "SEM_ARGUMENT_COUNT",
                function.name,
                f"La llamada a {name} recibe {len(arg_types)} argumento(s), pero espera {len(function.params)}.",
                f"Proporciona exactamente {len(function.params)} argumento(s).",
            )
        for index, (actual, (_, expected)) in enumerate(zip(arg_types, function.params), start=1):
            if not self._compatible(expected, actual):
                self._error(
                    ctx,
                    "SEM_ARGUMENT_TYPE",
                    function.name,
                    f"El argumento {index} de {name} debe ser {expected}, pero se obtuvo {actual}.",
                    f"Cambia el argumento {index} por una expresión de tipo {expected}.",
                )

    # ------------------------------------------------------------------
    # Clases / propiedades
    # ------------------------------------------------------------------

    def _class_chain(self, class_name: str):
        seen: set[str] = set()
        current = class_name
        while current and current not in seen:
            seen.add(current)
            info = self.classes.get(current)
            if info is None:
                break
            yield info
            current = info.parent

    def _find_attribute(self, class_name: str, name: str) -> Symbol | None:
        for info in self._class_chain(class_name):
            if name in info.attributes:
                return info.attributes[name]
        return None

    def _find_method(self, class_name: str, name: str) -> Symbol | None:
        for info in self._class_chain(class_name):
            if name in info.methods:
                return info.methods[name]
        return None

    def _resolve_property(self, ctx, owner_type: str, name: str, *, for_assignment: bool) -> Symbol | None:
        if owner_type == UNKNOWN:
            return None
        if owner_type in PRIMITIVE_TYPES or self._is_array(owner_type) or owner_type == NULL:
            self._error(
                ctx,
                "SEM_PROPERTY_NON_OBJECT",
                name,
                f"No se puede acceder a {name} sobre un valor de tipo {owner_type}.",
                "Usa notación punto sobre una instancia de una clase que declare ese miembro.",
            )
            return None
        if owner_type not in self.classes:
            self._error(
                ctx,
                "SEM_UNKNOWN_CLASS",
                owner_type,
                f"El tipo de objeto {owner_type} no corresponde a una clase declarada.",
                "Corrige el tipo del objeto o declara la clase correspondiente.",
            )
            return None
        attr = self._find_attribute(owner_type, name)
        method = self._find_method(owner_type, name)
        member = attr or method
        if member is None:
            self._error(
                ctx,
                "SEM_UNKNOWN_MEMBER",
                name,
                f"La clase {owner_type} no declara un atributo o método llamado {name}.",
                "Corrige el nombre del miembro o decláralo en la clase.",
            )
            return None
        if for_assignment and member.kind == "method":
            self._error(
                ctx,
                "SEM_ASSIGN_METHOD",
                name,
                f"No se puede asignar un valor al método {name}.",
                "Asigna únicamente sobre atributos modificables.",
            )
            return None
        return member
