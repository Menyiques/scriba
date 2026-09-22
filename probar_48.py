# -*- coding: utf-8 -*-
"""
probar_48.py - La bateria .pru, jugada sobre el binario de ZX Spectrum 48K.

Mismo fichero .pru y mismo juez que probar_juego.py; lo unico que cambia es el
binario que se mete en el simulador: en vez de un .nex con sus bancos, los 64K
planos de un 48K con el motor nativo en &6000 y ni una instruccion Z80N.

    python probar_48.py juego.yaml bateria.pru [-v|-vv]
"""
import io
import os
import sys
import time

import yaml

import probar_juego as pj
import spectrum48_nativo as s48
import spectrum_export as sx
import verify_next as vn
import z80


class Juego48(pj.Juego):
    """Un juego compilado al 48K nativo y listo para jugarse en el simulador."""

    def __init__(self, yaml_path, tap=None):
        self.game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
        code, db, sym, spec, dbaddr = s48.compila(
            self.game, ancho=vn.ANCHO, org=s48.ORG,
            game_dir=os.path.dirname(os.path.abspath(yaml_path)))
        self.code, self.db, self.dbaddr = code, db, dbaddr
        self.sym = sym
        self.info = {'localizaciones': len(spec['locations']),
                     'objetos': len(spec['objects']),
                     'imagenes': [],
                     'codigo': len(code), 'datos': len(db),
                     'total': len(code) + len(db),
                     'libre': s48.SP48 - (s48.ORG + len(code) + len(db))}
        if tap:
            with open(tap, 'wb') as f:
                f.write(s48.tap(code + db, org=s48.ORG))
        c = sx.recolecta(self.game)
        self.vars = {k.upper(): i for i, k in enumerate(c.vars.keys())}
        self.locs = list(c.locids)
        self.objs = {n.upper(): i for i, n in enumerate(
            n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
        self.cpu = self.mem = self.tec = None

    def arranca(self):
        """Monta los 64K, arranca en &6000 igual que haria el RANDOMIZE USR del
        cargador, y deja el juego pidiendo orden."""
        mem = bytearray(65536)
        mem[s48.ORG:s48.ORG + len(self.code)] = self.code
        mem[self.dbaddr:self.dbaddr + len(self.db)] = self.db
        cpu = z80.Z80(mem)
        cpu.sp = s48.SP48
        tec = vn.Teclado(cpu, mem, self.sym)
        cpu.pc = s48.ORG
        self.cpu, self.mem, self.tec = cpu, mem, tec
        self.marca_fin(s48.SP48)     # el motor hace 'ld sp,S48SP' al arrancar
        soltar = False
        n = 0
        while n < 8000000 and cpu.pc != self.sym['read_line']:
            if cpu.pc == self.sym['kmread']:
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
    juego = Juego48(sueltos[0])
    i = juego.info
    print('juego      %s -> %d localizaciones, %d objetos'
          % (os.path.basename(sueltos[0]), i['localizaciones'], i['objetos']))
    print('binario    motor %d + datos %d = %d bytes, %d libres bajo &%04X'
          % (i['codigo'], i['datos'], i['total'], i['libre'], s48.SP48))
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
