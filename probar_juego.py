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
    * 40 ESPERAR                repite una orden 40 veces (dejar pasar turnos)
    << fichero                  mete las ordenes de otro fichero (un walkthrough)

Las comprobaciones miran el estado de DESPUES de la ultima orden. El texto se
busca sin distinguir mayusculas y con los espacios normalizados, porque en
pantalla viene partido en lineas de 42 columnas.

    python probar_juego.py juego.yaml pruebas.pru [-v | -vv]

Con -v se va contando la partida orden a orden (donde acaba el jugador, la
puntuacion y el final de la pantalla) y cada comprobacion con su ok o su fallo;
con -vv, ademas, la pantalla entera despues de cada orden.
"""
import io
import os
import re
import sys
import tempfile
import unicodedata
import time

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
    """Para comparar texto: sin mayusculas, sin acentos y con un solo espacio.
    Lo de los acentos no es pereza: en pantalla salen como codigos propios de
    la fuente del juego, y obligar a escribirlos en el .pru solo sirve para que
    una prueba falle por una tilde."""
    t = unicodedata.normalize('NFD', ' '.join(str(t).split()).lower())
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn')


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


def corre(juego, path_pru, nivel=0, salida=None):
    """Ejecuta un fichero de pruebas. Devuelve [(prueba, ok, detalle), ...].

    nivel 0 = callado (al final se listan los fallos), 1 = cuenta cada orden y
    cada comprobacion segun pasan, 2 = ademas la pantalla entera tras la orden.
    """
    out = salida or sys.stdout

    def di(s):
        if nivel:
            out.write(s + '\n')
            out.flush()

    base = os.path.dirname(os.path.abspath(path_pru))
    res = []
    nombre = '(sin nombre)'
    activa = False
    ultima = ''
    n = 0

    def falla(txt):
        res.append((nombre, False, txt))
        di('        FALLA %s' % txt)

    def bien(txt):
        di('        ok    %s' % txt)

    def cuenta(orden):
        """Una linea por orden: donde acaba el jugador, puntos y la respuesta."""
        if not nivel:
            return
        etiqueta = ('  .  %s' % orden) if orden.startswith('(') else ('%3d. %s' % (n, orden))
        estado = juego.donde().ljust(16)
        try:
            estado += ' puntos=%-3d' % juego.var('PUNTOS')
        except KeyError:
            pass
        # el final de la pantalla, que es donde esta la respuesta a esta orden
        t = ' '.join(' '.join(juego.pantalla()[-3:]).replace('>', ' ').split())
        di('%s %s %s' % (etiqueta.ljust(31)[:31], estado,
                         ('...' + t[-67:]) if len(t) > 70 else t))
        if nivel >= 2:
            for linea in juego.pantalla():
                di('          | %s' % linea.rstrip())

    def mete(orden):
        nonlocal ultima, n
        ultima = orden
        n += 1
        juego.escribe(orden)
        cuenta(orden)

    for cruda in io.open(path_pru, encoding='utf-8'):
        linea = cruda.rstrip('\n').strip()
        if not linea or linea.startswith('#'):
            continue
        if linea.startswith('==='):
            nombre = linea.lstrip('= ').strip() or '(sin nombre)'
            juego.arranca()
            activa = True
            n = 0
            ultima = ''
            res.append((nombre, None, 'inicio'))
            di('=== %s' % nombre)
            cuenta('(arranque)')
            continue
        if not activa:
            juego.arranca()
            activa = True
            n = 0
            cuenta('(arranque)')
        try:
            if linea.startswith('*'):
                # '* 40 ESPERAR' repite una orden 40 veces. Dejar pasar
                # turnos es lo que mas se repite en una bateria, y el
                # guion viaja DENTRO del .nex: conviene que ocupe poco.
                m = re.match(r'\*\s*(\d+)\s+(.+)', linea)
                if not m:
                    raise ValueError('no entiendo la repeticion: %s' % linea)
                for _ in range(int(m.group(1))):
                    mete(m.group(2).strip())
            elif linea.startswith('<<'):
                # "<< fichero" mete todas las ordenes; "<< fichero : 21" solo las
                # 21 primeras, que sirve para dejar la partida en un punto
                # concreto sin repetir medio walkthrough en cada prueba.
                arg = linea[2:].strip()
                tope = None
                if ':' in arg:
                    arg, _, cuantas = arg.rpartition(':')
                    arg, tope = arg.strip(), int(cuantas)
                for o in ordenes_de(os.path.join(base, arg))[:tope]:
                    mete(o)
            elif linea.startswith('!?'):
                busca = _norm(linea[2:])
                if busca in juego.texto():
                    falla('!? %s   -> sale y no deberia (tras "%s")'
                          % (linea[2:].strip(), ultima))
                else:
                    bien('!? %s' % linea[2:].strip())
            elif linea.startswith('?'):
                busca = _norm(linea[1:])
                if busca not in juego.texto():
                    falla('? %s   -> no sale (tras "%s")' % (linea[1:].strip(), ultima))
                else:
                    bien('? %s' % linea[1:].strip())
            elif linea.startswith('$'):
                m = re.match(r'\$\s*(\w+)\s*(=|==|<>|!=|>=|<=|>|<)\s*(\d+)', linea)
                if not m:
                    falla('no entiendo la comprobacion: %s' % linea)
                    continue
                v = juego.var(m.group(1))
                if not CMP[m.group(2)](v, int(m.group(3))):
                    falla('$ %s %s %s   -> vale %d (tras "%s")'
                          % (m.group(1), m.group(2), m.group(3), v, ultima))
                else:
                    bien('$ %s %s %s' % (m.group(1), m.group(2), m.group(3)))
            elif linea.startswith('%'):
                m = re.match(r'%\s*(\S+)\s*(=|==|<>|!=)\s*(\S+)', linea)
                if not m:
                    falla('no entiendo la comprobacion: %s' % linea)
                    continue
                esta = juego.donde_obj(m.group(1))
                igual = esta.upper() == m.group(3).upper()
                if (m.group(2) in ('=', '==')) != igual:
                    falla('%% %s %s %s   -> esta en %s (tras "%s")'
                          % (m.group(1), m.group(2), m.group(3), esta, ultima))
                else:
                    bien('%% %s %s %s' % (m.group(1), m.group(2), m.group(3)))
            elif linea.startswith('@'):
                esperada = linea[1:].strip()
                if juego.donde() != esperada:
                    falla('@ %s   -> esta en %s (tras "%s")'
                          % (esperada, juego.donde(), ultima))
                else:
                    bien('@ %s' % esperada)
            else:
                mete(linea)
        except Exception as e:
            falla('%s: %s' % (type(e).__name__, e))
    return res


def main():
    argv = sys.argv[1:]
    sueltos = [a for a in argv if not a.startswith('-')]
    if len(sueltos) < 2:
        print(__doc__)
        sys.exit(2)
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    juego = Juego(sueltos[0])
    print('juego      %s -> %d localizaciones, %d objetos, %d imagenes'
          % (os.path.basename(sueltos[0]), juego.info['localizaciones'],
             juego.info['objetos'], len(juego.info['imagenes'])))
    print('bateria    %s\n' % os.path.basename(sueltos[1]))
    sys.stdout.flush()
    t0 = time.time()
    res = corre(juego, sueltos[1], nivel)
    tardado = time.time() - t0

    fallos = [(n, d) for n, ok, d in res if ok is False]
    pruebas = sum(1 for _, ok, _ in res if ok is None)
    comprobadas = len(res) - pruebas
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
