# -*- coding: utf-8 -*-
"""
probar_cpc.py - La bateria .pru, jugada sobre el disco del Amstrad CPC.

Mismo fichero .pru y mismo juez que probar_juego.py. Lo que se mete en el
simulador es el .dsk tal cual lo escribe cpc_nativo: el cargador BASIC se
interpreta (lo que usa: MEMORY, OUT, POKE, PEEK, IF, PRINT, END, LOAD, CALL),
el firmware se hace en Python -- la pantalla de texto, el teclado, el disco
(CAS IN), las tintas -- y la RAM extra se pagina como en un 6128, por el
puerto &7Fxx. Asi se prueban de verdad el texto en bancos, la cache de
imagenes en los bancos y el ZX0: cada vez que se describe una sala, la imagen
que queda en la pantalla se compara con la que se convirtio.

    python probar_cpc.py juego.yaml bateria.pru [-v|-vv] [--modo 2] [--464]
                         [--png carpeta]

--464 simula un CPC sin RAM extra (el cargador debe negarse si el texto va en
bancos). --png guarda la pantalla de cada sala nueva, con sus tintas.
"""
import io
import os
import re
import sys
import tempfile
import time

import yaml

import cpc_nativo as cn
import game_engine as ge
import png2cpc
import probar_juego as pj
import spectrum_export as sx
import z80

FW_TXT_OUTPUT = 0xBB5A
FW_KM_WAIT = 0xBB06
FW_KM_READ = 0xBB09
FW_TXT_WIN = 0xBB66
FW_TXT_GETWIN = 0xBB69
FW_TXT_GETCUR = 0xBB78
FW_KM_RETURN = 0xBB0C
FW_CAS_OPEN = 0xBC77
FW_CAS_CLOSE = 0xBC7A
FW_CAS_DIRECT = 0xBC83
FW_SCR_MODE = 0xBC0E
FW_SCR_INK = 0xBC32
FW_SCR_BORDER = 0xBC38
# lo que no hace falta imitar: tinta de texto, matrices, eventos, sonido...
FW_NADA = (0xBB90, 0xBB96, 0xBBA8, 0xBBA5, 0xBBAB, 0xBCEF, 0xBCD7, 0xBCDD,
           0xBD19, 0xBD34, 0xBCAA)
MUSICA = (0x8B00, 0x8B03, 0x8B06)       # el reproductor del titulo


def lee_dsk(img):
    """Los ficheros de un .dsk de dsk.make_dsk: {'NOMBRE.EXT': bytes}."""
    datos = bytearray()
    off = 256
    for _t in range(40):
        ids = [img[off + 24 + 8 * k + 2] for k in range(9)]   # orden fisico
        pista = {sid: img[off + 256 + 512 * k:off + 256 + 512 * (k + 1)]
                 for k, sid in enumerate(ids)}
        for sid in range(0xC1, 0xCA):
            datos += pista[sid]
        off += 256 + 9 * 512
    bloque = lambda b: bytes(datos[b * 1024:(b + 1) * 1024])
    fich = {}
    for i in range(64):
        e = datos[i * 32:(i + 1) * 32]
        if e[0] != 0 or not (32 < e[1] < 127):
            continue
        nm = (bytes(e[1:9]).decode('ascii').strip() + '.' +
              bytes(e[9:12]).decode('ascii').strip())
        trozo = b''.join(bloque(b) for b in e[16:32] if b)[:e[15] * 128]
        fich[nm] = fich.get(nm, b'') + trozo
    return fich


def cabecera(f):
    """(direccion de carga, datos) de un fichero con cabecera AMSDOS."""
    h = f[:128]
    lon = h[64] | (h[65] << 8) | (h[66] << 16)
    return h[21] | (h[22] << 8), f[128:128 + lon]


class Pantalla:
    """La pantalla de texto del firmware: ventana, cursor y desplazamiento."""

    def __init__(self, acentos):
        self.acentos = acentos
        self.raros = set()
        self.modo(1)

    def modo(self, m):
        self.cols = {0: 20, 1: 40, 2: 80}.get(m, 40)
        self.m = m
        self.s = [[' '] * self.cols for _ in range(25)]
        self.ventana(0, self.cols - 1, 0, 24)

    def ventana(self, iz, de, ar, ab):
        de = min(de, self.cols - 1)
        ab = min(ab, 24)
        self.w = (min(iz, de), de, min(ar, ab), ab)
        self.x, self.y = self.w[0], self.w[2]

    def cls(self):
        iz, de, ar, ab = self.w
        for y in range(ar, ab + 1):
            for x in range(iz, de + 1):
                self.s[y][x] = ' '
        self.x, self.y = iz, ar

    def lf(self):
        iz, de, ar, ab = self.w
        self.y += 1
        if self.y > ab:
            for y in range(ar, ab):
                self.s[y][iz:de + 1] = self.s[y + 1][iz:de + 1]
            self.s[ab][iz:de + 1] = [' '] * (de - iz + 1)
            self.y = ab

    def out(self, ch):
        iz, de, ar, ab = self.w
        if ch >= 32:
            if self.x > de:
                self.x = iz
                self.lf()
            self.s[self.y][self.x] = self.acentos.get(ch, chr(ch) if ch < 127 else '?')
            self.x += 1
        elif ch == 13:
            self.x = iz
        elif ch == 10:
            self.lf()
        elif ch == 8:
            if self.x > iz:
                self.x -= 1
        elif ch == 12:
            self.cls()
        elif ch != 7:
            self.raros.add(ch)

    def tapa(self, filas):
        """Una imagen pintada encima de las primeras filas: su texto ya no se ve."""
        for y in range(filas):
            self.s[y] = [' '] * self.cols

    def lineas(self):
        return [''.join(f).rstrip() for f in self.s]


class JuegoCPC(pj.Juego):
    maquina = 'cpc'
    """Un juego exportado a .dsk y listo para jugarse en el simulador."""

    def __init__(self, yaml_path, modo=1, sin_ram_extra=False, png=None, game=None,
                 img_dir=None):
        raiz = os.path.dirname(os.path.abspath(yaml_path))
        self.game = game if game is not None else \
            yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
        self.dsk = os.path.join(tempfile.gettempdir(), 'scriba_pruebas_cpc.dsk')
        img = img_dir or os.path.join(raiz, 'img')
        self.img_dir = img if os.path.isdir(img) else None
        self.modo_juego = modo
        self.info = cn.export_native(self.game, self.dsk, modo=modo,
                                     img_dir=self.img_dir)
        self.sym = {k.lower(): v for k, v in self.info['simbolos'].items()}
        self.ficheros = lee_dsk(open(self.dsk, 'rb').read())
        self.sin_ram_extra = sin_ram_extra
        self.png = png
        c = sx.recolecta(self.game)
        self.vars = {k.upper(): i for i, k in enumerate(c.vars.keys())}
        self.locs = list(c.locids)
        self.objs = {n.upper(): i for i, n in enumerate(
            n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
        lang = str(((self.game.get('metadata') or {}).get('language') or '')).lower()
        tabla = sx._ACC_CODE_PT if lang.startswith('pt') else sx._ACC_CODE
        self.acentos = {v + 80: k for k, v in tabla.items()}
        # lo que deberia verse arriba en cada sala: la imagen convertida
        self.esperada = {}
        if self.img_dir:
            tintas = cn._tintas_texto(self.game, modo)
            cpcdir = os.path.join(self.img_dir, 'AmstradCPC')
            origdir = os.path.join(self.img_dir, 'Original')
            for name, lid in c.locidx.items():
                r = cn._loc_image(cpcdir, origdir, name, modo, tintas)
                if r is not None:
                    self.esperada[lid - 1] = r
        self.fallos_imagen = []
        self.salas_vistas = set()
        self.cpu = self.mem = None

    # ---- memoria de 128K ----
    def pagina(self, cfg):
        if cfg == self.cfg:
            return
        if self.sin_ram_extra:
            return                      # un 464: el puerto no hace nada
        if cfg not in (0xC0, 0xC4, 0xC5, 0xC6, 0xC7):
            raise RuntimeError('configuracion de RAM no prevista: &%02X' % cfg)
        self.bancos[self.cfg] = bytes(self.mem[0x4000:0x8000])
        self.mem[0x4000:0x8000] = self.bancos[cfg]
        self.cfg = cfg

    def banco(self, cfg):
        """Los 16K de un banco, esten o no puestos en la ventana."""
        return bytes(self.mem[0x4000:0x8000]) if cfg == self.cfg else self.bancos[cfg]

    # ---- el cargador BASIC ----
    def basic(self):
        txt = cabecera_ascii(self.ficheros['DISC.BAS'])
        vars_b = {}
        self.impreso = []
        himem = 0xA67B                  # con AMSDOS
        for linea in txt.split('\n'):
            linea = linea.strip()
            if not linea:
                continue
            m = re.match(r'(\d+)\s+(.*)', linea)
            nlinea = m.group(1)
            sentencias = trocea(m.group(2))
            k = 0
            while k < len(sentencias):
                st = sentencias[k].strip()
                k += 1
                u = st.upper()
                mm = re.match(r'INK\s+(\d+),\s*(\d+)$', u)
                if mm:
                    self.tintas[int(mm.group(1)) & 15] = int(mm.group(2))
                    continue
                mm = re.match(r'BORDER\s+(\d+)$', u)
                if mm:
                    self.borde = int(mm.group(1))
                    continue
                if u.startswith(('MEMORY', 'MODE', 'FOR ', 'INK ', 'NEXT')):
                    if u.startswith('MEMORY'):
                        himem = int(u.split('&')[1], 16)
                    if u.startswith('MODE'):
                        self.pant.modo(int(u.split()[1]))
                    continue
                mm = re.match(r'OUT\s+&7F00,\s*&([0-9A-F]{2})$', u)
                if mm:
                    self.pagina(int(mm.group(1), 16))
                    continue
                mm = re.match(r'POKE\s+&([0-9A-F]+),\s*(\d+)$', u)
                if mm:
                    self.mem[int(mm.group(1), 16)] = int(mm.group(2))
                    continue
                mm = re.match(r'(\w+)=PEEK\(&([0-9A-F]+)\)$', u)
                if mm:
                    vars_b[mm.group(1)] = self.mem[int(mm.group(2), 16)]
                    continue
                mm = re.match(r'IF\s+(\w+)<>(\d+)\s+THEN\s+(.*)$', st, re.I)
                if mm:
                    if vars_b.get(mm.group(1).upper()) != int(mm.group(2)):
                        sentencias = [mm.group(3)] + sentencias[k:]
                        k = 0
                    else:
                        break               # falso: el resto de la linea, fuera
                    continue
                mm = re.match(r'PRINT\s*"(.*)"$', st, re.I)
                if mm:
                    self.impreso.append(mm.group(1))
                    continue
                if u == 'END':
                    return None
                mm = re.match(r'LOAD\s*"([^"]+)"$', st, re.I)
                if mm:
                    nm = mm.group(1).upper()
                    # BASIC aparta su buffer de disco debajo de HIMEM
                    if cn.libre_basic(txt, himem + 1) < cn.BASIC_BUFFER:
                        raise RuntimeError('Memory full in %s (quedan %d bytes '
                                           'para el buffer de %d)'
                                           % (nlinea, cn.libre_basic(txt, himem + 1),
                                              cn.BASIC_BUFFER))
                    dire, datos = cabecera(self.ficheros[nm])
                    if dire <= himem:
                        raise RuntimeError('Memory full in %s: %s va a &%04X, '
                                           'debajo de HIMEM' % (nlinea, nm, dire))
                    self.mem[dire:dire + len(datos)] = datos
                    continue
                mm = re.match(r'CALL\s+&([0-9A-F]+)$', u)
                if mm:
                    return int(mm.group(1), 16)
                raise RuntimeError('el cargador trae algo que no se imitar: %s' % st)
        return None

    # ---- el firmware ----
    def firmware(self, cpu, pc):
        m = self.mem
        if pc == FW_TXT_OUTPUT:
            self.pant.out(cpu.a)
        elif pc == FW_KM_READ:
            if self.ocioso > 0:
                self.ocioso -= 1           # un rato sin tecla: precarga
                cpu.f &= ~z80.FC
            elif self.cola:
                cpu.a = ord(self.cola.pop(0))
                cpu.f |= z80.FC
            else:
                self.esperando = True
                cpu.f &= ~z80.FC
        elif pc == FW_KM_WAIT:
            cpu.a = 32
            cpu.f |= z80.FC
        elif pc == FW_KM_RETURN:
            self.cola.insert(0, chr(cpu.a))
        elif pc == FW_TXT_WIN:
            self.pant.ventana(cpu.h, cpu.d, cpu.l, cpu.e)
        elif pc == FW_TXT_GETWIN:
            iz, de, ar, ab = self.pant.w
            cpu.h, cpu.d, cpu.l, cpu.e = iz, de, ar, ab
        elif pc == FW_TXT_GETCUR:          # logicas: 1,1 = arriba a la izquierda
            iz, de, ar, ab = self.pant.w
            cpu.h, cpu.l = self.pant.x - iz + 1, self.pant.y - ar + 1
        elif pc == FW_SCR_MODE:
            self.pant.modo(cpu.a)
            self.modo = cpu.a
            m[0xC000:0x10000] = bytes(0x4000)
        elif pc == FW_SCR_INK:
            self.tintas[cpu.a & 15] = cpu.b
        elif pc == FW_SCR_BORDER:
            self.borde = cpu.b
        elif pc == FW_CAS_OPEN:
            nm = bytes(m[cpu.hl:cpu.hl + cpu.b]).decode('latin-1').upper()
            f = self.ficheros.get(nm)
            self.cargas.append(nm)
            if f is None:
                self.abierto = None
                cpu.f &= ~(z80.FC | z80.FZ)
            else:
                dire, datos = cabecera(f)
                self.abierto = datos
                m[cpu.de:cpu.de + 128] = f[:128]
                cpu.hl = cpu.de
                cpu.de = dire
                cpu.bc = len(datos)
                cpu.a = 2
                cpu.f = (cpu.f | z80.FC) & ~z80.FZ
        elif pc == FW_CAS_DIRECT:
            d = self.abierto
            if 0x4000 <= cpu.hl + len(d) and cpu.hl < 0x8000 and self.cfg != 0xC0:
                raise RuntimeError('CAS IN DIRECT con un banco puesto')
            m[cpu.hl:cpu.hl + len(d)] = d
            if cpu.hl == 0xC000:
                self.pant.tapa(25)         # una pantalla entera, derecha a video
            cpu.f |= z80.FC
        elif pc == FW_CAS_CLOSE:
            cpu.f |= z80.FC
        elif pc in FW_NADA or pc in MUSICA:
            pass
        else:
            raise RuntimeError('llamada al firmware sin imitar: &%04X' % pc)
        cpu.pc = cpu.pop()

    def corre(self, hasta, tope=60000000):
        """Ejecuta hasta que `hasta()` diga basta. Devuelve False si se agota."""
        cpu, fw = self.cpu, self.fw
        pinta = self.sym['pinta_pic']
        n = 0
        while n < tope:
            pc = cpu.pc
            if pc in fw:
                self.firmware(cpu, pc)
            elif pc == pinta:
                self.pant.tapa(8)          # la imagen tapa las 8 filas de arriba
                cpu.step()
            elif 0xB900 <= pc < 0xBE00:
                raise RuntimeError('llamada al firmware sin imitar: &%04X' % pc)
            else:
                cpu.step()
            n += 1
            if hasta():
                return True
        return False

    def arranca(self):
        self.mem = bytearray(65536)
        self.bancos = {c: bytes(0x4000) for c in (0xC0, 0xC4, 0xC5, 0xC6, 0xC7)}
        self.cfg = 0xC0
        self.pant = Pantalla(self.acentos)
        self.tintas = [1, 24, 20, 6] + [0] * 12
        self.borde = 1
        self.modo = 1
        self.cola = []
        self.ocioso = 0
        self.esperando = False
        self.cargas = []
        self.abierto = None
        inicio = self.basic()
        if inicio is None:
            raise RuntimeError('el cargador no llega a arrancar el juego: %s'
                               % ' / '.join(self.impreso))
        cpu = z80.Z80(self.mem)
        cpu.sp = 0xBFF0
        cpu.pc = inicio
        for p in range(0x7FC0, 0x7FC8):
            cpu.hook_out[p] = lambda c, port, v: self.pagina(v)
        self.cpu = cpu
        self.fw = set((FW_TXT_OUTPUT, FW_KM_WAIT, FW_KM_READ, FW_TXT_WIN,
                       FW_TXT_GETWIN, FW_TXT_GETCUR, FW_KM_RETURN, FW_CAS_OPEN, FW_CAS_CLOSE, FW_CAS_DIRECT,
                       FW_SCR_MODE, FW_SCR_INK, FW_SCR_BORDER) + FW_NADA + MUSICA)
        self.fin = self.sym.get('gameover', 0xFFFE)
        self._acabado = False
        rl = self.sym['read_line']
        if not self.corre(lambda: cpu.pc == rl, tope=20000000):
            raise RuntimeError('el juego no llego a pedir orden al arrancar')
        self.mira_imagen()
        return self

    def escribe(self, orden):
        texto = self.tecleable(orden)
        if not texto and orden != '':
            raise ValueError('orden vacia o no tecleable: %r' % orden)
        if self._acabado:
            return self.pantalla()
        cpu = self.cpu
        rl = self.sym['read_line']
        self.cola = list(texto) + ['\r']
        self.ocioso = 0
        self.esperando = False
        self.n_cargas = len(self.cargas)

        def basta():
            return cpu.pc == self.fin or (cpu.pc == rl and not self.cola)
        # se esta parado en la entrada de read_line: la primera instruccion,
        # fuera, para que esa misma entrada no cuente como la siguiente orden
        cpu.step()
        if not self.corre(basta):
            raise RuntimeError('se colgo escribiendo: %s' % orden)
        if cpu.pc == self.fin or self.mem[self.sym['quitf']]:
            self._acabado = True
        self.mira_imagen()
        return self.pantalla()

    def pantalla(self):
        return [l for l in self.pant.lineas() if l.strip()]

    # ---- la imagen de arriba ----
    def mira_imagen(self):
        """Si la sala tiene imagen y no esta a oscuras, lo que hay en las 64
        lineas de arriba tiene que ser exactamente esa imagen (y en Modo 1,
        con sus tintas)."""
        sala = self.mem[self.sym['curloc']]
        esp = self.esperada.get(sala)
        if esp is None or self.modo != self.modo_juego:
            return
        if self.pant.w[2] != 8:
            return                      # a oscuras, o una SCR encima
        if any(n.startswith('SCR') for n in self.cargas[getattr(self, 'n_cargas', 0):]):
            return                      # un SCR de 8 filas pintado encima
        lscr = self.sym.get('locscr')
        if lscr is not None and self.mem[lscr + sala] != 255:
            return
        raw, t23 = esp
        vista = png2cpc.lineal(self.mem[0xC000:0x10000], cn.IMG_LINEAS)
        if vista != raw:
            self.fallos_imagen.append('sala %s: la imagen no coincide' % self.locs[sala])
        elif self.modo_juego == 1 and tuple(self.tintas[2:4]) != tuple(t23):
            self.fallos_imagen.append('sala %s: tintas %r, esperaba %r'
                                      % (self.locs[sala], self.tintas[2:4], t23))
        if self.png and sala not in self.salas_vistas:
            os.makedirs(self.png, exist_ok=True)
            self.captura(os.path.join(self.png, '%02d_%s.png'
                                      % (sala, self.locs[sala].lstrip('@'))))
        self.salas_vistas.add(sala)

    def captura(self, ruta):
        """La pantalla entera como PNG (Modo 1 o 2, con las tintas puestas)."""
        from PIL import Image
        scr = self.mem[0xC000:0x10000]
        fw = png2cpc.CPC_FW
        if self.modo == 2:
            im = Image.new('RGB', (640, 200))
            p = im.load()
            for y in range(200):
                for xb in range(80):
                    v = scr[(y % 8) * 0x800 + (y // 8) * 80 + xb]
                    for k in range(8):
                        p[xb * 8 + k, y] = fw[self.tintas[(v >> (7 - k)) & 1]]
        else:
            im = Image.new('RGB', (320, 200))
            p = im.load()
            for y in range(200):
                for xb in range(80):
                    v = scr[(y % 8) * 0x800 + (y // 8) * 80 + xb]
                    for k in range(4):
                        c = ((v >> (7 - k)) & 1) | (((v >> (3 - k)) & 1) << 1)
                        p[xb * 4 + k, y] = fw[self.tintas[c]]
            im = im.resize((640, 400))
        im.save(ruta)


def cabecera_ascii(f):
    """El cargador va en ASCII y sin cabecera; el disco lo rellena a 128."""
    return f.split(b'\x1a')[0].rstrip(b'\x00').decode('ascii').replace('\r', '')


def trocea(linea):
    """Las sentencias de una linea de BASIC (los ':' de dentro de "" no parten)."""
    out, cur, dentro = [], '', False
    for ch in linea:
        if ch == '"':
            dentro = not dentro
        if ch == ':' and not dentro:
            out.append(cur)
            cur = ''
        else:
            cur += ch
    out.append(cur)
    return out


def main():
    argv = sys.argv[1:]
    modo = 1
    png = None
    if '--modo' in argv:
        modo = int(argv[argv.index('--modo') + 1])
    if '--png' in argv:
        png = argv[argv.index('--png') + 1]
    sueltos = [a for i, a in enumerate(argv) if not a.startswith('-')
               and (i == 0 or argv[i - 1] not in ('--modo', '--png'))]
    if len(sueltos) < 2:
        print(__doc__)
        sys.exit(2)
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    juego = JuegoCPC(sueltos[0], modo=modo, sin_ram_extra='--464' in argv, png=png)
    i = juego.info
    print('juego      %s -> Modo %d, %d bloques de disco, texto en bancos: %s'
          % (os.path.basename(sueltos[0]), modo, i['dsk_bloques'],
             i['bancos_texto'] or 'no'))
    print('bateria    %s\n' % os.path.basename(sueltos[1]))
    sys.stdout.flush()
    t0 = time.time()
    res = pj.corre(juego, sueltos[1], nivel)
    tardado = time.time() - t0
    fallos = [(n, d) for n, ok, d in res if ok is False]
    pruebas = sum(1 for _, ok, _ in res if ok is None)
    print()
    if not nivel:
        anterior = None
        for nombre, detalle in fallos:
            if nombre != anterior:
                print('=== %s' % nombre)
                anterior = nombre
            print('        FALLA %s' % detalle)
    for f in juego.fallos_imagen:
        print('IMAGEN     %s' % f)
    if juego.pant.raros:
        print('codigos de control sin imitar: %s' % sorted(juego.pant.raros))
    comprobaciones = len(res) - pruebas
    print('%d prueba(s)%s, %s, %d sala(s) con imagen comprobadas  (%.0fs)'
          % (pruebas,
             ', %d comprobacion(es)' % comprobaciones if comprobaciones else '',
             '%d fallo(s)' % len(fallos) if fallos else 'todo correcto',
             len(juego.salas_vistas), tardado))
    sys.exit(1 if fallos or juego.fallos_imagen else 0)


if __name__ == '__main__':
    main()
