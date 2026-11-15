"""Prueba opcional del IDE real. Requiere pantalla gráfica o xvfb-run en Linux."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from bootstrap import ensure_generated


def main():
    ensure_generated()
    from main import CompiscriptApp
    app = CompiscriptApp()
    checks = 0
    try:
        app.update_idletasks()
        assert app.font_delta >= 3
        checks += 1
        old = app.font_delta
        app.change_font(1)
        assert app.font_delta == old + 1
        app.change_font(-1)
        assert app.font_delta == old
        checks += 1
        app.toggle_dark_mode()
        assert app.dark_mode
        app.toggle_dark_mode()
        assert not app.dark_mode
        checks += 1
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'prueba.cps'
            source.write_text('let a:integer=2; let b:integer=3; print(a+b);', encoding='utf-8')
            with patch('main.filedialog.askopenfilename', return_value=str(source)):
                app.open_file()
            assert app.current_file == source
            assert 'print(a+b)' in app.editor.get_content()
            checks += 1
            app.analyze()
            assert not app.errors and app.analysis_result.tac is not None
            assert ' + ' in app.tac_view.get('1.0', 'end')
            checks += 1
            output = Path(work) / 'exportado.tac'
            with patch('main.filedialog.asksaveasfilename', return_value=str(output)):
                app.export_tac()
            assert output.is_file() and 'main:' in output.read_text(encoding='utf-8')
            checks += 1
            # Editing the editor invalidates the old analysis, including export.
            app.editor.text.insert('end', '\nlet c:integer=;')
            app.update()
            assert app.analysis_result is None
            assert not app.tac_view.get('1.0','end').strip()
            checks += 1
            stale = Path(work) / 'stale.tac'
            with patch('main.filedialog.asksaveasfilename', return_value=str(stale)), \
                    patch('main.messagebox.showwarning') as warning:
                app.export_tac()
            assert not stale.exists() and warning.called
            checks += 1
            app.analyze()
            assert app.errors and app.analysis_result.tac is None
            assert not app.tac_view.get('1.0','end').strip()
            checks += 1
            # An unexpected compiler failure must not preserve a previous TAC.
            app.editor.set_content('let x:integer=3;')
            app.analyze()
            assert not app.errors and app.analysis_result.tac is not None
            with patch.object(app.analyzer, 'analyze_full_text', side_effect=RuntimeError('test')), \
                    patch('main.messagebox.showerror') as alert:
                app.analyze()
            assert alert.called and app.analysis_result is None
            assert not app.tac_view.get('1.0', 'end').strip()
            checks += 1
            # ---------------- Proyecto 3: MIPS, ejecución y árbol de activación ----------------
            app.editor.set_content(
                'function fact(n: integer): integer { if (n <= 1) { return 1; } return n * fact(n - 1); }\n'
                'print("fact(5) = " + fact(5));\n')
            app.analyze()
            asm = app.mips_view.get('1.0', 'end')
            assert not app.errors and 'fn_fact:' in asm and 'jal    fn_fact' in asm
            assert app.mips_card.value_label.cget('text').isdigit()
            checks += 1
            app.run_program()
            for _ in range(200):
                app.update()
                if not app._running:
                    break
                app.after(20)
            console = app.console_view.get('1.0', 'end')
            assert 'fact(5) = 120' in console and 'código 0' in console
            checks += 1
            roots = app.activation_tree.get_children()
            assert len(roots) == 1
            first = app.activation_tree.get_children(roots[0])[0]
            assert app.activation_tree.item(first, 'text') == 'fact(n=5)'
            assert app.activation_tree.item(first, 'values')[0] == '120'
            checks += 1
            assert '$s0' in app.frames_view.get('1.0', 'end') and 'REGISTROS DE ACTIVACIÓN' in app.frames_view.get('1.0', 'end')
            assert 'OPTIMIZACIÓN POR MIRILLA' in app.peephole_view.get('1.0', 'end')
            checks += 1
            asm_out = Path(work) / 'programa.asm'
            with patch('main.filedialog.asksaveasfilename', return_value=str(asm_out)):
                app.export_asm()
            assert asm_out.is_file() and '.globl main' in asm_out.read_text(encoding='latin-1')
            checks += 1
            app.optimize_var.set(False)
            app._on_optimize_toggle()
            assert app.analysis_result.mips is not None and not app.analysis_result.mips.optimized
            assert 'desactivada' in app.peephole_view.get('1.0', 'end')
            app.optimize_var.set(True)
            app._on_optimize_toggle()
            checks += 1
            # Error no capturado en tiempo de ejecución: se informa en la consola.
            app.editor.set_content('let a: integer[] = [1];\nprint(a[4]);\n')
            app.run_program()
            for _ in range(200):
                app.update()
                if not app._running:
                    break
                app.after(20)
            console = app.console_view.get('1.0', 'end')
            assert 'no capturado' in console and 'código 1' in console
            checks += 1
            # Un programa con errores no produce MIPS ni se ejecuta.
            app.editor.set_content('let x: integer = "a";')
            with patch('main.messagebox.showwarning') as warning:
                app.run_program()
            assert warning.called and app.analysis_result.mips is None
            assert not app.mips_view.get('1.0', 'end').strip()
            checks += 1
            app.clear_all()
            assert not app.editor.get_content().strip()
            assert not app.tac_view.get('1.0','end').strip()
            assert not app.mips_view.get('1.0','end').strip()
            checks += 1
        print(f'INTERFAZ REAL: {checks}/19 verificaciones superadas.')
        return 0
    finally:
        app.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
