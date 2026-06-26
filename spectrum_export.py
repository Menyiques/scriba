#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spectrum_export.py — Exporta un juego Scriba (dict/YAML) a ZX BASIC (Boriel)
para ZX Spectrum 48K, con transpilador de condacts y compresion de textos
por diccionario (tokens 1-2 bytes + pack DEFM accedido por PEEK).

Uso CLI:    python spectrum_export.py juego.yaml salida.bas
Desde el editor: from spectrum_export import export_bas; export_bas(game, path)

Compilar el resultado:
  zxb --tap --BASIC --autorun --org 24000 --heap-size 1792 -O2 salida.bas
"""
import re
import sys
from collections import Counter
import heapq
import paws_lang

# ─── Transliteracion al charset del Spectrum ────────────────────────────
_TR = str.maketrans({
    'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
    'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U',
    '¡': '', '¿': '', '—': '-', '–': '-', '«': "'", '»': "'",
    '“': "'", '”': "'", '’': "'", '…': '...', '·': '-', '━': '-',
    '"': "'",
    '\n': ' ', '\r': ' ', '\t': ' ',
    'ä': 'a', 'ö': 'o', 'Ä': 'A', 'Ö': 'O', 'ß': 'ss',
    'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
    'â': 'a', 'ê': 'e', 'î': 'i', 'ô': 'o', 'û': 'u',
    'ç': 'c', 'Ç': 'C', 'ë': 'e', 'ï': 'i',
    'ã': 'a', 'õ': 'o', 'Ã': 'A', 'Õ': 'O',
    'À': 'A', 'È': 'E', 'Ì': 'I', 'Ò': 'O', 'Ù': 'U',
    'Â': 'A', 'Ê': 'E', 'Î': 'I', 'Ô': 'O', 'Û': 'U',
})
def translit(s):
    """Para VOCABULARIO (nouns/verbs/alias) y comentarios: quita acentos y ñ,
    porque el jugador teclea sin tildes y el parser debe casar igualmente."""
    s = (s or '').translate(_TR)
    s = s.replace('ñ', 'ni').replace('Ñ', 'Ni')
    # solo ASCII imprimible
    s = ''.join(c if 32 <= ord(c) < 127 else '?' for c in s)
    return s


# ─── Transliteracion de DISPLAY (conserva ñ y vocales acentuadas) ───────────
# Cada carácter soportado se mapea a un código 144-159 (UDG A-P). En 32 col se
# pintan como UDGs; en 42/64 col, con los glifos añadidos a print42_es/print64_es.
_ACC_CODE = {
    'á': 144, 'é': 145, 'í': 146, 'ó': 147, 'ú': 148, 'ñ': 149, 'ü': 150,
    '¿': 151, '¡': 152, 'Á': 153, 'É': 154, 'Í': 155, 'Ó': 156, 'Ú': 157,
    'Ñ': 158, 'Ü': 159,
}
# Set PORTUGUES (mismos codigos 144-159, glifos distintos en las fuentes _pt):
# 12 minusculas + 4 mayusculas clave. Las demas mayusculas acentuadas caen a
# letra simple via _TR_DISP_PT.
_ACC_CODE_PT = {
    'á': 144, 'à': 145, 'â': 146, 'ã': 147, 'ç': 148, 'é': 149, 'ê': 150,
    'í': 151, 'ó': 152, 'ô': 153, 'õ': 154, 'ú': 155, 'Á': 156, 'É': 157,
    'Ã': 158, 'Ç': 159,
}
_PT_LANG = False   # lo fija export_bas segun metadata['language'] ('pt')
# Conversiones de display SIN los acentos soportados (esos van por _ACC_CODE).
_TR_DISP = str.maketrans({
    '—': '-', '–': '-', '«': "'", '»': "'", '“': "'", '”': "'", '’': "'",
    '…': '...', '·': '-', '━': '-', '"': "'",
    '\n': ' ', '\r': ' ', '\t': ' ',
    'ä': 'a', 'ö': 'o', 'Ä': 'A', 'Ö': 'O', 'ß': 'ss',
    'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
    'â': 'a', 'ê': 'e', 'î': 'i', 'ô': 'o', 'û': 'u',
    'ç': 'c', 'Ç': 'C', 'ë': 'e', 'ï': 'i',
})

# Transliteracion de DISPLAY para PORTUGUES: conserva los del set _ACC_CODE_PT
# (á à â ã ç é ê í ó ô õ ú Á É Ã Ç); el resto de acentos a letra simple.
_TR_DISP_PT = str.maketrans({
    '—': '-', '–': '-', '«': "'", '»': "'", '“': "'", '”': "'", '’': "'",
    '…': '...', '·': '-', '━': '-', '"': "'",
    '\n': ' ', '\r': ' ', '\t': ' ',
    'ä': 'a', 'ö': 'o', 'Ä': 'A', 'Ö': 'O', 'ß': 'ss', 'ü': 'u', 'Ü': 'U',
    'ñ': 'ni', 'Ñ': 'Ni',
    'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u', 'î': 'i', 'û': 'u', 'ë': 'e', 'ï': 'i',
    'À': 'A', 'Â': 'A', 'Ê': 'E', 'Î': 'I', 'Ô': 'O', 'Û': 'U', 'Õ': 'O',
    'Í': 'I', 'Ó': 'O', 'Ú': 'U', '¿': '?', '¡': '!',
})


def translit_disp(s):
    """Para TEXTO MOSTRADO: conserva los acentos soportados como códigos 144-159
    (set español o portugués según el idioma); el resto no-ASCII se transcribe o
    pasa a '?'."""
    acc = _ACC_CODE_PT if _PT_LANG else _ACC_CODE
    trd = _TR_DISP_PT if _PT_LANG else _TR_DISP
    s = (s or '').translate(trd)
    out = []
    for ch in s:
        if ch in acc:
            out.append(chr(acc[ch]))
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append('?')
    return ''.join(out)

def parrafos(texto, maxlen=230):
    """Divide un texto en parrafos. Respeta los saltos de linea escritos
    en el editor (cada linea sale en su propia linea en pantalla) y trocea
    las lineas largas en trozos <= maxlen cortando por frases."""
    out = []
    for linea in (texto or '').split('\n'):
        linea = ' '.join(translit_disp(linea).split())
        if not linea:
            if out and out[-1] != '':
                out.append('')      # linea en blanco intencionada
            continue
        while len(linea) > maxlen:
            corte = linea.rfind('. ', 0, maxlen)
            if corte < maxlen // 3:
                corte = linea.rfind(' ', 0, maxlen)
            if corte <= 0:
                corte = maxlen
            else:
                corte += 1
            out.append(linea[:corte].strip())
            linea = linea[corte:].strip()
        if linea:
            out.append(linea)
    while out and out[0] == '':
        out.pop(0)
    while out and out[-1] == '':
        out.pop()
    return out

def q(s):
    """Literal ZX BASIC simple (ya transliterado). Se dictariza al .bin, asi que
    los acentos (bytes 144-159) viajan en binario sin problema de codificacion."""
    return '"' + s + '"'


def _qchr(s):
    """Como q() pero para literales INLINE que no se dictarizan (prints con
    variable): los bytes >=128 salen como CHR$(n) porque zxbc lee cp1252."""
    out, buf = [], ''
    for ch in s:
        b = ord(ch)
        if b >= 128:
            if buf:
                out.append('"' + buf + '"')
                buf = ''
            out.append('CHR$(%d)' % b)
        else:
            buf += ch
    if buf or not out:
        out.append('"' + buf + '"')
    return ' + '.join(out)


# Bitmaps 8x8 de los 16 acentos (códigos 144-159) para UDGs en modo 32 col.
_UDG_BYTES = [
    8,16,56,4,60,68,60,0,    8,16,56,68,120,64,60,0,  8,16,0,48,16,16,56,0,
    8,16,56,68,68,68,56,0,   8,16,68,68,68,76,52,0,   40,20,120,68,68,68,68,0,
    0,40,68,68,68,76,52,0,   0,16,0,16,32,68,68,56,   0,16,0,16,16,16,16,16,
    8,56,68,68,124,68,68,0,  8,124,64,120,64,64,124,0, 8,56,16,16,16,16,56,0,
    8,56,68,68,68,68,56,0,   8,84,68,68,68,68,56,0,   40,84,100,84,76,68,68,0,
    0,108,68,68,68,68,56,0,
]

# Bitmaps 8x8 del set PORTUGUES (codigos 144-159): á à â ã ç é ê í ó ô õ ú Á É Ã Ç.
_UDG_BYTES_PT = [
    8,16,56,4,60,68,60,0,    32,16,56,4,60,68,60,0,   16,40,56,4,60,68,60,0,
    40,20,56,4,60,68,60,0,   0,0,56,68,64,68,56,16,   8,16,56,68,120,64,60,0,
    16,40,56,68,120,64,60,0, 8,16,0,48,16,16,56,0,    8,16,56,68,68,68,56,0,
    16,40,56,68,68,68,56,0,  40,20,56,68,68,68,56,0,  8,16,68,68,68,76,52,0,
    8,56,68,68,124,68,68,0,  8,124,64,120,64,64,124,0, 40,20,56,68,124,68,68,0,
    0,56,68,64,64,68,56,16,
]

# ─── Recoleccion de datos del juego ─────────────────────────────────────
DIRS = ['N', 'S', 'E', 'O', 'U', 'D']
LOC_INVEN = 240
LOC_PUESTO = 241
LOC_NADA = 0
CONT_BASE = 100   # contenedores: 100 + indice de objeto contenedor

class Ctx:
    pass

def recolecta(game):
    c = Ctx()
    c.game = game
    c.meta = game.get('metadata', {})
    c.avisos = []

    locs = game.get('locations', {})
    c.locids = list(locs.keys())
    if len(c.locids) > 90:
        raise ValueError('Demasiadas localizaciones para el exportador (max 90)')
    c.locidx = {lid: i + 1 for i, lid in enumerate(c.locids)}

    objs = game.get('objects', {})
    c.objids = list(objs.keys())
    if len(c.objids) > 90:
        raise ValueError('Demasiados objetos para el exportador (max 90)')
    c.objidx = {oid: i + 1 for i, oid in enumerate(c.objids)}

    tims = game.get('timers', {})
    c.timids = list(tims.keys())
    c.timidx = {tid: i + 1 for i, tid in enumerate(c.timids)}

    # posicion inicial de cada objeto
    def locval(loc):
        if not loc or loc == 'NADA':
            return LOC_NADA
        if loc == 'INVEN':
            return LOC_INVEN
        if loc == 'PUESTO':
            return LOC_PUESTO
        if loc in c.locidx:
            return c.locidx[loc]
        if loc in c.objidx:
            return CONT_BASE + c.objidx[loc]
        c.avisos.append(f"objeto en localizacion desconocida '{loc}' -> NADA")
        return LOC_NADA
    c.locval = locval

    # nouns: canonico 5 letras -> id. Objetos primero (id = indice objeto)
    c.nounid = {}
    for oid in c.objids:
        n5 = translit((objs[oid].get('noun') or '')[:5]).upper()
        if n5 and n5 not in c.nounid:
            c.nounid[n5] = c.objidx[oid]
    extra = 100
    for nkey, aliases in (game.get('vocabulary', {}).get('nouns') or {}).items():
        n5 = translit(nkey[:5]).upper()
        if n5 not in c.nounid:
            c.nounid[n5] = extra
            extra += 1
    c.nounid.setdefault('TODO', 95)

    # alias de nouns -> id canonico
    c.nounalias = {}
    for nkey, aliases in (game.get('vocabulary', {}).get('nouns') or {}).items():
        n5 = translit(nkey[:5]).upper()
        nid = c.nounid.get(n5)
        if nid is None:
            continue
        c.nounalias[n5] = nid
        for a in (aliases or []):
            c.nounalias[translit(a[:5]).upper()] = nid
    for oid in c.objids:
        n5 = translit((objs[oid].get('noun') or '')[:5]).upper()
        if n5:
            c.nounalias.setdefault(n5, c.nounid[n5])
    c.nounalias['TODO'] = c.nounid['TODO']
    c.nounalias['ALL'] = c.nounid['TODO']

    # verbos: direcciones 1..6 + resto desde 10
    c.verbid = {'N': 1, 'S': 2, 'E': 3, 'O': 4, 'U': 5, 'D': 6}
    vid = 10
    DIRCANON = {'NORTE': 'N', 'SUR': 'S', 'ESTE': 'E', 'OESTE': 'O',
                'ARRIB': 'U', 'ABAJO': 'D', 'SUBIR': 'U', 'BAJAR': 'D',
                'NORTH': 'N', 'SOUTH': 'S', 'EAST': 'E', 'WEST': 'O',
                'UP': 'U', 'DOWN': 'D'}
    builtins = {
        'EXAMI': ['exami', 'mirar', 'mira', 'ver', 'obser'],
        'COGER': ['coger', 'coge', 'tomar', 'toma', 'agarr', 'recog'],
        'DEJAR': ['dejar', 'deja', 'solta', 'suelt'],
        'PONER': ['poner', 'ponte', 'vesti', 'equip'],
        'QUITA': ['quita', 'desve'],
        'METER': ['meter', 'mete', 'intro'],
        'SACAR': ['sacar', 'saca'],
        'INVEN': ['inven', 'inv', 'i', 'llevo'],
        'PUNT':  ['punto', 'puntu', 'score'],
        'SALIR': ['salir', 'quit', 'exit'],
        'ABRIR': ['abrir', 'abre'],
        'CERRA': ['cerra', 'cierr'],
    }
    c.verbalias = {}
    todos = dict(builtins)
    for vkey, aliases in (game.get('vocabulary', {}).get('verbs') or {}).items():
        v5 = translit(vkey[:5]).upper()
        if v5 in DIRCANON:      # verbos de direccion del juego
            for a in [vkey] + list(aliases or []):
                c.verbalias[translit(a[:5]).upper()] = c.verbid[DIRCANON[v5]]
            continue
        todos.setdefault(v5, [])
        todos[v5] = list(todos[v5]) + list(aliases or [])
    for v5 in todos:
        if v5 not in c.verbid:
            c.verbid[v5] = vid
            vid += 1
    for v5, aliases in todos.items():
        i = c.verbid[v5]
        c.verbalias[v5] = i
        for a in aliases:
            a5 = translit(a[:5]).upper()
            mapped = DIRCANON.get(a5)
            c.verbalias[a5] = c.verbid[mapped] if mapped else i
    # direcciones en claro
    for w, d in [('NORTE', 'N'), ('SUR', 'S'), ('ESTE', 'E'), ('OESTE', 'O'),
                 ('N', 'N'), ('S', 'S'), ('E', 'E'), ('O', 'O'), ('W', 'O'),
                 ('U', 'U'), ('D', 'D'), ('ARRIB', 'U'), ('ABAJO', 'D'),
                 ('SUBIR', 'U'), ('BAJAR', 'D'), ('SUBE', 'U'), ('BAJA', 'D')]:
        c.verbalias[w] = c.verbid[d]

    # variables del juego
    c.vars = {}
    for k, vv in (game.get('variables') or {}).items():
        k = re.sub(r'[^A-Za-z0-9]', '', k)
        c.vars[k] = int(vv) if isinstance(vv, (int, float)) else 0
    for extra_v in ('PUNTOS', 'TURNOS'):
        c.vars.setdefault(extra_v, 0)
    return c

# ─── Transpilador de condacts (mini-BASIC PAWS -> ZX BASIC) ─────────────
_KEYWORDS = {'AT', 'NOTAT', 'CARRIED', 'NOTCARR', 'PRESENT', 'ABSENT',
             'WORN', 'NOTWORN', 'ISAT', 'DARK', 'CHANCE', 'TIMER',
             'ZERO', 'NOTZERO', 'EQ', 'GT', 'LT', 'HASOBJOPEN',
             'VERB', 'NOUN1', 'NOUN2'}

def _vname(c, name):
    name = re.sub(r'[^A-Za-z0-9]', '', name)
    c.vars.setdefault(name, 0)
    return 'Vv' + name

def _objref(c, arg):
    """id de objeto o noun -> indice numerico."""
    if arg in c.objidx:
        return c.objidx[arg]
    a5 = translit(arg[:5]).upper()
    for oid in c.objids:
        n5 = translit((c.game['objects'][oid].get('noun') or '')[:5]).upper()
        if n5 == a5:
            return c.objidx[oid]
    c.avisos.append(f"objeto desconocido en script: '{arg}'")
    return 0

def _pred2zx(c, kw, args):
    """Condición-palabra-clave PAWS -> expresión booleana ZX BASIC.
    (El análisis sintáctico lo hace paws_lang; esto solo mapea cada
    predicado a su forma BASIC.)"""
    if kw == 'AT':
        return f'(l = {c.locidx.get(args[0], 0)})'
    if kw == 'NOTAT':
        return f'(l <> {c.locidx.get(args[0], 0)})'
    if kw == 'CARRIED':
        return f'(carried({_objref(c, args[0])}) = 1)'
    if kw == 'NOTCARR':
        return f'(carried({_objref(c, args[0])}) = 0)'
    if kw == 'PRESENT':
        return f'(presente({_objref(c, args[0])}) = 1)'
    if kw == 'ABSENT':
        return f'(presente({_objref(c, args[0])}) = 0)'
    if kw == 'WORN':
        return f'(oloc({_objref(c, args[0])}) = {LOC_PUESTO})'
    if kw == 'NOTWORN':
        return f'(oloc({_objref(c, args[0])}) <> {LOC_PUESTO})'
    if kw == 'ISAT':
        o = _objref(c, args[0])
        dst = args[1]
        if dst in c.locidx:
            dv = c.locidx[dst]
        elif dst in ('INVEN', 'PUESTO', 'NADA'):
            dv = {'INVEN': LOC_INVEN, 'PUESTO': LOC_PUESTO, 'NADA': LOC_NADA}[dst]
        else:
            dv = CONT_BASE + _objref(c, dst)
        return f'(oloc({o}) = {dv})'
    if kw == 'DARK':
        return '(oscuro() = 1)'
    if kw == 'CHANCE':
        return f'(INT(RND * 100) + 1 <= {args[0]})'
    if kw == 'TIMER':
        return f'(tcur({c.timidx.get(args[0], 0)}) = {args[1]})'
    if kw == 'ZERO':
        return f'({_vname(c, args[0])} = 0)'
    if kw == 'NOTZERO':
        return f'({_vname(c, args[0])} <> 0)'
    if kw == 'EQ':
        return f'({_vname(c, args[0])} = {args[1]})'
    if kw == 'GT':
        return f'({_vname(c, args[0])} > {args[1]})'
    if kw == 'LT':
        return f'({_vname(c, args[0])} < {args[1]})'
    if kw == 'HASOBJOPEN':
        return f'(copen({_objref(c, args[0])}) = 1)'
    if kw == 'VERB':
        p = args[0].upper() if args else '*'
        return '1' if p == '*' else f'(v = {c.verbid.get(p, 0)})'
    if kw == 'NOUN1':
        p = args[0].upper() if args else '*'
        if p == '_':
            return '(n1 = 0)'
        return '1' if p == '*' else f'(n1 = {c.nounid.get(translit(p[:5]).upper(), 0)})'
    if kw == 'NOUN2':
        p = args[0].upper() if args else '*'
        if p == '_':
            return '(n2 = 0)'
        return '1' if p == '*' else f'(n2 = {c.nounid.get(translit(p[:5]).upper(), 0)})'
    c.avisos.append(f'condicion no soportada: {kw} {args}')
    return '1'


class _ZXBackend:
    """Backend de emisión ZX BASIC para paws_lang (var/num/predicate)."""
    def __init__(self, c):
        self.c = c

    def var(self, name):
        return _vname(self.c, name)

    def num(self, n):
        return str(n)

    def predicate(self, kw, args):
        return _pred2zx(self.c, kw, args)


def cond2zx(c, s):
    """Transpila una condición PAWS a ZX BASIC con el parser compartido
    (paws_lang). Idéntica gramática que el intérprete y el validador."""
    try:
        return paws_lang.emit_condition(paws_lang.parse_condition(s), _ZXBackend(c))
    except paws_lang.ParseError as e:
        c.avisos.append(f'condicion con sintaxis invalida {s!r}: {e}')
        return '1'

def _print2zx(c, texto):
    """PRINT "..." con {VAR} -> expresion pw(...)"""
    texto = translit_disp(texto)
    partes = re.split(r'\{([A-Z_][A-Z0-9_]*)\}', texto)
    ql = _qchr if len(partes) > 1 else q
    expr = []
    for i, p in enumerate(partes):
        if i % 2 == 0:
            if p:
                expr.append(ql(p))
        else:
            expr.append(f'STR$({_vname(c, p)})')
    if not expr:
        expr = ['""']
    return 'pw(' + ' + '.join(expr) + ')'

def _extraestr(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s

def stmt2zx(c, linea, dentro_resp):
    """Una sentencia PAWS -> lista de lineas ZX BASIC."""
    partes = linea.strip().split(None, 1)
    if not partes:
        return []
    cmd = partes[0].upper()
    resto = partes[1].strip() if len(partes) > 1 else ''
    if cmd in ('PRINT', 'PRINTLN'):
        return [_print2zx(c, _extraestr(resto))]
    if cmd == 'LET':
        if '=' in resto:
            lhs, rhs = resto.split('=', 1)
            try:
                rhs_zx = paws_lang.emit_expr(paws_lang.parse_expr(rhs), _ZXBackend(c))
            except paws_lang.ParseError as e:
                c.avisos.append(f'expresion LET invalida {rhs!r}: {e}')
                rhs_zx = '0'
            return [f'{_vname(c, lhs.strip())} = {rhs_zx}']
        return []
    if cmd == 'ADDSCORE':
        return [f'addsc({resto.strip()})']
    if cmd == 'GOTO':
        idx = c.locidx.get(resto.strip(), 0)
        return [f'irA({idx})']
    if cmd == 'DESC':
        return ['descL()']
    if cmd == 'SCORE':
        return ['verPts()']
    if cmd == 'END':
        return ['gameOver()', 'RETURN']
    if cmd == 'QUIT':
        return ['fin = 1', 'RETURN']
    if cmd == 'NEWLINE':
        return ['pnl()']
    if cmd == 'BEEP':
        # BEEP duracion, tono -> se traslada literal a ZX BASIC (Boriel)
        return [f'BEEP {resto}']
    if cmd == 'BORDER':
        # BORDER n (0-7) -> literal a ZX BASIC
        return [f'BORDER {resto}']
    if cmd == 'PAUSE':
        # PAUSE n (frames; 0 = esperar tecla) -> literal a ZX BASIC
        return [f'PAUSE {resto}']
    if cmd in ('INK', 'PAPER', 'BRIGHT', 'FLASH', 'INVERSE'):
        # INK/PAPER n (0-7), BRIGHT/FLASH/INVERSE n (0/1) -> literal a ZX BASIC
        return [f'{cmd} {resto}']
    if cmd == 'CLS':
        # CLS -> literal a ZX BASIC (borra la pantalla)
        return ['CLS']
    if cmd == 'MATCH':
        return (['hnd = 1', 'RETURN'] if dentro_resp else [])
    if cmd == 'REM':
        return ["' " + translit(resto)]
    if cmd == 'GET':
        return [f'oloc({_objref(c, resto)}) = {LOC_INVEN}']
    if cmd == 'DROP':
        return [f'oloc({_objref(c, resto)}) = l']
    if cmd == 'WEAR':
        return [f'oloc({_objref(c, resto)}) = {LOC_PUESTO}']
    if cmd == 'REMOVE':
        return [f'oloc({_objref(c, resto)}) = {LOC_INVEN}']
    if cmd == 'DESTROY':
        return [f'oloc({_objref(c, resto)}) = {LOC_NADA}']
    if cmd in ('CREATE', 'PUT'):
        a = resto.split()
        o = _objref(c, a[0])
        return [f'oloc({o}) = {c.locval(a[1])}']
    if cmd == 'PUTIN':
        a = resto.split()
        return [f'oloc({_objref(c, a[0])}) = {CONT_BASE + _objref(c, a[1])}']
    if cmd == 'TAKEOUT':
        a = resto.split()
        return [f'oloc({_objref(c, a[0])}) = {LOC_INVEN}']
    if cmd == 'LIT':
        return [f'olit({_objref(c, resto)}) = 1']
    if cmd == 'UNLIT':
        return [f'olit({_objref(c, resto)}) = 0']
    if cmd == 'OPEN':
        o = _objref(c, resto)
        return [f'copen({o}) = 1', f'olock({o}) = 0']
    if cmd == 'CLOSE':
        return [f'copen({_objref(c, resto)}) = 0']
    if cmd == 'LOCK':
        return [f'olock({_objref(c, resto)}) = 1']
    if cmd == 'UNLOCK':
        return [f'olock({_objref(c, resto)}) = 0']
    if cmd == 'TIMER_START':
        t = c.timidx.get(resto.strip(), 0)
        return [f'tact({t}) = 1', f'tcur({t}) = tdur({t})']
    if cmd == 'TIMER_STOP':
        return [f'tact({c.timidx.get(resto.strip(), 0)}) = 0']
    if cmd == 'TIMER_RESET':
        t = c.timidx.get(resto.strip(), 0)
        return [f'tcur({t}) = tdur({t})']
    if cmd == 'PLAY':
        # PLAY "nombre" (o PLAY n) -> reproduce el efecto FX por el AY. El
        # reproductor (playfx) solo se inyecta si el juego usa PLAY; en 48K (sin
        # AY) es mudo. El nombre se resuelve al índice 1-based de la lista de FX.
        import fx_engine
        ni = fx_engine.fx_index((c.game.get('fx') or []), resto.strip())
        if not ni:
            c.avisos.append(f'PLAY: efecto no encontrado {resto.strip()!r}')
            return []
        return [f'playfx({ni})']
    c.avisos.append(f'comando no soportado: {linea!r}')
    return ["' ?? " + translit(linea)]

def _on_cond_zx(c, var, slot, kind):
    """Condición ZX para un hueco de ON (var = v/n1/n2). slot: '*' | '_' |
    lista de alternativas. kind: 'verb' o 'noun'. Devuelve None si '*'."""
    if slot == '*':
        return None
    if slot == '_':
        return f'{var} = 0'

    def ident(tok):
        if kind == 'verb':
            return c.verbid.get(tok, c.verbalias.get(tok, 0))
        return c.nounid.get(translit(tok[:5]).upper(), 0)

    ids = [ident(t) for t in slot]
    if len(ids) == 1:
        return f'{var} = {ids[0]}'
    return '(' + ' OR '.join(f'{var} = {i}' for i in ids) + ')'


def script2zx(c, script, dentro_resp, ind='    '):
    """Transpila un script PAWS completo a lineas ZX BASIC."""
    if isinstance(script, list):
        if script and not isinstance(script[0], str):
            c.avisos.append('bloque JSON legacy ignorado')
            return []
        lineas = list(script)
    elif isinstance(script, str):
        lineas = script.split('\n')
    else:
        return []
    # quitar numeros de linea y vacias
    prog = []
    for ln in lineas:
        ln = ln.strip()
        if not ln:
            continue
        p = ln.split(None, 1)
        if p[0].isdigit():
            ln = p[1].strip() if len(p) > 1 else ''
        if ln:
            prog.append(ln)
    out = []
    nivel = [0]

    def emite(s):
        out.append(ind + '    ' * nivel[0] + s)

    i = 0
    def bloque(hasta):
        nonlocal i
        while i < len(prog):
            ln = prog[i]
            up = ln.upper()
            if up in hasta:
                return ln
            i += 1
            if up.startswith('IF ') and ' THEN' in up:
                idx = up.rfind(' THEN')
                cond = ln[3:idx].strip()
                emite('IF ' + cond2zx(c, cond) + ' THEN')
                nivel[0] += 1
                fin = bloque(('ELSE', 'ENDIF'))
                if fin and fin.upper() == 'ELSE':
                    i += 1
                    nivel[0] -= 1
                    emite('ELSE')
                    nivel[0] += 1
                    fin = bloque(('ENDIF',))
                if fin:
                    i += 1
                nivel[0] -= 1
                emite('END IF')
            elif up.startswith('ON '):
                pa = ln.split(None, 1)
                s = paws_lang.parse_on(pa[1] if len(pa) > 1 else '')
                conds = []
                for var, slot, kind in (('v', s[0], 'verb'),
                                        ('n1', s[1], 'noun'),
                                        ('n2', s[2], 'noun')):
                    cnd = _on_cond_zx(c, var, slot, kind)
                    if cnd:
                        conds.append(cnd)
                emite('IF ' + (' AND '.join(conds) if conds else '1') + ' THEN')
                nivel[0] += 1
                fin = bloque(('ENDON',))
                if fin:
                    i += 1
                nivel[0] -= 1
                emite('END IF')
                if dentro_resp:
                    emite('IF hnd = 1 THEN RETURN')
            else:
                for s in stmt2zx(c, ln, dentro_resp):
                    emite(s)
        return None
    bloque(())
    return out

# ─── Generacion del fuente ZX BASIC ──────────────────────────────────────
def _alias_por_id(aliases):
    porid = {}
    for w, i in aliases.items():
        if w:
            porid.setdefault(i, []).append(w)
    return porid

def _chain_id(fn_name, porid, default=0):
    out = [f'FUNCTION {fn_name}(w$ AS STRING) AS UBYTE']
    for i, palabras in sorted(porid.items()):
        palabras = sorted(set(palabras))
        for k in range(0, len(palabras), 4):
            grupo = palabras[k:k+4]
            cond = ' OR '.join(f'w$ = "{w}"' for w in grupo)
            out.append(f'    IF {cond} THEN RETURN {i}')
    out.append(f'    RETURN {default}')
    out.append('END FUNCTION')
    return out

def genera_fuente(c):
    g = c.game
    L = []
    nlocs = len(c.locids)
    nobjs = len(c.objids)
    ntims = max(1, len(c.timids))
    titulo = translit_disp(c.meta.get('title', 'Aventura'))

    L.append("' " + "=" * 60)
    L.append(f"' {titulo} - ZX Spectrum 48K")
    L.append("' Generado por Scriba (motor + juego + compresion)")
    L.append("' Compilar:")
    L.append("'   zxb --tap --BASIC --autorun --org 24000 --heap-size 1792 --array-base=0 --string-base=0 -O2 <este.bas>")
    L.append("' " + "=" * 60)
    L.append('')
    L.append('#include <print64.bas>')
    L.append('#include <winscroll.bas>')
    L.append('')
    # Predeclaración: oscuro() se usa en rutinas que aparecen antes de su
    # definición (p.ej. el bloque de imágenes), así Boriel la resuelve.
    L.append('DECLARE FUNCTION oscuro () AS UBYTE')
    L.append('')
    L.append("' ---------- ESTADO ----------")
    L.append('DIM crow AS UBYTE')
    L.append('DIM ccol AS UBYTE')
    L.append(f'DIM ex({nlocs}, 5) AS UBYTE')
    L.append(f'DIM ldark({nlocs}) AS UBYTE')
    for arr in ('oloc', 'oini', 'olit', 'copen', 'olock', 'ofix',
                'owear', 'olight', 'oable', 'obnoun', 'okey', 'owght'):
        L.append(f'DIM {arr}({nobjs}) AS UBYTE')
    for arr in ('tact', 'tloop'):
        L.append(f'DIM {arr}({ntims}) AS UBYTE')
    for arr in ('tcur', 'tdur'):
        L.append(f'DIM {arr}({ntims}) AS INTEGER')
    L.append('DIM l AS UBYTE')
    L.append('DIM v AS UBYTE')
    L.append('DIM n1 AS UBYTE')
    L.append('DIM n2 AS UBYTE')
    L.append('DIM hnd AS UBYTE')
    L.append('DIM fin AS UBYTE')
    for k in sorted(c.vars):
        L.append(f'DIM Vv{k} AS INTEGER')
    L.append('')
    L.append("'@DICCIONARIO@")
    L.append('')
    L.append("' ---------- SALIDA 64 COLUMNAS CON SCROLL ----------")
    L.append("""SUB limpia()
    CLS
    crow = 0: ccol = 0
END SUB

SUB pgchk()
    DO WHILE crow > 23
        WinScrollUp(0, 0, 32, 24)
        crow = crow - 1
    LOOP
END SUB

SUB pri(t$ AS STRING)
    pgchk()
    printat64(crow, ccol)
    print64(t$)
    ccol = ccol + LEN(t$)
END SUB

SUB pnl()
    crow = crow + 1
    ccol = 0
END SUB

SUB pw(t$ AS STRING)
    DIM avail AS UBYTE
    DIM cut AS UBYTE
    DIM j AS UBYTE
    t$ = pex(t$)
    DO
        avail = 64 - ccol
        IF LEN(t$) <= avail THEN
            pri(t$): pnl()
            RETURN
        END IF
        cut = 0
        FOR j = 1 TO avail
            IF j < LEN(t$) THEN
                IF CODE(t$(j)) = 32 THEN cut = j
            END IF
        NEXT j
        IF cut = 0 THEN
            pri(t$(0 TO avail - 1)): pnl()
            t$ = t$(avail TO )
        ELSE
            pri(t$(0 TO cut - 1)): pnl()
            t$ = t$(cut + 1 TO )
        END IF
    LOOP
END SUB""")
    L.append('')

    # ── datos: salidas y flags de localizacion ──
    L.append("' ---------- DATOS DEL MAPA ----------")
    L.append('SUB initMapa()')
    L.append('    DIM i AS UBYTE')
    L.append('    DIM j AS UBYTE')
    L.append(f'    FOR i = 1 TO {nlocs}')
    L.append('        FOR j = 0 TO 5')
    L.append('            READ ex(i, j)')
    L.append('        NEXT j')
    L.append('    NEXT i')
    for lid in c.locids:
        if g['locations'][lid].get('dark'):
            L.append(f'    ldark({c.locidx[lid]}) = 1')
    L.append('END SUB')
    L.append('')
    L.append('mapdata:')
    for lid in c.locids:
        exs = g['locations'][lid].get('exits') or {}
        fila = ','.join(str(c.locidx.get(exs.get(d) or '', 0)) for d in DIRS)
        L.append('DATA ' + fila)
    L.append("'@DICDATA@")
    L.append('')

    # ── objetos ──
    L.append('SUB initObj()')
    L.append('    DIM i AS UBYTE')
    for oid in c.objids:
        o = g['objects'][oid]
        i = c.objidx[oid]
        sets = [f'oloc({i}) = {c.locval(o.get("location"))}']
        n5 = translit((o.get('noun') or '')[:5]).upper()
        if n5 and n5 in c.nounid:
            sets.append(f'obnoun({i}) = {c.nounid[n5]}')
        if 'fixed' in (o.get('attributes') or []):
            sets.append(f'ofix({i}) = 1')
        if o.get('wearable'):
            sets.append(f'owear({i}) = 1')
        if o.get('light_source'):
            sets.append(f'olight({i}) = 1')
        if o.get('lit'):
            sets.append(f'olit({i}) = 1')
        if o.get('container') or o.get('openable'):
            if o.get('openable'):
                sets.append(f'oable({i}) = 1')
            if o.get('open'):
                sets.append(f'copen({i}) = 1')
            if o.get('locked'):
                sets.append(f'olock({i}) = 1')
            k = o.get('key')
            if k and k in c.objidx:
                sets.append(f'okey({i}) = {c.objidx[k]}')
        w = int(o.get('weight', 0) or 0)
        if w:
            sets.append(f'owght({i}) = {w & 0xFF}')
        L.append('    ' + ': '.join(sets))
    L.append(f'    FOR i = 1 TO {nobjs}')
    L.append('        oini(i) = oloc(i)')
    L.append('    NEXT i')
    # timers
    for tid in c.timids:
        t = g['timers'][tid]
        i = c.timidx[tid]
        L.append(f'    tdur({i}) = {int(t.get("turns", 10))}')
        if t.get('loop'):
            L.append(f'    tloop({i}) = 1')
        if t.get('active'):
            L.append(f'    tact({i}) = 1: tcur({i}) = tdur({i})')
    # variables iniciales
    for k in sorted(c.vars):
        if c.vars[k]:
            L.append(f'    Vv{k} = {c.vars[k]}')
    L.append('END SUB')
    L.append('')

    # ── utilidades ──
    L.append(f"""' ---------- UTILIDADES ----------
FUNCTION carried(i AS UBYTE) AS UBYTE
    IF oloc(i) = {LOC_INVEN} OR oloc(i) = {LOC_PUESTO} THEN RETURN 1
    RETURN 0
END FUNCTION

FUNCTION presente(i AS UBYTE) AS UBYTE
    DIM h AS UBYTE
    IF carried(i) = 1 OR oloc(i) = l THEN RETURN 1
    IF oloc(i) >= {CONT_BASE} AND oloc(i) < {LOC_INVEN} THEN
        h = oloc(i) - {CONT_BASE}
        IF copen(h) = 1 AND (oloc(h) = l OR carried(h) = 1) THEN RETURN 1
    END IF
    RETURN 0
END FUNCTION

FUNCTION oscuro() AS UBYTE
    DIM i AS UBYTE
    IF ldark(l) = 0 THEN RETURN 0
    FOR i = 1 TO {len(c.objids)}
        IF olight(i) = 1 AND olit(i) = 1 THEN
            IF carried(i) = 1 OR oloc(i) = l THEN RETURN 0
        END IF
    NEXT i
    RETURN 1
END FUNCTION

FUNCTION porNoun(nid AS UBYTE) AS UBYTE
    DIM i AS UBYTE
    FOR i = 1 TO {len(c.objids)}
        IF obnoun(i) = nid AND carried(i) = 1 THEN RETURN i
    NEXT i
    FOR i = 1 TO {len(c.objids)}
        IF obnoun(i) = nid AND presente(i) = 1 THEN RETURN i
    NEXT i
    RETURN 0
END FUNCTION

SUB addsc(n AS UBYTE)
    VvPUNTOS = VvPUNTOS + n
    pw("[+" + STR$(n) + " puntos]")
END SUB

SUB verPts()
    pw("Puntuacion: " + STR$(VvPUNTOS) + "/{int(c.meta.get('max_score', 0))}")
END SUB

SUB gameOver()
    pnl()
    pw("== FIN DEL JUEGO - Puntuacion: " + STR$(VvPUNTOS) + "/{int(c.meta.get('max_score', 0))} ==")
    fin = 1
END SUB""")
    L.append('')
    return L

def genera_fuente2(c, L):
    """Parte 2: descripciones, examinar, parser, builtins, condacts, main."""
    g = c.game
    nobjs = len(c.objids)

    # ── mensajes iniciales de objetos ──
    L.append('SUB msgIni(i AS UBYTE)')
    primero = True
    for oid in c.objids:
        o = g['objects'][oid]
        msg = o.get('initial_message')
        if msg:
            kw = 'IF' if primero else 'ELSEIF'
            primero = False
            L.append(f'    {kw} i = {c.objidx[oid]} THEN')
            for p in parrafos(msg):
                L.append(f'        pw({q(p)})')
    if primero:
        # Ningún objeto tiene initial_message: sin IF (Boriel no admite THEN vacío)
        L.append('    pw("Aqui hay " + onomW$(i) + ".")')
    else:
        L.append('    ELSE')
        L.append('        pw("Aqui hay " + onomW$(i) + ".")')
        L.append('    END IF')
    L.append('END SUB')
    L.append('')

    # tieneMsg
    con_msg = [str(c.objidx[oid]) for oid in c.objids
               if g['objects'][oid].get('initial_message')]
    L.append('FUNCTION tieneMsg(i AS UBYTE) AS UBYTE')
    for k in range(0, len(con_msg), 8):
        cond = ' OR '.join(f'i = {x}' for x in con_msg[k:k+8])
        L.append(f'    IF {cond} THEN RETURN 1')
    L.append('    RETURN 0')
    L.append('END FUNCTION')
    L.append('')

    # ── descripciones de localizacion ──
    L.append('SUB descL()')
    L.append('    DIM i AS UBYTE')
    L.append('    pnl()')
    for k, lid in enumerate(c.locids):
        loc = g['locations'][lid]
        kw = 'IF' if k == 0 else 'ELSEIF'
        L.append(f'    {kw} l = {c.locidx[lid]} THEN')
        L.append(f'        pw({q(translit_disp(loc.get("name", lid).upper()))})')
        if loc.get('dark'):
            L.append('        IF oscuro() = 1 THEN')
            L.append('            pw("Esta completamente oscuro. No puedes ver nada.")')
            L.append('            RETURN')
            L.append('        END IF')
        for p in parrafos(loc.get('description', '')):
            L.append(f'        pw({q(p)})')
    L.append('    END IF')
    # objetos visibles
    L.append(f'    FOR i = 1 TO {nobjs}')
    L.append('        IF oloc(i) = l THEN')
    L.append('            IF ofix(i) = 1 THEN')
    L.append('                IF tieneMsg(i) = 1 THEN msgIni(i)')
    L.append('            ELSEIF oloc(i) = oini(i) THEN')
    L.append('                msgIni(i)')
    L.append('            ELSE')
    L.append('                pw("Aqui hay " + onomW$(i) + ".")')
    L.append('            END IF')
    L.append('        END IF')
    L.append('    NEXT i')
    L.append('    pri("Salidas:")')
    for d, et in zip(range(6), (' N', ' S', ' E', ' O', ' Subir', ' Bajar')):
        L.append(f'    IF ex(l, {d}) > 0 THEN pri("{et}")')
    L.append('    pnl()')
    L.append('END SUB')
    L.append('')
    # ── examinar ──
    L.append('SUB exDesc(i AS UBYTE)')
    primero = True
    for oid in c.objids:
        d = g['objects'][oid].get('description')
        if not d:
            continue
        kw = 'IF' if primero else 'ELSEIF'
        primero = False
        L.append(f'    {kw} i = {c.objidx[oid]} THEN')
        for p in parrafos(d):
            L.append(f'        pw({q(p)})')
    if primero:
        L.append('    IF 0 THEN')
    L.append('    ELSE')
    L.append('        pw("No ves nada especial.")')
    L.append('    END IF')
    L.append('END SUB')
    L.append('')

    # ── parser ──
    L.extend(_chain_id('verbId', _alias_por_id(c.verbalias)))
    L.append('')
    L.extend(_chain_id('nounId', _alias_por_id(c.nounalias)))
    L.append('')
    L.append("""SUB parse(li$ AS STRING)
    DIM i AS UBYTE
    DIM ch AS UBYTE
    DIM w$ AS STRING
    DIM t AS UBYTE
    v = 0: n1 = 0: n2 = 0
    w$ = ""
    FOR i = 0 TO LEN(li$)
        IF i = LEN(li$) THEN
            ch = 32
        ELSE
            ch = CODE(li$(i))
            IF ch > 96 AND ch < 123 THEN ch = ch - 32
        END IF
        IF ch = 32 THEN
            IF LEN(w$) > 0 THEN
                IF LEN(w$) > 5 THEN w$ = w$(0 TO 4)
                t = verbId(w$)
                IF t > 0 AND v = 0 THEN
                    v = t
                ELSE
                    t = nounId(w$)
                    IF t > 0 THEN
                        IF n1 = 0 THEN
                            n1 = t
                        ELSEIF n2 = 0 THEN
                            n2 = t
                        END IF
                    END IF
                END IF
                w$ = ""
            END IF
        ELSE
            w$ = w$ + CHR$(ch)
        END IF
    NEXT i
END SUB

FUNCTION leeLinea$() AS STRING
    DIM s$ AS STRING
    DIM k$ AS STRING
    DIM ch AS UBYTE
    s$ = ""
    pri("> ")
    DO
        PAUSE 0
        k$ = INKEY$
        IF LEN(k$) = 1 THEN
            ch = CODE(k$)
            IF ch = 13 THEN
                pnl()
                RETURN s$
            ELSEIF ch = 12 THEN
                IF LEN(s$) > 0 THEN
                    s$ = s$(0 TO LEN(s$) - 2)
                    ccol = ccol - 1
                    printat64(crow, ccol)
                    print64(" ")
                END IF
            ELSEIF ch >= 32 AND ch < 128 AND LEN(s$) < 60 THEN
                s$ = s$ + k$
                pri(k$)
            END IF
        END IF
    LOOP
END FUNCTION""")
    L.append('')
    return L

def genera_fuente3(c, L):
    g = c.game
    nobjs = len(c.objids)
    cond = g.get('condacts', {}) or {}

    # ── on_enter por localizacion ──
    enters = {}
    for lid in c.locids:
        sc = g['locations'][lid].get('on_enter')
        cuerpo = script2zx(c, sc, False) if sc else []
        if cuerpo:
            enters[c.locidx[lid]] = cuerpo
    L.append('SUB onEnter()')
    if enters:
        for k, (idx, cuerpo) in enumerate(sorted(enters.items())):
            kw = 'IF' if k == 0 else 'ELSEIF'
            L.append(f'    {kw} l = {idx} THEN')
            L.extend('    ' + x for x in cuerpo)
        L.append('    END IF')
    L.append('END SUB')
    L.append('')
    L.append("""SUB irA(d AS UBYTE)
    l = d
    onEnter()
END SUB

SUB mueve(d AS UBYTE)
    DIM dest AS UBYTE
    dest = ex(l, d)
    IF dest = 0 THEN
        pw("No puedes ir en esa direccion.")
        RETURN
    END IF
    l = dest
    descL()
    onEnter()
END SUB""")
    L.append('')

    # ── timers: on_expire ──
    for tid in c.timids:
        sc = g['timers'][tid].get('on_expire')
        L.append(f'SUB texp{c.timidx[tid]}()')
        L.extend(script2zx(c, sc, False))
        L.append('END SUB')
        L.append('')
    L.append('SUB tick()')
    for tid in c.timids:
        i = c.timidx[tid]
        L.append(f'    IF tact({i}) = 1 THEN')
        L.append(f'        tcur({i}) = tcur({i}) - 1')
        L.append(f'        IF tcur({i}) <= 0 THEN')
        L.append(f'            texp{i}()')
        L.append(f'            IF tloop({i}) = 1 THEN')
        L.append(f'                tcur({i}) = tdur({i})')
        L.append('            ELSE')
        L.append(f'                tact({i}) = 0')
        L.append('            END IF')
        L.append('        END IF')
        L.append('    END IF')
    L.append('END SUB')
    L.append('')

    # ── condact subs ──
    for nombre, clave in (('onStart', 'on_start'), ('beforeT', 'before_turn'),
                          ('afterT', 'after_turn')):
        L.append(f'SUB {nombre}()')
        L.extend(script2zx(c, cond.get(clave), False))
        L.append('END SUB')
        L.append('')
    L.append('SUB resp()')
    L.append('    hnd = 0')
    L.extend(script2zx(c, cond.get('responses'), True))
    L.append('END SUB')
    L.append('')
    return L

def genera_fuente4(c, L):
    """Builtins + bucle principal."""
    g = c.game
    nobjs = len(c.objids)
    titulo = translit_disp(c.meta.get('title', 'Aventura'))
    start = c.locidx.get(c.meta.get('start_location'), 1)
    TODO = c.nounid['TODO']
    # Limite de peso: solo si el juego define la variable LLEVAR_MAX (si no, 0 =
    # sin limite). pesoLlevado() suma el peso de lo que se lleva o se viste.
    maxexpr = '0'
    for _k in (g.get('variables') or {}):
        if re.sub(r'[^A-Za-z0-9]', '', _k).upper() == 'LLEVARMAX':
            maxexpr = 'Vv' + re.sub(r'[^A-Za-z0-9]', '', _k)
            break

    L.append(f"""' ---------- BUILTINS ----------
FUNCTION pesoLlevado() AS UINTEGER
    DIM i AS UBYTE
    DIM p AS UINTEGER
    p = 0
    FOR i = 1 TO {nobjs}
        IF carried(i) = 1 THEN p = p + owght(i)
    NEXT i
    RETURN p
END FUNCTION
SUB engCoge(i AS UBYTE)
    IF carried(i) = 1 THEN
        pw("Ya lo llevas."): RETURN
    END IF
    IF ofix(i) = 1 THEN
        pw("No puedes coger eso."): RETURN
    END IF
    IF {maxexpr} > 0 AND pesoLlevado() + owght(i) > {maxexpr} THEN
        pw("Llevas demasiado peso."): RETURN
    END IF
    oloc(i) = {LOC_INVEN}
    pw("Coges " + onomW$(i) + ".")
END SUB

SUB engDeja(i AS UBYTE)
    IF carried(i) = 0 THEN
        pw("No lo llevas."): RETURN
    END IF
    oloc(i) = l
    pw("Dejas " + onomW$(i) + ".")
END SUB

SUB builtins()
    DIM i AS UBYTE
    DIM o AS UBYTE
    IF v >= 1 AND v <= 6 THEN
        mueve(v - 1)
        RETURN
    END IF
    IF v = {c.verbid.get('INVEN', 0)} THEN
        o = 0
        FOR i = 1 TO {nobjs}
            IF oloc(i) = {LOC_INVEN} THEN
                IF o = 0 THEN pw("Llevas:"): o = 1
                pw("  " + onomW$(i))
            END IF
        NEXT i
        FOR i = 1 TO {nobjs}
            IF oloc(i) = {LOC_PUESTO} THEN
                IF o = 0 THEN o = 1
                pw("Llevas puesto: " + onomW$(i))
            END IF
        NEXT i
        IF o = 0 THEN pw("No llevas nada.")
        RETURN
    END IF
    IF v = {c.verbid.get('PUNT', 0)} THEN
        verPts()
        RETURN
    END IF
    IF v = {c.verbid.get('SALIR', 0)} THEN
        pw("Abandonas la aventura.")
        gameOver()
        RETURN
    END IF
    IF v = {c.verbid.get('EXAMI', 0)} THEN
        IF oscuro() = 1 THEN
            pw("Esta demasiado oscuro para ver nada."): RETURN
        END IF
        IF n1 = 0 THEN descL(): RETURN
        o = porNoun(n1)
        IF o = 0 THEN
            pw("No ves eso aqui.")
        ELSE
            exDesc(o)
        END IF
        RETURN
    END IF
    IF v = {c.verbid.get('COGER', 0)} THEN
        IF n1 = {TODO} THEN
            IF oscuro() = 1 THEN
                pw("Esta demasiado oscuro para ver que hay."): RETURN
            END IF
            o = 0
            FOR i = 1 TO {nobjs}
                IF oloc(i) = l AND ofix(i) = 0 THEN
                    o = 1
                    engCoge(i)
                ELSEIF presente(i) = 1 AND oloc(i) >= {CONT_BASE} AND oloc(i) < {LOC_INVEN} THEN
                    o = 1
                    engCoge(i)
                END IF
            NEXT i
            IF o = 0 THEN pw("No ves nada que puedas coger aqui.")
            RETURN
        END IF
        IF n1 = 0 THEN pw("Que quieres coger?"): RETURN
        o = porNoun(n1)
        IF o = 0 THEN pw("No ves eso aqui."): RETURN
        engCoge(o)
        RETURN
    END IF
    IF v = {c.verbid.get('DEJAR', 0)} THEN
        IF n1 = {TODO} THEN
            o = 0
            FOR i = 1 TO {nobjs}
                IF oloc(i) = {LOC_INVEN} THEN
                    o = 1
                    engDeja(i)
                END IF
            NEXT i
            IF o = 0 THEN pw("No llevas nada que dejar.")
            RETURN
        END IF
        IF n1 = 0 THEN pw("Que quieres dejar?"): RETURN
        o = porNoun(n1)
        IF o = 0 OR carried(o) = 0 THEN pw("No llevas eso."): RETURN
        engDeja(o)
        RETURN
    END IF
    IF v = {c.verbid.get('PONER', 0)} THEN
        o = porNoun(n1)
        IF o = 0 OR oloc(o) <> {LOC_INVEN} THEN
            pw("No llevas eso."): RETURN
        END IF
        IF owear(o) = 0 THEN
            pw("No puedes ponerte eso."): RETURN
        END IF
        oloc(o) = {LOC_PUESTO}
        pw("Te pones " + onomW$(o) + ".")
        RETURN
    END IF
    IF v = {c.verbid.get('QUITA', 0)} THEN
        o = porNoun(n1)
        IF o = 0 OR oloc(o) <> {LOC_PUESTO} THEN
            pw("No llevas puesto eso."): RETURN
        END IF
        oloc(o) = {LOC_INVEN}
        pw("Te quitas " + onomW$(o) + ".")
        RETURN
    END IF
    IF v = {c.verbid.get('ABRIR', 0)} THEN
        o = porNoun(n1)
        IF o = 0 THEN pw("No ves eso aqui."): RETURN
        IF oable(o) = 0 THEN pw("No puedes abrir eso."): RETURN
        IF copen(o) = 1 THEN pw("Ya esta abierto."): RETURN
        IF olock(o) = 1 THEN
            IF okey(o) > 0 AND carried(okey(o)) = 1 THEN
                olock(o) = 0
                copen(o) = 1
                pw("Lo abres con " + onomW$(okey(o)) + ".")
            ELSE
                pw("Esta cerrado con llave.")
            END IF
            RETURN
        END IF
        copen(o) = 1
        pw("Abierto.")
        RETURN
    END IF
    IF v = {c.verbid.get('CERRA', 0)} THEN
        o = porNoun(n1)
        IF o = 0 THEN pw("No ves eso aqui."): RETURN
        IF oable(o) = 0 OR copen(o) = 0 THEN pw("Ya esta cerrado."): RETURN
        copen(o) = 0
        pw("Cerrado.")
        RETURN
    END IF
    IF v = {c.verbid.get('METER', 0)} THEN
        o = porNoun(n1)
        i = porNoun(n2)
        IF o = 0 OR i = 0 OR carried(o) = 0 THEN
            pw("No puedes hacer eso."): RETURN
        END IF
        IF copen(i) = 0 THEN pw("Esta cerrado."): RETURN
        oloc(o) = {CONT_BASE} + i
        pw("Metes " + onomW$(o) + ".")
        RETURN
    END IF
    IF v = {c.verbid.get('SACAR', 0)} THEN
        o = porNoun(n1)
        IF o = 0 OR presente(o) = 0 OR oloc(o) < {CONT_BASE} OR oloc(o) >= {LOC_INVEN} THEN
            pw("No esta en ningun contenedor."): RETURN
        END IF
        oloc(o) = {LOC_INVEN}
        pw("Sacas " + onomW$(o) + ".")
        RETURN
    END IF
    pw("No puedes hacer eso.")
END SUB""")
    L.append('')

    # ── main ──
    msg_inicio = parrafos(c.meta.get('start_message', ''))
    L.append("' ---------- PRINCIPAL ----------")
    L.append('DIM li$ AS STRING')
    L.append('')
    L.append('initDic()')
    L.append('')
    L.append("' al terminar la partida se vuelve aqui")
    L.append('reinicio:')
    L.append('RESTORE mapdata')
    L.append('fin = 0')
    for k in sorted(c.vars):
        L.append(f'Vv{k} = 0')
    L.append('initMapa()')
    L.append('initObj()')
    L.append(f'l = {start}')
    L.append('limpia()')
    L.append('onStart()')   # tras la presentacion, ANTES del mensaje inicial
    for p in msg_inicio:
        L.append(f'pw({q(p)})')
    if msg_inicio:
        L.append('PAUSE 0')   # espera tecla para leer el mensaje inicial
    L.append('descL()')
    L.append('onEnter()')
    L.append('')
    L.append("""DO
    pnl()
    li$ = leeLinea$()
    IF LEN(li$) > 0 AND fin = 0 THEN
        beforeT()
        IF fin = 0 THEN
            parse(li$)
            IF v = 0 THEN
                pw("No entiendo eso.")
            ELSE
                resp()
                IF fin = 0 AND hnd = 0 THEN
                    builtins()
                END IF
            END IF
        END IF
        IF fin = 0 THEN tick()
        IF fin = 0 THEN afterT()
    END IF
LOOP UNTIL fin = 1

pw("Pulsa una tecla...")
PAUSE 0
GOTO reinicio""")
    return L


# ─── ZX0 v2: puerto fiel del compresor oficial (Einar Saukas) ────────────
# Salida identica byte a byte al zx0 C oficial; verificado contra el
# descompresor canonico dzx0_standard.asm mediante simulacion exacta.

class _ZB(object):
    __slots__ = ('bits', 'index', 'offset', 'chain')
    def __init__(self, bits, index, offset, chain):
        self.bits = bits; self.index = index
        self.offset = offset; self.chain = chain

def _egbits(value):
    bits = 1
    while True:
        value >>= 1
        if not value:
            return bits
        bits += 2

def _zx0_optimiza(data, size, offset_limit):
    def ceil_off(i):
        return offset_limit if i > offset_limit else (1 if i < 1 else i)
    max_offset = ceil_off(size - 1)
    last_literal = [None] * (max_offset + 1)
    last_match = [None] * (max_offset + 1)
    optimal = [None] * size
    match_length = [0] * (max_offset + 1)
    best_length = [0] * size
    if size > 2:
        best_length[2] = 2
    last_match[1] = _ZB(-1, -1, 1, None)
    for index in range(size):
        best_length_size = 2
        max_offset = ceil_off(index)
        di = data[index]
        oi = optimal[index]
        for offset in range(1, max_offset + 1):
            if index and index >= offset and di == data[index - offset]:
                ll = last_literal[offset]
                if ll is not None:
                    length = index - ll.index
                    bits = ll.bits + 1 + _egbits(length)
                    lm = _ZB(bits, index, offset, ll)
                    last_match[offset] = lm
                    if oi is None or oi.bits > bits:
                        oi = lm
                ml = match_length[offset] + 1
                match_length[offset] = ml
                if ml > 1:
                    if best_length_size < ml:
                        bits = (optimal[index - best_length[best_length_size]].bits
                                + _egbits(best_length[best_length_size] - 1))
                        while True:
                            best_length_size += 1
                            bits2 = (optimal[index - best_length_size].bits
                                     + _egbits(best_length_size - 1))
                            if bits2 <= bits:
                                best_length[best_length_size] = best_length_size
                                bits = bits2
                            else:
                                best_length[best_length_size] = best_length[best_length_size - 1]
                            if best_length_size >= ml:
                                break
                    length = best_length[ml]
                    bits = (optimal[index - length].bits + 8
                            + _egbits((offset - 1) // 128 + 1) + _egbits(length - 1))
                    lm = last_match[offset]
                    if lm is None or lm.index != index or lm.bits > bits:
                        nb = _ZB(bits, index, offset, optimal[index - length])
                        last_match[offset] = nb
                        if oi is None or oi.bits > bits:
                            oi = nb
            else:
                match_length[offset] = 0
                lm = last_match[offset]
                if lm is not None:
                    length = index - lm.index
                    bits = lm.bits + 1 + _egbits(length) + length * 8
                    nb = _ZB(bits, index, 0, lm)
                    last_literal[offset] = nb
                    if oi is None or oi.bits > bits:
                        oi = nb
        optimal[index] = oi
    return optimal[size - 1]

def zx0_comprime(data, offset_limit=32640):
    """Comprime en formato ZX0 v2 (el que entiende dzx0_standard.asm)."""
    data = bytes(data)
    if not data:
        raise ValueError('zx0: entrada vacia')
    optimal = _zx0_optimiza(data, len(data), offset_limit)
    out = bytearray((optimal.bits + 25) // 8)
    st = {'oi': 0, 'bm': 0, 'bi': 0, 'bt': True}
    def wbyte(v):
        out[st['oi']] = v & 0xFF
        st['oi'] += 1
    def wbit(v):
        if st['bt']:
            if v:
                out[st['oi'] - 1] |= 1
            st['bt'] = False
        else:
            if not st['bm']:
                st['bm'] = 128
                st['bi'] = st['oi']
                wbyte(0)
            if v:
                out[st['bi']] |= st['bm']
            st['bm'] >>= 1
    def welias(value, inv):
        i = 2
        while i <= value:
            i <<= 1
        i >>= 1
        while True:
            i >>= 1
            if not i:
                break
            wbit(0)
            b = value & i
            wbit((not b) if inv else b)
        wbit(1)
    prev = None
    while optimal is not None:
        nxt = optimal.chain
        optimal.chain = prev
        prev = optimal
        optimal = nxt
    last_offset = 1
    input_index = 0
    node = prev.chain
    while node is not None:
        length = node.index - prev.index
        if not node.offset:
            wbit(0)
            welias(length, False)
            for _ in range(length):
                wbyte(data[input_index])
                input_index += 1
        elif node.offset == last_offset:
            wbit(0)
            welias(length, False)
            input_index += length
        else:
            wbit(1)
            welias((node.offset - 1) // 128 + 1, True)
            wbyte((127 - (node.offset - 1) % 128) << 1)
            st['bt'] = True
            welias(length - 1, False)
            input_index += length
            last_offset = node.offset
        prev = node
        node = node.chain
    wbit(1)
    welias(256, True)
    return bytes(out[:st['oi']])

def dzx0_simula(comp, max_out=65536):
    """Simulacion instruccion a instruccion de dzx0_standard.asm.
    Se usa para verificar en el export que cada stream comprimido se
    descomprime EXACTAMENTE como lo hara el Z80."""
    SRC = 0x10000
    mem = bytearray(0x10000 + len(comp) + 16)
    mem[SRC:SRC + len(comp)] = comp
    hl = SRC
    de = 0
    stack = []
    a = 0x80
    carry = 0
    def add_a_a():
        nonlocal a, carry
        carry = (a >> 7) & 1
        a = (a << 1) & 0xFF
    def elias_loop(bc):
        nonlocal hl, a, carry
        while True:
            add_a_a()
            if a == 0:
                nv = mem[hl]
                hl += 1
                nc = (nv >> 7) & 1
                a = ((nv << 1) | carry) & 0xFF
                carry = nc
            if carry:
                return bc
            add_a_a()
            b = (bc >> 8) & 0xFF
            c = bc & 0xFF
            nc = (c >> 7) & 1
            c = ((c << 1) | carry) & 0xFF
            nb = (b >> 7) & 1
            b = ((b << 1) | nc) & 0xFF
            bc = (b << 8) | c
    def elias(bc):
        return elias_loop((bc & 0xFF00) | ((bc + 1) & 0xFF))
    stack.append(0xFFFF)
    bc = 0
    estado = 'lit'
    while True:
        if estado == 'lit':
            bc = elias(0)
            for _ in range(bc):
                mem[de] = mem[hl]
                hl += 1
                de += 1
            if de > max_out:
                raise RuntimeError('dzx0: desbordamiento')
            add_a_a()
            if carry:
                estado = 'new'
                continue
            bc = elias(0)
            estado = 'cp'
        elif estado == 'cp':
            saddr = (stack[-1] + de) & 0xFFFF
            for k in range(bc):
                mem[de + k] = mem[saddr + k]
            de += bc
            if de > max_out:
                raise RuntimeError('dzx0: desbordamiento')
            add_a_a()
            estado = 'new' if carry else 'lit'
        else:
            stack.pop()
            bc = elias_loop((bc & 0xFF00) | 0xFE)
            c = (bc + 1) & 0xFF
            if c == 0:
                return bytes(mem[0:de])
            b = c
            c2 = mem[hl]
            hl += 1
            cy = carry
            nc = b & 1
            b = ((cy << 7) | (b >> 1)) & 0xFF
            cy = nc
            nc = c2 & 1
            c2 = ((cy << 7) | (c2 >> 1)) & 0xFF
            carry = nc
            stack.append((b << 8) | c2)
            bc = 1
            if not carry:
                add_a_a()
                cl = ((bc & 0xFF) << 1) | carry
                ch = ((bc >> 8) << 1) | (cl >> 8)
                bc = ((ch & 0xFF) << 8) | (cl & 0xFF)
                bc = elias_loop(bc)
            bc = (bc + 1) & 0xFFFF
            estado = 'cp'

# ─── Imagenes de localizacion (modo 128K) ────────────────────────────────
# img/<loc_id>.scr junto al .bas exportado. Formatos admitidos:
#   6912 bytes (SCR completo): se usa el tercio superior + 8 filas de attrs
#   2304 bytes: 2048 de bitmap + 256 de atributos, ya recortado
# Cada imagen se comprime con ZX0 en dos streams (bitmap y atributos) que
# nunca cruzan un limite de banco de 16K (dzx0 lee secuencialmente por la
# ventana $C000 de un solo banco).

def _carga_scr(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if len(raw) == 6912:
        return raw[0:2048], raw[6144:6400]
    if len(raw) == 2304:
        return raw[0:2048], raw[2048:2304]
    raise ValueError('tamano no admitido (%d bytes; usar 6912 o 2304)' % len(raw))

def imagenes_128k(img_dir, locids, locidx, texto_len, progreso=None):
    """Comprime las imagenes y construye el bloque extra del payload.
    Devuelve (extra_blob, tabla {indice_runtime_l: (offB, offA)}, informe)."""
    import os
    lineas = []
    origdir = os.path.join(os.path.dirname(img_dir), 'Original')
    encontradas = []
    for lid in locids:
        scrp = os.path.join(img_dir, lid + '.scr')
        if os.path.isfile(scrp):
            encontradas.append((locidx[lid], lid, scrp, 'scr'))
            continue
        for ext in ('.png', '.jpg', '.jpeg'):     # fallback: master de img/Original
            pp = os.path.join(origdir, lid + ext)
            if os.path.isfile(pp):
                encontradas.append((locidx[lid], lid, pp, 'png'))
                break
    scr_path = os.path.join(img_dir, 'screen.scr')
    scr_raw = None
    if os.path.isfile(scr_path):
        with open(scr_path, 'rb') as f:
            scr_raw = f.read()
        if len(scr_raw) != 6912:
            lineas.append('  - img/screen.scr IGNORADA: debe medir 6912 bytes '
                          '(mide %d)' % len(scr_raw))
            scr_raw = None
    if scr_raw is None:                        # fallback: master de img/Original
        for ext in ('.png', '.jpg', '.jpeg'):
            sp = os.path.join(origdir, 'screen' + ext)
            if os.path.isfile(sp):
                try:
                    import png2spectrum
                    scr_raw = png2spectrum.to_scr_full(sp)
                    lineas.append('  - pantalla de carga: Original/screen%s '
                                  '(dithering)' % ext)
                except Exception as e:
                    lineas.append('  - screen IGNORADA: %s' % e)
                break
    if not encontradas and scr_raw is None:
        return b'', {}, None, ['imagenes: ninguna (carpeta img/ sin '
                               '<loc_id>.scr ni screen.scr)']
    extra = bytearray()
    tabla = {}
    originales = {}
    scr_off = None
    if scr_raw is not None:
        if progreso:
            progreso(89, 'Comprimiendo pantalla de presentacion...')
        blob = zx0_comprime(scr_raw, offset_limit=2048)
        off = texto_len + len(extra)
        if off // 16384 != (off + len(blob) - 1) // 16384:
            extra += b'\x00' * (16384 - off % 16384)
            off = texto_len + len(extra)
        if off % 2:
            extra += b'\x00'
            off = texto_len + len(extra)
        extra += blob
        scr_off = off
        lineas.append('  - img/screen.scr (presentacion): 6912 -> %d bytes '
                      '(banco %d)' % (len(blob), off // 16384))
    for n, (k, lid, ruta, kind) in enumerate(encontradas):
        if progreso:
            progreso(89 + 5 * n // len(encontradas),
                     'Comprimiendo imagen %s (%d/%d)...'
                     % (lid, n + 1, len(encontradas)))
        try:
            if kind == 'scr':
                bmp, att = _carga_scr(ruta)
            else:                                   # convertir master de Original
                import png2spectrum
                bmp, att = png2spectrum.to_scr_topthird(ruta)
        except Exception as e:
            lineas.append('  - %s IGNORADA: %s' % (lid, e))
            continue
        offs = []
        for blob in (zx0_comprime(bmp), zx0_comprime(att)):
            off = texto_len + len(extra)
            if off // 16384 != (off + len(blob) - 1) // 16384:
                extra += b'\x00' * (16384 - off % 16384)
                off = texto_len + len(extra)
            if off % 2:
                extra += b'\x00'
                off = texto_len + len(extra)
            extra += blob
            offs.append((off, len(blob)))
        tabla[k] = (offs[0][0], offs[1][0])
        originales[k] = (bmp, att, offs)
        _src = ('Spectrum/%s.scr' % lid if kind == 'scr'
                else 'Original/%s (dithering)' % os.path.basename(ruta))
        lineas.append('  - img/%s: 2304 -> %d bytes (banco %d)'
                      % (_src, offs[0][1] + offs[1][1], offs[0][0] // 16384))
    if texto_len + len(extra) > 81920:
        raise ValueError('imagenes: el payload supera los 5 bancos (80 KB): '
                         '%d bytes' % (texto_len + len(extra)))
    # verificacion: cada stream debe descomprimirse exacto con el asm simulado
    if progreso:
        progreso(94, 'Verificando imagenes (dzx0)...')
    for k, (bmp, att, offs) in originales.items():
        for esperado, (off, ln) in zip((bmp, att), offs):
            if off // 16384 != (off + ln - 1) // 16384:
                raise AssertionError('imagen cruza limite de banco')
            stream = extra[off - texto_len: off - texto_len + ln]
            if dzx0_simula(stream) != esperado:
                raise AssertionError('verificacion dzx0 fallida (loc idx %d)' % k)
    if scr_off is not None:
        if dzx0_simula(bytes(extra[scr_off - texto_len:])) != scr_raw:
            raise AssertionError('verificacion dzx0 fallida (screen.scr)')
    lineas.insert(0, 'imagenes: %d incrustadas%s (+%d bytes de payload)'
                  % (len(tabla),
                     ' + pantalla de presentacion' if scr_off is not None else '',
                     len(extra)))
    return bytes(extra), tabla, scr_off, lineas

_BLOQUE_IMG = """' ---------- IMAGENES ZX0 EN BANCOS 128K ----------
' dimgB/dimgA paginan el banco, descomprimen con dzx0 (Saukas/Urusergi)
' directo a pantalla ($4000 bitmap / $5800 atributos) y restauran banco 0.
DIM imgB(@NL@) AS UINTEGER
DIM imgA(@NL@) AS UINTEGER
DIM pcnt AS UBYTE
DIM tw0 AS UBYTE

SUB FASTCALL dimgB(off AS UINTEGER)
    asm
        ld de, 4000h
        jp dimgGo
    end asm
END SUB

SUB FASTCALL dimgA(off AS UINTEGER)
    asm
        ld de, 5800h
dimgGo:
        push de
        add hl, hl
        ld a, 0
        adc a, a
        rlca
        rlca
        ld c, a
        ld a, h
        rlca
        rlca
        and 3
        add a, c
        ld e, a
        ld d, 0
        ex de, hl
        ld bc, tbim
        add hl, bc
        ld b, (hl)
        ex de, hl
        ld a, h
        and 3fh
        or 0c0h
        ld h, a
        di
        ld a, b
        ld bc, 7ffdh
        out (c), a
        pop de
        call dzx0st
        ld bc, 7ffdh
        ld a, 16
        out (c), a
        ei
        jp dimgFn
tbim:
        defb 17, 19, 20, 22, 23
        ; ---- dzx0_standard (Einar Saukas & Urusergi), etiquetas renombradas
dzx0st:
        ld bc, 0ffffh
        push bc
        inc bc
        ld a, 080h
dzx0li:
        call dzx0el
        ldir
        add a, a
        jr c, dzx0no
        call dzx0el
dzx0cp:
        ex (sp), hl
        push hl
        add hl, de
        ldir
        pop hl
        ex (sp), hl
        add a, a
        jr nc, dzx0li
dzx0no:
        pop bc
        ld c, 0feh
        call dzx0lo
        inc c
        ret z
        ld b, c
        ld c, (hl)
        inc hl
        rr b
        rr c
        push bc
        ld bc, 1
        call nc, dzx0bt
        inc bc
        jr dzx0cp
dzx0el:
        inc c
dzx0lo:
        add a, a
        jr nz, dzx0sk
        ld a, (hl)
        inc hl
        rla
dzx0sk:
        ret c
dzx0bt:
        add a, a
        rl c
        rl b
        jr dzx0lo
dimgFn:
    end asm
END SUB

SUB borraImg()
    asm
        ld hl, 4000h
        ld de, 4001h
        ld bc, 2047
        ld (hl), 0
        ldir
        ld hl, 5800h
        ld de, 5801h
        ld bc, 255
        ld a, (23693)
        ld (hl), a
        ldir
    end asm
END SUB

SUB negraImg()
    asm
        ld hl, 4000h
        ld de, 4001h
        ld bc, 2047
        ld (hl), 0
        ldir
        ld hl, 5800h
        ld de, 5801h
        ld bc, 255
        ld (hl), 0
        ldir
    end asm
END SUB

SUB dibujaImg()
    IF imgB(l) > 0 THEN
        dimgB(imgB(l) - 1)
        dimgA(imgA(l) - 1)
        tw0 = 8
    ELSE
        borraImg()
        tw0 = 0
    END IF
END SUB

SUB initImg()
    tw0 = 8
@ASIGNA@
END SUB

"""

def aplica_imagenes(src, tabla, nloc, scr_off=None):
    """Parchea el BASIC ya comprimido: bloque de imagenes, ventana de texto
    de 16 filas, gancho en descL y borrado en localizaciones oscuras."""
    asigna = []
    for k in sorted(tabla):
        offB, offA = tabla[k]
        asigna.append('    imgB(%d) = %d' % (k, offB // 2 + 1))
        asigna.append('    imgA(%d) = %d' % (k, offA // 2 + 1))
    bloque = (_BLOQUE_IMG
              .replace('@NL@', str(nloc))
              .replace('@ASIGNA@', '\n'.join(asigna)))
    ancla = "' ---------- SALIDA 64 COLUMNAS CON SCROLL ----------"
    if ancla not in src:
        raise AssertionError('ancla de insercion de imagenes no encontrada')
    src = src.replace(ancla, bloque + ancla, 1)
    # ventana de texto: filas 8-23 (el tercio superior queda para la imagen)
    viejo = 'SUB limpia()\n    CLS\n    crow = 0: ccol = 0\nEND SUB'
    nuevo = 'SUB limpia()\n    CLS\n    crow = 8: ccol = 0\nEND SUB'
    if viejo not in src:
        raise AssertionError('SUB limpia() no encontrado para parchear')
    src = src.replace(viejo, nuevo, 1)
    if 'WinScrollUp(0, 0, 32, 24)' not in src:
        raise AssertionError('WinScrollUp no encontrado para parchear')
    src = src.replace('WinScrollUp(0, 0, 32, 24)', 'WinScrollUp(tw0, 0, 32, 24 - tw0)', 1)
    # gancho: descL dibuja la imagen de la localizacion actual
    viejo = 'SUB descL()\n    DIM i AS UBYTE\n    pnl()'
    if viejo not in src:
        raise AssertionError('SUB descL() no encontrado para parchear')
    # Al describir una localización NO se pregunta "[mas]": se dibuja la imagen
    # y se limpia la ventana de texto directamente (limpiaTxt pone pcnt = 0).
    # Así, al moverse a otra localización, va directo sin pausa de paginación.
    # descL decide aquí (oscuro() ya está definida en este punto): si la
    # localización tiene imagen y está a oscuras, pinta el tercio en negro;
    # en cuanto haya luz y se redescriba, dibuja la imagen correspondiente.
    src = src.replace(viejo,
                      'SUB descL()\n    DIM i AS UBYTE\n'
                      '    IF imgB(l) > 0 AND oscuro() = 1 THEN\n'
                      '        negraImg()\n'
                      '        tw0 = 8\n'
                      '    ELSE\n'
                      '        dibujaImg()\n'
                      '    END IF\n'
                      '    limpiaTxt()', 1)
    # initImg tras initDic en el arranque
    if '\ninitDic()\n' not in src:
        raise AssertionError('llamada a initDic() no encontrada')
    src = src.replace('\ninitDic()\n', '\ninitDic()\ninitImg()\n', 1)
    # la imagen de la escena inicial debe salir ANTES del mensaje de inicio
    if '\nlimpia()\n' not in src:
        raise AssertionError('llamada a limpia() no encontrada')
    # La imagen de la 1a localizacion se dibuja DESPUES de onStart(): el on_start
    # puede hacer CLS (fijar colores), y en 128K la imagen va en la pantalla ULA,
    # asi que dibujarla antes la borraria. En la presentacion/mensaje inicial debe
    # verse igualmente (en Next es Layer 2 y sobrevive al CLS).
    arranque = '\nlimpia()\ncrow = tw0\n'
    if scr_off is not None:
        arranque = ('\ndimgB(%d)\nPAUSE 0\n' % (scr_off // 2)) + arranque[1:]
    src = src.replace('\nlimpia()\n', arranque, 1)
    src = src.replace('\nonStart()\n', '\nonStart()\ndibujaImg()\ncrow = tw0\n', 1)
    # paginacion [mas]: con 16 filas un texto largo escapa sin leerse
    src = src.replace('    crow = 8: ccol = 0\n',
                      '    crow = tw0: ccol = 0: pcnt = 0\n', 1)
    viejo_pg = ('        WinScrollUp(tw0, 0, 32, 24 - tw0)\n'
                '        crow = crow - 1\n    LOOP\nEND SUB')
    if viejo_pg not in src:
        raise AssertionError('cuerpo de pgchk no encontrado')
    pmas = viejo_pg + ('\n\nSUB pmas()\n'
                       '    pgchk()\n'
                       '    PAUSE 0\n'        # espera una tecla, sin mensaje
                       '    pcnt = 0\n'
                       'END SUB\n\n'
                       'SUB limpiaTxt()\n'
                       '    asm\n'
                       '        ld hl, 4800h\n'
                       '        ld de, 4801h\n'
                       '        ld bc, 4095\n'
                       '        ld (hl), 0\n'
                       '        ldir\n'
                       '    end asm\n'
                       '    crow = tw0: ccol = 0: pcnt = 0\n'
                       'END SUB')
    src = src.replace(viejo_pg, pmas, 1)
    viejo_pnl = 'SUB pnl()\n    crow = crow + 1\n    ccol = 0\nEND SUB'
    if viejo_pnl not in src:
        raise AssertionError('SUB pnl() no encontrado')
    src = src.replace(viejo_pnl,
                      'SUB pnl()\n    crow = crow + 1\n    ccol = 0\n'
                      '    pcnt = pcnt + 1\n'
                      '    IF pcnt >= 23 - tw0 THEN pmas()\nEND SUB', 1)
    # cada turno del jugador resetea la cuenta
    viejo_lee = '    li$ = leeLinea$()\n'
    if viejo_lee not in src:
        raise AssertionError('lectura de linea no encontrada')
    src = src.replace(viejo_lee, '    li$ = leeLinea$()\n    pcnt = 0\n', 1)
    return src

# ─── Compresion de literales (tokens 1-2 bytes, pack DEFM/PEEK) ──────────
ALFA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
PREF = "~{}|"
GUARD = r'(?<![~{}|])'

def comprime(src, nombres, avisos, bin_name, progreso=None, modo='48k'):
    def _p(pct, msg):
        if progreso:
            progreso(pct, msg)
    pat = re.compile(r'pw\("([^"]*)"\)')
    lits = [m.group(1) for m in pat.finditer(src)]
    npw = len(lits)
    todos = lits + nombres
    orig_total = sum(len(x) for x in todos)
    corpus = '\n'.join(todos)
    usados = set(corpus)
    if set(PREF) & usados:
        raise ValueError('los textos contienen ~ { } o | (reservados)')
    # Un carácter solo puede ser byte-token si NO aparece en NINGÚN literal del
    # programa. Las llamadas pw() concatenadas (puntuacion "[+N puntos]", reloj
    # "[0H:0M]", etc.) no pasan por el diccionario, así que sus caracteres deben
    # excluirse o pex los expandiría por error y se corrompería el texto.
    for _m in re.finditer(r'"([^"\n]*)"', src):
        usados |= set(_m.group(1))
    singles = [ch for ch in "@#$%&*+<>[]^_`;=" if ch not in usados]
    NS = len(singles)
    MAXTOK = NS + len(ALFA) * len(PREF)
    OVH = 5
    tokch = set(PREF) | set(singles)

    cnt = Counter()
    Lc = len(corpus)
    paso = max(1, Lc // 12)
    for i in range(Lc):
        if i % paso == 0:
            _p(15 + 20 * i // max(1, Lc), 'Analizando subcadenas...')
        for n in range(3, 30):
            if i + n > Lc:
                break
            s = corpus[i:i+n]
            if '\n' in s:
                continue
            cnt[s] += 1
    heap = []
    for s, cc in cnt.items():
        if cc >= 2 and not (set(s) & tokch):
            gan = cc * (len(s) - 1) - (len(s) + OVH)
            if gan > 1:
                heap.append((-gan, s))
    heapq.heapify(heap)
    dic = []
    while heap and len(dic) < MAXTOK:
        if len(dic) % 8 == 0:
            _p(35 + 50 * len(dic) // MAXTOK,
               f'Construyendo diccionario ({len(dic)} entradas)...')
        tokw = 1 if len(dic) < NS else 2
        _, s = heapq.heappop(heap)
        occ = len(re.findall(GUARD + re.escape(s), corpus))
        gan = occ * (len(s) - tokw) - (len(s) + OVH)
        if gan <= 1:
            continue
        if heap and -heap[0][0] > gan:
            heapq.heappush(heap, (-gan, s))
            continue
        if len(dic) < NS:
            tok = singles[len(dic)]
        else:
            k = len(dic) - NS
            tok = PREF[k // 62] + ALFA[k % 62]
        dic.append((tok, s))
        corpus = re.sub(GUARD + re.escape(s), tok, corpus)

    textos = corpus.split('\n')
    comp_total = sum(len(t) for t in textos)
    _p(88, 'Verificando ida y vuelta...')
    # ── verificacion ida y vuelta ──
    tok2w = dict(dic)
    sset = set(singles)
    def expand(t):
        out, i = "", 0
        while i < len(t):
            ch = t[i]
            if ch in sset:
                out += tok2w[ch]; i += 1
            elif ch in PREF:
                out += tok2w[t[i:i+2]]; i += 2
            else:
                out += ch; i += 1
        return out
    assert len(textos) == len(todos)
    for a, b in zip(textos, todos):
        if expand(a) != b:
            raise AssertionError('verificacion de compresion fallida: ' + b[:60])

    # mensajes deduplicados -> indices; nombres tokenizados
    nombres_tok = textos[npw:]
    unicos = []
    idx_de = {}
    indices = []
    for t in textos[:npw]:
        if t not in idx_de:
            idx_de[t] = len(unicos)
            unicos.append(t)
        indices.append(idx_de[t])
    MSG0 = len(dic) + len(nombres_tok)
    it = iter(indices)
    src = pat.sub(lambda m: f'pwI({MSG0 + next(it)})', src)

    # ── binario de textos: [T][offsets x T+1][datos] ──
    palabras = [w for _, w in dic]
    NW = len(palabras)
    NN = len(nombres_tok)
    entradas = palabras + nombres_tok + unicos
    T = len(entradas)
    datos = b''
    offs = []
    for e in entradas:
        offs.append(len(datos))
        datos += e.encode('latin-1')
    offs.append(len(datos))
    import struct
    bin_blob = struct.pack('<H', T)
    for o in offs:
        bin_blob += struct.pack('<H', o)
    bin_blob += datos
    
    tl = [f"    tmap({ord(ch)}) = {j+1}" for j, ch in enumerate(singles)]
    tl += [f"    tmap({ord(ch)}) = {101+j}" for j, ch in enumerate(PREF)]
    bloque = f"""\' ---------- TEXTOS COMPRIMIDOS (ver {bin_name}) ----------
DIM dbase AS UINTEGER
DIM ddata AS UINTEGER
DIM tmap(255) AS UBYTE

FUNCTION FASTCALL binBase() AS UINTEGER
    asm
        ld hl, texto_bin
        ret
texto_bin:
        incbin "{bin_name}"
    end asm
END FUNCTION

FUNCTION entW$(k AS UINTEGER) AS STRING
    DIM o AS UINTEGER
    DIM a AS UINTEGER
    DIM f AS UINTEGER
    DIM w$ AS STRING
    o = dbase + 2 + 2 * k
    a = ddata + PEEK(o) + 256 * PEEK(o + 1)
    f = ddata + PEEK(o + 2) + 256 * PEEK(o + 3)
    w$ = ""
    DO WHILE a < f
        w$ = w$ + CHR$(PEEK(a))
        a = a + 1
    LOOP
    RETURN w$
END FUNCTION

FUNCTION onomW$(i AS UBYTE) AS STRING
    DIM k AS UINTEGER
    k = i
    RETURN entW$({NW} + k - 1)
END FUNCTION

SUB initDic()
    dbase = binBase()
    ddata = dbase + 2 + 2 * {T + 1}
{chr(10).join(tl)}
END SUB

FUNCTION idxTok(ch AS UBYTE) AS UBYTE
    IF ch >= 97 AND ch <= 122 THEN RETURN ch - 97
    IF ch >= 65 AND ch <= 90 THEN RETURN ch - 39
    IF ch >= 48 AND ch <= 57 THEN RETURN ch + 4
    RETURN 0
END FUNCTION

FUNCTION pex(t$ AS STRING) AS STRING
    DIM r$ AS STRING
    DIM i AS UINTEGER
    DIM s AS UINTEGER
    DIM m AS UBYTE
    DIM k2 AS UINTEGER
    r$ = "": i = 0: s = 0
    DO WHILE i < LEN(t$)
        m = tmap(CODE(t$(i)))
        IF m = 0 THEN
            i = i + 1
        ELSEIF m <= {NS} THEN
            IF i > s THEN r$ = r$ + t$(s TO i - 1)
            r$ = r$ + entW$(m - 1)
            i = i + 1: s = i
        ELSE
            IF i + 1 < LEN(t$) THEN
                IF i > s THEN r$ = r$ + t$(s TO i - 1)
                k2 = m - 101
                r$ = r$ + entW$({NS} + k2 * 62 + idxTok(CODE(t$(i + 1))))
                i = i + 2: s = i
            ELSE
                i = i + 1
            END IF
        END IF
    LOOP
    IF i > s THEN r$ = r$ + t$(s TO i - 1)
    RETURN r$
END FUNCTION

SUB pwI(k AS UINTEGER)
    pw(entW$(k))
END SUB"""
    DD = 2 + 2 * (T + 1)
    bloque128 = f"""' ---------- TEXTOS EN BANCOS 128K (ver {bin_name}) ----------
' Los textos viven en los bancos 1/3/4/6 paginados en $C000.
' pk128() lee un byte paginando con DI y sin tocar la pila.
DIM tmap(255) AS UBYTE

FUNCTION FASTCALL pk128(off AS UINTEGER) AS UBYTE
    asm
        ; HL = offset global dentro de texto.bin
        ld a, h
        rlca
        rlca
        and 3
        ld c, a
        ld b, 0
        ex de, hl
        ld hl, tb128
        add hl, bc
        ld c, (hl)
        ex de, hl
        ld a, h
        and 3fh
        or 0c0h
        ld h, a
        ld a, c
        ld bc, 7ffdh
        di
        out (c), a
        ld e, (hl)
        ld a, 16
        out (c), a
        ei
        ld a, e
        ret
tb128:
        defb 17, 19, 20, 22
    end asm
END FUNCTION

FUNCTION entW$(k AS UINTEGER) AS STRING
    DIM a AS UINTEGER
    DIM f AS UINTEGER
    DIM o AS UINTEGER
    DIM w$ AS STRING
    o = 2 + 2 * k
    a = 256 * pk128(o + 1) + pk128(o) + {DD}
    f = 256 * pk128(o + 3) + pk128(o + 2) + {DD}
    w$ = ""
    DO WHILE a < f
        w$ = w$ + CHR$(pk128(a))
        a = a + 1
    LOOP
    RETURN w$
END FUNCTION

FUNCTION onomW$(i AS UBYTE) AS STRING
    DIM k AS UINTEGER
    k = i
    RETURN entW$({NW} + k - 1)
END FUNCTION

SUB initDic()
{chr(10).join(tl)}
END SUB

FUNCTION idxTok(ch AS UBYTE) AS UBYTE
    IF ch >= 97 AND ch <= 122 THEN RETURN ch - 97
    IF ch >= 65 AND ch <= 90 THEN RETURN ch - 39
    IF ch >= 48 AND ch <= 57 THEN RETURN ch + 4
    RETURN 0
END FUNCTION

FUNCTION pex(t$ AS STRING) AS STRING
    DIM r$ AS STRING
    DIM i AS UINTEGER
    DIM s AS UINTEGER
    DIM m AS UBYTE
    DIM k2 AS UINTEGER
    r$ = "": i = 0: s = 0
    DO WHILE i < LEN(t$)
        m = tmap(CODE(t$(i)))
        IF m = 0 THEN
            i = i + 1
        ELSEIF m <= {NS} THEN
            IF i > s THEN r$ = r$ + t$(s TO i - 1)
            r$ = r$ + entW$(m - 1)
            i = i + 1: s = i
        ELSE
            IF i + 1 < LEN(t$) THEN
                IF i > s THEN r$ = r$ + t$(s TO i - 1)
                k2 = m - 101
                r$ = r$ + entW$({NS} + k2 * 62 + idxTok(CODE(t$(i + 1))))
                i = i + 2: s = i
            ELSE
                i = i + 1
            END IF
        END IF
    LOOP
    IF i > s THEN r$ = r$ + t$(s TO i - 1)
    RETURN r$
END FUNCTION

SUB pwI(k AS UINTEGER)
    pw(entW$(k))
END SUB"""
    if modo == '128k':
        bloque = bloque128
    src = src.replace("'@DICCIONARIO@", bloque)
    src = src.replace("'@DICDATA@\n", '')

    # ── deduplicar literales pw repetidos (frase -> SUB compartido) ──
    cuenta = Counter(m.group(1) for m in re.finditer(r'pw\("([^"]*)"\)', src))
    frases = [t for t, n in cuenta.items() if n >= 3 and len(t) >= 10]
    if frases:
        subs = []
        for j, t in enumerate(sorted(frases, key=len, reverse=True), 1):
            subs.append(f'SUB fz{j}()')
            subs.append(f'    pw("{t}")')
            subs.append('END SUB')
            src = src.replace(f'pw("{t}")', f'fz{j}()')
        marca = "' ---------- DATOS DEL MAPA ----------"
        src = src.replace(marca, '\n'.join(subs) + '\n\n' + marca, 1)
    rep = (f"textos: {orig_total} -> {comp_total} chars | diccionario: "
           f"{len(dic)} entradas | mensajes unicos: {len(unicos)} | "
           f"binario de textos: {len(bin_blob)} bytes | verificacion: OK")
    return src, rep, bin_blob

def poda(src):
    """Elimina variables Vv* sin uso real y el SUB irA si no hay GOTOs.
    Evita los avisos W150/W170 de zxb sin cambiar la semantica."""
    # variables: solo DIM (1 aparicion) o DIM + inicializacion -> fuera
    for m in re.finditer(r'^DIM (Vv\w+) AS INTEGER$', src, re.M):
        nombre = m.group(1)
        usos = len(re.findall(r'\b' + nombre + r'\b', src))
        inits = re.findall(r'^\s*' + nombre + r' = -?\d+$', src, re.M)
        if usos - 1 - len(inits) == 0:
            src = re.sub(r'^DIM ' + nombre + r' AS INTEGER\n', '', src, flags=re.M)
            src = re.sub(r'^\s*' + nombre + r' = -?\d+\n', '', src, flags=re.M)
    # irA: solo existe para los GOTO transpilados
    if len(re.findall(r'\birA\(', src)) == 1:
        a = src.index('SUB irA(d AS UBYTE)')
        b = src.index('END SUB', a) + len('END SUB\n')
        src = src[:a] + src[b:]
    return src

EMPAQUETA128 = r'''#!/usr/bin/env python3
# Empaqueta el TAP final para ZX Spectrum 128K (textos en bancos):
#   python empaqueta128.py juego.bin juego_texto.bin [salida.tap] [org] [pantalla.scr]
# Orden del TAP: cargador BASIC, [pantalla de carga 6912 @ 16384], codigo, bancos.
# La pantalla de carga se busca en: argumento 5, img/screen.scr, screen.scr.
# IMPORTANTE: org por defecto 24576. El cargador hace CLEAR org-1 y
# necesita ~600 bytes de holgura sobre el programa BASIC (23755+212):
# con org 24000 el Spectrum da 'M RAMTOP no good'.
# El cargador pagina los bancos 1/3/4/6 en $C000 y carga alli el texto.
import sys, struct, os

def buscar_scr(extra):
    cand = ([extra] if extra else []) + ['img/Spectrum/screen.scr',
                                         'img/128/screen.scr',
                                         'img/screen.scr', 'screen.scr']
    for p in cand:
        if p and os.path.isfile(p) and os.path.getsize(p) == 6912:
            return open(p, 'rb').read(), p
    return None, None

def bloque(data, flag):
    b = bytes([flag]) + data
    chk = 0
    for x in b:
        chk ^= x
    return struct.pack('<H', len(b) + 1) + b + bytes([chk])

def cab(tipo, nombre, lon, p1, p2=32768):
    n = (nombre + ' ' * 10)[:10].encode('ascii')
    return bloque(bytes([tipo]) + n + struct.pack('<HHH', lon, p1, p2), 0)

def num(n):
    return str(n).encode('ascii') + bytes([0x0E, 0, 0, n & 255, (n >> 8) & 255, 0])

def linea(nl, cuerpo):
    return struct.pack('>H', nl) + struct.pack('<H', len(cuerpo) + 1) + cuerpo + b'\r'

def leer_border():
    for p in ('border.txt', '../border.txt', '../../border.txt'):
        try:
            if os.path.isfile(p):
                return int(open(p).read().strip()) & 7
        except (ValueError, OSError):
            pass
    return 0

def main():
    if len(sys.argv) < 3:
        print('uso: python empaqueta128.py juego.bin juego_texto.bin [salida.tap] [org]')
        sys.exit(1)
    code = open(sys.argv[1], 'rb').read()
    texto = open(sys.argv[2], 'rb').read()
    out = sys.argv[3] if len(sys.argv) > 3 else 'juego128.tap'
    org = int(sys.argv[4]) if len(sys.argv) > 4 else 24576
    scr, scrnom = buscar_scr(sys.argv[5] if len(sys.argv) > 5 else None)
    BANCOS = [17, 19, 20, 22, 23]   # 16 + banco RAM 1,3,4,6,7
    trozos = [texto[i:i + 16384] for i in range(0, len(texto), 16384)]
    if len(trozos) > 5:
        print('ERROR: texto.bin supera 80K (5 bancos)')
        sys.exit(1)
    CLEAR, LOAD, CODE_T = 0xFD, 0xEF, 0xAF
    POKE, OUT, RND, USR = 0xF4, 0xDF, 0xF9, 0xC0
    BORDER = 0xE7
    cuerpo10 = (bytes([BORDER]) + num(leer_border()) + b':' +
                bytes([CLEAR]) + num(org - 1) + b':' +
                bytes([POKE]) + num(23739) + b',' + num(111) + b':' +
                bytes([LOAD]) + b'""' + bytes([CODE_T]))
    if scr:
        cuerpo10 += b':' + bytes([LOAD]) + b'""' + bytes([CODE_T])
    prog = linea(10, cuerpo10)
    nl = 20
    for j in range(len(trozos)):
        prog += linea(nl, bytes([POKE]) + num(23388) + b',' + num(BANCOS[j]) + b':' +
                      bytes([OUT]) + num(32765) + b',' + num(BANCOS[j]) + b':' +
                      bytes([LOAD]) + b'""' + bytes([CODE_T]) + num(49152))
        nl += 10
    prog += linea(nl, bytes([POKE]) + num(23388) + b',' + num(16) + b':' +
                  bytes([OUT]) + num(32765) + b',' + num(16) + b':' +
                  bytes([POKE]) + num(23739) + b',' + num(244) + b':' +
                  bytes([RND, USR]) + num(org))
    tap = cab(0, 'cargador', len(prog), 10, len(prog)) + bloque(prog, 0xFF)
    if scr:
        tap += cab(3, 'pantalla', len(scr), 16384) + bloque(scr, 0xFF)
    tap += cab(3, 'codigo', len(code), org) + bloque(code, 0xFF)
    for j, t in enumerate(trozos):
        tap += cab(3, 'texto' + str(j + 1), len(t), 49152) + bloque(t, 0xFF)
    open(out, 'wb').write(tap)
    print(out + ': ' + str(len(tap)) + ' bytes | codigo ' + str(len(code)) +
          ' @ ' + str(org) + ' | ' + str(len(trozos)) + ' banco(s) de texto' +
          (' | pantalla de carga: ' + scrnom if scr else ' | sin pantalla de carga'))
    heap = 4096
    fin_code = org + len(code)
    tope = fin_code + heap
    libre_ram = 65536 - tope
    print()
    print('=== MEMORIA LIBRE ===')
    print('RAM principal: motor %d bytes ($%04X-$%04X) + heap %d -> libre %d bytes' %
          (len(code), org, fin_code - 1, heap, max(0, libre_ram)))
    if libre_ram < 0:
        print('  *** NO CABE: sobran %d bytes (motor+heap > 65536) ***' % -libre_ram)
    print('Bancos 128K (5 x 16384 = 81920):')
    for j in range(5):
        usado = len(trozos[j]) if j < len(trozos) else 0
        print('  banco %d: %5d usados | %5d libres' % (j, usado, 16384 - usado))
    print('  total bancos: %d usados | %d libres (texto+imagenes futuros)' %
          (len(texto), len(BANCOS) * 16384 - len(texto)))

main()
'''


EMPAQUETA48 = r'''#!/usr/bin/env python3
# Empaqueta el TAP para ZX Spectrum 48K:
#   python empaqueta48.py juego.bin [salida.tap] [org] [pantalla.scr]
# Orden del TAP: cargador BASIC, [pantalla de carga 6912 @ 16384], codigo.
# La pantalla de carga se busca en: argumento 4, img/screen.scr, screen.scr.
# El .bin se compila antes con:  zxbc --org 24000 ... juego.bas  (sin --tap).
import sys, struct, os

def bloque(data, flag):
    b = bytes([flag]) + data
    chk = 0
    for x in b:
        chk ^= x
    return struct.pack('<H', len(b) + 1) + b + bytes([chk])

def cab(tipo, nombre, lon, p1, p2=32768):
    n = (nombre + ' ' * 10)[:10].encode('ascii')
    return bloque(bytes([tipo]) + n + struct.pack('<HHH', lon, p1, p2), 0)

def num(n):
    return str(n).encode('ascii') + bytes([0x0E, 0, 0, n & 255, (n >> 8) & 255, 0])

def linea(nl, cuerpo):
    return struct.pack('>H', nl) + struct.pack('<H', len(cuerpo) + 1) + cuerpo + b'\r'

def buscar_scr(extra):
    cand = ([extra] if extra else []) + ['img/screen.scr', 'screen.scr']
    for p in cand:
        if p and os.path.isfile(p) and os.path.getsize(p) == 6912:
            return open(p, 'rb').read(), p
    return None, None

def leer_border():
    for p in ('border.txt', '../border.txt', '../../border.txt'):
        try:
            if os.path.isfile(p):
                return int(open(p).read().strip()) & 7
        except (ValueError, OSError):
            pass
    return 0

def main():
    if len(sys.argv) < 2:
        print('uso: python empaqueta48.py juego.bin [salida.tap] [org] [pantalla.scr]')
        sys.exit(1)
    code = open(sys.argv[1], 'rb').read()
    out = sys.argv[2] if len(sys.argv) > 2 else 'juego.tap'
    org = int(sys.argv[3]) if len(sys.argv) > 3 else 24000
    scr, scrnom = buscar_scr(sys.argv[4] if len(sys.argv) > 4 else None)
    CLEAR, LOAD, CODE_T, RND, USR, POKE = 0xFD, 0xEF, 0xAF, 0xF9, 0xC0, 0xF4
    BORDER = 0xE7
    cuerpo = (bytes([BORDER]) + num(leer_border()) + b':' +
              bytes([CLEAR]) + num(org - 1) + b':' +
              bytes([POKE]) + num(23739) + b',' + num(111) + b':' +
              bytes([LOAD]) + b'""' + bytes([CODE_T]))
    if scr:
        cuerpo += b':' + bytes([LOAD]) + b'""' + bytes([CODE_T])
    cuerpo += (b':' + bytes([POKE]) + num(23739) + b',' + num(244) +
               b':' + bytes([RND, USR]) + num(org))
    prog = linea(10, cuerpo)
    tap = cab(0, 'cargador', len(prog), 10, len(prog)) + bloque(prog, 0xFF)
    if scr:
        tap += cab(3, 'pantalla', len(scr), 16384) + bloque(scr, 0xFF)
    tap += cab(3, 'codigo', len(code), org) + bloque(code, 0xFF)
    open(out, 'wb').write(tap)
    print(out + ': ' + str(len(tap)) + ' bytes | codigo ' + str(len(code)) +
          ' @ ' + str(org) +
          (' | pantalla de carga: ' + scrnom if scr else ' | sin pantalla de carga'))
    fin = org + len(code)
    print('Binario 48K: $%04X-$%04X (%d bytes). Limite practico ~39.7 KB.' %
          (org, fin - 1, len(code)))

main()
'''

# ─── API principal ───────────────────────────────────────────────────────
# ─── Musica AY del menu (PSG) ────────────────────────────────────────────
# Reproductor PSG minimalista: durante la pantalla de titulo se reproduce un
# volcado PSG (registros del AY por frame) sincronizado a 50 Hz con PAUSE 1,
# hasta que se pulsa una tecla; entonces se silencia el AY. Los datos van en
# RAM principal (defb), no en bancos. Puertos 128K: $FFFD (sel), $BFFD (dato).
_PSG_PLAYER = """' ---------- REPRODUCTOR PSG (musica AY del menu) ----------
SUB psginit()
    asm
        ld hl, psgdata
        ld (psgpos), hl
    end asm
END SUB

SUB psgframe()
    asm
        ld hl, (psgpos)
        inc hl                  ; saltar marcador de frame (0xFF)
pf_rp:
        ld a, (hl)
        cp 0ffh
        jr z, pf_done           ; siguiente frame -> fin de este
        cp 0fdh
        jr z, pf_loop           ; fin de musica -> rebobinar
        inc hl
        ld d, a                 ; numero de registro AY
        ld e, (hl)              ; valor
        inc hl
        ld bc, 0fffdh
        out (c), d
        ld bc, 0bffdh
        out (c), e
        jr pf_rp
pf_loop:
        ld hl, psgdata
        ld (psgpos), hl
        ret
pf_done:
        ld (psgpos), hl
        ret
psgpos:
        defw psgdata
psgdata:
@PSGDATA@
    end asm
END SUB

SUB psgoff()
    asm
        ld bc, 0fffdh
        ld a, 7
        out (c), a
        ld bc, 0bffdh
        ld a, 3fh
        out (c), a              ; mezclador: todo desactivado
        ld d, 8
psgo_l:
        ld bc, 0fffdh
        out (c), d
        ld bc, 0bffdh
        xor a
        out (c), a              ; volumen canal = 0
        inc d
        ld a, d
        cp 11
        jr nz, psgo_l
    end asm
END SUB

"""


def _psg_defb(stream):
    out = []
    for i in range(0, len(stream), 16):
        out.append('        defb ' + ','.join(str(b) for b in stream[i:i + 16]))
    return '\n'.join(out)


# ─── Reproductor de efectos FX por el AY (128K / Next) ───────────────────────
# Reproduce un efecto bloqueante: para cada frame escribe R0/R1 (tono), R6 (ruido),
# R7 (mezclador) y R8 (volumen) del canal A y espera 1/50 s con HALT (sincroniza
# con la interrupcion de video). Al acabar silencia el canal. En 48K (sin chip AY)
# las salidas a $FFFD/$BFFD no hacen nada: queda mudo, sin colgarse.
# playfx(n) es FASTCALL: el numero de efecto (1-based) llega en A.
_FX_PLAYER = '''' ---------- REPRODUCTOR DE EFECTOS FX (AY) ----------
SUB FASTCALL playfx(n AS UBYTE)
    asm
        or a
        ret z                   ; n=0 -> nada
        ld hl, fxdata
        ld c, (hl)              ; C = nfx (numero de ranuras)
        cp c
        jr z, fx_in             ; n == nfx -> valido (ultima ranura)
        ret nc                  ; n > nfx -> fuera de rango
fx_in:
        dec a                   ; n-1
        add a, a                ; (n-1)*2
        ld e, a
        ld d, 0
        inc hl                  ; fxdata+1 (inicio de la tabla de offsets)
        add hl, de              ; -> &offset[n-1]
        ld e, (hl)
        inc hl
        ld d, (hl)              ; DE = offset (relativo a fxdata)
        ld a, d
        or e
        ret z                   ; offset 0 -> efecto no incluido (mudo)
        ld hl, fxdata
        add hl, de              ; HL -> bloque del efecto
        ld b, (hl)              ; B = nframes
        inc hl
        ld a, b
        or a
        ret z
fx_frame:
        push bc
        ld bc, 0fffdh
        xor a
        out (c), a              ; reg 0 (tono lo)
        ld a, (hl)
        ld bc, 0bffdh
        out (c), a
        inc hl
        ld bc, 0fffdh
        ld a, 1
        out (c), a              ; reg 1 (tono hi)
        ld a, (hl)
        ld bc, 0bffdh
        out (c), a
        inc hl
        ld bc, 0fffdh
        ld a, 6
        out (c), a              ; reg 6 (ruido)
        ld a, (hl)
        ld bc, 0bffdh
        out (c), a
        inc hl
        ld bc, 0fffdh
        ld a, 7
        out (c), a              ; reg 7 (mezclador)
        ld a, (hl)
        ld bc, 0bffdh
        out (c), a
        inc hl
        ld bc, 0fffdh
        ld a, 8
        out (c), a              ; reg 8 (volumen canal A)
        ld a, (hl)
        ld bc, 0bffdh
        out (c), a
        inc hl
        halt                    ; esperar 1/50 s
        pop bc
        djnz fx_frame
        ; silenciar canal A: mezclador todo off y volumen 0
        ld bc, 0fffdh
        ld a, 7
        out (c), a
        ld bc, 0bffdh
        ld a, 3fh
        out (c), a
        ld bc, 0fffdh
        ld a, 8
        out (c), a
        ld bc, 0bffdh
        xor a
        out (c), a
        ret
fxdata:
@FXDATA@
    end asm
END SUB

'''


def _fx_defb(blob):
    out = []
    for i in range(0, len(blob), 16):
        out.append('        defb ' + ','.join(str(b) for b in blob[i:i + 16]))
    return '\n'.join(out) if out else '        defb 0'


def aplica_fx(src, game, clock=1773400, embed=True):
    """Si el juego usa PLAY, inyecta el reproductor de FX (playfx) y los datos de
    los efectos REFERENCIADOS (solo esos) en el codigo. Devuelve src sin cambios
    si no hay FX en uso. clock: reloj del AY (Spectrum/Next = 1773400).
    embed=False (p.ej. 48K, sin chip AY): inyecta el reproductor pero SIN datos
    (nfx=0), para que los playfx() compilen y sean mudos sin gastar RAM."""
    try:
        import capabilities
        import fx_engine
    except Exception:
        return src
    used = capabilities.used_fx(game)
    if not used:
        return src
    if embed:
        blob = fx_engine.pack_ay_fx(game.get('fx', []) or [], used, clock=clock)
        if not blob:
            blob = bytes([0])
    else:
        blob = bytes([0])                  # nfx=0 -> playfx siempre retorna (mudo)
    player = _FX_PLAYER.replace('@FXDATA@', _fx_defb(blob))
    ancla = "' ---------- SALIDA 64 COLUMNAS CON SCROLL ----------"
    if ancla in src:
        return src.replace(ancla, player + ancla, 1)
    return src + '\n' + player


def _leer_psg(musdir):
    """Devuelve (stream_sin_cabecera, nombre) de la musica de music/, o (None,
    None). Prioridad: un .psg hecho a mano; si no hay, convierte un .mid con
    mid2psg (afinado al reloj del AY del Spectrum, 1,77 MHz)."""
    import os
    import glob
    if not os.path.isdir(musdir):
        return None, None
    psgs = sorted(glob.glob(os.path.join(musdir, '*.psg')))
    mids = sorted(glob.glob(os.path.join(musdir, '*.mid'))
                  + glob.glob(os.path.join(musdir, '*.midi')))
    if psgs:
        raw = open(psgs[0], 'rb').read()
        nombre = os.path.basename(psgs[0])
        if raw[:3] == b'PSG':            # quitar cabecera de 16 bytes
            raw = raw[16:]
    elif mids:
        try:
            import mid2psg
            raw = mid2psg.midi_to_psg_standard(mids[0], clock=mid2psg.CLOCK_ZX)
            nombre = os.path.basename(mids[0])
        except Exception:
            return None, None
    else:
        return None, None
    if not raw or raw[0] != 0xFF:    # debe empezar en marcador de frame
        raw = b'\xFF' + raw
    if raw[-1] != 0xFD:              # y terminar en fin-de-musica (bucle)
        raw = raw + b'\xFD'
    return raw, nombre


def aplica_musica(src, musfile, scr_off):
    """Inyecta el reproductor PSG y sustituye la espera del titulo por el bucle
    de musica (suena hasta pulsar tecla, luego silencia el AY). La musica se
    incrusta con incbin desde 'musfile' (al FINAL del codigo, en RAM principal);
    el editor recorta ese fichero a la RAM que quede libre antes de compilar, asi
    un MIDI largo no desborda &FFFF y NO se gastan bancos (reservados a texto e
    imagenes, igual que en 48K)."""
    player = _PSG_PLAYER.replace('@PSGDATA@', '        incbin "%s"' % musfile)
    ancla = "' ---------- SALIDA 64 COLUMNAS CON SCROLL ----------"
    if ancla not in src:
        raise AssertionError('ancla para el reproductor PSG no encontrada')
    src = src.replace(ancla, player + ancla, 1)
    title_old = 'dimgB(%d)\nPAUSE 0\n' % (scr_off // 2)
    if title_old not in src:
        raise AssertionError('espera del titulo (dimgB + PAUSE 0) no encontrada')
    # Primero espera a SOLTAR cualquier tecla (la que se uso para cargar) y luego
    # a una pulsacion NUEVA; si no, el bucle saldria al instante por la tecla
    # residual y la pantalla de presentacion no esperaria.
    title_new = ('dimgB(%d)\npsginit()\n'
                 'DO\n    PAUSE 1\n    psgframe()\nLOOP UNTIL INKEY$ = ""\n'
                 'DO\n    PAUSE 1\n    psgframe()\nLOOP UNTIL INKEY$ <> ""\n'
                 'psgoff()\n') % (scr_off // 2)
    src = src.replace(title_old, title_new, 1)
    return src


def export_bas(game, out_path, progreso=None, modo='48k', columnas=42):
    def _p(pct, msg):
        if progreso:
            progreso(pct, msg)
    _p(2, 'Recolectando datos del juego...')
    global _PT_LANG
    _lang = (game.get('metadata', {}).get('language') or 'es').strip().lower()
    _PT_LANG = _lang.startswith('pt') or _lang.startswith('por')
    c = recolecta(game)
    _p(5, 'Generando motor y datos...')
    L = genera_fuente(c)
    genera_fuente2(c, L)
    _p(8, 'Transpilando condacts...')
    genera_fuente3(c, L)
    genera_fuente4(c, L)
    src = '\n'.join(L) + '\n'
    # mensajes del sistema personalizados (metadata['mensajes']) -> sustitucion
    # ANTES de comprimir (son literales pw("...")).
    try:
        import mensajes
        src, _ = mensajes.aplica(src, c.meta.get('mensajes'),
                                 int(c.meta.get('max_score', 0) or 0),
                                 translit_disp)
    except Exception:
        pass
    _p(12, 'Podando codigo muerto...')
    src = poda(src)
    import os
    nombres = [translit_disp(c.game['objects'][oid].get('name', oid))
               for oid in c.objids]
    base = os.path.splitext(os.path.basename(out_path))[0]
    bin_name = base + '_texto.bin'
    src, rep, bin_blob = comprime(src, nombres, c.avisos, bin_name,
                                  progreso=progreso, modo=modo)
    # FX por AY: en 128K se embeben los efectos usados; en 48K (sin AY) solo el
    # reproductor mudo (para que los playfx() compilen sin gastar RAM).
    src = aplica_fx(src, game, clock=1773400, embed=(modo != '48k'))
    # carpeta de imagenes por modo: 128K -> img/Spectrum (.scr ULA), resto img/.
    _imgsub = {'128k': os.path.join('img', 'Spectrum'),
               '48k': os.path.join('img', '48')}.get(modo, 'img')
    # raiz del juego: el .bas y los temporales van en temp/<target>/, pero los
    # assets (img/, music/) viven en la raiz del juego.
    _outdir = os.path.dirname(out_path) or '.'
    if os.path.basename(os.path.dirname(_outdir)).lower() == 'temp':   # temp/<target>
        _raiz = os.path.dirname(os.path.dirname(_outdir))
    elif os.path.basename(_outdir).lower() == 'temp':                 # temp
        _raiz = os.path.dirname(_outdir)
    else:
        _raiz = _outdir
    img_dir = os.path.join(_raiz, _imgsub)
    # color de borde para el cargador BASIC del TAP (lo lee empaqueta48/128 desde
    # border.txt; metadata['border'] 0-7, por defecto 0 = negro).
    try:
        _bd = int((game.get('metadata') or {}).get('border', 0) or 0) & 7
    except (TypeError, ValueError):
        _bd = 0
    try:
        with open(os.path.join(_outdir, 'border.txt'), 'w', encoding='ascii') as f:
            f.write(str(_bd))
    except OSError:
        pass
    img_lineas = []
    if modo == '128k':
        extra, tabla, scr_off, img_lineas = imagenes_128k(
            img_dir, c.locids, c.locidx, len(bin_blob), progreso=progreso)
        if tabla or scr_off is not None:
            src = aplica_imagenes(src, tabla, max(c.locidx.values()), scr_off)
            bin_blob += extra
        # musica AY del menu: primer .psg de la carpeta music/
        musdir = os.path.join(_raiz, 'music')
        psg_stream, psg_nom = _leer_psg(musdir)
        if psg_stream is not None:
            if scr_off is None:
                c.avisos.append('musica del menu: hay .psg en music/ pero falta '
                                'img/screen.scr (pantalla de presentacion); se omite')
            else:
                # PSG en RAM principal (incbin al final del codigo). Se escribe
                # completo; el editor lo recorta a la RAM libre antes de compilar.
                musfile = 'musica.bin'        # nombre fijo (sin espacios) en temp/
                with open(os.path.join(_outdir, musfile), 'wb') as f:
                    f.write(psg_stream)
                src = aplica_musica(src, musfile, scr_off)
                img_lineas.append('musica del menu: %s (%d bytes PSG; se recorta '
                                  'a la RAM principal libre al compilar)'
                                  % (psg_nom, len(psg_stream)))
    elif os.path.isdir(img_dir):
        n_img = len([lid for lid in c.locids
                     if os.path.isfile(os.path.join(img_dir, lid + '.scr'))])
        if n_img:
            c.avisos.append('%d imagenes en img/ ignoradas '
                            '(solo se incrustan en modo 128K)' % n_img)
    import shutil
    here = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.dirname(out_path) or '.'

    def _copylib(name):
        """Copia la librería de fuente junto al .bas, salvo que ya esté ahí
        (al exportar dentro de la propia carpeta del proyecto, origen=destino)."""
        s = os.path.join(here, name)
        d = os.path.join(outdir, name)
        if os.path.isfile(s) and os.path.abspath(s) != os.path.abspath(d):
            shutil.copy(s, d)

    # Fuente segun idioma: _pt (acentos portugueses) o _es (español).
    _fsuf = '_pt' if _PT_LANG else '_es'
    if columnas == 64:
        # Fuente propia de 64 col CON acentos (códigos 144-159).
        src = src.replace('#include <print64.bas>', '#include "print64%s.bas"' % _fsuf)
        _copylib('print64%s.bas' % _fsuf)
    elif columnas == 42:
        # Fuente de 42 col CON acentos.
        src = (src.replace('#include <print64.bas>', '#include "print42%s.bas"' % _fsuf)
                  .replace('printat64(', 'printat42(')
                  .replace('print64(', 'print42(')
                  .replace('avail = 64 - ccol', 'avail = 42 - ccol')
                  .replace('LEN(s$) < 60', 'LEN(s$) < 38'))
        _copylib('print42%s.bas' % _fsuf)
    elif columnas == 32:
        # 32 col usa el PRINT de la ROM; los acentos (144-159) se cargan como
        # UDGs en initUDG() (llamado tras initDic). Set ES o PT segun idioma.
        udgdata = ','.join(str(b) for b in (_UDG_BYTES_PT if _PT_LANG else _UDG_BYTES))
        shim = ('DIM p32y AS UBYTE\n'
                'DIM p32x AS UBYTE\n'
                'SUB printat64(y AS UBYTE, x AS UBYTE)\n'
                '    p32y = y: p32x = x\n'
                'END SUB\n'
                'SUB print64(t$ AS STRING)\n'
                '    PRINT AT p32y, p32x; t$;\n'
                'END SUB\n'
                'SUB initUDG()\n'
                '    DIM iu AS UINTEGER\n'
                '    DIM adu AS UINTEGER\n'
                '    DIM bu AS UBYTE\n'
                '    adu = PEEK(23675) + 256 * PEEK(23676)\n'
                '    RESTORE udgdata\n'
                '    FOR iu = 0 TO 127\n'
                '        READ bu\n'
                '        POKE adu + iu, bu\n'
                '    NEXT iu\n'
                'END SUB\n'
                'udgdata:\n'
                'DATA ' + udgdata)
        src = (src.replace('#include <print64.bas>', shim)
                  .replace('avail = 64 - ccol', 'avail = 32 - ccol')
                  .replace('LEN(s$) < 60', 'LEN(s$) < 28'))
        src = src.replace('\ninitDic()\n', '\ninitDic()\ninitUDG()\n', 1)
    _p(95, 'Escribiendo ficheros...')
    # latin-1: los acentos van como bytes 144-159 (literales con {VAR} que no
    # pasan por el diccionario los conservan tal cual en el .bas).
    # utf-8-sig (con BOM): zxbc lo lee como UTF-8 y emite cada char con ord(c),
    # asi los codigos UDG de acentos (0x80-0x9F; p.ej. 0x90 = 'a' acentuada del
    # portugues) sobreviven. cp1252 no define 0x81/0x8D/0x8F/0x90/0x9D y por eso
    # la version portuguesa fallaba al compilar ("Invalid file encoding").
    with open(out_path, 'w', encoding='utf-8-sig') as f:
        f.write(src)
    bin_path = os.path.join(os.path.dirname(out_path) or '.', bin_name)
    with open(bin_path, 'wb') as f:
        f.write(bin_blob)
    nom = os.path.basename(out_path)
    if modo == '128k':
        emp_path = os.path.join(os.path.dirname(out_path) or '.', 'empaqueta128.py')
        with open(emp_path, 'w', encoding='utf-8') as f:
            f.write(EMPAQUETA128)
        informe = [f'Exportado (128K): {out_path} (+ {bin_name} + empaqueta128.py)', rep]
        informe.extend(img_lineas)
        informe.append('Imagenes: pon img/<id_localizacion>.scr (6912 o 2304 '
                       'bytes) junto al .bas y reexporta; se comprimen con '
                       'ZX0 en los bancos y se dibujan al entrar en la '
                       'localizacion (texto en las 16 filas inferiores).')
        informe.append('Paso 1: zxb --org 24576 --heap-size 4096 '
                       '--array-base=0 --string-base=0 -O2 ' + nom)
        informe.append('Paso 2: python empaqueta128.py ' +
                       nom.replace('.bas', '.bin') + ' ' + bin_name + ' juego128.tap')
        informe.append('Pantalla de carga: si hay img/screen.scr (6912 bytes) se '
                       'incluye en el TAP (orden: BASIC, pantalla, juego, bancos).')
        informe.append('Texto+imagenes van en los bancos 1/3/4/6/7 del 128K (hasta '
                       '80 KB en 5 bancos) y el motor dispone de ~35 KB propios. '
                       'Cargar con 128 BASIC: LOAD "" (no usar modo 48K/USR0).')
    else:
        emp_path = os.path.join(os.path.dirname(out_path) or '.', 'empaqueta48.py')
        with open(emp_path, 'w', encoding='utf-8') as f:
            f.write(EMPAQUETA48)
        informe = [f'Exportado (48K): {out_path} (+ ' + bin_name +
                   ' + empaqueta48.py)', rep]
        informe.append('Paso 1: zxb --org 24000 --heap-size 1792 --array-base=0 '
                       '--string-base=0 -O2 ' + nom)
        informe.append('Paso 2: python empaqueta48.py ' +
                       nom.replace('.bas', '.bin') + ' juego.tap')
        informe.append('Pantalla de carga: pon img/screen.scr (6912 bytes) junto al '
                       '.bas; el TAP cargara en orden BASIC, pantalla y juego.')
        informe.append('Limite 48K: el binario -O2 debe quedar bajo ~39.7 KB '
                       '(org 24000 + heap 1792). Como referencia, motor ~14 KB '
                       'mas ~1.4 bytes por caracter de texto comprimido. Si no '
                       'cabe: acorta textos, quita objetos o divide el juego, '
                       'o exporta en modo 128K.')
    _p(100, 'Completado.')
    if c.avisos:
        informe.append(f'AVISOS ({len(c.avisos)}):')
        vistos = set()
        for a in c.avisos:
            if a not in vistos:
                vistos.add(a)
                informe.append('  - ' + a)
    return '\n'.join(informe)

def main():
    import yaml
    if len(sys.argv) < 3:
        print('uso: python spectrum_export.py juego.yaml salida.bas')
        sys.exit(1)
    with open(sys.argv[1], encoding='utf-8') as f:
        game = yaml.safe_load(f)
    print(export_bas(game, sys.argv[2]))

if __name__ == '__main__':
    main()
