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
    * 40 ESPERAR                repite una orden 40 veces (dejar pasar turnos)
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
    --maquina M     next (por defecto), 48 o 128. En 48 y 128 se prueba el
                    MISMO binario que va en el .tap, metido en un .nex para
                    que jnext lo arranque: o sea el motor y la base de datos
                    de esas maquinas, no el cargador BASIC de la cinta. El
                    guion de la bateria viaja en bancos aparte y se pagina
                    sobre la ROM, que es sitio que el motor no usa.
    --jnext RUTA    el emulador (si no, la variable JNEXT o el PATH)
    --sdcard FILE   imagen de tarjeta SD ya bajada (util en CI)
    --frames N      tope de barridos de emulador (por defecto se estima)
    --traza FILE    guarda la traza cruda para mirarla luego
    --bajar-sd      deja que jnext se baje la imagen de tarjeta SD (1 GB) si es
                    la primera vez que se usa en esta maquina
    --paciencia N   segundos sin noticias del emulador antes de cortar (120)

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
import unicodedata
import threading
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
    """Para comparar texto: sin mayusculas, sin acentos y con un solo espacio.
    Lo de los acentos no es pereza: en pantalla salen como codigos propios de
    la fuente del juego, y obligar a escribirlos en el .pru solo sirve para que
    una prueba falle por una tilde."""
    t = unicodedata.normalize('NFD', ' '.join(str(t).split()).lower())
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn')


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
        if linea.startswith('*'):
            # '* 40 ESPERAR' repite una orden 40 veces. Dejar pasar
            # turnos es lo que mas se repite en una bateria, y el
            # guion viaja DENTRO del .nex: conviene que ocupe poco.
            m = re.match(r'\*\s*(\d+)\s+(.+)', linea)
            if not m:
                raise ValueError('no entiendo la repeticion: %s' % linea)
            for _ in range(int(m.group(1))):
                pon('orden', m.group(2).strip())
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


# Las marcas del volcado. El \r es de rigor: el motor manda 13 y 10 para saltar
# de linea, y ademas en Windows el runtime de C convierte en \r\n cada \n que
# jnext escribe, o sea que una marca puede llegar como \r\n#RESET\r\n. Se tiran
# los retornos al descodificar y aun asi las expresiones los toleran, que esto
# ya costo una tarde.
FOTO_RE = re.compile(
    r'\r?\n#VARS ([0-9A-F ]*)\r?\n#OBJLOC ([0-9A-F ]*)\r?\n#OBJIN ([0-9A-F ]*)'
    r'\r?\n#LOC ([0-9A-F ]*)\r?\n')
RESET_RE = re.compile(r'\r?\n#RESET\r?\n')
FIN_RE = re.compile(r'\r?\n#FIN\r?\n')


def descodifica(trozo, acc):
    """Bytes del puerto -> texto. Los acentos vienen en 224-239, y el retorno
    de carro sobra: la linea la corta el 10 que va detras."""
    return ''.join(acc.get(b, chr(b) if 10 <= b < 127 else '?')
                   for b in trozo if b != 13)


def _hex(s):
    return [int(x, 16) for x in s.split()]


def rutas_sdcard():
    """Donde puede estar la imagen de tarjeta SD, con las mismas reglas que usa
    jnext (sdcard_provisioner.cpp): $JNEXT_CONFIG_DIR, si no $HOME/.jnext, y si
    no hay HOME, .jnext en el directorio desde el que se lance. Ojo a lo
    ultimo: en Windows HOME no suele estar puesta, asi que la imagen acaba en
    la carpeta desde la que se ejecuto jnext la primera vez, no en la del
    usuario."""
    dirs = []
    d = os.environ.get('JNEXT_CONFIG_DIR')
    if d:
        dirs.append(d)
    h = os.environ.get('HOME')
    if h:
        dirs.append(os.path.join(h, '.jnext'))
    else:
        dirs.append(os.path.join(os.getcwd(), '.jnext'))
    # y por si acaso, la carpeta del usuario, que es donde la busca todo el
    # mundo cuando no la encuentra
    casa = os.path.join(os.path.expanduser('~'), '.jnext')
    if casa not in dirs:
        dirs.append(casa)
    return [os.path.join(d, 'sdcard', 'cspect-next-1gb-fixed.img') for d in dirs]


def hay_sdcard():
    return any(os.path.exists(r) for r in rutas_sdcard())


def pista_sdcard(sdcard):
    """Lo que hay que hacer si el emulador no arranca por falta de tarjeta."""
    if sdcard or hay_sdcard():
        return ''
    return ('\nLo mas probable: jnext no tiene todavia la imagen de tarjeta SD, '
            'de donde\nsaca las ROMs igual que una maquina de verdad. He mirado '
            'en:\n'
            + ''.join('  %s\n' % r for r in rutas_sdcard()) +
            'Cualquiera de estas tres vale:\n'
            '  - vuelve a lanzar la bateria con --bajar-sd (son 1 GB)\n'
            '  - pasale una imagen que ya tengas con --sdcard FICHERO\n'
            '  - ejecuta jnext a mano una vez y acepta la descarga (pero ojo: si '
            'HOME\n    no esta puesta, la deja en la carpeta desde la que lo '
            'lances)\n')


def ejecuta(jnext, nex, frames, sdcard=None, alvuelo=None, pt=False,
            bajar_sd=False, paciencia=120, eco=None):
    """Corre el .nex en jnext y devuelve el texto que salio por el puerto.

    El puerto magico escribe a la salida de error caracter a caracter y sin
    buffer, asi que se lee segun sale: `alvuelo` recibe cada trozo de texto ya
    descodificado y puede ir contando lo que pasa mientras la partida corre.

    Tres cosas que hay que hacer bien o el proceso se queda colgado sin decir
    nada, que es justo lo que pasa la primera vez en una maquina limpia:

    - **stdin cerrado.** Sin imagen de tarjeta SD, jnext pregunta si se la baja
      y espera respuesta. La pregunta sale por su salida ESTANDAR, que aqui no
      se enseña, asi que sin esto el proceso se queda esperando una tecla que
      nadie ve que haga falta. Con stdin cerrado la da por contestada que no y
      sale con un mensaje, que si se enseña.
    - **Su salida estandar se guarda**, no se tira: ahi es donde pone lo que le
      pasa cuando no arranca.
    - **Un plazo.** Si no llega nada por el puerto en `paciencia` segundos, se
      corta y se cuenta, en vez de esperar sin fin.
    """
    acc = _mapa_acentos(pt)
    tmp = tempfile.mkdtemp(prefix='bateria_next_')
    log = os.path.join(tmp, 'jnext.log')
    salida = os.path.join(tmp, 'jnext.out')
    cmd = [jnext, '--headless', nex,
           '--magic-port', hex(nn.PUERTO_TRAZA), '--magic-port-mode', 'ascii',
           '--log-file', log,              # los mensajes del emulador, aparte
           '--delayed-automatic-exit-frames', str(int(frames))]
    if sdcard:
        cmd += ['--sdcard', sdcard]
    if bajar_sd:
        cmd += ['--sdcard-download-confirm']
    if eco:
        eco('orden      %s' % ' '.join(
            ('"%s"' % a if ' ' in a else a) for a in cmd))
    partes = []
    cortado = [False]
    try:
        with io.open(salida, 'wb') as fsal:
            p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fsal,
                                 stderr=subprocess.PIPE, bufsize=0)
            fd = p.stderr.fileno()
            reloj = [None]

            def sin_noticias():
                cortado[0] = True
                try:
                    p.kill()
                except Exception:
                    pass

            def rearma():
                if reloj[0]:
                    reloj[0].cancel()
                reloj[0] = threading.Timer(paciencia, sin_noticias)
                reloj[0].daemon = True
                reloj[0].start()

            rearma()
            try:
                while True:
                    try:
                        trozo = os.read(fd, 4096)
                    except OSError:
                        break
                    if not trozo:
                        break
                    rearma()
                    texto = descodifica(trozo, acc)
                    partes.append(texto)
                    if alvuelo:
                        alvuelo(texto)
                    # Al acabarse el guion el motor para la CPU, pero el
                    # emulador sigue barriendo hasta su tope. Como ya no va a
                    # salir nada mas, se corta aqui: el tope de barridos solo
                    # tiene que ser generoso, no exacto.
                    if FIN_RE.search(''.join(partes[-2:])):
                        p.kill()
                        break
            finally:
                if reloj[0]:
                    reloj[0].cancel()
            p.wait()
        entero = ''.join(partes)
        if entero:
            return entero
        # No salio nada por el puerto: hay que contar por que, con lo que diga
        # el propio emulador, que es lo unico que sabe lo que le ha pasado.
        pistas = []
        for f in (salida, log):
            if os.path.exists(f):
                t = io.open(f, encoding='utf-8', errors='replace').read().strip()
                if t:
                    pistas.append(t[-1200:])
        motivo = ('jnext no contesto en %ds' % paciencia) if cortado[0] \
            else ('jnext termino con codigo %d' % p.returncode)
        raise RuntimeError('%s y no solto nada por el puerto de traza.\n%s\n%s'
                           % (motivo, '\n'.join(pistas), pista_sdcard(sdcard)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def trocea(texto):
    """Traza -> [[(segmento, foto), ...], ...] por prueba. El segmento es lo que
    se imprimio hasta esa foto, o sea la respuesta a la orden que la precede."""
    pruebas = []
    for trozo in RESET_RE.split(texto)[1:]:
        trozo = FIN_RE.split(trozo)[0]
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
    conval = ('--jnext', '--sdcard', '--frames', '--traza', '--paciencia',
              '--maquina')
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
    maquina = str(_opcion(argv, '--maquina', 'next')).lower()
    if maquina not in ('next', '48', '128'):
        print('--maquina admite next, 48 o 128 (no %r)' % maquina)
        sys.exit(2)
    traza_out = _opcion(argv, '--traza')

    jnext = busca_jnext(_opcion(argv, '--jnext'))
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    pruebas = lee_pru(pru_path)
    guion = guion_de(pruebas)
    nordenes = sum(1 for _, p in pruebas for t, _d in p if t == 'orden')
    nchecks = sum(1 for _, p in pruebas for t, _d in p if t != 'orden')

    print('emulador   %s' % jnext)
    print('maquina    %s' % {'next': 'ZX Spectrum Next (.nex)',
                             '48': 'ZX Spectrum 48K (binario del .tap en un .nex)',
                             '128': 'ZX Spectrum 128K (binario del .tap en un .nex)'}[maquina])
    print('juego      %s' % os.path.basename(yaml_path))
    print('bateria    %s: %d prueba(s), %d orden(es), %d comprobacion(es)'
          % (os.path.basename(pru_path), len(pruebas), nordenes, nchecks))
    sys.stdout.flush()

    nex = os.path.join(tempfile.gettempdir(),
                       'scriba_bateria_%s.nex' % maquina)
    t0 = time.time()
    try:
        if maquina == '48':
            # El .tap es lo que se distribuye; aqui el MISMO binario viaja en
            # el contenedor que sabe cargar el emulador. Se prueba el motor y
            # la base de datos de 48K, no el cargador BASIC de la cinta.
            import spectrum48_nativo as s48
            info = s48.export_nex_prueba(game, nex, guion, game_dir=raiz)
        elif maquina == '128':
            import spectrum128_nativo as s128
            info = s128.export_nex_prueba(game, nex, guion, game_dir=raiz)
        else:
            info = nn.export_nex(game, nex,
                                 datadir=os.path.join(raiz, 'temp', 'Next', 'data'),
                                 musicdir=os.path.join(raiz, 'music'),
                                 guion=guion)
    except ValueError as e:
        # El guion viaja DENTRO del .nex, asi que una bateria larga puede no
        # caber. Decirlo con todas las letras en vez de soltar el error del
        # exportador, que habla de direcciones y no de pruebas.
        if 'no cabe en el mapa plano' not in str(e):
            raise
        print('\nEl guion de la bateria (%d bytes, %d ordenes) no cabe en el .nex '
              'junto al juego.\n%s\n\nSale mas barato acortarlo que agrandar el '
              'mapa:\n'
              '  - usa \'* 40 I\' en vez de repetir una orden larga 40 veces\n'
              '    (cada orden ocupa sus letras + 1, y I pasa turno igual)\n'
              '  - parte la bateria en dos ficheros .pru' % (len(guion), nordenes, e))
        sys.exit(2)
    print('compilado  %d loc, %d obj, %d imagenes; %d bytes de motor + %d de '
          'datos; guion de %d bytes (%.1fs)'
          % (info['localizaciones'], info['objetos'], len(info['imagenes']),
             info['codigo'], info['datos'], len(guion), time.time() - t0))

    frames = int(frames) if frames else (
        FRAMES_ARRANQUE * max(1, len(pruebas)) + FRAMES_POR_ORDEN * nordenes)
    sdcard = _opcion(argv, '--sdcard')
    bajar = '--bajar-sd' in argv
    if not sdcard and not bajar and not hay_sdcard():
        print('AVISO      no encuentro la imagen de tarjeta SD de jnext, de donde\n'
              '           saca las ROMs igual que una maquina de verdad. He mirado\n'
              + ''.join('             %s\n' % r for r in rutas_sdcard())
              + '           Si no arranca: --bajar-sd (son 1 GB) o --sdcard FICHERO.\n'
                '           (jnext la busca en $HOME/.jnext, y si HOME no esta\n'
                '           puesta -lo normal en Windows- en .jnext de la carpeta\n'
                '           desde la que se le lance.)', end='')
    print('jugando    %d barridos de emulador como mucho\n' % frames)
    sys.stdout.flush()

    ref = Referencias(game)
    rel = Relator(plan_de(pruebas), ref, nivel)
    t0 = time.time()
    texto = ejecuta(jnext, nex, frames, sdcard, alvuelo=rel.come, pt=ref.pt,
                    bajar_sd=bajar, paciencia=int(_opcion(argv, '--paciencia', 120)),
                    eco=(print if nivel else None))
    tardado = time.time() - t0
    if traza_out:
        io.open(traza_out, 'w', encoding='utf-8').write(texto)
    if rel.t < 0:
        # Ni una sola partida llego a empezar: no tiene sentido dar por fallada
        # cada prueba una por una, lo unico que importa es que salio de ahi.
        print('\nNinguna partida llego a empezar (%.0fs). Esto es lo que solto '
              'el emulador:\n' % tardado)
        print((texto.strip()[:2000] or '(nada)'))
        print(pista_sdcard(sdcard))
        if texto.strip() and '#RESET' in texto:
            # Salio traza, pero sin las marcas donde se esperaban: no es el
            # emulador, es que la traza no se esta leyendo bien.
            print('OJO: la traza trae "#RESET" pero no donde se espera, o sea '
                  'que el fallo es de la bateria leyendola, no del juego.\n'
                  'Guardala con --traza traza.txt y mandala.')
        elif not traza_out:
            print('Si hace falta mirarla entera: --traza traza.txt')
        sys.exit(1)
    rel.cierra()

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
    if not FIN_RE.search(texto):
        print('AVISO: el guion no llego al final en %d barridos; reintenta con '
              '--frames %d' % (frames, frames * 2))
    print('%d comprobacion(es) en %d prueba(s), %s  (%.0fs de emulador)'
          % (rel.hechas, len(pruebas),
             '%d fallo(s)' % len(rel.fallos) if rel.fallos else 'todo correcto',
             tardado))
    sys.exit(1 if rel.fallos else 0)


if __name__ == '__main__':
    main()
