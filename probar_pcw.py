# -*- coding: utf-8 -*-
"""
probar_pcw.py - La bateria .pru, jugada sobre el disco de Amstrad PCW.

Mismo fichero .pru y mismo juez que probar_juego.py, sin emulador: el motor y
la base de datos del disco corren en el simulador Z80 (z80.py) con la memoria
del PCW imitada en Python -- bloques de 16K paginados por &F0-&F3, el teclado
mapeado en &FFF0, el reloj de &F4 -- y la pantalla se lee de su memoria de
verdad, fila a fila por ROWADR, igual que la dibuja el roller-RAM.

Lo que NO prueba es el sector de arranque (la lectura del disco por el
uPD765): el juego se monta en los bloques tal como los deja el cargador. Eso
se prueba en un emulador (JOYCE: xjoyce -a juego.dsk).

    python probar_pcw.py juego.yaml bateria.pru [-v|-vv] [--8512]

Con --8512, el juego de los dos discos (el que lleva en la B de 720K todo lo
que no cabe en 180K, portada incluida).
"""
import io
import os
import sys
import time

import yaml

import game_engine as ge
import pcw_nativo as pn
import probar_juego as pj
import spectrum_export as sx
import verify_next as vn
import z80

BLOQUE = 16384


class MemoriaPCW:
    """Los bloques de 16K del PCW sobre la memoria plana del simulador. Al
    cambiar lo que hay en una pagina se guarda lo que habia (es RAM: la
    pantalla se escribe) y se trae el bloque nuevo."""

    def __init__(self, cpu, mem, bloques):
        self.mem = mem
        self.bloques = bloques            # {n: bytearray(16384)}
        self.puesto = [0, 1, 2, 3]
        for pag in range(4):
            mem[pag * BLOQUE:(pag + 1) * BLOQUE] = self._bloque(pag)
        for p in (0xF0, 0xF1, 0xF2, 0xF3):
            cpu.hook_out[p] = self._out
        cpu.hook_in[0xF4] = lambda cpu, port: 6     # seis ticks: un barrido
        cpu.hook_in[0xF8] = lambda cpu, port: 0x40
        for p in (0xF5, 0xF6, 0xF7, 0xF8):
            cpu.hook_out[p] = lambda cpu, port, val: None

    def _bloque(self, n):
        if n not in self.bloques:
            self.bloques[n] = bytearray(BLOQUE)
        return self.bloques[n]

    def _out(self, cpu, port, val):
        pag = (port & 0xFF) - 0xF0
        n = val & 0x7F if val & 0x80 else val & 7
        if self.puesto[pag] == n:
            return
        a = pag * BLOQUE
        self._bloque(self.puesto[pag])[:] = self.mem[a:a + BLOQUE]
        self.mem[a:a + BLOQUE] = self._bloque(n)
        self.puesto[pag] = n

    def lee(self, bloque, off, n):
        """Lo que hay en un bloque, este puesto o no."""
        for pag in range(4):
            if self.puesto[pag] == bloque:
                a = pag * BLOQUE + off
                return bytes(self.mem[a:a + n])
        return bytes(self._bloque(bloque)[off:off + n])


class TecladoPCW:
    """Pulsa teclas en el mapa de &FFF2-&FFFA como lo haria el teclado."""

    def __init__(self, mem, sym):
        self.mem = mem
        tabla = mem[sym['keytab']:sym['keytab'] + 72]
        self.pos = {}
        for i, c in enumerate(tabla):
            if c and c not in self.pos:
                self.pos[c] = divmod(i, 8)

    def pulsa(self, ch):
        self.suelta()
        c = ord(ch) if isinstance(ch, str) else ch
        byte, bit = self.pos[c]
        self.mem[0xFFF2 + byte] |= 1 << bit

    def suelta(self):
        for i in range(0xFFF0, 0xFFFB):
            self.mem[i] = 0


class JuegoPCW(pj.Juego):
    maquina = 'pcw'

    def __init__(self, yaml_path, modelo='8256'):
        self.game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
        import presupuesto
        presupuesto.empieza()
        self.raiz = os.path.dirname(os.path.abspath(yaml_path))
        _dsk, info = pn.compila(self.game, game_dir=self.raiz, modelo=modelo)
        self.sym = info['sym']
        self.flujo, self.imgoff = info['flujo'], info['imgoff']
        self.info = {'localizaciones': info['localizaciones'],
                     'objetos': info['objetos'], 'imagenes': info['imagenes'],
                     'codigo': info['codigo'], 'datos': info['datos'],
                     'total': info['codigo'] + info['datos'],
                     'libre': info['libre']}
        c = sx.recolecta(self.game)
        self.vars = {k.upper(): i for i, k in enumerate(c.vars.keys())}
        self.locs = list(c.locids)
        self.objs = {n.upper(): i for i, n in enumerate(
            n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
        self.cpu = self.mem = self.tec = None

    def arranca(self):
        """Los bloques como los deja el cargador: el flujo del disco desde el
        bloque 4 y el motor en &8000 (bloques 2 y 3)."""
        bloques = {}
        for k in range(0, self.imgoff, BLOQUE):
            b = bytearray(self.flujo[k:k + BLOQUE]).ljust(BLOQUE, b'\x00')
            bloques[pn.BLK0 + k // BLOQUE] = b
        imagen = self.flujo[self.imgoff:]
        plano = bytearray(2 * BLOQUE)
        plano[:len(imagen)] = imagen
        bloques[2] = plano[:BLOQUE]
        bloques[3] = plano[BLOQUE:]
        mem = bytearray(65536)
        cpu = z80.Z80(mem)
        self.pcw = MemoriaPCW(cpu, mem, bloques)
        cpu.sp = pn.SPPCW
        tec = TecladoPCW(mem, self.sym)
        tec.suelta()
        cpu.pc = self.sym['start']
        self.cpu, self.mem, self.tec = cpu, mem, tec
        self.marca_fin(pn.SPPCW - 2)
        soltar = False
        n = 0
        while n < 20000000 and cpu.pc != self.sym['read_line']:
            if cpu.pc in (self.sym['kmread'], self.sym.get('nxscan')):
                if soltar:
                    tec.suelta()
                    soltar = False
                else:
                    tec.pulsa(' ')
                    soltar = True
            cpu.step()
            n += 1
        tec.suelta()
        if cpu.pc != self.sym['read_line']:
            raise RuntimeError('el juego no llego a pedir orden al arrancar')
        return self

    def tecleable(self, orden):
        return ''.join(c for c in pj.Juego.tecleable(self, orden)
                       if ord(c) in self.tec.pos or c == ' ')

    def escribe(self, orden):
        texto = self.tecleable(orden)
        if not texto and orden != '':
            raise ValueError('orden vacia o no tecleable: %r' % orden)
        if getattr(self, '_acabado', False):
            return self.pantalla()
        if not vn.teclea(self.cpu, self.sym, self.tec, texto + chr(13),
                         tope=60000000, fin=self.fin):
            if self.cpu.pc == self.fin or self.mem[self.sym['quitf']]:
                self._acabado = True
                return self.pantalla()
            raise RuntimeError('se colgo escribiendo: %s' % orden)
        return self.pantalla()

    def _glifos(self):
        if getattr(self, '_tg', None) is None:
            t = {}
            base = self.sym['nxfont']
            acc = sx._ACC_CODE_PT if sx._PT_LANG else sx._ACC_CODE
            por_codigo = {code: ch for ch, code in acc.items()}
            for i in range(112):
                g = bytes(b & 0xFC for b in self.mem[base + i * 8:base + i * 8 + 8])
                ch = chr(32 + i) if i < 96 else por_codigo.get(144 + i - 96, '?')
                t.setdefault(g, ch)
            t[bytes(8)] = ' '
            self._tg = t
        return self._tg

    def pantalla(self):
        """Las 32 filas de texto, leidas de la memoria de pantalla."""
        glifos = self._glifos()
        mem = self.mem
        ra = self.sym['rowadr']
        lineas = []
        for fila in range(pn.FILAS):
            d = mem[ra + 2 * fila] | (mem[ra + 2 * fila + 1] << 8)
            bloque, off = (pn.S0, d) if d < 0x4000 else (pn.S1, d - 0x4000)
            datos = self.pcw.lee(bloque, off, pn.FILA_BYTES)
            out = []
            for col in range(pn.COLS):
                celda = datos[col * 8:col * 8 + 8]
                g = bytes((b << 1) & 0xFC for b in celda)
                ch = glifos.get(g)
                if ch is None:
                    ch = glifos.get(bytes((~b << 1) & 0xFC for b in celda), '?')
                out.append(ch)
            linea = ''.join(out).rstrip()
            if linea.strip() and linea.count('?') < len(linea.strip()) // 2:
                lineas.append(linea)
        return lineas


def main():
    argv = sys.argv[1:]
    sueltos = [a for a in argv if not a.startswith('-')]
    if len(sueltos) < 2:
        print(__doc__)
        sys.exit(2)
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    juego = JuegoPCW(sueltos[0], modelo='8512' if '--8512' in argv else '8256')
    i = juego.info
    print('juego      %s -> %d localizaciones, %d objetos, %d imagenes'
          % (os.path.basename(sueltos[0]), i['localizaciones'], i['objetos'],
             len(i['imagenes'])))
    print('binario    motor %d + datos %d = %d bytes, %d libres bajo la pila'
          % (i['codigo'], i['datos'], i['total'], i['libre']))
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
        if fallos:
            print()
    comprobaciones = len(res) - pruebas
    print('%d prueba(s)%s, %s  (%.0fs)'
          % (pruebas,
             ', %d comprobacion(es)' % comprobaciones if comprobaciones else '',
             '%d fallo(s)' % len(fallos) if fallos else 'todo correcto',
             tardado))
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
