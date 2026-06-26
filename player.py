# -*- coding: utf-8 -*-
"""
player.py — Reproductor de ventana (Windows/escritorio) para juegos de Scriba.

Ejecuta la aventura con el intérprete Python (PAWSInterpreter) dentro de una
ventana: imagen original de la localización arriba y el texto del juego a 32/42/64
columnas debajo, con una caja de entrada de comandos.

Dos formas de uso:
  • Suelto (desarrollo/pruebas):   python player.py <juego.yaml> [columnas]
  • Empaquetado por juego (.exe):  el juego, las imágenes (img/Original) y la
    configuración (player_cfg.json) viajan dentro del ejecutable; ver
    build_game_exe.py. Al estar "congelado" (PyInstaller) los lee del bundle.

GameSession no depende de tkinter (se puede probar sin pantalla); PlayerApp es la
ventana.
"""

import os
import sys
import io
import json
import queue
import threading
import builtins

# El intérprete y el cargador de juego ya existen en el proyecto.
import interpreter as _engine


# ─── Localización de recursos (disco o bundle PyInstaller) ───────────────────

def _frozen_base():
    """Carpeta de recursos cuando el programa va empaquetado (.exe), o None."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return None


def cargar_config(argv):
    """Resuelve (game_dict, img_dir, titulo) según el modo.

    Empaquetado, dos variantes:
      • PORTABLE: el juego (game.yaml + player_cfg.json + img/Original) está en la
        MISMA carpeta que el .exe. Lo usa ScribaPlayer.exe (reproductor genérico).
      • EMBEBIDO: el juego viaja dentro del .exe (bundle _MEIPASS).
    Suelto (desde código): argv[1] = ruta al .yaml."""
    base = _frozen_base()
    if base:
        # Portable: ¿hay datos de juego junto al ejecutable?
        exedir = os.path.dirname(sys.executable)
        if (os.path.isfile(os.path.join(exedir, 'player_cfg.json'))
                or os.path.isfile(os.path.join(exedir, 'game.yaml'))):
            base = exedir
        cfg_path = os.path.join(base, 'player_cfg.json')
        cfg = {}
        if os.path.isfile(cfg_path):
            with open(cfg_path, encoding='utf-8') as f:
                cfg = json.load(f)
        yaml_name = cfg.get('game', 'game.yaml')
        game = _engine.load_game(os.path.join(base, yaml_name))
        img_dir = os.path.join(base, 'img', 'Original')
        titulo = cfg.get('title') or game.get('metadata', {}).get('title', 'Scriba')
        return game, img_dir, titulo
    # Modo suelto
    if len(argv) < 2:
        raise SystemExit('uso: python player.py <juego.yaml>')
    yaml_path = argv[1]
    game = _engine.load_game(yaml_path)
    base_dir = os.path.dirname(os.path.abspath(yaml_path))
    img_dir = os.path.join(base_dir, 'img', 'Original')
    titulo = game.get('metadata', {}).get('title', 'Scriba')
    return game, img_dir, titulo


# ─── Sin ajuste por columnas (la ventana es redimensionable) ─────────────────

class _SinAjuste:
    """Sustituto de textwrap dentro del intérprete: NO parte las líneas. El texto
    se ajusta solo al ancho de la ventana (el widget reflow con cada cambio de
    tamaño). Conserva los saltos de línea que ya trae el texto."""
    @staticmethod
    def fill(text, width=None, **kw):
        return text


# ─── Sesión de juego (sin tkinter; testeable) ────────────────────────────────

class _ColaSalida(io.TextIOBase):
    """Stream de escritura que vuelca lo que imprima el intérprete a una cola."""
    def __init__(self, cola):
        self._cola = cola

    def write(self, s):
        if s:
            self._cola.put(s)
        return len(s)

    def flush(self):
        pass


class GameSession:
    """Ejecuta el intérprete en un hilo y comunica con la GUI por colas.

    - out_queue: trozos de texto que va imprimiendo el juego.
    - send(linea): entrega un comando a la entrada del intérprete.
    - location: localización actual (para refrescar la imagen).
    - alive: True mientras el hilo del juego sigue vivo.
    """
    def __init__(self, game):
        self.interp = _engine.PAWSInterpreter(game)
        self.out_queue = queue.Queue()
        self._in_queue = queue.Queue()
        self._hilo = None
        self._stdout_prev = None
        self._input_prev = None

    # --- API ---
    def start(self):
        self._hilo = threading.Thread(target=self._run, daemon=True)
        self._hilo.start()

    def send(self, linea):
        self._in_queue.put(linea)

    def read_output(self, timeout=0.0):
        """Devuelve todo el texto disponible ahora (cadena), o '' si no hay.

        NO bloquea por defecto (timeout=0.0): la GUI lo sondea desde el hilo
        principal y bloquear ahí congelaría la ventana. Con timeout>0 espera ese
        tiempo al primer trozo (útil en pruebas). El marcador de fin (None) se
        ignora aquí; el fin se detecta con .alive."""
        trozos = []
        if timeout:
            try:
                trozos.append(self.out_queue.get(timeout=timeout))
            except queue.Empty:
                return ''
        while True:
            try:
                trozos.append(self.out_queue.get_nowait())
            except queue.Empty:
                break
        return ''.join(t for t in trozos if isinstance(t, str))

    @property
    def location(self):
        return getattr(self.interp, 'player_location', None)

    @property
    def alive(self):
        return self._hilo is not None and self._hilo.is_alive()

    # --- interno ---
    def _input(self, prompt=''):
        if prompt:
            self.out_queue.put(prompt)
        linea = self._in_queue.get()           # bloquea hasta que la GUI envíe
        if linea is None:                       # señal de cierre
            raise EOFError
        return linea

    def _run(self):
        # Redirección de E/S y ajuste de columnas SOLO durante la partida.
        self._stdout_prev = sys.stdout
        self._input_prev = builtins.input
        tw_prev = _engine.textwrap
        sys.stdout = _ColaSalida(self.out_queue)
        builtins.input = self._input
        _engine.textwrap = _SinAjuste()
        try:
            self.interp.run()
        except EOFError:
            pass
        except Exception as e:                  # no romper la ventana
            self.out_queue.put('\n[Error del intérprete: %s]\n' % e)
        finally:
            sys.stdout = self._stdout_prev
            builtins.input = self._input_prev
            _engine.textwrap = tw_prev
            self.out_queue.put(None)            # marca de fin

    def stop(self):
        self._in_queue.put(None)


# ─── Imágenes ────────────────────────────────────────────────────────────────

def buscar_imagen(img_dir, loc_id):
    """Ruta de la imagen original de una localización, o None."""
    if not img_dir or not loc_id:
        return None
    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
        p = os.path.join(img_dir, str(loc_id) + ext)
        if os.path.isfile(p):
            return p
    return None


# ─── Ventana ─────────────────────────────────────────────────────────────────

def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    game, img_dir, titulo = cargar_config(argv)

    import tkinter as tk
    from tkinter import ttk, font as tkfont
    try:
        from PIL import Image, ImageTk
    except Exception:
        Image = ImageTk = None

    root = tk.Tk()
    root.title(titulo)
    root.minsize(720, 600)
    try:
        ttk.Style().theme_use('clam')
    except Exception:
        pass

    BG = '#f4f5f7'
    root.configure(bg=BG)

    # Panel de imagen (arriba)
    img_panel = tk.Label(root, bg='#1b1d22', bd=0)
    img_panel.pack(side=tk.TOP, fill=tk.X)
    img_panel.configure(height=300)
    _img_ref = {'tk': None, 'loc': object()}

    # Fuente proporcional del sistema (sin columnas fijas: el texto se ajusta solo
    # al ancho de la ventana, que es redimensionable).
    fam = None
    fams = set(tkfont.families())
    for c in ('Segoe UI', 'Calibri', 'DejaVu Sans', 'Helvetica', 'Arial'):
        if c in fams:
            fam = c
            break
    fnt = tkfont.Font(family=fam, size=12) if fam else tkfont.nametofont('TkTextFont')

    # Texto del juego (centro): word-wrap al ancho actual de la ventana
    wrap = tk.Frame(root, bg=BG)
    wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))
    txt = tk.Text(wrap, height=18, wrap=tk.WORD, font=fnt,
                  bg='#ffffff', fg='#1b1d22', bd=1, relief=tk.SOLID,
                  padx=12, pady=10, state=tk.DISABLED, cursor='arrow')
    sb = ttk.Scrollbar(wrap, command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Entrada de comandos (abajo)
    barra = tk.Frame(root, bg=BG)
    barra.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
    ent = ttk.Entry(barra, font=fnt)
    ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
    btn = ttk.Button(barra, text='Enviar')
    btn.pack(side=tk.LEFT, padx=(6, 0))

    ses = GameSession(game)

    def _append(s):
        txt.configure(state=tk.NORMAL)
        txt.insert(tk.END, s)
        txt.see(tk.END)
        txt.configure(state=tk.DISABLED)

    def _enviar(*_):
        s = ent.get().strip()
        if not s or not ses.alive:
            return
        ent.delete(0, tk.END)
        _append('\n> %s\n' % s)
        ses.send(s)

    btn.configure(command=_enviar)
    ent.bind('<Return>', _enviar)

    def _set_imagen(loc_id):
        if _img_ref['loc'] == loc_id:
            return
        _img_ref['loc'] = loc_id
        p = buscar_imagen(img_dir, loc_id)
        if not p or Image is None:
            if not p:
                img_panel.configure(image='', height=8)
            return
        try:
            im = Image.open(p)
            pw = max(root.winfo_width() - 20, 400)
            ph = 320
            im.thumbnail((pw, ph))
            ph_img = ImageTk.PhotoImage(im)
            _img_ref['tk'] = ph_img
            img_panel.configure(image=ph_img, height=im.height)
        except Exception:
            img_panel.configure(image='', height=8)

    def _poll():
        s = ses.read_output()
        if s:
            _append(s)
        _set_imagen(ses.location)
        if not ses.alive and ses.out_queue.empty():
            ent.configure(state=tk.DISABLED)
            btn.configure(state=tk.DISABLED)
            return
        root.after(60, _poll)

    def _cerrar():
        try:
            ses.stop()
        except Exception:
            pass
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', _cerrar)
    ses.start()
    ent.focus_set()
    root.after(60, _poll)
    root.mainloop()


if __name__ == '__main__':
    main()
