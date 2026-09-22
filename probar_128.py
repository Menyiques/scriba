# -*- coding: utf-8 -*-
"""
probar_128.py - La bateria .pru, jugada sobre el binario de ZX Spectrum 128K.

Mismo fichero .pru y mismo juez que probar_48.py; lo que cambia es la maquina:
los 64K planos llevan ademas los cinco bancos conmutables con las imagenes, y
el puerto &7FFD los trae y los lleva de &C000 a &FFFF.

    python probar_128.py juego.yaml bateria.pru [-v|-vv]
"""
import io
import os
import sys
import time

import yaml

import probar_juego as pj
import spectrum128_nativo as s128
import spectrum_export as sx
import verify_128 as v128
import verify_next as vn
import z80


class Juego128(pj.Juego):
    """Un juego compilado al 128K nativo y listo para jugarse en el simulador."""

    def __init__(self, yaml_path, tap=None):
        self.game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
        raiz = os.path.dirname(os.path.abspath(yaml_path))
        (code, db, sym, spec, dbaddr, payload, avisos,
         npsg, psg_nom) = s128.compila(self.game, raiz, ancho=vn.ANCHO)
        self.code, self.db, self.dbaddr = code, db, dbaddr
        self.payload, self.sym = payload, sym
        self.info = {'localizaciones': len(spec['locations']),
                     'objetos': len(spec['objects']),
                     'imagenes': [],
                     'codigo': len(code), 'datos': len(db),
                     'total': len(code) + len(db),
                     'libre': s128.SP128 - (s128.ORG + len(code) + len(db)),
                     'payload': len(payload),
                     'bancos': (len(payload) + 16383) // 16384,
                     'avisos': avisos}
        if tap:
            with open(tap, 'wb') as f:
                f.write(s128.tap(code + db, payload, org=s128.ORG))
        c = sx.recolecta(self.game)
        self.vars = {k.upper(): i for i, k in enumerate(c.vars.keys())}
        self.locs = list(c.locids)
        self.objs = {n.upper(): i for i, n in enumerate(
            n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
        self.cpu = self.mem = self.tec = None

    def arranca(self):
        mem = bytearray(65536)
        mem[s128.ORG:s128.ORG + len(self.code)] = self.code
        mem[self.dbaddr:self.dbaddr + len(self.db)] = self.db
        cpu = z80.Z80(mem)
        cpu.sp = s128.SP128
        self.bancos = v128.Bancos(cpu, mem, self.payload)
        tec = vn.Teclado(cpu, mem, self.sym)
        cpu.pc = s128.ORG
        self.cpu, self.mem, self.tec = cpu, mem, tec
        self.marca_fin(s128.SP128)
        # La portada no espera en KMREAD: tiene su propio bucle de barrido
        # (s128frm) mientras suena la musica, asi que hay que teclear ahi
        # tambien o el arnes se queda mirando la pantalla de titulo.
        fr = self.sym.get('s128frm')
        soltar = False
        n = 0
        while n < 8000000 and cpu.pc != self.sym['read_line']:
            if cpu.pc == self.sym['kmread'] or (fr is not None and cpu.pc == fr):
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


def main():
    argv = sys.argv[1:]
    sueltos = [a for a in argv if not a.startswith('-')]
    if len(sueltos) < 2:
        print(__doc__)
        sys.exit(2)
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    juego = Juego128(sueltos[0])
    i = juego.info
    print('juego      %s -> %d localizaciones, %d objetos'
          % (os.path.basename(sueltos[0]), i['localizaciones'], i['objetos']))
    print('binario    motor %d + datos %d = %d bytes, %d libres bajo &%04X'
          % (i['codigo'], i['datos'], i['total'], i['libre'], s128.SP128))
    print('imagenes   %d bytes en %d banco(s), %d libres de %d'
          % (i['payload'], i['bancos'], s128.TOPE_BANCOS - i['payload'],
             s128.TOPE_BANCOS))
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
    print('%d prueba(s), %s  (%.0fs)'
          % (pruebas, '%d fallo(s)' % len(fallos) if fallos else 'todo correcto',
             tardado))
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
