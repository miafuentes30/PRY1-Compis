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


if __name__=='__main__':
    unittest.main(verbosity=2)
