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
    python bateria_next.py juego.yaml pruebas.pru [--jnext RUTA] [-v]

jnext se busca en --jnext, en la variable de entorno JNEXT y en el PATH.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

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
#  2. ejecutar en jnext y trocear la traza
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


def ejecuta(jnext, nex, frames, sdcard=None):
    """Corre el .nex y devuelve lo que salio por el puerto de traza."""
    with tempfile.TemporaryDirectory() as tmp:
        traza = os.path.join(tmp, 'traza.txt')
        log = os.path.join(tmp, 'jnext.log')
        cmd = [jnext, '--headless', nex,
               '--magic-port', hex(nn.PUERTO_TRAZA), '--magic-port-mode', 'ascii',
               '--log-file', log,            # los mensajes del emulador, aparte
               '--delayed-automatic-exit-frames', str(int(frames))]
        if sdcard:
            cmd += ['--sdcard', sdcard]
        with io.open(traza, 'wb') as fe:
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=fe)
        crudo = io.open(traza, 'rb').read()
        if p.returncode != 0 and not crudo:
            cola = ''
            if os.path.exists(log):
                cola = io.open(log, encoding='utf-8', errors='replace').read()[-800:]
            raise RuntimeError('jnext fallo (codigo %d)\n%s' % (p.returncode, cola))
    return crudo


def descodifica(crudo, pt):
    """Bytes del puerto -> texto. Los acentos vienen en 224-239."""
    acc = _mapa_acentos(pt)
    return ''.join(acc.get(b, chr(b) if 10 <= b < 127 else '?') for b in crudo)


def trocea(texto):
    """Traza -> [[segmento, foto], ...] por prueba. El segmento es lo que se
    imprimio hasta esa foto, o sea la respuesta a la orden que la precede."""
    fotos = re.compile(
        r'\n#VARS ([0-9A-F ]*)\n#OBJLOC ([0-9A-F ]*)\n#OBJIN ([0-9A-F ]*)\n#LOC ([0-9A-F ]*)\n')
    pruebas = []
    for trozo in texto.split('\n#RESET\n')[1:]:
        trozo = trozo.split('\n#FIN\n')[0]
        pasos, ini = [], 0
        for m in fotos.finditer(trozo):
            pasos.append((trozo[ini:m.start()],
                          {'vars': _hex(m.group(1)), 'objloc': _hex(m.group(2)),
                           'objin': _hex(m.group(3)), 'loc': _hex(m.group(4))[0]}))
            ini = m.end()
        pruebas.append(pasos)
    return pruebas


def _hex(s):
    return [int(x, 16) for x in s.split()]


# ---------------------------------------------------------------------------
#  3. comprobar
# ---------------------------------------------------------------------------

class Referencias:
    """Los nombres del YAML traducidos a los indices que usa el motor."""

    def __init__(self, game):
        c = sx.recolecta(game)
        self.vars = {k.upper().replace('_', ''): i for i, k in enumerate(c.vars.keys())}
        self.locs = [n for n, _ in sorted(c.locidx.items(), key=lambda kv: kv[1])]
        self.locidx = {n: i for i, n in enumerate(self.locs)}
        self.objidx = {n.upper(): i for i, n in enumerate(
            n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
        self.pt = str((game.get('metadata') or {}).get('language', '')).lower().startswith('pt')

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
            c = foto['objin'][i]
            return self.locs and ('#%s' % self._obj_nombre(c - 1)) or '?'
        return self.locs[v] if v < len(self.locs) else '?%d' % v

    def _obj_nombre(self, i):
        for n, k in self.objidx.items():
            if k == i:
                return n.lstrip('#').lower()
        return '?%d' % i


def comprueba(pruebas, pasos_traza, ref):
    """Devuelve [(nombre, ok, detalle), ...]; ok=None marca cabecera de prueba."""
    res = []
    for n, (nombre, pasos) in enumerate(pruebas):
        res.append((nombre, None, 'inicio'))
        if n >= len(pasos_traza):
            res.append((nombre, False, 'la partida no llego hasta aqui: '
                        'sube los barridos con --frames'))
            continue
        traza = pasos_traza[n]
        k = 0                       # 0 = estado al arrancar, antes de ordenes
        ultima = '(el arranque)'
        for tipo, dato in pasos:
            if tipo == 'orden':
                k += 1
                ultima = dato
                continue
            if k >= len(traza):
                res.append((nombre, False, 'la partida se corto en "%s"' % ultima))
                break
            texto, foto = traza[k]
            try:
                fallo = _juzga(tipo, dato, texto, foto, ref, ultima)
            except Exception as e:
                fallo = '%s: %s' % (type(e).__name__, e)
            if fallo:
                res.append((nombre, False, fallo))
    return res


def _juzga(tipo, dato, texto, foto, ref, ultima):
    if tipo == 'texto':
        if _norm(dato) not in _norm(texto):
            return 'no sale: "%s" (tras "%s")' % (dato, ultima)
    elif tipo == 'notexto':
        if _norm(dato) in _norm(texto):
            return 'sale y no deberia: "%s" (tras "%s")' % (dato, ultima)
    elif tipo == 'var':
        nombre, op, esperado = dato
        v = foto['vars'][ref.var(nombre)]
        if not CMP[op](v, esperado):
            return '%s vale %d, no %s %d (tras "%s")' % (nombre, v, op, esperado, ultima)
    elif tipo == 'loc':
        i = foto['loc']
        esta = ref.locs[i] if i < len(ref.locs) else '?%d' % i
        if esta != dato:
            return 'esta en %s, no en %s (tras "%s")' % (esta, dato, ultima)
    elif tipo == 'obj':
        nombre, op, esperado = dato
        esta = ref.donde(foto, ref.obj(nombre))
        igual = esta.upper() == esperado.upper()
        if (op in ('=', '==')) != igual:
            return '%s esta en %s, y se esperaba %s %s (tras "%s")' % (
                nombre, esta, op, esperado, ultima)
    return None


# ---------------------------------------------------------------------------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if len(args) < 2:
        print(__doc__)
        sys.exit(2)
    yaml_path, pru_path = args[0], args[1]
    verboso = '-v' in sys.argv
    ruta_jnext = None
    sdcard = None
    for k, a in enumerate(sys.argv):
        if a == '--jnext' and k + 1 < len(sys.argv):
            ruta_jnext = sys.argv[k + 1]
        if a == '--sdcard' and k + 1 < len(sys.argv):
            sdcard = sys.argv[k + 1]
    frames = None
    for k, a in enumerate(sys.argv):
        if a == '--frames' and k + 1 < len(sys.argv):
            frames = int(sys.argv[k + 1])

    jnext = busca_jnext(ruta_jnext)
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    pruebas = lee_pru(pru_path)
    guion = guion_de(pruebas)
    nordenes = sum(1 for _, p in pruebas for t, _d in p if t == 'orden')

    nex = os.path.join(tempfile.gettempdir(), 'scriba_bateria_next.nex')
    info = nn.export_nex(game, nex,
                         datadir=os.path.join(raiz, 'temp', 'Next', 'data'),
                         musicdir=os.path.join(raiz, 'music'),
                         guion=guion)
    print('%s -> %d localizaciones, %d objetos, %d imagenes; %d bytes de codigo'
          % (os.path.basename(yaml_path), info['localizaciones'],
             info['objetos'], len(info['imagenes']), info['codigo']))
    print('%d prueba(s), %d orden(es); guion de %d bytes'
          % (len(pruebas), nordenes, len(guion)))
    print('emulador: %s' % jnext)

    if frames is None:
        frames = FRAMES_ARRANQUE * max(1, len(pruebas)) + FRAMES_POR_ORDEN * nordenes
    crudo = ejecuta(jnext, nex, frames, sdcard)
    ref = Referencias(game)
    texto = descodifica(crudo, ref.pt)
    if verboso:
        io.open('traza_next.txt', 'w', encoding='utf-8').write(texto)
        print('traza completa en traza_next.txt')
    if '#RESET' not in texto:
        print('\nla partida no arranco. Traza:\n%s' % texto[:2000])
        sys.exit(1)
    if '#FIN' not in texto:
        print('\nAVISO: el guion no llego al final en %d barridos; '
              'reintenta con --frames %d' % (frames, frames * 2))

    res = comprueba(pruebas, trocea(texto), ref)
    print()
    fallos = 0
    for nombre, ok, detalle in res:
        if ok is None:
            print('=== %s' % nombre)
        elif not ok:
            fallos += 1
            print('   FALLA  %s' % detalle)
    print()
    if fallos:
        print('%d prueba(s), %d fallo(s)' % (len(pruebas), fallos))
    else:
        print('%d prueba(s), todo correcto' % len(pruebas))
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
