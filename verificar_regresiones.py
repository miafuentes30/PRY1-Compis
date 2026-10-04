"""Regresiones estructurales del Proyecto 2 (no ejecuta Compiscript)."""
from __future__ import annotations

import unittest
from pathlib import Path

from bootstrap import ensure_generated


class TACRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_generated()
        from analyzer import CompiscriptAnalyzer
        cls.compiler = CompiscriptAnalyzer()

    def compile(self, source):
        result = self.compiler.analyze_full_text(source)
        self.assertFalse(result.errors, [(e.code, e.description) for e in result.errors])
        self.assertIsNotNone(result.tac)
        self.check_targets(result.tac)
        return result.tac.instructions

    def compile_result(self, source):
        result = self.compiler.analyze_full_text(source)
        self.assertFalse(result.errors, [(e.code, e.description) for e in result.errors])
        self.assertIsNotNone(result.tac)
        self.check_targets(result.tac)
        return result

    def check_targets(self, tac):
        labels = [i.args[0] for i in tac.instructions if i.opcode == 'LABEL']
        self.assertEqual(len(labels), len(set(labels)), 'etiquetas duplicadas')
        for inst in tac.instructions:
            if inst.opcode in {'GOTO', 'IF_TRUE', 'IF_FALSE', 'TRY'}:
                self.assertIn(inst.args[-1], labels, 'salto a etiqueta inexistente')

    @staticmethod
    def fixture(filename):
        return (Path(__file__).resolve().parent / 'pruebas_regresion' / filename).read_text(encoding='utf-8')

    @staticmethod
    def op_instructions(ir, opcode):
        return [i for i in ir if i.opcode == opcode]

    @staticmethod
    def op_indexes(ir, opcode):
        return [n for n, i in enumerate(ir) if i.opcode == opcode]

    @staticmethod
    def temp_uses(inst):
        def is_temp(value):
            return isinstance(value, str) and value.startswith('t') and value[1:].isdigit()
        op, args = inst.opcode, inst.args
        if op in {'MOVE', 'UNARY'}:
            return [x for x in args[1:] if is_temp(x)]
        if op == 'BIN':
            return [x for x in (args[1], args[3]) if is_temp(x)]
        if op in {'IF_TRUE', 'IF_FALSE', 'PARAM', 'PRINT', 'RETURN', 'ARRAY_LEN', 'NEW_ARRAY'}:
            return [x for x in args[:1] if is_temp(x)]
        if op == 'ARRAY_GET':
            return [x for x in args[1:] if is_temp(x)]
        if op == 'ARRAY_SET':
            return [x for x in args if is_temp(x)]
        if op in {'GET_FIELD', 'SET_FIELD'}:
            return [x for x in args if is_temp(x)]
        if op in {'CALL', 'CALL_METHOD', 'NEW', 'CLOSURE'}:
            return [x for x in args[1:] if is_temp(x)]
        return []

    @staticmethod
    def temp_def(inst):
        if inst.opcode in {'MOVE', 'BIN', 'UNARY', 'CALL', 'CALL_METHOD', 'NEW_ARRAY', 'ARRAY_GET', 'ARRAY_LEN', 'NEW', 'GET_FIELD', 'CLOSURE'}:
            target = inst.args[0]
            if target.startswith('t') and target[1:].isdigit():
                return target
        return None

    def assert_reserved_typo(self, source, misspelled, expected):
        result = self.compiler.analyze_full_text(source)
        typo_errors = [e for e in result.errors if e.code == 'SYN_RESERVED_WORD_TYPO']
        self.assertEqual(len(typo_errors), 1, [(e.code, e.line, e.column, e.description) for e in result.errors])
        self.assertIn(f'«{misspelled}»', typo_errors[0].description)
        self.assertIn(f'«{expected}»', typo_errors[0].description)
        self.assertIn(f'Reemplaza «{misspelled}» por «{expected}».', typo_errors[0].suggestion)
        self.assertEqual(typo_errors[0].error_type, 'Sintáctico')
        self.assertIsNone(result.tac)
        self.assertEqual(result.tac_text, '')
        return result

    def test_for_sin_condicion_con_incremento(self):
        ir = self.compile(self.fixture('01_for_sin_condicion.cps'))
        begin = next(n for n,i in enumerate(ir) if i.opcode=='LABEL' and i.args[0].startswith('for'))
        conditionals = [n for n,i in enumerate(ir) if i.opcode=='IF_FALSE']
        self.assertTrue(conditionals)
        self.assertFalse(any(begin < n < begin+1 for n in conditionals))
        self.assertTrue(any(i.opcode=='BIN' and i.args[2]=='+' for i in ir))

    def test_for_solo_incremento(self):
        ir = self.compile('let i:integer=0;for(;;i=i+1){break;}')
        self.assertFalse(self.op_instructions(ir,'IF_FALSE'))
        self.assertTrue(any(i.opcode=='BIN' and i.args[2]=='+' for i in ir))

    def test_for_sin_condicion_ni_incremento(self):
        ir = self.compile('for(;;){break;}')
        self.assertFalse(self.op_instructions(ir,'IF_FALSE'))

    def test_for_solo_condicion(self):
        ir = self.compile('for(;true;){break;}')
        self.assertEqual(self.op_instructions(ir,'IF_FALSE')[0].args[0], 'true')

    def test_for_completo(self):
        ir = self.compile('for(let i:integer=0;i<3;i=i+1){print(i);}')
        self.assertEqual(len(self.op_instructions(ir,'IF_FALSE')),1)
        self.assertTrue(any(i.opcode=='BIN' and i.args[2]=='+' for i in ir))

    def test_for_inicializador_asignacion(self):
        ir = self.compile('let i:integer=0;for(i=1;i<3;i=i+1){print(i);}')
        self.assertTrue(any(i.opcode=='MOVE' and i.args==('i@s0','1') for i in ir))

    def test_condicion_for_rechaza_no_boolean(self):
        bad = self.compiler.analyze_full_text('for(let i:integer=0;i+1;i=i+1){print(i);}')
        self.assertTrue(bad.errors)
        self.assertIsNone(bad.tac)

    def test_try_return_desinstala_manejador(self):
        ir = self.compile(self.fixture('02_return_en_try.cps'))
        indexes=[n for n,i in enumerate(ir) if i.opcode=='RETURN' and i.args==('1',)]
        self.assertEqual(len(indexes),1)
        self.assertEqual(ir[indexes[0]-1].opcode,'END_TRY')

    def test_try_break_desinstala_manejador(self):
        ir = self.compile(self.fixture('03_break_en_try.cps'))
        jumps=[n for n,i in enumerate(ir) if i.opcode=='GOTO' and i.args[0].startswith('endwhile')]
        self.assertEqual(len(jumps),1)
        self.assertEqual(ir[jumps[0]-1].opcode, 'END_TRY')

    def test_try_continue_desinstala_manejador(self):
        ir = self.compile(self.fixture('04_continue_en_try.cps'))
        jumps=[n for n,i in enumerate(ir) if i.opcode=='GOTO' and i.args[0].startswith('while')]
        self.assertTrue(any(ir[j-1].opcode=='END_TRY' for j in jumps))

    def test_try_anidado_dos_manejadores(self):
        ir = self.compile(self.fixture('05_try_anidados.cps'))
        target=next(n for n,i in enumerate(ir) if i.opcode=='GOTO' and i.args[0].startswith('endwhile'))
        self.assertEqual([i.opcode for i in ir[target-2:target]],['END_TRY','END_TRY'])

    def test_try_ciclo_interno_conserva_manejador(self):
        ir = self.compile('try{while(true){break;}print(1);}catch(e){print(e);}')
        target=next(n for n,i in enumerate(ir) if i.opcode=='GOTO' and i.args[0].startswith('endwhile'))
        self.assertNotEqual(ir[target-1].opcode,'END_TRY')
        self.assertEqual(len(self.op_instructions(ir,'TRY')),1)

    def test_try_switch_break_interno_conserva_manejador(self):
        ir = self.compile('let x:integer=1;try{switch(x){case 1:break;default:print(0);}}catch(e){print(e);}')
        target=next(n for n,i in enumerate(ir) if i.opcode=='GOTO' and i.args[0].startswith('endswitch'))
        self.assertNotEqual(ir[target-1].opcode,'END_TRY')

    def test_try_break_desde_switch_desinstala(self):
        ir = self.compile('let x:integer=1;switch(x){case 1:try{break;}catch(e){print(e);}default:print(0);}')
        target=next(n for n,i in enumerate(ir) if i.opcode=='GOTO' and i.args[0].startswith('endswitch'))
        self.assertEqual(ir[target-1].opcode,'END_TRY')

    def test_binario_snapshot_si_rhs_muta_variable(self):
        ir=self.compile(self.fixture('06_expresion_con_mutacion.cps'))
        assignment=next(n for n,i in enumerate(ir) if i.opcode=='MOVE' and i.args==('a@s0','3'))
        snapshot=next(i for i in ir[:assignment] if i.opcode=='MOVE' and i.args[1]=='a@s0')
        addition=next(i for i in ir if i.opcode=='BIN' and i.args[2]=='+')
        self.assertEqual(addition.args[1],snapshot.args[0])
        self.assertNotEqual(addition.args[1],'a@s0')

    def test_binario_comparacion_con_funcion_mutadora(self):
        ir=self.compile('let a:integer=1;function mutate():integer{a=5;return 2;}let x:boolean=a<mutate();')
        copy=next(i for i in ir if i.opcode=='MOVE' and i.args[1]=='a@s0')
        compare=next(i for i in ir if i.opcode=='BIN' and i.args[2]=='<')
        self.assertEqual(compare.args[1],copy.args[0])

    def test_orden_argumentos_y_snapshot(self):
        ir=self.compile(self.fixture('07_argumentos_efectos.cps'))
        first=next(i for i in ir if i.opcode=='MOVE' and i.args[1]=='a@s0')
        params=self.op_instructions(ir,'PARAM')
        self.assertEqual([p.args[0] for p in params], [first.args[0],'3'])

    def test_arreglo_preserva_referencia_antes_de_indice(self):
        ir=self.compile(self.fixture('09_indice_con_efectos.cps'))
        snap=next(i for i in ir if i.opcode=='MOVE' and i.args[1]=='a@s0')
        get=next(i for i in ir if i.opcode=='ARRAY_GET')
        self.assertEqual(get.args[1],snap.args[0])

    def test_metodo_preserva_receptor_antes_argumentos(self):
        ir=self.compile(self.fixture('08_receptor_efectos.cps'))
        snap=next(i for i in ir if i.opcode=='MOVE' and i.args[1]=='a@s0')
        method=next(i for i in ir if i.opcode=='CALL_METHOD' and i.args[1].endswith('.get'))
        self.assertEqual(method.args[1],snap.args[0]+'.get')

    def test_arreglo_argumentos_con_efecto_lateral(self):
        ir=self.compile('let x:integer=1;function h(v:integer):integer{return v;}let a:integer[]=[x,x=5,h(x)];')
        arr=self.op_instructions(ir,'ARRAY_SET')
        # The first element must be written before the later assignment, so no snapshot needed.
        first=next(n for n,i in enumerate(ir) if i is arr[0]);mutate=next(n for n,i in enumerate(ir) if i.opcode=='MOVE' and i.args==('x@s0','5'))
        self.assertLess(first,mutate)

    def test_constructor_argumentos_antes_de_campos(self):
        source = self.fixture('11_constructor_orden.cps')
        ir=self.compile(source)
        call=next(n for n,i in enumerate(ir) if i.opcode=='CALL' and i.args[1].startswith('change@s'))
        allocate=next(n for n,i in enumerate(ir) if i.opcode=='NEW')
        fields=next(n for n,i in enumerate(ir) if i.opcode=='INIT_FIELDS')
        constructor=next(n for n,i in enumerate(ir) if i.opcode=='CALL_METHOD' and i.args[1].endswith('.constructor'))
        self.assertLess(call,allocate)
        self.assertLess(allocate,fields)
        self.assertLess(fields,constructor)

    def test_arreglo_indice_antes_rhs_mutador(self):
        ir=self.compile('let i:integer=0;let a:integer[]=[1];a[i]=(i=3);')
        snapshot=next(i for i in ir if i.opcode=='MOVE' and i.args[1]=='i@s0')
        store=next(i for i in ir if i.opcode=='ARRAY_SET' and i.args[2]=='3')
        self.assertEqual(store.args[1],snapshot.args[0])

    def test_propiedad_receptor_antes_rhs_mutador(self):
        ir=self.compile('class A{let x:integer;}let a:A=new A();function reset():integer{a=new A();return 3;}a.x=reset();')
        snapshot=next(i for i in ir if i.opcode=='MOVE' and i.args[1]=='a@s0')
        setter=next(i for i in ir if i.opcode=='SET_FIELD' and i.args[1]=='x')
        self.assertEqual(setter.args[0],snapshot.args[0])

    def test_errores_impiden_tac(self):
        for source in ('let x:integer=;','let x:integer=1; x="no";', 'let x:integer=1; @ let y:integer=2;', 'let x:integer=1; x = false; let y:integer = "a";'):
            with self.subTest(source=source):
                result=self.compiler.analyze_full_text(source)
                self.assertTrue(result.errors)
                self.assertIsNone(result.tac)
                self.assertEqual(result.tac_text, '')

    def test_errores_multiple_no_se_repiten(self):
        result=self.compiler.analyze_full_text(self.fixture('10_errores_multiples.cps'))
        self.assertGreaterEqual(len(result.errors), 3)
        keys=[(e.error_type,e.line,e.column,e.code,e.description) for e in result.errors]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertIsNone(result.tac)

    def test_typo_new_reporta_ne_en_lugar_del_token_siguiente(self):
        result = self.assert_reserved_typo('class Perro {}\nlet perro: Perro = ne Perro();', 'ne', 'new')
        self.assertEqual(result.errors[0].line, 2)
        self.assertEqual(result.errors[0].symbol, '«ne»')

    def test_typos_de_palabras_reservadas_contextuales(self):
        cases = [
            ('class Perro {}\nlet perro: Perro = nwe Perro();', 'nwe', 'new'),
            ('functio f():integer { return 1; }', 'functio', 'function'),
            ('whil (true) { break; }', 'whil', 'while'),
            ('let xs: integer[] = [1]; foreac (x in xs) { print(x); }', 'foreac', 'foreach'),
            ('function f():integer { retun 1; }', 'retun', 'return'),
            ('clas A {}', 'clas', 'class'),
        ]
        for source, misspelled, expected in cases:
            with self.subTest(misspelled=misspelled, expected=expected):
                self.assert_reserved_typo(source, misspelled, expected)

    def test_identificadores_parecidos_no_generan_falsos_positivos(self):
        sources = [
            'let ne: integer = 1;',
            'let news: integer = 1;',
            'let next: integer = 1;',
            'let format: string = "hola";',
        ]
        for source in sources:
            with self.subTest(source=source):
                result = self.compiler.analyze_full_text(source)
                self.assertFalse([e for e in result.errors if e.code == 'SYN_RESERVED_WORD_TYPO'])
                self.assertFalse(result.errors, [(e.code, e.description) for e in result.errors])
                self.assertIsNotNone(result.tac)

    def test_tac_determinista_para_misma_entrada(self):
        source = 'function f(a:integer,b:integer):integer{return a+b;} let x:integer=f(1,2);'
        first = self.compile_result(source).tac.render(numbered=True)
        second = self.compile_result(source).tac.render(numbered=True)
        self.assertEqual(first, second)

    def test_variables_constantes_y_aritmetica_opcodes_argumentos(self):
        ir = self.compile('const c:integer=2;let x:integer=3;let y:integer=x+c*4;print(y);')
        self.assertEqual([i.opcode for i in ir[:2]], ['LABEL', 'MOVE'])
        self.assertIn(('c@s0', '2'), [i.args for i in self.op_instructions(ir, 'MOVE')])
        self.assertTrue(any(i.opcode == 'BIN' and i.args[2] == '*' and i.args[3] == '4' for i in ir))
        self.assertTrue(any(i.opcode == 'BIN' and i.args[2] == '+' for i in ir))
        self.assertEqual(self.op_instructions(ir, 'PRINT')[-1].args, ('y@s0',))

    def test_if_else_while_do_for_foreach_switch_estructura(self):
        source = (
            'let xs:integer[]=[1,2];let acc:integer=0;'
            'if(true){acc=1;}else{acc=2;}'
            'while(acc<3){acc=acc+1;continue;}'
            'do{acc=acc-1;}while(acc>0);'
            'for(let i:integer=0;i<2;i=i+1){acc=acc+i;}'
            'foreach(v in xs){switch(v){case 1:break;default:acc=acc+v;}}'
        )
        ir = self.compile(source)
        labels = [i.args[0] for i in ir if i.opcode == 'LABEL']
        for prefix in ('else', 'while', 'endwhile', 'do', 'docond', 'enddo', 'for', 'forstep', 'endfor', 'foreach', 'foreachstep', 'endforeach', 'case', 'default', 'endswitch'):
            self.assertTrue(any(label.startswith(prefix) for label in labels), prefix)
        self.assertTrue(any(i.opcode == 'ARRAY_LEN' for i in ir))
        self.assertTrue(any(i.opcode == 'ARRAY_GET' for i in ir))
        self.assertTrue(any(i.opcode == 'IF_TRUE' for i in ir))
        self.assertTrue(any(i.opcode == 'IF_FALSE' for i in ir))

    def test_logica_cortocircuito_and_or(self):
        ir = self.compile('let a:boolean=false;let b:boolean=true;let c:boolean=a&&b||true;')
        jumps = [i for i in ir if i.opcode in {'IF_FALSE', 'IF_TRUE'}]
        self.assertEqual([i.opcode for i in jumps], ['IF_FALSE', 'IF_TRUE'])
        self.assertTrue(jumps[0].args[1].startswith('shortcircuit'))
        self.assertTrue(jumps[1].args[1].startswith('shortcircuit'))
        first_jump = next(n for n, i in enumerate(ir) if i is jumps[0])
        first_label = next(n for n, i in enumerate(ir) if i.opcode == 'LABEL' and i.args[0] == jumps[0].args[1])
        self.assertLess(first_jump, first_label)

    def test_parametros_antes_de_call_y_argumentos_en_orden(self):
        ir = self.compile('function f(a:integer,b:integer):integer{return a-b;} let x:integer=f(1,2);')
        call_index = next(n for n, i in enumerate(ir) if i.opcode == 'CALL' and i.args[1] == 'f@s0')
        params = [i for i in ir[:call_index] if i.opcode == 'PARAM']
        self.assertEqual([p.args[0] for p in params], ['1', '2'])
        self.assertEqual(ir[call_index].args, ('t0', 'f@s0', '2'))

    def test_recursividad_usa_misma_etiqueta_de_funcion(self):
        ir = self.compile('function fact(n:integer):integer{if(n<=1){return 1;}else{return n*fact(n-1);}} let x:integer=fact(3);')
        func = next(i for i in ir if i.opcode == 'FUNC' and i.args[0].startswith('fact@s'))
        calls = [i for i in ir if i.opcode == 'CALL' and i.args[1] == func.args[0]]
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(n > self.op_indexes(ir, 'FUNC')[0] for n, i in enumerate(ir) if i in calls))

    def test_clases_objetos_constructor_this_y_herencia(self):
        result = self.compile_result(
            'class A{let x:integer;function constructor(x:integer){this.x=x;}function get():integer{return this.x;}}'
            'class B:A{let y:integer;function getY():integer{return this.y;}}'
            'let b:B=new B(4);let x:integer=b.get();let y:integer=b.getY();'
        )
        ir = result.tac.instructions
        self.assertTrue(any(i.opcode == 'CLASS' and i.args == ('A', '') for i in ir))
        self.assertTrue(any(i.opcode == 'CLASS' and i.args == ('B', 'A') for i in ir))
        self.assertTrue(any(i.opcode == 'NEW' and i.args[1] == 'B' for i in ir))
        self.assertTrue(any(i.opcode == 'INIT_FIELDS' and i.args[1] == 'B' for i in ir))
        self.assertTrue(any(i.opcode == 'CALL_METHOD' and i.args[1].endswith('.constructor') for i in ir))
        self.assertTrue(any(i.opcode == 'MOVE' and i.args == ('t0', 'this') for i in ir))
        self.assertTrue(any(i.opcode == 'SET_FIELD' and i.args[1:] == ('x', 'x@s2') for i in ir))
        self.assertTrue(any(i.opcode == 'GET_FIELD' and i.args[1] == 'this' and i.args[2] == 'x' for i in ir))
        rows = result.symbol_table.rows()
        inherited = next(r for r in rows if r['name'] == 'x' and r['scope'] == 'class_A')
        child = next(r for r in rows if r['name'] == 'y' and r['scope'] == 'class_B')
        self.assertEqual((inherited['storage_class'], inherited['offset']), ('field', 0))
        self.assertEqual((child['storage_class'], child['offset']), ('field', 8))

    def test_try_catch_push_pop_balance_y_orden(self):
        ir = self.compile('try{print(1);}catch(e){print(e);}')
        self.assertEqual([i.opcode for i in ir if i.opcode in {'TRY', 'END_TRY', 'CATCH'}], ['TRY', 'END_TRY', 'CATCH'])
        try_index = self.op_indexes(ir, 'TRY')[0]
        pop_index = self.op_indexes(ir, 'END_TRY')[0]
        catch_index = self.op_indexes(ir, 'CATCH')[0]
        self.assertLess(try_index, pop_index)
        self.assertLess(pop_index, catch_index)
        self.assertEqual(len(self.op_instructions(ir, 'TRY')), len(self.op_instructions(ir, 'END_TRY')))

    def test_tabla_simbolos_sombreado_offsets_y_frames(self):
        result = self.compile_result('function f(a:integer):integer{let x:integer=a+1;{let x:integer=2;print(x);}return x;}let x:integer=f(3);')
        rows = result.symbol_table.rows()
        param = next(r for r in rows if r['name'] == 'a' and r['kind'] == 'parameter')
        locals_x = [r for r in rows if r['name'] == 'x' and r['storage_class'] == 'local']
        global_x = next(r for r in rows if r['name'] == 'x' and r['storage_class'] == 'global')
        self.assertEqual(param['storage_class'], 'parameter')
        self.assertGreaterEqual(param['offset'], 16)
        self.assertEqual(len(locals_x), 2)
        self.assertEqual(len({r['tac_name'] for r in locals_x + [global_x]}), 3)
        self.assertTrue(all(r['offset'] < 0 for r in locals_x))
        self.assertNotEqual(locals_x[0]['offset'], locals_x[1]['offset'])
        self.assertEqual({r['frame_name'] for r in locals_x}, {param['frame_name']})

    def test_temporales_reutilizados_y_usos_definidos(self):
        result = self.compile_result('let a:integer=1;let b:integer=2;let c:integer=3;let d:integer=(a+b)*(b+c)-(a+c);')
        ir = result.tac.instructions
        self.assertGreaterEqual(result.tac.reused_temporaries, 1)
        self.assertLess(result.tac.allocated_temporaries, 4)
        defined = set()
        for inst in ir:
            for temp in self.temp_uses(inst):
                self.assertIn(temp, defined, f'{temp} usado antes de definirse en {inst}')
            target = self.temp_def(inst)
            if target:
                defined.add(target)
        self.assertTrue(any(i.opcode == 'BIN' and i.args[0] == i.args[1] for i in ir), 'no hay reutilizacion in-place')

    def test_no_sobrescribe_temporal_antes_del_ultimo_uso_observable(self):
        ir = self.compile('let a:integer=1;let b:integer=2;let c:integer=3;let d:integer=(a+b)*(b+c)-(a+c);')
        definitions = {}
        uses = {}
        for index, inst in enumerate(ir):
            for temp in self.temp_uses(inst):
                uses.setdefault(temp, []).append(index)
            target = self.temp_def(inst)
            if target:
                definitions.setdefault(target, []).append(index)
        for temp, defs in definitions.items():
            for left, right in zip(defs, defs[1:]):
                later_uses = [use for use in uses.get(temp, []) if left < use < right]
                self.assertTrue(later_uses or any(ir[left].opcode == op for op in {'MOVE', 'BIN', 'CALL', 'NEW_ARRAY', 'ARRAY_GET', 'ARRAY_LEN', 'NEW', 'GET_FIELD'}))

    def test_invalidos_no_generan_tac(self):
        cases = [
            'const c:integer;',
            'let x:integer=1.5;',
            'break;',
            'function f(a:integer):integer{return true;}',
            'class A{} let a:A=new B();',
        ]
        for source in cases:
            with self.subTest(source=source):
                result = self.compiler.analyze_full_text(source)
                self.assertTrue(result.errors)
                self.assertIsNone(result.tac)
                self.assertEqual(result.tac_text, '')


if __name__=='__main__':
    unittest.main(verbosity=2)
