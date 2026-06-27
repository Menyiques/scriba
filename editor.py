#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scriba — Editor gráfico para ZX Spectrum (Sistema de Creacion Retro de Interactivas, Bit-8 y Aventuras)
Requiere: Python 3.8+, tkinter (incluido), PyYAML (pip install pyyaml)

Uso:
  python editor.py
  python editor.py mi_juego.yaml
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, scrolledtext
import tkinter.font as tkfont
import yaml
import json
import os
import re
import sys
import copy

# ─── Versión del IDE (incrementar AQUÍ cuando se pida) ──────────────────
SCRIBA_VERSION   = '2.2'
SCRIBA_COPYRIGHT = '(c) 2026 Menyiques Soft'

try:
    from interpreter import BUILTIN_VERBS, BUILTIN_PREPS
except ImportError:
    BUILTIN_VERBS = {}
    BUILTIN_PREPS = {}

try:
    from compiler import validate_game, validate_scripts, check_vocabulary
except ImportError:
    validate_game = validate_scripts = check_vocabulary = None

BUILTIN_BY_SECTION = {'verbs': BUILTIN_VERBS, 'prepositions': BUILTIN_PREPS}


def _yaml_str_representer(dumper, data):
    """Strings multilínea como bloques '|' al volcar YAML (registro único).
    Se eliminan los espacios al final de cada línea: PyYAML no puede usar
    estilo literal con ellos y degradaría todo el bloque a estilo escapado
    (ilegible). Para los scripts BASIC son irrelevantes."""
    if '\n' in data:
        data = '\n'.join(l.rstrip() for l in data.split('\n'))
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


yaml.add_representer(str, _yaml_str_representer)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES DE LAYOUT Y COLOR
# ═══════════════════════════════════════════════════════════════════════════════

CW, CH   = 140, 76      # ancho, alto de casilla
PX, PY   = 65, 50       # padding entre casillas (para colocación inicial)
OX, OY   = 110, 110     # offset inicial del canvas (margen)
STEP_X   = CW + PX      # paso horizontal entre nodos
STEP_Y   = CH + PY      # paso vertical entre nodos
# Pasos de colocación inicial por dirección
DIR_PIX  = {
    'N': ( 0,       -STEP_Y),
    'S': ( 0,       +STEP_Y),
    'E': (+STEP_X,   0),
    'O': (-STEP_X,   0),
    'U': (+STEP_X//2, -STEP_Y),
    'D': (+STEP_X//2, +STEP_Y),
}

C_BG          = "#16213e"
C_LOC         = "#1a4a8a"
C_LOC_SEL     = "#8b1a1a"
C_LOC_GHOST   = "#1a2a3a"   # casilla de otro nivel en misma posición xy
C_TEXT        = "#ecf0f1"
C_TEXT_GHOST  = "#445566"
C_TEXT_ID     = "#7090cc"
C_ARROW_H     = "#3498db"   # flechas horizontales/verticales
C_ARROW_UD    = "#2ecc71"   # indicadores arriba/abajo
C_BORDER      = "#4a8eff"
C_BORDER_SEL  = "#ff4444"
C_BORDER_GHOST= "#223344"
C_STACK_FILL  = "#0d1b2e"
C_TOOLBAR     = "#0d1b2a"
C_STATUS      = "#0a1520"

DIR_OPPOSITE = {'N':'S','S':'N','E':'O','O':'E','U':'D','D':'U'}
DIR_DELTA    = {          # (dcol, drow, dlevel) — mapa plano: U/D en diagonal
    'N': ( 0, -1,  0),
    'S': ( 0,  1,  0),
    'E': ( 1,  0,  0),
    'O': (-1,  0,  0),
    'U': ( 1, -1,  0),
    'D': ( 1,  1,  0),
}
DIR_NAMES = {'N':'Norte','S':'Sur','E':'Este','O':'Oeste','U':'Arriba','D':'Abajo'}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE GEOMETRÍA
# ═══════════════════════════════════════════════════════════════════════════════

def cell_rect(cx, cy):
    """Rectángulo a partir del CENTRO del nodo."""
    return cx - CW//2, cy - CH//2, cx + CW//2, cy + CH//2

def cell_center(cx, cy):
    return cx, cy

def edge_point(cx, cy, direction):
    """Punto en el borde del nodo hacia 'direction'."""
    hw, hh = CW // 2, CH // 2
    offsets = {
        'N': (0, -hh), 'S': (0, hh),
        'E': (hw, 0),  'O': (-hw, 0),
        'U': (hw, -hh), 'D': (hw, hh),
    }
    dx, dy = offsets.get(direction, (0, 0))
    return cx + dx, cy + dy

def dir_label(direction):
    """Etiqueta de la dirección para mostrar en la flecha."""
    return {'U': 'Up', 'D': 'Dw'}.get(
        direction, direction if direction in ('N','S','E','O') else 'X')


# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# BARRA DE BÚSQUEDA REUTILIZABLE
# ═══════════════════════════════════════════════════════════════════════════════

class SearchBar(ttk.Frame):
    """
    Barra de búsqueda rápida (estilo Ctrl+F) para widgets Text / ScrolledText.
    Se incrusta como Frame encima del widget de texto. Uso:
        bar = SearchBar(parent_frame, text_widget)
        # Bind Ctrl+F al text_widget → bar.show()
    """

    TAG_ALL = "sb_match"    # resaltado de todas las coincidencias
    TAG_CUR = "sb_current"  # resaltado de la coincidencia activa

    def __init__(self, parent, text_widget, **kw):
        super().__init__(parent, **kw)
        self._tw   = text_widget
        self._hits = []   # lista de (start_idx, end_idx)
        self._idx  = -1   # posición actual

        # Configurar tags de resaltado en el text widget
        text_widget.tag_configure(self.TAG_ALL,
                                   background="#8b6914", foreground="white")
        text_widget.tag_configure(self.TAG_CUR,
                                   background="#e6a817", foreground="black")

        # Al editar el texto, refrescar las coincidencias (sin desplazar) para que
        # no queden apariciones "fantasma" del texto que había antes.
        text_widget.bind("<<Modified>>", self._on_text_change, add="+")

        # ── Widgets de la barra ──────────────────────────────────────────
        ttk.Label(self, text=" 🔍").pack(side=tk.LEFT, padx=(4, 1))

        self._svar = tk.StringVar()
        self._svar.trace_add("write", lambda *_: self._do_search())
        self._entry = ttk.Entry(self, textvariable=self._svar, width=24)
        self._entry.pack(side=tk.LEFT, padx=2)
        self._entry.bind("<Return>",        lambda e: self._step(+1))
        self._entry.bind("<Shift-Return>",  lambda e: self._step(-1))
        self._entry.bind("<Escape>",        lambda e: self.hide())

        self._info = ttk.Label(self, text="", width=10, anchor=tk.W)
        self._info.pack(side=tk.LEFT, padx=(3, 6))

        ttk.Button(self, text="▲", width=2,
                   command=lambda: self._step(-1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(self, text="▼", width=2,
                   command=lambda: self._step(+1)).pack(side=tk.LEFT, padx=1)

        self._case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Aa", variable=self._case_var,
                        command=self._do_search).pack(side=tk.LEFT, padx=(8, 2))

        ttk.Button(self, text="✕", width=2,
                   command=self.hide).pack(side=tk.RIGHT, padx=(2, 4))

    # ── API pública ────────────────────────────────────────────────────────────

    def show(self):
        """Muestra la barra encima del text widget y enfoca el campo."""
        self.pack(fill=tk.X, before=self._tw)
        self._entry.focus_set()
        self._entry.select_range(0, tk.END)
        self._do_search()

    def hide(self):
        """Oculta la barra y elimina todos los resaltados."""
        self._clear_tags()
        self.pack_forget()
        self._tw.focus_set()

    # ── Lógica interna ─────────────────────────────────────────────────────────

    def _rescan(self):
        """Recalcula la lista de coincidencias y los resaltados a partir del texto
        ACTUAL del widget. No toca el índice ni desplaza la vista."""
        query = self._svar.get()
        self._clear_tags()
        self._hits = []
        if not query:
            return
        tw = self._tw
        nocase = not self._case_var.get()
        pos = "1.0"
        while True:
            found = tw.search(query, pos, stopindex=tk.END, nocase=nocase)
            if not found:
                break
            end = f"{found}+{len(query)}c"
            self._hits.append((found, end))
            tw.tag_add(self.TAG_ALL, found, end)
            pos = end

    def _do_search(self, scroll=True):
        self._rescan()
        if not self._hits:
            self._idx = -1
            self._info.config(text="0 resultados" if self._svar.get() else "")
            return
        self._idx = 0
        self._highlight_current(scroll)

    def _on_text_change(self, event=None):
        """El contenido del text widget ha cambiado: recalcula las coincidencias
        para no dejar 'fantasmas' del texto anterior. No desplaza la vista."""
        tw = self._tw
        try:
            if not tw.edit_modified():
                return
            tw.edit_modified(False)   # rearmar el evento para próximos cambios
        except tk.TclError:
            return
        if self.winfo_ismapped() and self._svar.get():
            self._do_search(scroll=False)

    def _step(self, delta):
        # Re-escanear SIEMPRE: si el texto cambió desde la última búsqueda, las
        # posiciones viejas eran "fantasma". Así nunca navega a algo inexistente.
        prev = self._idx
        self._rescan()
        if not self._hits:
            self._idx = -1
            self._info.config(text="0 resultados" if self._svar.get() else "")
            self._entry.focus_set()
            return
        if prev < 0:
            self._idx = 0
        else:
            self._idx = (prev + delta) % len(self._hits)
        self._highlight_current()

    def _highlight_current(self, scroll=True):
        tw = self._tw
        tw.tag_remove(self.TAG_CUR, "1.0", tk.END)
        if self._idx < 0 or not self._hits:
            return
        s, e = self._hits[self._idx]
        tw.tag_add(self.TAG_CUR, s, e)
        tw.tag_raise(self.TAG_CUR, self.TAG_ALL)
        if scroll:
            tw.see(s)
        self._info.config(text=f"{self._idx + 1}/{len(self._hits)}")

    def _clear_tags(self):
        self._tw.tag_remove(self.TAG_ALL, "1.0", tk.END)
        self._tw.tag_remove(self.TAG_CUR, "1.0", tk.END)
        self._info.config(text="")


# ═══════════════════════════════════════════════════════════════════════════════
# EDITOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class ScribaEditor:

    # ─── Init ─────────────────────────────────────────────────────────────────

    def __init__(self, root, initial_file=None):
        self.root  = root
        self.root.title("Scriba " + SCRIBA_VERSION)
        self.root.geometry("1560x950")
        self.root.minsize(1100, 700)

        self.game      = self._empty_game()
        self.filepath  = None
        self.level     = 0             # nivel mostrado
        self.sel       = None          # loc_id seleccionada
        self.positions = {}            # {loc_id: [col, row, level]}
        self.dirty     = False
        self.sel_arrow   = None         # (from_id, direction, to_id) o None
        self._drag_src   = None         # loc_id origen del arrastre
        self._drag_dir   = None         # dirección de borde desde la que se arrastra
        self._drag_line  = None         # item canvas de la línea rubber-band
        self.player_loc  = None         # loc_id del jugador (intérprete activo)
        self._interp_win = None         # ventana del intérprete
        self._moving_node = None        # nodo que se está arrastrando
        self._move_offset = (0, 0)      # offset ratón→centro del nodo
        self._moving_px   = None        # posición píxel actual durante el drag
        self.breakpoints  = {}          # {section: set(línea normalizada)}
        self._code_gutters = {}         # {section: Text gutter}
        self._code_after   = {}         # {section: id de after pendiente}
        self._col_texts    = []         # [(ScrolledText, regla)] sensibles a columnas ZX
        self._img_locs     = set()      # localizaciones con imagen <id>.scr en img/

        # Fuentes globales (compartidas con InterpreterWindow)
        self.fnt_code  = tkfont.Font(family='Courier',    size=10)
        self.fnt_ui    = tkfont.Font(family='Helvetica',  size=9)
        self.fnt_bold  = tkfont.Font(family='Helvetica',  size=9,  weight='bold')
        self.fnt_sm    = tkfont.Font(family='Courier',    size=8)
        self.fnt_map   = tkfont.Font(family='Helvetica',  size=9,  weight='bold')  # nombres en mapa
        self.fnt_mapid = tkfont.Font(family='Courier',    size=8)                  # IDs en mapa
        self.fnt_map7  = tkfont.Font(family='Courier',    size=7)                  # objetos en mapa
        self.fnt_map8b = tkfont.Font(family='Courier',    size=8, weight='bold')   # etiquetas flecha

        self.zoom = 1.0   # factor de zoom del mapa

        self._build_menus()
        self._build_layout()
        self._load_all_forms()
        self._redraw()
        self._run_validation()

        if initial_file and os.path.exists(initial_file):
            self._do_open(initial_file)

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ─── Datos ────────────────────────────────────────────────────────────────

    def _empty_game(self):
        return {
            "metadata": {
                "title": "Nueva Aventura",
                "author": "",
                "version": "1.0",
                "language": "es",
                "start_location": "",
                "max_score": 0,
                "start_message": "",
                "border": 0
            },
            "variables": {"PUNTOS": 0, "TURNOS": 0, "LLEVAR_MAX": 50, "PESO_ACT": 0},
            "vocabulary": {"verbs": {}, "nouns": {}, "prepositions": {}},
            "locations": {},
            "objects": {},
            "timers": {},
            "condacts": {
                "on_start": "", "before_turn": "",
                "after_turn": "", "on_end": "", "responses": ""
            },
            "fx": []
        }

    def _unique_id(self, prefix="loc"):
        i = 1
        while f"{prefix}{i}" in self.game["locations"]:
            i += 1
        return f"{prefix}{i}"

    # ── Posiciones ──

    def _pos_free(self, col, row, level, exclude=None):
        for lid, p in self.positions.items():
            if lid == exclude:
                continue
            if p[0] == col and p[1] == row and p[2] == level:
                return False
        return True

    def _loc_at(self, col, row, level):
        for lid, p in self.positions.items():
            if p[0] == col and p[1] == row and p[2] == level:
                return lid
        return None

    # ── Geometría con zoom ──

    ZOOM_MIN, ZOOM_MAX = 0.25, 2.0

    def _zgeom(self):
        """(cw, ch, step_x, step_y) escalados por el zoom actual."""
        z = self.zoom
        return (max(8, int(CW * z)), max(6, int(CH * z)),
                max(10, int(STEP_X * z)), max(10, int(STEP_Y * z)))

    def _cell_rect(self, cx, cy):
        cw, ch, _, _ = self._zgeom()
        return cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2

    def _edge_point(self, cx, cy, direction):
        cw, ch, _, _ = self._zgeom()
        hw, hh = cw // 2, ch // 2
        offsets = {
            'N': (0, -hh), 'S': (0, hh),
            'E': (hw, 0),  'O': (-hw, 0),
            'U': (hw, -hh), 'D': (hw, hh),
        }
        dx, dy = offsets.get(direction, (0, 0))
        return cx + dx, cy + dy

    def _grid_to_px(self, col, row):
        """Convierte coordenadas de cuadrícula (col, row) a píxeles del centro del nodo."""
        _, _, sx, sy = self._zgeom()
        return OX + col * sx, OY + row * sy

    def _px_to_grid(self, wx, wy):
        """Inversa de _grid_to_px."""
        _, _, sx, sy = self._zgeom()
        return round((wx - OX) / sx), round((wy - OY) / sy)

    def _stack_at(self, col, row):
        """Todos los loc_id en (col, row) de cualquier nivel."""
        return [lid for lid, p in self.positions.items()
                if p[0] == col and p[1] == row]

    def _flatten_positions(self):
        """Mapa plano: todos los niveles a 0, resolviendo colisiones (col,row).
        Los niveles heredados de mapas antiguos se despliegan en diagonal
        (arriba = derecha-arriba), como las nuevas conexiones U/D."""
        occ = set()
        new_pos = {}
        for lid, (col, row, lev) in sorted(self.positions.items(),
                                           key=lambda kv: (kv[1][2], kv[0])):
            c, r = col + lev, row - lev
            if (c, r) in occ:
                k = 1
                placed = False
                while not placed:
                    for dc, dr in ((k, 0), (0, k), (k, k), (-k, 0),
                                   (0, -k), (k, -k), (-k, k), (-k, -k)):
                        if (c + dc, r + dr) not in occ:
                            c, r = c + dc, r + dr
                            placed = True
                            break
                    k += 1
            occ.add((c, r))
            new_pos[lid] = [c, r, 0]
        self.positions = new_pos
        self.level = 0

    # ── Zoom ──

    def _set_zoom(self, z):
        z = max(self.ZOOM_MIN, min(self.ZOOM_MAX, z))
        self.zoom = z
        self._apply_map_fonts()
        self._redraw()

    def _zoom_in(self):
        self._set_zoom(self.zoom * 1.2)

    def _zoom_out(self):
        self._set_zoom(self.zoom / 1.2)

    def _apply_map_fonts(self):
        z = self.zoom
        self.fnt_map.config(size=max(5, int(round(9 * z))))
        self.fnt_mapid.config(size=max(5, int(round(8 * z))))
        self.fnt_map7.config(size=max(5, int(round(7 * z))))
        self.fnt_map8b.config(size=max(5, int(round(8 * z))))

    def _zoom_fit(self):
        """Ajusta el zoom para que TODO el mapa quepa en la vista."""
        if not self.positions:
            return
        cols = [p[0] for p in self.positions.values()]
        rows = [p[1] for p in self.positions.values()]
        span_x = (max(cols) - min(cols)) * STEP_X + CW + 180
        span_y = (max(rows) - min(rows)) * STEP_Y + CH + 180
        vw = max(50, self.canvas.winfo_width())
        vh = max(50, self.canvas.winfo_height())
        z = min(vw / span_x, vh / span_y, 1.0)
        self._set_zoom(z)
        self._center_map()

    # ─── Menús ────────────────────────────────────────────────────────────────

    def _build_menus(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)

        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Archivo", menu=fm)
        fm.add_command(label="Nuevo",            command=self._new_file)
        fm.add_command(label="Abrir YAML…",      command=self._open_file)
        fm.add_command(label="Guardar",          command=self._save_file,  accelerator="Ctrl+S")
        fm.add_command(label="Guardar como…",    command=self._save_as)
        fm.add_separator()
        fm.add_command(label="Validar juego",
                       command=lambda: self._run_validation(silent=False))
        fm.add_command(label="Exportar ZX Spectrum 48K (.bas)…",
                       command=lambda: self._export_spectrum('48k'))
        fm.add_command(label="Exportar ZX Spectrum 128K (.bas)…",
                       command=lambda: self._export_spectrum('128k'))
        fm.add_command(label="Exportar ZX Spectrum Next (.tap + imágenes)…",
                       command=self._export_next)
        fm.add_command(label="Exportar Amstrad CPC (.dsk, motor nativo)…",
                       command=lambda: self._export_cpc_nativo(2))
        fm.add_command(label="Exportar para Windows (.exe)…",
                       command=self._export_windows)
        fm.add_separator()
        fm.add_command(label="Exportar literales para traducir (CSV)…",
                       command=self._export_literales)
        fm.add_command(label="Importar literales traducidos (CSV → YAML)…",
                       command=self._import_literales)
        fm.add_separator()
        fm.add_command(label="Configuración de compilación (TAP)…",
                       command=self._build_config_dialog)
        self._zx_cols = tk.IntVar(value=42)
        cm = tk.Menu(fm, tearoff=0)
        fm.add_cascade(label="Columnas de texto ZX", menu=cm)
        for nc in (32, 42, 64):
            cm.add_radiobutton(label=f"{nc} columnas",
                               variable=self._zx_cols, value=nc,
                               command=self._apply_zx_cols)
        # Plataforma de imágenes a PREVISUALIZAR (no afecta a la exportación):
        # 128K usa img/Spectrum/<id>.scr (ULA, o dithering de img/Original si no hay);
        # Next previsualiza siempre img/Original/<id>.png|jpg (master en color).
        self._plataforma = tk.StringVar(value='next')
        pm = tk.Menu(fm, tearoff=0)
        fm.add_cascade(label="Imágenes a previsualizar", menu=pm)
        pm.add_radiobutton(label="128K  (img/Spectrum .scr, o dithering)",
                           variable=self._plataforma, value='128k',
                           command=self._apply_plataforma)
        pm.add_radiobutton(label="Next  (img/Original, .png/.jpg)",
                           variable=self._plataforma, value='next',
                           command=self._apply_plataforma)
        fm.add_separator()
        fm.add_command(label="Salir",            command=self._quit)

        tm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Herramientas", menu=tm)
        tm.add_command(label="Validar juego", accelerator="F7",
                       command=lambda: self._run_validation(silent=False))
        tm.add_command(label="Estadísticas y auditoría de puntos",
                       command=self._show_stats)

        vm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Ver", menu=vm)
        vm.add_command(label="Zoom +",           command=self._zoom_in,   accelerator="PgUp")
        vm.add_command(label="Zoom −",           command=self._zoom_out,  accelerator="PgDn")
        vm.add_command(label="Ver todo el mapa", command=self._zoom_fit)
        vm.add_command(label="Centrar mapa",     command=self._center_map)
        vm.add_separator()
        vm.add_command(label="Fuente más grande", command=lambda: self._font_change(+1), accelerator="Ctrl++")
        vm.add_command(label="Fuente más pequeña",command=lambda: self._font_change(-1), accelerator="Ctrl+-")
        vm.add_command(label="Fuente normal",     command=lambda: self._font_reset())

        hm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Ayuda", menu=hm)
        hm.add_command(label="Referencia (manual)…", command=self._open_manual)
        hm.add_command(label="Sobre Scriba…",
                       command=lambda: _show_splash(self.root))

        self.root.bind("<Control-equal>",  lambda e: self._font_change(+1))
        self.root.bind("<Control-plus>",   lambda e: self._font_change(+1))
        self.root.bind("<Control-minus>",  lambda e: self._font_change(-1))
        # Atajos de debug (activos cuando el intérprete está abierto)
        self.root.bind("<F10>", lambda e: self._dbg_step())
        self.root.bind("<F5>",  lambda e: self._dbg_continue())

        self.root.bind("<Control-s>", lambda e: self._save_file())
        self.root.bind("<Prior>",     lambda e: self._zoom_in())
        self.root.bind("<Next>",      lambda e: self._zoom_out())

    # ─── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self):
        # Barra de estado (se empaqueta antes para que quede fija abajo)
        self.sv_status = tk.StringVar(value="Listo · Doble clic en espacio vacío para añadir la primera localización")
        tk.Label(self.root, textvariable=self.sv_status, bd=1, relief=tk.SUNKEN,
                 anchor=tk.W, bg=C_STATUS, fg="#778899", font=("Helvetica", 9)
                 ).pack(side=tk.BOTTOM, fill=tk.X)

        # Splitter horizontal principal: mapa | derecha
        pw = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True)

        lf = ttk.Frame(pw)
        pw.add(lf, weight=3)
        self._build_map_panel(lf)

        # Lado derecho: splitter vertical: propiedades | intérprete
        self._right_pw = tk.PanedWindow(pw, orient=tk.VERTICAL,
                                         bg='#0d1b2a', sashwidth=5,
                                         sashrelief=tk.FLAT, sashpad=1)
        pw.add(self._right_pw, weight=2)

        props_f = ttk.Frame(self._right_pw)
        self._right_pw.add(props_f, stretch='always', minsize=100)
        self._build_props_panel(props_f)

        # Panel del intérprete (inicialmente con minsize=0, casi oculto)
        self._interp_frame = tk.Frame(self._right_pw, bg='#0d1b2a')
        self._right_pw.add(self._interp_frame, stretch='never', minsize=0)
        self._interp_placeholder = tk.Label(
            self._interp_frame,
            text='▶  Pulsa "Probar juego" para iniciar el intérprete',
            bg='#0d1b2a', fg='#334466', font=('Helvetica', 9, 'italic'))
        self._interp_placeholder.pack(expand=True)

    # ── Helper: texto con búsqueda integrada ────────────────────────────────────

    def _make_searchable_text(self, parent, height=5, width=35, ruler=False,
                              **kwargs):
        """
        Crea un Frame que contiene una SearchBar oculta + ScrolledText.
        Devuelve (wrapper_frame, text_widget).

        • Posiciona wrapper_frame en el layout (pack/grid).
        • Usa text_widget para leer/escribir contenido.
        • Ctrl+F sobre text_widget despliega la barra de búsqueda.

        Si ruler=True se trata de una caja de PROSA (descripciones, mensaje
        inicial): se le añade una regla de columnas arriba, se fija su ancho
        al número de columnas ZX elegido (32/42/64) y se ajusta por palabras,
        para previsualizar cómo se verá el texto en el Spectrum.
        """
        frame = ttk.Frame(parent)
        rule = None
        if ruler:
            kwargs.setdefault('wrap', tk.WORD)
            rule = tk.Text(frame, height=2, width=width, wrap=tk.NONE,
                           bd=0, padx=1, pady=0, highlightthickness=0,
                           takefocus=0, cursor='arrow', font=self.fnt_code,
                           bg="#0d1a2a", fg="#6b85a3")
            rule.pack(side=tk.TOP, anchor='w')
        t = scrolledtext.ScrolledText(frame, height=height, width=width,
                                       font=self.fnt_code, **kwargs)
        bar = SearchBar(frame, t)
        # La barra empieza oculta. Las cajas de prosa mantienen ancho fijo
        # (solo crecen en vertical); el resto ocupa todo el espacio.
        if ruler:
            t.pack(side=tk.TOP, fill=tk.Y, expand=True, anchor='w')
        else:
            t.pack(fill=tk.BOTH, expand=True)

        def _show(event=None):
            bar.show()
            return "break"

        t.bind("<Control-f>", _show)
        t.bind("<Control-F>", _show)

        if ruler:
            self._col_texts.append((t, rule))
            self._fill_ruler(rule, width)
        return frame, t

    @staticmethod
    def _ruler_lines(n):
        """Dos líneas de regla para n columnas (índices 0..n-1):
        decenas (un dígito cada 10) sobre unidades (0-9 repetidas)."""
        tens  = ''.join(str(c // 10) if c % 10 == 0 else ' ' for c in range(n))
        units = ''.join(str(c % 10) for c in range(n))
        return tens + '\n' + units

    def _fill_ruler(self, rule, n):
        rule.configure(state=tk.NORMAL, width=n)
        rule.delete('1.0', tk.END)
        rule.insert('1.0', self._ruler_lines(n))
        rule.configure(state=tk.DISABLED)

    def _apply_zx_cols(self, announce=True):
        """Redimensiona las cajas de prosa al ancho de columnas ZX elegido
        (32/42/64) y actualiza sus reglas, para ver el ajuste de línea tal
        como aparecerá en el Spectrum."""
        n = self._zx_cols.get()
        for t, rule in getattr(self, '_col_texts', []):
            try:
                t.configure(width=n)
                self._fill_ruler(rule, n)
            except tk.TclError:
                pass
        if announce and hasattr(self, 'sv_status'):
            self.sv_status.set(f'Columnas de texto ZX: {n}  '
                               f'(vista previa del ajuste de línea, col. 0–{n - 1})')

    # ── Panel mapa ──

    def _build_map_panel(self, parent):
        # Barra de herramientas
        tb = tk.Frame(parent, bg=C_TOOLBAR, pady=3)
        tb.pack(fill=tk.X)

        def tb_btn(text, cmd, color="#1e3a5a"):
            return tk.Button(tb, text=text, command=cmd,
                             bg=color, fg=C_TEXT, relief=tk.FLAT,
                             padx=8, pady=2, font=("Helvetica", 9),
                             activebackground="#2a5080", activeforeground=C_TEXT,
                             cursor="hand2")

        tk.Label(tb, text="  Zoom:", bg=C_TOOLBAR, fg="#aaaaaa",
                 font=("Helvetica", 9)).pack(side=tk.LEFT)
        tb_btn(" − ", self._zoom_out).pack(side=tk.LEFT, padx=1)
        self.lbl_zoom = tk.Label(tb, text="100%", bg=C_TOOLBAR, fg="#4fc3f7",
                                  font=("Courier", 11, "bold"), width=5)
        self.lbl_zoom.pack(side=tk.LEFT)
        tb_btn(" + ", self._zoom_in).pack(side=tk.LEFT, padx=1)
        tb_btn("⛶ Todo", self._zoom_fit, "#2a2a3a").pack(side=tk.LEFT, padx=3)

        tk.Frame(tb, width=1, bg="#334466").pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        tb_btn("＋ Nueva loc",  self._add_first_loc, "#1e5a3a").pack(side=tk.LEFT, padx=2)
        tb_btn("✕ Borrar loc",  self._delete_loc,    "#5a1e1e").pack(side=tk.LEFT, padx=2)

        tk.Frame(tb, width=1, bg="#334466").pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)
        tb_btn("🔗 Conectar",   self._start_connect, "#3a3a1e").pack(side=tk.LEFT, padx=2)
        tk.Frame(tb, width=1, bg="#334466").pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)
        tb_btn("▶ Probar juego", self._open_interpreter, "#1e4a1e").pack(side=tk.LEFT, padx=2)
        tk.Frame(tb, width=1, bg="#334466").pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)
        tb_btn("A−", lambda: self._font_change(-1), "#2a2a3a").pack(side=tk.LEFT, padx=1)
        tb_btn("A+", lambda: self._font_change(+1), "#2a2a3a").pack(side=tk.LEFT, padx=1)

        # Canvas
        cf = tk.Frame(parent)
        cf.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(cf, bg=C_BG, highlightthickness=0, cursor="arrow")
        hbar = tk.Scrollbar(cf, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vbar = tk.Scrollbar(cf, orient=tk.VERTICAL,   command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set,
                              scrollregion=(-300, -300, 2500, 2500))
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar.pack(side=tk.RIGHT,  fill=tk.Y)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>",        self._canvas_press)   # click + inicio drag
        self.canvas.bind("<Button-3>",        self._canvas_rclick)
        self.canvas.bind("<Double-Button-1>", self._canvas_dblclick)
        self.canvas.bind("<Motion>",          self._canvas_motion)
        self.canvas.bind("<B1-Motion>",       self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_release)
        self.canvas.bind("<Control-MouseWheel>",
                         lambda e: self._set_zoom(self.zoom * (1.1 if e.delta > 0 else 1/1.1)))
        self.root.bind("<Delete>",            self._delete_selected)

        # Brújula (panel de dirección)
        self._build_compass(parent)

    def _build_compass(self, parent):
        frame = tk.Frame(parent, bg=C_TOOLBAR, pady=4)
        frame.pack(fill=tk.X)

        tk.Label(frame, text="  Añadir adyacente →", bg=C_TOOLBAR,
                 fg="#778899", font=("Helvetica", 9)).pack(side=tk.LEFT, padx=4)

        btn_fr = tk.Frame(frame, bg=C_TOOLBAR)
        btn_fr.pack(side=tk.LEFT, padx=4)

        def dbtn(text, dir_):
            return tk.Button(btn_fr, text=text, width=4, height=1,
                             bg="#1e3a5a", fg="#81c784" if dir_ in ("U","D") else C_TEXT,
                             relief=tk.FLAT, font=("Courier", 8, "bold"),
                             activebackground="#2a5080", cursor="hand2",
                             command=lambda d=dir_: self._add_adj(d))

        # Layout de brújula 3x4:
        #      U
        #  O   N   E
        #      S
        #      D
        dbtn("U↑", "U").grid(row=0, column=1, padx=1, pady=1)
        dbtn("O",  "O").grid(row=1, column=0, padx=1, pady=1)
        dbtn("N",  "N").grid(row=1, column=1, padx=1, pady=1)
        dbtn("E",  "E").grid(row=1, column=2, padx=1, pady=1)
        dbtn("S",  "S").grid(row=2, column=1, padx=1, pady=1)
        dbtn("D↓", "D").grid(row=3, column=1, padx=1, pady=1)

        tk.Label(frame, text=" (selecciona una loc primero)", bg=C_TOOLBAR,
                 fg="#445566", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=8)

    # ── Panel propiedades ──

    def _build_props_panel(self, parent):
        self.nb = ttk.Notebook(parent)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        self._build_meta_tab()
        self._build_loc_tab()
        self._build_obj_tab()
        self._build_vocab_tab()
        self._build_vars_tab()
        self._build_timers_tab()
        self._build_fx_tab()
        self._build_condacts_tab()
        self._build_crossref_tab()
        self._build_problems_tab()
        self.nb.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        self._apply_zx_cols(announce=False)   # ancho inicial de cajas + reglas

    def _on_tab_changed(self, event=None):
        """Al entrar en la pestaña Código, refresca los combos por si se han
        añadido o borrado objetos/localizaciones en otras pestañas."""
        try:
            if self.nb.tab(self.nb.select(), 'text') == self._CS_TAB_TEXT:
                self._crossref_refresh_combos()
        except Exception:
            pass

    # ─── Tab: Metadata ─────────────────────────────────────────────────────

    # Colores de borde del Spectrum (indice 0-7) para el combo de metadata.
    _BORDER_NOMBRES = ['0 - Negro', '1 - Azul', '2 - Rojo', '3 - Magenta',
                       '4 - Verde', '5 - Cian', '6 - Amarillo', '7 - Blanco']

    def _build_meta_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Metadata ")

        fields = [
            ("Título",           "title",          False),
            ("Autor",            "author",         False),
            ("Versión",          "version",        False),
            ("Idioma",           "language",       False),
            ("Start location",   "start_location", False),
            ("Puntuación máx",   "max_score",      False),
            ("Mensaje inicial",  "start_message",  True),
        ]
        self._meta_w = {}   # key → widget
        for i, (label, key, multi) in enumerate(fields):
            ttk.Label(fr, text=label + ":").grid(row=i, column=0, sticky=tk.NW,
                                                   padx=8, pady=4)
            if multi:
                _f, w = self._make_searchable_text(fr, height=12, width=46,
                                                   ruler=True)
                _f.grid(row=i, column=1, sticky=tk.NSEW, padx=4, pady=2)
                fr.rowconfigure(i, weight=1)   # crece con la ventana
            else:
                w = tk.Entry(fr, width=46, font=self.fnt_ui, relief=tk.FLAT)
                w.grid(row=i, column=1, sticky=tk.EW, padx=4, pady=2)
            self._meta_w[key] = w

        # Combo del color de BORDE: se fija en el cargador BASIC (loader) del TAP.
        brow = len(fields)
        ttk.Label(fr, text="Borde (loader):").grid(row=brow, column=0, sticky=tk.NW,
                                                   padx=8, pady=4)
        self._border_var = tk.StringVar(value=self._BORDER_NOMBRES[0])
        ttk.Combobox(fr, textvariable=self._border_var, state='readonly',
                     values=self._BORDER_NOMBRES, width=20).grid(
                         row=brow, column=1, sticky=tk.W, padx=4, pady=2)

        mbtn = ttk.Frame(fr)
        mbtn.grid(row=brow + 1, column=0, columnspan=2, pady=8, sticky=tk.W)
        ttk.Button(mbtn, text="Aplicar metadata",
                   command=self._apply_meta).pack(side=tk.LEFT, padx=(8, 4))
        ttk.Button(mbtn, text="Mensajes del sistema…",
                   command=self._dialog_mensajes).pack(side=tk.LEFT, padx=4)
        # ── preview de la imagen de menú/título (según la plataforma elegida) ──
        mfr = ttk.Frame(fr)
        mfr.grid(row=0, column=2, rowspan=len(fields) + 2, sticky=tk.N,
                 padx=12, pady=4)
        ttk.Label(mfr, text="Imagen de menú / título:").pack(anchor=tk.W)
        self.menu_img_canvas = tk.Canvas(mfr, width=256, height=192,
                                         bg="#000000", highlightthickness=1,
                                         highlightbackground="#44556a")
        self.menu_img_canvas.pack(pady=4)
        ttk.Label(mfr, foreground='#667788', justify=tk.LEFT,
                  text="128K: img/Spectrum/screen.scr (o dithering de Original)"
                       "\nNext: img/Original/screen.png|jpg"
                  ).pack(anchor=tk.W)
        fr.columnconfigure(1, weight=1)
        self._refresh_menu_img()

    # ─── Tab: Localización ─────────────────────────────────────────────────

    def _build_loc_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Localización ")

        pw = ttk.PanedWindow(fr, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True)

        # ── Izquierda: lista de localizaciones ───────────────────────────────
        lf = ttk.Frame(pw)
        pw.add(lf, weight=1)

        ttk.Label(lf, text="Localizaciones").pack(anchor=tk.W, padx=4, pady=(4,1))

        list_fr = tk.Frame(lf)
        list_fr.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.loc_list = tk.Listbox(list_fr, font=self.fnt_ui,
                                    selectmode=tk.SINGLE,
                                    bg="#0d1b2a", fg="#c8d8e8",
                                    selectbackground="#1a4a8a",
                                    selectforeground="#ffffff",
                                    activestyle="none",
                                    relief=tk.FLAT, borderwidth=0)
        lsb = ttk.Scrollbar(list_fr, orient=tk.VERTICAL, command=self.loc_list.yview)
        self.loc_list.configure(yscrollcommand=lsb.set)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.loc_list.pack(fill=tk.BOTH, expand=True)
        self.loc_list.bind("<<ListboxSelect>>", self._loc_list_select)

        bf = tk.Frame(lf)
        bf.pack(fill=tk.X, padx=2, pady=2)
        ttk.Button(bf, text="+ Nueva", command=self._loc_list_new).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Borrar",  command=self._loc_list_del).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🧭 Consistencia",
                   command=self._check_map_consistency).pack(side=tk.LEFT, padx=2)

        # ── Derecha: formulario de edición ───────────────────────────────────
        rf = ttk.Frame(pw)
        pw.add(rf, weight=2)

        ttk.Label(rf, text="ID:").grid(row=0, column=0, sticky=tk.W, padx=8, pady=3)
        self.loc_id = tk.Entry(rf, width=22, font=self.fnt_ui, relief=tk.FLAT)
        self.loc_id.grid(row=0, column=1, sticky=tk.W)

        ttk.Label(rf, text="Nombre:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=3)
        self.loc_name = tk.Entry(rf, width=38, font=self.fnt_ui, relief=tk.FLAT)
        self.loc_name.grid(row=1, column=1, sticky=tk.EW, padx=4)

        ttk.Label(rf, text="Descripcion:").grid(row=2, column=0, sticky=tk.NW, padx=8, pady=3)
        _f, self.loc_desc = self._make_searchable_text(rf, height=9, width=44,
                                                       ruler=True)
        _f.grid(row=2, column=1, sticky=tk.NSEW, padx=4, pady=2)

        self.loc_dark = tk.BooleanVar()
        ttk.Checkbutton(rf, text="Oscuro (dark)", variable=self.loc_dark
                        ).grid(row=3, column=1, sticky=tk.W)

        ttk.Label(rf, text="Salidas:").grid(row=4, column=0, sticky=tk.NW, padx=8, pady=3)
        ef = ttk.Frame(rf)
        ef.grid(row=4, column=1, sticky=tk.EW, pady=2)
        self.exit_vars = {}
        dirs_layout = [('N',0,1),('S',2,1),('E',1,2),('O',1,0),('U',0,3),('D',2,3)]
        for d, gr, gc in dirs_layout:
            ttk.Label(ef, text=f"{d}:").grid(row=gr, column=gc*2, sticky=tk.E, padx=2)
            v = tk.StringVar()
            tk.Entry(ef, textvariable=v, width=10, font=self.fnt_ui,
                     relief=tk.FLAT).grid(row=gr, column=gc*2+1, padx=2, pady=1)
            self.exit_vars[d] = v

        ttk.Label(rf, text="Objetos aquí:").grid(row=5, column=0, sticky=tk.NW, padx=8, pady=3)
        of = ttk.Frame(rf)
        of.grid(row=5, column=1, sticky=tk.EW, padx=4, pady=2)
        self.loc_objs = tk.Listbox(of, height=4, font=self.fnt_ui,
                                    bg="#0d1b2a", fg="#88aacc",
                                    selectbackground="#1a4a8a",
                                    selectforeground="#ffffff",
                                    activestyle="none",
                                    relief=tk.FLAT, borderwidth=0)
        osb = ttk.Scrollbar(of, orient=tk.VERTICAL, command=self.loc_objs.yview)
        self.loc_objs.configure(yscrollcommand=osb.set)
        osb.pack(side=tk.RIGHT, fill=tk.Y)
        self.loc_objs.pack(fill=tk.BOTH, expand=True)
        self.loc_objs.bind("<Double-Button-1>", self._loc_obj_goto)

        ttk.Label(rf, text="on_enter (BASIC):").grid(row=6, column=0, sticky=tk.NW, padx=8, pady=3)
        _f, self.loc_enter = self._make_searchable_text(rf, height=8, width=44)
        _f.grid(row=6, column=1, sticky=tk.NSEW, padx=4, pady=2)

        # Previsualización del tercio superior de img/<id>.scr (si existe)
        ttk.Label(rf, text="Imagen (img/):").grid(row=7, column=0, sticky=tk.NW, padx=8, pady=3)
        self.loc_img_canvas = tk.Canvas(rf, width=512, height=128, bg="#000000",
                                        highlightthickness=1,
                                        highlightbackground="#33506e")
        self.loc_img_canvas.grid(row=7, column=1, sticky=tk.W, padx=4, pady=2)
        self.loc_img_photo = None   # referencia viva para evitar el GC de Tk

        ttk.Button(rf, text="Guardar localización",
                   command=self._apply_loc).grid(row=8, column=0, columnspan=2, pady=6)
        rf.columnconfigure(1, weight=1)
        # Las dos cajas de texto se reparten el alto sobrante (desc 2:1)
        rf.rowconfigure(2, weight=2)
        rf.rowconfigure(6, weight=1)

    # ─── Tab: Objetos ──────────────────────────────────────────────────────

    def _build_obj_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Objetos ")

        # Lista
        top = ttk.Frame(fr)
        top.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        cols = ("ID", "Nombre", "Ubicación", "Peso")
        self.obj_tree = ttk.Treeview(top, columns=cols, show="headings", height=7)
        for c, w in zip(cols, (90, 130, 90, 50)):
            self.obj_tree.heading(c, text=c)
            self.obj_tree.column(c, width=w)
        vsb = ttk.Scrollbar(top, orient=tk.VERTICAL, command=self.obj_tree.yview)
        self.obj_tree.configure(yscrollcommand=vsb.set)
        self.obj_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.obj_tree.bind("<<TreeviewSelect>>", self._obj_selected)

        bb = ttk.Frame(fr)
        bb.pack(fill=tk.X, padx=4)
        ttk.Button(bb, text="＋ Nuevo",  command=self._new_obj ).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(bb, text="🗑 Borrar", command=self._del_obj ).pack(side=tk.LEFT, padx=2)

        # Formulario edición
        form = ttk.LabelFrame(fr, text=" Editar objeto ")
        form.pack(fill=tk.X, padx=4, pady=4)

        simple_fields = [("ID","id"),("Nombre","name"),("Noun","noun"),
                         ("Ubicación","location"),("Peso","weight"),("Key (llave)","key")]
        self._obj_w = {}
        for i, (label, key) in enumerate(simple_fields):
            ttk.Label(form, text=label+":").grid(row=i, column=0, sticky=tk.W,
                                                   padx=6, pady=2)
            w = tk.Entry(form, width=28, font=self.fnt_ui, relief=tk.FLAT)
            w.grid(row=i, column=1, sticky=tk.EW, padx=4)
            self._obj_w[key] = w

        ttk.Label(form, text="Descripción:").grid(row=len(simple_fields), column=0,
                                                   sticky=tk.NW, padx=6, pady=2)
        _f, self._obj_w["description"] = self._make_searchable_text(form, height=3, width=28,
                                                                    ruler=True)
        _f.grid(row=len(simple_fields), column=1, sticky=tk.EW, padx=4, pady=2)

        # Checkboxes
        cb_fr = ttk.Frame(form)
        cb_fr.grid(row=len(simple_fields)+1, column=0, columnspan=2, sticky=tk.W, padx=4)
        self._obj_cb = {}
        for cb in ["wearable","container","openable","open","locked","light_source","lit"]:
            v = tk.BooleanVar()
            ttk.Checkbutton(cb_fr, text=cb, variable=v).pack(side=tk.LEFT, padx=3)
            self._obj_cb[cb] = v

        ttk.Button(form, text="💾 Guardar objeto",
                   command=self._apply_obj).grid(row=len(simple_fields)+2, column=0,
                                                  columnspan=2, pady=6)
        form.columnconfigure(1, weight=1)

    # ─── Tab: Vocabulario ─────────────────────────────────────────────────

    def _build_vocab_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Vocabulario ")

        self._vocab_trees = {}
        self._vocab_bold  = tkfont.Font(family="Courier", size=10, weight="bold")
        SECTIONS = [("verbs","Verbos"),("nouns","Nombres"),("prepositions","Preposiciones")]

        inner = ttk.Notebook(fr)
        inner.pack(fill=tk.BOTH, expand=True)

        for key, title in SECTIONS:
            pf = ttk.Frame(inner)
            inner.add(pf, text=" " + title + " ")

            # Botones debajo — empaquetar ANTES que el tree
            bf = tk.Frame(pf)
            bf.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)
            ttk.Button(bf, text="+ Anadir",
                       command=lambda k=key: self._vocab_add(k)).pack(side=tk.LEFT, padx=2)
            ttk.Button(bf, text="Editar",
                       command=lambda k=key: self._vocab_edit_sel(k)).pack(side=tk.LEFT, padx=2)
            ttk.Button(bf, text="Borrar",
                       command=lambda k=key: self._vocab_del(k)).pack(side=tk.LEFT, padx=2)

            vsb = ttk.Scrollbar(pf, orient=tk.VERTICAL)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)

            tree = ttk.Treeview(pf, columns=("palabra","sinonimos"),
                                show="headings", selectmode="browse",
                                yscrollcommand=vsb.set)
            vsb.configure(command=tree.yview)
            tree.heading("palabra",   text="Palabra")
            tree.heading("sinonimos", text="Sinonimos")
            tree.column("palabra",   width=120, minwidth=80,  anchor=tk.W, stretch=False)
            tree.column("sinonimos", width=100, minwidth=80,  anchor=tk.W, stretch=True)
            tree.tag_configure("word",    font=self._vocab_bold)
            tree.tag_configure("builtin", font=self._vocab_bold,
                               foreground="#556688", background="#0d1b2a")
            tree.pack(fill=tk.BOTH, expand=True)
            tree.bind("<Double-Button-1>", lambda e, k=key: self._vocab_edit_sel(k))

            self._vocab_trees[key] = tree

    # ─── Tab: Variables ───────────────────────────────────────────────────

    def _build_vars_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Variables ")

        # Treeview con columnas Variable / Valor inicial / Valor actual
        cols = ("Variable", "Valor inicial", "Valor actual")
        self.vars_tree = ttk.Treeview(fr, columns=cols, show="headings", height=12)
        for c, w in zip(cols, (110, 90, 90)):
            self.vars_tree.heading(c, text=c)
            self.vars_tree.column(c, width=w, anchor=tk.W)
        vsb = ttk.Scrollbar(fr, orient=tk.VERTICAL, command=self.vars_tree.yview)
        self.vars_tree.configure(yscrollcommand=vsb.set)
        self.vars_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4,0), pady=4)
        vsb.pack(side=tk.LEFT, fill=tk.Y, pady=4)

        # Botones y edición
        bf = ttk.Frame(fr)
        bf.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(bf, text="+ Nueva", command=self._var_new).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Borrar",  command=self._var_del).pack(side=tk.LEFT, padx=2)

        # Edición inline
        ef = ttk.LabelFrame(fr, text="Editar variable")
        ef.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(ef, text="Nombre:").grid(row=0, column=0, padx=4, pady=3, sticky=tk.W)
        self.var_name_e = tk.Entry(ef, font=self.fnt_ui, relief=tk.FLAT, width=16)
        self.var_name_e.grid(row=0, column=1, padx=4, pady=3, sticky=tk.EW)

        ttk.Label(ef, text="Valor inicial:").grid(row=1, column=0, padx=4, pady=3, sticky=tk.W)
        self.var_val_e = tk.Entry(ef, font=self.fnt_ui, relief=tk.FLAT, width=16)
        self.var_val_e.grid(row=1, column=1, padx=4, pady=3, sticky=tk.EW)
        ttk.Button(ef, text="Guardar inicial", command=self._var_save).grid(
            row=1, column=2, padx=4, pady=3)

        ttk.Separator(ef, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=3, sticky=tk.EW, padx=4, pady=2)

        self.lbl_actual = ttk.Label(ef, text="Valor actual:",
                                     foreground="#81c784")
        self.lbl_actual.grid(row=3, column=0, padx=4, pady=3, sticky=tk.W)
        self.var_actual_e = tk.Entry(ef, font=self.fnt_ui, relief=tk.FLAT, width=16,
                                      disabledbackground="#1a2a1a",
                                      disabledforeground="#556655",
                                      state=tk.DISABLED)
        self.var_actual_e.grid(row=3, column=1, padx=4, pady=3, sticky=tk.EW)
        self.btn_set_actual = ttk.Button(ef, text="Aplicar en juego",
                                          command=self._var_set_actual,
                                          state=tk.DISABLED)
        self.btn_set_actual.grid(row=3, column=2, padx=4, pady=3)

        ef.columnconfigure(1, weight=1)
        self.vars_tree.bind("<<TreeviewSelect>>", self._var_selected)

    # ─── Tab: Timers ──────────────────────────────────────────────────────

    def _build_timers_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Timers ")

        pw = ttk.PanedWindow(fr, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True)

        # ── Izquierda: lista ─────────────────────────────────────────────
        lf = ttk.Frame(pw)
        pw.add(lf, weight=1)

        ttk.Label(lf, text="Timers").pack(anchor=tk.W, padx=4, pady=(4, 1))

        list_fr = tk.Frame(lf)
        list_fr.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.timer_list = tk.Listbox(list_fr, font=self.fnt_ui,
                                      selectmode=tk.SINGLE,
                                      bg="#0d1b2a", fg="#c8d8e8",
                                      selectbackground="#1a4a8a",
                                      selectforeground="#ffffff",
                                      activestyle="none",
                                      relief=tk.FLAT, borderwidth=0)
        tsb = ttk.Scrollbar(list_fr, orient=tk.VERTICAL, command=self.timer_list.yview)
        self.timer_list.configure(yscrollcommand=tsb.set)
        tsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.timer_list.pack(fill=tk.BOTH, expand=True)
        self.timer_list.bind("<<ListboxSelect>>", self._timer_list_select)

        bf = tk.Frame(lf)
        bf.pack(fill=tk.X, padx=2, pady=2)
        ttk.Button(bf, text="+ Nuevo",  command=self._timer_new).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Borrar",   command=self._timer_del).pack(side=tk.LEFT, padx=2)

        # ── Derecha: formulario ──────────────────────────────────────────
        rf = ttk.Frame(pw)
        pw.add(rf, weight=2)

        ttk.Label(rf, text="ID:").grid(row=0, column=0, sticky=tk.W, padx=8, pady=3)
        self.timer_id = tk.Entry(rf, width=22, font=self.fnt_ui, relief=tk.FLAT)
        self.timer_id.grid(row=0, column=1, sticky=tk.W)

        ttk.Label(rf, text="Nombre:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=3)
        self.timer_name = tk.Entry(rf, width=34, font=self.fnt_ui, relief=tk.FLAT)
        self.timer_name.grid(row=1, column=1, sticky=tk.EW, padx=4)

        ttk.Label(rf, text="Turnos:").grid(row=2, column=0, sticky=tk.W, padx=8, pady=3)
        self.timer_turns = tk.Entry(rf, width=8, font=self.fnt_ui, relief=tk.FLAT)
        self.timer_turns.grid(row=2, column=1, sticky=tk.W, padx=4)

        self.timer_active = tk.BooleanVar()
        self.timer_loop   = tk.BooleanVar()
        cb_fr = ttk.Frame(rf)
        cb_fr.grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=8, pady=2)
        ttk.Checkbutton(cb_fr, text="Activo al inicio", variable=self.timer_active).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(cb_fr, text="Loop",             variable=self.timer_loop  ).pack(side=tk.LEFT, padx=4)

        ttk.Label(rf, text="on_expire (BASIC):").grid(row=4, column=0, sticky=tk.NW, padx=8, pady=3)
        _f, self.timer_expire = self._make_searchable_text(rf, height=8, width=34)
        _f.grid(row=4, column=1, sticky=tk.NSEW, padx=4, pady=2)

        ttk.Button(rf, text="Guardar timer",
                   command=self._apply_timer).grid(row=5, column=0, columnspan=2, pady=6)

        rf.columnconfigure(1, weight=1)
        rf.rowconfigure(4, weight=1)

    # ─── Tab: Condacts ────────────────────────────────────────────────────

    # Vocabulario del mini-BASIC para resaltado y autocompletado
    BASIC_KEYWORDS = ["IF", "THEN", "ELSE", "ENDIF", "ON", "ENDON",
                      "AND", "OR", "NOT", "MATCH"]
    BASIC_COMMANDS = ["PRINT", "PRINTLN", "LET", "ADDSCORE", "GOTO", "DESC",
                      "SCORE", "END", "QUIT", "NEWLINE", "GET", "DROP", "LIT",
                      "UNLIT", "OPEN", "CLOSE", "LOCK", "UNLOCK", "DESTROY",
                      "WEAR", "REMOVE", "CREATE", "PUTIN", "TAKEOUT", "PUT",
                      "TIMER_START", "TIMER_STOP", "TIMER_RESET", "REM"]
    BASIC_CONDITIONS = ["AT", "NOTAT", "CARRIED", "NOTCARR", "PRESENT",
                        "ABSENT", "WORN", "NOTWORN", "ISAT", "DARK", "CHANCE",
                        "TIMER", "ZERO", "NOTZERO", "EQ", "GT", "LT",
                        "HASOBJOPEN", "VERB", "NOUN1", "NOUN2"]

    _RE_HL = {
        "rem":  re.compile(r'(?m)^[ \t]*(?:\d+[ \t]+)?REM\b.*$'),
        "str":  re.compile(r'"[^"\n]*"'),
        "kw":   re.compile(r'\b(' + '|'.join(BASIC_KEYWORDS) + r')\b'),
        "cmd":  re.compile(r'\b(' + '|'.join(c for c in BASIC_COMMANDS if c != 'REM') + r')\b'),
        "cond": re.compile(r'\b(' + '|'.join(BASIC_CONDITIONS) + r')\b'),
        "num":  re.compile(r'\b\d+\b'),
    }

    def _build_condacts_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Condacts ")
        self._condact_nb = ttk.Notebook(fr)   # referencia directa
        self._condact_nb.pack(fill=tk.BOTH, expand=True)
        self._condact_w = {}
        self._condact_sections = ["on_start","before_turn","after_turn","on_end","responses"]
        for section in self._condact_sections:
            sf = ttk.Frame(self._condact_nb)
            self._condact_nb.add(sf, text=section)
            _f, t = self._make_code_editor(sf, section)
            _f.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            self._condact_w[section] = t
        bf = ttk.Frame(fr)
        bf.pack(pady=4)
        ttk.Button(bf, text="Aplicar condacts",
                   command=self._apply_condacts).pack(side=tk.LEFT, padx=4)
        ttk.Label(bf, text="Ctrl+Espacio: autocompletar · clic en el margen: breakpoint",
                  foreground="#667788").pack(side=tk.LEFT, padx=8)

    # ── Editor de código con gutter, resaltado y breakpoints ───────────────

    def _make_code_editor(self, parent, section):
        """Crea un editor de código: gutter (números + breakpoints) + Text
        con resaltado de sintaxis BASIC + barra de búsqueda Ctrl+F."""
        frame = ttk.Frame(parent)
        body  = ttk.Frame(frame)

        gutter = tk.Text(body, width=5, padx=2, takefocus=0, bd=0,
                         bg="#16202e", fg="#557099", state=tk.DISABLED,
                         font=self.fnt_code, cursor="hand2", wrap=tk.NONE)
        t = tk.Text(body, wrap=tk.NONE, undo=True, font=self.fnt_code,
                    bg="#0f1623", fg="#d8e2f0", insertbackground="#ffffff",
                    selectbackground="#1a4a8a")
        vs = ttk.Scrollbar(body, orient=tk.VERTICAL)
        hs = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=t.xview)

        def _on_yscroll(first, last):
            vs.set(first, last)
            gutter.yview_moveto(first)
        t.configure(yscrollcommand=_on_yscroll, xscrollcommand=hs.set)

        def _vs_cmd(*args):
            t.yview(*args)
            gutter.yview_moveto(t.yview()[0])
        vs.configure(command=_vs_cmd)

        # Colores de sintaxis
        t.tag_configure("kw",      foreground="#66b3ff")
        t.tag_configure("cmd",     foreground="#ffcc66")
        t.tag_configure("cond",    foreground="#7fd6a0")
        t.tag_configure("num",     foreground="#c0a0ff")
        t.tag_configure("str",     foreground="#e69ae6")
        t.tag_configure("rem",     foreground="#5a6b80")
        t.tag_configure("bp_line", background="#3a1620")

        bar = SearchBar(frame, t)

        def _show_bar(event=None):
            bar.pack(fill=tk.X, before=body)
            bar._entry.focus_set()
            bar._entry.select_range(0, tk.END)
            bar._do_search()
            return "break"

        gutter.pack(side=tk.LEFT, fill=tk.Y)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body.pack(fill=tk.BOTH, expand=True)

        t.bind("<Control-f>", _show_bar)
        t.bind("<Control-F>", _show_bar)
        t.bind("<KeyRelease>", lambda e, s=section: self._code_changed(s))
        t.bind("<Control-space>", lambda e, s=section: self._autocomplete(s))
        gutter.bind("<Button-1>", lambda e, s=section: self._gutter_click(e, s))

        self._code_gutters[section] = gutter
        return frame, t

    @staticmethod
    def _norm_code_line(line):
        """Normaliza una línea como hace PAWSBasic: sin indentación ni
        número de línea. Devuelve '' si no es 'breakable'."""
        s = line.strip()
        m = re.match(r'\d+\s+', s)
        if m:
            s = s[m.end():].strip()
        if not s or s.upper().startswith('REM'):
            return ''
        return s

    def _code_changed(self, section):
        """Debounce: re-resalta y refresca el gutter 200 ms tras teclear."""
        pending = self._code_after.get(section)
        if pending:
            try:
                self.root.after_cancel(pending)
            except Exception:
                pass
        self._code_after[section] = self.root.after(
            200, lambda: self._refresh_code_view(section))

    def _refresh_code_view(self, section):
        self._code_after[section] = None
        t = self._condact_w.get(section)
        if not t:
            return
        self._highlight_code(t)
        self._refresh_gutter(section)
        self._mark_breakpoint_lines(section)

    def _highlight_code(self, t):
        content = t.get("1.0", "end-1c")
        for tag in ("kw", "cmd", "cond", "num", "str", "rem"):
            t.tag_remove(tag, "1.0", tk.END)
        for tag in ("kw", "cmd", "cond", "num", "str", "rem"):
            for m in self._RE_HL[tag].finditer(content):
                t.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        # strings y REM por encima del resto
        t.tag_raise("str")
        t.tag_raise("rem")

    def _refresh_gutter(self, section):
        t = self._condact_w[section]
        g = self._code_gutters[section]
        lines = t.get("1.0", "end-1c").split("\n")
        bps = self.breakpoints.get(section, set())
        out = []
        for i, line in enumerate(lines, 1):
            norm = self._norm_code_line(line)
            mark = "●" if norm and norm in bps else " "
            out.append(f"{mark}{i:>4}")
        g.config(state=tk.NORMAL)
        g.delete("1.0", tk.END)
        g.insert("1.0", "\n".join(out))
        g.config(state=tk.DISABLED)
        g.tag_configure("bp", foreground="#ff5555")
        # colorear las marcas ●
        for i, line in enumerate(lines, 1):
            norm = self._norm_code_line(line)
            if norm and norm in bps:
                g.tag_add("bp", f"{i}.0", f"{i}.1")
        g.yview_moveto(t.yview()[0])

    def _mark_breakpoint_lines(self, section):
        t = self._condact_w[section]
        t.tag_remove("bp_line", "1.0", tk.END)
        bps = self.breakpoints.get(section, set())
        if not bps:
            return
        lines = t.get("1.0", "end-1c").split("\n")
        for i, line in enumerate(lines, 1):
            norm = self._norm_code_line(line)
            if norm and norm in bps:
                t.tag_add("bp_line", f"{i}.0", f"{i}.end")

    def _gutter_click(self, event, section):
        g = self._code_gutters[section]
        t = self._condact_w[section]
        line_no = int(g.index(f"@{event.x},{event.y}").split('.')[0])
        line = t.get(f"{line_no}.0", f"{line_no}.end")
        norm = self._norm_code_line(line)
        if not norm:
            return
        bps = self.breakpoints.setdefault(section, set())
        if norm in bps:
            bps.discard(norm)
            self.sv_status.set(f"Breakpoint quitado: {norm[:50]}")
        else:
            bps.add(norm)
            self.sv_status.set(f"Breakpoint: {norm[:50]}  (líneas idénticas comparten breakpoint)")
        self._refresh_gutter(section)
        self._mark_breakpoint_lines(section)

    def has_breakpoint(self, section, line):
        """API para el depurador del intérprete embebido."""
        bps = self.breakpoints.get(section)
        if not bps:
            return False
        return self._norm_code_line(line) in bps

    def any_breakpoints(self):
        return any(v for v in self.breakpoints.values())

    # ── Autocompletado (Ctrl+Espacio) ────────────────────────────────────────

    def _autocomplete(self, section):
        t = self._condact_w[section]
        before = t.get("insert linestart", "insert")
        m = re.search(r'[\w]+$', before)
        prefix = m.group(0) if m else ''
        cands = sorted(set(
            list(self.game.get("locations", {}).keys()) +
            list(self.game.get("objects", {}).keys()) +
            list(self.game.get("timers", {}).keys()) +
            list(self.game.get("variables", {}).keys()) +
            self.BASIC_KEYWORDS + self.BASIC_COMMANDS + self.BASIC_CONDITIONS))
        if prefix:
            pl = prefix.lower()
            cands = [c for c in cands if c.lower().startswith(pl) and c != prefix]
        if not cands:
            return "break"

        top = tk.Toplevel(self.root)
        top.wm_overrideredirect(True)
        bbox = t.bbox("insert") or (0, 0, 0, 16)
        top.geometry(f"+{t.winfo_rootx() + bbox[0]}+{t.winfo_rooty() + bbox[1] + bbox[3] + 2}")
        lb = tk.Listbox(top, height=min(10, len(cands)), font=self.fnt_code,
                        bg="#16202e", fg="#d8e2f0",
                        selectbackground="#1a4a8a", activestyle="none")
        for c in cands[:60]:
            lb.insert(tk.END, c)
        lb.pack()
        lb.selection_set(0)
        lb.focus_set()

        def _accept(event=None):
            sel = lb.curselection()
            if sel:
                word = lb.get(sel[0])
                if prefix:
                    t.delete(f"insert-{len(prefix)}c", "insert")
                t.insert("insert", word)
            top.destroy()
            t.focus_set()
            self._code_changed(section)
            return "break"

        def _cancel(event=None):
            top.destroy()
            t.focus_set()
            return "break"

        lb.bind("<Return>", _accept)
        lb.bind("<Tab>", _accept)
        lb.bind("<Double-Button-1>", _accept)
        lb.bind("<Escape>", _cancel)
        lb.bind("<FocusOut>", _cancel)
        return "break"

    # ─── Tab: Problemas (validación en vivo) ────────────────────────────────

    def _build_problems_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=" Problemas ")
        self._problems_tab_frame = fr

        top = ttk.Frame(fr)
        top.pack(fill=tk.X, pady=3)
        ttk.Button(top, text="Revalidar (F7)",
                   command=lambda: self._run_validation(silent=False)
                   ).pack(side=tk.LEFT, padx=6)
        self._problems_info = ttk.Label(top, text="")
        self._problems_info.pack(side=tk.LEFT, padx=8)
        ttk.Label(top, text="Doble clic: ir al elemento",
                  foreground="#667788").pack(side=tk.RIGHT, padx=8)

        cols = ("tipo", "donde", "mensaje")
        tree = ttk.Treeview(fr, columns=cols, show="headings")
        tree.heading("tipo", text="Tipo")
        tree.column("tipo", width=64, stretch=False)
        tree.heading("donde", text="Dónde")
        tree.column("donde", width=190, stretch=False)
        tree.heading("mensaje", text="Mensaje")
        tree.column("mensaje", width=430)
        tree.tag_configure("error", foreground="#cc3333")
        tree.tag_configure("aviso", foreground="#aa7711")
        sb = ttk.Scrollbar(fr, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        tree.bind("<Double-1>", self._problem_goto)
        self.problems_tree = tree

        self.root.bind("<F7>", lambda e: self._run_validation(silent=False))

    def _run_validation(self, silent=True):
        """Ejecuta los validadores del compilador y puebla el panel."""
        if validate_game is None or not hasattr(self, 'problems_tree'):
            return
        game = self.game
        try:
            errors = list(validate_game(game))
            s_err, s_warn = validate_scripts(game)
        except Exception as e:
            errors, s_err, s_warn = [f"validador: excepción interna: {e}"], [], []
        errors += s_err
        warnings = list(s_warn)
        if check_vocabulary:
            try:
                trunc, dups = check_vocabulary(game)
                warnings += [f"vocabulary: {d}" for d in dups]
                warnings += [f"vocabulary: alias >5 letras {w}" for w in trunc]
            except Exception:
                pass

        # Comprobaciones básicas: al menos una localización y un start válido.
        locs = game.get('locations', {})
        meta = game.get('metadata', {})
        start = meta.get('start_location')
        if isinstance(start, str):
            start = start.strip()
        if not locs:
            errors.insert(0, 'metadata.start_location: el juego no tiene ninguna '
                             'localización.')
        elif not start:
            errors.insert(0, 'metadata.start_location: no hay localización inicial '
                             'definida.')
        elif start not in locs:
            errors.insert(0, "metadata.start_location: '%s' no es una localización "
                             "válida." % start)

        # Avisos de paridad entre intérpretes: características usadas por el juego
        # que algún target no soporta (mismo juego, comportamiento distinto).
        try:
            import capabilities
            for t, lbl in (('spectrum', 'ZX Spectrum / Next'),
                           ('cpc', 'Amstrad CPC')):
                u = capabilities.unsupported(game, t)
                parts = []
                if u['condacts']:
                    parts.append('comandos ' + ', '.join(u['condacts']))
                if u['predicates']:
                    parts.append('predicados ' + ', '.join(u['predicates']))
                if u['features']:
                    parts.append('funciones ' + ', '.join(
                        capabilities.FEATURE_LABEL.get(f, f)
                        for f in u['features']))
                if parts:
                    warnings.append('%s no soporta: %s' % (lbl, '; '.join(parts)))
        except Exception:
            pass

        tree = self.problems_tree
        tree.delete(*tree.get_children())
        for msg in errors:
            tree.insert("", tk.END, tags=("error",),
                        values=("ERROR", self._problem_where(msg), msg))
        for msg in warnings:
            tree.insert("", tk.END, tags=("aviso",),
                        values=("aviso", self._problem_where(msg), msg))

        n_e, n_w = len(errors), len(warnings)
        label = f" Problemas ({n_e + n_w}) " if (n_e or n_w) else " Problemas "
        try:
            self.nb.tab(self._problems_tab_frame, text=label)
        except Exception:
            pass
        self._problems_info.config(text=f"{n_e} errores · {n_w} avisos")
        if not silent:
            self.nb.select(self._problems_tab_frame)
            self.sv_status.set(f"Validación: {n_e} errores, {n_w} avisos")
        return n_e, n_w

    @staticmethod
    def _problem_where(msg):
        head = msg.split(':', 1)[0].strip()
        return head[:42]

    def _problem_goto(self, event=None):
        sel = self.problems_tree.selection()
        if not sel:
            return
        msg = self.problems_tree.item(sel[0], "values")[2]

        m = re.match(r'locations\.([\w]+)', msg)
        if m and m.group(1) in self.game.get("locations", {}):
            lid = m.group(1)
            self.sel = lid
            if lid in self.positions:
                self.level = self.positions[lid][2]
            self.nb.select(1)
            self._refresh_loc_list()
            self._load_loc_to_form(lid)
            self._redraw()
            return
        m = re.match(r'objects\.([\w]+)', msg) or \
            re.search(r"objects: '?([\w]+)'?", msg)
        if m and m.group(1) in self.game.get("objects", {}):
            self.nb.select(2)
            oid = m.group(1)
            try:
                self.obj_tree.selection_set(oid)
                self.obj_tree.see(oid)
                self._load_obj_to_form(oid)
            except Exception:
                pass
            return
        m = re.match(r'condacts\.(\w+)', msg)
        if m:
            self.nb.select(6)
            if m.group(1) in self._condact_sections:
                self._condact_nb.select(self._condact_sections.index(m.group(1)))
            return
        if msg.startswith('timers.'):
            self.nb.select(5)
            return
        if msg.startswith('vocabulary'):
            self.nb.select(3)
            return
        if msg.startswith(('metadata', 'start_location')):
            self.nb.select(0)
            return

    # ─── Estadísticas y auditoría de puntos ──────────────────────────────────

    def _iter_scripts(self):
        """(nombre, texto) de todos los scripts BASIC del juego."""
        def as_text(v):
            if isinstance(v, str):
                return v
            if isinstance(v, list) and v and isinstance(v[0], str):
                return "\n".join(v)
            return ""
        for k, v in self.game.get("condacts", {}).items():
            yield f"condacts.{k}", as_text(v)
        for lid, loc in self.game.get("locations", {}).items():
            for hook in ("on_enter", "on_look"):
                yield f"locations.{lid}.{hook}", as_text(loc.get(hook))
        for tid, tim in self.game.get("timers", {}).items():
            yield f"timers.{tid}.on_expire", as_text(tim.get("on_expire"))

    def _show_stats(self):
        g = self.game
        locs = g.get("locations", {})
        objs = g.get("objects", {})
        vocab = g.get("vocabulary", {})
        n_words_vocab = sum(len(v or {}) for v in vocab.values())
        n_aliases = sum(len(a or []) for sec in vocab.values()
                        for a in (sec or {}).values())

        script_lines = 0
        n_on = 0
        score_hits = []   # (sección, n)
        for name, text in self._iter_scripts():
            if not text:
                continue
            script_lines += len([l for l in text.split("\n") if l.strip()])
            n_on += len(re.findall(r'(?m)^\s*(?:\d+\s+)?ON\b', text))
            for mm in re.finditer(r'ADDSCORE\s+(\d+)', text):
                score_hits.append((name, int(mm.group(1))))

        text_words = sum(len((loc.get("description") or "").split())
                         for loc in locs.values())
        text_words += sum(len((o.get("description") or "").split())
                          for o in objs.values())
        text_words += len((g.get("metadata", {}).get("start_message") or "").split())

        total_score = sum(n for _, n in score_hits)
        max_score = g.get("metadata", {}).get("max_score", 0)

        lines = []
        lines.append(f"Localizaciones:     {len(locs)}")
        lines.append(f"Objetos:            {len(objs)}"
                     f"  (fijos: {sum(1 for o in objs.values() if 'fixed' in (o.get('attributes') or []))})")
        lines.append(f"Vocabulario:        {n_words_vocab} entradas, {n_aliases} aliases")
        lines.append(f"Timers:             {len(g.get('timers', {}))}")
        lines.append(f"Variables:          {len(g.get('variables', {}))}")
        lines.append(f"Líneas de script:   {script_lines}  (bloques ON: {n_on})")
        lines.append(f"Palabras de prosa:  ~{text_words}")
        lines.append("")
        lines.append("── Auditoría de puntos ──")
        lines.append(f"max_score declarado: {max_score}")
        lines.append(f"Suma de ADDSCORE:    {total_score}"
                     f"  ({'=' if total_score == max_score else '≠'} max_score)")
        if total_score != max_score:
            lines.append("  ¡Atención!: si cada ADDSCORE se cobra una sola vez,")
            lines.append("  la suma debería coincidir con max_score.")
        lines.append("")
        for name, n in score_hits:
            lines.append(f"  +{n:<4} {name}")

        win = tk.Toplevel(self.root)
        win.title("Estadísticas del juego")
        win.geometry("560x520")
        st = scrolledtext.ScrolledText(win, font=self.fnt_code,
                                       bg="#0f1623", fg="#d8e2f0")
        st.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        st.insert("1.0", "\n".join(lines))
        st.config(state=tk.DISABLED)
        win.bind("<Escape>", lambda e: win.destroy())

    # ─── Consistencia geográfica del mapa ────────────────────────────────────

    # Proyección geográfica de cada dirección: (dx, dy, dnivel).
    # A diferencia de DIR_DELTA (layout del canvas), aquí U/D cambian de
    # nivel y NO se desplazan en el plano.
    GEO_DELTA = {'N': (0, -1, 0), 'S': (0, 1, 0), 'E': (1, 0, 0),
                 'O': (-1, 0, 0), 'U': (0, 0, 1), 'D': (0, 0, -1)}

    def _geo_consistency(self):
        """
        Comprueba la coherencia geográfica de las salidas. Devuelve
        (errores, avisos) como listas de strings.

        1. Reciprocidad: si A dice que B está al Sur, B debe decir que A
           está al Norte. Una vuelta por otra dirección es un error.
        2. Geometría global: se deducen coordenadas (x, y, nivel) por BFS;
           si una salida lleva a una casilla que no cuadra con la posición
           ya deducida del destino, el mapa se pliega sobre sí mismo.
        3. Solapamientos: dos localizaciones distintas en la misma celda
           deducida.
        Los puntos 2 y 3 son avisos (a veces son decisiones de diseño);
        el 1 es un error: desorienta siempre al jugador.
        """
        locs = self.game.get("locations", {})
        errors, warnings = [], []
        bad_pairs = set()

        # 1 ── Reciprocidad direccional
        for lid, loc in locs.items():
            for d, dest in (loc.get("exits") or {}).items():
                if not dest or dest not in locs or d not in DIR_OPPOSITE:
                    continue
                opp  = DIR_OPPOSITE[d]
                back = [d2 for d2, b in (locs[dest].get("exits") or {}).items()
                        if b == lid]
                if not back:
                    warnings.append(
                        f"{lid} →{d}→ {dest}: sin salida de vuelta "
                        f"(¿camino de un solo sentido?)")
                elif opp not in back:
                    pair = frozenset((lid, dest))
                    if pair not in bad_pairs:
                        bad_pairs.add(pair)
                        errors.append(
                            f"{lid} dice que {dest} está al {DIR_NAMES[d]}, "
                            f"pero {dest} dice que {lid} está al "
                            f"{'/'.join(DIR_NAMES[b] for b in back)} "
                            f"(la vuelta debería ser {DIR_NAMES[opp]})")

        # 2 ── Geometría global por BFS (por componente conexa)
        coords, comp = {}, {}
        cid = 0
        for start in sorted(locs):
            if start in coords:
                continue
            cid += 1
            coords[start], comp[start] = (0, 0, 0), cid
            queue = [start]
            while queue:
                cur = queue.pop(0)
                cx, cy, cz = coords[cur]
                for d, dest in sorted((locs[cur].get("exits") or {}).items()):
                    if not dest or dest not in locs or d not in self.GEO_DELTA:
                        continue
                    dx, dy, dz = self.GEO_DELTA[d]
                    want = (cx + dx, cy + dy, cz + dz)
                    if dest not in coords:
                        coords[dest], comp[dest] = want, cid
                        queue.append(dest)
                    elif coords[dest] != want and \
                            frozenset((cur, dest)) not in bad_pairs:
                        warnings.append(
                            f"geometría: {cur} →{DIR_NAMES[d]}→ {dest} no "
                            f"cuadra con la posición de {dest} deducida por "
                            f"el resto del mapa (el mapa se pliega aquí)")

        # 3 ── Solapamientos en la misma celda deducida
        seen = {}
        for lid in sorted(coords):
            key = (comp[lid], coords[lid])
            if key in seen:
                x, y, z = coords[lid]
                warnings.append(
                    f"solapamiento: '{seen[key]}' y '{lid}' caen en la misma "
                    f"posición deducida ({x},{y}) nivel {z:+d}")
            else:
                seen[key] = lid

        return errors, warnings

    def _check_map_consistency(self):
        """Muestra el informe de consistencia geográfica en una ventana."""
        errors, warnings = self._geo_consistency()
        lines = []
        if not errors and not warnings:
            lines.append("✓ Mapa geográficamente consistente:")
            lines.append("  todas las vueltas concuerdan y la geometría cuadra.")
        if errors:
            lines.append(f"ERRORES DE RECIPROCIDAD ({len(errors)})")
            lines.append("─" * 60)
            for e in errors:
                lines.append("  ✗ " + e)
            lines.append("")
        if warnings:
            lines.append(f"AVISOS ({len(warnings)})")
            lines.append("─" * 60)
            for w in warnings:
                lines.append("  ! " + w)

        win = tk.Toplevel(self.root)
        win.title("Consistencia geográfica del mapa")
        win.geometry("640x440")
        st = scrolledtext.ScrolledText(win, font=self.fnt_code, wrap=tk.WORD,
                                       bg="#0f1623", fg="#d8e2f0")
        st.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        st.insert("1.0", "\n".join(lines))
        st.config(state=tk.DISABLED)
        win.bind("<Escape>", lambda e: win.destroy())
        self.sv_status.set(f"Consistencia: {len(errors)} errores, "
                           f"{len(warnings)} avisos")

    # ─── Refactor de IDs en scripts ──────────────────────────────────────────

    def _refactor_id_in_scripts(self, old, new):
        """Reemplaza old→new como palabra completa en todos los scripts.
        Devuelve el número de reemplazos."""
        pat = re.compile(r'\b' + re.escape(old) + r'\b')
        count = 0

        cond = self.game.get("condacts", {})
        for k, v in cond.items():
            if isinstance(v, str) and v:
                v2, n = pat.subn(new, v)
                if n:
                    cond[k] = v2
                    count += n

        def fix_hook(holder, key):
            nonlocal count
            v = holder.get(key)
            if isinstance(v, str) and v:
                v2, n = pat.subn(new, v)
                if n:
                    holder[key] = v2
                    count += n
            elif isinstance(v, list) and v and isinstance(v[0], str):
                new_list = []
                for line in v:
                    l2, n = pat.subn(new, line)
                    count += n
                    new_list.append(l2)
                holder[key] = new_list

        for loc in self.game.get("locations", {}).values():
            fix_hook(loc, "on_enter")
            fix_hook(loc, "on_look")
        for tim in self.game.get("timers", {}).values():
            fix_hook(tim, "on_expire")

        if count:
            self._load_condacts_to_form()
        return count

    # ═══════════════════════════════════════════════════════════════════════════
    # DIBUJO DEL MAPA
    # ═══════════════════════════════════════════════════════════════════════════

    def _plat(self):
        """Plataforma de imagenes a previsualizar ('128k' o 'next')."""
        v = getattr(self, '_plataforma', None)
        return v.get() if v is not None else 'next'

    def _img_dir_loc(self):
        """(carpeta, extensiones) de imagenes de localizacion segun plataforma."""
        if not self.filepath:
            return None, ()
        base = os.path.join(os.path.dirname(os.path.abspath(self.filepath)), 'img')
        if self._plat() == 'next':
            return os.path.join(base, 'Original'), ('.png', '.jpg', '.jpeg')
        return os.path.join(base, 'Spectrum'), ('.scr',)

    def _img_file_for(self, lid):
        """Ruta del fichero de imagen de la localizacion lid (o None).
        128K: img/Spectrum/<id>.scr; Next: img/Original/<id>.png|jpg.
        Si no existe, cae al master de img/Original (.png/.jpg)."""
        d, exts = self._img_dir_loc()
        if d:
            for ext in exts:
                p = os.path.join(d, lid + ext)
                if os.path.isfile(p):
                    return p
        # Fallback: master en img/Original
        if self.filepath:
            orig = os.path.join(os.path.dirname(os.path.abspath(self.filepath)),
                                'img', 'Original')
            for ext in ('.png', '.jpg', '.jpeg'):
                p = os.path.join(orig, lid + ext)
                if os.path.isfile(p):
                    return p
        return None

    def _apply_plataforma(self):
        """Al cambiar la plataforma de preview, refresca el mapa y las imagenes."""
        try:
            self._redraw()
        except Exception:
            pass
        lid = getattr(self, '_loc_img_lid', None)
        if lid:
            self._refresh_loc_img(lid)
        try:
            self._refresh_menu_img()
        except Exception:
            pass

    def _refresh_img_locs(self):
        """Conjunto de localizaciones con imagen segun la plataforma seleccionada
        (img/Spectrum/<id>.scr para 128K, img/Original/<id>.png|jpg para Next)."""
        self._img_locs = set()
        for lid in self.game.get('locations', {}):
            if self._img_file_for(lid):
                self._img_locs.add(lid)

    # Paleta ZX Spectrum (normal / brillo)
    _ZXPAL = [(0,0,0),(0,0,0xD7),(0xD7,0,0),(0xD7,0,0xD7),
              (0,0xD7,0),(0,0xD7,0xD7),(0xD7,0xD7,0),(0xD7,0xD7,0xD7)]
    _ZXPALB = [(0,0,0),(0,0,0xFF),(0xFF,0,0),(0xFF,0,0xFF),
               (0,0xFF,0),(0,0xFF,0xFF),(0xFF,0xFF,0),(0xFF,0xFF,0xFF)]

    def _scr_top_third(self, raw):
        """Decodifica el tercio superior (256x64) de un SCR de 6912 bytes o de
        un recorte de 2304 (2048 bitmap + 256 atributos). Devuelve la lista de
        64 filas, cada una con 256 colores '#rrggbb', o None si el tamaño no vale."""
        if len(raw) == 6912:
            bmp, att = raw[0:2048], raw[6144:6400]
        elif len(raw) == 2304:
            bmp, att = raw[0:2048], raw[2048:2304]
        else:
            return None
        filas = []
        for y in range(64):
            base = ((y & 7) << 8) | ((y & 0x38) << 2)   # offset ZX del tercio
            crow = y >> 3
            fila = []
            for cx in range(32):
                b = bmp[base + cx]
                a = att[crow * 32 + cx]
                pal = self._ZXPALB if (a >> 6) & 1 else self._ZXPAL
                inkc = pal[a & 7]
                paperc = pal[(a >> 3) & 7]
                for bit in range(7, -1, -1):
                    r, g, bl = inkc if (b >> bit) & 1 else paperc
                    fila.append('#%02x%02x%02x' % (r, g, bl))
            filas.append(fila)
        return filas

    def _img_top_third(self, path):
        """Carga un PNG/JPG y devuelve 64 filas de 256 colores '#rrggbb' (la tira
        256x64 de Layer 2, tal como se vera en el juego en Next)."""
        try:
            from PIL import Image
            im = Image.open(path).convert('RGB').resize((256, 64))
        except Exception:
            return None
        px = im.load()
        return [['#%02x%02x%02x' % px[x, y] for x in range(256)]
                for y in range(64)]

    def _refresh_loc_img(self, lid):
        """Pinta la imagen de la localizacion (tira 256x64) en el canvas segun la
        plataforma: .scr (ULA) en 128K, .png/.jpg (Layer 2) en Next."""
        self._loc_img_lid = lid
        cv = getattr(self, 'loc_img_canvas', None)
        if cv is None:
            return
        cv.delete('all')
        self.loc_img_photo = None
        path = self._img_file_for(lid)
        filas = None
        if path and path.lower().endswith('.scr'):
            try:
                with open(path, 'rb') as f:
                    filas = self._scr_top_third(f.read())
            except OSError:
                filas = None
        elif path and self._plat() != 'next':
            # 128K sin .scr propio: mostramos la conversion dithered (Spectrum),
            # exactamente como saldra en el export. En Next se ve el master tal cual.
            try:
                import png2spectrum
                bmp, att = png2spectrum.to_scr_topthird(path)
                filas = self._scr_top_third(bytes(bmp) + bytes(att))
            except Exception:
                filas = self._img_top_third(path)
        elif path:
            filas = self._img_top_third(path)
        if not filas:
            d, _ = self._img_dir_loc()
            sub = os.path.basename(d) if d else '?'
            cv.create_text(256, 64, text='(sin imagen en img/%s/%s)' % (sub, lid),
                           fill='#5a7a9a', font=self.fnt_ui)
            return
        img = tk.PhotoImage(width=256, height=64)
        img.put(' '.join('{' + ' '.join(f) + '}' for f in filas))
        img = img.zoom(2)                       # 256x64 -> 512x128
        cv.create_image(0, 0, anchor=tk.NW, image=img)
        self.loc_img_photo = img                # mantener referencia viva

    def _scr_full(self, raw):
        """Decodifica un SCR completo (6912 bytes) a 192 filas de 256 colores."""
        if len(raw) != 6912:
            return None
        bmp, att = raw[0:6144], raw[6144:6912]
        filas = []
        for y in range(192):
            third = y >> 6
            yy = y & 63
            base = third * 2048 + (((yy & 7) << 8) | ((yy & 0x38) << 2))
            crow = y >> 3
            fila = []
            for cx in range(32):
                b = bmp[base + cx]
                a = att[crow * 32 + cx]
                pal = self._ZXPALB if (a >> 6) & 1 else self._ZXPAL
                inkc = pal[a & 7]
                paperc = pal[(a >> 3) & 7]
                for bit in range(7, -1, -1):
                    r, g, bl = inkc if (b >> bit) & 1 else paperc
                    fila.append('#%02x%02x%02x' % (r, g, bl))
            filas.append(fila)
        return filas

    def _img_full(self, path):
        """Carga un PNG/JPG y devuelve 192 filas de 256 colores (pantalla 256x192)."""
        try:
            from PIL import Image
            im = Image.open(path).convert('RGB').resize((256, 192))
        except Exception:
            return None
        px = im.load()
        return [['#%02x%02x%02x' % px[x, y] for x in range(256)]
                for y in range(192)]

    def _refresh_menu_img(self):
        """Previsualiza la imagen de menu/titulo (screen) en metadatos, segun la
        plataforma: img/Spectrum/screen.scr (ULA) o img/Original/screen.(png|jpg)."""
        cv = getattr(self, 'menu_img_canvas', None)
        if cv is None:
            return
        cv.delete('all')
        self.menu_img_photo = None
        path = None
        if self.filepath:
            base = os.path.join(os.path.dirname(os.path.abspath(self.filepath)),
                                'img')
            if self._plat() == 'next':
                for nm in ('screen', 'menu'):
                    for ext in ('.png', '.jpg', '.jpeg'):
                        p = os.path.join(base, 'Original', nm + ext)
                        if os.path.isfile(p):
                            path = p
                            break
                    if path:
                        break
            else:
                for nm in ('screen', 'menu'):
                    p = os.path.join(base, 'Spectrum', nm + '.scr')
                    if os.path.isfile(p):
                        path = p
                        break
                if not path:                      # fallback: master de Original
                    for nm in ('screen', 'menu'):
                        for ext in ('.png', '.jpg', '.jpeg'):
                            p = os.path.join(base, 'Original', nm + ext)
                            if os.path.isfile(p):
                                path = p
                                break
                        if path:
                            break
        filas = None
        if path and path.lower().endswith('.scr'):
            try:
                with open(path, 'rb') as f:
                    filas = self._scr_full(f.read())
            except OSError:
                filas = None
        elif path and self._plat() != 'next':
            # 128K sin screen.scr propio: conversion dithered de pantalla completa
            try:
                import png2spectrum
                filas = self._scr_full(png2spectrum.to_scr_full(path))
            except Exception:
                filas = self._img_full(path)
        elif path:
            filas = self._img_full(path)
        if not filas:
            sub = 'Original' if self._plat() == 'next' else 'Spectrum'
            cv.create_text(128, 96, text='(sin screen en img/%s/)' % sub,
                           fill='#5a7a9a', font=self.fnt_ui)
            return
        img = tk.PhotoImage(width=256, height=192)
        img.put(' '.join('{' + ' '.join(f) + '}' for f in filas))
        cv.create_image(0, 0, anchor=tk.NW, image=img)
        self.menu_img_photo = img

    def _redraw(self):
        self.canvas.delete("all")
        self._refresh_img_locs()
        locs = self.game["locations"]

        # Offsets perpendiculares para flechas bidireccionales
        # N/S son verticales → offset en X; E/O son horizontales → offset en Y
        BIDIR_OFF = {'N': (7,0), 'S': (-7,0), 'E': (0,-7), 'O': (0,7)}

        # Paso 1 – dibujar flechas (mapa plano: U/D son flechas normales
        # con etiqueta Up/Dw)
        drawn_arrows = set()
        for lid, loc in locs.items():
            if lid not in self.positions:
                continue
            col, row, lev = self.positions[lid]
            if self._moving_node == lid and self._moving_px:
                cx, cy = self._moving_px
            else:
                cx, cy = self._grid_to_px(col, row)
            for direction, dest in loc.get("exits", {}).items():
                if not dest or dest not in self.positions:
                    continue
                dcol, drow, dlev = self.positions[dest]
                if self._moving_node == dest and self._moving_px:
                    dcx, dcy = self._moving_px
                else:
                    dcx, dcy = self._grid_to_px(dcol, drow)
                key = tuple(sorted([lid, dest])) + (direction,)
                if key in drawn_arrows:
                    continue
                drawn_arrows.add(key)
                opp      = DIR_OPPOSITE[direction]
                has_back = locs.get(dest, {}).get("exits", {}).get(opp) == lid
                if has_back:
                    self._draw_arrow(cx, cy, dcx, dcy, direction, lid, dest, 7)
                    self._draw_arrow(dcx, dcy, cx, cy, opp, dest, lid, 7)
                    drawn_arrows.add(tuple(sorted([dest, lid])) + (opp,))
                else:
                    self._draw_arrow(cx, cy, dcx, dcy, direction, lid, dest, 0)

        # Paso 2 – calcular objetos por localización
        # Si el intérprete está activo usar su estado; si no, el del juego
        if self._interp_win is not None:
            try:
                raw_objs = self._interp_win.interp.objects
            except Exception:
                raw_objs = self.game.get("objects", {})
        else:
            raw_objs = self.game.get("objects", {})

        loc_objects = {}   # {loc_id: [id_corto, ...]}
        for oid, obj in raw_objs.items():
            loc = obj.get("location", "")
            if loc and loc not in ("INVEN", "PUESTO", "NADA", ""):
                # El ID es más corto e inequívoco que el nombre largo
                short = oid if len(oid) <= 14 else oid[:13] + "…"
                loc_objects.setdefault(loc, []).append(short)

        # Paso 3 – todas las casillas (mapa plano)
        for lid, (col, row, lev) in self.positions.items():
            if self._moving_node == lid and self._moving_px:
                cx, cy = self._moving_px
            else:
                cx, cy = self._grid_to_px(col, row)
            self._draw_cell(lid, cx, cy, [0],
                            selected=(lid == self.sel),
                            obj_names=loc_objects.get(lid, []))

        self.lbl_zoom.config(text=f"{int(round(self.zoom * 100))}%")
        self._update_scroll()

    def _draw_cell(self, lid, cx, cy, stack_levs, selected=False, obj_names=None):
        x1, y1, x2, y2 = self._cell_rect(cx, cy)
        z = self.zoom
        cw = x2 - x1

        is_player = (lid == self.player_loc)
        bg  = C_LOC_SEL if selected else ("#1a6a2a" if is_player else C_LOC)
        bd  = C_BORDER_SEL if selected else ("#44ff88" if is_player else C_BORDER)

        self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline=bd, width=2)

        loc  = self.game["locations"].get(lid, {})
        name = loc.get("name", lid)

        # Con zoom muy bajo, solo el nombre centrado
        compact = z < 0.55

        # ── Franja de objetos: se calcula ANTES de pintar para que nunca
        #    se salga de la casilla (líneas medidas en píxeles, no en chars)
        obj_lines, sep_y = [], y2
        if obj_names and not compact:
            obj_lines = self._fit_obj_lines(obj_names, cw - 12,
                                            max_lines=2 if z >= 0.8 else 1)
            line_h = self.fnt_map7.metrics("linespace")
            strip_h = line_h * len(obj_lines) + int(6 * z)
            sep_y = max(y1 + int(30 * z), y2 - strip_h)
        has_objs = bool(obj_lines)

        if not compact:
            # ID (arriba izquierda)
            self.canvas.create_text(x1 + int(6*z) + 1, y1 + int(9*z) + 1,
                                     text=lid, fill=C_TEXT_ID,
                                     font=self.fnt_mapid, anchor=tk.W)
        # Nombre (centrado en el espacio que queda sobre la franja)
        disp = name if len(name) <= 17 else name[:15] + "…"
        name_y = (y1 + sep_y) // 2 + 2
        self.canvas.create_text((x1+x2)//2, name_y, text=disp,
                                  fill=C_TEXT, font=self.fnt_map,
                                  width=cw - 8)

        # Objetos en esta localización
        if has_objs:
            line_h = self.fnt_map7.metrics("linespace")
            self.canvas.create_line(x1+4, sep_y, x2-4, sep_y,
                                     fill="#2a4a6a", width=1)
            for li, ltext in enumerate(obj_lines):
                self.canvas.create_text(x1 + 5, sep_y + int(3*z) + line_h*li,
                                         text=ltext, fill="#88aacc",
                                         font=self.fnt_map7, anchor=tk.NW)

        # Indicador oscuro
        if loc.get("dark") and not compact:
            self.canvas.create_text(x1 + int(6*z), y2 - int(7*z),
                                     text="☾", fill="#7090c0",
                                     font=self.fnt_mapid, anchor=tk.W)

        # Indicador de imagen asociada (img/<id>.scr): mini icono de foto
        if lid in self._img_locs and not compact:
            ix2 = x2 - int(5*z); ix1 = ix2 - int(14*z)
            iy1 = y1 + int(5*z); iy2 = iy1 + int(11*z)
            self.canvas.create_rectangle(ix1, iy1, ix2, iy2,
                                         fill="#0e3b3b", outline="#3fd6c0", width=1)
            r = max(1, int(2*z))
            self.canvas.create_oval(ix1+int(2*z), iy1+int(2*z),
                                    ix1+int(2*z)+r, iy1+int(2*z)+r,
                                    fill="#3fd6c0", outline="")
            self.canvas.create_line(ix1+int(1*z), iy2-int(2*z),
                                    (ix1+ix2)//2, iy1+int(5*z),
                                    ix2-int(1*z), iy2-int(2*z), fill="#3fd6c0")

        # Zona de clic transparente con tag
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="", outline="",
                                      tags=(f"loc:{lid}", "loc"))

    def _fit_obj_lines(self, names, avail_px, max_lines=2):
        """
        Reparte los nombres en hasta max_lines líneas que quepan en
        avail_px (medido con la fuente real del mapa). Si no caben todos,
        la última línea termina en ' +N' con el número de ocultos.
        """
        f = self.fnt_map7
        sep = "  "
        lines = [""]
        hidden = 0
        for i, nm in enumerate(names):
            cur  = lines[-1]
            cand = cur + (sep if cur else "") + nm
            if f.measure(cand) <= avail_px:
                lines[-1] = cand
                continue
            if cur and len(lines) < max_lines:
                lines.append("")
                cur = ""
                if f.measure(nm) <= avail_px:
                    lines[-1] = nm
                    continue
            if not cur:
                # Un id solo no cabe ni en línea vacía: recortar con …
                while nm and f.measure(nm + "…") > avail_px:
                    nm = nm[:-1]
                lines[-1] = nm + "…"
                continue
            hidden = len(names) - i
            break
        if hidden:
            tag = f" +{hidden}"
            base = lines[-1]
            while base and f.measure(base + tag) > avail_px:
                base = base[:-1]
            lines[-1] = (base + tag).strip()
        return [l for l in lines if l]

    def _draw_ghost(self, cx, cy, stack_levs):
        x1, y1, x2, y2 = cell_rect(cx, cy)
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=C_LOC_GHOST,
                                      outline=C_BORDER_GHOST, width=1, dash=(5, 4))
        label = "niveles: " + " ".join(f"{l:+d}" if l != 0 else "0"
                                        for l in stack_levs)
        self.canvas.create_text((x1+x2)//2, (y1+y2)//2, text=label,
                                  fill=C_TEXT_GHOST, font=("Helvetica", 8))

    def _draw_arrow(self, cx1, cy1, cx2, cy2, direction, from_id, to_id, perp_off=0):
        """Dibuja flecha de nodo a nodo con letra de dirección."""
        import math
        # Calcular vector
        dx, dy = cx2 - cx1, cy2 - cy1
        length = max(1, math.hypot(dx, dy))
        nx, ny = dx/length, dy/length   # vector unitario
        # Offset perpendicular para flechas bidireccionales
        px, py = -ny * perp_off, nx * perp_off
        sx, sy = cx1 + px, cy1 + py
        ex, ey = cx2 + px, cy2 + py
        # Recortar a los bordes de los nodos
        def clip_to_rect(ox, oy, tx, ty, rcx, rcy):
            x1, y1, x2, y2 = self._cell_rect(rcx, rcy)
            tdx, tdy = tx-ox, ty-oy
            tl = max(1, math.hypot(tdx, tdy))
            tnx, tny = tdx/tl, tdy/tl
            t_vals = []
            if tnx != 0:
                t_vals += [( (x1 if tnx<0 else x2) - ox ) / tnx]
            if tny != 0:
                t_vals += [( (y1 if tny<0 else y2) - oy ) / tny]
            t = min((t for t in t_vals if t > 0), default=tl)
            return ox + tnx*t, oy + tny*t
        sxc, syc = clip_to_rect(sx, sy, ex, ey, cx1, cy1)
        exc, eyc = clip_to_rect(ex, ey, sx, sy, cx2, cy2)
        tag   = f"arrow:{from_id}:{direction}:{to_id}"
        sel   = (self.sel_arrow == (from_id, direction, to_id))
        color = "#ffe066" if sel else C_ARROW_H
        width = 3         if sel else 2
        self.canvas.create_line(sxc, syc, exc, eyc, fill=color, width=width,
                                 arrow=tk.LAST, arrowshape=(10,13,4),
                                 tags=(tag,"arrow"))
        # Línea invisible para clic fácil
        self.canvas.create_line(sxc, syc, exc, eyc, fill="", width=12,
                                 tags=(tag,"arrow"))
        # Etiqueta de dirección en el 30% desde el origen
        lx = sxc + (exc-sxc)*0.28 + (-ny)*10
        ly = syc + (eyc-syc)*0.28 + ( nx)*10
        label = dir_label(direction)
        self.canvas.create_text(lx, ly, text=label,
                                 fill="#ffe066" if sel else
                                      ("#7fe8a8" if direction in ('U', 'D')
                                       else "#88ccff"),
                                 font=self.fnt_map8b,
                                 tags=(tag,"arrow"))

    def _draw_ud_indicator(self, cx, cy, direction, dest_id, from_id):
        x1, y1, x2, y2 = cell_rect(cx, cy)
        is_up  = (direction == 'U')
        cx     = x2 - 10
        cy     = y1 + 10 if is_up else y2 - 10
        pts    = [(cx, cy-7, cx-5, cy+3, cx+5, cy+3) if is_up
                  else (cx, cy+7, cx-5, cy-3, cx+5, cy-3)][0]
        tag    = f"arrow:{from_id}:{direction}:{dest_id}"
        sel    = (self.sel_arrow == (from_id, direction, dest_id))
        color  = "#ffe066" if sel else C_ARROW_UD
        self.canvas.create_polygon(*pts, fill=color, outline="",
                                    tags=(tag, "arrow"))
        dest_lev = self.positions.get(dest_id, [0,0,0])[2]
        label = f"{'U' if is_up else 'D'} L{dest_lev:+d}" if dest_lev != 0 else f"{'U' if is_up else 'D'}"
        self.canvas.create_text(cx, cy + (14 if is_up else -14), text=label,
                                 fill=color, font=("Courier", 7, "bold"),
                                 tags=(tag, "arrow"))
        # zona de clic invisible
        self.canvas.create_rectangle(cx-12, cy-10, cx+12, cy+20,
                                      fill="", outline="", tags=(tag, "arrow"))

    def _update_scroll(self):
        if not self.positions:
            return
        cw, ch, sx, sy = self._zgeom()
        pxs = [OX + p[0] * sx for p in self.positions.values()]
        pys = [OY + p[1] * sy for p in self.positions.values()]
        self.canvas.configure(scrollregion=(
            min(pxs) - cw - 60, min(pys) - ch - 60,
            max(pxs) + cw + 60, max(pys) + ch + 60))

    # ═══════════════════════════════════════════════════════════════════════════
    # EVENTOS DEL CANVAS
    # ═══════════════════════════════════════════════════════════════════════════

    def _wx(self, event):
        return self.canvas.canvasx(event.x)

    def _wy(self, event):
        return self.canvas.canvasy(event.y)

    def _hit(self, wx, wy):
        """Devuelve loc_id si el punto (wx,wy) cae en un nodo."""
        for lid, (col, row, lev) in self.positions.items():
            cx, cy = self._grid_to_px(col, row)
            x1, y1, x2, y2 = self._cell_rect(cx, cy)
            if x1 <= wx <= x2 and y1 <= wy <= y2:
                return lid
        return None

    def _arrow_hit(self, wx, wy):
        """Devuelve (from_id, direction, to_id) si el punto toca una flecha, o None."""
        items = self.canvas.find_closest(wx, wy, halo=8)
        for item in items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("arrow:"):
                    parts = tag.split(":")
                    if len(parts) == 4:
                        return (parts[1], parts[2], parts[3])
        return None

    def _near_edge(self, wx, wy, lid):
        """Devuelve dirección si (wx,wy) está en la zona de borde del nodo, o None."""
        col, row, lev = self.positions[lid]
        cx, cy = self._grid_to_px(col, row)
        x1, y1, x2, y2 = self._cell_rect(cx, cy)
        ZONE = max(6, int(14 * self.zoom))
        if not (x1 <= wx <= x2 and y1 <= wy <= y2):
            return None
        if wy - y1 < ZONE: return 'N'
        if y2 - wy < ZONE: return 'S'
        if wx - x1 < ZONE: return 'O'
        if x2 - wx < ZONE: return 'E'
        return None

    def _canvas_press(self, event):
        """Manejador único de ButtonPress-1: selección + inicio de arrastre."""
        wx, wy = self._wx(event), self._wy(event)
        hit    = self._hit(wx, wy)

        # Modo conectar
        if hasattr(self, '_connect_mode') and self._connect_mode:
            self._connect_click(hit)
            return

        # Inicio de arrastre desde borde de casilla
        if hit:
            edge = self._near_edge(wx, wy, hit)
            if edge:
                self._drag_src  = hit
                self._drag_dir  = edge
                self._drag_line = None
                self.canvas.config(cursor="crosshair")
                return  # no seleccionar la casilla todavía

        # Selección + inicio de arrastre de nodo (centro)
        if hit:
            self.sel_arrow = None
            self.sel = hit
            col, row, _ = self.positions[hit]
            cx, cy = self._grid_to_px(col, row)
            self._moving_node = hit
            self._move_offset = (wx - cx, wy - cy)
            self._moving_px   = (cx, cy)
            self.canvas.config(cursor="fleur")
            self._redraw()
            self._load_loc_to_form(hit)
            self.nb.select(1)
            self.sv_status.set(
                f"Seleccionado: {hit}  |  arrastra para mover  |  clic derecho = menú")
            return

        # Selección de flecha
        arrow = self._arrow_hit(wx, wy)
        if arrow:
            self.sel_arrow = arrow
            self.sel = None
            self._redraw()
            from_id, direction, to_id = arrow
            self.sv_status.set(
                f"Flecha: {from_id} → {DIR_NAMES[direction]} → {to_id}"
                f"  |  Delete = borrar  |  clic derecho = menú")
            return

        # Clic en vacío → deseleccionar todo
        self.sel = None
        self.sel_arrow = None
        self._redraw()

    def _canvas_dblclick(self, event):
        wx, wy = self._wx(event), self._wy(event)
        hit = self._hit(wx, wy)
        if hit:
            self._load_loc_to_form(hit)
            self.nb.select(1)
        elif not self.game["locations"]:
            # Primera localización: doble clic en vacío
            col, row = self._px_to_grid(wx, wy)
            col, row = max(0, col), max(0, row)
            self._create_loc_at(col, row, 0)

    def _canvas_rclick(self, event):
        wx, wy = self._wx(event), self._wy(event)
        hit    = self._hit(wx, wy)
        arrow  = None if hit else self._arrow_hit(wx, wy)

        m = tk.Menu(self.root, tearoff=0)
        if arrow:
            from_id, direction, to_id = arrow
            m.add_command(label=f"Conexión: {from_id} → {DIR_NAMES[direction]} → {to_id}",
                          state=tk.DISABLED)
            m.add_separator()
            m.add_command(label="🗑  Eliminar esta conexión",
                          command=lambda: self._remove_exit_arrow(arrow))
            m.add_command(label="↔  Cambiar dirección…",
                          command=lambda: self._change_arrow_dir(arrow))
        elif hit:
            m.add_command(label=f"✏  Editar: {hit}",
                          command=lambda: (self._load_loc_to_form(hit), self.nb.select(1)))
            m.add_separator()
            loc   = self.game["locations"][hit]
            exits = loc.get("exits", {})
            for d in ['N','S','E','O','U','D']:
                dest = exits.get(d)
                if dest:
                    m.add_command(
                        label=f"  ↔ {DIR_NAMES[d]}  → {dest}  [quitar conexión]",
                        command=lambda d=d, h=hit: self._remove_exit(h, d))
                else:
                    m.add_command(
                        label=f"  ＋ Añadir al {DIR_NAMES[d]}",
                        command=lambda d=d, h=hit: self._add_adj_from(h, d))
            m.add_separator()
            m.add_command(label="🗑  Eliminar localización",
                          command=lambda: self._delete_loc_id(hit))
        else:
            if not self.game["locations"]:
                m.add_command(label="＋ Primera localización",
                              command=lambda: self._create_loc_at(0, 0, self.level))
            else:
                m.add_command(label="(clic en una localización para ver opciones)",
                              state=tk.DISABLED)
        m.post(event.x_root, event.y_root)

    def _canvas_motion(self, event):
        if self._drag_src or self._moving_node:
            return  # el drag_motion gestiona el cursor durante el arrastre
        wx, wy = self._wx(event), self._wy(event)
        hit = self._hit(wx, wy)
        if hit:
            edge = self._near_edge(wx, wy, hit)
            self.canvas.config(cursor="crosshair" if edge else "hand2")
        elif self._arrow_hit(wx, wy):
            self.canvas.config(cursor="hand2")
        else:
            self.canvas.config(cursor="arrow")

    # ─── Arrastre para crear conexiones ────────────────────────────────────

    def _drag_motion(self, event):
        if self._moving_node:
            wx, wy = self._wx(event), self._wy(event)
            ox, oy = self._move_offset
            self._moving_px = (wx - ox, wy - oy)
            self._redraw()
            return
        if not self._drag_src:
            return
        wx, wy = self._wx(event), self._wy(event)
        col, row, _ = self.positions[self._drag_src]
        cx, cy = self._grid_to_px(col, row)
        sx, sy = self._edge_point(cx, cy, self._drag_dir)
        if self._drag_line:
            self.canvas.coords(self._drag_line, sx, sy, wx, wy)
        else:
            self._drag_line = self.canvas.create_line(
                sx, sy, wx, wy,
                fill="#ffe066", width=2, dash=(6, 3),
                arrow=tk.LAST, arrowshape=(10, 13, 4))

    def _drag_release(self, event):
        if self._moving_node:
            wx, wy = self._wx(event), self._wy(event)
            ox, oy = self._move_offset
            px, py = wx - ox, wy - oy
            new_col, new_row = self._px_to_grid(px, py)
            lid = self._moving_node
            old_col, old_row, lev = self.positions[lid]
            occupant = self._loc_at(new_col, new_row, lev)
            if occupant and occupant != lid:
                # Swap con el nodo que ocupa la celda destino
                self.positions[occupant] = [old_col, old_row, lev]
            self.positions[lid] = [new_col, new_row, lev]
            self._moving_node = None
            self._moving_px   = None
            self.canvas.config(cursor="arrow")
            self.dirty = True
            self._redraw()
            return
        if not self._drag_src:
            return
        wx, wy = self._wx(event), self._wy(event)
        if self._drag_line:
            self.canvas.delete(self._drag_line)
            self._drag_line = None

        dest = self._hit(wx, wy)
        src  = self._drag_src
        self._drag_src = None
        self._drag_dir = None
        self.canvas.config(cursor="arrow")

        if dest and dest != src:
            d = self._ask_direction(f"Dirección de '{src}' → '{dest}':")
            if d:
                self._connect(src, d, dest)
                self._redraw()
                self.sv_status.set(f"Conectado: {src} → {DIR_NAMES[d]} → {dest}")

    # ─── Acciones sobre flechas ─────────────────────────────────────────────

    def _delete_selected(self, event=None):
        if self.sel_arrow:
            from_id, direction, to_id = self.sel_arrow
            self._remove_exit(from_id, direction)
            self.sel_arrow = None
            self._redraw()
            self.sv_status.set(f"Conexión eliminada: {from_id} → {DIR_NAMES[direction]}")

    def _remove_exit_arrow(self, arrow):
        from_id, direction, to_id = arrow
        self._remove_exit(from_id, direction)
        if self.sel_arrow == arrow:
            self.sel_arrow = None
        self._redraw()

    def _change_arrow_dir(self, arrow):
        from_id, old_dir, to_id = arrow
        new_dir = self._ask_direction(
            f"Nueva dirección de '{from_id}' → '{to_id}':")
        if new_dir and new_dir != old_dir:
            self._remove_exit(from_id, old_dir)
            self._connect(from_id, new_dir, to_id)
            self.sel_arrow = (from_id, new_dir, to_id)
            self._redraw()

    # ─── Modo conectar ─────────────────────────────────────────────────────

    def _start_connect(self):
        if not self.sel:
            messagebox.showinfo("Conectar",
                "Selecciona primero una localización de origen.")
            return
        self._connect_mode = True
        self._connect_src  = self.sel
        self.sv_status.set(
            f"Modo CONECTAR: clic en la localización destino para enlazarla con '{self.sel}'  |  Esc = cancelar")
        self.canvas.config(cursor="crosshair")
        self.root.bind("<Escape>", self._cancel_connect)

    def _connect_click(self, hit):
        if hit and hit != self._connect_src:
            # Pedir dirección
            d = self._ask_direction(
                f"Dirección de '{self._connect_src}' → '{hit}':")
            if d:
                self._connect(self._connect_src, d, hit)
                self._redraw()
                self.sv_status.set(
                    f"Conectado: {self._connect_src} → {DIR_NAMES[d]} → {hit}")
        self._cancel_connect()

    def _ask_direction(self, prompt):
        win = tk.Toplevel(self.root)
        win.title("Dirección")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        result = tk.StringVar(value="")

        ttk.Label(win, text=prompt, padding=10).pack()
        fr = ttk.Frame(win, padding=8)
        fr.pack()
        dirs = [("U↑","U"),("N","N"),("S","S"),("E","E"),("O","O"),("D↓","D")]
        for i, (label, d) in enumerate(dirs):
            ttk.Button(fr, text=label, width=6,
                       command=lambda d=d: (result.set(d), win.destroy())
                       ).grid(row=0, column=i, padx=2)
        ttk.Button(win, text="Cancelar",
                   command=win.destroy).pack(pady=4)
        self.root.wait_window(win)
        return result.get() or None

    def _cancel_connect(self, event=None):
        self._connect_mode = False
        self._connect_src  = None
        self.canvas.config(cursor="arrow")
        self.root.unbind("<Escape>")
        self.sv_status.set("Listo")

    # ═══════════════════════════════════════════════════════════════════════════
    # OPERACIONES DE MAPA
    # ═══════════════════════════════════════════════════════════════════════════

    def _center_map(self):
        if not self.positions:
            return
        _, _, sx, sy = self._zgeom()
        cols = [p[0] for p in self.positions.values()]
        rows = [p[1] for p in self.positions.values()]
        cx = OX + (min(cols) + max(cols)) / 2 * sx
        cy = OY + (min(rows) + max(rows)) / 2 * sy
        self._update_scroll()
        try:
            x1, y1, x2, y2 = (float(v) for v in
                              str(self.canvas.cget('scrollregion')).split())
        except (ValueError, TypeError):
            return
        vw = max(1, self.canvas.winfo_width())
        vh = max(1, self.canvas.winfo_height())
        sw = max(1.0, x2 - x1)
        sh = max(1.0, y2 - y1)
        self.canvas.xview_moveto(max(0.0, min(1.0, (cx - x1 - vw / 2) / sw)))
        self.canvas.yview_moveto(max(0.0, min(1.0, (cy - y1 - vh / 2) / sh)))

    def _add_first_loc(self):
        if not self.game["locations"]:
            self._create_loc_at(0, 0, self.level)
        else:
            messagebox.showinfo("Añadir localización",
                "Selecciona una localización existente y usa los botones de brújula\n"
                "o el menú de clic derecho para agregar adyacentes.")

    def _add_adj(self, direction):
        if not self.sel:
            messagebox.showwarning("Sin selección",
                "Selecciona primero una localización en el mapa.")
            return
        self._add_adj_from(self.sel, direction)

    def _add_adj_from(self, lid, direction):
        col, row, lev = self.positions[lid]
        dc, dr, dl     = DIR_DELTA[direction]
        nc, nr, nl     = col + dc, row + dr, lev + dl

        existing = self._loc_at(nc, nr, nl)
        if existing:
            if messagebox.askyesno("Posición ocupada",
                    f"Ya existe '{existing}' en esa posición.\n"
                    f"¿Conectar '{lid}' → {direction} → '{existing}'?"):
                self._connect(lid, direction, existing)
                self._redraw()
            return

        new_id = self._create_loc_at(nc, nr, nl,
                                      connect_from=lid, connect_dir=direction)
        if new_id:
            self.sel   = new_id
            self.level = nl
            self._redraw()
            self._load_loc_to_form(new_id)
            self.nb.select(1)

    def _create_loc_at(self, col, row, level,
                        connect_from=None, connect_dir=None):
        new_id = simpledialog.askstring(
            "Nueva localización", "ID de la localización:",
            initialvalue=self._unique_id(), parent=self.root)
        if not new_id:
            return None
        new_id = new_id.strip()
        if not new_id:
            return None
        if new_id in self.game["locations"]:
            messagebox.showerror("Error", f"Ya existe '{new_id}'")
            return None

        self.game["locations"][new_id] = {
            "name": new_id,
            "description": "",
            "dark": False,
            "exits": {d: None for d in ('N','S','E','O','U','D')},
            "on_enter": [],
            "on_look": []
        }
        # Si no hay start_location, esta es la primera → asignarla y refrescar
        if not self.game["metadata"].get("start_location"):
            self.game["metadata"]["start_location"] = new_id
            self._load_meta_to_form()      # refresca el campo Start location

        self.positions[new_id] = [col, row, level]

        if connect_from and connect_dir:
            self._connect(connect_from, connect_dir, new_id)

        self.dirty = True
        # Refresca lista + panel + mapa al instante (no esperar a un clic en el mapa)
        self._loc_changed(select=new_id)
        return new_id

    def _connect(self, from_id, direction, to_id):
        self.game["locations"][from_id]["exits"][direction] = to_id
        opp = DIR_OPPOSITE[direction]
        if not self.game["locations"][to_id].get("exits", {}).get(opp):
            self.game["locations"][to_id]["exits"][opp] = from_id
        self.dirty = True
        if self.sel in (from_id, to_id):       # sincroniza el panel si procede
            self._load_loc_to_form(self.sel)

    def _remove_exit(self, lid, direction):
        self.game["locations"][lid]["exits"][direction] = None
        self.dirty = True
        if self.sel == lid:                    # sincroniza el panel si procede
            self._load_loc_to_form(self.sel)
        self._redraw()

    def _delete_loc(self):
        if not self.sel:
            messagebox.showwarning("Sin selección",
                "Selecciona una localización en el mapa primero.")
            return
        self._delete_loc_id(self.sel)

    def _delete_loc_id(self, lid):
        is_start = self.game.get("metadata", {}).get("start_location") == lid
        prompt = f"¿Eliminar '{lid}'?"
        if is_start:
            prompt += "\n\n¡Atención! Es la localización inicial del juego."
        if not messagebox.askyesno("Confirmar", prompt):
            return
        del self.game["locations"][lid]
        self.positions.pop(lid, None)
        for loc in self.game["locations"].values():
            for d in loc.get("exits", {}):
                if loc["exits"][d] == lid:
                    loc["exits"][d] = None
        # Objetos que estaban allí → al limbo (NADA)
        moved = 0
        for o in self.game.get("objects", {}).values():
            if o.get("location") == lid:
                o["location"] = "NADA"
                moved += 1
        if moved:
            self._refresh_obj_tree()
            self.sv_status.set(f"{moved} objeto(s) de '{lid}' movidos a NADA.")
        # Reasignar start_location si era la inicial
        if is_start:
            new_start = next(iter(self.game["locations"]), "")
            self.game["metadata"]["start_location"] = new_start
            self._load_meta_to_form()
            messagebox.showwarning(
                "start_location",
                f"'{lid}' era la localización inicial.\n"
                f"Nueva start_location: '{new_start or '(ninguna)'}'.")
        if self.sel == lid:
            self.sel = None
        self._loc_changed()        # refresca lista + panel + mapa tras borrar
        self.dirty = True
        self._redraw()

    # ═══════════════════════════════════════════════════════════════════════════
    # FORMULARIOS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Localización ──

    def _refresh_loc_list(self):
        """Recarga el Listbox de localizaciones desde game['locations'].
        Las que tienen imagen <id>.scr en img/ se muestran en color."""
        self.loc_list.delete(0, tk.END)
        self._refresh_img_locs()
        for idx, lid in enumerate(sorted(self.game.get("locations", {}).keys())):
            self.loc_list.insert(tk.END, lid)
            if lid in self._img_locs:
                self.loc_list.itemconfig(idx, foreground='#3fd6c0')
        # Resaltar la seleccionada
        if self.sel:
            items = list(self.loc_list.get(0, tk.END))
            if self.sel in items:
                idx = items.index(self.sel)
                self.loc_list.selection_clear(0, tk.END)
                self.loc_list.selection_set(idx)
                self.loc_list.see(idx)

    def _loc_changed(self, select=None):
        """Tras CUALQUIER cambio en localizaciones: refresca la lista, sincroniza
        el panel de detalle con la localización marcada (o la primera si la marcada
        ya no existe, o lo vacía si no queda ninguna) y redibuja el mapa."""
        locs = self.game.get('locations', {})
        if select is not None:
            self.sel = select
        if self.sel not in locs:
            self.sel = (sorted(locs)[0] if locs else None)
        self._refresh_loc_list()
        self._load_loc_to_form(self.sel if self.sel else '')
        self._redraw()

    def _loc_list_select(self, event):
        sel = self.loc_list.curselection()
        if sel:
            lid = self.loc_list.get(sel[0])
            self.sel = lid
            self._load_loc_to_form(lid)
            self._redraw()

    def _loc_list_new(self):
        new_id = simpledialog.askstring("Nueva localización", "ID:",
                                         initialvalue=self._unique_id(),
                                         parent=self.root)
        if not new_id:
            return
        new_id = new_id.strip()
        if new_id in self.game["locations"]:
            messagebox.showerror("Error", f"Ya existe '{new_id}'"); return
        self.game["locations"][new_id] = {
            "name": new_id, "description": "", "dark": False,
            "exits": {d: None for d in ('N','S','E','O','U','D')},
            "on_enter": [], "on_look": []
        }
        if not self.game["metadata"].get("start_location"):
            self.game["metadata"]["start_location"] = new_id
            self._load_meta_to_form()      # refresca el campo Start location
        col, row = 0, 0
        while not self._pos_free(col, row, self.level):
            col += 1
        self.positions[new_id] = [col, row, self.level]
        self.dirty = True
        self._loc_changed(select=new_id)

    def _loc_list_del(self):
        sel = self.loc_list.curselection()
        if not sel:
            return
        # _delete_loc_id ya pide confirmación y sincroniza lista + panel + mapa.
        self._delete_loc_id(self.loc_list.get(sel[0]))

    def _sync_loc_list(self, lid):
        """Sincroniza la selección del Listbox con lid sin reconstruir la lista."""
        items = list(self.loc_list.get(0, tk.END))
        if lid in items:
            idx = items.index(lid)
            self.loc_list.selection_clear(0, tk.END)
            self.loc_list.selection_set(idx)
            self.loc_list.see(idx)

    def _load_loc_to_form(self, lid):
        loc = self.game["locations"].get(lid, {})
        self.loc_id.delete(0, tk.END);   self.loc_id.insert(0, lid)
        self.loc_name.delete(0, tk.END); self.loc_name.insert(0, loc.get("name",""))
        self.loc_desc.delete("1.0", tk.END)
        self.loc_desc.insert("1.0", loc.get("description",""))
        self.loc_dark.set(loc.get("dark", False))
        exits = loc.get("exits", {})
        for d, v in self.exit_vars.items():
            v.set(exits.get(d) or "")
        on_enter = loc.get("on_enter", "")
        if isinstance(on_enter, list):
            on_enter = "\n".join(str(x) for x in on_enter)
        self.loc_enter.delete("1.0", tk.END)
        self.loc_enter.insert("1.0", on_enter)
        self._refresh_loc_objs(lid)
        self._refresh_loc_img(lid)
        self._sync_loc_list(lid)

    def _refresh_loc_objs(self, lid):
        """Rellena la lista 'Objetos aquí' con los objetos cuya location es
        lid (y el contenido de los contenedores presentes)."""
        if not hasattr(self, "loc_objs"):
            return
        objects = self.game.get("objects", {})
        self.loc_objs.delete(0, tk.END)
        self._loc_obj_ids = []
        for oid, obj in sorted(objects.items()):
            if obj.get("location") != lid:
                continue
            extra = []
            if "fixed" in (obj.get("attributes") or []):
                extra.append("fijo")
            if obj.get("wearable"):
                extra.append("ropa")
            if obj.get("container"):
                extra.append("contenedor")
            suffix = f"  [{', '.join(extra)}]" if extra else ""
            self._loc_obj_ids.append(oid)
            self.loc_objs.insert(tk.END,
                                 f"{oid} — {obj.get('name', oid)}{suffix}")
            # Contenido del contenedor (un nivel)
            for cid2, co in sorted(objects.items()):
                if co.get("location") == oid:
                    self._loc_obj_ids.append(cid2)
                    self.loc_objs.insert(
                        tk.END, f"    └ {cid2} — {co.get('name', cid2)}")
        if not self._loc_obj_ids:
            self.loc_objs.insert(tk.END, "(ninguno)")

    def _loc_obj_goto(self, event=None):
        """Doble clic en un objeto de la lista → abrirlo en la pestaña Objetos."""
        sel = self.loc_objs.curselection()
        ids = getattr(self, "_loc_obj_ids", [])
        if not sel or sel[0] >= len(ids):
            return
        oid = ids[sel[0]]
        self.nb.select(2)
        try:
            self.obj_tree.selection_set(oid)
            self.obj_tree.see(oid)
            self._load_obj_to_form(oid)
        except Exception:
            pass

    def _apply_loc(self):
        old_id = self.sel
        new_id = self.loc_id.get().strip()
        if not new_id:
            messagebox.showerror("Error", "El ID no puede estar vacío."); return

        loc = {}
        loc["name"]        = self.loc_name.get().strip()
        loc["description"] = self.loc_desc.get("1.0", tk.END).strip()
        loc["dark"]        = self.loc_dark.get()
        loc["exits"] = {}
        for d, v in self.exit_vars.items():
            val = v.get().strip()
            loc["exits"][d] = val if val else None
        loc["on_enter"] = self.loc_enter.get("1.0", tk.END).strip()
        loc["on_look"]  = self.game["locations"].get(old_id or new_id, {}).get("on_look", [])

        if old_id and old_id != new_id:
            # Renombrar
            if new_id in self.game["locations"]:
                messagebox.showerror(
                    "Error", f"Ya existe una localización '{new_id}'.")
                return
            del self.game["locations"][old_id]
            if old_id in self.positions:
                self.positions[new_id] = self.positions.pop(old_id)
            else:
                col = 0
                while not self._pos_free(col, 0, self.level):
                    col += 1
                self.positions[new_id] = [col, 0, self.level]
            for l in self.game["locations"].values():
                for d in l.get("exits", {}):
                    if l["exits"][d] == old_id:
                        l["exits"][d] = new_id
            # Objetos que estaban en la localización renombrada
            for o in self.game.get("objects", {}).values():
                if o.get("location") == old_id:
                    o["location"] = new_id
            if self.game["metadata"].get("start_location") == old_id:
                self.game["metadata"]["start_location"] = new_id
                self._load_meta_to_form()
            self.sel = new_id
            self._refresh_obj_tree()

        self.game["locations"][new_id] = loc
        # Localización nueva (no venía del botón «Nueva»): asignarle una posición
        # libre en el mapa para que se dibuje ya, sin esperar a un clic en el mapa.
        if new_id not in self.positions:
            col = 0
            while not self._pos_free(col, 0, self.level):
                col += 1
            self.positions[new_id] = [col, 0, self.level]
            self.sel = new_id
        self.dirty = True
        extra = ""
        if old_id and old_id != new_id:
            n = self._refactor_id_in_scripts(old_id, new_id)
            if n:
                extra = f" ({n} referencias actualizadas en scripts)"
        self._loc_changed(select=new_id)
        self.sv_status.set(f"Localización '{new_id}' guardada.{extra}")
        self._run_validation()

    # ── Metadata ──

    def _load_meta_to_form(self):
        meta = self.game.get("metadata", {})
        for key, w in self._meta_w.items():
            val = str(meta.get(key, "") or "")
            if isinstance(w, scrolledtext.ScrolledText):
                w.delete("1.0", tk.END); w.insert("1.0", val)
            else:
                w.delete(0, tk.END);    w.insert(0, val)
        try:
            b = int(meta.get('border', 0) or 0)
        except (TypeError, ValueError):
            b = 0
        self._border_var.set(self._BORDER_NOMBRES[max(0, min(7, b))])
        self._refresh_menu_img()      # preview de la imagen de menu/titulo

    def _dialog_mensajes(self):
        """Editor de los mensajes del sistema del motor (para multiidioma). Los
        que difieran del por defecto se guardan en metadata['mensajes']."""
        if not self.game.get('locations'):
            messagebox.showinfo('Mensajes', 'Abre o crea un juego primero.')
            return
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import mensajes
            if not getattr(sys, 'frozen', False):
                importlib.reload(mensajes)
        except Exception as e:
            messagebox.showerror('Mensajes', 'No se pudo cargar mensajes.py:\n%s' % e)
            return
        win = tk.Toplevel(self.root)
        win.title('Mensajes del sistema del motor')
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, foreground='#667788', justify=tk.LEFT, wraplength=660,
                  text='Edita los mensajes del motor para tu idioma. Usa {o} para '
                       'el nombre del objeto y {p}/{max} para la puntuación. Un '
                       'campo igual al por defecto no se personaliza. (También se '
                       'exportan/importan en el CSV de traducción.)'
                  ).pack(anchor=tk.W, padx=10, pady=(10, 4))
        cont = ttk.Frame(win)
        cont.pack(fill=tk.BOTH, expand=True, padx=6)
        canvas = tk.Canvas(cont, width=690, height=460, highlightthickness=0)
        sb = ttk.Scrollbar(cont, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(int(-e.delta / 120), 'units'))
        defs = mensajes.defaults()
        desc = mensajes.descripciones()
        ov = (self.game.get('metadata') or {}).get('mensajes') or {}
        ents = {}
        for i, mid in enumerate(mensajes.orden()):
            ttk.Label(inner, text=desc.get(mid, mid), width=36, anchor=tk.W
                      ).grid(row=i, column=0, sticky=tk.W, padx=6, pady=1)
            e = tk.Entry(inner, width=50, font=self.fnt_ui)
            e.insert(0, str(ov.get(mid, defs[mid])))
            e.grid(row=i, column=1, sticky=tk.EW, padx=6, pady=1)
            ents[mid] = e
        inner.columnconfigure(1, weight=1)

        def aplicar():
            nuevos = {}
            for mid, e in ents.items():
                v = e.get()
                if v.strip() and v != defs[mid]:
                    nuevos[mid] = v
            meta = self.game.setdefault('metadata', {})
            if nuevos:
                meta['mensajes'] = nuevos
            else:
                meta.pop('mensajes', None)
            self.dirty = True
            self.sv_status.set('Mensajes del sistema: %d personalizados'
                               % len(nuevos))
            canvas.unbind_all('<MouseWheel>')
            win.destroy()

        def restaurar():
            for mid, e in ents.items():
                e.delete(0, tk.END)
                e.insert(0, defs[mid])

        def cerrar():
            canvas.unbind_all('<MouseWheel>')
            win.destroy()

        bf = ttk.Frame(win)
        bf.pack(pady=8)
        ttk.Button(bf, text='Aplicar', command=aplicar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text='Restaurar por defecto',
                   command=restaurar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text='Cancelar', command=cerrar).pack(side=tk.LEFT, padx=4)
        win.protocol('WM_DELETE_WINDOW', cerrar)

    def _apply_meta(self):
        meta = self.game["metadata"]
        for key, w in self._meta_w.items():
            if isinstance(w, scrolledtext.ScrolledText):
                val = w.get("1.0", tk.END).strip()
            else:
                val = w.get().strip()
            if key == "max_score":
                try: val = int(val)
                except ValueError: val = 0
            meta[key] = val
        try:
            meta['border'] = int(self._border_var.get().split(' ')[0])
        except (ValueError, IndexError):
            meta['border'] = 0
        self.dirty = True
        self.sv_status.set("Metadata guardada.")
        self._run_validation()

    # ── Objetos ──

    def _refresh_obj_tree(self):
        self.obj_tree.delete(*self.obj_tree.get_children())
        for oid, obj in self.game.get("objects", {}).items():
            self.obj_tree.insert("", tk.END, iid=oid, values=(
                oid, obj.get("name",""), obj.get("location",""), obj.get("weight",0)))

    def _obj_selected(self, event):
        sel = self.obj_tree.selection()
        if sel:
            self._load_obj_to_form(sel[0])

    def _load_obj_to_form(self, oid):
        obj = self.game["objects"].get(oid, {})
        for key in ["name","noun","location","weight","key"]:
            w = self._obj_w[key]
            w.delete(0, tk.END)
            w.insert(0, str(obj.get(key, "") or ""))
        self._obj_w["id"].delete(0, tk.END); self._obj_w["id"].insert(0, oid)
        self._obj_w["description"].delete("1.0", tk.END)
        self._obj_w["description"].insert("1.0", obj.get("description",""))
        for cb, v in self._obj_cb.items():
            v.set(bool(obj.get(cb, False)))

    def _new_obj(self):
        oid = simpledialog.askstring("Nuevo objeto", "ID del objeto:",
                                      parent=self.root)
        if not oid: return
        oid = oid.strip()
        if oid in self.game["objects"]:
            messagebox.showerror("Error", f"Ya existe '{oid}'"); return
        self.game["objects"][oid] = {
            "name":oid,"noun":"","description":"","location":"",
            "weight":0,"wearable":False,"container":False,"openable":False,
            "open":False,"locked":False,"light_source":False,"lit":False,
            "key":None,"attributes":[]
        }
        self._refresh_obj_tree()
        self.obj_tree.selection_set(oid)
        self._load_obj_to_form(oid)
        self.dirty = True

    def _del_obj(self):
        sel = self.obj_tree.selection()
        if not sel: return
        oid = sel[0]
        if messagebox.askyesno("Confirmar", f"¿Eliminar objeto '{oid}'?"):
            old_noun = self.game["objects"][oid].get("noun", "") or ""
            del self.game["objects"][oid]
            self._sync_noun_vocab(old_noun=old_noun)
            self._refresh_obj_tree()
            self._load_vocab_to_form()
            if self.sel:
                self._refresh_loc_objs(self.sel)
            self.dirty = True

    def _apply_obj(self):
        sel = self.obj_tree.selection()
        old_id = sel[0] if sel else None
        new_id = self._obj_w["id"].get().strip()
        if not new_id:
            messagebox.showerror("Error", "ID no puede estar vacío."); return
        if old_id and old_id != new_id and new_id in self.game["objects"]:
            messagebox.showerror("Error", f"Ya existe un objeto '{new_id}'.")
            return
        old_obj  = self.game["objects"].get(old_id, {})
        old_noun = old_obj.get("noun", "") or ""
        obj = copy.deepcopy(old_obj)
        obj["name"]     = self._obj_w["name"].get().strip() or new_id
        obj["noun"]     = self._obj_w["noun"].get().strip()
        obj["location"] = self._obj_w["location"].get().strip()
        obj["key"]      = self._obj_w["key"].get().strip() or None
        try:    obj["weight"] = int(self._obj_w["weight"].get())
        except: obj["weight"] = 0
        obj["description"] = self._obj_w["description"].get("1.0", tk.END).strip()
        for cb, v in self._obj_cb.items():
            obj[cb] = v.get()
        if old_id and old_id != new_id and old_id in self.game["objects"]:
            del self.game["objects"][old_id]
            # Actualizar referencias al id antiguo en otros objetos
            for o in self.game["objects"].values():
                if o.get("key") == old_id:
                    o["key"] = new_id
                if o.get("location") == old_id:   # objetos contenidos en él
                    o["location"] = new_id
        self.game["objects"][new_id] = obj
        new_noun = obj.get("noun") or ""
        self._sync_noun_vocab(old_noun=old_noun if old_noun != new_noun else None,
                              new_noun=new_noun)
        self._refresh_obj_tree()
        self._load_vocab_to_form()
        if self.sel:
            self._refresh_loc_objs(self.sel)
        self.dirty = True
        extra = ""
        if old_id and old_id != new_id:
            n = self._refactor_id_in_scripts(old_id, new_id)
            if n:
                extra = f" ({n} referencias actualizadas en scripts)"
        self.sv_status.set(f"Objeto '{new_id}' guardado.{extra}")
        self._run_validation()

    # ── Sincronización automática sustantivos ──────────────────────────────

    def _sync_noun_vocab(self, old_noun=None, new_noun=None):
        """Mantiene vocabulary.nouns sincronizado con los objetos del juego.
        Elimina old_noun si ningún otro objeto lo usa; añade new_noun si no existe."""
        nouns = self.game.setdefault("vocabulary", {}).setdefault("nouns", {})

        # Quitar noun anterior si ya no lo usa ningún objeto
        if old_noun:
            still_used = any(
                (obj.get("noun") or "").strip().lower() == old_noun.lower()
                for obj in self.game.get("objects", {}).values()
            )
            if not still_used:
                nouns.pop(old_noun, None)
                nouns.pop(old_noun.lower(), None)

        # Añadir noun nuevo con el propio nombre como alias
        if new_noun:
            key = new_noun.lower()
            if key not in nouns:
                nouns[key] = [new_noun.lower()]
            self._load_vocab_to_form()

    # ── Vocabulario / Variables / Timers ──

    def _load_vocab_to_form(self):
        vocab = self.game.get("vocabulary", {})
        for key, tree in self._vocab_trees.items():
            tree.delete(*tree.get_children())
            # Entradas predefinidas (solo lectura) para verbos y preposiciones
            for bkey, baliases in BUILTIN_BY_SECTION.get(key, {}).items():
                iid = "__builtin__::" + bkey
                tree.insert("", tk.END, iid=iid,
                            values=(bkey, ", ".join(baliases)),
                            tags=("builtin",))
            for word, aliases in sorted((vocab.get(key) or {}).items()):
                syns = ", ".join(a for a in (aliases or []) if a != word)
                tree.insert("", tk.END, iid=key+"::"+word,
                            values=(word, syns), tags=("word",))

    def _apply_vocab(self):
        vocab = self.game.setdefault("vocabulary", {})
        for key, tree in self._vocab_trees.items():
            section = {}
            for iid in tree.get_children():
                if iid.startswith("__builtin__::"):
                    continue  # los built-ins no se guardan en el YAML
                word, syns = tree.item(iid, "values")
                word = word.strip()
                if not word:
                    continue
                section[word] = [s.strip() for s in syns.split(",") if s.strip()]
            vocab[key] = section
        self.dirty = True
        self.sv_status.set("Vocabulario actualizado.")
        self._run_validation()

    def _vocab_add(self, section_key):
        self._vocab_dialog(section_key, "", "")

    def _vocab_edit_sel(self, section_key):
        tree = self._vocab_trees[section_key]
        sel  = tree.selection()
        if not sel:
            return
        if sel[0].startswith("__builtin__::"):
            messagebox.showinfo("Solo lectura",
                "Este verbo es una constante del intérprete y no se puede editar.")
            return
        word, syns = tree.item(sel[0], "values")
        self._vocab_dialog(section_key, word, syns, old_iid=sel[0])

    def _vocab_del(self, section_key):
        tree = self._vocab_trees[section_key]
        sel  = tree.selection()
        if sel:
            if sel[0].startswith("__builtin__::"):
                messagebox.showinfo("Solo lectura",
                    "Este verbo es una constante del intérprete y no se puede eliminar.")
                return
            tree.delete(sel[0])
            self._apply_vocab()

    def _vocab_dialog(self, section_key, word, syns, old_iid=None):
        win = tk.Toplevel(self.root)
        win.title("Editar entrada")
        win.transient(self.root)
        win.grab_set()
        win.resizable(True, False)

        tk.Label(win, text="Palabra:").grid(row=0, column=0, padx=8, pady=6, sticky=tk.W)
        word_var = tk.StringVar(value=word)
        tk.Entry(win, textvariable=word_var, font=self.fnt_ui, width=22).grid(
            row=0, column=1, padx=8, pady=6, sticky=tk.EW)

        tk.Label(win, text="Sinonimos (coma):").grid(
            row=1, column=0, padx=8, pady=6, sticky=tk.W)
        syns_var = tk.StringVar(value=syns)
        tk.Entry(win, textvariable=syns_var, font=self.fnt_ui, width=30).grid(
            row=1, column=1, padx=8, pady=6, sticky=tk.EW)

        def _save():
            w = word_var.get().strip()
            s = syns_var.get().strip()
            if not w:
                return
            tree    = self._vocab_trees[section_key]
            new_iid = section_key + "::" + w
            if old_iid and old_iid != new_iid:
                tree.delete(old_iid)
            try:
                tree.item(new_iid, values=(w, s), tags=("word",))
            except tk.TclError:
                tree.insert("", tk.END, iid=new_iid, values=(w, s), tags=("word",))
            self._apply_vocab()
            win.destroy()

        bf = tk.Frame(win)
        bf.grid(row=2, column=0, columnspan=2, pady=8)
        ttk.Button(bf, text="Guardar",  command=_save).pack(side=tk.LEFT, padx=6)
        ttk.Button(bf, text="Cancelar", command=win.destroy).pack(side=tk.LEFT, padx=6)
        win.columnconfigure(1, weight=1)
        win.bind("<Return>", lambda e: _save())
        win.bind("<Escape>", lambda e: win.destroy())

    def _load_vars_to_form(self):
        self.vars_tree.delete(*self.vars_tree.get_children())
        for k, v in sorted(self.game.get("variables", {}).items()):
            self.vars_tree.insert("", tk.END, iid=k, values=(k, v, "--"))

    def refresh_vars_actual(self, live_vars):
        for iid in self.vars_tree.get_children():
            vals = self.vars_tree.item(iid, "values")
            self.vars_tree.item(iid, values=(vals[0], vals[1], live_vars.get(vals[0], "--")))

    def _apply_vars(self):
        result = {}
        for iid in self.vars_tree.get_children():
            k, v, _ = self.vars_tree.item(iid, "values")
            try: result[k] = int(v)
            except (ValueError, TypeError):
                try: result[k] = float(v)
                except (ValueError, TypeError): result[k] = v
        self.game["variables"] = result
        self.dirty = True
        self.sv_status.set("Variables actualizadas.")

    def _var_selected(self, event):
        sel = self.vars_tree.selection()
        if not sel:
            return
        k, v_ini, v_act = self.vars_tree.item(sel[0], "values")
        self.var_name_e.delete(0, tk.END); self.var_name_e.insert(0, k)
        self.var_val_e.delete(0, tk.END);  self.var_val_e.insert(0, str(v_ini))
        # Valor actual: editable solo si el intérprete está activo
        interp_active = (self._interp_win is not None)
        self.var_actual_e.config(state=tk.NORMAL)
        self.var_actual_e.delete(0, tk.END)
        self.var_actual_e.insert(0, str(v_act))
        if interp_active:
            self.btn_set_actual.config(state=tk.NORMAL)
            self.var_actual_e.config(state=tk.NORMAL)
        else:
            self.btn_set_actual.config(state=tk.DISABLED)
            self.var_actual_e.config(state=tk.DISABLED)

    def _var_set_actual(self):
        """Aplica el valor actual editado directamente en el intérprete."""
        sel = self.vars_tree.selection()
        if not sel or not self._interp_win:
            return
        k = self.vars_tree.item(sel[0], "values")[0]
        raw = self.var_actual_e.get().strip()
        try:    val = int(raw)
        except ValueError:
            try:    val = float(raw)
            except ValueError: val = raw
        self._interp_win.interp.variables[k] = val
        # Refrescar tabla
        self.refresh_vars_actual(self._interp_win.interp.variables)
        self.sv_status.set(f"Variable '{k}' = {val} (en juego)")

    def _var_new(self):
        name = simpledialog.askstring("Nueva variable", "Nombre:", parent=self.root)
        if not name: return
        try: self.vars_tree.insert("", tk.END, iid=name, values=(name, 0, "--"))
        except tk.TclError: pass
        self._apply_vars()

    def _var_del(self):
        sel = self.vars_tree.selection()
        if sel:
            self.vars_tree.delete(sel[0])
            self._apply_vars()

    def _var_save(self):
        name = self.var_name_e.get().strip()
        val  = self.var_val_e.get().strip()
        if not name: return
        sel = self.vars_tree.selection()
        old_iid = sel[0] if sel else None
        if old_iid and old_iid != name:
            self.vars_tree.delete(old_iid)
        try: self.vars_tree.item(name, values=(name, val, "--"))
        except tk.TclError:
            self.vars_tree.insert("", tk.END, iid=name, values=(name, val, "--"))
        self._apply_vars()

    def _load_timers_to_form(self):
        self.timer_list.delete(0, tk.END)
        for tid in sorted(self.game.get('timers', {}).keys()):
            self.timer_list.insert(tk.END, tid)
        self._timer_clear_form()

    def _timer_clear_form(self):
        for w in (self.timer_id, self.timer_name, self.timer_turns):
            w.delete(0, tk.END)
        self.timer_active.set(False)
        self.timer_loop.set(False)
        self.timer_expire.delete('1.0', tk.END)

    def _timer_list_select(self, event):
        sel = self.timer_list.curselection()
        if sel:
            self._load_timer_to_form(self.timer_list.get(sel[0]))

    def _load_timer_to_form(self, tid):
        t = self.game.get('timers', {}).get(tid, {})
        self.timer_id.delete(0, tk.END);   self.timer_id.insert(0, tid)
        self.timer_name.delete(0, tk.END); self.timer_name.insert(0, t.get('name', ''))
        self.timer_turns.delete(0, tk.END); self.timer_turns.insert(0, str(t.get('turns', 10)))
        self.timer_active.set(bool(t.get('active', False)))
        self.timer_loop.set(bool(t.get('loop', False)))
        self.timer_expire.delete('1.0', tk.END)
        expire = t.get('on_expire', '')
        if isinstance(expire, list):
            expire = '\n'.join(str(x) for x in expire)
        self.timer_expire.insert('1.0', expire)

    def _apply_timer(self):
        old_id = self.timer_list.get(self.timer_list.curselection()[0]) \
                 if self.timer_list.curselection() else None
        new_id = self.timer_id.get().strip()
        if not new_id:
            messagebox.showerror('Error', 'El ID no puede estar vacío.'); return
        try:
            turns = int(self.timer_turns.get().strip() or '10')
        except ValueError:
            turns = 10
        expire = self.timer_expire.get('1.0', tk.END).strip()
        timers = self.game.setdefault('timers', {})
        if old_id and old_id != new_id and old_id in timers:
            del timers[old_id]
        timers[new_id] = {
            'name':    self.timer_name.get().strip(),
            'active':  self.timer_active.get(),
            'turns':   turns,
            'current': turns if self.timer_active.get() else 0,
            'loop':    self.timer_loop.get(),
            'on_expire': expire,
        }
        self.dirty = True
        self._load_timers_to_form()
        # Reseleccionar
        items = list(self.timer_list.get(0, tk.END))
        if new_id in items:
            idx = items.index(new_id)
            self.timer_list.selection_set(idx)
            self._load_timer_to_form(new_id)
        self.sv_status.set(f"Timer '{new_id}' guardado.")
        self._run_validation()

    def _timer_new(self):
        tid = simpledialog.askstring('Nuevo timer', 'ID del timer:', parent=self.root)
        if not tid: return
        tid = tid.strip()
        if tid in self.game.get('timers', {}):
            messagebox.showerror('Error', f"Ya existe '{tid}'"); return
        self.game.setdefault('timers', {})[tid] = {
            'name': tid, 'active': False, 'turns': 10,
            'current': 0, 'loop': False, 'on_expire': ''
        }
        self.dirty = True
        self._load_timers_to_form()
        items = list(self.timer_list.get(0, tk.END))
        if tid in items:
            idx = items.index(tid)
            self.timer_list.selection_set(idx)
            self._load_timer_to_form(tid)

    def _timer_del(self):
        sel = self.timer_list.curselection()
        if not sel: return
        tid = self.timer_list.get(sel[0])
        if messagebox.askyesno('Confirmar', f"¿Eliminar timer '{tid}'?"):
            del self.game['timers'][tid]
            self.dirty = True
            self._load_timers_to_form()

    def _apply_timers(self):
        pass  # ya no se usa — mantenido por compatibilidad

    def _load_condacts_to_form(self):
        condacts = self.game.get('condacts', {})
        for s, t in self._condact_w.items():
            t.delete('1.0', tk.END)
            t.insert('1.0', condacts.get(s, '') or '')
            self._refresh_code_view(s)

    def _apply_condacts(self):
        c = self.game.setdefault('condacts', {})
        for s, t in self._condact_w.items():
            c[s] = t.get('1.0', tk.END).strip()
        self.dirty = True
        self.sv_status.set('Condacts actualizados.')
        self._run_validation()

    # ─── Tab: Código (vista unificada / referencias cruzadas) ──────────────
    #
    # Una sola vista con TODO el código del juego (sin dividir en secciones),
    # filtrable por localización o por objeto.  El código vive en varios
    # orígenes:  condacts.<sección>, locations.<id>.on_enter/on_look y
    # timers.<id>.on_expire.  Los objetos no tienen código propio: solo
    # aparecen referenciados.  Al filtrar:
    #   · Localización → sus on_enter/on_look propios (completos) MÁS cada
    #     bloque IF…ENDIF / ON…ENDON (o tramo suelto) de cualquier script que
    #     la mencione.
    #   · Objeto       → cada bloque IF/ON que mencione su id o su noun.
    # Cada bloque mostrado se edita aquí y, al "Aplicar cambios", se reescribe
    # exactamente en su origen (el resto del script se conserva intacto).

    _CS_TAB_TEXT  = ' Código '
    _CS_NONE_LOC  = '(ninguna)'
    _CS_NONE_OBJ  = '(ninguno)'
    _CS_NONE_VOC  = '(ninguna palabra)'
    _CS_HDR       = '>>> '          # prefijo de las cabeceras de bloque

    # ─── Tab: FX (efectos de sonido beeper) ─────────────────────────────────

    def _build_fx_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=' FX ')
        self._fx_cur = -1
        # Izquierda: lista de efectos + botones CRUD
        left = ttk.Frame(fr)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        ttk.Label(left, text='Efectos (úsalos con PLAY "nombre"):').pack(anchor=tk.W)
        self.fx_list = tk.Listbox(left, width=24, height=16,
                                  exportselection=False, font=self.fnt_code)
        self.fx_list.pack(fill=tk.Y, expand=True)
        self.fx_list.bind('<<ListboxSelect>>', lambda e: self._fx_select())
        self.fx_list.bind('<Double-Button-1>', lambda e: self._fx_play())
        b1 = ttk.Frame(left)
        b1.pack(fill=tk.X, pady=(4, 0))
        for txt, cmd in (('Nuevo', self._fx_new), ('Plantilla', self._fx_template),
                         ('Duplicar', self._fx_dup)):
            ttk.Button(b1, text=txt, width=8, command=cmd).pack(side=tk.LEFT, padx=1)
        b2 = ttk.Frame(left)
        b2.pack(fill=tk.X, pady=(2, 0))
        for txt, cmd in (('Renombrar', self._fx_rename), ('Borrar', self._fx_del)):
            ttk.Button(b2, text=txt, width=12, command=cmd).pack(side=tk.LEFT, padx=1)
        b3 = ttk.Frame(left)
        b3.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(b3, text='Importar .afx / .afb (AYFX)',
                   command=self._fx_import).pack(side=tk.LEFT, padx=1)
        # Derecha: bloques del efecto seleccionado
        right = ttk.Frame(fr)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.fx_title = ttk.Label(right, text='Bloques del efecto', font=self.fnt_bold)
        self.fx_title.pack(anchor=tk.W)
        ttk.Label(right, text='p1=altura inicial, p2=altura final (deslizado), '
                  'dur=duración, ruido=sí/no. Alturas 1-255, dur 1-255.',
                  font=self.fnt_sm).pack(anchor=tk.W, pady=(0, 3))
        cols = ('p1', 'p2', 'dur', 'ruido')
        self.fx_blocks = ttk.Treeview(right, columns=cols, show='headings',
                                      height=12, selectmode='browse')
        for c, w in zip(cols, (60, 60, 60, 60)):
            self.fx_blocks.heading(c, text=c)
            self.fx_blocks.column(c, width=w, anchor=tk.CENTER)
        self.fx_blocks.pack(fill=tk.BOTH, expand=True)
        self.fx_blocks.bind('<Double-Button-1>', lambda e: self._fx_block_edit())
        bb = ttk.Frame(right)
        bb.pack(fill=tk.X, pady=(4, 0))
        for txt, cmd in (('+ Bloque', self._fx_block_add),
                         ('Editar', self._fx_block_edit),
                         ('Eliminar', self._fx_block_del),
                         ('▲', lambda: self._fx_block_move(-1)),
                         ('▼', lambda: self._fx_block_move(1))):
            ttk.Button(bb, text=txt, width=9, command=cmd).pack(side=tk.LEFT, padx=1)
        ttk.Button(bb, text='▶ Probar', command=self._fx_play).pack(side=tk.RIGHT, padx=1)

    def _fx_all(self):
        fx = self.game.setdefault('fx', [])
        if not isinstance(fx, list):
            fx = []
            self.game['fx'] = fx
        return fx

    def _load_fx_to_form(self):
        if not hasattr(self, 'fx_list'):
            return
        self.fx_list.delete(0, tk.END)
        for i, e in enumerate(self._fx_all(), 1):
            tag = 'AY' if e.get('afx') else 'syn'
            self.fx_list.insert(tk.END, '%2d. [%s] %s'
                                % (i, tag, e.get('name', 'efecto')))
        self._fx_cur = -1
        self._fx_load_blocks()

    def _fx_select(self):
        s = self.fx_list.curselection()
        self._fx_cur = s[0] if s else -1
        self._fx_load_blocks()

    def _fx_load_blocks(self):
        self.fx_blocks.delete(*self.fx_blocks.get_children())
        fx = self._fx_all()
        if 0 <= self._fx_cur < len(fx):
            e = fx[self._fx_cur]
            if e.get('afx'):
                try:
                    import afx as _afx
                    nfr = len(_afx.parse_afx(bytes.fromhex(e['afx'])))
                except Exception:
                    nfr = 0
                self.fx_title.config(
                    text='«%s» — efecto AYFX importado (%d frames). Se edita en '
                    'el AY Sound FX Editor; aquí puedes probarlo y usarlo con '
                    'PLAY "%s".' % (e.get('name', ''), nfr, e.get('name', '')))
                return
            self.fx_title.config(text='Bloques de «%s»' % e.get('name', ''))
            for b in e.get('blocks', []):
                self.fx_blocks.insert('', tk.END, values=(
                    b.get('p1', 1), b.get('p2', b.get('p1', 1)),
                    b.get('dur', 1), 'sí' if b.get('noise') else 'no'))
        else:
            self.fx_title.config(text='Bloques del efecto')

    def _fx_cur_effect(self):
        fx = self._fx_all()
        return fx[self._fx_cur] if 0 <= self._fx_cur < len(fx) else None

    def _fx_new(self):
        fx = self._fx_all()
        fx.append({'name': 'efecto%d' % (len(fx) + 1),
                   'blocks': [{'p1': 120, 'p2': 120, 'dur': 5, 'noise': 0}]})
        self.dirty = True
        self._load_fx_to_form()
        self.fx_list.selection_set(len(fx) - 1)
        self._fx_select()

    def _fx_template(self):
        import fx_engine
        names = list(fx_engine.PRESETS.keys())
        dlg = tk.Toplevel(self.root)
        dlg.title('Nuevo efecto desde plantilla')
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text='Elige una plantilla:').pack(padx=12, pady=(12, 4))
        var = tk.StringVar(value=names[0])
        ttk.Combobox(dlg, textvariable=var, values=names, state='readonly',
                     width=20).pack(padx=12)

        def ok():
            import copy as _c
            preset = _c.deepcopy(fx_engine.PRESETS[var.get()])
            fx = self._fx_all()
            preset['name'] = preset.get('name', var.get())
            fx.append(preset)
            self.dirty = True
            dlg.destroy()
            self._load_fx_to_form()
            self.fx_list.selection_set(len(fx) - 1)
            self._fx_select()
        bf = ttk.Frame(dlg)
        bf.pack(pady=10)
        ttk.Button(bf, text='Crear', command=ok).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text='Cancelar', command=dlg.destroy).pack(side=tk.LEFT, padx=3)

    def _fx_dup(self):
        e = self._fx_cur_effect()
        if not e:
            return
        import copy as _c
        d = _c.deepcopy(e)
        d['name'] = e.get('name', 'efecto') + '_copia'
        fx = self._fx_all()
        fx.insert(self._fx_cur + 1, d)
        self.dirty = True
        self._load_fx_to_form()
        self.fx_list.selection_set(self._fx_cur + 1)
        self._fx_select()

    def _fx_rename(self):
        e = self._fx_cur_effect()
        if not e:
            return
        from tkinter import simpledialog
        v = simpledialog.askstring('Renombrar efecto', 'Nombre:',
                                   initialvalue=e.get('name', ''), parent=self.root)
        if v:
            e['name'] = v.strip()
            self.dirty = True
            cur = self._fx_cur
            self._load_fx_to_form()
            self.fx_list.selection_set(cur)
            self._fx_select()

    def _fx_del(self):
        e = self._fx_cur_effect()
        if not e:
            return
        if not messagebox.askyesno('Borrar efecto',
                                   '¿Borrar «%s»?\n(Los PLAY que usen ese nombre '
                                   'dejarán de sonar.)' % e.get('name', '')):
            return
        del self._fx_all()[self._fx_cur]
        self.dirty = True
        self._load_fx_to_form()

    def _fx_block_dialog(self, init=None):
        init = init or {'p1': 120, 'p2': 120, 'dur': 5, 'noise': 0}
        dlg = tk.Toplevel(self.root)
        dlg.title('Bloque de sonido')
        dlg.transient(self.root)
        dlg.grab_set()
        vp1 = tk.IntVar(value=int(init.get('p1', 120)))
        vp2 = tk.IntVar(value=int(init.get('p2', init.get('p1', 120))))
        vd = tk.IntVar(value=int(init.get('dur', 5)))
        vn = tk.BooleanVar(value=bool(init.get('noise', 0)))
        g = ttk.Frame(dlg)
        g.pack(padx=12, pady=12)
        rows = (('Altura inicial (p1) 1-255', vp1),
                ('Altura final (p2) 1-255', vp2),
                ('Duración (dur) 1-255', vd))
        for i, (lbl, var) in enumerate(rows):
            ttk.Label(g, text=lbl).grid(row=i, column=0, sticky=tk.W, pady=2)
            ttk.Spinbox(g, from_=1, to=255, textvariable=var,
                        width=6).grid(row=i, column=1, padx=6)
        ttk.Checkbutton(g, text='Ruido', variable=vn).grid(row=3, column=0,
                                                           sticky=tk.W, pady=2)
        res = {}

        def ok():
            res.update(p1=max(1, min(255, vp1.get())),
                       p2=max(1, min(255, vp2.get())),
                       dur=max(1, min(255, vd.get())),
                       noise=1 if vn.get() else 0)
            dlg.destroy()
        bf = ttk.Frame(dlg)
        bf.pack(pady=(0, 10))
        ttk.Button(bf, text='Aceptar', command=ok).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text='Cancelar', command=dlg.destroy).pack(side=tk.LEFT, padx=3)
        dlg.wait_window()
        return res or None

    def _fx_block_add(self):
        e = self._fx_cur_effect()
        if not e:
            messagebox.showinfo('FX', 'Crea o selecciona un efecto primero.')
            return
        if e.get('afx'):
            messagebox.showinfo('FX', 'Es un efecto AYFX importado: se edita en el '
                                'AY Sound FX Editor de Shiru, no aquí.')
            return
        b = self._fx_block_dialog()
        if b:
            e.setdefault('blocks', []).append(b)
            self.dirty = True
            self._fx_load_blocks()

    def _fx_block_sel(self):
        s = self.fx_blocks.selection()
        if not s:
            return -1
        return self.fx_blocks.index(s[0])

    def _fx_block_edit(self):
        e = self._fx_cur_effect()
        i = self._fx_block_sel()
        if not e or i < 0:
            return
        b = self._fx_block_dialog(e['blocks'][i])
        if b:
            e['blocks'][i] = b
            self.dirty = True
            self._fx_load_blocks()

    def _fx_block_del(self):
        e = self._fx_cur_effect()
        i = self._fx_block_sel()
        if not e or i < 0:
            return
        del e['blocks'][i]
        self.dirty = True
        self._fx_load_blocks()

    def _fx_block_move(self, d):
        e = self._fx_cur_effect()
        i = self._fx_block_sel()
        if not e or i < 0:
            return
        j = i + d
        bl = e['blocks']
        if 0 <= j < len(bl):
            bl[i], bl[j] = bl[j], bl[i]
            self.dirty = True
            self._fx_load_blocks()
            ch = self.fx_blocks.get_children()
            if j < len(ch):
                self.fx_blocks.selection_set(ch[j])

    def _play_wav_bytes(self, data):
        """Reproduce un WAV (bytes) por el altavoz del PC. Usa winsound si está
        (Windows) y, si no, vuelca a un temporal y lo abre con el reproductor."""
        try:
            import winsound
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
            return
        except Exception:
            pass
        try:
            import tempfile
            fp = os.path.join(tempfile.gettempdir(), 'scriba_fx.wav')
            with open(fp, 'wb') as f:
                f.write(data)
            if sys.platform.startswith('win'):
                os.startfile(fp)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['afplay', fp])
            else:
                import subprocess
                subprocess.Popen(['aplay', fp])
        except Exception as ex:
            messagebox.showinfo('FX', 'Vista previa no disponible aquí: %s' % ex)

    def _fx_wav_of(self, e):
        """WAV (bytes) de un efecto (AYFX importado o sintetizado)."""
        if e.get('afx'):
            import afx as _afx
            return _afx.render_wav(_afx.parse_afx(bytes.fromhex(e['afx'])))
        import fx_engine
        return fx_engine.wav_bytes(e)

    def _fx_play(self):
        e = self._fx_cur_effect()
        if not e:
            return
        try:
            data = self._fx_wav_of(e)
        except Exception as ex:
            messagebox.showerror('FX', 'No se pudo sintetizar: %s' % ex)
            return
        self._play_wav_bytes(data)

    def _fx_import(self):
        """Importa efectos del AY Sound FX Editor de Shiru (.afx único o banco
        .afb). Abre un diálogo para OÍR cada efecto candidato y elegir SOLO los que
        interesen: así los importados quedan numerados de forma compacta (1,2,3...)
        y los PLAY n no dejan huecos. Quedan como efectos 'AY' (PLAY n)."""
        paths = filedialog.askopenfilenames(
            title='Importar efectos AYFX (.afx / .afb)',
            filetypes=[('AYFX', '*.afx *.afb'), ('Todos', '*.*')])
        if not paths:
            return
        import afx as _afx
        # Reunir candidatos (sin añadir nada todavía).
        cand = []      # cada uno: {'name','afx'(hex),'frames','dur'}
        for p in paths:
            try:
                data = open(p, 'rb').read()
            except Exception:
                continue
            base = os.path.splitext(os.path.basename(p))[0]
            raws = (_afx.split_afb(data) if p.lower().endswith('.afb')
                    else [data])
            multi = len(raws) > 1
            for k, raw in enumerate(raws):
                fr = _afx.parse_afx(raw)
                if not fr:
                    continue
                cand.append({'name': ('%s_%d' % (base, k + 1)) if multi else base,
                             'afx': raw.hex(), 'frames': len(fr),
                             'dur': len(fr) / 50.0})
        if not cand:
            messagebox.showwarning('Importar AYFX',
                                   'No se pudo leer ningún efecto de esos archivos.')
            return
        self._fx_preview_dialog(cand)

    _FX_OFF = '☐'      # ☐ casilla vacía
    _FX_ON = '☑'       # ☑ casilla marcada

    def _fx_preview_dialog(self, cand):
        """Diálogo de importación. Siempre hay un sonido resaltado (blanco sobre
        azul): moverse con ↑/↓ (o clic) cambia el resaltado y REPRODUCE ese sonido;
        ESPACIO marca/desmarca su casilla. Solo se importan los marcados (índices
        PLAY compactos, sin huecos)."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Previsualizar e importar AYFX')
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text='↑/↓ o clic: cambia de sonido y lo reproduce.  '
                  'ESPACIO: marca/desmarca.  Solo se importan los marcados.',
                  wraplength=460, justify=tk.LEFT,
                  foreground='#556677').pack(anchor=tk.W, padx=10, pady=(10, 4))
        mid = ttk.Frame(dlg)
        mid.pack(fill=tk.BOTH, expand=True, padx=10)
        sb = ttk.Scrollbar(mid, orient=tk.VERTICAL)
        tv = ttk.Treeview(mid, columns=('chk', 'desc'), show='headings',
                          height=14, selectmode='browse', yscrollcommand=sb.set)
        tv.heading('chk', text='✓')
        tv.column('chk', width=34, anchor=tk.CENTER, stretch=False)
        tv.heading('desc', text='Efecto')
        tv.column('desc', width=380, anchor=tk.W)
        sb.config(command=tv.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ids = []
        checked = set()                         # iids marcados (por defecto ninguno)
        for c in cand:
            iid = tv.insert('', tk.END, values=(
                self._FX_OFF, '%s   %d frames · %.2fs'
                % (c['name'], c['frames'], c['dur'])))
            ids.append(iid)

        info = tk.StringVar(value='')
        armed = [False]      # evita reproducir en la selección inicial

        def _upd():
            info.set('%d de %d marcados' % (len(checked), len(cand)))

        def _cur():
            s = tv.selection()
            return s[0] if s else (tv.focus() or (ids[0] if ids else None))

        def _play(iid):
            try:
                self._play_wav_bytes(self._fx_wav_of(cand[ids.index(iid)]))
            except Exception as ex:
                messagebox.showerror('FX', 'No se pudo reproducir: %s' % ex,
                                     parent=dlg)

        def _on_select(_e=None):
            if not armed[0]:
                return
            iid = _cur()
            if iid:
                _play(iid)
        tv.bind('<<TreeviewSelect>>', _on_select)

        def _toggle(_e=None):
            iid = _cur()
            if not iid:
                return 'break'
            if iid in checked:
                checked.discard(iid); tv.set(iid, 'chk', self._FX_OFF)
            else:
                checked.add(iid); tv.set(iid, 'chk', self._FX_ON)
            _upd()
            return 'break'                       # no usar el espacio para otra cosa
        tv.bind('<space>', _toggle)

        def _all():
            checked.clear(); checked.update(ids)
            for iid in ids:
                tv.set(iid, 'chk', self._FX_ON)
            _upd()

        def _none():
            checked.clear()
            for iid in ids:
                tv.set(iid, 'chk', self._FX_OFF)
            _upd()

        def _do_import():
            sel = [i for i, iid in enumerate(ids) if iid in checked]
            if not sel:
                messagebox.showinfo('Importar AYFX',
                                    'No has marcado ningún efecto.', parent=dlg)
                return
            fx = self._fx_all()
            for i in sel:
                c = cand[i]
                fx.append({'name': c['name'], 'afx': c['afx']})
            dlg.destroy()
            self.dirty = True
            self._load_fx_to_form()
            self.fx_list.selection_set(len(fx) - 1)
            self._fx_select()
            messagebox.showinfo('Importar AYFX',
                                'Importados %d efecto(s).' % len(sel))

        bb = ttk.Frame(dlg)
        bb.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(bb, text='Marcar todo', command=_all).pack(side=tk.LEFT)
        ttk.Button(bb, text='Desmarcar', command=_none).pack(side=tk.LEFT, padx=4)
        ttk.Label(bb, textvariable=info, foreground='#7c93ad').pack(side=tk.LEFT,
                                                                    padx=10)
        ttk.Button(bb, text='Cancelar', command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(bb, text='Importar marcados',
                   command=_do_import).pack(side=tk.RIGHT, padx=4)
        _upd()
        # Resaltar el primero y dar el foco al teclado; armar la reproducción tras
        # asentarse la selección inicial (para no sonar nada al abrir).
        if ids:
            tv.selection_set(ids[0]); tv.focus(ids[0])
        tv.focus_set()
        dlg.after(200, lambda: armed.__setitem__(0, True))
        dlg.bind('<Escape>', lambda e: dlg.destroy())

    def _build_crossref_tab(self):
        fr = ttk.Frame(self.nb)
        self.nb.add(fr, text=self._CS_TAB_TEXT)

        self._cs_loc_var = tk.StringVar(value=self._CS_NONE_LOC)
        self._cs_obj_var = tk.StringVar(value=self._CS_NONE_OBJ)
        self._cs_voc_var = tk.StringVar(value=self._CS_NONE_VOC)
        self._cs_info    = tk.StringVar(value='')
        self._cs_sources = {}     # origen → lista de grupos (listas de líneas)
        self._cs_units   = []     # orden de render: (origen, índice_de_grupo)
        self._cs_targets = []     # tokens buscados (para resaltar)

        top = ttk.Frame(fr)
        top.pack(fill=tk.X, padx=6, pady=(6, 2))
        ttk.Label(top, text='Localización:').pack(side=tk.LEFT)
        self._cs_loc_combo = ttk.Combobox(top, textvariable=self._cs_loc_var,
                                           state='readonly', width=20,
                                           values=[self._CS_NONE_LOC])
        self._cs_loc_combo.pack(side=tk.LEFT, padx=(2, 10))
        self._cs_loc_combo.bind('<<ComboboxSelected>>', self._crossref_on_loc)
        ttk.Label(top, text='Objeto:').pack(side=tk.LEFT)
        self._cs_obj_combo = ttk.Combobox(top, textvariable=self._cs_obj_var,
                                           state='readonly', width=20,
                                           values=[self._CS_NONE_OBJ])
        self._cs_obj_combo.pack(side=tk.LEFT, padx=(2, 10))
        self._cs_obj_combo.bind('<<ComboboxSelected>>', self._crossref_on_obj)
        ttk.Label(top, text='Vocabulario:').pack(side=tk.LEFT)
        self._cs_voc_combo = ttk.Combobox(top, textvariable=self._cs_voc_var,
                                           state='readonly', width=18,
                                           values=[self._CS_NONE_VOC])
        self._cs_voc_combo.pack(side=tk.LEFT, padx=(2, 10))
        self._cs_voc_combo.bind('<<ComboboxSelected>>', self._crossref_on_voc)
        ttk.Button(top, text='Mostrar todo',
                   command=self._crossref_show_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text='↻ Actualizar listas',
                   command=self._crossref_refresh_combos).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text='Aplicar cambios',
                   command=self._crossref_apply).pack(side=tk.RIGHT, padx=2)

        ttk.Label(fr, textvariable=self._cs_info,
                  foreground='#7c93ad').pack(anchor=tk.W, padx=8)

        hint = ttk.Label(fr, foreground='#667788', wraplength=560, justify=tk.LEFT,
                         text='Filtra por localización u objeto. NO modifiques las '
                              'líneas que empiezan por ">>> " (marcan el origen de '
                              'cada bloque). Pulsa "Aplicar cambios" para guardar.')
        hint.pack(side=tk.BOTTOM, anchor=tk.W, padx=8, pady=(0, 4))

        body = ttk.Frame(fr)
        t = tk.Text(body, wrap=tk.NONE, undo=True, font=self.fnt_code,
                    bg="#0f1623", fg="#d8e2f0", insertbackground="#ffffff",
                    selectbackground="#1a4a8a")
        vs = ttk.Scrollbar(body, orient=tk.VERTICAL, command=t.yview)
        hs = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=t.xview)
        t.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        for tag, color in (("kw", "#66b3ff"), ("cmd", "#ffcc66"),
                           ("cond", "#7fd6a0"), ("num", "#c0a0ff"),
                           ("str", "#e69ae6"), ("rem", "#5a6b80")):
            t.tag_configure(tag, foreground=color)
        t.tag_configure("xref_hdr", foreground="#0f1623", background="#ffae57")
        t.tag_configure("xref_hit", background="#1f5236")
        self._cs_text = t

        bar = SearchBar(fr, t)

        def _show_bar(event=None):
            bar.pack(fill=tk.X, before=body)
            bar._entry.focus_set()
            bar._entry.select_range(0, tk.END)
            bar._do_search()
            return "break"
        t.bind("<Control-f>", _show_bar)
        t.bind("<Control-F>", _show_bar)

        vs.pack(side=tk.RIGHT, fill=tk.Y)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # ── combos ───────────────────────────────────────────────────────────────

    def _crossref_refresh_combos(self):
        if not hasattr(self, '_cs_loc_combo'):
            return
        locs = [self._CS_NONE_LOC] + sorted(self.game.get('locations', {}).keys())
        objs = [self._CS_NONE_OBJ] + sorted(self.game.get('objects', {}).keys())
        vocab = self.game.get('vocabulary', {})
        words = []
        for sec in ('verbs', 'nouns', 'prepositions'):
            words += list((vocab.get(sec) or {}).keys())
        vocs = [self._CS_NONE_VOC] + sorted(dict.fromkeys(words))
        self._cs_loc_combo['values'] = locs
        self._cs_obj_combo['values'] = objs
        self._cs_voc_combo['values'] = vocs
        if self._cs_loc_var.get() not in locs:
            self._cs_loc_var.set(self._CS_NONE_LOC)
        if self._cs_obj_var.get() not in objs:
            self._cs_obj_var.set(self._CS_NONE_OBJ)
        if self._cs_voc_var.get() not in vocs:
            self._cs_voc_var.set(self._CS_NONE_VOC)

    def _crossref_on_loc(self, event=None):
        if self._cs_loc_var.get() != self._CS_NONE_LOC:
            self._cs_obj_var.set(self._CS_NONE_OBJ)
            self._cs_voc_var.set(self._CS_NONE_VOC)
        self._crossref_rebuild()

    def _crossref_on_obj(self, event=None):
        if self._cs_obj_var.get() != self._CS_NONE_OBJ:
            self._cs_loc_var.set(self._CS_NONE_LOC)
            self._cs_voc_var.set(self._CS_NONE_VOC)
        self._crossref_rebuild()

    def _crossref_on_voc(self, event=None):
        if self._cs_voc_var.get() != self._CS_NONE_VOC:
            self._cs_loc_var.set(self._CS_NONE_LOC)
            self._cs_obj_var.set(self._CS_NONE_OBJ)
        self._crossref_rebuild()

    def _crossref_show_all(self):
        self._cs_loc_var.set(self._CS_NONE_LOC)
        self._cs_obj_var.set(self._CS_NONE_OBJ)
        self._cs_voc_var.set(self._CS_NONE_VOC)
        self._crossref_rebuild()

    # ── segmentación y búsqueda ────────────────────────────────────────────

    # Tokens que abren / cierran un bloque de nivel superior. Se segmenta por
    # IF…ENDIF y por ON…ENDON: así, al filtrar, solo se muestran los bloques
    # que realmente mencionan la entidad (y no todo un condact entero porque
    # la mencione en una línea suelta lejana).
    _CS_OPEN  = {'ON', 'IF'}
    _CS_CLOSE = {'ENDON', 'ENDIF'}

    @staticmethod
    def _crossref_segments(text):
        """Divide un script en grupos contiguos de líneas: cada bloque de
        nivel superior IF…ENDIF u ON…ENDON es un grupo, y los tramos de
        sentencias sueltas entre ellos forman otro. La concatenación de los
        grupos reproduce exactamente el texto original."""
        lines = (text or '').split('\n')
        groups, run = [], []
        OPEN, CLOSE = ScribaEditor._CS_OPEN, ScribaEditor._CS_CLOSE

        def head(line):
            s = line.strip()
            m = re.match(r'\d+\s+(.*)', s)
            if m:
                s = m.group(1)
            return s.split(None, 1)[0].upper() if s else ''

        i, n = 0, len(lines)
        while i < n:
            if head(lines[i]) in OPEN:
                if run:
                    groups.append(run)
                    run = []
                depth, block = 0, []
                while i < n:
                    h = head(lines[i])
                    block.append(lines[i])
                    i += 1
                    if h in OPEN:
                        depth += 1
                    elif h in CLOSE:
                        depth -= 1
                        if depth <= 0:
                            break
                groups.append(block)
            else:
                run.append(lines[i])
                i += 1
        if run:
            groups.append(run)
        return groups or [['']]

    def _crossref_refs(self, seg_text, targets):
        up = seg_text.upper()
        return any(re.search(r'\b' + re.escape(tg) + r'\b', up) for tg in targets)

    # ── construir / refrescar la vista ─────────────────────────────────────

    def _crossref_rebuild(self):
        if not hasattr(self, '_cs_text'):
            return
        loc = self._cs_loc_var.get()
        obj = self._cs_obj_var.get()
        voc = self._cs_voc_var.get()
        filt = None
        targets = []
        if loc and loc != self._CS_NONE_LOC:
            filt = ('loc', loc)
            targets = [loc.upper()]
        elif obj and obj != self._CS_NONE_OBJ:
            filt = ('obj', obj)
            o = self.game.get('objects', {}).get(obj, {})
            noun = (o.get('noun') or '').strip()
            targets = [obj.upper()]
            if noun:
                targets.append(noun.upper())
                if len(noun) > 5:
                    targets.append(noun[:5].upper())
            targets = list(dict.fromkeys(targets))
        elif voc and voc != self._CS_NONE_VOC:
            filt = ('voc', voc)
            targets = [voc.upper()]
            vocab = self.game.get('vocabulary', {})
            for sec in ('verbs', 'nouns', 'prepositions'):
                for a in ((vocab.get(sec) or {}).get(voc) or []):
                    targets.append(a.upper())
                    if len(a) > 5:
                        targets.append(a[:5].upper())
            targets = list(dict.fromkeys(targets))
        self._cs_targets = targets
        self._cs_sources = {}
        self._cs_units = []
        pieces = []
        nblocks = nsources = 0

        for name, text in self._iter_scripts():
            owned = bool(filt and filt[0] == 'loc' and name in (
                f'locations.{loc}.on_enter', f'locations.{loc}.on_look'))
            if owned:
                groups = [(text or '').split('\n')]
                unit_idx = [0]
            elif filt is None:
                if not (text or '').strip():
                    continue
                groups = [(text or '').split('\n')]
                unit_idx = [0]
            else:
                if not (text or '').strip():
                    continue
                groups = self._crossref_segments(text)
                unit_idx = [gi for gi, g in enumerate(groups)
                            if self._crossref_refs('\n'.join(g), targets)]
                if not unit_idx:
                    continue
            self._cs_sources[name] = groups
            nsources += 1
            for gi in unit_idx:
                self._cs_units.append((name, gi))
                nblocks += 1
                # Cuerpo = exactamente las líneas del grupo (sin separadores
                # cosméticos: añadir blancos corrompería bloques que terminan
                # en línea vacía al reescribirlos).
                pieces.append(self._CS_HDR + name)
                pieces.extend(groups[gi])

        t = self._cs_text
        t.delete('1.0', tk.END)
        if not self._cs_units:
            if filt is None:
                t.insert('1.0', '(No hay código en el juego.)')
            else:
                ent = {'loc': loc, 'obj': obj, 'voc': voc}[filt[0]]
                t.insert('1.0', f'(No se ha encontrado código que mencione «{ent}».)')
            self._cs_info.set('0 bloques')
            return

        t.insert('1.0', '\n'.join(pieces))
        self._highlight_code(t)
        self._crossref_highlight_extra()

        if filt is None:
            self._cs_info.set(f'Todo el código · {nblocks} bloques en {nsources} scripts')
        else:
            ent = {'loc': f'localización «{loc}»',
                   'obj': f'objeto «{obj}»',
                   'voc': f'palabra «{voc}»'}[filt[0]]
            self._cs_info.set(f'{ent} · {nblocks} bloques en {nsources} scripts')

    def _crossref_highlight_extra(self):
        t = self._cs_text
        t.tag_remove('xref_hdr', '1.0', tk.END)
        t.tag_remove('xref_hit', '1.0', tk.END)
        total = int(t.index('end-1c').split('.')[0])
        for ln in range(1, total + 1):
            if t.get(f'{ln}.0', f'{ln}.end').startswith(self._CS_HDR):
                t.tag_add('xref_hdr', f'{ln}.0', f'{ln}.end')
        content = t.get('1.0', 'end-1c')
        for tg in self._cs_targets:
            for m in re.finditer(r'\b' + re.escape(tg) + r'\b', content, re.IGNORECASE):
                t.tag_add('xref_hit', f'1.0+{m.start()}c', f'1.0+{m.end()}c')
        t.tag_raise('xref_hit')

    # ── aplicar los cambios de vuelta a cada origen ─────────────────────────

    def _crossref_write_back(self, source, text):
        g = self.game
        if source.startswith('condacts.'):
            g.setdefault('condacts', {})[source[len('condacts.'):]] = text
        elif source.startswith('locations.'):
            lid, hook = source[len('locations.'):].rsplit('.', 1)
            loc = g.get('locations', {}).get(lid)
            if loc is not None:
                if text:
                    loc[hook] = text
                else:
                    loc.pop(hook, None)
        elif source.startswith('timers.'):
            tid, field = source[len('timers.'):].rsplit('.', 1)
            tim = g.get('timers', {}).get(tid)
            if tim is not None:
                tim[field] = text

    def _crossref_apply(self):
        if not getattr(self, '_cs_units', None):
            self.sv_status.set('Nada que aplicar en la vista de código.')
            return
        content = self._cs_text.get('1.0', 'end-1c')

        # Reparsear: cada cabecera ">>> origen" abre un bloque
        parsed, cur = [], None
        for ln in content.split('\n'):
            if ln.startswith(self._CS_HDR):
                if cur is not None:
                    parsed.append(cur)
                cur = [ln[len(self._CS_HDR):].strip(), []]
            elif cur is not None:
                cur[1].append(ln)
        if cur is not None:
            parsed.append(cur)

        # Si el editor de texto añadió una línea final vacía (cuerpo del último
        # bloque), no pasa nada: forma parte del cuerpo y se conserva tal cual.
        if len(parsed) != len(self._cs_units):
            messagebox.showerror(
                'No se puede aplicar',
                f'El número de bloques no coincide ({len(parsed)} encontrados, '
                f'{len(self._cs_units)} esperados).\n\nNo edites ni borres las '
                f'líneas que empiezan por ">>> ".')
            return
        for i, (src, _) in enumerate(self._cs_units):
            if parsed[i][0] != src:
                messagebox.showerror(
                    'No se puede aplicar',
                    f'La cabecera del bloque {i + 1} ha cambiado '
                    f'("{parsed[i][0]}" ≠ "{src}").\n\nNo edites las líneas ">>> ".')
                return

        # Texto original de cada origen (antes de volcar las ediciones), para
        # reescribir SOLO lo que de verdad cambió (no tocar lo no editado).
        orig = {src: '\n'.join('\n'.join(g) for g in groups).strip()
                for src, groups in self._cs_sources.items()}

        for i, (src, gi) in enumerate(self._cs_units):
            self._cs_sources[src][gi] = parsed[i][1]

        changed = 0
        for src, groups in self._cs_sources.items():
            rebuilt = '\n'.join('\n'.join(g) for g in groups).strip()
            if rebuilt != orig[src]:
                self._crossref_write_back(src, rebuilt)
                changed += 1

        if not changed:
            self.sv_status.set('Vista de código: sin cambios que aplicar.')
            return

        self.dirty = True
        self._load_condacts_to_form()
        if self.sel:
            self._load_loc_to_form(self.sel)
        self._run_validation()
        self.sv_status.set(f'Código aplicado desde la vista unificada '
                           f'({changed} script(s) modificados).')
        self._crossref_rebuild()

    def _load_all_forms(self):
        self._load_meta_to_form()
        self._refresh_loc_list()
        self._refresh_obj_tree()
        self._load_vocab_to_form()
        self._load_vars_to_form()
        self._load_timers_to_form()
        self._load_condacts_to_form()
        self._load_fx_to_form()
        self._reset_detalle_forms()
        self._crossref_refresh_combos()
        self._crossref_rebuild()

    def _reset_detalle_forms(self):
        """Al cargar/crear un juego, deja los formularios de detalle (localización
        y objeto) en el primer ítem del juego nuevo, o los limpia si no hay ninguno.
        Evita que queden datos del juego anterior en las pestañas de datos."""
        locs = sorted(self.game.get('locations', {}).keys())
        if locs:
            self.sel = locs[0]
            self._load_loc_to_form(locs[0])
            try:
                items = list(self.loc_list.get(0, tk.END))
                if locs[0] in items:
                    i = items.index(locs[0])
                    self.loc_list.selection_clear(0, tk.END)
                    self.loc_list.selection_set(i)
                    self.loc_list.see(i)
            except Exception:
                pass
        else:
            self.sel = None
            self._load_loc_to_form('')          # formulario de localización vacío
        objs = sorted(self.game.get('objects', {}).keys())
        if objs:
            self._load_obj_to_form(objs[0])
            try:
                self.obj_tree.selection_set(objs[0])
                self.obj_tree.see(objs[0])
            except Exception:
                pass
        else:
            self._load_obj_to_form('')          # formulario de objeto vacío

    def _new_file(self):
        if self.dirty and not messagebox.askyesno(
                'Sin guardar', 'Hay cambios sin guardar. Continuar?'):
            return
        # Juego en blanco: cerrar el probador si estaba abierto (no hay nada
        # que jugar todavía).
        if self._interp_win is not None:
            try:
                self._interp_win.close()
            except Exception:
                pass
        self.game      = self._empty_game()
        self.positions = {}
        self.sel       = None
        self.level     = 0
        self.filepath  = None
        self.dirty     = False
        self._load_all_forms()
        self._redraw()
        self.root.title('Scriba ' + SCRIBA_VERSION)

    def _open_file(self):
        path = filedialog.askopenfilename(
            title='Abrir juego Scriba',
            filetypes=[('Juegos Scriba','*.yaml *.yml *.json'),
                       ('YAML','*.yaml *.yml'),('JSON','*.json'),
                       ('Todos','*.*')])
        if path:
            self._do_open(path)

    def _do_open(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if path.lower().endswith('.json'):
                    game = json.load(f)
                else:
                    game = yaml.safe_load(f)
        except Exception as e:
            messagebox.showerror('Error', 'No se pudo abrir: ' + str(e))
            return
        editor_data = game.pop('_editor', {}) if isinstance(game, dict) else {}
        self.game      = game
        self.filepath  = path
        self.positions = {}
        self.sel       = None
        self.level     = 0
        self.dirty     = False
        self._restore_positions(editor_data)
        self._flatten_positions()   # mapa plano: niveles antiguos → diagonal
        self._load_all_forms()
        self._redraw()
        self.root.after(150, self._zoom_fit)   # ver todo el mapa al abrir
        self.root.title('Scriba ' + SCRIBA_VERSION + ' - ' + os.path.basename(path))
        self.sv_status.set('Abierto: ' + path + '  |  ' +
                           str(len(self.game.get('locations',{}))) + ' locs, ' +
                           str(len(self.game.get('objects',{}))) + ' objetos')
        self._run_validation()
        # Si el probador de juegos está abierto, reinícialo con el juego recién
        # cargado (nuevo intérprete, salida/histórico/snapshot limpios).
        if self._interp_win is not None:
            try:
                if self._interp_win.win.winfo_exists():
                    self._interp_win._restart()
            except Exception:
                pass

    def _restore_positions(self, editor_data):
        """Restaura posiciones guardadas en '_editor'; si no hay, usa BFS.
        Las localizaciones sin posición guardada se colocan en una fila aparte."""
        locs = self.game.get('locations', {})
        saved = {}
        if isinstance(editor_data, dict):
            raw = editor_data.get('positions', {})
            if isinstance(raw, dict):
                for lid, p in raw.items():
                    if (lid in locs and isinstance(p, (list, tuple))
                            and len(p) == 3):
                        try:
                            saved[lid] = [int(p[0]), int(p[1]), int(p[2])]
                        except (TypeError, ValueError):
                            pass
        if not saved:
            self._rebuild_positions()
            return
        self.positions = saved
        # Colocar las localizaciones que no tienen posición guardada
        missing = [lid for lid in locs if lid not in saved]
        if missing:
            max_row = max((p[1] for p in saved.values()), default=0)
            uc, ur = 0, max_row + 2
            for lid in sorted(missing):
                while self._pos_overlap(self.positions, uc, ur, 0):
                    uc += 1
                self.positions[lid] = [uc, ur, 0]
                uc += 1

    def _rebuild_positions(self):
        """Reconstruye posiciones en cuadrícula (col, row, level) usando BFS."""
        locs = self.game.get('locations', {})
        if not locs:
            return
        placed = {}
        start = (self.game.get('metadata', {}).get('start_location')
                 or next(iter(locs)))
        if start not in locs:
            start = next(iter(locs))

        queue = [(start, 0, 0, 0)]
        visited = set()
        while queue:
            lid, col, row, lev = queue.pop(0)
            if lid in visited or lid not in locs:
                continue
            visited.add(lid)
            # Encontrar celda libre
            fc, fr = col, row
            attempts = 0
            while self._pos_overlap(placed, fc, fr, lev) and attempts < 40:
                fc += 1
                attempts += 1
            placed[lid] = [fc, fr, lev]
            for direction, dest in locs[lid].get('exits', {}).items():
                if dest and dest not in visited and dest in locs:
                    dc, dr, dl = DIR_DELTA.get(direction, (1, 0, 0))
                    queue.append((dest, fc + dc, fr + dr, lev + dl))

        # Localizaciones sin conexión → fila separada debajo
        unvisited = [lid for lid in locs if lid not in placed]
        if unvisited:
            max_row = max((p[1] for p in placed.values()), default=0)
            uc, ur = 0, max_row + 2
            for lid in sorted(unvisited):
                while self._pos_overlap(placed, uc, ur, 0):
                    uc += 1
                placed[lid] = [uc, ur, 0]
                uc += 1

        self.positions = placed

    def _pos_overlap(self, placed, col, row, level):
        """True si (col, row, level) coincide con algún nodo ya colocado."""
        for p in placed.values():
            if p[0] == col and p[1] == row and p[2] == level:
                return True
        return False

    def _pos_free_placed(self, placed, col, row, level):
        # Compatibilidad legado — no debería usarse
        return not self._pos_overlap(placed, col, row, level)

    def _save_file(self):
        if not self.filepath:
            self._save_as()
        else:
            self._write(self.filepath)

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERPRETE
    # ═══════════════════════════════════════════════════════════════════════════

    def _dbg_step(self):
        """F10: avanza un paso en el debug del intérprete."""
        if self._interp_win and self._interp_win.win.winfo_exists():
            self._interp_win._step()

    def _dbg_continue(self):
        """F5: continúa la ejecución en el debug."""
        if self._interp_win and self._interp_win.win.winfo_exists():
            self._interp_win._continue_exec()

    def _open_interpreter(self):
        if self._interp_win is not None:
            # Ya existe — dar foco a la entrada
            try:
                self._interp_win.entry.focus_set()
            except Exception:
                pass
            return
        if not self.game.get('locations'):
            messagebox.showinfo('Sin juego', 'Abre o crea un juego primero.')
            return
        # Quitar el placeholder
        self._interp_placeholder.pack_forget()
        # Mover el sash para dar espacio al intérprete (~55% props, ~45% interp)
        def _show_interp():
            h = self._right_pw.winfo_height()
            if h > 100:
                self._right_pw.sash_place(0, 0, int(h * 0.52))
            else:
                self._right_pw.after(100, _show_interp)
        self._right_pw.after(50, _show_interp)
        self._interp_win = InterpreterWindow(self, self._interp_frame)

    def highlight_player_loc(self, loc_id):
        self.player_loc = loc_id
        if loc_id and loc_id in self.positions:
            self.level = self.positions[loc_id][2]
        self._redraw()

    def highlight_condact(self, section, line_text=None):
        """Activa la pestaña del condact en el editor y resalta la línea activa."""
        try:
            # Seleccionar tab Condacts en el notebook principal
            tabs = list(self.nb.tabs())
            for i, tab in enumerate(tabs):
                if 'Condacts' in self.nb.tab(tab, 'text'):
                    self.nb.select(i)
                    break
            # Seleccionar sub-tab de la sección
            t = self._condact_w.get(section)
            if t is None:
                return
            if section in self._condact_sections:
                self._condact_nb.select(self._condact_sections.index(section))
            # Limpiar highlight anterior
            for tw in self._condact_w.values():
                tw.tag_remove('exec_hi',   '1.0', tk.END)
                tw.tag_remove('exec_line', '1.0', tk.END)
            if not line_text:
                return
            needle = line_text.strip()
            if not needle:
                return
            # Buscar la línea (exacta primero, luego parcial)
            pos = t.search(needle, '1.0', stopindex=tk.END, exact=True)
            if not pos and len(needle) > 10:
                pos = t.search(needle[:min(30, len(needle))], '1.0', stopindex=tk.END)
            if pos:
                row = pos.split('.')[0]
                line_start = row + '.0'
                line_end   = row + '.end'
                t.tag_add('exec_line', line_start, line_end)
                t.tag_config('exec_line', background='#1a3a00', foreground='#ccff66')
                end_pos = pos + '+' + str(len(needle)) + 'c'
                t.tag_add('exec_hi', pos, end_pos)
                t.tag_config('exec_hi', background='#4a7a00', foreground='#ffffff')
                t.see(pos)
                # Subir editor al frente para edición inmediata
                self.root.lift()
                self.root.focus_force()
                t.focus_set()
        except Exception as e:
            pass

    def clear_condact_highlight(self):
        """Elimina todos los highlights de debug en los condacts."""
        try:
            for tw in self._condact_w.values():
                tw.tag_remove('exec_hi',   '1.0', tk.END)
                tw.tag_remove('exec_line', '1.0', tk.END)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # FUENTES
    # ═══════════════════════════════════════════════════════════════════════════

    _BASE_SIZES = {
        'Courier':   10,
        'Helvetica': 9,
    }
    _MIN_SIZE = 7
    _MAX_SIZE = 22

    def _font_change(self, delta):
        for f in (self.fnt_code, self.fnt_ui, self.fnt_bold,
                  self.fnt_sm, self.fnt_map, self.fnt_mapid):
            cur = f.cget('size')
            nw  = max(self._MIN_SIZE, min(self._MAX_SIZE, cur + delta))
            f.config(size=nw)
        self._redraw()

    def _font_reset(self):
        for f, sz in ((self.fnt_code,10),(self.fnt_ui,9),(self.fnt_bold,9),
                      (self.fnt_sm,8),(self.fnt_map,9),(self.fnt_mapid,8)):
            f.config(size=sz)
        self._redraw()


    def _save_as(self):
        path = filedialog.asksaveasfilename(
            title='Guardar como',
            defaultextension='.yaml',
            filetypes=[('YAML','*.yaml'),('JSON','*.json')])
        if path:
            path = self._crea_estructura_juego(path)
            self.filepath = path
            self._write(path)

    def _crea_estructura_juego(self, path):
        """Juego nuevo: crea <carpeta>/<nombre>/ con la estructura estandar
        (img/Original, img/Spectrum, music, temp, dist) y devuelve la ruta del
        .yaml dentro de esa carpeta. Si el .yaml ya esta en una carpeta con su
        mismo nombre, la usa tal cual (no anida dos veces)."""
        d = os.path.dirname(os.path.abspath(path))
        name = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1] or '.yaml'
        if os.path.basename(d) != name:           # crear carpeta con el nombre
            root = os.path.join(d, name)
            path = os.path.join(root, name + ext)
        else:
            root = d
        try:
            # dist es UNA sola carpeta (todos los .tap/.dsk/.zip juntos, con el
            # nombre {juego}_{plataforma}_{idioma}); temp sí va por compilación.
            subs = [('img', 'Original'), ('img', 'Spectrum'), ('music',), ('dist',)]
            for tgt in ('48', '128', 'Next'):       # un subnivel por compilacion
                subs += [('temp', tgt)]
            for sub in subs:
                os.makedirs(os.path.join(root, *sub), exist_ok=True)
        except Exception as e:
            messagebox.showwarning('Estructura de carpetas',
                                   'No pude crear todas las carpetas: %s' % e)
        return path

    def _write(self, path):
        try:
            game = copy.deepcopy(self.game)
            game.pop('_vocab_lookup', None)
            # Persistir el layout del mapa (posiciones de los nodos)
            game['_editor'] = {
                'positions': {lid: list(p) for lid, p in self.positions.items()
                              if lid in self.game.get('locations', {})}
            }
            with open(path, 'w', encoding='utf-8') as f:
                if path.lower().endswith('.json'):
                    json.dump(game, f, ensure_ascii=False, indent=2)
                else:
                    yaml.dump(game, f, allow_unicode=True,
                              default_flow_style=False, sort_keys=False)
            self.dirty = False
            self.root.title('Scriba ' + SCRIBA_VERSION + ' - ' + os.path.basename(path))
            self.sv_status.set('Guardado: ' + path)
            self._run_validation()
        except Exception as e:
            messagebox.showerror('Error al guardar', str(e))

    # ── Compilación automática a .TAP ──────────────────────────────────────
    _BUILD_DEFAULTS = {
        'auto_tap': True,
        # Auto-contenido: usa el zxbc.exe y el python embebidos en <Scriba>/zxbasic/
        # (no depende del PATH ni de un Python del sistema, y funciona en cualquier PC).
        # {zxdir} = carpeta zxbasic empaquetada con Scriba (ruta absoluta). Antes
        # se usaba .\zxbasic (relativo), pero ahora el .bas se compila en
        # <juego>/temp, asi que la ruta a zxbc debe ser absoluta.
        'cmd_48': (r'"{zxdir}\zxbc.exe" --org 24576 --heap-size 4096 --array-base=0 '
                   r'--string-base=0 -O2 -M memory.txt "{bas}" && '
                   r'"{zxdir}\python\python.exe" empaqueta48.py "{base}.bin" "{tap}" 24576'),
        'cmd_128_compile': (r'"{zxdir}\zxbc.exe" --org 24576 --heap-size 4096 '
                            r'--array-base=0 --string-base=0 -O2 -M memory.txt "{bas}"'),
        'cmd_128_pack': r'"{zxdir}\python\python.exe" empaqueta128.py "{bin}" "{texto}" "{tap}" 24576',
        # ZX Spectrum Next (SELF-CONTAINED, sin NextBuild ni NextLib):
        #   1) se compila el .bas con zxbc PELADO a un binario crudo en org
        #      $8000 (--arch zxnext).
        #   2) empaqueta_nex.py (junto al editor) construye el .nex propio:
        #      motor en banco 2, sysvars.bin en banco 10, y cada imagen
        #      (.nxi de data/) en su banco 16K segun el manifiesto "<bas>.banks".
        # {nb} = carpeta donde estan zxbc y Tools\sysvars.bin (vale la de
        # NextBuild, que ya trae un zxbc bundle, o cualquier zxbasic).
        'auto_nex': True,
        'nextbuild_dir': '.',
        'cmd_next_compile': (r'"{nb}\zxbasic\python\python.exe" '
                             r'"{nb}\zxbasic\zxbc.py" --arch zxnext -O2 '
                             r'--org 32768 --heap-size 4096 --array-base=0 '
                             r'--string-base=0 -o "{bin}" "{bas}"'),
        'sysvars': r'{nb}\Tools\sysvars.bin',
    }

    def _build_cfg_path(self):
        # Congelado (PyInstaller): junto al .exe; si no, junto a editor.py
        base = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                else os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'scriba_build.json')

    def _build_cfg(self):
        cfg = dict(self._BUILD_DEFAULTS)
        try:
            with open(self._build_cfg_path(), encoding='utf-8') as f:
                cfg.update(json.load(f))
        except Exception:
            pass
        return cfg

    def _save_build_cfg(self, cfg):
        try:
            with open(self._build_cfg_path(), 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.sv_status.set('Configuración de compilación guardada')
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def _build_config_dialog(self):
        cfg = self._build_cfg()
        win = tk.Toplevel(self.root)
        win.title('Configuración de compilación (TAP)')
        win.transient(self.root)
        win.grab_set()
        auto = tk.BooleanVar(value=cfg.get('auto_tap', True))
        ttk.Checkbutton(win, text='Generar el .TAP automáticamente al exportar',
                        variable=auto).grid(row=0, column=0, columnspan=2,
                                            sticky=tk.W, padx=10, pady=(10, 6))
        rows = [('48K — zxbc:', 'cmd_48'),
                ('128K — zxbc (compilar):', 'cmd_128_compile'),
                ('128K — empaquetar:', 'cmd_128_pack')]
        entries = {}
        for i, (lab, key) in enumerate(rows, start=1):
            ttk.Label(win, text=lab).grid(row=i, column=0, sticky=tk.W,
                                          padx=10, pady=3)
            e = tk.Entry(win, width=74, font=self.fnt_ui)
            e.insert(0, cfg.get(key, ''))
            e.grid(row=i, column=1, sticky=tk.EW, padx=10, pady=3)
            entries[key] = e
        # Next: carpeta donde esta zxbasic (con zxbc). Por defecto "." (directorio
        # actual); ademas siempre se prueba el zxbasic empaquetado con Scriba.
        ttk.Label(win, text='Next — carpeta zxbasic:').grid(
            row=4, column=0, sticky=tk.W, padx=10, pady=3)
        nbf = ttk.Frame(win)
        nbf.grid(row=4, column=1, sticky=tk.EW, padx=10, pady=3)
        nb_entry = tk.Entry(nbf, font=self.fnt_ui)
        nb_entry.insert(0, cfg.get('nextbuild_dir', '.'))
        nb_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _examinar_nb():
            from tkinter import filedialog
            d = filedialog.askdirectory(
                title='Carpeta que contiene zxbasic/ con zxbc',
                parent=win)
            if d:
                nb_entry.delete(0, tk.END)
                nb_entry.insert(0, d)
        ttk.Button(nbf, text='Examinar…', command=_examinar_nb).pack(
            side=tk.LEFT, padx=(4, 0))
        ttk.Label(win, foreground='#667788', justify=tk.LEFT,
                  text='Variables: {bas} {bin} {texto} {tap} {base}   (rutas '
                       'relativas a la carpeta del .bas). El 48K usa el primer '
                       'comando; el 128K sus dos.\nNext (.tap) usa por defecto el '
                       'zxbc incluido en Scriba (carpeta zxbasic/). Si no está, '
                       'indica arriba una carpeta que contenga zxbasic/ con zxbc '
                       '(zxbc.exe, o zxbc.py + python/), o la carpeta zxbasic '
                       'directamente.'
                  ).grid(row=5, column=0, columnspan=2, sticky=tk.W,
                         padx=10, pady=(2, 8))
        bf = ttk.Frame(win)
        bf.grid(row=6, column=0, columnspan=2, pady=(0, 10))

        def guardar():
            nc = dict(cfg)                 # preserva claves no editadas (auto_nex…)
            nc['auto_tap'] = auto.get()
            for key, e in entries.items():
                nc[key] = e.get().strip()
            nc['nextbuild_dir'] = nb_entry.get().strip()
            self._save_build_cfg(nc)
            win.destroy()

        def restaurar():
            for k, e in entries.items():
                e.delete(0, tk.END)
                e.insert(0, self._BUILD_DEFAULTS[k])

        ttk.Button(bf, text='Guardar', command=guardar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text='Restaurar valores',
                   command=restaurar).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text='Cancelar', command=win.destroy).pack(side=tk.LEFT, padx=4)
        win.columnconfigure(1, weight=1)

    def _game_root(self):
        """Carpeta raiz del juego = carpeta del .yaml abierto (o None)."""
        return (os.path.dirname(os.path.abspath(self.filepath))
                if self.filepath else None)

    @staticmethod
    def _raiz_desde(d):
        """Raiz del juego a partir de la carpeta del .bas. El .bas vive en
        <raiz>/temp/<target> (target = 48/128/Next); tambien se admite <raiz>/temp
        (sin subnivel) y el layout antiguo (todo junto al .yaml)."""
        if os.path.basename(os.path.dirname(d)).lower() == 'temp':  # temp/<target>
            return os.path.dirname(os.path.dirname(d))
        if os.path.basename(d).lower() == 'temp':                   # temp
            return os.path.dirname(d)
        return d                                                    # layout antiguo

    def _dirs_salida(self, d):
        """A partir de la carpeta del .bas (d) devuelve (raiz, dist_dir). Todos los
        ficheros de distribución van juntos a <raiz>/dist (sin subcarpeta por
        plataforma); el nombre lleva la plataforma (ver _dist_name)."""
        if os.path.basename(os.path.dirname(d)).lower() == 'temp':  # temp/<target>
            raiz = os.path.dirname(os.path.dirname(d))
            return raiz, os.path.join(raiz, 'dist')
        if os.path.basename(d).lower() == 'temp':                   # temp
            raiz = os.path.dirname(d)
            return raiz, os.path.join(raiz, 'dist')
        return d, d                                                 # layout antiguo

    def _dist_name(self, base, plataforma, ext):
        """Nombre de distribución: {juego}_{plataforma}_{idioma}.{ext}.
        'base' es el nombre del .bas/.dsk (p.ej. 'apolo11_en'); se le quita el
        sufijo de idioma si lo lleva y se usa metadata['language'] (es/en/pt)."""
        lng = str((self.game.get('metadata') or {}).get('language') or 'es').strip().lower()
        lang = ('pt' if lng.startswith(('pt', 'por'))
                else 'en' if lng.startswith('en') else 'es')
        juego = base
        for suf in ('_es', '_en', '_pt', '_pt-pt', '_por'):
            if juego.lower().endswith(suf):
                juego = juego[:-len(suf)]
                break
        return '%s_%s_%s.%s' % (juego, plataforma, lang, ext)

    def _dir_juego(self, sub):
        """Subcarpeta <raiz>/<sub> del juego, creandola si falta (o None)."""
        r = self._game_root()
        if not r:
            return None
        d = os.path.join(r, sub)
        os.makedirs(d, exist_ok=True)
        return d

    def _bas_temp_path(self, target):
        """Ruta del .bas en <raiz>/temp/<target>/<nombre>.bas (crea la carpeta).
        target: '48', '128' o 'Next'. None si el juego no esta guardado todavia."""
        if not self.filepath:
            return None
        temp = self._dir_juego(os.path.join('temp', target))
        name = os.path.splitext(os.path.basename(self.filepath))[0]
        return os.path.join(temp, name + '.bas')

    def _zxbasic_dir(self, cfg):
        """Carpeta zxbasic ABSOLUTA. Como el .bas se compila en <juego>/temp,
        la ruta a zxbc NO puede ser relativa. Busca, en orden: junto al editor/
        .exe, en su carpeta padre (p.ej. .exe en dist\\ y zxbasic al lado de
        Scriba), y la carpeta configurada (nextbuild_dir, ignorando '.')."""
        here = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                else os.path.dirname(os.path.abspath(__file__)))
        cands = [os.path.join(here, 'zxbasic'),
                 os.path.join(os.path.dirname(here), 'zxbasic')]
        nb = (cfg.get('nextbuild_dir', '') or '').strip()
        if nb and nb not in ('.', './', '.\\'):
            cands += [os.path.join(nb, 'zxbasic'), nb]
        for c in cands:
            if os.path.isdir(c):
                return os.path.abspath(c)
        return os.path.abspath(cands[0])

    @staticmethod
    def _trunc_psg(stream, maxb):
        """Recorta un stream PSG a <=maxb en un limite de frame (0xFF) y lo cierra
        con 0xFD (bucle)."""
        cut = min(maxb, len(stream))
        while cut > 0 and stream[cut] != 0xFF:
            cut -= 1
        if cut <= 0:
            return b'\xFD'
        return stream[:cut] + b'\xFD'

    def _ajusta_musica_ram(self, bas_path, cfg, org=24576, heap=4096, margen=512):
        """Recorta <base>_musica.bin (incbin de la musica del titulo) a la RAM
        principal que quede LIBRE tras el motor, para que un MIDI largo no desborde
        &FFFF y sin gastar bancos. Compila una vez con un stub para medir el codigo,
        calcula el hueco (65536 - org - codigo - heap - margen) y trunca el PSG a un
        limite de frame. Devuelve (orig, recortado, hueco) o None si no hay musica."""
        import subprocess
        d = os.path.dirname(os.path.abspath(bas_path))
        base = os.path.splitext(os.path.basename(bas_path))[0]
        mus = os.path.join(d, 'musica.bin')         # nombre fijo (= incbin del .bas)
        if not os.path.isfile(mus):
            return None
        full = open(mus, 'rb').read()
        zxbc = self._zxbc_base(cfg)
        if not zxbc:                                    # sin compilador: corte seguro
            self._trunc_write(mus, full, 6144)
            return (len(full), min(len(full), 6145), 6144)
        stub = b'\xFF\xFD'
        probe = os.path.join(d, base + '_probe.bin')
        try:
            with open(mus, 'wb') as f:
                f.write(stub)
            cmd = zxbc + ['--org', str(org), '--heap-size', str(heap),
                          '--array-base=0', '--string-base=0', '-O2',
                          '-o', base + '_probe.bin', base + '.bas']
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True,
                               timeout=300)
            if r.returncode != 0 or not os.path.isfile(probe):
                self._trunc_write(mus, full, 6144)      # no se pudo medir: corte seguro
                return (len(full), min(len(full), 6145), 6144)
            codigo = os.path.getsize(probe) - len(stub)
            try:
                os.remove(probe)
            except OSError:
                pass
            hueco = 65536 - org - codigo - heap - margen
            if hueco < 64:
                with open(mus, 'wb') as f:
                    f.write(b'\xFD')                    # sin sitio: silencio
                return (len(full), 1, 0)
            self._trunc_write(mus, full, hueco)
            recb = min(len(full), hueco) + 1
            return (len(full), recb, hueco)
        except Exception:
            self._trunc_write(mus, full, 6144)
            return (len(full), min(len(full), 6145), 6144)

    def _trunc_write(self, path, full, maxb):
        with open(path, 'wb') as f:
            f.write(self._trunc_psg(full, maxb))

    def _run_build(self, modo, bas_path, cfg):
        """Ejecuta los comandos de compilación en la carpeta del .bas.
        Devuelve (log, tap_ok, tap_path)."""
        import subprocess
        d = os.path.dirname(os.path.abspath(bas_path))
        base = os.path.splitext(os.path.basename(bas_path))[0]
        # el .tap final va a <raiz>/dist/<target> (o junto al .bas en el antiguo)
        raiz, dist = self._dirs_salida(d)
        os.makedirs(dist, exist_ok=True)
        plat = '128kb' if modo == '128k' else '48kb'
        tap_path = os.path.join(dist, self._dist_name(base, plat, 'tap'))
        tap_rel = os.path.relpath(tap_path, d)
        # carpeta zxbasic ABSOLUTA (el .bas se compila en <juego>/temp).
        zxdir = self._zxbasic_dir(cfg)
        subst = {'bas': base + '.bas', 'bin': base + '.bin',
                 'texto': base + '_texto.bin', 'tap': tap_rel, 'base': base,
                 'zxdir': zxdir}
        cmds = ([cfg.get('cmd_128_compile', ''), cfg.get('cmd_128_pack', '')]
                if modo == '128k' else [cfg.get('cmd_48', '')])
        log, ok = [], True
        for raw in cmds:
            if not raw.strip():
                continue
            # compatibilidad: configs antiguas con .\zxbasic (relativo) -> {zxdir}
            cmd = raw.replace('.\\zxbasic', '{zxdir}').replace('./zxbasic', '{zxdir}')
            for k, v in subst.items():
                cmd = cmd.replace('{' + k + '}', v)
            log.append('$ ' + cmd)
            try:
                if os.name == 'nt':
                    # CMD.EXE no admite rutas UNC (\\servidor\...) como directorio
                    # de trabajo; 'pushd' le asigna una letra de unidad temporal y
                    # se situa alli, asi la compilacion funciona desde un recurso de red.
                    full = 'pushd "%s" && ( %s ) && popd' % (d, cmd)
                    r = subprocess.run(full, shell=True, capture_output=True,
                                       text=True, timeout=180)
                else:
                    r = subprocess.run(cmd, shell=True, cwd=d, capture_output=True,
                                       text=True, timeout=180)
                out = ((r.stdout or '') + (r.stderr or '')).rstrip()
                if out:
                    log.append(out)
                if r.returncode != 0:
                    ok = False
                    log.append('[código de salida %d]' % r.returncode)
                    break
            except Exception as e:
                ok = False
                log.append('[ERROR al ejecutar: %s]' % e)
                break
        return '\n'.join(log), (ok and os.path.isfile(tap_path)), tap_path

    def _mem48_line(self, bas_path, cfg=None):
        """Línea de resumen con la memoria libre del .bin compilado (48K).
        Mide el binario que produjo zxbc y la compara con el techo de RAM
        (65536), descontando org y heap. Devuelve None si no hay .bin."""
        import re as _re
        ORG, HEAP, TOP = 24000, 1792, 65536
        cmd = (cfg or {}).get('cmd_48', '') or ''
        m = _re.search(r'--org[ =](\d+)', cmd)
        if m:
            ORG = int(m.group(1))
        m = _re.search(r'--heap-size[ =](\d+)', cmd)
        if m:
            HEAP = int(m.group(1))
        d = os.path.dirname(os.path.abspath(bas_path))
        base = os.path.splitext(os.path.basename(bas_path))[0]
        binf = os.path.join(d, base + '.bin')
        if not os.path.isfile(binf):
            return None
        sz = os.path.getsize(binf)
        end = ORG + sz
        libre = TOP - end                 # bytes por encima del binario
        tras_heap = libre - HEAP          # lo que queda para pila/datos
        if tras_heap >= 0:
            estado = '✓ cabe'
        else:
            estado = '⚠ NO cabe (faltan %d B)' % (-tras_heap)
        return ('Memoria 48K: binario %d B, carga en %d–%d. Libre hasta '
                '65535: %d B (%.1f KB); con heap de %d B quedan ~%d B para '
                'pila/datos — %s.'
                % (sz, ORG, end - 1, libre, libre / 1024.0, HEAP,
                   tras_heap, estado))

    def _show_build_result(self, informe, build_log, tap_ok, tap_path):
        win = tk.Toplevel(self.root)
        win.title('Compilación a TAP')
        win.transient(self.root)
        hdr = (('TAP generado: ' + os.path.basename(tap_path)) if tap_ok
               else 'No se pudo generar el TAP (revisa los comandos y la salida)')
        ttk.Label(win, text=hdr,
                  foreground=('#2e7d32' if tap_ok else '#c62828'),
                  font=self.fnt_bold).pack(anchor=tk.W, padx=10, pady=(10, 4))
        body = scrolledtext.ScrolledText(win, width=94, height=26,
                                         font=self.fnt_code, wrap=tk.NONE)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.insert('1.0', informe + '\n\n===== COMPILACIÓN =====\n' + build_log)
        body.configure(state=tk.DISABLED)
        bf = ttk.Frame(win)
        bf.pack(pady=(0, 10))
        if tap_ok:
            ttk.Button(bf, text='Abrir carpeta',
                       command=lambda: self._open_folder(
                           os.path.dirname(tap_path))).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text='Cerrar', command=win.destroy).pack(side=tk.LEFT, padx=4)

    def _open_folder(self, d):
        try:
            if sys.platform.startswith('win'):
                os.startfile(d)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', d])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', d])
        except Exception:
            pass

    def _open_manual(self):
        """Abre el manual de referencia (PDF) con el visor del sistema. Busca el
        PDF de la versión actual junto a Scriba (o empaquetado con el .exe)."""
        cands = ['Scriba manual v%s.pdf' % SCRIBA_VERSION, 'Scriba_Manual.pdf',
                 'Scriba manual v1.1.pdf', 'Scriba manual v1.0.pdf',
                 'Scriba_Manual.docx', 'manual.pdf']
        path = None
        for n in cands:
            c = _resource_path(n)
            if os.path.isfile(c) and os.path.getsize(c) > 0:
                path = c
                break
        if not path:
            messagebox.showinfo('Referencia',
                'No encontré el manual junto a Scriba.\nEsperaba "Scriba manual '
                'v%s.pdf" en la carpeta del programa.' % SCRIBA_VERSION)
            return
        try:
            if sys.platform.startswith('win'):
                os.startfile(path)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', path])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            messagebox.showerror('Referencia', 'No se pudo abrir el manual:\n%s' % e)

    def _export_spectrum(self, modo='48k'):
        """Exporta el juego a ZX BASIC (Boriel) para ZX Spectrum 48K/128K."""
        if not self.game.get('locations'):
            messagebox.showinfo('Exportar', 'Abre o crea un juego primero.')
            return
        path = self._bas_temp_path('128' if modo == '128k' else '48')
        if not path:
            messagebox.showinfo('Exportar', 'Guarda el juego (.yaml) primero para '
                                'crear su carpeta. El .bas irá a temp\\<target>\\ y '
                                'el .tap a dist\\ (nombre {juego}_{plataforma}_{idioma}).')
            return
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import spectrum_export
            if not getattr(sys, 'frozen', False):
                importlib.reload(spectrum_export)   # solo en desarrollo
        except Exception as e:
            messagebox.showerror('Error al exportar', str(e))
            return
        game = copy.deepcopy(self.game)
        game.pop('_editor', None)

        # Ventana de progreso (el export corre en un hilo aparte)
        import threading
        win = tk.Toplevel(self.root)
        win.title('Exportando a ZX BASIC ' + ('128K' if modo == '128k' else '48K'))
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', lambda: None)
        sv_msg = tk.StringVar(value='Preparando...')
        ttk.Label(win, textvariable=sv_msg, width=46,
                  anchor=tk.W).pack(padx=14, pady=(12, 4))
        bar = ttk.Progressbar(win, length=340, mode='determinate',
                              maximum=100)
        bar.pack(padx=14, pady=(0, 6))
        sv_pct = tk.StringVar(value='0%')
        ttk.Label(win, textvariable=sv_pct).pack(pady=(0, 10))

        # Centrar sobre la ventana principal
        win.update_idletasks()
        px = self.root.winfo_rootx() + \
            (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        py = self.root.winfo_rooty() + \
            (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f'+{max(0, px)}+{max(0, py)}')

        def cb(pct, msg):
            def _ui():
                try:
                    bar.config(value=pct)
                    sv_msg.set(msg)
                    sv_pct.set(f'{int(pct)}%')
                except tk.TclError:
                    pass
            self.root.after(0, _ui)

        cols = self._zx_cols.get() if hasattr(self, '_zx_cols') else 42

        def trabajo():
            try:
                informe = spectrum_export.export_bas(game, path,
                                                     progreso=cb, modo=modo,
                                                     columnas=cols)
            except Exception as e:
                self.root.after(0, lambda e=e: (
                    win.destroy(),
                    messagebox.showerror('Error al exportar', str(e))))
                return
            adv = self._aviso_caps(game, 'spectrum')
            if adv:
                informe = adv + '\n\n' + informe
            cfg = self._build_cfg()
            build_log = tap_ok = tap_path = None
            if cfg.get('auto_tap'):
                cb(96, 'Ajustando música a la RAM libre…')
                try:
                    self._ajusta_musica_ram(path, cfg)
                except Exception:
                    pass
                cb(97, 'Generando TAP (zxbc / empaqueta)...')
                build_log, tap_ok, tap_path = self._run_build(modo, path, cfg)
            # Resumen de memoria 48K: se mide el binario que produjo zxbc.
            if modo == '48k' and build_log is not None:
                mem = self._mem48_line(path, cfg)
                if mem:
                    informe = informe + '\n' + mem
            def _fin():
                win.destroy()
                if build_log is None:
                    messagebox.showinfo('Exportar ZX Spectrum', informe)
                else:
                    self._show_build_result(informe, build_log, tap_ok, tap_path)
                self.sv_status.set('Exportado a ZX BASIC: ' + path)
            self.root.after(0, _fin)

        threading.Thread(target=trabajo, daemon=True).start()

    def _aviso_caps(self, game, target):
        """Aviso (str) de las características que el juego usa pero el target NO
        soporta (paridad entre intérpretes), o '' si todo está soportado. Se
        antepone al informe de cada exportación para no omitir nada en silencio."""
        try:
            import capabilities
            return capabilities.report(game, target)
        except Exception:
            return ''

    def _export_windows(self):
        """Exporta el juego a un PAQUETE PORTABLE de Windows: copia el reproductor
        ScribaPlayer.exe junto al juego (game.yaml + img/Original) en
        <juego>/dist/Windows/<Título>/ y lo comprime en un .zip. NO compila nada:
        ni quien exporta ni quien juega necesitan instalar nada. ScribaPlayer.exe
        se compila UNA sola vez (build_scribaplayer.bat) y viaja junto a Scriba.exe."""
        if not self.game.get('locations'):
            messagebox.showinfo('Exportar', 'Abre o crea un juego primero.')
            return
        if not self.filepath:
            messagebox.showinfo('Exportar', 'Guarda el juego (.yaml) primero.')
            return
        try:
            self._write(self.filepath)
        except Exception:
            pass

        import shutil
        import json as _json
        import threading
        import zipfile
        import re as _re
        # Localizar el reproductor portable (junto a Scriba.exe, su carpeta padre,
        # o el código fuente / dist).
        here = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                else os.path.dirname(os.path.abspath(__file__)))
        cand = [os.path.join(here, 'ScribaPlayer.exe'),
                os.path.join(os.path.dirname(here), 'ScribaPlayer.exe'),
                os.path.join(here, 'dist', 'ScribaPlayer.exe')]
        player_exe = next((c for c in cand if os.path.isfile(c)), None)
        if not player_exe:
            messagebox.showerror(
                'Exportar para Windows',
                'No encuentro ScribaPlayer.exe (el reproductor portable).\n\n'
                'Se compila UNA sola vez con build_scribaplayer.bat y se deja '
                'junto a Scriba.exe. Después, exportar a Windows no necesita '
                'instalar nada (ni tú ni el jugador).')
            return

        yaml_path = self.filepath
        game_dir = os.path.dirname(os.path.abspath(yaml_path))
        title = (self.game.get('metadata', {}).get('title')
                 or os.path.splitext(os.path.basename(yaml_path))[0])
        safe = _re.sub(r'[^\w .\-]+', '', title).strip() or 'Aventura'
        base = os.path.splitext(os.path.basename(yaml_path))[0]
        zip_name = self._dist_name(base, 'windows', 'zip')   # {juego}_windows_{idioma}.zip
        stem = zip_name[:-4]
        distdir = os.path.join(game_dir, 'dist')             # todo junto en dist/
        outdir = os.path.join(distdir, stem)                 # carpeta ejecutable portable
        zip_path = os.path.join(distdir, zip_name)

        win = tk.Toplevel(self.root)
        win.title('Exportando para Windows')
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(win, justify=tk.LEFT, width=46, anchor=tk.W,
                  text='Preparando el paquete portable…').pack(padx=16, pady=(14, 8))
        bar = ttk.Progressbar(win, length=320, mode='indeterminate')
        bar.pack(padx=16, pady=(0, 14))
        bar.start(12)
        win.update_idletasks()
        px = self.root.winfo_rootx() + \
            (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        py_ = self.root.winfo_rooty() + \
            (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f'+{max(0, px)}+{max(0, py_)}')

        def trabajo():
            err = None
            try:
                if os.path.isdir(outdir):
                    shutil.rmtree(outdir, ignore_errors=True)
                os.makedirs(outdir, exist_ok=True)
                shutil.copy2(player_exe, os.path.join(outdir, safe + '.exe'))
                shutil.copy2(yaml_path, os.path.join(outdir, 'game.yaml'))
                with open(os.path.join(outdir, 'player_cfg.json'), 'w',
                          encoding='utf-8') as f:
                    _json.dump({'game': 'game.yaml', 'title': title}, f,
                               ensure_ascii=False)
                orig = os.path.join(game_dir, 'img', 'Original')
                if os.path.isdir(orig):
                    dst = os.path.join(outdir, 'img', 'Original')
                    os.makedirs(dst, exist_ok=True)
                    for fn in os.listdir(orig):
                        if fn.lower().endswith(('.png', '.jpg', '.jpeg',
                                                '.gif', '.bmp')):
                            shutil.copy2(os.path.join(orig, fn),
                                         os.path.join(dst, fn))
                if os.path.isfile(zip_path):
                    os.remove(zip_path)
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
                    for root, _d, files in os.walk(outdir):
                        for fn in files:
                            fp = os.path.join(root, fn)
                            arc = os.path.join(safe, os.path.relpath(fp, outdir))
                            z.write(fp, arc)
            except Exception as e:
                err = str(e)

            def _fin():
                try:
                    bar.stop()
                except Exception:
                    pass
                win.destroy()
                if err:
                    self.sv_status.set('Error al exportar a Windows')
                    messagebox.showerror(
                        'Exportar para Windows',
                        'No se pudo crear el paquete portable.\n\n' + err)
                else:
                    self.sv_status.set('Exportado a Windows: ' + outdir)
                    if messagebox.askyesno(
                            'Exportar para Windows',
                            'Paquete portable creado (no necesita instalar nada):\n\n'
                            'Carpeta: %s\nZIP para compartir: %s\n\n'
                            'El jugador descomprime y ejecuta %s.exe.\n\n'
                            '¿Abrir la carpeta?' % (outdir, zip_path, safe)):
                        self._open_folder(distdir)
            self.root.after(0, _fin)

        threading.Thread(target=trabajo, daemon=True).start()

    def _export_cpc(self, modo=2, con_imagenes=False):
        """Exporta el juego a Amstrad CPC (.dsk, Locomotive BASIC).
        modo: 1 (40 col) o 2 (80 col). con_imagenes: pantalla partida B/N (Modo 2)."""
        if not self.game.get('locations'):
            messagebox.showinfo('Exportar', 'Abre o crea un juego primero.')
            return
        path = filedialog.asksaveasfilename(
            title='Exportar a Amstrad CPC (.dsk)',
            defaultextension='.dsk',
            filetypes=[('Imagen de disco CPC', '*.dsk'), ('Todos', '*.*')])
        if not path:
            return
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import cpc_export, png2cpc, empaqueta_cpc
            if not getattr(sys, 'frozen', False):
                importlib.reload(cpc_export)
                importlib.reload(png2cpc)
                importlib.reload(empaqueta_cpc)
        except Exception as e:
            messagebox.showerror('Error al exportar', str(e))
            return
        game = copy.deepcopy(self.game)
        game.pop('_editor', None)

        img_dir = None
        if con_imagenes:
            cands = []
            if self.filepath:
                cands.append(os.path.join(os.path.dirname(self.filepath), 'img'))
            cands.append(os.path.join(here, 'img'))
            img_dir = next((d for d in cands
                            if os.path.isdir(os.path.join(d, 'Original'))
                            or os.path.isdir(os.path.join(d, 'AmstradCPC'))), None)
            if not img_dir:
                if not messagebox.askyesno(
                        'Exportar Amstrad CPC',
                        'No encuentro img/Original ni img/AmstradCPC.\n'
                        '¿Exportar solo texto (Modo 2)?'):
                    return
                con_imagenes = False

        # Ventana de espera (la conversión de imágenes tarda unos segundos)
        import threading
        win = tk.Toplevel(self.root)
        win.title('Exportando a Amstrad CPC')
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(win, text='Generando .dsk para Amstrad CPC…',
                  width=42, anchor=tk.W).pack(padx=16, pady=(14, 6))
        bar = ttk.Progressbar(win, length=320, mode='indeterminate')
        bar.pack(padx=16, pady=(0, 14))
        bar.start(12)
        win.update_idletasks()
        px = self.root.winfo_rootx() + \
            (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        py = self.root.winfo_rooty() + \
            (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f'+{max(0, px)}+{max(0, py)}')

        def trabajo():
            try:
                if con_imagenes:
                    dsk, avisos, locs = empaqueta_cpc.export_dsk_img(
                        game, path, img_dir, modo=2)
                    msg = ('Exportado a Amstrad CPC (Modo 2, pantalla partida B/N).\n'
                           f'{len(dsk)} bytes — {len(locs)} localizaciones con imagen.\n\n'
                           'Monta el .dsk en un emulador y arranca con  RUN"DISC"')
                else:
                    dsk, avisos = empaqueta_cpc.export_dsk(game, path, modo=modo)
                    msg = (f'Exportado a Amstrad CPC (Modo {modo}, solo texto).\n'
                           f'{len(dsk)} bytes.\n\n'
                           'Monta el .dsk en un emulador y arranca con  RUN"DISC"')
                if avisos:
                    msg += f'\n\n({len(avisos)} avisos de conversion)'
            except Exception as e:
                self.root.after(0, lambda e=e: (
                    win.destroy(),
                    messagebox.showerror('Error al exportar CPC', str(e))))
                return

            def _fin():
                win.destroy()
                messagebox.showinfo('Exportar Amstrad CPC', msg)
                self.sv_status.set('Exportado a Amstrad CPC: ' + path)
            self.root.after(0, _fin)

        threading.Thread(target=trabajo, daemon=True).start()

    def _export_cpc_nativo(self, modo=2):
        """Exporta al MOTOR NATIVO Z80 (modelo PAW/DAAD) en un .dsk arrancable.
        modo: 1 (40 col, Modo 1) o 2 (80 col, Modo 2). Mucho mas pequeno y rapido
        que el export BASIC, y no da 'Memory full'."""
        if not self.game.get('locations'):
            messagebox.showinfo('Exportar', 'Abre o crea un juego primero.')
            return
        if not self.filepath:
            messagebox.showinfo('Exportar', 'Guarda el juego (.yaml) primero.')
            return
        # Automatico, como las demas plataformas: <raiz>/dist/{juego}_cpc_{idioma}.dsk
        distdir = self._dir_juego('dist')
        if not distdir:
            messagebox.showinfo('Exportar', 'Guarda el juego (.yaml) primero.')
            return
        name = os.path.splitext(os.path.basename(self.filepath))[0]
        path = os.path.join(distdir, self._dist_name(name, 'cpc', 'dsk'))
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import cpc_nativo
            if not getattr(sys, 'frozen', False):
                for m in ('z80asm', 'txtpack', 'game_engine', 'nativecc',
                          'dsk', 'cpc_nativo'):
                    try:
                        importlib.reload(importlib.import_module(m))
                    except Exception:
                        pass
                import cpc_nativo
        except Exception as e:
            messagebox.showerror('Error al exportar', str(e))
            return
        game = copy.deepcopy(self.game)
        game.pop('_editor', None)

        cands = []
        if self.filepath:
            cands.append(os.path.join(os.path.dirname(self.filepath), 'img'))
        cands.append(os.path.join(here, 'img'))
        img_dir = next((d for d in cands
                        if os.path.isdir(os.path.join(d, 'Original'))
                        or os.path.isdir(os.path.join(d, 'AmstradCPC'))), None)

        import threading
        win = tk.Toplevel(self.root)
        win.title('Exportando a CPC nativo')
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(win, text='Compilando motor nativo Z80…',
                  width=42, anchor=tk.W).pack(padx=16, pady=(14, 6))
        bar = ttk.Progressbar(win, length=320, mode='indeterminate')
        bar.pack(padx=16, pady=(0, 14))
        bar.start(12)
        win.update_idletasks()
        px = self.root.winfo_rootx() + \
            (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        py = self.root.winfo_rooty() + \
            (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f'+{max(0, px)}+{max(0, py)}')

        def trabajo():
            try:
                info = cpc_nativo.export_native(game, path, modo=modo,
                                                img_dir=img_dir)
                cols = '80' if modo == 2 else '40'
                msg = ('Exportado al MOTOR NATIVO Z80 '
                       f'(Modo {modo}, {cols} columnas).\n'
                       f'Motor + base de datos: {info["blob_size"]} bytes '
                       f'(&{info["engine_org"]:04X}–&{info["end_addr"]:04X}).\n'
                       f'{info["nloc"]} localizaciones · {info["nobj"]} objetos · '
                       f'{info["nresp"]} respuestas.\n'
                       + ('Con pantalla de título (TITLE.SCR).\n'
                          if info.get('title')
                          else 'Sin pantalla de título (no encontré img/.../screen.*).\n')
                       + '\nMonta el .dsk en un emulador y arranca con  RUN"DISC"')
                adv = self._aviso_caps(game, 'cpc')
                if adv:
                    msg = adv + '\n\n' + msg
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.root.after(0, lambda e=e: (
                    win.destroy(),
                    messagebox.showerror('Error al exportar CPC nativo', str(e))))
                return

            def _fin():
                win.destroy()
                self.sv_status.set('Exportado a CPC nativo: ' + path)
                if messagebox.askyesno(
                        'Exportar CPC nativo',
                        msg + '\n\nGuardado en:\n%s\n\n¿Abrir la carpeta?' % path):
                    self._open_folder(os.path.dirname(path))
            self.root.after(0, _fin)

        threading.Thread(target=trabajo, daemon=True).start()

    # ── Exportación a ZX Spectrum Next ─────────────────────────────────────
    def _next_convert_images(self, out_path, cb=None):
        """Paso de conversión de imágenes de la exportación a Next.
        Lee los PNG/JPG de  <carpeta_del_bas>/img/Next/  y genera, JUNTO al .bas,
        un par <id>.nxi (256x64, ó screen 256x192) + <id>.nxp (paleta 9-bit) por
        cada uno, con la mejor paleta por imagen. El motor los incrusta en el
        .nex (incbin/bancos). Convención: img/Next/<id_localización>.(png|jpg) +
        screen.(png|jpg) opcional para el menú (256x192)."""
        outdir = os.path.dirname(os.path.abspath(out_path)) or '.'
        raiz = self._raiz_desde(outdir)                          # raiz del juego
        img_dir = os.path.join(raiz, 'img', 'Next')
        if not os.path.isdir(img_dir):
            img_dir = os.path.join(raiz, 'img', 'Original')      # fallback a masters
        data_dir = os.path.join(outdir, 'data')                  # intermedios -> temp/
        if not os.path.isdir(img_dir):
            return ['imágenes Next: no hay carpeta img/Next ni img/Original (sin pantallas)']
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import png2next
            if not getattr(sys, 'frozen', False):
                importlib.reload(png2next)
            os.makedirs(data_dir, exist_ok=True)
        except Exception as e:
            return ['imágenes Next: ERROR al cargar el conversor png2next '
                    '(¿falta Pillow? «pip install pillow»): %s' % e]

        locids = set(self.game.get('locations', {}).keys())
        exts = ('.png', '.jpg', '.jpeg')
        imgs = sorted(f for f in os.listdir(img_dir)
                      if f.lower().endswith(exts))
        lineas, n_ok, n_skip = [], 0, 0
        total = len(imgs) or 1
        for i, fn in enumerate(imgs):
            base = os.path.splitext(fn)[0]
            es_screen = base.lower() in ('screen', 'menu')
            if not (base in locids or es_screen):
                lineas.append('  - %s OMITIDO: no coincide con ninguna '
                              'localización' % fn)
                n_skip += 1
                continue
            if cb:
                cb(5 + 45 * i // total,
                   'Convirtiendo imagen Next: %s (%d/%d)…' % (fn, i + 1, len(imgs)))
            try:
                nxi = os.path.join(data_dir, base + '.nxi')
                nxp = os.path.join(data_dir, base + '.nxp')
                _, _, info = png2next.convert(os.path.join(img_dir, fn),
                                              nxi, nxp, menu=es_screen)
                lineas.append('  - ' + info[0])
                n_ok += 1
            except Exception as e:
                lineas.append('  - %s ERROR: %s' % (fn, e))
        cabecera = ('imágenes Next: %d convertida(s) a data/*.nxi+*.nxp '
                    '(para incrustar en el .nex)' % n_ok)
        if n_skip:
            cabecera += '  (%d omitida[s])' % n_skip
        return [cabecera] + lineas

    def _export_next(self):
        """Exporta el juego para ZX Spectrum Next como .tap:
        convierte img/Next/*.png|jpg a Layer 2 (.nxi/.nxp en data/), genera el
        ZX BASIC (texto comprimido en bancos + imagenes Layer 2 + pantalla de
        titulo + musica), compila con zxbc y empaqueta el .tap (texto en bancos
        bajos $7FFD, imagenes en altos $DFFD). Sin limite de tamano."""
        if not self.game.get('locations'):
            messagebox.showinfo('Exportar', 'Abre o crea un juego primero.')
            return
        path = self._bas_temp_path('Next')
        if not path:
            messagebox.showinfo('Exportar', 'Guarda el juego (.yaml) primero para '
                                'crear su carpeta. El .bas irá a temp\\Next\\ y el '
                                '.tap a dist\\ (nombre {juego}_next_{idioma}).')
            return
        game = copy.deepcopy(self.game)
        game.pop('_editor', None)

        import threading
        win = tk.Toplevel(self.root)
        win.title('Exportando a ZX Spectrum Next')
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', lambda: None)
        sv_msg = tk.StringVar(value='Preparando…')
        ttk.Label(win, textvariable=sv_msg, width=50,
                  anchor=tk.W).pack(padx=14, pady=(12, 4))
        bar = ttk.Progressbar(win, length=360, mode='determinate', maximum=100)
        bar.pack(padx=14, pady=(0, 6))
        sv_pct = tk.StringVar(value='0%')
        ttk.Label(win, textvariable=sv_pct).pack(pady=(0, 10))
        win.update_idletasks()
        px = self.root.winfo_rootx() + \
            (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        py = self.root.winfo_rooty() + \
            (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f'+{max(0, px)}+{max(0, py)}')

        def cb(pct, msg):
            def _ui():
                try:
                    if str(bar.cget('mode')) == 'determinate':
                        bar.config(value=pct)
                        sv_pct.set(f'{int(pct)}%')
                    sv_msg.set(msg)
                except tk.TclError:
                    pass
            self.root.after(0, _ui)

        def pulse(on):
            # barra pulsante para fases largas sin progreso medible (compilacion)
            def _ui():
                try:
                    if on:
                        bar.config(mode='indeterminate')
                        bar.start(12)
                        sv_pct.set('…')
                    else:
                        bar.stop()
                        bar.config(mode='determinate')
                except tk.TclError:
                    pass
            self.root.after(0, _ui)

        cols = self._zx_cols.get() if hasattr(self, '_zx_cols') else 42

        def trabajo():
            informe_partes = []
            # ── Paso 1: conversión de imágenes Layer 2 ──────────────────────
            cb(5, 'Convirtiendo imágenes Layer 2 (img/Next)…')
            try:
                img_lineas = self._next_convert_images(path, cb)
            except Exception as e:
                img_lineas = ['imágenes Next: ERROR (%s)' % e]
            informe_partes.append('\n'.join(img_lineas))

            # ── Paso 2: generar el ZX BASIC para Next ───────────────────────
            cb(55, 'Generando ZX BASIC para Next…')
            bas_ok = False
            try:
                here = os.path.dirname(os.path.abspath(__file__))
                if here not in sys.path:
                    sys.path.insert(0, here)
                import importlib
                import next_export
                if not getattr(sys, 'frozen', False):
                    importlib.reload(next_export)
                informe = next_export.export_bas(game, path, progreso=cb,
                                                 columnas=cols, modo='tap')
                informe_partes.append(informe)
                bas_ok = os.path.isfile(path)
            except ImportError:
                informe_partes.append(
                    'BASIC Next: PENDIENTE — falta el backend next_export.py. '
                    'Las imágenes ya se han convertido; el .bas se generará '
                    'cuando se añada el exportador.')
            except Exception as e:
                informe_partes.append('BASIC Next: ERROR — %s' % e)

            # ── Paso 3: compilar (zxbc) + empaquetar el .tap para Next ──
            cfg = self._build_cfg()
            build_log = nex_ok = nex_path = None
            if bas_ok and cfg.get('auto_nex'):
                cb(92, 'Compilando con zxbc y empaquetando el .tap…')
                pulse(True)
                build_log, nex_ok, nex_path = self._build_nextap(
                    path, cfg, cb)
                pulse(False)

            adv = self._aviso_caps(game, 'next')
            if adv:
                informe_partes.insert(0, adv)
            informe = '\n\n'.join(informe_partes)

            def _fin():
                win.destroy()
                if build_log is None:
                    messagebox.showinfo('Exportar ZX Spectrum Next', informe)
                else:
                    self._show_build_result(informe, build_log, nex_ok, nex_path)
                self.sv_status.set('Exportado a ZX Spectrum Next (.tap): ' + path)
            self.root.after(0, _fin)

        threading.Thread(target=trabajo, daemon=True).start()

    # ─── Traducción: exportar / importar literales ─────────────────────────
    def _export_literales(self):
        """Exporta todos los literales del juego a un CSV (clave;original;
        traduccion) para traducir. Si el CSV ya existe, reaprovecha lo ya
        traducido (memoria de traduccion)."""
        if not self.game.get('locations'):
            messagebox.showinfo('Traducción', 'Abre o crea un juego primero.')
            return
        base = (os.path.splitext(os.path.basename(self.filepath))[0]
                if self.filepath else 'juego')
        path = filedialog.asksaveasfilename(
            title='Exportar literales para traducir',
            defaultextension='.csv', initialfile=base + '_textos.csv',
            filetypes=[('CSV', '*.csv'), ('Todos', '*.*')])
        if not path:
            return
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import traduccion
            if not getattr(sys, 'frozen', False):
                importlib.reload(traduccion)
            game = copy.deepcopy(self.game)
            game.pop('_editor', None)
            previo = path if os.path.isfile(path) else None
            total, vacias = traduccion.exporta_csv(game, path, previo=previo)
            self.sv_status.set('Literales exportados: ' + path)
            msg = ('Exportados %d literales a:\n%s\n\nSin traducir: %d.\n\n'
                   'Rellena la 3ª columna (traduccion) en una hoja de cálculo y '
                   'luego usa "Importar literales traducidos".'
                   % (total, path, vacias))
            if previo:
                msg += ('\n\n(Se reaprovecharon las traducciones previas cuyo '
                        'original no ha cambiado.)')
            messagebox.showinfo('Exportar literales', msg)
        except Exception as e:
            messagebox.showerror('Exportar literales', str(e))

    def _import_literales(self):
        """Importa un CSV de literales traducidos y genera un YAML del juego en
        el idioma destino (sin tocar el original)."""
        if not self.game.get('locations'):
            messagebox.showinfo('Traducción', 'Abre o crea un juego primero.')
            return
        csv_path = filedialog.askopenfilename(
            title='Importar literales traducidos (CSV)',
            filetypes=[('CSV', '*.csv'), ('Todos', '*.*')])
        if not csv_path:
            return
        from tkinter import simpledialog
        idioma = (simpledialog.askstring(
            'Idioma', 'Código de idioma destino (ej. en, fr, de):',
            parent=self.root) or '').strip().lower()
        base = (os.path.splitext(os.path.basename(self.filepath))[0]
                if self.filepath else 'juego')
        suf = ('_' + idioma) if idioma else '_traducido'
        out = filedialog.asksaveasfilename(
            title='Guardar juego traducido (YAML)',
            defaultextension='.yaml', initialfile=base + suf + '.yaml',
            filetypes=[('YAML', '*.yaml'), ('Todos', '*.*')])
        if not out:
            return
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import traduccion
            import yaml
            if not getattr(sys, 'frozen', False):
                importlib.reload(traduccion)
            game = copy.deepcopy(self.game)
            game.pop('_editor', None)
            g, aplicadas, avisos = traduccion.importa_csv(
                game, csv_path, idioma=idioma or None)
            with open(out, 'w', encoding='utf-8') as f:
                yaml.safe_dump(g, f, allow_unicode=True, sort_keys=False)
            self.sv_status.set('Juego traducido: ' + out)
            msg = ('Aplicadas %d traducciones.\nJuego traducido guardado en:\n%s'
                   % (aplicadas, out))
            if avisos:
                msg += ('\n\nAvisos (%d):\n' % len(avisos)
                        + '\n'.join('  - ' + a for a in avisos[:12]))
                if len(avisos) > 12:
                    msg += '\n  …(+%d mas)' % (len(avisos) - 12)
            messagebox.showinfo('Importar literales', msg)
        except Exception as e:
            messagebox.showerror('Importar literales', str(e))

    def _zxbc_base(self, cfg):
        """Comando-base ABSOLUTO para invocar zxbc (Boriel empaquetado con
        Scriba). Usa _zxbasic_dir (junto al editor/.exe, su padre, o la carpeta
        configurada). Devuelve ['.../zxbc.exe'] o ['.../python.exe', '.../zxbc.py']
        o None. Rutas absolutas: el .bas se compila con cwd=<juego>/temp."""
        dd = self._zxbasic_dir(cfg)
        exe = os.path.join(dd, 'zxbc.exe')
        if os.path.isfile(exe):
            return [os.path.abspath(exe)]
        zxpy = os.path.join(dd, 'zxbc.py')
        if os.path.isfile(zxpy):
            py = os.path.join(dd, 'python', 'python.exe')
            if os.path.isfile(py):
                return [os.path.abspath(py), os.path.abspath(zxpy)]
            if not getattr(sys, 'frozen', False):
                return [sys.executable, os.path.abspath(zxpy)]
            return ['python', os.path.abspath(zxpy)]
        return None

    def _build_nextap(self, bas_path, cfg, cb=None):
        """Compila el .bas (modo tap) con zxbc y empaqueta el .tap para Next:
        texto comprimido en bancos bajos ($7FFD) + imagenes Layer 2 en bancos
        altos ($DFFD), que el cargador 128 del .tap pagina con BANKM sincronizado.
        El empaquetado se hace EN PROCESO (sin python externo). El org se calcula
        segun el nº de bancos (para que el cargador BASIC quepa bajo RAMTOP).
        Devuelve (log, ok, salida)."""
        import subprocess
        d = os.path.dirname(os.path.abspath(bas_path))
        base = os.path.splitext(os.path.basename(bas_path))[0]
        bin_name = base + '.bin'
        texto_name = base + '_texto.bin'
        # intermedios (.bin, _texto.bin, .banks, .loading, data/) en temp = d;
        # el .tap final va a <raiz>/dist con nombre {juego}_next_{idioma}.tap.
        raiz, dist = self._dirs_salida(d)
        os.makedirs(dist, exist_ok=True)
        tap_name = self._dist_name(base, 'next', 'tap')
        tap_path = os.path.join(dist, tap_name)
        bin_path = os.path.join(d, bin_name)
        texto_path = os.path.join(d, texto_name)
        man = bas_path + '.banks'
        log = []

        # org adaptativo: PROG + cargador (crece con nº de bancos) + holgura.
        n_img = 0
        if os.path.isfile(man):
            with open(man, encoding='ascii') as f:
                n_img = sum(1 for ln in f if ln.strip())
        n_text = ((os.path.getsize(texto_path) + 16383) // 16384
                  if os.path.isfile(texto_path) else 0)
        n_banks = n_text + n_img
        # Cada banco son ~114 B de cargador (paginar + LOAD + actualizar el %);
        # +1000 de base = linea de "CARGANDO", linea final y holgura de pila. Con
        # esto el cargador BASIC cabe bajo RAMTOP (= org-1) y no da "RAMTOP no good".
        org = 23755 + 120 * n_banks + 1000
        org = max(24576, ((org + 255) // 256) * 256)

        # ── 1) compilar con zxbc (empaquetado con Scriba o, si no, configurado) ──
        zxbc_base = self._zxbc_base(cfg)
        if not zxbc_base:
            log.append('[no se encontro zxbc: incluye el compilador Boriel en '
                       '<Scriba>/zxbasic/ (zxbc.exe, o zxbc.py + python/) o '
                       'configura una carpeta valida en Compilacion → Next].')
            return '\n'.join(log), False, tap_path
        # Heap: 2 KB solo si el juego usa FX (el reproductor + datos van al final del
        # binario y la RAM de Next va muy justa; bajar el heap libera ~2 KB para que
        # quepan). Sin FX se deja 4 KB (más holgura para cadenas).
        try:
            with open(os.path.join(d, base + '.bas'), encoding='latin-1') as _f:
                _usa_fx = 'playfx' in _f.read()
        except OSError:
            _usa_fx = False
        heapsz = '2048' if _usa_fx else '4096'
        if cb:
            cb(93, 'Compilando ZX BASIC (zxbc, org %d, %d bancos, heap %s)…'
               % (org, n_banks, heapsz))
        cmd = zxbc_base + ['--arch', 'zxnext', '-O2', '--org', str(org),
                           '--heap-size', heapsz, '--array-base=0',
                           '--string-base=0', '-M', 'memory_next.txt',
                           '-o', bin_name, base + '.bas']
        log.append('$ ' + ' '.join(cmd))
        try:
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True,
                               timeout=300)
            out = ((r.stdout or '') + (r.stderr or '')).rstrip()
            if out:
                log.append(out)
        except Exception as e:
            log.append('[ERROR al compilar: %s]' % e)
            return '\n'.join(log), False, tap_path
        if not os.path.isfile(bin_path):
            log.append('[la compilacion no genero %s]' % bin_name)
            return '\n'.join(log), False, tap_path

        # ── 2) empaquetar el .tap EN PROCESO (empaqueta_nextap, sin python externo) ──
        if cb:
            cb(96, 'Empaquetando el .tap (texto en bancos + imagenes Layer 2)…')
        ok = False
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import importlib
            import empaqueta_nextap
            if not getattr(sys, 'frozen', False):
                importlib.reload(empaqueta_nextap)
            code = open(bin_path, 'rb').read()
            texto = (open(texto_path, 'rb').read()
                     if os.path.isfile(texto_path) else b'')
            imgs = []
            deferidos = []          # bancos que carga el motor (2ª fase, LD-BYTES)
            if os.path.isfile(man):
                with open(man, encoding='ascii') as f:
                    for line in f:
                        parts = line.rstrip('\n').split('\t')
                        if len(parts) < 2:
                            continue
                        bank, fn = parts[0], parts[1]
                        p = os.path.join(d, 'data', fn)
                        if bank and fn and os.path.isfile(p):
                            imgs.append((int(bank), open(p, 'rb').read()))
                            if len(parts) >= 3 and parts[2].strip() == 'D':
                                deferidos.append(int(bank))
            # texto de carga (metadato 'loading', traducible); lo escribe next_export
            cargando = 'CARGANDO...'
            load_txt = bas_path + '.loading'
            if os.path.isfile(load_txt):
                try:
                    with open(load_txt, encoding='ascii', errors='replace') as f:
                        t = f.read().strip()
                    if t:
                        cargando = t
                except Exception:
                    pass
            try:
                _bd = int(self.game.get('metadata', {}).get('border', 0) or 0) & 7
            except (TypeError, ValueError):
                _bd = 0
            tap = empaqueta_nextap.construye_tap(code, texto, imgs, org=org,
                                                 deferidos=deferidos,
                                                 cargando=cargando, border=_bd)
            with open(tap_path, 'wb') as f:
                f.write(tap)
            log.append('TAP: %s (%d bytes) | %d texto | %d img (%d en 2 fases)'
                       % (tap_name, len(tap), n_text, len(imgs), len(deferidos)))
            ok = True
        except Exception as e:
            log.append('[ERROR al empaquetar: %s]' % e)
        ok = ok and os.path.isfile(tap_path)
        if cb and ok:
            cb(99, 'TAP creado.')
        return '\n'.join(log), ok, tap_path

    def _build_nex_selfcontained(self, bas_path, cfg, cb=None):
        """Cadena PROPIA (sin NextBuild ni NextLib): compila el .bas con zxbc
        PELADO a un binario crudo (org $8000) y luego empaqueta_nex.py construye
        el .nex (motor en banco 2, sysvars.bin en banco 10, y cada imagen de
        data/ en su banco 16K segun el manifiesto <bas>.banks).
        Devuelve (log, ok, salida)."""
        import subprocess
        d = os.path.dirname(os.path.abspath(bas_path))
        base = os.path.splitext(os.path.basename(bas_path))[0]
        nb = cfg.get('nextbuild_dir', '').strip()
        bin_name = base + '.bin'
        nex_name = base + '.nex'
        nex_path = os.path.join(d, nex_name)
        log = []

        # 1) compilar .bas -> .bin (cwd = carpeta del .bas: incbin/includes
        #    se resuelven con ruta relativa: data/<id>.nxp, print*_es.bas).
        cmd = cfg.get('cmd_next_compile', '')
        for k, v in {'nb': nb, 'bas': base + '.bas', 'bin': bin_name,
                     'base': base}.items():
            cmd = cmd.replace('{' + k + '}', v)
        log.append('$ ' + cmd)
        if cb:
            cb(93, 'Compilando ZX BASIC (zxbc -O2)…')
        try:
            r = subprocess.run(cmd, shell=True, cwd=d, capture_output=True,
                               text=True, timeout=300)
            out = ((r.stdout or '') + (r.stderr or '')).rstrip()
            if out:
                log.append(out)
        except Exception as e:
            log.append('[ERROR al compilar: %s]' % e)
            return '\n'.join(log), False, nex_path
        if r.returncode != 0 or not os.path.isfile(os.path.join(d, bin_name)):
            log.append('[la compilacion no genero %s]' % bin_name)
            return '\n'.join(log), False, nex_path

        # 2) empaquetar el .nex propio con empaqueta_nex.py + manifiesto.
        if cb:
            cb(96, 'Empaquetando el .nex (motor + imagenes + sysvars)…')
        here = os.path.dirname(os.path.abspath(__file__))
        emp = os.path.join(here, 'empaqueta_nex.py')
        # sysvars.bin: se prefiere una copia PROPIA junto a Scriba (independiente
        # de NextBuild). Si no existe, se usa la ruta configurada ({nb}\Tools\...).
        sysv = cfg.get('sysvars', '').replace('{nb}', nb)
        bundled = os.path.join(here, 'sysvars.bin')
        if os.path.isfile(bundled):
            sysv = bundled
        # interprete para el empaquetador: el bundle de NextBuild si existe;
        # si no, el del editor (o 'python').
        pyexe = os.path.join(nb, 'zxbasic', 'python', 'python.exe')
        if not os.path.isfile(pyexe):
            pyexe = (sys.executable if not getattr(sys, 'frozen', False)
                     else 'python')
        cmd2 = [pyexe, emp, bin_name, nex_name]
        if sysv and os.path.isfile(sysv):
            cmd2 += ['--sysvars', sysv]
        else:
            log.append('AVISO: no se encontro sysvars.bin (%s); el .nex puede '
                       'no arrancar. Revisa la ruta en la configuracion.' % sysv)
        man = bas_path + '.banks'           # manifiesto que escribe next_export
        if os.path.isfile(man):
            with open(man, encoding='ascii') as f:
                for line in f:
                    bank, _, fn = line.strip().partition('\t')
                    if bank and fn:
                        cmd2 += ['--img', '%s:%s'
                                 % (bank, os.path.join('data', fn))]
        log.append('$ ' + ' '.join(cmd2))
        ok = False
        try:
            r2 = subprocess.run(cmd2, cwd=d, capture_output=True, text=True,
                                timeout=120)
            out = ((r2.stdout or '') + (r2.stderr or '')).rstrip()
            if out:
                log.append(out)
            ok = (r2.returncode == 0)
        except Exception as e:
            log.append('[ERROR al empaquetar: %s]' % e)
        ok = ok and os.path.isfile(nex_path)
        if cb and ok:
            cb(99, 'NEX creado.')
        return '\n'.join(log), ok, nex_path

    def _quit(self):
        if self.dirty and not messagebox.askyesno(
                'Sin guardar', 'Hay cambios sin guardar. Salir de todas formas?'):
            return
        self.root.quit()


# =========================================================================
# VENTANA DEL INTERPRETE
# =========================================================================

class InterpreterWindow:

    def __init__(self, editor, parent_frame):
        import threading
        self.editor      = editor
        self.frame       = parent_frame   # Frame embebido en el editor
        self.history     = []
        self.history_pos = -1
        self._snap       = None   # snapshot del estado del juego en memoria
        # Debug
        self._debug_mode  = False
        self._step_event  = threading.Event()
        self._cont_mode   = False
        self._cur_section = ''
        self._build_ui()
        self._init_interp()

    def _build_ui(self):
        # ── Barra principal ──────────────────────────────────────────────────
        tb = tk.Frame(self.frame, bg='#0d1b2a', pady=3)
        tb.pack(fill=tk.X)
        def tbtn(text, cmd, bg='#1e3a5a', **kw):
            b = tk.Button(tb, text=text, command=cmd, bg=bg, fg='#e0e0e0',
                          relief=tk.FLAT, padx=8, font=('Helvetica', 9),
                          cursor='hand2', **kw)
            b.pack(side=tk.LEFT, padx=2)
            return b
        tbtn('Reiniciar', self._restart)
        tbtn('✎ Editar', self._edit_history, bg='#2a2a4a')
        tbtn('💾 Save', self._save_history, bg='#1e3a2a')
        tbtn('📂 Load', self._replay_script, bg='#2a2a4a')
        tbtn('📸 Snapshot', self._snapshot, bg='#3a3a1a')
        self.btn_recall = tbtn('↩ Recall Snap', self._recall_snap, bg='#3a3a1a')
        self.btn_recall.config(state=tk.DISABLED)   # solo activo si hay snapshot
        tbtn('✕', self.close, bg='#3a1a1a')
        self.lbl_loc = tk.Label(tb, text='Loc: --', bg='#0d1b2a', fg='#7090cc',
                                 font=self.editor.fnt_sm)
        self.lbl_loc.pack(side=tk.LEFT, padx=10)
        self.lbl_score = tk.Label(tb, text='Pts: 0  T: 0', bg='#0d1b2a',
                                   fg='#81c784', font=self.editor.fnt_sm)
        self.lbl_score.pack(side=tk.LEFT, padx=4)
        self.lbl_condact = tk.Label(tb, text='', bg='#0d1b2a', fg='#ffe066',
                                     font=self.editor.fnt_sm)
        self.lbl_condact.pack(side=tk.RIGHT, padx=8)

        # ── Barra de debug ───────────────────────────────────────────────────
        db = tk.Frame(self.frame, bg='#1a1a0a', pady=2)
        db.pack(fill=tk.X)
        self.btn_debug = tk.Button(db, text='  Debug: OFF  ',
                                    command=self._toggle_debug,
                                    bg='#2a2a0a', fg='#888866',
                                    relief=tk.FLAT, padx=8,
                                    font=self.editor.fnt_sm, cursor='hand2')
        self.btn_debug.pack(side=tk.LEFT, padx=2)

        self.btn_step = tk.Button(db, text='Step ▶',
                                   command=self._step,
                                   bg='#1a3a1a', fg='#66cc66',
                                   relief=tk.FLAT, padx=8,
                                   font=self.editor.fnt_sm, cursor='hand2',
                                   state=tk.DISABLED)
        self.btn_step.pack(side=tk.LEFT, padx=2)

        self.btn_cont = tk.Button(db, text='Continuar ▶▶',
                                   command=self._continue_exec,
                                   bg='#1a2a3a', fg='#6699cc',
                                   relief=tk.FLAT, padx=8,
                                   font=self.editor.fnt_sm, cursor='hand2',
                                   state=tk.DISABLED)
        self.btn_cont.pack(side=tk.LEFT, padx=2)

        self.lbl_dbg_line = tk.Label(db, text='', bg='#1a1a0a', fg='#ffe066',
                                      font=self.editor.fnt_sm, anchor=tk.W)
        self.lbl_dbg_line.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # ── Output (se crea ahora; se empaqueta DESPUÉS de la entrada) ──────
        self.out = scrolledtext.ScrolledText(
            self.frame, state=tk.DISABLED, bg='#0d1b2a', fg='#c8d8e8',
            font=self.editor.fnt_code, wrap=tk.WORD, insertbackground='white')

        # ── Input: al fondo y empaquetado ANTES que el output, para que su
        #    altura quede SIEMPRE reservada. Si no, el expand=True del output
        #    lo aplastaba y la línea de comandos no se veía hasta hacer resize.
        inf = tk.Frame(self.frame, bg='#0d1b2a')
        inf.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))
        tk.Label(inf, text='> ', bg='#0d1b2a', fg='#4fc3f7',
                 font=('Courier', 12, 'bold')).pack(side=tk.LEFT)
        self.ivar  = tk.StringVar()
        self.entry = tk.Entry(inf, textvariable=self.ivar, bg='#1a3a5a',
                              fg='#e0e0e0', insertbackground='#e0e0e0',
                              font=self.editor.fnt_code, relief=tk.FLAT)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.entry.bind('<Return>', lambda e: self._submit())
        self.entry.bind('<Up>',    self._hist_up)
        self.entry.bind('<Down>',  self._hist_down)

        # El output llena el resto, por ENCIMA de la entrada.
        self.out.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.out.tag_config('head',    foreground='#4fc3f7', font=('Courier', 10, 'bold'))
        self.out.tag_config('loc',     foreground='#4fc3f7')
        self.out.tag_config('prompt',  foreground='#556677')
        self.out.tag_config('score',   foreground='#81c784')
        self.out.tag_config('warn',    foreground='#ff9944')
        self.out.tag_config('special', foreground='#ffe066')

    def _write(self, text, tag=''):
        """Thread-safe: puede llamarse desde el hilo de debug."""
        def _do():
            self.out.config(state=tk.NORMAL)
            if tag:
                self.out.insert(tk.END, text, tag)
            else:
                self.out.insert(tk.END, text)
            self.out.see(tk.END)
            self.out.config(state=tk.DISABLED)
        self.editor.root.after(0, _do)

    def _run_captured(self, func, *args, tag='', **kwargs):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = func(*args, **kwargs)
        txt = buf.getvalue()
        if txt:
            self._write(txt, tag)
        return result

    # ── Debug ────────────────────────────────────────────────────────────────

    def _toggle_debug(self):
        self._debug_mode = not self._debug_mode
        if self._debug_mode:
            self.btn_debug.config(text='  Debug: ON  ', bg='#2a1a0a', fg='#ffcc44')
            self.btn_step.config(state=tk.NORMAL)
            self.btn_cont.config(state=tk.NORMAL)
        else:
            self.btn_debug.config(text='  Debug: OFF  ', bg='#2a2a0a', fg='#888866')
            self.btn_step.config(state=tk.DISABLED)
            self.btn_cont.config(state=tk.DISABLED)
            self.lbl_dbg_line.config(text='')
            # Liberar si estaba pausado
            self._cont_mode = True
            self._step_event.set()

    def _step(self):
        """Avanza un paso en el debug."""
        self._cont_mode = False
        self._step_event.set()

    def _continue_exec(self):
        """Continúa sin pausar hasta el fin del bloque actual."""
        self._cont_mode = True
        self._step_event.set()

    def _debug_hook(self, line, cond_result):
        if not self._debug_mode:
            return
        # No pausar en REMs
        if line.strip().upper().startswith('REM'):
            return
        # Un IF que NO se cumple SÍ se muestra (el usuario quiere pasar por el if
        # aunque sea falso y, al hacer step, saltar a la línea tras el ENDIF).
        # Un ON que NO casa no pausa: la tabla de respuestas tiene decenas de ON.
        _is_if = line.strip().upper().startswith('IF ')
        if cond_result is False and not _is_if:
            return
        # En modo "continuar", solo detenerse en breakpoints
        if self._cont_mode:
            if not self.editor.has_breakpoint(self._cur_section, line):
                return
            self._cont_mode = False   # breakpoint alcanzado → pausar
        suffix = ''
        if cond_result is True:
            suffix = '  ->  VERDADERO'
        elif cond_result is False:
            suffix = '  ->  FALSO'
        section = self._cur_section
        def _ui():
            self.editor.highlight_condact(section, line)
            self.editor.sv_status.set(
                '[DEBUG] ' + section + ' | ' + line.strip()[:60] + suffix)
            self._update_vars_panel()
        self.editor.root.after(0, _ui)
        if self._cont_mode:
            return
        self.editor.root.after(0, lambda: self._set_step_buttons(True))
        self._step_event.clear()
        self._step_event.wait()
        self.editor.root.after(0, lambda: self._set_step_buttons(False))
    def _update_vars_panel(self):
        try:
            self.editor.refresh_vars_actual(self.interp.variables)
        except Exception:
            pass

    def _init_interp(self):
        import sys as _sys
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in _sys.path:
            _sys.path.insert(0, here)
        from interpreter import PAWSInterpreter, PAWSBasic as _PB
        self._PAWSBasic = _PB
        game = copy.deepcopy(self.editor.game)
        self.interp = PAWSInterpreter(game)
        # En el intérprete embebido no hay consola: SALIR termina sin preguntar
        self.interp.confirm_quit = lambda: True
        self._start()

    def _start(self):
        i = self.interp
        self._write('=' * 52 + chr(10), 'head')
        self._write('  ' + i.meta.get('title', 'Aventura') + chr(10), 'head')
        self._write('=' * 52 + chr(10), 'head')
        msg = i.meta.get('start_message', '')
        # on_start: tras la presentacion, ANTES del mensaje inicial
        self._notify_condact('on_start')
        self._run_captured(i.execute_condact_blocks, i.condacts.get('on_start', []))
        self._notify_condact('')
        if msg:
            self._write(chr(10) + msg + chr(10), 'special')
        self._run_captured(i.describe_location, tag='loc')
        # on_enter de la localización inicial (paridad con el CLI)
        self._run_captured(
            i.execute_condact_blocks,
            i.locations.get(i.player_location, {}).get('on_enter', []))
        self._update_status()
        self.entry.config(state=tk.NORMAL)
        self.entry.focus_set()

    def _restart(self):
        from interpreter import PAWSInterpreter
        # Liberar un posible hilo de turno pausado en el debugger: si no,
        # quedaría bloqueado para siempre y podría escribir salida vieja
        # sobre la sesión nueva.
        self.interp.running = False
        self._cont_mode = True
        self._step_event.set()
        self.lbl_dbg_line.config(text='')
        self._cur_section = ''
        self.out.config(state=tk.NORMAL)
        self.out.delete('1.0', tk.END)
        self.out.config(state=tk.DISABLED)
        self.entry.config(state=tk.NORMAL)
        self.interp = PAWSInterpreter(copy.deepcopy(self.editor.game))
        self.interp.confirm_quit = lambda: True
        # Reiniciar también el histórico/walkthrough: cada partida empieza limpia
        # (antes se acumulaban los comandos de sesiones anteriores).
        self.history = []
        self.history_pos = -1
        self._snap = None                       # el snapshot pertenece a la sesión
        try:
            self.btn_recall.config(state=tk.DISABLED)
        except Exception:
            pass
        self.editor.highlight_player_loc(None)
        self.editor.clear_condact_highlight()
        self._start()

    def _snapshot(self):
        """Guarda en memoria la situación actual del juego (variables, objetos,
        timers, localización y turno) para poder volver a ella con Recall Snap."""
        i = self.interp
        if i is None:
            return
        import copy
        self._snap = {
            'variables': copy.deepcopy(i.variables),
            'objects': copy.deepcopy(i.objects),
            'timers': copy.deepcopy(i.timers),
            'player_location': i.player_location,
            'turns': i.turns,
            'last_command': i.last_command,
            'running': i.running,
        }
        self.btn_recall.config(state=tk.NORMAL)
        self._write('[Snapshot guardado (turno %d)]' % i.turns + chr(10), 'special')

    def _recall_snap(self):
        """Recupera el juego al último snapshot guardado en memoria."""
        if not self._snap:
            return
        import copy
        i = self.interp
        s = self._snap
        i.variables = copy.deepcopy(s['variables'])
        i.objects = copy.deepcopy(s['objects'])
        i.timers = copy.deepcopy(s['timers'])
        i.player_location = s['player_location']
        i.turns = s['turns']
        i.last_command = s['last_command']
        i.running = s.get('running', True)
        self.entry.config(state=tk.NORMAL)
        self._write(chr(10) + '[Partida recuperada al último snapshot]'
                    + chr(10), 'special')
        self._run_captured(i.describe_location, tag='loc')
        self._update_status()
        self.entry.focus_set()

    def _submit(self):
        text = self.ivar.get().strip()
        if not text or not self.interp.running:
            return
        self.history.append(text)
        self.history_pos = -1
        self.ivar.set('')
        self.editor.root.after(0, lambda: None)  # flush
        self._write(chr(10) + '> ' + text + chr(10), 'prompt')
        self.entry.config(state=tk.DISABLED)
        import threading
        self._cont_mode = False
        t = threading.Thread(target=self._do_turn, args=(text,), daemon=True)
        t.start()

    def _do_turn(self, text):
        import io, contextlib
        i = self.interp
        if self._debug_mode:
            self._cont_mode = True
        def enter_section(section):
            self._cur_section = section
            self.editor.root.after(0, lambda s=section: self._notify_condact(s))
            if self._debug_mode:
                # Con breakpoints definidos se corre libre hasta el siguiente
                # breakpoint; sin ellos, pausa al inicio de cada sección.
                self._cont_mode = bool(self.editor.any_breakpoints())
        def leave_section():
            self.editor.root.after(0, lambda: self._notify_condact(''))
        def run_section_blocks(section, script):
            if not script:
                return
            enter_section(section)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                if self._debug_mode:
                    if isinstance(script, str):
                        text2 = script
                    elif script and isinstance(script[0], str):
                        text2 = chr(10).join(script)
                    else:
                        text2 = None
                    if text2:
                        b = self._PAWSBasic(i)
                        b.pre_exec_hook = self._debug_hook
                        b.run(text2)
                    else:
                        i.execute_condact_blocks(script)
                else:
                    i.execute_condact_blocks(script)
            if buf.getvalue():
                self._write(buf.getvalue())
            leave_section()
        def make_basic(verb, noun1, noun2):
            basic = self._PAWSBasic(i)
            basic._current_verb  = verb
            basic._current_noun1 = noun1
            basic._current_noun2 = noun2
            basic.pre_exec_hook  = self._debug_hook if self._debug_mode else None
            return basic
        def alive():
            # False si la sesión se reinició mientras este turno corría
            # (p. ej. Reiniciar con el debugger pausado)
            return self.interp is i
        i.last_command = text
        i.turns += 1
        run_section_blocks('before_turn', i.condacts.get('before_turn', []))
        if not alive():
            return
        if not i.running:
            return self.editor.root.after(0, self._end)
        verb, noun1, noun2 = i.parse(text)
        if not verb:
            self._write('No entiendo eso.' + chr(10), 'warn')
            # El turno cuenta igualmente: timers y after_turn corren abajo
            # (paridad con el CLI; antes el reloj se congelaba).
        else:
            enter_section('responses')
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                handled = False
                resp_script = i.condacts.get('responses', '')
                if resp_script:
                    basic = make_basic(verb, noun1, noun2)
                    basic.run(resp_script)
                    # MATCH o fin de partida (END): no caer a los built-ins
                    handled = basic._stop or not i.running
                if not handled:
                    handled = i.find_response(verb, noun1, noun2)
                if not handled:
                    handled = i.handle_builtin(verb, noun1, noun2)
                if not handled:
                    print('No puedes hacer eso.')
            self._write(buf.getvalue())
            leave_section()
        if not alive():
            return
        if not i.running:
            return self.editor.root.after(0, self._end)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            i.tick_timers()
        if buf.getvalue():
            self._write(buf.getvalue())
        run_section_blocks('after_turn', i.condacts.get('after_turn', []))
        if not alive():
            return
        if not i.running:
            return self.editor.root.after(0, self._end)
        self.editor.root.after(0, self._update_status)
        self.editor.root.after(0, lambda: self.entry.config(state=tk.NORMAL))
        self.editor.root.after(0, lambda: self.lbl_dbg_line.config(text=''))
        self.editor.root.after(0, lambda: self._set_step_buttons(False))

    def _end(self):
        self._write(chr(10) + '[ FIN DEL JUEGO ]' + chr(10), 'score')
        self.entry.config(state=tk.DISABLED)
        self.editor.highlight_player_loc(None)
        self.editor.clear_condact_highlight()
        self._notify_condact('')
        self.lbl_dbg_line.config(text='')
        self.editor.sv_status.set('Juego terminado')
        self._set_step_buttons(False)

    def _notify_condact(self, section):
        self.lbl_condact.config(text=('[' + section + ']') if section else '')
        if section:
            self.editor.highlight_condact(section)

    def _update_status(self):
        i   = self.interp
        loc = i.player_location
        pts = i.variables.get('PUNTOS', 0)
        self.lbl_loc.config(text='Loc: ' + loc)
        self.lbl_score.config(text='Pts: ' + str(pts) + '  T: ' + str(i.turns))
        self.editor.highlight_player_loc(loc)
        self._update_vars_panel()

    # ── Walkthroughs: editar, guardar historial y reproducir scripts ─────────

    def _edit_history(self):
        """Editor del walkthrough actual: permite eliminar pasos (p. ej. el último),
        editarlos y reordenarlos antes de guardar."""
        if not self.history:
            messagebox.showinfo('Walkthrough vacío',
                                'Aún no has tecleado ningún comando.')
            return
        from tkinter import simpledialog
        win = tk.Toplevel(self.editor.root)
        win.title('Editar walkthrough actual')
        win.transient(self.editor.root)
        win.grab_set()
        tmp = list(self.history)
        tk.Label(win, text='Pasos del walkthrough (elimina, reordena o edita; '
                 'doble clic para editar):').pack(anchor=tk.W, padx=10, pady=(10, 4))
        body = tk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=10)
        lb = tk.Listbox(body, width=52, height=16, activestyle='dotbox',
                        font=self.editor.fnt_code)
        sb = ttk.Scrollbar(body, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def refill(sel=None):
            lb.delete(0, tk.END)
            for i, c in enumerate(tmp, 1):
                lb.insert(tk.END, '%3d.  %s' % (i, c))
            if sel is not None and 0 <= sel < len(tmp):
                lb.selection_set(sel)
                lb.activate(sel)
                lb.see(sel)

        def cur():
            s = lb.curselection()
            return s[0] if s else None

        def del_sel():
            i = cur()
            if i is None:
                return
            del tmp[i]
            refill(min(i, len(tmp) - 1))

        def del_last():
            if tmp:
                tmp.pop()
                refill(len(tmp) - 1)

        def move(d):
            i = cur()
            if i is None:
                return
            j = i + d
            if 0 <= j < len(tmp):
                tmp[i], tmp[j] = tmp[j], tmp[i]
                refill(j)

        def edit_line():
            i = cur()
            if i is None:
                return
            v = simpledialog.askstring('Editar paso', 'Comando:',
                                       initialvalue=tmp[i], parent=win)
            if v is not None:
                tmp[i] = v.strip()
                refill(i)

        def clear_all():
            if messagebox.askyesno('Vaciar', '¿Eliminar todos los pasos?',
                                   parent=win):
                tmp.clear()
                refill()

        lb.bind('<Double-Button-1>', lambda e: edit_line())
        refill(len(tmp) - 1)
        bf1 = tk.Frame(win)
        bf1.pack(fill=tk.X, padx=10, pady=(6, 2))
        for txt, cmd in (('Eliminar último', del_last),
                         ('Eliminar selección', del_sel),
                         ('Editar…', edit_line),
                         ('▲ Subir', lambda: move(-1)),
                         ('▼ Bajar', lambda: move(1)),
                         ('Vaciar', clear_all)):
            tk.Button(bf1, text=txt, command=cmd).pack(side=tk.LEFT, padx=2)
        bf2 = tk.Frame(win)
        bf2.pack(fill=tk.X, padx=10, pady=(4, 10))

        def accept():
            self.history = list(tmp)
            self.history_pos = -1
            self._write('[Walkthrough editado: %d pasos]' % len(self.history)
                        + chr(10), 'special')
            win.destroy()
        ttk.Button(bf2, text='Aceptar', command=accept).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bf2, text='Cancelar',
                   command=win.destroy).pack(side=tk.RIGHT, padx=2)

    def _save_history(self):
        """Guarda los comandos tecleados en esta sesión como walkthrough."""
        if not self.history:
            messagebox.showinfo('Sin historial',
                                'Aún no has tecleado ningún comando.')
            return
        path = filedialog.asksaveasfilename(
            title='Guardar walkthrough',
            defaultextension='.txt',
            filetypes=[('Walkthrough', '*.txt'), ('Todos', '*.*')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('# Walkthrough Scriba — un comando por línea\n')
                f.write('\n'.join(self.history) + '\n')
            self._write('[Historial guardado: ' + os.path.basename(path)
                        + ' (' + str(len(self.history)) + ' comandos)]' + chr(10),
                        'special')
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def _replay_script(self):
        """Carga un walkthrough (.txt, un comando por línea) y lo reproduce."""
        if not self.interp.running:
            messagebox.showinfo('Juego terminado',
                                'Reinicia la partida antes de reproducir.')
            return
        path = filedialog.askopenfilename(
            title='Reproducir walkthrough',
            filetypes=[('Walkthrough', '*.txt'), ('Todos', '*.*')])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cmds = [l.strip() for l in f
                        if l.strip() and not l.strip().startswith('#')]
        except Exception as e:
            messagebox.showerror('Error', str(e))
            return
        if not cmds:
            return
        self._write(chr(10) + '[Reproduciendo ' + os.path.basename(path)
                    + ': ' + str(len(cmds)) + ' comandos]' + chr(10), 'special')
        self.entry.config(state=tk.DISABLED)
        import threading
        threading.Thread(target=self._replay_run, args=(cmds,),
                         daemon=True).start()

    def _replay_run(self, cmds):
        i_ref = self.interp
        for n, cmd in enumerate(cmds, 1):
            if self.interp is not i_ref or not self.interp.running:
                break
            self.history.append(cmd)
            self._write(chr(10) + '> ' + cmd + chr(10), 'prompt')
            self._do_turn(cmd)
        if self.interp is i_ref:
            if self.interp.running:
                self._write(chr(10) + '[Fin del walkthrough]' + chr(10), 'special')
            self.editor.root.after(
                0, lambda: self.entry.config(
                    state=tk.NORMAL if self.interp.running else tk.DISABLED))

    def _hist_up(self, event):
        if self.history:
            self.history_pos = min(self.history_pos + 1, len(self.history) - 1)
            self.ivar.set(self.history[-(self.history_pos + 1)])

    def _hist_down(self, event):
        if self.history_pos > 0:
            self.history_pos -= 1
            self.ivar.set(self.history[-(self.history_pos + 1)])
        else:
            self.history_pos = -1
            self.ivar.set('')

    def close(self):
        # Liberar el hilo del turno si estaba pausado en el debugger
        self._debug_mode = False
        self._cont_mode  = True
        self._step_event.set()
        self.editor.highlight_player_loc(None)
        self.editor.clear_condact_highlight()
        self.editor._interp_win = None
        placeholder = self.editor._interp_placeholder
        for w in self.frame.winfo_children():
            if w is not placeholder:
                w.destroy()
        placeholder.pack(expand=True)
        h = self.editor._right_pw.winfo_height()
        self.editor._right_pw.sash_place(0, 0, h - 4)

    def _set_step_buttons(self, active):
        state = tk.NORMAL if active else tk.DISABLED
        self.btn_step.config(state=state)
        self.btn_cont.config(state=state)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def _resource_path(name):
    """Ruta de un recurso, válida también en el .exe de PyInstaller."""
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def _show_splash(root):
    """Pantalla de bienvenida de Scriba (logo + lema). Se cierra sola a los
    ~2,5 s o al pulsar. Si no encuentra scriba_logo.png muestra el texto."""
    try:
        sp = tk.Toplevel(root)
        sp.withdraw()                      # oculta mientras se posiciona
        sp.configure(bg='white', highlightthickness=1,
                     highlightbackground='#1f3a5f')
        img = None
        try:
            p = None
            for _n in ('scriba_logo.png', 'scriba_logo.PNG', 'scriba-logo.png',
                       'scriba-logo.PNG', 'logo.png'):
                _c = _resource_path(_n)
                if os.path.isfile(_c) and os.path.getsize(_c) > 0:
                    p = _c
                    break
            if p:
                img = tk.PhotoImage(file=p)
                f = max(1, (img.width() + 299) // 300)   # objetivo ~300 px ancho
                if f > 1:
                    img = img.subsample(f, f)
        except Exception:
            img = None
        if img is not None:
            lbl = tk.Label(sp, image=img, bg='white')
            lbl.image = img                              # referencia viva
            lbl.pack(padx=30, pady=(24, 2))
        else:
            tk.Label(sp, text='SCRIBA', bg='white', fg='#1f3a5f',
                     font=('Helvetica', 44, 'bold')).pack(padx=70, pady=(46, 2))
        tk.Label(sp, text='Multiplatform Adventure Writing System',
                 bg='white', fg='#2e6da4',
                 font=('Helvetica', 12)).pack(padx=24, pady=(0, 6))
        tk.Label(sp, text='Version ' + SCRIBA_VERSION + '     ' + SCRIBA_COPYRIGHT,
                 bg='white', fg='#8090a0',
                 font=('Helvetica', 9)).pack(padx=24, pady=(0, 22))
        sp.update_idletasks()
        w, h = sp.winfo_reqwidth(), sp.winfo_reqheight()
        # Centrar sobre la ventana principal si ya tiene geometría; si no, pantalla
        try:
            root.update_idletasks()
            rw, rh = root.winfo_width(), root.winfo_height()
            rx, ry = root.winfo_rootx(), root.winfo_rooty()
        except Exception:
            rw = rh = 0
        if rw > 1 and rh > 1 and (rx or ry):
            x, y = rx + (rw - w) // 2, ry + (rh - h) // 2
        else:
            x = (sp.winfo_screenwidth() - w) // 2
            y = (sp.winfo_screenheight() - h) // 2
        x, y = max(0, x), max(0, y)
        sp.geometry('%dx%d+%d+%d' % (w, h, x, y))
        sp.overrideredirect(True)              # tras fijar geometría (Windows)
        sp.deiconify()
        sp.geometry('+%d+%d' % (x, y))         # reafirmar posición
        sp.after(10, lambda: sp.geometry('+%d+%d' % (x, y)))
        try:
            sp.attributes('-topmost', True)
        except Exception:
            pass

        def _close():
            try:
                sp.destroy()
            except Exception:
                pass
        sp.bind('<Button-1>', lambda e: _close())
        sp.after(2500, _close)
        sp.update()
        return sp
    except Exception:
        return None


if __name__ == '__main__':
    root = tk.Tk()
    initial = sys.argv[1] if len(sys.argv) > 1 else None
    app = ScribaEditor(root, initial_file=initial)
    root.update_idletasks()          # la ventana ya tiene tamaño/posición
    _show_splash(root)               # splash centrada sobre la ventana
    root.mainloop()
