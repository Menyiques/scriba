# -*- coding: utf-8 -*-
"""
capabilities.py — Contrato canónico de funcionalidad de Scriba y comprobación de
compatibilidad por plataforma (fuente única de verdad).

Define qué condacts, predicados y funciones de juego soporta cada intérprete/target
y permite avisar, ANTES o AL exportar, de lo que un target NO soporta (en vez de
omitirlo en silencio). El intérprete de PC (interpreter.py) es la referencia: lo
soporta todo. Lo "particular de hardware" (color, sonido, imágenes) se exime de los
avisos de paridad porque puede variar por máquina.

Uso:
    import capabilities
    aviso = capabilities.report(game, 'cpc')   # '' si todo está soportado
    # o por línea de comandos:
    python capabilities.py juego.yaml
"""

import re

try:
    from paws_lang import PREDICATES
except Exception:                       # por si se usa aislado
    PREDICATES = {
        'AT', 'NOTAT', 'CARRIED', 'NOTCARR', 'PRESENT', 'ABSENT', 'WORN',
        'NOTWORN', 'ISAT', 'DARK', 'CHANCE', 'TIMER', 'HASOBJOPEN', 'ZERO',
        'NOTZERO', 'EQ', 'GT', 'LT', 'VERB', 'NOUN1', 'NOUN2',
    }

# ─── Universo de condacts (palabra inicial de cada sentencia) ────────────────
# Condacts "de autor" comprobables. Se excluyen los estructurales (IF/ELSE/...)
# y los internos del compilador (JMP).
CONDACTS = {
    'MESSAGE', 'PRINT', 'PRINTLN', 'NEWLINE', 'LET',
    'GOTO', 'GET', 'DROP', 'CREATE', 'DESTROY', 'PUT', 'PLACE',
    'PUTIN', 'TAKEOUT', 'OPEN', 'CLOSE', 'LOCK', 'UNLOCK', 'WEAR', 'REMOVE',
    'LIT', 'UNLIT', 'ADDSCORE', 'SCORE', 'DESC', 'LOOK', 'INVEN',
    'TIMER_START', 'TIMER_STOP', 'TIMER_RESET',
    'END', 'MATCH', 'QUIT',
    # particulares de hardware (pantalla/sonido): no rompen la paridad lógica
    'INK', 'PAPER', 'BORDER', 'PAUSE', 'CLS', 'BRIGHT', 'BEEP', 'SOUND',
    'FLASH', 'INVERSE',
}
STRUCTURAL = {'IF', 'ELSE', 'ENDIF', 'ON', 'ENDON', 'THEN', 'REM', 'JMP'}

# Condacts particulares de hardware: si un target no los tiene, NO se avisa como
# rotura de paridad (es una diferencia de máquina esperada).
HARDWARE_CONDACTS = {'INK', 'PAPER', 'BORDER', 'PAUSE', 'CLS', 'BRIGHT',
                     'BEEP', 'SOUND', 'FLASH', 'INVERSE'}

# Funciones de juego detectables en el modelo de datos (no son palabras clave).
FEATURES = {'weight', 'containers', 'wearables', 'lightsource', 'timers'}
FEATURE_LABEL = {
    'weight':      'límite de peso (LLEVAR_MAX / peso por objeto)',
    'containers':  'contenedores (abrir/cerrar/meter/sacar)',
    'wearables':   'objetos vestibles (WEAR/WORN)',
    'lightsource': 'fuentes de luz (lámpara que ilumina la oscuridad)',
    'timers':      'temporizadores (TIMER_START/STOP/RESET, on_expire)',
}

TARGET_LABEL = {
    'pc': 'PC (intérprete)', 'spectrum': 'ZX Spectrum 48K/128K',
    'next': 'ZX Spectrum Next', 'cpc': 'Amstrad CPC',
}

# ─── Contrato: qué soporta cada target ───────────────────────────────────────
# Se define lo SOPORTADO. La referencia (pc) soporta todo.
_NONHW = CONDACTS - HARDWARE_CONDACTS

CAPS = {
    'pc': {
        'condacts': set(CONDACTS),
        'predicates': set(PREDICATES),
        'features': set(FEATURES),
    },
    'spectrum': {
        'condacts': set(CONDACTS),
        'predicates': set(PREDICATES),
        'features': set(FEATURES),     # incluye peso desde v2.0
    },
    'cpc': {
        # Motor nativo Z80 (v2.0): paridad de logica completa (incluido NOUN2 con
        # parser de dos nombres). Solo difiere en hardware: sonido (BEEP/SOUND) y
        # atributos de pantalla no portados (BRIGHT/FLASH/INVERSE).
        'condacts': set(CONDACTS) - {'BRIGHT', 'BEEP', 'SOUND', 'FLASH', 'INVERSE'},
        'predicates': set(PREDICATES),
        'features': set(FEATURES),
    },
}
CAPS['next'] = CAPS['spectrum']        # Next reutiliza el motor de Spectrum


# ─── Escaneo del juego ───────────────────────────────────────────────────────

_STR = re.compile(r'"[^"]*"|\'[^\']*\'')
_WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _scripts(game):
    """Devuelve todos los textos de condacts del juego (str)."""
    out = []

    def add(s):
        if isinstance(s, str):
            out.append(s)
        elif isinstance(s, (list, tuple)):
            for x in s:
                add(x)

    cond = game.get('condacts', {}) or {}
    if isinstance(cond, dict):
        for v in cond.values():
            add(v)
    for loc in (game.get('locations', {}) or {}).values():
        if isinstance(loc, dict):
            add(loc.get('on_enter'))
    for tim in (game.get('timers', {}) or {}).values():
        if isinstance(tim, dict):
            add(tim.get('on_expire'))
    resp = game.get('responses', {}) or {}
    for e in (resp.get('entries', []) if isinstance(resp, dict) else []):
        if isinstance(e, dict):
            for k in ('actions', 'conditions', 'message', 'condition', 'action'):
                add(e.get(k))
    return out


def scan_game(game):
    """Devuelve {'condacts','predicates','features'} REALMENTE usados por el juego."""
    used_c, used_p = set(), set()
    for sc in _scripts(game):
        for line in str(sc).split('\n'):
            line = _STR.sub('', line)              # fuera literales de texto
            toks = [t.upper() for t in _WORD.findall(line)]
            if not toks:
                continue
            for t in toks:                          # predicados en cualquier sitio
                if t in PREDICATES:
                    used_p.add(t)
            # condact = primera palabra no estructural de la línea
            first = toks[0]
            if first not in STRUCTURAL and first in CONDACTS:
                used_c.add(first)
            # tras THEN puede venir un condact en la misma línea
            if 'THEN' in toks:
                k = toks.index('THEN')
                if k + 1 < len(toks) and toks[k + 1] in CONDACTS:
                    used_c.add(toks[k + 1])

    feats = set()
    objs = (game.get('objects', {}) or {}).values()
    for o in objs:
        if not isinstance(o, dict):
            continue
        try:
            if float(o.get('weight', 0) or 0) > 0:
                feats.add('weight')
        except (TypeError, ValueError):
            pass
        if o.get('container') or o.get('openable'):
            feats.add('containers')
        if o.get('wearable'):
            feats.add('wearables')
        if o.get('lit') or o.get('light') or o.get('lightsource'):
            feats.add('lightsource')
    if game.get('timers'):
        feats.add('timers')
    return {'condacts': used_c, 'predicates': used_p, 'features': feats}


def unsupported(game, target):
    """Lo que el juego USA pero el target NO soporta (avisos de paridad).
    Los condacts de hardware se eximen."""
    target = target.lower()
    cap = CAPS.get(target, CAPS['pc'])
    used = scan_game(game)
    return {
        'condacts': sorted((used['condacts'] - cap['condacts']) - HARDWARE_CONDACTS),
        'predicates': sorted(used['predicates'] - cap['predicates']),
        'features': sorted(used['features'] - cap['features']),
    }


def report(game, target):
    """Aviso legible (str) de lo no soportado por el target, o '' si todo va."""
    u = unsupported(game, target)
    if not (u['condacts'] or u['predicates'] or u['features']):
        return ''
    lbl = TARGET_LABEL.get(target.lower(), target)
    out = ['AVISO de compatibilidad — %s no soporta lo siguiente que usa el juego'
           % lbl,
           '(se comportará distinto que en el PC u otras máquinas):']
    if u['condacts']:
        out.append('  · Comandos: ' + ', '.join(u['condacts']))
    if u['predicates']:
        out.append('  · Predicados: ' + ', '.join(u['predicates']))
    if u['features']:
        out.append('  · Funciones: '
                   + '; '.join(FEATURE_LABEL.get(f, f) for f in u['features']))
    return '\n'.join(out)


if __name__ == '__main__':
    import sys
    import yaml
    if len(sys.argv) < 2:
        raise SystemExit('uso: python capabilities.py juego.yaml')
    g = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
    used = scan_game(g)
    print('Usados -> condacts:', ', '.join(sorted(used['condacts'])) or '(ninguno)')
    print('         predicados:', ', '.join(sorted(used['predicates'])) or '(ninguno)')
    print('         funciones:', ', '.join(sorted(used['features'])) or '(ninguna)')
    for t in ('spectrum', 'next', 'cpc'):
        r = report(g, t)
        print('\n=== %s ===' % TARGET_LABEL[t])
        print(r if r else '  OK: todo soportado.')
