"""Traducción estática Compiscript -> TAC (ANTLR Visitor). Nunca interpreta el TAC."""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import contextmanager

from generated.CompiscriptVisitor import CompiscriptVisitor
from tac_ir import TACProgram, Instruction, TemporaryPool


@dataclass
class Value:
    place: str
    temporary: bool = False
    receiver: str | None = None


class TACGenerationError(Exception):
    pass


class TACGenerator(CompiscriptVisitor):
    def __init__(self, symbol_table, classes):
        super().__init__()
        self.symbols, self.classes = symbol_table, classes
        self.program = TACProgram()
        self.scope = 0
        self.pool = TemporaryPool()
        self.frame = '<global>'
        self.label_number = 0
        self.break_targets = []
        self.continue_targets = []
        # Depths of installed try handlers; required for abrupt exits.
        self.active_try = []
        self.function_queue = []
        self.class_owner = None
        self.field_initializer_jobs = []

    def emit(self, op, *args, ctx=None):
        line = getattr(getattr(ctx, 'start', None), 'line', 0) if ctx is not None else 0
        self.program.instructions.append(Instruction(op, tuple(str(a) for a in args), line))

    def label(self, prefix='L'):
        number = self.label_number
        self.label_number += 1
        return f'{prefix}{number}'

    def tmp(self):
        return Value(self.pool.acquire(), True)

    def free(self, *values):
        for v in values:
            if isinstance(v, Value) and v.temporary:
                self.pool.release(v.place)

    def snapshot(self, value):
        """Preserve an lvalue's current value before evaluating a later operand.

        A variable such as `a@s0` is a *location*, not a frozen value: evaluating
        `a + (a = 3)` without copying the first operand reads a twice after
        mutation. Constants and live temporaries already have value semantics.
        """
        if not isinstance(value, Value) or value.temporary or value.receiver is not None:
            return value
        if '@s' not in value.place and value.place != 'this':
            return value
        result = self.tmp()
        self.emit('MOVE', result.place, value.place)
        return result

    @staticmethod
    def _for_clauses(ctx):
        """Identify condition and step by the actual semicolon token positions.

        `for (; ; i = i + 1)` has ONE expression and it is the step, not
        the condition. Counting ctx.expression() loses that distinction.
        """
        semicolons = [node for node in ctx.children if node.getText() == ';']
        if not semicolons:
            raise TACGenerationError('for: no se encontró separador de cláusulas')
        boundary = semicolons[-1].symbol.tokenIndex
        condition = step = None
        for expr in ctx.expression():
            if expr.start.tokenIndex < boundary: condition = expr
            else: step = expr
        return condition, step

    def _jump_cleanup(self, target_depth):
        """Remove handlers exited by a nonlocal jump; keep surrounding ones."""
        for _ in self.active_try[target_depth:]:
            self.emit('END_TRY')

    def scope_of(self, ctx):
        return getattr(ctx, '_tac_scope_id', self.scope)

    @contextmanager
    def in_scope(self, ctx):
        previous = self.scope
        self.scope = self.scope_of(ctx)
        try:
            yield
        finally:
            self.scope = previous

    def name(self, identifier):
        symbol = self.symbols.lookup(identifier, self.scope)
        if symbol is None:
            raise TACGenerationError(f'Símbolo no disponible para TAC: {identifier} (ámbito {self.scope})')
        return symbol.tac_name or f'{identifier}@s{symbol.scope_id}'

    def generate(self, tree):
        self.symbols.plan_storage(self.classes)
        self.emit('LABEL', 'main')
        self.visit(tree)
        self.emit('RETURN')
        while self.function_queue:
            ctx, label, parent_scope, owner = self.function_queue.pop(0)
            self._function_body(ctx, label, parent_scope, owner)
        for owner, parent_scope, fields in self.field_initializer_jobs:
            self._field_initializer_body(owner, parent_scope, fields)
        self._finish_frame()
        self.program.allocated_temporaries += self.pool.next_id
        self.program.reused_temporaries += self.pool.reused
        self.program.peak_temporaries = max(self.program.peak_temporaries, self.pool.peak)
        self.program.frame_temporaries[self.frame] = self.pool.peak
        return self.program

    def _finish_frame(self):
        self.program.frame_temporaries[self.frame] = max(self.pool.peak, self.program.frame_temporaries.get(self.frame, 0))

    def visitProgram(self, ctx):
        for stmt in ctx.statement(): self.visit(stmt)

    def visitBlock(self, ctx):
        with self.in_scope(ctx):
            for stmt in ctx.statement(): self.visit(stmt)

    def visitVariableDeclaration(self, ctx):
        name = self.name(ctx.Identifier().getText())
        if ctx.initializer():
            rhs = self.visit(ctx.initializer().expression())
            self.emit('MOVE', name, rhs.place, ctx=ctx)
            self.free(rhs)
        else:
            self.emit('DECLARE', name, ctx=ctx)

    def visitConstantDeclaration(self, ctx):
        name = self.name(ctx.Identifier().getText())
        if ctx.expression():
            rhs = self.visit(ctx.expression())
            self.emit('MOVE', name, rhs.place, ctx=ctx)
            self.free(rhs)

    def visitAssignment(self, ctx):
        if ctx.Identifier() and ctx.expression() and ctx.getChild(0).getText() == ctx.Identifier().getText():
            value = self.visit(ctx.expression(0))
            self.emit('MOVE', self.name(ctx.Identifier().getText()), value.place, ctx=ctx)
            self.free(value)
        else:
            # expr.prop = rhs: evaluation of receiver precedes RHS, including side effects.
            receiver = self.snapshot(self.visit(ctx.expression(0)))
            rhs = self.visit(ctx.expression(1))
            self.emit('SET_FIELD', receiver.place, ctx.Identifier().getText(), rhs.place, ctx=ctx)
            self.free(receiver, rhs)

    def visitPrintStatement(self, ctx):
        v = self.visit(ctx.expression())
        self.emit('PRINT', v.place, ctx=ctx)
        self.free(v)

    def visitExpressionStatement(self, ctx):
        self.free(self.visit(ctx.expression()))

    def visitIfStatement(self, ctx):
        else_label, exit_label = self.label('else'), self.label('endif')
        condition = self.visit(ctx.expression())
        self.emit('IF_FALSE', condition.place, else_label, ctx=ctx)
        self.free(condition)
        blocks = ctx.block()
        self.visit(blocks[0])
        if len(blocks) > 1: self.emit('GOTO', exit_label)
        self.emit('LABEL', else_label)
        if len(blocks) > 1:
            self.visit(blocks[1])
            self.emit('LABEL', exit_label)

    def visitWhileStatement(self, ctx):
        begin, exit_ = self.label('while'), self.label('endwhile')
        self.emit('LABEL', begin)
        cond = self.visit(ctx.expression())
        self.emit('IF_FALSE', cond.place, exit_, ctx=ctx)
        self.free(cond)
        self.break_targets.append((exit_, len(self.active_try))); self.continue_targets.append((begin, len(self.active_try)))
        self.visit(ctx.block())
        self.break_targets.pop(); self.continue_targets.pop()
        self.emit('GOTO', begin); self.emit('LABEL', exit_)

    def visitDoWhileStatement(self, ctx):
        begin, condition_label, end = self.label('do'), self.label('docond'), self.label('enddo')
        self.emit('LABEL', begin)
        self.break_targets.append((end, len(self.active_try))); self.continue_targets.append((condition_label, len(self.active_try)))
        self.visit(ctx.block())
        self.break_targets.pop(); self.continue_targets.pop()
        self.emit('LABEL', condition_label)
        cond = self.visit(ctx.expression())
        self.emit('IF_TRUE', cond.place, begin, ctx=ctx)
        self.free(cond)
        self.emit('LABEL', end)

    def visitForStatement(self, ctx):
        with self.in_scope(ctx):
            if ctx.variableDeclaration(): self.visit(ctx.variableDeclaration())
            if ctx.assignment(): self.visit(ctx.assignment())
            condlabel, step, exit_ = self.label('for'), self.label('forstep'), self.label('endfor')
            condition, increment = self._for_clauses(ctx)
            self.emit('LABEL', condlabel)
            if condition is not None:
                cond = self.visit(condition); self.emit('IF_FALSE', cond.place, exit_, ctx=ctx); self.free(cond)
            self.break_targets.append((exit_, len(self.active_try))); self.continue_targets.append((step, len(self.active_try)))
            self.visit(ctx.block())
            self.break_targets.pop(); self.continue_targets.pop()
            self.emit('LABEL', step)
            if increment is not None: self.free(self.visit(increment))
            self.emit('GOTO', condlabel); self.emit('LABEL', exit_)

    def visitForeachStatement(self, ctx):
        array = self.snapshot(self.visit(ctx.expression()))
        with self.in_scope(ctx):
            item = self.name(ctx.Identifier().getText())
            index = self.tmp(); length = self.tmp()
            self.emit('MOVE', index.place, '0', ctx=ctx)
            self.emit('ARRAY_LEN', length.place, array.place, ctx=ctx)
            begin, step, end = self.label('foreach'), self.label('foreachstep'), self.label('endforeach')
            self.emit('LABEL', begin)
            cond = self.tmp(); self.emit('BIN', cond.place, index.place, '<', length.place)
            self.emit('IF_FALSE', cond.place, end); self.free(cond)
            self.emit('ARRAY_GET', item, array.place, index.place)
            self.break_targets.append((end, len(self.active_try))); self.continue_targets.append((step, len(self.active_try)))
            self.visit(ctx.block())
            self.break_targets.pop(); self.continue_targets.pop()
            self.emit('LABEL', step)
            self.emit('BIN', index.place, index.place, '+', '1')
            self.emit('GOTO', begin); self.emit('LABEL', end)
            self.free(index, length)
        self.free(array)

    def visitSwitchStatement(self, ctx):
        v = self.snapshot(self.visit(ctx.expression()))
        end = self.label('endswitch')
        with self.in_scope(ctx):
            cases = ctx.switchCase()
            labels = [self.label('case') for _ in cases]
            default = self.label('default') if ctx.defaultCase() else end
            for case, target in zip(cases, labels):
                x = self.visit(case.expression()); pred = self.tmp()
                self.emit('BIN', pred.place, v.place, '==', x.place)
                self.emit('IF_TRUE', pred.place, target)
                self.free(x, pred)
            self.emit('GOTO', default); self.free(v)
            self.break_targets.append((end, len(self.active_try)))
            for case, target in zip(cases, labels):
                self.emit('LABEL', target)
                for stmt in case.statement(): self.visit(stmt)
            if ctx.defaultCase():
                self.emit('LABEL', default)
                for stmt in ctx.defaultCase().statement(): self.visit(stmt)
            self.break_targets.pop()
            self.emit('LABEL', end)

    def visitBreakStatement(self, ctx):
        if not self.break_targets: raise TACGenerationError('break sin destino (validación semántica inconsistente)')
        destination, depth = self.break_targets[-1]
        self._jump_cleanup(depth)
        self.emit('GOTO', destination, ctx=ctx)

    def visitContinueStatement(self, ctx):
        if not self.continue_targets: raise TACGenerationError('continue sin destino (validación semántica inconsistente)')
        destination, depth = self.continue_targets[-1]
        self._jump_cleanup(depth)
        self.emit('GOTO', destination, ctx=ctx)

    def visitReturnStatement(self, ctx):
        if ctx.expression():
            value = self.visit(ctx.expression())
            self._jump_cleanup(0)
            self.emit('RETURN', value.place, ctx=ctx)
            self.free(value)
        else:
            self._jump_cleanup(0)
            self.emit('RETURN', ctx=ctx)

    def visitTryCatchStatement(self, ctx):
        handler, end = self.label('catch'), self.label('endtry')
        self.emit('TRY', handler, ctx=ctx)
        self.active_try.append(handler)
        try:
            self.visit(ctx.block(0))
        finally:
            self.active_try.pop()
        self.emit('END_TRY')
        self.emit('GOTO', end)
        self.emit('LABEL', handler)
        previous = self.scope
        self.scope = getattr(ctx, '_tac_catch_scope_id', self.scope)
        self.emit('CATCH', self.name(ctx.Identifier().getText()))
        self.visit(ctx.block(1))
        self.scope = previous
        self.emit('LABEL', end)

    def visitFunctionDeclaration(self, ctx):
        name = ctx.Identifier().getText()
        label = f'{self.class_owner}.{name}' if self.class_owner else self.name(name)
        parent = self.scope
        self.function_queue.append((ctx, label, parent, self.class_owner))
        if parent != 0 and self.class_owner is None:
            # Abstracto: capta el entorno léxico; se materializa por invocación.
            self.emit('CLOSURE', label, label, f's{parent}', ctx=ctx)

    def _function_body(self, ctx, label, parent_scope, owner):
        previous = (self.scope, self.pool, self.frame, self.break_targets, self.continue_targets, self.class_owner, self.active_try)
        self._finish_frame()
        self.scope = getattr(ctx, '_tac_scope_id', parent_scope)
        self.pool = TemporaryPool()
        self.frame = f'{label}@s{self.scope}'
        self.break_targets, self.continue_targets, self.active_try = [], [], []
        # Dentro de métodos, funciones locales son closures normales, no métodos.
        self.class_owner = None
        params = ctx.parameters().parameter() if ctx.parameters() else []
        self.emit('FUNC', label, ', '.join(self.name(p.Identifier().getText()) for p in params), ctx=ctx)
        self.visit(ctx.block())
        self.emit('RETURN')
        self.emit('ENDFUNC', label)
        self._finish_frame()
        self.program.allocated_temporaries += self.pool.next_id
        self.program.reused_temporaries += self.pool.reused
        self.program.peak_temporaries = max(self.program.peak_temporaries, self.pool.peak)
        self.scope, self.pool, self.frame, self.break_targets, self.continue_targets, self.class_owner, self.active_try = previous

    def visitClassDeclaration(self, ctx):
        names = ctx.Identifier()
        name = names[0].getText()
        parent = names[1].getText() if len(names) > 1 else ''
        self.emit('CLASS', name, parent, ctx=ctx)
        initializers = []
        previous = self.class_owner
        self.class_owner = name
        with self.in_scope(ctx):
            for member in ctx.classMember():
                if member.functionDeclaration():
                    self.visit(member.functionDeclaration())
                else:
                    field = member.variableDeclaration() or member.constantDeclaration()
                    self.emit('FIELD', name, field.Identifier().getText(), ctx=field)
                    initializer = (field.initializer().expression() if field.initializer() else None) if member.variableDeclaration() else field.expression()
                    if initializer is not None:
                        initializers.append((field.Identifier().getText(), initializer))
        self.emit('ENDCLASS', name)
        if initializers:
            self.field_initializer_jobs.append((name, self.scope_of(ctx), initializers))
        self.class_owner = previous

    def _field_initializer_body(self, owner, scope_id, fields):
        """Inicializadores evaluados en cada NEW, nunca durante la declaración de clase."""
        previous = (self.scope, self.pool, self.frame, self.break_targets, self.continue_targets, self.class_owner, self.active_try)
        self.scope = scope_id
        self.pool = TemporaryPool()
        self.frame = f'{owner}.$fields'
        self.class_owner = owner
        self.break_targets, self.continue_targets, self.active_try = [], [], []
        self.emit('FUNC', f'{owner}.$fields', 'this')
        for name, expr in fields:
            value = self.visit(expr)
            self.emit('SET_FIELD', 'this', name, value.place, ctx=expr)
            self.free(value)
        self.emit('RETURN')
        self.emit('ENDFUNC', f'{owner}.$fields')
        self._finish_frame()
        self.program.allocated_temporaries += self.pool.next_id
        self.program.reused_temporaries += self.pool.reused
        self.program.peak_temporaries = max(self.program.peak_temporaries, self.pool.peak)
        self.scope, self.pool, self.frame, self.break_targets, self.continue_targets, self.class_owner, self.active_try = previous

    def visitExpression(self, ctx): return self.visit(ctx.assignmentExpr())
    def visitExprNoAssign(self, ctx): return self.visit(ctx.conditionalExpr())

    def _lvalue(self, ctx):
        if len(ctx.suffixOp()) == 0 and ctx.primaryAtom().Identifier():
            return ('var', self.name(ctx.primaryAtom().Identifier().getText()), None)
        suffixes = ctx.suffixOp()
        last = suffixes[-1]
        if getattr(last, "expression", lambda: None)() is not None:
            base = self._lhs_prefix(ctx, len(suffixes)-1)
            base = self.snapshot(base)
            index = self.snapshot(self.visit(last.expression()))
            return ('index', base, index)
        if getattr(last, "Identifier", lambda: None)():
            base = self.snapshot(self._lhs_prefix(ctx, len(suffixes)-1))
            return ('field', base, last.Identifier().getText())
        raise TACGenerationError('Destino de asignación no representable')

    def _lhs_prefix(self, ctx, n):
        base = self.visit(ctx.primaryAtom())
        for suffix in ctx.suffixOp()[:n]:
            base = self._apply_suffix(base, suffix)
        if base.receiver is not None:
            out = self.tmp()
            receiver, field = base.place.rsplit('.', 1)
            self.emit('GET_FIELD', out.place, receiver, field)
            if base.temporary: self.pool.release(receiver)
            base = out
        return base

    def _store(self, ref, rhs):
        kind, base, key = ref
        if kind == 'var': self.emit('MOVE', base, rhs.place)
        elif kind == 'field': self.emit('SET_FIELD', base.place, key, rhs.place); self.free(base)
        else: self.emit('ARRAY_SET', base.place, key.place, rhs.place); self.free(base, key)

    def visitAssignExpr(self, ctx):
        ref = self._lvalue(ctx.lhs)
        rhs = self.visit(ctx.assignmentExpr())
        self._store(ref, rhs)
        return rhs

    def visitPropertyAssignExpr(self, ctx):
        base = self.snapshot(self.visit(ctx.lhs))
        rhs = self.visit(ctx.assignmentExpr())
        self.emit('SET_FIELD', base.place, ctx.Identifier().getText(), rhs.place)
        self.free(base)
        return rhs

    def visitTernaryExpr(self, ctx):
        cond = self.visit(ctx.logicalOrExpr())
        exprs = ctx.expression()
        if not exprs: return cond
        out = self.tmp(); else_label, end = self.label('ternary_else'), self.label('ternary_end')
        self.emit('IF_FALSE', cond.place, else_label); self.free(cond)
        left = self.visit(exprs[0]); self.emit('MOVE', out.place, left.place); self.free(left)
        self.emit('GOTO', end); self.emit('LABEL', else_label)
        right = self.visit(exprs[1]); self.emit('MOVE', out.place, right.place); self.free(right)
        self.emit('LABEL', end)
        return out

    def _binary_chain(self, ctx, getter, operators):
        parts = getter()
        value = self.visit(parts[0])
        for op, term in zip(operators, parts[1:]):
            value = self.snapshot(value)
            right = self.visit(term)
            out = value if value.temporary else self.tmp()
            if out is value:
                # Reutilización in situ: conserva el registro y sobrescribe un valor muerto.
                self.pool.reused += 1
            self.emit('BIN', out.place, value.place, op, right.place, ctx=ctx)
            if out is not value: self.free(value)
            self.free(right)
            value = out
        return value

    @staticmethod
    def _operators(ctx):
        return [child.getText() for child in ctx.children if child.getText() in {'+', '-', '*', '/', '%', '==', '!=', '<', '<=', '>', '>='}]

    def visitEqualityExpr(self, ctx): return self._binary_chain(ctx, ctx.relationalExpr, self._operators(ctx))
    def visitRelationalExpr(self, ctx): return self._binary_chain(ctx, ctx.additiveExpr, self._operators(ctx))
    def visitAdditiveExpr(self, ctx): return self._binary_chain(ctx, ctx.multiplicativeExpr, self._operators(ctx))
    def visitMultiplicativeExpr(self, ctx): return self._binary_chain(ctx, ctx.unaryExpr, self._operators(ctx))

    def _logical(self, ctx, members, short_circuit, jump):
        pieces = members()
        value = self.visit(pieces[0])
        if len(pieces) == 1: return value
        out, end = self.tmp(), self.label('shortcircuit')
        self.emit('MOVE', out.place, value.place); self.free(value)
        for next_expr in pieces[1:]:
            self.emit(jump, out.place, end)
            rhs = self.visit(next_expr)
            self.emit('MOVE', out.place, rhs.place); self.free(rhs)
        self.emit('LABEL', end)
        return out

    def visitLogicalAndExpr(self, ctx): return self._logical(ctx, ctx.equalityExpr, 'false', 'IF_FALSE')
    def visitLogicalOrExpr(self, ctx): return self._logical(ctx, ctx.logicalAndExpr, 'true', 'IF_TRUE')

    def visitUnaryExpr(self, ctx):
        if ctx.unaryExpr() is not None:
            v = self.visit(ctx.unaryExpr())
            out = v if v.temporary else self.tmp()
            if out is v: self.pool.reused += 1
            self.emit('UNARY', out.place, ctx.getChild(0).getText(), v.place, ctx=ctx)
            return out
        return self.visit(ctx.primaryExpr())

    def visitPrimaryExpr(self, ctx):
        if ctx.literalExpr(): return self.visit(ctx.literalExpr())
        if ctx.leftHandSide(): return self.visit(ctx.leftHandSide())
        return self.visit(ctx.expression())

    def visitLiteralExpr(self, ctx):
        if ctx.arrayLiteral(): return self.visit(ctx.arrayLiteral())
        return Value(ctx.getText())

    def visitArrayLiteral(self, ctx):
        expressions = ctx.expression()
        result = self.tmp()
        self.emit('NEW_ARRAY', result.place, str(len(expressions)), ctx=ctx)
        for i, expr in enumerate(expressions):
            v = self.visit(expr)
            self.emit('ARRAY_SET', result.place, str(i), v.place)
            self.free(v)
        return result

    def visitIdentifierExpr(self, ctx): return Value(self.name(ctx.Identifier().getText()))
    def visitThisExpr(self, ctx): return Value('this')

    def visitNewExpr(self, ctx):
        name = ctx.Identifier().getText()
        params = ctx.arguments().expression() if ctx.arguments() else []
        # Argument expressions run before the field initializers/constructor.
        # Snapshot each earlier argument before a later argument can mutate it.
        args = [self.snapshot(self.visit(expr)) for expr in params]
        obj = self.tmp()
        self.emit('NEW', obj.place, name, ctx=ctx)
        # NEW initializes the inherited field layout; constructor follows.
        self.emit('INIT_FIELDS', obj.place, name)
        if args:
            for arg in args: self.emit('PARAM', arg.place)
            self.emit('CALL_METHOD', '_', obj.place + '.constructor', str(len(args)), ctx=ctx)
            self.free(*args)
        else:
            # Explicit zero-argument constructors must also be invoked.
            info = self.classes.get(name)
            parent = info
            while parent is not None:
                if 'constructor' in parent.methods:
                    self.emit('CALL_METHOD', '_', obj.place + '.constructor', '0')
                    break
                parent = self.classes.get(parent.parent) if parent.parent else None
        return obj

    def _apply_suffix(self, base, suffix):
        if getattr(suffix, "expression", lambda: None)() is not None:
            base = self.snapshot(base)
            index = self.visit(suffix.expression())
            out = self.tmp()
            self.emit('ARRAY_GET', out.place, base.place, index.place, ctx=suffix)
            self.free(base, index)
            return out
        if getattr(suffix, "Identifier", lambda: None)():
            if base.receiver is not None:
                intermediate = self.tmp()
                obj, prop = base.place.rsplit(".", 1)
                self.emit("GET_FIELD", intermediate.place, obj, prop)
                if base.temporary: self.pool.release(obj)
                base = intermediate
            property_name = suffix.Identifier().getText()
            # Deferred property load: when followed by (), it denotes a method.
            return Value(f'{base.place}.{property_name}', base.temporary, receiver=base.place)
        if suffix.getChild(0).getText() == '(':
            # Freeze receiver and each argument before later side effects.
            if base.receiver is not None:
                receiver, field = base.place.rsplit('.', 1)
                fixed = self.snapshot(Value(receiver, base.temporary))
                base = Value(f'{fixed.place}.{field}', fixed.temporary, receiver=fixed.place)
            args = [self.snapshot(self.visit(expr)) for expr in (suffix.arguments().expression() if suffix.arguments() else [])]
            for arg in args: self.emit('PARAM', arg.place)
            out = self.tmp()
            if base.receiver is not None:
                self.emit('CALL_METHOD', out.place, base.place, str(len(args)), ctx=suffix)
            else:
                self.emit('CALL', out.place, base.place, str(len(args)), ctx=suffix)
            # For a property receiver held in a temporary, release its register.
            if base.temporary:
                if base.receiver is not None: self.pool.release(base.receiver)
                else: self.pool.release(base.place)
            self.free(*args)
            return out
        raise TACGenerationError('Sufijo sin implementación')

    def visitLeftHandSide(self, ctx):
        suffixes = ctx.suffixOp()
        value = self.visit(ctx.primaryAtom())
        for suffix in suffixes:
            if value.receiver is not None and getattr(suffix, "expression", lambda: None)() is not None:
                # Resolve property before indexing it.
                target = self.tmp()
                base, prop = value.place.rsplit('.', 1)
                self.emit('GET_FIELD', target.place, base, prop)
                if value.temporary: self.pool.release(base)
                value = target
            value = self._apply_suffix(value, suffix)
        if value.receiver is not None:
            out = self.tmp()
            base, prop = value.place.rsplit('.', 1)
            self.emit('GET_FIELD', out.place, base, prop)
            if value.temporary: self.pool.release(base)
            return out
        return value
