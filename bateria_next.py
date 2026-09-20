# -*- coding: utf-8 -*-
"""
bateria_next.py - Bateria de pruebas sobre el .nex REAL, en un emulador de Next.

Hermana de probar_juego.py. Aquella juega dentro del simulador Z80 de Python y
lee la pantalla de los pixeles; esta ejecuta el .nex en jnext
(https://github.com/jorgegv/jnext), un emulador de ZX Spectrum Next con modo
headless. Cuesta mas ponerla en marcha -- hay que tener jnext -- pero prueba lo
que de verdad se distribuye: el cargador NEX, la ROM, la MMU, Layer 2 y el Z80N,
ciclo a ciclo.

COMO FUNCIONA
El juego se compila en MODO PRUEBA (next_nativo._modo_prueba): el .nex lleva
dentro el guion de la partida, se teclea solo y copia cada caracter que imprime
a un puerto de E/S. jnext vuelca ese puerto a su salida de error
(--magic-port), o sea que una partida entera sale como texto plano: ni se leen
pixeles ni hay que adivinar cuantos barridos tarda cada cosa. El guion lleva
ademas dos bytes de control: 1 pide una foto del estado del motor (variables,
donde esta cada objeto, dentro de que contenedor, sala actual) y 2 vuelve a
empezar la partida. El .nex que se distribuye no lleva nada de esto.

FORMATO DEL FICHERO DE PRUEBAS (.pru) -- el mismo que probar_juego.py

    === nombre de la prueba     empieza una prueba nueva (reinicia el juego)
    # comentario                se ignora
    MIRAR                       una orden, tal cual la escribiria el jugador
    ? texto                     la respuesta DEBE contener ese texto
    !? texto                    NO debe contenerlo
    $ PUNTOS = 110              una variable del juego (=, <>, >, <, >=, <=)
    @ @playa                    el jugador debe estar en esa localizacion
    % #linterna = INVEN         donde tiene que estar un objeto: una
                                localizacion (@sala), INVEN, PUESTO, NADA o un
                                contenedor (#objeto)
    << fichero                  mete las ordenes de otro fichero (un walkthrough)
    << fichero : 21             solo las 21 primeras

Una comprobacion mira SIEMPRE la respuesta a la ultima orden, no la pantalla
entera: en la pantalla queda texto de ordenes anteriores y en cuanto hay
scroll deja de estar lo de arriba. El texto se busca sin distinguir mayusculas
y con los espacios normalizados, porque viene partido en lineas de 42 columnas.

USO
    python bateria_next.py juego.yaml pruebas.pru [opciones]

    -v              cuenta la partida orden a orden segun sale del emulador:
                    donde acaba el jugador, la puntuacion y el principio de la
                    respuesta, y cada comprobacion con su ok o su fallo
    -vv             ademas, la respuesta entera de cada orden
    --jnext RUTA    el emulador (si no, la variable JNEXT o el PATH)
    --sdcard FILE   imagen de tarjeta SD ya bajada (util en CI)
    --frames N      tope de barridos de emulador (por defecto se estima)
    --traza FILE    guarda la traza cruda para mirarla luego

La traza se lee SEGUN SALE del emulador, asi que con -v se ve lo que esta
pasando mientras la partida corre, no un volcado al terminar.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

import game_engine as ge
import next_nativo as nn
import spectrum_export as sx

CMP = {'=': lambda a, b: a == b, '==': lambda a, b: a == b,
       '<>': lambda a, b: a != b, '!=': lambda a, b: a != b,
       '>': lambda a, b: a > b, '<': lambda a, b: a < b,
       '>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b}

RESET = b'\x02'      # bytes de control del guion (ver _modo_prueba)
FOTO = b'\x01'

# Barridos de emulador por orden tecleada. Con la CPU a 28 MHz y sin las
# esperas decorativas una orden no pasa de un pu?ado, pero mas vale que sobre:
# si el guion se queda a medias la bateria no puede distinguirlo de un fallo.
FRAMES_POR_ORDEN = 12
FRAMES_ARRANQUE = 240


def _norm(t):
    return ' '.join(str(t).split()).lower()


def _mapa_acentos(pt):
    """Codigo que sale por el puerto -> caracter. El motor guarda los acentos
    en 144-159 y nativecc.desplaza_acentos los sube a 224-239 para que no
    choquen con los tokens de compresion."""
    tabla = sx._ACC_CODE_PT if pt else sx._ACC_CODE
    return {v + 80: k for k, v in tabla.items()}


def _tecleable(orden):
    """Lo que de verdad puede teclear un jugador en el Spectrum. El guion no
    pasa por la matriz del teclado, pero si dejaramos colar mayusculas o
    acentos estariamos probando algo que en la maquina no se puede escribir."""
    acc = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o',
           'ú': 'u', 'ñ': 'n', 'ü': 'u', 'ç': 'c'}
    out = [acc.get(ch, ch) for ch in str(orden).lower()]
    return ''.join(c for c in out
                   if c in 'abcdefghijklmnopqrstuvwxyz0123456789 ').strip()


def ordenes_de(path):
    """Lee un fichero de ordenes: una lista pelada o un walkthrough en Markdown,
    del que saca los bloques ``` y les quita comentarios, puntos y flechas."""
    txt = io.open(path, encoding='utf-8').read()
    bloques = re.findall(r'```(.*?)```', txt, re.S) if '```' in txt else [txt]
    out = []
    for b in bloques:
        for linea in b.split('\n'):
            linea = linea.split('#')[0].split('(')[0].split('→')[0]
            linea = re.sub(r'\+\d+', '', linea).strip()
            if not linea:
                continue
            for parte in linea.split('·'):
                parte = parte.strip()
                if parte:
                    out.append(parte)
    return out


# ---------------------------------------------------------------------------
#  1. el .pru -> lista de pruebas
# ---------------------------------------------------------------------------

def lee_pru(path):
    """Devuelve [(nombre, [(tipo, dato), ...]), ...].
    tipo: 'orden' | 'texto' | 'notexto' | 'var' | 'loc' | 'obj'."""
    base = os.path.dirname(os.path.abspath(path))
    pruebas = []
    actual = None

    def pon(t, d):
        if actual is None:
            raise ValueError('hay ordenes antes del primer "==="')
        actual[1].append((t, d))

    for cruda in io.open(path, encoding='utf-8'):
        linea = cruda.rstrip('\n').strip()
        if not linea or linea.startswith('#'):
            continue
        if linea.startswith('==='):
            actual = (linea.lstrip('= ').strip() or '(sin nombre)', [])
            pruebas.append(actual)
            continue
        if linea.startswith('<<'):
            arg, tope = linea[2:].strip(), None
            if ':' in arg:
                arg, _, n = arg.rpartition(':')
                arg, tope = arg.strip(), int(n)
            for o in ordenes_de(os.path.join(base, arg))[:tope]:
                pon('orden', o)
        elif linea.startswith('!?'):
            pon('notexto', linea[2:].strip())
        elif linea.startswith('?'):
            pon('texto', linea[1:].strip())
        elif linea.startswith('$'):
            m = re.match(r'\$\s*(\w+)\s*(=|==|<>|!=|>=|<=|>|<)\s*(\d+)', linea)
            if not m:
                raise ValueError('no entiendo la comprobacion: %s' % linea)
            pon('var', (m.group(1), m.group(2), int(m.group(3))))
        elif linea.startswith('%'):
            m = re.match(r'%\s*(\S+)\s*(=|==|<>|!=)\s*(\S+)', linea)
            if not m:
                raise ValueError('no entiendo la comprobacion: %s' % linea)
            pon('obj', (m.group(1), m.group(2), m.group(3)))
        elif linea.startswith('@'):
            pon('loc', linea[1:].strip())
        else:
            pon('orden', linea)
    return pruebas


def guion_de(pruebas):
    """Traduce las pruebas al guion que va dentro del .nex. Cada prueba empieza
    con un reinicio y cada orden lleva detras una foto del estado, que es lo que
    separa una respuesta de la siguiente al leer la traza."""
    g = bytearray()
    for _nombre, pasos in pruebas:
        g += RESET
        g += FOTO                       # estado nada mas arrancar la partida
        for tipo, dato in pasos:
            if tipo == 'orden':
                orden = _tecleable(dato)
                if not orden:
                    raise ValueError('orden vacia o no tecleable: %r' % dato)
                g += orden.encode('ascii') + b'\r' + FOTO
    return bytes(g)


# ---------------------------------------------------------------------------
#  2. ejecutar en jnext, leyendo la traza segun sale
# ---------------------------------------------------------------------------

def busca_jnext(ruta=None):
    for cand in (ruta, os.environ.get('JNEXT'), 'jnext', 'jnext.exe'):
        if not cand:
            continue
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
        hallado = shutil.which(cand)
        if hallado:
            return hallado
    raise RuntimeError(
        'no encuentro jnext. Pasa --jnext RUTA, pon la variable de entorno '
        'JNEXT o metelo en el PATH. Se descarga de '
        'https://github.com/jorgegv/jnext/releases')


FOTO_RE = re.compile(
    r'\n#VARS ([0-9A-F ]*)\n#OBJLOC ([0-9A-F ]*)\n#OBJIN ([0-9A-F ]*)\n#LOC ([0-9A-F ]*)\n')
RESET_RE = re.compile(r'\n#RESET\n')


def _hex(s):
    return [int(x, 16) for x in s.split()]


def ejecuta(jnext, nex, frames, sdcard=None, alvuelo=None, pt=False):
    """Corre el .nex en jnext y devuelve el texto que salio por el puerto.

    El puerto magico escribe a la salida de error carácter a carácter y sin
    buffer, asi que se lee segun sale: `alvuelo` recibe cada trozo de texto ya
    descodificado y puede ir contando lo que pasa mientras la partida corre.
    """
    acc = _mapa_acentos(pt)
    tmp = tempfile.mkdtemp(prefix='bateria_next_')
    log = os.path.join(tmp, 'jnext.log')
    cmd = [jnext, '--headless', nex,
           '--magic-port', hex(nn.PUERTO_TRAZA), '--magic-port-mode', 'ascii',
           '--log-file', log,              # los mensajes del emulador, aparte
           '--delayed-automatic-exit-frames', str(int(frames))]
    if sdcard:
        cmd += ['--sdcard', sdcard]
    partes = []
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, bufsize=0)
        while True:
            trozo = p.stderr.read1(4096) if hasattr(p.stderr, 'read1') \
                else p.stderr.read(1)
            if not trozo:
                break
            texto = ''.join(acc.get(b, chr(b) if 10 <= b < 127 else '?')
                            for b in trozo)
            partes.append(texto)
            if alvuelo:
                alvuelo(texto)
        p.wait()
        entero = ''.join(partes)
        if p.returncode != 0 and not entero:
            cola = ''
            if os.path.exists(log):
                cola = io.open(log, encoding='utf-8', errors='replace').read()[-800:]
            raise RuntimeError('jnext fallo (codigo %d)\n%s' % (p.returncode, cola))
        return entero
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def trocea(texto):
    """Traza -> [[(segmento, foto), ...], ...] por prueba. El segmento es lo que
    se imprimio hasta esa foto, o sea la respuesta a la orden que la precede."""
    pruebas = []
    for trozo in RESET_RE.split(texto)[1:]:
        trozo = trozo.split('\n#FIN\n')[0]
        pasos, ini = [], 0
        for m in FOTO_RE.finditer(trozo):
            pasos.append((trozo[ini:m.start()], _foto(m)))
            ini = m.end()
        pruebas.append(pasos)
    return pruebas


def _foto(m):
    return {'vars': _hex(m.group(1)), 'objloc': _hex(m.group(2)),
            'objin': _hex(m.group(3)), 'loc': _hex(m.group(4))[0]}


# ---------------------------------------------------------------------------
#  3. el plan: que se espera, orden a orden
# ---------------------------------------------------------------------------

def plan_de(pruebas):
    """Cada prueba -> lista de bloques. El bloque k son las comprobaciones que
    van DESPUES de la orden k (el bloque 0, las de antes de ninguna orden), y
    es tambien el indice de la foto que las resuelve."""
    plan = []
    for nombre, pasos in pruebas:
        bloques = [(None, [])]
        for tipo, dato in pasos:
            if tipo == 'orden':
                bloques.append((dato, []))
            else:
                bloques[-1][1].append((tipo, dato))
        plan.append((nombre, bloques))
    return plan


class Referencias:
    """Los nombres del YAML traducidos a los indices que usa el motor."""

    def __init__(self, game):
        c = sx.recolecta(game)
        self.vars = {k.upper().replace('_', ''): i for i, k in enumerate(c.vars.keys())}
        self.locs = [n for n, _ in sorted(c.locidx.items(), key=lambda kv: kv[1])]
        self.objnom = [n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1])]
        self.objidx = {n.upper(): i for i, n in enumerate(self.objnom)}
        self.pt = str((game.get('metadata') or {}).get('language', '')).lower().startswith('pt')
        # variable de puntuacion, para enseñarla al lado de cada orden
        self.punt = next((k for k in ('PUNTOS', 'SCORE', 'PUNTUACION')
                          if k in self.vars), None)

    def var(self, nombre):
        k = nombre.upper().replace('_', '')
        if k not in self.vars:
            raise KeyError('el juego no tiene la variable %s' % nombre)
        return self.vars[k]

    def obj(self, nombre):
        k = str(nombre).upper()
        if k not in self.objidx:
            raise KeyError('el juego no tiene el objeto %s' % nombre)
        return self.objidx[k]

    def sala(self, i):
        return self.locs[i] if i < len(self.locs) else '?%d' % i

    def donde(self, foto, i):
        """Donde esta el objeto i, con el mismo vocabulario que el .pru."""
        v = foto['objloc'][i]
        if v == ge.CARRIED:
            return 'INVEN'
        if v == ge.WORN:
            return 'PUESTO'
        if v == ge.NOWHERE:
            return 'NADA'
        if v == ge.CONTAINED:
            c = foto['objin'][i] - 1
            return self.objnom[c] if 0 <= c < len(self.objnom) else '?%d' % c
        return self.sala(v)


def juzga(tipo, dato, texto, foto, ref):
    """None si la comprobacion pasa; si no, por que ha fallado."""
    if tipo == 'texto':
        if _norm(dato) not in _norm(texto):
            return 'no sale'
    elif tipo == 'notexto':
        if _norm(dato) in _norm(texto):
            return 'sale y no deberia'
    elif tipo == 'var':
        nombre, op, esperado = dato
        v = foto['vars'][ref.var(nombre)]
        if not CMP[op](v, esperado):
            return 'vale %d' % v
    elif tipo == 'loc':
        esta = ref.sala(foto['loc'])
        if esta != dato:
            return 'esta en %s' % esta
    elif tipo == 'obj':
        nombre, op, esperado = dato
        esta = ref.donde(foto, ref.obj(nombre))
        if (op in ('=', '==')) != (esta.upper() == esperado.upper()):
            return 'esta en %s' % esta
    return None


def dibuja(tipo, dato):
    """La comprobacion, escrita como estaba en el .pru."""
    if tipo == 'texto':
        return '? %s' % dato
    if tipo == 'notexto':
        return '!? %s' % dato
    if tipo == 'var':
        return '$ %s %s %d' % dato
    if tipo == 'loc':
        return '@ %s' % dato
    if tipo == 'obj':
        return '%% %s %s %s' % dato
    return str(dato)


# ---------------------------------------------------------------------------
#  4. el relator: va contando la partida segun sale del emulador
# ---------------------------------------------------------------------------

class Relator:
    """Consume la traza a trozos y, cada vez que se completa un paso, lo cuenta
    y resuelve las comprobaciones que le tocaban. Asi se ve lo que esta pasando
    mientras el emulador corre, en vez de un volcado al final."""

    ANCHO_ORDEN = 26

    def __init__(self, plan, ref, nivel=0, salida=None):
        self.plan = plan
        self.ref = ref
        self.nivel = nivel              # 0 callado, 1 ordenes, 2 + respuesta entera
        self.out = salida or sys.stdout
        self.buf = ''                   # lo que aun no se ha analizado
        self.t = -1                     # prueba en curso
        self.k = 0                      # paso dentro de la prueba
        self.fallos = []                # (prueba, detalle)
        self.hechas = 0

    # -- entrada ---------------------------------------------------------
    def come(self, texto):
        self.buf += texto
        while True:
            mr = RESET_RE.search(self.buf)
            mf = FOTO_RE.search(self.buf)
            if mf and (not mr or mf.start() < mr.start()):
                self._paso(self.buf[:mf.start()], _foto(mf))
                self.buf = self.buf[mf.end():]
            elif mr:
                self._reset()
                self.buf = self.buf[mr.end():]
            else:
                break

    def cierra(self):
        """Lo que quedaba sin resolver cuando se acabo la traza."""
        for t in range(self.t + 1, len(self.plan)):
            if self.nivel:
                self._di('=== %s' % self.plan[t][0])
            self._falla(t, 'la partida no llego hasta aqui '
                           '(sube los barridos con --frames)')

    # -- eventos ---------------------------------------------------------
    def _reset(self):
        if self.t >= 0:
            self._pendientes()
        self.t += 1
        self.k = 0
        if self.t < len(self.plan):
            self._di('=== %s' % self.plan[self.t][0])

    def _paso(self, texto, foto):
        if self.t < 0 or self.t >= len(self.plan):
            return
        bloques = self.plan[self.t][1]
        if self.k >= len(bloques):
            self.k += 1
            return
        orden, checks = bloques[self.k]
        self._cuenta(orden, texto, foto)
        for tipo, dato in checks:
            self.hechas += 1
            try:
                mal = juzga(tipo, dato, texto, foto, self.ref)
            except Exception as e:
                mal = '%s: %s' % (type(e).__name__, e)
            if mal:
                self._falla(self.t, '%s   -> %s%s' % (
                    dibuja(tipo, dato), mal,
                    '' if orden is None else ' (tras "%s")' % orden))
            elif self.nivel:
                self._di('        ok    %s' % dibuja(tipo, dato))
        self.k += 1

    def _pendientes(self):
        """La prueba se corto antes de tiempo: lo que faltaba es fallo."""
        bloques = self.plan[self.t][1]
        for orden, checks in bloques[self.k:]:
            for tipo, dato in checks:
                self.hechas += 1
                self._falla(self.t, '%s   -> la partida se corto antes'
                            % dibuja(tipo, dato))

    # -- salida ----------------------------------------------------------
    def _cuenta(self, orden, texto, foto):
        if not self.nivel:
            return
        etiqueta = '  .  (arranque)' if orden is None else '%3d. %s' % (self.k, orden)
        etiqueta = etiqueta.ljust(5 + self.ANCHO_ORDEN)[:5 + self.ANCHO_ORDEN]
        estado = self.ref.sala(foto['loc']).ljust(16)
        if self.ref.punt is not None:
            estado += ' %s=%-3d' % (self.ref.punt.lower(),
                                    foto['vars'][self.ref.vars[self.ref.punt]])
        self._di('%s %s %s' % (etiqueta, estado, _resumen(texto, orden)))
        if self.nivel >= 2:
            for linea in texto.strip().split('\n'):
                if linea.strip():
                    self._di('          | %s' % linea.rstrip())

    def _falla(self, t, detalle):
        self.fallos.append((self.plan[t][0], detalle))
        self._di('        FALLA %s' % detalle)

    def _di(self, s):
        if not self.nivel:      # sin -v no se cuenta nada segun pasa: al final
            return              # main imprime solo los fallos, agrupados
        self.out.write(s + '\n')
        self.out.flush()


def _resumen(texto, orden):
    """La respuesta en una linea: se quita el eco de la orden y el prompt."""
    t = texto
    if orden:
        i = t.lower().find(_tecleable(orden))
        if i >= 0:
            t = t[i + len(_tecleable(orden)):]
    t = ' '.join(t.replace('>', ' ').split())
    return (t[:70] + '...') if len(t) > 73 else t


# ---------------------------------------------------------------------------
#  5. programa
# ---------------------------------------------------------------------------

def _opcion(argv, nombre, por_defecto=None):
    for k, a in enumerate(argv):
        if a == nombre and k + 1 < len(argv):
            return argv[k + 1]
    return por_defecto


def main():
    argv = sys.argv[1:]
    conval = ('--jnext', '--sdcard', '--frames', '--traza')
    sueltos, salta = [], False
    for a in argv:
        if salta:
            salta = False
            continue
        if a in conval:
            salta = True
        elif not a.startswith('-'):
            sueltos.append(a)
    if len(sueltos) < 2:
        print(__doc__)
        sys.exit(2)
    yaml_path, pru_path = sueltos[0], sueltos[1]
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    frames = _opcion(argv, '--frames')
    traza_out = _opcion(argv, '--traza')

    jnext = busca_jnext(_opcion(argv, '--jnext'))
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    pruebas = lee_pru(pru_path)
    guion = guion_de(pruebas)
    nordenes = sum(1 for _, p in pruebas for t, _d in p if t == 'orden')
    nchecks = sum(1 for _, p in pruebas for t, _d in p if t != 'orden')

    print('emulador   %s' % jnext)
    print('juego      %s' % os.path.basename(yaml_path))
    print('bateria    %s: %d prueba(s), %d orden(es), %d comprobacion(es)'
          % (os.path.basename(pru_path), len(pruebas), nordenes, nchecks))
    sys.stdout.flush()

    nex = os.path.join(tempfile.gettempdir(), 'scriba_bateria_next.nex')
    t0 = time.time()
    info = nn.export_nex(game, nex,
                         datadir=os.path.join(raiz, 'temp', 'Next', 'data'),
                         musicdir=os.path.join(raiz, 'music'),
                         guion=guion)
    print('compilado  %d loc, %d obj, %d imagenes; %d bytes de motor + %d de '
          'datos; guion de %d bytes (%.1fs)'
          % (info['localizaciones'], info['objetos'], len(info['imagenes']),
             info['codigo'], info['datos'], len(guion), time.time() - t0))

    frames = int(frames) if frames else (
        FRAMES_ARRANQUE * max(1, len(pruebas)) + FRAMES_POR_ORDEN * nordenes)
    print('jugando    %d barridos de emulador como mucho\n' % frames)
    sys.stdout.flush()

    ref = Referencias(game)
    rel = Relator(plan_de(pruebas), ref, nivel)
    t0 = time.time()
    texto = ejecuta(jnext, nex, frames, _opcion(argv, '--sdcard'),
                    alvuelo=rel.come, pt=ref.pt)
    rel.cierra()
    tardado = time.time() - t0

    if traza_out:
        io.open(traza_out, 'w', encoding='utf-8').write(texto)
    if '#RESET' not in texto:
        print('\nla partida no arranco siquiera. Traza:\n%s' % texto[:2000])
        sys.exit(1)

    print()
    if not nivel:
        anterior = None
        for nombre, detalle in rel.fallos:
            if nombre != anterior:
                print('=== %s' % nombre)
                anterior = nombre
            print('        FALLA %s' % detalle)
        if rel.fallos:
            print()
    if '#FIN' not in texto:
        print('AVISO: el guion no llego al final en %d barridos; reintenta con '
              '--frames %d' % (frames, frames * 2))
    print('%d comprobacion(es) en %d prueba(s), %s  (%.0fs de emulador)'
          % (rel.hechas, len(pruebas),
             '%d fallo(s)' % len(rel.fallos) if rel.fallos else 'todo correcto',
             tardado))
    sys.exit(1 if rel.fallos else 0)


if __name__ == '__main__':
    main()
