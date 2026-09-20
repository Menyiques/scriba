# -*- coding: utf-8 -*-
"""
probar_juego.py - Bateria de pruebas de una aventura sobre el .nex REAL.

No hace falta emulador. Compila el juego con el motor nativo, arranca el .nex
dentro del simulador Z80 (z80.py), teclea ordenes como un jugador y comprueba
lo que sale: el texto de la pantalla, decodificado de los pixeles, y el estado
interno del motor (variables y localizacion actual). Cada prueba parte de un
arranque limpio, asi que no se contaminan entre si.

Formato del fichero de pruebas (.pru), una cosa por linea:

    === nombre de la prueba     empieza una prueba nueva (reinicia el juego)
    # comentario                se ignora
    MIRAR                       una orden, tal cual la escribiria el jugador
    ? texto                     la pantalla DEBE contener ese texto
    !? texto                    la pantalla NO debe contenerlo
    $ PUNTOS = 110              una variable del juego (=, <>, >, <, >=, <=)
    @ @playa                    el jugador debe estar en esa localizacion
    % #linterna = INVEN         donde tiene que estar un objeto: una
                                localizacion (@sala), INVEN, PUESTO, NADA o un
                                contenedor (#objeto)
    << fichero                  mete las ordenes de otro fichero (un walkthrough)

Las comprobaciones miran el estado de DESPUES de la ultima orden. El texto se
busca sin distinguir mayusculas y con los espacios normalizados, porque en
pantalla viene partido en lineas de 42 columnas.

    python probar_juego.py juego.yaml pruebas.pru
"""
import io
import os
import re
import sys
import tempfile

import yaml

import game_engine as ge
import next_nativo as nn
import spectrum_export as sx
import verify_next as vn
import z80

CMP = {'=': lambda a, b: a == b, '==': lambda a, b: a == b,
       '<>': lambda a, b: a != b, '!=': lambda a, b: a != b,
       '>': lambda a, b: a > b, '<': lambda a, b: a < b,
       '>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b}


def _norm(t):
    return ' '.join(str(t).split()).lower()


class Juego:
    """Un juego compilado a .nex y listo para jugarse en el simulador."""

    def __init__(self, yaml_path, nex=None):
        raiz = os.path.dirname(os.path.abspath(yaml_path))
        self.game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
        self.nex = nex or os.path.join(tempfile.gettempdir(), 'scriba_pruebas.nex')
        self.info = nn.export_nex(self.game, self.nex,
                                  datadir=os.path.join(raiz, 'temp', 'Next', 'data'),
                                  musicdir=os.path.join(raiz, 'music'))
        self.sym = self.info['simbolos']
        c = sx.recolecta(self.game)
        # las variables viven en FLAGS, en el orden en que las declara el juego
        self.vars = {k.upper(): i for i, k in enumerate(c.vars.keys())}
        self.locs = list(c.locids)
        self.objs = {n.upper(): i for i, n in enumerate(
            n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
        self.cpu = self.mem = self.tec = None

    def arranca(self):
        """Carga el .nex, pasa portada y presentacion, y deja el juego pidiendo
        orden. Cada prueba empieza aqui, con el estado recien inicializado."""
        mem, pc, sp, _, cont = nn.carga_nex(self.nex)
        cpu = z80.Z80(mem)
        cpu.sp = sp
        vn.EspiaNextReg(cpu)
        vn.Mmu(cpu, mem, cont)
        tec = vn.Teclado(cpu, mem, self.sym)
        cpu.pc = pc
        self.cpu, self.mem, self.tec = cpu, mem, tec
        fr = self.sym.get('nxframe')
        soltar = False
        n = 0
        while n < 8000000 and cpu.pc != self.sym['read_line']:
            if cpu.pc == fr or cpu.pc == self.sym['kmread']:
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

    ACENTOS = {'\u00e1': 'a', '\u00e9': 'e', '\u00ed': 'i', '\u00f3': 'o',
               '\u00fa': 'u', '\u00f1': 'n', '\u00fc': 'u', '\u00e7': 'c'}

    def tecleable(self, orden):
        """Lo que de verdad puede teclear un jugador en el Spectrum: minusculas,
        sin acentos y solo los caracteres que tiene la matriz del teclado. El
        parser del juego ya pasa a mayusculas por su cuenta."""
        out = []
        for ch in str(orden).lower():
            ch = self.ACENTOS.get(ch, ch)
            if ch in 'abcdefghijklmnopqrstuvwxyz0123456789 ':
                out.append(ch)
        return ''.join(out).strip()

    def escribe(self, orden):
        texto = self.tecleable(orden)
        if not texto:
            raise ValueError('orden vacia o no tecleable: %r' % orden)
        # margen amplio: una respuesta larga se escribe a 4 caracteres por
        # barrido y puede pararse varias veces a esperar tecla
        if not vn.teclea(self.cpu, self.sym, self.tec, texto + chr(13),
                         tope=40000000):
            raise RuntimeError('se colgo escribiendo: %s' % orden)
        return self.pantalla()

    def pantalla(self):
        return [l for l in vn.leer_pantalla(self.mem, self.sym) if l.strip()]

    def texto(self):
        return _norm(' '.join(self.pantalla()))

    def var(self, nombre):
        clave = nombre.upper().replace('_', '')
        if clave not in self.vars:
            raise KeyError('el juego no tiene la variable %s' % nombre)
        return self.mem[self.sym['flags'] + self.vars[clave]]

    def donde(self):
        i = self.mem[self.sym['curloc']]
        return self.locs[i] if i < len(self.locs) else '?'

    def donde_obj(self, nombre):
        """Donde esta un objeto, con el mismo vocabulario que el .pru:
        una localizacion, INVEN, PUESTO, NADA o '#contenedor'."""
        k = str(nombre).upper()
        if k not in self.objs:
            raise KeyError('el juego no tiene el objeto %s' % nombre)
        i = self.objs[k]
        v = self.mem[self.sym['objloc'] + i]
        if v == ge.CARRIED:
            return 'INVEN'
        if v == ge.WORN:
            return 'PUESTO'
        if v == ge.NOWHERE:
            return 'NADA'
        if v == ge.CONTAINED:
            c = self.mem[self.sym['objin'] + i] - 1
            for n, j in self.objs.items():
                if j == c:
                    return n
            return '?%d' % c
        return self.locs[v] if v < len(self.locs) else '?%d' % v


def ordenes_de(path):
    """Lee un fichero de ordenes. Admite tanto una lista pelada (una por linea)
    como un walkthrough en Markdown, del que saca los bloques ``` y les quita
    los comentarios entre parentesis, los '+5' de puntos y las flechas."""
    txt = io.open(path, encoding='utf-8').read()
    bloques = re.findall(r'```(.*?)```', txt, re.S) if '```' in txt else [txt]
    out = []
    for b in bloques:
        for linea in b.split('\n'):
            linea = linea.split('#')[0].split('(')[0]
            linea = linea.split('→')[0]                 # flecha
            linea = re.sub(r'\+\d+', '', linea).strip()
            if not linea:
                continue
            for parte in linea.split('·'):              # "SUBIR · OESTE"
                parte = parte.strip()
                if parte:
                    out.append(parte)
    return out


def corre(juego, path_pru, verboso=False):
    """Ejecuta un fichero de pruebas. Devuelve [(prueba, ok, detalle), ...]."""
    base = os.path.dirname(os.path.abspath(path_pru))
    res = []
    nombre = '(sin nombre)'
    activa = False
    ultima = ''

    def falla(txt):
        res.append((nombre, False, txt))

    for cruda in io.open(path_pru, encoding='utf-8'):
        linea = cruda.rstrip('\n').strip()
        if not linea or linea.startswith('#'):
            continue
        if linea.startswith('==='):
            nombre = linea.lstrip('= ').strip() or '(sin nombre)'
            juego.arranca()
            activa = True
            res.append((nombre, None, 'inicio'))
            continue
        if not activa:
            juego.arranca()
            activa = True
        try:
            if linea.startswith('<<'):
                # "<< fichero" mete todas las ordenes; "<< fichero : 21" solo las
                # 21 primeras, que sirve para dejar la partida en un punto
                # concreto sin repetir medio walkthrough en cada prueba.
                arg = linea[2:].strip()
                tope = None
                if ':' in arg:
                    arg, _, n = arg.rpartition(':')
                    arg, tope = arg.strip(), int(n)
                for o in ordenes_de(os.path.join(base, arg))[:tope]:
                    ultima = o
                    juego.escribe(o)
            elif linea.startswith('!?'):
                busca = _norm(linea[2:])
                if busca in juego.texto():
                    falla('sale y no deberia: "%s" (tras "%s")' % (linea[2:].strip(), ultima))
            elif linea.startswith('?'):
                busca = _norm(linea[1:])
                if busca not in juego.texto():
                    falla('no sale: "%s" (tras "%s")' % (linea[1:].strip(), ultima))
            elif linea.startswith('$'):
                m = re.match(r'\$\s*(\w+)\s*(=|==|<>|!=|>=|<=|>|<)\s*(\d+)', linea)
                if not m:
                    falla('no entiendo la comprobacion: %s' % linea)
                    continue
                v = juego.var(m.group(1))
                if not CMP[m.group(2)](v, int(m.group(3))):
                    falla('%s vale %d, no %s %s' % (m.group(1), v, m.group(2), m.group(3)))
            elif linea.startswith('%'):
                m = re.match(r'%\s*(\S+)\s*(=|==|<>|!=)\s*(\S+)', linea)
                if not m:
                    falla('no entiendo la comprobacion: %s' % linea)
                    continue
                esta = juego.donde_obj(m.group(1))
                igual = esta.upper() == m.group(3).upper()
                if (m.group(2) in ('=', '==')) != igual:
                    falla('%s esta en %s, y se esperaba %s %s'
                          % (m.group(1), esta, m.group(2), m.group(3)))
            elif linea.startswith('@'):
                esperada = linea[1:].strip()
                if juego.donde() != esperada:
                    falla('esta en %s, no en %s' % (juego.donde(), esperada))
            else:
                ultima = linea
                juego.escribe(linea)
                if verboso:
                    print('    > %s' % linea)
        except Exception as e:
            falla('%s: %s' % (type(e).__name__, e))
    return res


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    juego = Juego(sys.argv[1])
    print('%s -> %d localizaciones, %d objetos, %d imagenes'
          % (os.path.basename(sys.argv[1]), juego.info['localizaciones'],
             juego.info['objetos'], len(juego.info['imagenes'])))
    print()
    res = corre(juego, sys.argv[2], verboso='-v' in sys.argv)
    fallos = 0
    for nombre, ok, detalle in res:
        if ok is None:
            print('=== %s' % nombre)
        elif not ok:
            fallos += 1
            print('   FALLA  %s' % detalle)
    pruebas = sum(1 for _, ok, _ in res if ok is None)
    print()
    if fallos:
        print('%d prueba(s), %d fallo(s)' % (pruebas, fallos))
    else:
        print('%d prueba(s), todo correcto' % pruebas)
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
