from __future__ import annotations

import json
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bootstrap import ensure_generated


APP_TITLE = "Analizador Compiscript"
BG = "#F4F7FB"
SURFACE = "#FFFFFF"
NAVY = "#14213D"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
TEXT = "#172033"
MUTED = "#64748B"
BORDER = "#D9E2EF"
SUCCESS = "#15803D"
SUCCESS_BG = "#DCFCE7"
DANGER = "#B42318"
DANGER_BG = "#FEE4E2"
WARNING = "#B54708"
WARNING_BG = "#FEF0C7"
EDITOR_BG = "#0F172A"
EDITOR_FG = "#E2E8F0"

# Paleta del modo oscuro. El editor de código ya utiliza una superficie oscura
# en ambos modos para mantener buen contraste del resaltado sintáctico.
DARK_BG = "#0B1220"
DARK_SURFACE = "#111827"
DARK_NAVY = "#0F172A"
DARK_TEXT = "#E5E7EB"
DARK_MUTED = "#94A3B8"
DARK_BORDER = "#334155"
DARK_DETAIL = "#172033"
DARK_HEADING = "#1E293B"
DARK_HOVER = "#253247"
DARK_BLUE_TEXT = "#60A5FA"


def _show_startup_error(error: Exception) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("No se pudo iniciar el Analizador Compiscript", str(error), parent=root)
        root.destroy()
    except Exception:
        print(f"ERROR: {error}", file=sys.stderr)


try:
    ensure_generated()
except Exception as exc:
    _show_startup_error(exc)
    raise SystemExit(1)

from analyzer import CompiscriptAnalyzer  # noqa: E402
from error_listener import AnalysisError  # noqa: E402
from parse_tree_utils import node_label  # noqa: E402


class CodeEditor(ttk.Frame):
    """Editor con números de línea, resaltado básico y navegación a errores."""

    KEYWORDS = {
        "let", "var", "const", "function", "class", "if", "else", "while", "do",
        "for", "foreach", "in", "try", "catch", "switch", "case", "default", "break",
        "continue", "return", "print", "new", "this", "null", "true", "false",
        "boolean", "integer", "string",
    }

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._highlight_job: str | None = None

        self.line_numbers = tk.Canvas(
            self,
            width=52,
            bg="#111C30",
            highlightthickness=0,
            bd=0,
        )
        self.text = tk.Text(
            self,
            wrap="none",
            undo=True,
            maxundo=-1,
            autoseparators=True,
            font=("Cascadia Code", 11),
            bg=EDITOR_BG,
            fg=EDITOR_FG,
            insertbackground="#F8FAFC",
            selectbackground="#334155",
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=12,
            tabs=(32,),
        )
        self.v_scroll = ttk.Scrollbar(self, orient="vertical", command=self._on_scrollbar)
        self.h_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)

        self.text.configure(
            yscrollcommand=self._on_text_scroll,
            xscrollcommand=self.h_scroll.set,
        )
        self.line_numbers.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.v_scroll.grid(row=0, column=2, sticky="ns")
        self.h_scroll.grid(row=1, column=1, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.text.tag_configure("current_line", background="#172554")
        self.text.tag_configure("keyword", foreground="#93C5FD")
        self.text.tag_configure("string", foreground="#86EFAC")
        self.text.tag_configure("number", foreground="#FDE68A")
        self.text.tag_configure("comment", foreground="#94A3B8")
        self.text.tag_configure("boolean", foreground="#C4B5FD")
        self.text.tag_configure("lexical_error", background="#4C1D1D", underline=True)
        self.text.tag_configure("syntactic_error", background="#4A2C0A", underline=True)
        self.text.tag_configure("semantic_error", background="#3B255F", underline=True)

        for event in ("<KeyRelease>", "<ButtonRelease-1>", "<MouseWheel>", "<Configure>"):
            self.text.bind(event, self._on_change, add="+")
        self.text.bind("<<Modified>>", self._on_modified, add="+")
        self.text.bind("<Tab>", self._insert_spaces)
        self.after_idle(self._redraw_line_numbers)

    def _insert_spaces(self, _event: tk.Event) -> str:
        self.text.insert("insert", "  ")
        return "break"

    def _on_modified(self, _event: tk.Event) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._schedule_highlight()
            self._redraw_line_numbers()

    def _on_change(self, _event: tk.Event | None = None) -> None:
        self._highlight_current_line()
        self._redraw_line_numbers()

    def _on_scrollbar(self, *args: str) -> None:
        self.text.yview(*args)
        self._redraw_line_numbers()

    def _on_text_scroll(self, first: str, last: str) -> None:
        self.v_scroll.set(first, last)
        self._redraw_line_numbers()

    def _redraw_line_numbers(self) -> None:
        self.line_numbers.delete("all")
        index = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(index)
            if info is None:
                break
            y = info[1]
            line = index.split(".")[0]
            self.line_numbers.create_text(
                43,
                y,
                anchor="ne",
                text=line,
                fill="#7C8AA5",
                font=("Cascadia Code", 10),
            )
            index = self.text.index(f"{index}+1line")

    def _highlight_current_line(self) -> None:
        self.text.tag_remove("current_line", "1.0", "end")
        line = self.text.index("insert").split(".")[0]
        self.text.tag_add("current_line", f"{line}.0", f"{line}.0 lineend+1c")
        self.text.tag_lower("current_line")

    def _schedule_highlight(self) -> None:
        if self._highlight_job:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(180, self.highlight_syntax)

    def highlight_syntax(self) -> None:
        self._highlight_job = None
        content = self.get_content()
        for tag in ("keyword", "string", "number", "comment", "boolean"):
            self.text.tag_remove(tag, "1.0", "end")

        patterns = [
            ("comment", r"//[^\n]*|/\*.*?\*/", re.DOTALL),
            ("string", r'"(?:\\.|[^"\\\r\n])*"', 0),
            ("number", r"\b\d+\b", 0),
            ("boolean", r"\b(?:true|false|null)\b", 0),
            ("keyword", r"\b(?:" + "|".join(sorted(self.KEYWORDS - {"true", "false", "null"})) + r")\b", 0),
        ]
        blocked: list[tuple[int, int]] = []
        for tag, pattern, flags in patterns:
            for match in re.finditer(pattern, content, flags):
                start, end = match.span()
                if tag not in ("comment", "string") and any(a <= start < b for a, b in blocked):
                    continue
                self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
                if tag in ("comment", "string"):
                    blocked.append((start, end))
        self._highlight_current_line()

    def set_content(self, content: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.highlight_syntax()
        self._redraw_line_numbers()

    def get_content(self) -> str:
        return self.text.get("1.0", "end-1c")

    def goto(self, line: int, column: int = 0) -> None:
        index = f"{max(1, line)}.{max(0, column)}"
        self.text.mark_set("insert", index)
        self.text.see(index)
        self.text.focus_set()
        self._highlight_current_line()

    def show_error_lines(self, errors: list[AnalysisError]) -> None:
        for tag in ("lexical_error", "syntactic_error", "semantic_error"):
            self.text.tag_remove(tag, "1.0", "end")
        for error in errors:
            tag = {"Léxico": "lexical_error", "Sintáctico": "syntactic_error", "Semántico": "semantic_error"}.get(error.error_type)
            if tag is None:
                continue
            editor_column = max(0, error.column - 1)
            start = f"{error.line}.{editor_column}"
            end = f"{error.line}.{editor_column + max(1, len(error.symbol.strip('«»')))}"
            try:
                self.text.tag_add(tag, start, end)
            except tk.TclError:
                self.text.tag_add(tag, f"{error.line}.0", f"{error.line}.0 lineend")


class StatCard(tk.Frame):
    def __init__(self, master: tk.Misc, title: str, value: str, accent: str) -> None:
        super().__init__(master, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        self.configure(height=74)
        stripe = tk.Frame(self, bg=accent, width=5)
        stripe.pack(side="left", fill="y")
        body = tk.Frame(self, bg=SURFACE)
        body.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        tk.Label(body, text=title, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self.value_label = tk.Label(body, text=value, bg=SURFACE, fg=TEXT, font=("Segoe UI", 18, "bold"))
        self.value_label.pack(anchor="w")

    def set_value(self, value: str) -> None:
        self.value_label.configure(text=value)


class CompiscriptApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} · Proyecto 01")
        self.geometry("1320x820")
        self.minsize(1050, 680)
        self.configure(bg=BG)

        self.analyzer = CompiscriptAnalyzer()
        self.current_file: Path | None = None
        self.errors: list[AnalysisError] = []
        self.analysis_result = None
        self.item_to_error: dict[str, AnalysisError] = {}
        self.dark_mode = False
        # Conserva los colores originales de widgets tk para poder alternar
        # entre modo claro y oscuro sin reconstruir la interfaz.
        self._light_widget_options: dict[str, dict[str, str]] = {}

        self._configure_styles()
        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        if self.dark_mode:
            bg, surface, text, muted, border = DARK_BG, DARK_SURFACE, DARK_TEXT, DARK_MUTED, DARK_BORDER
            heading_bg, hover_bg = DARK_HEADING, DARK_HOVER
            selected_bg, selected_fg = PRIMARY_DARK, "#FFFFFF"
        else:
            bg, surface, text, muted, border = BG, SURFACE, TEXT, MUTED, BORDER
            heading_bg, hover_bg = "#EEF3F9", "#EEF2F7"
            selected_bg, selected_fg = "#DCEAFE", "#173B73"

        style.configure("App.TFrame", background=bg)
        style.configure("Surface.TFrame", background=surface)
        style.configure("Toolbar.TFrame", background=surface)
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Surface.TLabel", background=surface, foreground=text, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=surface, foreground=text, font=("Segoe UI", 11, "bold"))
        style.configure(
            "Primary.TButton",
            background=PRIMARY,
            foreground="white",
            borderwidth=0,
            focuscolor="none",
            padding=(16, 9),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Primary.TButton", background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_DARK)])
        style.configure(
            "Secondary.TButton",
            background=surface,
            foreground=text,
            bordercolor=border,
            borderwidth=1,
            focuscolor="none",
            padding=(13, 8),
            font=("Segoe UI", 10),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", hover_bg), ("pressed", hover_bg)],
            foreground=[("disabled", muted)],
        )
        style.configure(
            "Treeview",
            background=surface,
            fieldbackground=surface,
            foreground=text,
            rowheight=31,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background=heading_bg,
            foreground=text if self.dark_mode else "#344054",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padding=(8, 8),
        )
        style.map("Treeview", background=[("selected", selected_bg)], foreground=[("selected", selected_fg)])
        style.configure(
            "TCombobox",
            padding=6,
            fieldbackground=surface,
            background=surface,
            foreground=text,
            arrowcolor=text,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", surface)],
            foreground=[("readonly", text)],
            selectbackground=[("readonly", surface)],
            selectforeground=[("readonly", text)],
        )
        style.configure("TPanedwindow", background=bg)

    def _build_ui(self) -> None:
        self._build_header()
        self._build_toolbar()
        self._build_stats()
        self._build_workspace()
        self._build_statusbar()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=NAVY, height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        inner = tk.Frame(header, bg=NAVY)
        inner.pack(fill="both", expand=True, padx=26, pady=17)

        title_box = tk.Frame(inner, bg=NAVY)
        title_box.pack(side="left", fill="y")
        tk.Label(
            title_box,
            text=APP_TITLE,
            bg=NAVY,
            fg="white",
            font=("Segoe UI", 21, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="IDE con análisis léxico, sintáctico y semántico para archivos .cps",
            bg=NAVY,
            fg="#B8C6DC",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 0))

        badge = tk.Label(
            inner,
            text="ANTLR4 · Visitor semántico · tabla de símbolos",
            bg="#203354",
            fg="#DCE7F8",
            font=("Segoe UI", 9, "bold"),
            padx=13,
            pady=7,
        )
        badge.pack(side="right", anchor="n", pady=7)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        bar.pack(fill="x", padx=22, pady=(16, 10))
        buttons = ttk.Frame(bar, style="Toolbar.TFrame", padding=(13, 10))
        buttons.pack(side="left")
        ttk.Button(buttons, text="Abrir archivo .cps", command=self.open_file, style="Secondary.TButton").pack(side="left")
        ttk.Button(buttons, text="Guardar", command=self.save_file, style="Secondary.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Guardar como", command=self.save_as, style="Secondary.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Analizar  F5", command=self.analyze, style="Primary.TButton").pack(side="left", padx=(14, 0))
        ttk.Button(buttons, text="Limpiar", command=self.clear_all, style="Secondary.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Pruebas semánticas", command=self.open_rubric_tests, style="Secondary.TButton").pack(side="left", padx=(8, 0))
        self.theme_button = ttk.Button(
            buttons, text="Modo oscuro", command=self.toggle_dark_mode, style="Secondary.TButton"
        )
        self.theme_button.pack(side="left", padx=(8, 0))

        file_box = tk.Frame(bar, bg=SURFACE)
        file_box.pack(side="right", fill="y", padx=16, pady=10)
        tk.Label(file_box, text="ARCHIVO ACTUAL", bg=SURFACE, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="e")
        self.file_label = tk.Label(
            file_box,
            text="Sin archivo seleccionado",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 9),
            width=46,
            anchor="e",
        )
        self.file_label.pack(anchor="e", pady=(2, 0))

    def _build_stats(self) -> None:
        stats = tk.Frame(self, bg=BG)
        stats.pack(fill="x", padx=22, pady=(0, 10))
        for index in range(4):
            stats.columnconfigure(index, weight=1, uniform="stats")

        self.total_card = StatCard(stats, "Resultado", "Sin analizar", PRIMARY)
        self.lexical_card = StatCard(stats, "Errores léxicos", "0", DANGER)
        self.syntactic_card = StatCard(stats, "Errores sintácticos", "0", WARNING)
        self.semantic_card = StatCard(stats, "Errores semánticos", "0", "#7C3AED")
        self.total_card.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.lexical_card.grid(row=0, column=1, sticky="ew", padx=6)
        self.syntactic_card.grid(row=0, column=2, sticky="ew", padx=6)
        self.semantic_card.grid(row=0, column=3, sticky="ew", padx=(6, 0))

    def _build_workspace(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=22, pady=(0, 12))

        editor_panel = tk.Frame(paned, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        editor_header = tk.Frame(editor_panel, bg=SURFACE)
        editor_header.pack(fill="x", padx=15, pady=(12, 9))
        tk.Label(editor_header, text="Código fuente", bg=SURFACE, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(
            editor_header,
            text="Ctrl+O abrir · Ctrl+S guardar · F5 analizar",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="right")
        self.editor = CodeEditor(editor_panel)
        self.editor.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        results_panel = tk.Frame(paned, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        self.notebook = ttk.Notebook(results_panel)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # ---------------- Diagnósticos ----------------
        diagnostics_tab = tk.Frame(self.notebook, bg=SURFACE)
        self.notebook.add(diagnostics_tab, text="Diagnósticos")
        results_header = tk.Frame(diagnostics_tab, bg=SURFACE)
        results_header.pack(fill="x", padx=5, pady=(4, 9))
        tk.Label(results_header, text="Resultados del análisis", bg=SURFACE, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(results_header, text="Mostrar:", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 6))
        self.filter_var = tk.StringVar(value="Todos")
        filter_combo = ttk.Combobox(
            results_header,
            textvariable=self.filter_var,
            values=("Todos", "Léxicos", "Sintácticos", "Semánticos"),
            state="readonly",
            width=14,
        )
        filter_combo.pack(side="left")
        filter_combo.bind("<<ComboboxSelected>>", lambda _event: self._populate_results())
        self.visible_count = tk.Label(results_header, text="0 resultados", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9))
        self.visible_count.pack(side="right")

        table_box = tk.Frame(diagnostics_tab, bg=SURFACE)
        table_box.pack(fill="both", expand=True, padx=5)
        columns = ("tipo", "codigo", "linea", "columna", "simbolo", "descripcion")
        self.results = ttk.Treeview(table_box, columns=columns, show="headings", selectmode="browse")
        headings = {
            "tipo": "Tipo", "codigo": "Regla", "linea": "Línea", "columna": "Col.",
            "simbolo": "Símbolo", "descripcion": "Descripción",
        }
        widths = {"tipo": 84, "codigo": 145, "linea": 50, "columna": 45, "simbolo": 100, "descripcion": 340}
        anchors = {"tipo": "center", "codigo": "w", "linea": "center", "columna": "center", "simbolo": "w", "descripcion": "w"}
        for column in columns:
            self.results.heading(column, text=headings[column])
            self.results.column(column, width=widths[column], minwidth=40, anchor=anchors[column])
        self.results.tag_configure("lexical", background="#FFF3F2")
        self.results.tag_configure("syntactic", background="#FFFAEB")
        self.results.tag_configure("semantic", background="#F5F3FF")
        y_scroll = ttk.Scrollbar(table_box, orient="vertical", command=self.results.yview)
        x_scroll = ttk.Scrollbar(table_box, orient="horizontal", command=self.results.xview)
        self.results.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.results.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        self.results.bind("<<TreeviewSelect>>", self._show_selected_error)
        self.results.bind("<Double-1>", self._jump_to_selected_error)

        detail = tk.Frame(diagnostics_tab, bg="#F8FAFC", highlightbackground=BORDER, highlightthickness=1)
        detail.pack(fill="x", padx=5, pady=(10, 3))
        self.detail_title = tk.Label(detail, text="Selecciona un diagnóstico para ver los detalles", bg="#F8FAFC", fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w")
        self.detail_title.pack(fill="x", padx=12, pady=(9, 3))
        self.detail_description = tk.Label(detail, text="El diagnóstico incluirá una explicación, una sugerencia y la línea donde ocurrió el problema.", bg="#F8FAFC", fg=MUTED, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=630)
        self.detail_description.pack(fill="x", padx=12, pady=(0, 5))
        self.detail_suggestion = tk.Label(detail, text="", bg="#F8FAFC", fg=PRIMARY_DARK, font=("Segoe UI", 9, "bold"), justify="left", anchor="w", wraplength=630)
        self.detail_suggestion.pack(fill="x", padx=12)
        self.detail_excerpt = tk.Text(detail, height=3, bg="#111827", fg="#D1D5DB", font=("Cascadia Code", 9), relief="flat", borderwidth=0, padx=9, pady=7, wrap="none")
        self.detail_excerpt.pack(fill="x", padx=12, pady=(7, 10))
        self.detail_excerpt.configure(state="disabled")

        # ---------------- Tabla de símbolos ----------------
        symbols_tab = tk.Frame(self.notebook, bg=SURFACE)
        self.notebook.add(symbols_tab, text="Tabla de símbolos")
        symbols_header = tk.Frame(symbols_tab, bg=SURFACE)
        symbols_header.pack(fill="x", padx=8, pady=8)
        tk.Label(symbols_header, text="Símbolos por alcance", bg=SURFACE, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        self.symbol_count = tk.Label(symbols_header, text="0 símbolos", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9))
        self.symbol_count.pack(side="right")
        symbol_box = tk.Frame(symbols_tab, bg=SURFACE)
        symbol_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        symbol_cols = ("scope", "depth", "name", "kind", "type", "signature", "mutable", "line")
        self.symbol_tree = ttk.Treeview(symbol_box, columns=symbol_cols, show="headings")
        symbol_headings = {"scope":"Ámbito", "depth":"Niv.", "name":"Nombre", "kind":"Clase", "type":"Tipo", "signature":"Firma / tipo", "mutable":"Mutable", "line":"Línea"}
        symbol_widths = {"scope":130, "depth":45, "name":120, "kind":90, "type":90, "signature":220, "mutable":65, "line":50}
        for col in symbol_cols:
            self.symbol_tree.heading(col, text=symbol_headings[col])
            self.symbol_tree.column(col, width=symbol_widths[col], anchor="center" if col in {"depth","mutable","line"} else "w")
        sy = ttk.Scrollbar(symbol_box, orient="vertical", command=self.symbol_tree.yview)
        sx = ttk.Scrollbar(symbol_box, orient="horizontal", command=self.symbol_tree.xview)
        self.symbol_tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.symbol_tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        symbol_box.rowconfigure(0, weight=1)
        symbol_box.columnconfigure(0, weight=1)

        # ---------------- Árbol sintáctico ----------------
        tree_tab = tk.Frame(self.notebook, bg=SURFACE)
        self.notebook.add(tree_tab, text="Árbol sintáctico")
        tree_header = tk.Frame(tree_tab, bg=SURFACE)
        tree_header.pack(fill="x", padx=8, pady=8)
        tk.Label(tree_header, text="Árbol generado por ANTLR", bg=SURFACE, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        self.tree_count = tk.Label(tree_header, text="0 nodos", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9))
        self.tree_count.pack(side="right")
        parse_box = tk.Frame(tree_tab, bg=SURFACE)
        parse_box.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self.parse_tree = ttk.Treeview(parse_box, columns=("pos",), show="tree headings")
        self.parse_tree.heading("#0", text="Regla / token")
        self.parse_tree.heading("pos", text="Posición")
        self.parse_tree.column("#0", width=540, anchor="w")
        self.parse_tree.column("pos", width=110, anchor="center")
        py = ttk.Scrollbar(parse_box, orient="vertical", command=self.parse_tree.yview)
        px = ttk.Scrollbar(parse_box, orient="horizontal", command=self.parse_tree.xview)
        self.parse_tree.configure(yscrollcommand=py.set, xscrollcommand=px.set)
        self.parse_tree.grid(row=0, column=0, sticky="nsew")
        py.grid(row=0, column=1, sticky="ns")
        px.grid(row=1, column=0, sticky="ew")
        parse_box.rowconfigure(0, weight=1)
        parse_box.columnconfigure(0, weight=1)

        paned.add(editor_panel, weight=3)
        paned.add(results_panel, weight=2)

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=NAVY, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status = tk.Label(
            bar,
            text="Listo para analizar un archivo Compiscript.",
            bg=NAVY,
            fg="#DCE7F8",
            font=("Segoe UI", 9),
            anchor="w",
            padx=18,
        )
        self.status.pack(side="left", fill="both", expand=True)
        self.position_label = tk.Label(
            bar,
            text="Línea 1, columna 1",
            bg=NAVY,
            fg="#9FB0CA",
            font=("Segoe UI", 9),
            padx=18,
        )
        self.position_label.pack(side="right")
        self.editor.text.bind("<KeyRelease>", self._update_cursor_position, add="+")
        self.editor.text.bind("<ButtonRelease-1>", self._update_cursor_position, add="+")

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-o>", lambda _event: self.open_file())
        self.bind_all("<Control-s>", lambda _event: self.save_file())
        self.bind_all("<Control-Shift-S>", lambda _event: self.save_as())
        self.bind_all("<Control-t>", lambda _event: self.toggle_dark_mode())
        self.bind_all("<F5>", lambda _event: self.analyze())

    @staticmethod
    def _dark_color_for(light_color: str) -> str:
        """Convierte únicamente colores de la interfaz clara a su equivalente oscuro."""
        mapping = {
            BG.upper(): DARK_BG,
            SURFACE.upper(): DARK_SURFACE,
            NAVY.upper(): DARK_NAVY,
            TEXT.upper(): DARK_TEXT,
            MUTED.upper(): DARK_MUTED,
            BORDER.upper(): DARK_BORDER,
            "#F8FAFC": DARK_DETAIL,
            "#EEF3F9": DARK_HEADING,
            "#EEF2F7": DARK_HOVER,
            "#344054": DARK_TEXT,
            "#173B73": "#DBEAFE",
            "#DCEAFE": "#1E3A5F",
            "#FFF3F2": "#3A1F24",
            "#FFFAEB": "#3A2D16",
            "#F5F3FF": "#2D2145",
            PRIMARY_DARK.upper(): DARK_BLUE_TEXT,
            "#B8C6DC": "#CBD5E1",
        }
        return mapping.get(str(light_color).upper(), light_color)

    def _apply_widget_theme(self, widget: tk.Misc, use_dark: bool) -> None:
        """Aplica el tema a widgets tk y conserva sus valores para restaurarlos."""
        key = str(widget)
        options = (
            "background", "foreground", "highlightbackground", "highlightcolor",
            "insertbackground", "selectbackground", "selectforeground",
        )
        if key not in self._light_widget_options:
            saved: dict[str, str] = {}
            for option in options:
                try:
                    saved[option] = str(widget.cget(option))
                except (tk.TclError, AttributeError):
                    pass
            self._light_widget_options[key] = saved

        saved = self._light_widget_options[key]
        updates: dict[str, str] = {}
        for option, original in saved.items():
            updates[option] = self._dark_color_for(original) if use_dark else original
        if updates:
            try:
                widget.configure(**updates)
            except tk.TclError:
                # Algunos widgets aceptan parte de las opciones pero no todas juntas.
                for option, value in updates.items():
                    try:
                        widget.configure(**{option: value})
                    except tk.TclError:
                        pass

        try:
            children = widget.winfo_children()
        except tk.TclError:
            children = []
        for child in children:
            self._apply_widget_theme(child, use_dark)

    def _apply_result_tag_theme(self) -> None:
        if self.dark_mode:
            self.results.tag_configure("lexical", background="#3A1F24", foreground=DARK_TEXT)
            self.results.tag_configure("syntactic", background="#3A2D16", foreground=DARK_TEXT)
            self.results.tag_configure("semantic", background="#2D2145", foreground=DARK_TEXT)
        else:
            self.results.tag_configure("lexical", background="#FFF3F2", foreground=TEXT)
            self.results.tag_configure("syntactic", background="#FFFAEB", foreground=TEXT)
            self.results.tag_configure("semantic", background="#F5F3FF", foreground=TEXT)

    def toggle_dark_mode(self) -> None:
        """Alterna entre modo claro y oscuro sin alterar el código cargado ni los errores."""
        self.dark_mode = not self.dark_mode
        self._configure_styles()
        self._apply_widget_theme(self, self.dark_mode)
        self._apply_result_tag_theme()
        self.theme_button.configure(text="Modo claro" if self.dark_mode else "Modo oscuro")
        self.status.configure(
            text="Modo oscuro activado." if self.dark_mode else "Modo claro activado."
        )

    def _update_cursor_position(self, _event: tk.Event | None = None) -> None:
        line, column = self.editor.text.index("insert").split(".")
        self.position_label.configure(text=f"Línea {line}, columna {int(column) + 1}")

    def open_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Seleccionar archivo Compiscript",
            filetypes=[("Archivos Compiscript", "*.cps"), ("Todos los archivos", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".cps":
            messagebox.showerror("Archivo no válido", "Selecciona un archivo con extensión .cps.", parent=self)
            return
        try:
            content = self._read_file(path)
        except OSError as exc:
            messagebox.showerror("No se pudo abrir el archivo", str(exc), parent=self)
            return

        self.current_file = path
        self.file_label.configure(text=path.name)
        self.editor.set_content(content)
        self._reset_analysis()
        self.status.configure(text=f"Archivo cargado: {path}")

    @staticmethod
    def _read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def save_file(self) -> None:
        if self.current_file is None:
            self.save_as()
            return
        self._write_current_file(self.current_file)

    def save_as(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Guardar archivo Compiscript",
            defaultextension=".cps",
            filetypes=[("Archivos Compiscript", "*.cps")],
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".cps":
            path = path.with_suffix(".cps")
        self.current_file = path
        self.file_label.configure(text=path.name)
        self._write_current_file(path)

    def _write_current_file(self, path: Path) -> None:
        try:
            path.write_text(self.editor.get_content(), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return
        self.status.configure(text=f"Archivo guardado: {path}")

    def analyze(self) -> None:
        source = self.editor.get_content()
        self.status.configure(text="Analizando léxico, sintaxis y semántica...")
        self.update_idletasks()
        try:
            self.analysis_result = self.analyzer.analyze_full_text(source)
            self.errors = self.analysis_result.errors
        except Exception as exc:
            messagebox.showerror(
                "No fue posible completar el análisis",
                f"Ocurrió un error inesperado:\n\n{exc}",
                parent=self,
            )
            self.status.configure(text="El análisis no pudo completarse.")
            return

        lexical = sum(error.error_type == "Léxico" for error in self.errors)
        syntactic = sum(error.error_type == "Sintáctico" for error in self.errors)
        semantic = sum(error.error_type == "Semántico" for error in self.errors)
        self.lexical_card.set_value(str(lexical))
        self.syntactic_card.set_value(str(syntactic))
        self.semantic_card.set_value(str(semantic))
        self.editor.show_error_lines(self.errors)
        self._populate_results()
        self._populate_symbol_table()
        self._populate_parse_tree()

        if not self.errors:
            self.total_card.set_value("Correcto")
            self.status.configure(text="Análisis completado: código léxica, sintáctica y semánticamente válido.")
            self._show_success_detail()
        else:
            self.total_card.set_value(f"{len(self.errors)} error(es)")
            if lexical or syntactic:
                self.status.configure(
                    text=f"Análisis completado: {lexical} léxico(s), {syntactic} sintáctico(s). El análisis semántico se omite para evitar cascadas."
                )
            else:
                self.status.configure(text=f"Análisis completado: {semantic} error(es) semántico(s).")
            first_item = next(iter(self.results.get_children()), None)
            if first_item:
                self.results.selection_set(first_item)
                self.results.focus(first_item)
                self._show_selected_error()

    def _filtered_errors(self) -> list[AnalysisError]:
        selected = self.filter_var.get()
        mapping = {"Léxicos": "Léxico", "Sintácticos": "Sintáctico", "Semánticos": "Semántico"}
        if selected in mapping:
            return [error for error in self.errors if error.error_type == mapping[selected]]
        return self.errors

    def _populate_results(self) -> None:
        for item in self.results.get_children():
            self.results.delete(item)
        self.item_to_error.clear()

        visible = self._filtered_errors()
        for error in visible:
            tag = {"Léxico": "lexical", "Sintáctico": "syntactic", "Semántico": "semantic"}.get(error.error_type, "")
            item = self.results.insert(
                "",
                "end",
                values=(error.error_type, error.code or "-", error.line, error.column, error.symbol, error.description),
                tags=(tag,) if tag else (),
            )
            self.item_to_error[item] = error
        self.visible_count.configure(text=f"{len(visible)} resultado(s)")

    def _populate_symbol_table(self) -> None:
        for item in self.symbol_tree.get_children():
            self.symbol_tree.delete(item)
        if self.analysis_result is None or self.analysis_result.symbol_table is None:
            self.symbol_count.configure(text="0 símbolos")
            return
        rows = self.analysis_result.symbol_table.rows()
        for row in rows:
            self.symbol_tree.insert(
                "", "end",
                values=(row["scope"], row["depth"], row["name"], row["kind"], row["type"], row["signature"], "Sí" if row["mutable"] else "No", row["line"]),
            )
        self.symbol_count.configure(text=f"{len(rows)} símbolo(s)")

    def _populate_parse_tree(self) -> None:
        for item in self.parse_tree.get_children():
            self.parse_tree.delete(item)
        if self.analysis_result is None or self.analysis_result.parse_tree is None:
            self.tree_count.configure(text="0 nodos")
            return
        parser = self.analysis_result.parser
        count = 0
        max_nodes = 2500

        def walk(node, parent=""):
            nonlocal count
            if count >= max_nodes:
                return
            count += 1
            start = getattr(node, "start", None) or getattr(node, "symbol", None)
            line = getattr(start, "line", "")
            col = getattr(start, "column", None)
            pos = f"{line}:{int(col)+1}" if line not in (None, "") and col is not None else ""
            item = self.parse_tree.insert(parent, "end", text=node_label(node, parser), values=(pos,))
            child_count = getattr(node, "getChildCount", lambda: 0)()
            for i in range(child_count):
                walk(node.getChild(i), item)
        walk(self.analysis_result.parse_tree)
        roots = self.parse_tree.get_children()
        if roots:
            self.parse_tree.item(roots[0], open=True)
        suffix = "+" if count >= max_nodes else ""
        self.tree_count.configure(text=f"{count}{suffix} nodos")

    def _show_selected_error(self, _event: tk.Event | None = None) -> None:
        selection = self.results.selection()
        if not selection:
            return
        error = self.item_to_error.get(selection[0])
        if error is None:
            return
        self.detail_title.configure(
            text=f"Error {error.error_type.lower()} · línea {error.line}, columna {error.column}"
        )
        self.detail_description.configure(text=error.description)
        self.detail_suggestion.configure(text=f"Sugerencia: {error.suggestion}")
        self._set_detail_excerpt(error.source_excerpt or "No hay una línea de contexto disponible.")

    def _jump_to_selected_error(self, _event: tk.Event | None = None) -> None:
        selection = self.results.selection()
        if not selection:
            return
        error = self.item_to_error.get(selection[0])
        if error:
            self.editor.goto(error.line, max(0, error.column - 1))

    def _show_success_detail(self) -> None:
        self.detail_title.configure(text="Código válido")
        self.detail_description.configure(
            text="El lexer, parser y visitor semántico recorrieron el archivo completo sin detectar errores."
        )
        self.detail_suggestion.configure(text="El archivo cumple las reglas léxicas, sintácticas y semánticas implementadas para Compiscript.")
        self._set_detail_excerpt("✓ Análisis léxico correcto\n✓ Análisis sintáctico correcto\n✓ Análisis semántico correcto")

    def _set_detail_excerpt(self, text: str) -> None:
        self.detail_excerpt.configure(state="normal")
        self.detail_excerpt.delete("1.0", "end")
        self.detail_excerpt.insert("1.0", text)
        self.detail_excerpt.configure(state="disabled")

    def _reset_analysis(self) -> None:
        self.errors = []
        self.analysis_result = None
        self.item_to_error.clear()
        for item in self.results.get_children():
            self.results.delete(item)
        self.total_card.set_value("Sin analizar")
        self.lexical_card.set_value("0")
        self.syntactic_card.set_value("0")
        self.semantic_card.set_value("0")
        self.visible_count.configure(text="0 resultados")
        self.editor.show_error_lines([])
        if hasattr(self, "symbol_tree"):
            for item in self.symbol_tree.get_children(): self.symbol_tree.delete(item)
            self.symbol_count.configure(text="0 símbolos")
        if hasattr(self, "parse_tree"):
            for item in self.parse_tree.get_children(): self.parse_tree.delete(item)
            self.tree_count.configure(text="0 nodos")
        self.detail_title.configure(text="Selecciona Analizar para iniciar")
        self.detail_description.configure(
            text="Los errores léxicos, sintácticos y semánticos aparecerán con línea, columna, regla y sugerencia."
        )
        self.detail_suggestion.configure(text="")
        self._set_detail_excerpt("")

    def open_rubric_tests(self) -> None:
        """Muestra la batería de pruebas semánticas entregada con el proyecto."""
        tests_dir = Path(__file__).resolve().parent / "pruebas_semanticas"
        manifest_path = tests_dir / "manifest.json"
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("No se pudieron cargar las pruebas", str(exc), parent=self)
            return

        window = tk.Toplevel(self)
        window.title("Batería de pruebas semánticas · Proyecto 01")
        window.geometry("1040x560")
        window.minsize(820, 420)
        window.configure(bg=BG)
        window.transient(self)

        header = tk.Frame(window, bg=NAVY)
        header.pack(fill="x")
        tk.Label(header, text="Casos exitosos y fallidos de reglas semánticas", bg=NAVY, fg="white", font=("Segoe UI", 14, "bold"), padx=18, pady=14).pack(anchor="w")

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        columns = ("archivo", "regla", "esperado", "descripcion")
        tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        tree.heading("archivo", text="Archivo")
        tree.heading("regla", text="Regla")
        tree.heading("esperado", text="Esperado")
        tree.heading("descripcion", text="Descripción")
        tree.column("archivo", width=250, anchor="w")
        tree.column("regla", width=180, anchor="w")
        tree.column("esperado", width=100, anchor="center")
        tree.column("descripcion", width=440, anchor="w")
        for entry in entries:
            tree.insert("", "end", values=(entry["archivo"], entry["regla"], entry["esperado"], entry["descripcion"]))
        tree.pack(fill="both", expand=True)

        footer = tk.Frame(body, bg=BG)
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(footer, text="Doble clic para cargar una prueba en el editor; luego F5 para ejecutar el pipeline completo.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")

        def load_selected(_event=None):
            selection = tree.selection()
            if not selection:
                return
            values = tree.item(selection[0], "values")
            if not values:
                return
            path = tests_dir / values[0]
            try:
                content = self._read_file(path)
            except OSError as exc:
                messagebox.showerror("No se pudo abrir la prueba", str(exc), parent=window)
                return
            self.current_file = path
            self.file_label.configure(text=path.name)
            self.editor.set_content(content)
            self._reset_analysis()
            self.status.configure(text=f"Prueba semántica cargada: {path.name}")
            window.destroy()

        ttk.Button(footer, text="Cargar seleccionada", command=load_selected, style="Primary.TButton").pack(side="right")
        tree.bind("<Double-1>", load_selected)
        first = next(iter(tree.get_children()), None)
        if first:
            tree.selection_set(first)
            tree.focus(first)
        if self.dark_mode:
            self._apply_widget_theme(window, True)

    def clear_all(self) -> None:
        self.current_file = None
        self.file_label.configure(text="Sin archivo seleccionado")
        self.editor.set_content("")
        self._reset_analysis()
        self.status.configure(text="Editor limpio. Listo para cargar o escribir código Compiscript.")


if __name__ == "__main__":
    # Mejora la nitidez en pantallas con escalado de Windows cuando está disponible.
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = CompiscriptApp()
    app.mainloop()
