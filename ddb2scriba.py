# -*- coding: utf-8 -*-
"""
ddb2scriba.py - Importa una base de datos DAAD (.ddb) a un juego de Scriba.

    python ddb2scriba.py juego.ddb juego.yaml [--base 0x8400] [--sin-textos]

Lo que se traduce solo:
  vocabulario, localizaciones y sus salidas, objetos (nombre, nombre de
  vocabulario, sitio inicial, peso, prenda, contenedor), mensajes, y los
  procesos: el 0 como tabla de respuestas (ON verbo nombre), el 1 como
  before_turn y el 2 como after_turn (el orden de PAWS y DAAD 1). Los
  subprocesos (PROCESS n) se copian en linea donde se llaman, con una
  variable de "hecho" por nivel para respetar DONE.

Lo que no tiene equivalente en Scriba (ventanas, graficos, PARSE, DOALL,
indireccion @flag, SAVE/LOAD...) queda como REM en el sitio, y el informe
dice cuantos hay y de que tipo, para rematarlo a mano.

--sin-textos sustituye todos los textos por marcadores ([LOC 3], [MSG 12]...):
sirve para probar la traduccion de la logica sin copiar el contenido.
"""
import io
import sys

import yaml

import daad_ddb

DIRS = {'N': ('NORTE', 'N'), 'S': ('SUR', 'S'), 'E': ('ESTE', 'E'),
        'O': ('OESTE', 'O', 'W', 'WEST'), 'U': ('SUBIR', 'ARRIB', 'SUBE', 'U', 'SUBO'),
        'D': ('BAJAR', 'ABAJO', 'BAJA', 'D', 'BAJO')}
VERBO_DIR = {'N': 'NORTE', 'S': 'SUR', 'E': 'ESTE', 'O': 'OESTE', 'U': 'ARRIB',
             'D': 'ABAJO'}
# Mensajes de sistema DAAD estandar sin huecos -> catalogo de Scriba
SISTEMA = {0: 'oscuro_ver', 6: 'no_entiendo', 7: 'no_direccion', 8: 'no_hacer',
           9: 'llevas_cab', 26: 'no_ves_eso', 28: 'no_llevas_eso',
           23: 'no_puesto'}
FLAG_PUNTOS, FLAG_TURNOS, FLAG_LOC, FLAG_OSCURO = 30, 31, 38, 0


def _q(s):
    return '"%s"' % s.replace('\\', '\\\\').replace('"', "'")


class Traductor:
    def __init__(self, ddb, textos=True):
        self.x = ddb
        self.textos = textos
        self.vars = set()
        self.sin_equivalente = {}       # condact -> veces
        self.aproximados = {}
        self.ok = {}
        self.niv = 0                    # profundidad de PROCESS en linea

    # ---- nombres ----
    def loc(self, n):
        return {252: '@NOWHERE', 253: '@ONME', 254: '@INVEN'}.get(n, '@l%d' % n)

    def obj(self, n):
        return '#o%d' % n

    def flag(self, f):
        if f == FLAG_PUNTOS:
            return '_PUNTOS'
        if f == FLAG_TURNOS:
            return '_TURNOS'
        self.vars.add(f)
        return '_F%d' % f

    def palabra(self, tipo, n):
        if n == 255:
            return '_'
        p = self.x.palabras(tipo, n)
        if not p and tipo == 0 and n < 20:       # nombres convertibles
            p = self.x.palabras(2, n)
        return p[0].upper() if p else ('V%d' % n if tipo == 0 else 'N%d' % n)

    def txt(self, tipo, n):
        if not self.textos:
            return '[%s %d]' % (tipo, n)
        tabla = {'LOC': self.x.localizaciones, 'MSG': self.x.mensajes,
                 'SYS': self.x.sistema, 'OBJ': self.x.objetos_txt}[tipo]
        return tabla[n] if n < len(tabla) else ''

    def _cuenta(self, d, k):
        d[k] = d.get(k, 0) + 1

    # ---- condiciones: devuelve texto o None si no hay equivalente ----
    def cond(self, c, p):
        x = self.x
        if c == 'AT':
            return 'AT %s' % self.loc(p[0])
        if c == 'NOTAT':
            return 'NOTAT %s' % self.loc(p[0])
        if c in ('ATGT', 'ATLT'):
            locs = [i for i in range(x.nloc)
                    if (i > p[0] if c == 'ATGT' else i < p[0])]
            if not locs:
                return 'NOT AT @l0 AND AT @l0'
            self._cuenta(self.aproximados, c)
            return '(' + ' OR '.join('AT %s' % self.loc(i) for i in locs) + ')'
        if c in ('PRESENT', 'ABSENT', 'WORN', 'NOTWORN', 'CARRIED', 'NOTCARR'):
            return '%s %s' % (c, self.obj(p[0]))
        if c == 'CHANCE':
            return 'CHANCE %d' % p[0]
        if c in ('ZERO', 'NOTZERO'):
            if p[0] == FLAG_LOC:
                return None
            return '%s %s 0' % (self.flag(p[0]), '=' if c == 'ZERO' else '<>')
        if c in ('EQ', 'NOTEQ', 'GT', 'LT'):
            if p[0] == FLAG_LOC and c in ('EQ', 'NOTEQ'):
                return '%s %s' % ('AT' if c == 'EQ' else 'NOTAT', self.loc(p[1]))
            op = {'EQ': '=', 'NOTEQ': '<>', 'GT': '>', 'LT': '<'}[c]
            return '%s %s %d' % (self.flag(p[0]), op, p[1])
        if c in ('SAME', 'NOTSAME', 'BIGGER', 'SMALLER'):
            op = {'SAME': '=', 'NOTSAME': '<>', 'BIGGER': '>', 'SMALLER': '<'}[c]
            return '%s %s %s' % (self.flag(p[0]), op, self.flag(p[1]))
        if c == 'ISAT':
            return 'ISAT %s %s' % (self.obj(p[0]), self.loc(p[1]))
        if c == 'ISNOTAT':
            return 'NOT ISAT %s %s' % (self.obj(p[0]), self.loc(p[1]))
        if c == 'NOUN2':
            return 'NOUN2 %s' % self.palabra(2, p[0])
        if c == 'QUIT':                 # "¿seguro?": se da por si
            self._cuenta(self.aproximados, c)
            return ''
        return None

    # ---- acciones: lista de lineas ----
    def accion(self, c, p, fin):
        L = []
        if c == 'DESC':
            L.append('DESC')
        elif c == 'GOTO':
            L += ['GOTO %s' % self.loc(p[0])]
        elif c in ('MESSAGE', 'MES'):
            L.append('PRINT %s' % _q(self.txt('MSG', p[0])))
        elif c == 'SYSMESS':
            L.append('PRINT %s' % _q(self.txt('SYS', p[0])))
        elif c in ('GET', 'DROP', 'WEAR', 'REMOVE', 'DESTROY'):
            L.append('%s %s' % (c, self.obj(p[0])))
        elif c == 'CREATE':
            L.append('CREATE %s' % self.obj(p[0]))
        elif c == 'PLACE':
            if p[1] == 255:
                L.append('CREATE %s' % self.obj(p[0]))
            else:
                L.append('PUT %s %s' % (self.obj(p[0]), self.loc(p[1])))
        elif c == 'SWAP':
            self._cuenta(self.aproximados, c)
            L += ['REM SWAP %d %d (aproximado: el segundo sale donde estaba el primero si estaba aqui)' % tuple(p),
                  'IF PRESENT %s THEN' % self.obj(p[0]),
                  '  DESTROY %s' % self.obj(p[0]), '  CREATE %s' % self.obj(p[1]),
                  'ENDIF']
        elif c == 'SET':
            L.append('LET %s = 255' % self.flag(p[0]))
        elif c == 'CLEAR':
            L.append('LET %s = 0' % self.flag(p[0]))
        elif c in ('PLUS', 'MINUS'):
            if p[0] == FLAG_PUNTOS and c == 'PLUS':
                L.append('ADDSCORE %d' % p[1])
            else:
                f = self.flag(p[0])
                L.append('LET %s = %s %s %d' % (f, f, '+' if c == 'PLUS' else '-', p[1]))
        elif c == 'LET':
            if p[0] == FLAG_LOC:
                L.append('GOTO %s' % self.loc(p[1]))
            else:
                L.append('LET %s = %d' % (self.flag(p[0]), p[1]))
        elif c in ('ADD', 'SUB'):
            a, b = self.flag(p[0]), self.flag(p[1])
            L.append('LET %s = %s %s %s' % (b, b, '+' if c == 'ADD' else '-', a))
        elif c in ('PRINT', 'DPRINT'):
            L.append('PRINT "{%s}"' % self.flag(p[0]))
        elif c == 'NEWLINE':
            L.append('NEWLINE')
        elif c == 'SPACE':
            L.append('PRINT " "')
        elif c == 'CLS':
            L.append('CLS')
        elif c in ('ANYKEY', 'PAUSE'):
            L.append('WAIT 1' if c == 'ANYKEY' else 'REM PAUSE %d' % p[0])
        elif c == 'END':
            L.append('END')
        elif c in ('DONE', 'NOTDONE'):
            L.append(fin)
        elif c == 'OK':
            L += ['PRINT %s' % _q(self.txt('SYS', 15)), fin]
        elif c == 'PUTIN':
            L.append('PUTIN %s %s' % (self.obj(p[0]), self.obj(p[1])))
        elif c == 'TAKEOUT':
            L.append('TAKEOUT %s %s' % (self.obj(p[0]), self.obj(p[1])))
        elif c in ('AUTOG', 'AUTOD', 'AUTOW', 'AUTOR'):
            L.append('REM %s: lo hace solo el motor de Scriba' % c)
            return L, 'auto'
        else:
            return None, None
        return L, None

    # ---- una entrada (lista de condacts) -> lineas, anidando condiciones ----
    def entrada(self, cs, fin, ind):
        out, abiertos, pad = [], 0, ind
        for c, indir, p in cs:
            if indir:
                self._cuenta(self.sin_equivalente, c + ' @')
                out.append(pad + 'REM %s @%s (indireccion)' % (c, p))
                continue
            if c in ('_VERB', '_NOUN'):
                out.append(pad + 'IF %s %s THEN' % (
                    'VERB' if c == '_VERB' else 'NOUN1',
                    self.palabra(0 if c == '_VERB' else 2, p[0])))
                abiertos += 1
                pad += '  '
                continue
            if c in daad_ddb.CONDICIONES:
                t = self.cond(c, p)
                if t is None:
                    self._cuenta(self.sin_equivalente, c)
                    out.append(pad + 'REM %s %s (sin equivalente; se da por cierta)'
                               % (c, ' '.join(map(str, p))))
                    continue
                self._cuenta(self.ok, c)
                if t:
                    out.append(pad + 'IF %s THEN' % t)
                    abiertos += 1
                    pad += '  '
                continue
            if c == 'PROCESS':
                self._cuenta(self.ok, c)
                out += self.subproceso(p[0], pad)
                continue
            lineas, _ = self.accion(c, p, fin)
            if lineas is None:
                self._cuenta(self.sin_equivalente, c)
                out.append(pad + 'REM %s %s' % (c, ' '.join(map(str, p))))
                continue
            self._cuenta(self.ok, c)
            out += [pad + l for l in lineas]
        for _ in range(abiertos):
            pad = pad[:-2]
            out.append(pad + 'ENDIF')
        return out

    def cabecera(self, v, n):
        conds = []
        if v != 255:
            conds.append('VERB %s' % self.palabra(0, v))
        if n != 255:
            conds.append('NOUN1 %s' % self.palabra(2, n))
        return ' AND '.join(conds)

    def subproceso(self, n, pad):
        if self.niv >= 4 or n >= len(self.x.procesos):
            self._cuenta(self.sin_equivalente, 'PROCESS (anidado)')
            return [pad + 'REM PROCESS %d (demasiado anidado)' % n]
        self.niv += 1
        h = '_H%d' % self.niv
        self.vars.add(h)
        out = [pad + 'REM -- PROCESS %d --' % n, pad + 'LET %s = 0' % h]
        for v, nn, cs in self.x.procesos[n]:
            out.append(pad + 'IF %s = 0 THEN' % h)
            cab = self.cabecera(v, nn)
            p2 = pad + '  '
            if cab:
                out.append(p2 + 'IF %s THEN' % cab)
                p2 += '  '
            out += self.entrada(cs, 'LET %s = 1' % h, p2)
            if cab:
                out.append(pad + '  ENDIF')
            out.append(pad + 'ENDIF')
        self.niv -= 1
        return out

    def hojas(self, cs, prof=0):
        """Aplana las llamadas de cola: una entrada que es "condiciones +
        PROCESS n [+ DONE]" se convierte en una hoja por cada entrada del
        subproceso, con las condiciones del padre delante. Asi cada hoja es un
        bloque pequeno (el motor nativo limita un IF a 255 bytes) y no se
        copia el subproceso entero en cada sitio que lo llama.
        Devuelve [(condacts)], donde las condiciones de verbo/nombre del
        subproceso van como pseudo-condacts _VERB/_NOUN."""
        k = len(cs)
        cola_done = k >= 2 and cs[-1][0] == 'DONE' and cs[-2][0] == 'PROCESS'
        if cola_done:
            k -= 1
        if (prof < 6 and k >= 1 and cs[k - 1][0] == 'PROCESS' and not cs[k - 1][1]
                and all(c in daad_ddb.CONDICIONES and not i for c, i, _p in cs[:k - 1])
                and cs[k - 1][2][0] < len(self.x.procesos)):
            pre = list(cs[:k - 1])
            n = cs[k - 1][2][0]
            self._cuenta(self.ok, 'PROCESS')
            out = []
            for v, nn, sub in self.x.procesos[n]:
                cab = []
                if v != 255:
                    cab.append(('_VERB', False, [v]))
                if nn != 255:
                    cab.append(('_NOUN', False, [nn]))
                for h in self.hojas(sub, prof + 1):
                    out.append(pre + cab + h)
            if cola_done:                 # nada del subproceso caso: DONE igual
                out.append(pre + [('DONE', False, [])])
            return out
        return [list(cs)]

    def tabla(self, n, como_on):
        """Proceso n: como bloques ON (respuestas) o como IFs (por turno)."""
        out = []
        if n >= len(self.x.procesos):
            return out
        if como_on:
            for v, nn, cs in self.x.procesos[n]:
                for h in self.hojas(cs):
                    out.append('ON %s %s' % (self.palabra(0, v) if v != 255 else '*',
                                             self.palabra(2, nn) if nn != 255 else '*'))
                    cuerpo = self.entrada(h, 'MATCH', '  ')
                    if any('lo hace solo el motor' in l for l in cuerpo):
                        cuerpo = [l for l in cuerpo if l.strip() != 'MATCH']
                    out += cuerpo + ['ENDON', '']
            return out
        # por turno: las entradas en orden; DONE corta el resto del proceso
        self.vars.add('_H0')
        out.append('LET _H0 = 0')
        for v, nn, cs in self.x.procesos[n]:
            for h in self.hojas(cs):
                cab = []
                if v != 255:
                    cab.append(('_VERB', False, [v]))
                if nn != 255:
                    cab.append(('_NOUN', False, [nn]))
                out.append('IF _H0 = 0 THEN')
                out += self.entrada(cab + h, 'LET _H0 = 1', '  ')
                out.append('ENDIF')
        return out

    # ---- el juego ----
    def juego(self):
        x = self.x
        # vocabulario
        verbos, nombres = {}, {}
        grupos = {}
        for pal, num, tipo in x.vocabulario:
            grupos.setdefault((tipo, num), []).append(pal)
        for (tipo, num), pals in grupos.items():
            clave = pals[0].upper()
            syn = [p.lower() for p in pals]
            if tipo == 0:
                verbos[clave] = syn
            elif tipo == 2:
                nombres[clave] = syn
                if num < 20:
                    verbos.setdefault(clave, syn)
        # direcciones -> verbos de Scriba
        def dir_de(num):
            for pal in [p.upper() for p, n, t in x.vocabulario if n == num and t in (0, 2)]:
                for d, nombres_d in DIRS.items():
                    if pal in nombres_d:
                        return d
            return None
        locs, extra = {}, []
        for i in range(x.nloc):
            texto = self.txt('LOC', i)
            nombre = texto.strip().split('\n')[0].split('.')[0][:40] if self.textos else '[LOC %d]' % i
            ex = {k: None for k in 'NSEOUD'}
            for pal, dest in x.conexiones[i]:
                d = dir_de(pal)
                if d and ex[d] is None:
                    ex[d] = self.loc(dest)
                else:
                    extra.append((self.palabra(0, pal), i, dest))
            locs[self.loc(i)] = {'name': nombre or 'Localizacion %d' % i,
                                 'description': texto, 'dark': False,
                                 'exits': ex, 'on_enter': []}
        objs = {}
        for i in range(x.nobj):
            noun, _adj = x.obj_pal[i]
            attr = x.obj_attr[i]
            objs[self.obj(i)] = {
                'name': self.txt('OBJ', i), 'noun': self.palabra(2, noun) if noun != 255 else '',
                'description': '', 'location': self.loc(x.ini[i]),
                'weight': attr & 0x3f, 'wearable': bool(attr & 0x40),
                'container': bool(attr & 0x80), 'openable': False,
                'light_source': i == 0, 'lit': i == 0, 'open': False,
                'locked': False, 'key': None, 'attributes': []}
        # logica
        resp = ['REM Importado de DAAD: proceso 0 (respuestas)', '']
        for pal, a, b in extra:
            resp += ['ON %s * *' % pal, '  IF AT %s THEN' % self.loc(a),
                     '    GOTO %s' % self.loc(b), '    DESC', '    MATCH',
                     '  ENDIF', 'ENDON', '']
        resp += self.tabla(0, True)
        antes = ['REM Importado de DAAD: proceso 1'] + self.tabla(1, False)
        despues = ['REM Importado de DAAD: proceso 2'] + self.tabla(2, False)
        variables = {'_PUNTOS': 0, '_TURNOS': 0}
        for f in sorted(v for v in self.vars if isinstance(v, int)):
            variables['_F%d' % f] = 0
        for h in sorted(v for v in self.vars if isinstance(v, str)):
            variables[h] = 0
        mensajes = {}
        if self.textos:
            for k, clave in SISTEMA.items():
                if k < len(x.sistema) and x.sistema[k].strip():
                    mensajes[clave] = x.sistema[k].strip()
        meta = {'title': 'Importado de DAAD', 'author': '', 'version': '1.0',
                'language': x.idioma if x.idioma in ('es', 'en') else 'es',
                'start_location': '@l0', 'max_score': 0, 'start_message': ''}
        if mensajes:
            meta['mensajes'] = mensajes
        return {
            'metadata': meta, 'variables': variables,
            'vocabulary': {'verbs': verbos, 'nouns': nombres, 'prepositions': {}},
            'locations': locs, 'objects': objs, 'timers': {},
            'condacts': {'on_start': 'REM importado de DAAD',
                         'responses': '\n'.join(resp),
                         'before_turn': '\n'.join(antes),
                         'after_turn': '\n'.join(despues), 'on_end': ''},
            'fx': [],
        }

    def informe(self):
        tot = lambda d: sum(d.values())
        return {
            'traducidos': tot(self.ok), 'aproximados': tot(self.aproximados),
            'sin_equivalente': tot(self.sin_equivalente),
            'detalle_aproximados': dict(sorted(self.aproximados.items(), key=lambda t: -t[1])),
            'detalle_sin_equivalente': dict(sorted(self.sin_equivalente.items(), key=lambda t: -t[1])),
            'variables': len(self.vars),
        }


def importa(ruta, base=None, textos=True):
    x = daad_ddb.lee(ruta, base)
    t = Traductor(x, textos)
    return t.juego(), t.informe(), x


def main():
    a = [s for s in sys.argv[1:] if not s.startswith('--')]
    if len(a) < 2:
        print(__doc__)
        sys.exit(2)
    base = None
    if '--base' in sys.argv:
        base = int(sys.argv[sys.argv.index('--base') + 1], 0)
    juego, inf, _x = importa(a[0], base, '--sin-textos' not in sys.argv)
    with io.open(a[1], 'w', encoding='utf-8') as f:
        yaml.safe_dump(juego, f, allow_unicode=True, sort_keys=False, width=100)
    for k, v in inf.items():
        print('%-24s %s' % (k, v))


if __name__ == '__main__':
    main()
