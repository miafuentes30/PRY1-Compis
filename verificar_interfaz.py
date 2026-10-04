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
            app.clear_all()
            assert not app.editor.get_content().strip()
            assert not app.tac_view.get('1.0','end').strip()
            checks += 1
        print(f'INTERFAZ REAL: {checks}/11 verificaciones superadas.')
        return 0
    finally:
        app.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
