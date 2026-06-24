#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpc_export.py — Exporta un juego Scriba (dict/YAML) a LOCOMOTIVE BASIC para
Amstrad CPC (464/664/6128), reutilizando el MOTOR de spectrum_export
(recolecta, _objref, translit, quoting) igual que hace next_export.

Diferencia clave con el backend Spectrum: alli se emite Boriel ZX Basic
(BASIC compilado, tipado, con FUNCTION/SUB/ENDIF). El CPC nativo es Locomotive
BASIC: interpretado, numerado por lineas, con GOSUB/RETURN y SIN ENDIF. Por eso
este modulo:

  · Mapea los predicados PAWS a expresiones booleanas Locomotive (cierto=-1,
    falso=0; AND/OR/NOT son bit a bit, asi que el algebra booleana coincide).
  · Baja los bloques estructurados IF/ELSE/ENDIF y ON/ENDON a saltos
    'IF NOT(cond) THEN GOTO Lxx', con un ensamblador (Asm) y un enlazador que
    asigna numeros de linea en dos pasadas.

MODELO DE RUNTIME (Locomotive)
  Escalares:  P  loc del jugador     VB verbo   N1/N2 nombres
              HD  marcado (MATCH)    QT salir    DK  oscuridad actual
  Arrays:     OL%(o) ubicacion objeto   OT%(o) encendido
              OO%(o) abierto            OK%(o) cerrado
              OF/OW/OG/OA/OBN/OY/HM    fixed/wearable/light/openable/noun/key/has-msg
              TA%(t)/TC%(t)/TD%(t)      timers (activo/actual/duracion)
              GV%(i) variables del juego (PUNTOS, TURNOS, ...)
  DEF FN:     FNca(o)=carried   FNwo(o)=worn   FNpr(o)=present (un nivel)
              FNns$(x)= STR$ sin el espacio inicial de los positivos

Uso:  from cpc_export import export_bas; export_bas(game, 'juego.bas', modo=1)
      python cpc_export.py juego.yaml 1     -> genera juego_cpc1.bas y valida
"""

import re
import spectrum_export as sx
import paws_lang

# Constantes de ubicacion (compartidas con el motor del Spectrum)
LOC_INVEN  = sx.LOC_INVEN     # 240
LOC_PUESTO = sx.LOC_PUESTO    # 241
LOC_NADA   = sx.LOC_NADA      # 0
CONT_BASE  = sx.CONT_BASE     # 100

# Depacker RLE PackBits en Z80: lee de &8B00, descomprime a &C000 (pantalla).
# Position-independent; se vuelca a &8A00 y se invoca con CALL &8A00.
DEPACK_Z80 = bytes([
    0x21,0x00,0x8B, 0x11,0x00,0xC0,
    0x7E,0x23,0xCB,0x7F,0x28,0x10,
    0xED,0x44,0x3C,0x47,0x7E,0x23,
    0x12,0x13,0x05,0x20,0xFB,
    0x7A,0xB3,0x20,0xEB,0xC9,
    0x3C,0x47,
    0x7E,0x23,0x12,0x13,0x05,0x20,0xF9,
    0x7A,0xB3,0x20,0xDD,0xC9,
])


# ─── Transliteracion para el CPC ────────────────────────────────────────────
# Primera version: a ASCII (como el vocabulario del Spectrum). El juego de
# caracteres del CPC SI tiene acentos y ñ en ROM; emitir esos codigos es una
# mejora posterior (translit_cpc es el unico punto a tocar).
def translit_cpc(s):
    return sx.translit(s)


# ─── Preparacion: indices de variables del juego (GV%) ──────────────────────
def cpc_prepare(c):
    """Asigna un indice GV%() a cada variable del juego. PUNTOS->marcador."""
    c.varidx = {}
    for k in c.vars:
        c.varidx[k] = len(c.varidx)
    c.sc_idx = c.varidx.get('PUNTOS', 0)
    return c


def _gv(c, name):
    name = re.sub(r'[^A-Za-z0-9]', '', name)
    if name not in c.varidx:
        c.vars.setdefault(name, 0)
        c.varidx[name] = len(c.varidx)
    return f'GV%({c.varidx[name]})'


# ─── Predicados PAWS -> expresion booleana Locomotive ───────────────────────
def _pred2cpc(c, kw, args):
    o = lambda a: sx._objref(c, a)
    if kw == 'AT':       return f'(P={c.locidx.get(args[0], 0)})'
    if kw == 'NOTAT':    return f'(P<>{c.locidx.get(args[0], 0)})'
    if kw == 'CARRIED':  return f'FNca({o(args[0])})'
    if kw == 'NOTCARR':  return f'(NOT FNca({o(args[0])}))'
    if kw == 'PRESENT':  return f'FNpr({o(args[0])})'
    if kw == 'ABSENT':   return f'(NOT FNpr({o(args[0])}))'
    if kw == 'WORN':     return f'FNwo({o(args[0])})'
    if kw == 'NOTWORN':  return f'(NOT FNwo({o(args[0])}))'
    if kw == 'ISAT':
        dst = args[1]
        if dst in c.locidx:                 dv = c.locidx[dst]
        elif dst in ('INVEN', 'PUESTO', 'NADA'):
            dv = {'INVEN': LOC_INVEN, 'PUESTO': LOC_PUESTO, 'NADA': LOC_NADA}[dst]
        else:                               dv = CONT_BASE + o(dst)
        return f'(OL%({o(args[0])})={dv})'
    if kw == 'DARK':     return '(DK<>0)'
    if kw == 'CHANCE':   return f'(INT(RND*100)+1<={args[0]})'
    if kw == 'TIMER':    return f'(TC%({c.timidx.get(args[0], 0)})={args[1]})'
    if kw == 'ZERO':     return f'({_gv(c, args[0])}=0)'
    if kw == 'NOTZERO':  return f'({_gv(c, args[0])}<>0)'
    if kw == 'EQ':       return f'({_gv(c, args[0])}={args[1]})'
    if kw == 'GT':       return f'({_gv(c, args[0])}>{args[1]})'
    if kw == 'LT':       return f'({_gv(c, args[0])}<{args[1]})'
    if kw == 'HASOBJOPEN': return f'(OO%({o(args[0])})<>0)'
    if kw == 'VERB':
        p = args[0].upper() if args else '*'
        return '-1' if p == '*' else f'(VB={c.verbid.get(p, 0)})'
    if kw == 'NOUN1':
        p = args[0].upper() if args else '*'
        if p == '_': return '(N1=0)'
        return '-1' if p == '*' else f'(N1={c.nounid.get(translit_cpc(p[:5]).upper(), 0)})'
    if kw == 'NOUN2':
        p = args[0].upper() if args else '*'
        if p == '_': return '(N2=0)'
        return '-1' if p == '*' else f'(N2={c.nounid.get(translit_cpc(p[:5]).upper(), 0)})'
    c.avisos.append(f'condicion no soportada (CPC): {kw} {args}')
    return '-1'


class _CPCBackend:
    """Backend de emision Locomotive BASIC para paws_lang."""
    def __init__(self, c):
        self.c = c
    def var(self, name):
        return _gv(self.c, name)
    def num(self, n):
        return str(n)
    def predicate(self, kw, args):
        return _pred2cpc(self.c, kw, args)


def cond2cpc(c, s):
    try:
        return paws_lang.emit_condition(paws_lang.parse_condition(s), _CPCBackend(c))
    except paws_lang.ParseError as e:
        c.avisos.append(f'condicion con sintaxis invalida {s!r}: {e}')
        return '-1'


def _print2cpc(c, texto):
    """Construye la expresion de cadena para PRINT, con {VAR} -> FNns$(GV%(i))."""
    texto = translit_cpc(texto)
    partes = re.split(r'\{([A-Z_][A-Z0-9_]*)\}', texto)
    ql = sx._qchr if len(partes) > 1 else sx.q
    expr = []
    for i, p in enumerate(partes):
        if i % 2 == 0:
            if p:
                expr.append(ql(p))
        else:
            expr.append(f'FNns$({_gv(c, p)})')
    return ' + '.join(expr) if expr else '""'


# ─── Una sentencia PAWS -> lista de sentencias Locomotive ───────────────────
def stmt2cpc(c, linea, dentro_resp):
    partes = linea.strip().split(None, 1)
    if not partes:
        return []
    cmd = partes[0].upper()
    resto = partes[1].strip() if len(partes) > 1 else ''
    o = lambda a: sx._objref(c, a)

    if cmd in ('PRINT', 'PRINTLN'):
        return [f'A$={_print2cpc(c, sx._extraestr(resto))}', 'GOSUB {PW}']
    if cmd == 'LET':
        if '=' in resto:
            lhs, rhs = resto.split('=', 1)
            try:
                rhs_b = paws_lang.emit_expr(paws_lang.parse_expr(rhs), _CPCBackend(c))
            except paws_lang.ParseError as e:
                c.avisos.append(f'expresion LET invalida {rhs!r}: {e}')
                rhs_b = '0'
            return [f'{_gv(c, lhs.strip())}={rhs_b}']
        return []
    if cmd == 'ADDSCORE':
        return [f'AN={resto.strip()}', 'GOSUB {ADDSC}']
    if cmd == 'GOTO':
        return [f'P={c.locidx.get(resto.strip(), 0)}', 'GOSUB {GOLOC}']
    if cmd == 'DESC':    return ['GOSUB {DESCL}']
    if cmd == 'SCORE':   return ['GOSUB {SHOWPTS}']
    if cmd == 'END':     return ['GOSUB {GAMEOVER}', 'RETURN']
    if cmd == 'QUIT':    return ['QT=1', 'RETURN']
    if cmd == 'NEWLINE': return ['PRINT']
    if cmd == 'CLS':     return ['CLS']
    if cmd == 'MATCH':   return (['HD=1', 'RETURN'] if dentro_resp else [])
    if cmd == 'REM':     return ["REM " + translit_cpc(resto)]
    # ── efectos: mapeo Spectrum -> Locomotive ──
    if cmd == 'BORDER':  return [f'BORDER {resto}']           # 0-26 en CPC
    if cmd == 'INK':
        # 2 args (INK pluma,color) -> INK del CPC (cambia la PALETA);
        # 1 arg (INK n, estilo Spectrum) -> selecciona pluma de texto con PEN
        return [f'INK {resto}'] if ',' in resto else [f'PEN {resto}']
    if cmd == 'PAPER':   return [f'PAPER {resto}']
    if cmd in ('FLASH', 'INVERSE'):
        return [f"REM {cmd} {resto} (sin equivalente directo CPC)"]
    if cmd == 'BEEP':    return ['SOUND 1,90,15,12']          # aprox.: pitido corto
    if cmd == 'PAUSE':
        return [f'PZ={resto.strip() or 0}', 'GOSUB {PAUSEK}']
    # ── manipulacion de objetos / timers ──
    if cmd == 'GET':     return [f'OL%({o(resto)})={LOC_INVEN}']
    if cmd == 'DROP':    return [f'OL%({o(resto)})=P']
    if cmd == 'WEAR':    return [f'OL%({o(resto)})={LOC_PUESTO}']
    if cmd == 'REMOVE':  return [f'OL%({o(resto)})={LOC_INVEN}']
    if cmd == 'DESTROY': return [f'OL%({o(resto)})={LOC_NADA}']
    if cmd in ('CREATE', 'PUT'):
        a = resto.split()
        return [f'OL%({o(a[0])})={c.locval(a[1])}']
    if cmd == 'PUTIN':
        a = resto.split()
        return [f'OL%({o(a[0])})={CONT_BASE + o(a[1])}']
    if cmd == 'TAKEOUT':
        a = resto.split()
        return [f'OL%({o(a[0])})={LOC_INVEN}']
    if cmd == 'LIT':     return [f'OT%({o(resto)})=1']
    if cmd == 'UNLIT':   return [f'OT%({o(resto)})=0']
    if cmd == 'OPEN':
        ob = o(resto); return [f'OO%({ob})=1', f'OK%({ob})=0']
    if cmd == 'CLOSE':   return [f'OO%({o(resto)})=0']
    if cmd == 'LOCK':    return [f'OK%({o(resto)})=1']
    if cmd == 'UNLOCK':  return [f'OK%({o(resto)})=0']
    if cmd == 'TIMER_START':
        t = c.timidx.get(resto.strip(), 0)
        return [f'TA%({t})=1', f'TC%({t})=TD%({t})']
    if cmd == 'TIMER_STOP':
        return [f'TA%({c.timidx.get(resto.strip(), 0)})=0']
    if cmd == 'TIMER_RESET':
        t = c.timidx.get(resto.strip(), 0)
        return [f'TC%({t})=TD%({t})']
    c.avisos.append(f'comando no soportado (CPC): {linea!r}')
    return ["REM ?? " + translit_cpc(linea)]


def _on_cond_cpc(c, var, slot, kind):
    """Condicion para un hueco de ON. Devuelve None si '*'."""
    if slot == '*':  return None
    if slot == '_':  return f'{var}=0'

    def ident(tok):
        if kind == 'verb':
            return c.verbid.get(tok, c.verbalias.get(tok, 0))
        return c.nounid.get(translit_cpc(tok[:5]).upper(), 0)

    ids = [ident(t) for t in slot]
    if len(ids) == 1:
        return f'{var}={ids[0]}'
    return '(' + ' OR '.join(f'{var}={i}' for i in ids) + ')'


# ─── Ensamblador con etiquetas -> lineas numeradas Locomotive ───────────────
class Asm:
    """Acumula sentencias y saltos con etiquetas; render() asigna numeros de
    linea. Las etiquetas locales son tuplas ('L',n); las globales (rutinas
    runtime) son cadenas como 'PW','DESCL' referenciadas como {PW} en el texto."""
    def __init__(self):
        self.ops = []
        self._n = 0

    def newlabel(self):
        self._n += 1
        return ('L', self._n)

    def place(self, lbl):       self.ops.append(('LBL', lbl))
    def stmt(self, s):          self.ops.append(('S', s))
    def goto(self, lbl):        self.ops.append(('GOTO', lbl))
    def iffalse(self, cond, lbl): self.ops.append(('IFF', cond, lbl))


def script2cpc(c, script, dentro_resp, asm=None):
    """Transpila un script PAWS completo a un Asm (lineas + saltos)."""
    if asm is None:
        asm = Asm()
    if isinstance(script, list):
        if script and not isinstance(script[0], str):
            c.avisos.append('bloque JSON legacy ignorado')
            return asm
        lineas = list(script)
    elif isinstance(script, str):
        lineas = script.split('\n')
    else:
        return asm

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

    i = [0]

    def bloque(hasta):
        while i[0] < len(prog):
            ln = prog[i[0]]
            up = ln.upper()
            if up in hasta:
                return ln
            i[0] += 1
            if up.startswith('IF ') and ' THEN' in up:
                idx = up.rfind(' THEN')
                cond = cond2cpc(c, ln[3:idx].strip())
                l_else = asm.newlabel()
                asm.iffalse(cond, l_else)          # si falso, salta tras el bloque
                fin = bloque(('ELSE', 'ENDIF'))
                if fin and fin.upper() == 'ELSE':
                    i[0] += 1
                    l_end = asm.newlabel()
                    asm.goto(l_end)
                    asm.place(l_else)
                    fin = bloque(('ENDIF',))
                    if fin:
                        i[0] += 1
                    asm.place(l_end)
                else:
                    if fin:
                        i[0] += 1
                    asm.place(l_else)
            elif up.startswith('ON '):
                pa = ln.split(None, 1)
                s = paws_lang.parse_on(pa[1] if len(pa) > 1 else '')
                conds = []
                for var, slot, kind in (('VB', s[0], 'verb'),
                                        ('N1', s[1], 'noun'),
                                        ('N2', s[2], 'noun')):
                    cnd = _on_cond_cpc(c, var, slot, kind)
                    if cnd:
                        conds.append(cnd)
                cond = ' AND '.join(conds) if conds else '-1'
                l_end = asm.newlabel()
                asm.iffalse(cond, l_end)
                fin = bloque(('ENDON',))
                if fin:
                    i[0] += 1
                asm.place(l_end)
                if dentro_resp:
                    asm.stmt('IF HD THEN RETURN')
            else:
                for s in stmt2cpc(c, ln, dentro_resp):
                    asm.stmt(s)
        return None

    bloque(())
    return asm


def render(asm, start=1000, step=2):
    """Asigna numeros de linea al Asm y devuelve lineas BASIC ya enlazadas.
    Etiquetas locales = tuplas; rutinas runtime = nombres ({NOMBRE} en el texto)."""
    produced, pending = [], []
    for op in asm.ops:
        if op[0] == 'LBL':
            pending.append(op[1]); continue
        produced.append((op, list(pending))); pending = []
    if pending:
        produced.append((('S', 'REM'), list(pending)))

    num = {}
    n = start
    for (_op, labs) in produced:
        for l in labs:
            num[l] = n
        n += step
    names = {k: v for k, v in num.items() if isinstance(k, str)}

    def ref(l):
        return num.get(l, 0)

    def subst(text):
        return re.sub(r'\{([A-Z_][A-Z0-9_]*)\}',
                      lambda m: str(names.get(m.group(1), 0)), text)

    out, n = [], start
    for (op, _labs) in produced:
        if op[0] == 'S':
            out.append(f'{n} {subst(op[1])}')
        elif op[0] == 'GOTO':
            out.append(f'{n} GOTO {ref(op[1])}')
        elif op[0] == 'IFF':
            out.append(f'{n} IF NOT({op[1]}) THEN GOTO {ref(op[2])}')
        n += step
    return out


# ─── Generador del programa Locomotive BASIC ────────────────────────────────
def genera_cpc(c, modo=1, image_locs=None, menu_inks=None, raw_locs=None, music=False,
               comprime_texto=False):
    """Genera el programa Locomotive BASIC completo (lista de lineas)."""
    g = c.game
    imgs = image_locs is not None
    if imgs:
        modo = 2
    nobj = max(1, len(c.objids))
    nloc = max(1, len(c.locids))
    ntim = max(1, len(c.timids))
    nvar = max(1, len(c.varidx))
    width = 40 if (modo == 1 and not imgs) else 80
    avw = width - 1
    maxsc = int(c.meta.get('max_score', 0))
    start = c.locidx.get(c.meta.get('start_location'), 1)
    TODO = c.nounid['TODO']
    titulo = translit_cpc(c.meta.get('title', 'Aventura'))

    asm = Asm()
    S = asm.stmt
    LBL = asm.place
    nl = asm.newlabel

    def PR(texto):
        for p in sx.parrafos(texto):
            S('A$=' + sx.q(translit_cpc(p))); S('GOSUB {PW}')

    def guard_locs(items, body):
        """Para cada (idx, datos) emite: IF P=idx THEN <body>; salta el resto."""
        for idx, dat in items:
            skip = nl()
            asm.iffalse(f'(P={idx})', skip)
            body(idx, dat)
            LBL(skip)

    # ── cabecera + pantalla + DIM + DEF FN ──
    S(f'REM {titulo} - Amstrad CPC (Locomotive BASIC)')
    S('REM Generado por Scriba (cpc_export)')
    if imgs:
        S('MEMORY &89FF')
        if menu_inks:
            # pantalla de titulo en Modo 0 (16 colores), luego al Modo 2 del juego
            S('MODE 0')
            S('RESTORE {MENUPAL}')
            S('FOR I=0 TO 15:READ DV:INK I,DV:NEXT')
            S('LOAD"MENU.SCR",&C000')
            if music:
                # musica de titulo Arkos AKY (.bin ensamblado a &8B00):
                # &8B00 init, &8B03 play (1 frame), &8B06 stop; &BD19 = barrido
                S('LOAD"MUSIC.BIN",&8B00:CALL &8B00')
                S('WHILE INKEY$<>"":WEND')
                LBL('MUSLOOP')
                S('CALL &BD19:CALL &8B03')
                S('IF INKEY$="" THEN GOTO {MUSLOOP}')
                S('CALL &8B06')
            else:
                S('WHILE INKEY$<>"":WEND:WHILE INKEY$="":WEND')
        S('MODE 2:INK 0,0:INK 1,26:PEN 1:PAPER 0:BORDER 0')
        S('WINDOW #0,1,80,9,25')
    else:
        S(f'MODE {modo}:INK 0,1:INK 1,24:PEN 1:PAPER 0:BORDER 1')
    S(f'DIM EX%({nloc},5),LD%({nloc})')
    S(f'DIM OL%({nobj}),OI%({nobj}),OT%({nobj}),OO%({nobj}),OK%({nobj}),OF%({nobj})')
    S(f'DIM OW%({nobj}),OG%({nobj}),OA%({nobj}),OBN%({nobj}),OY%({nobj}),HM%({nobj})')
    S(f'DIM NM$({nobj})')
    S(f'DIM TA%({ntim}),TL%({ntim}),TC%({ntim}),TD%({ntim})')
    S(f'DIM GV%({nvar})')
    # carried = en inventario o puesto ; worn = puesto ; present = un nivel
    S('DEF FNca(o)=(OL%(o)=240 OR OL%(o)=241)')
    S('DEF FNwo(o)=(OL%(o)=241)')
    # indice de contenedor ACOTADO a [1,nobj]: Locomotive no hace cortocircuito
    # en AND/OR, asi que el acceso al array debe ser siempre valido aunque el
    # guard (OL%(o)>100 AND OL%(o)<240) sea falso.
    S(f'DEF FNci(o)=MAX(1,MIN({nobj},OL%(o)-100))')
    S('DEF FNpr(o)=(OL%(o)=240 OR OL%(o)=241 OR OL%(o)=P OR (OL%(o)>100 AND OL%(o)<240 AND OO%(FNci(o))=1 AND (OL%(FNci(o))=P OR OL%(FNci(o))=240 OR OL%(FNci(o))=241)))')
    S('DEF FNns$(x)=MID$(STR$(x),2+(x<0))')
    if imgs:
        S('RESTORE {DEPDATA}')
        S(f'FOR I=0 TO {len(DEPACK_Z80)-1}:READ DV:POKE &8A00+I,DV:NEXT')

    # ── inicio / reinicio ──
    LBL('START')
    S('QT=0:HD=0:DK=0')
    S(f'FOR I=0 TO {nvar-1}:GV%(I)=0:NEXT')
    for k, idx in c.varidx.items():
        if c.vars.get(k):
            S(f'GV%({idx})={c.vars[k]}')
    S('GOSUB {INITMAP}:GOSUB {INITOBJ}')
    S(f'P={start}')
    S('GOSUB {ONSTART}')           # on_start PRIMERO: puede fijar INK/PAPER/BORDER...
    S('CLS')                        # limpia ya con los colores que haya puesto
    msg_ini = sx.parrafos(c.meta.get('start_message', ''))
    for p in msg_ini:
        S('A$=' + sx.q(translit_cpc(p))); S('GOSUB {PW}')
    if msg_ini:
        S('PZ=0:GOSUB {PAUSEK}')
    S('GOSUB {DARKCHK}:GOSUB {DESCL}:GOSUB {ONENTER}')

    # ── bucle principal ──
    LBL('LOOP')
    S('PRINT')
    S('PRINT "> ";:LINE INPUT LI$')
    S('IF LEN(LI$)=0 THEN GOTO {LOOP}')
    S('GOSUB {BEFORET}')
    S('IF QT=1 THEN GOTO {ENDGAME}')
    S('GOSUB {PARSE}:GOSUB {DARKCHK}')
    no_ent = nl()
    asm.iffalse('(VB=0)', no_ent)
    S('A$="No entiendo eso.":GOSUB {PW}:GOTO {TURNEND}')
    LBL(no_ent)
    S('GOSUB {RESP}')
    S('IF QT=0 AND HD=0 THEN GOSUB {BUILTINS}')
    LBL('TURNEND')
    S('IF QT=0 THEN GOSUB {TICK}')
    S('IF QT=0 THEN GOSUB {AFTERT}')
    S('IF QT=0 THEN GOTO {LOOP}')
    LBL('ENDGAME')
    S('A$="Pulsa una tecla...":GOSUB {PW}:PZ=0:GOSUB {PAUSEK}:GOTO {START}')

    # ── rutina de impresion con word-wrap (PW) ──
    LBL('PW')
    S('T$=A$')
    pwl = nl()
    LBL(pwl)
    pwfit = nl()
    asm.iffalse(f'(LEN(T$)>{avw})', pwfit)
    # buscar ultimo espacio dentro de avw
    S(f'CU=0:FOR J={avw} TO 1 STEP -1:IF MID$(T$,J,1)=" " AND CU=0 THEN CU=J')
    S('NEXT')
    nocut = nl()
    asm.iffalse('(CU<>0)', nocut)
    S('PRINT LEFT$(T$,CU-1):T$=MID$(T$,CU+1)')
    asm.goto(pwl)
    LBL(nocut)
    S(f'PRINT LEFT$(T$,{avw}):T$=MID$(T$,{avw+1})')
    asm.goto(pwl)
    LBL(pwfit)
    S('PRINT T$:RETURN')

    # ── pausa / espera de tecla ──
    LBL('PAUSEK')
    pkw = nl()
    asm.iffalse('(PZ>0)', pkw)
    S('FOR Z=1 TO PZ*30:NEXT:RETURN')
    LBL(pkw)
    S('WHILE INKEY$<>"":WEND:WHILE INKEY$="":WEND:RETURN')

    # ── oscuridad: recalcula DK ──
    LBL('DARKCHK')
    S('DK=0:IF LD%(P)=0 THEN RETURN')
    S(f'DK=1:FOR I=1 TO {nobj}:IF OG%(I)=1 AND OT%(I)=1 AND (FNca(I) OR OL%(I)=P) THEN DK=0')
    S('NEXT:RETURN')

    # ── localizar objeto por noun (NB -> OB) ──
    LBL('PORNOUN')
    S(f'OB=0:FOR I=1 TO {nobj}:IF OBN%(I)=NB AND OB=0 AND FNca(I) THEN OB=I')
    S('NEXT:IF OB>0 THEN RETURN')
    S(f'FOR I=1 TO {nobj}:IF OBN%(I)=NB AND OB=0 AND FNpr(I) THEN OB=I')
    S('NEXT:RETURN')

    # ── marcador / fin ──
    LBL('SHOWPTS')
    S(f'A$="Puntuacion: "+FNns$(GV%({c.sc_idx}))+"/{maxsc}":GOSUB {{PW}}:RETURN')
    LBL('ADDSC')
    S(f'GV%({c.sc_idx})=GV%({c.sc_idx})+AN')
    S('A$="[+"+FNns$(AN)+" puntos]":GOSUB {PW}:RETURN')
    LBL('GAMEOVER')
    S(f'PRINT:A$="== FIN - Puntuacion: "+FNns$(GV%({c.sc_idx}))+"/{maxsc} ==":GOSUB {{PW}}:QT=1:RETURN')
    LBL('GOLOC')
    S('GOSUB {ONENTER}:RETURN')

    # ── mensaje inicial de objeto (OE) ──
    LBL('MSGINI')
    for oid in c.objids:
        msg = g['objects'][oid].get('initial_message')
        if not msg:
            continue
        sk = nl()
        asm.iffalse(f'(OE={c.objidx[oid]})', sk)
        PR(msg)
        S('RETURN')
        LBL(sk)
    S('A$="Aqui hay "+NM$(OE)+".":GOSUB {PW}:RETURN')

    # ── examinar objeto (OE) ──
    LBL('EXDESC')
    for oid in c.objids:
        d = g['objects'][oid].get('description')
        if not d:
            continue
        sk = nl()
        asm.iffalse(f'(OE={c.objidx[oid]})', sk)
        PR(d)
        S('RETURN')
        LBL(sk)
    S('A$="No ves nada especial.":GOSUB {PW}:RETURN')

    # ── describir localizacion ──
    LBL('DESCL')
    if imgs:
        S('GOSUB {SHOWPIC}:GOSUB {DARKCHK}:CLS #0')
    else:
        S('GOSUB {DARKCHK}:PRINT')
    guard_locs([(c.locidx[lid], lid) for lid in c.locids],
               lambda idx, lid: S('A$=' + sx.q(translit_cpc(g['locations'][lid].get('name', lid).upper())) + ':GOSUB {PW}'))
    S('IF DK=1 THEN A$="Esta completamente oscuro. No puedes ver nada.":GOSUB {PW}:RETURN')
    def _desc_body(idx, lid):
        PR(g['locations'][lid].get('description', ''))
    guard_locs([(c.locidx[lid], lid) for lid in c.locids], _desc_body)
    # objetos visibles (el 'continue' del FOR salta a la etiqueta DLN = NEXT)
    S(f'FOR I=1 TO {nobj}')
    S('IF OL%(I)<>P THEN GOTO {DLN}')
    lfix = nl()
    asm.iffalse('(OF%(I)=1)', lfix)        # objeto fijo?
    lnomsg = nl()
    asm.iffalse('(HM%(I)=1)', lnomsg)      # fijo con mensaje inicial
    S('OE=I:GOSUB {MSGINI}')
    LBL(lnomsg)
    S('GOTO {DLN}')
    LBL(lfix)                              # objeto movil
    laq = nl()
    asm.iffalse('(OL%(I)=OI%(I))', laq)    # sigue en su sitio inicial -> su mensaje
    S('OE=I:GOSUB {MSGINI}')
    S('GOTO {DLN}')
    LBL(laq)
    S('A$="Aqui hay "+NM$(I)+".":GOSUB {PW}')
    LBL('DLN')
    S('NEXT')
    # salidas
    S('A$="Salidas:"')
    for d, et in zip(range(6), (' N', ' S', ' E', ' O', ' Subir', ' Bajar')):
        S(f'IF EX%(P,{d})>0 THEN A$=A$+"{et}"')
    S('GOSUB {PW}:RETURN')

    # ── coger / dejar (OE) ──
    if imgs:
        _raw = raw_locs or set()
        LBL('SHOWPIC')
        for _idx in sorted(image_locs):
            _sk = nl()
            asm.iffalse(f'(P={_idx})', _sk)
            if _idx in _raw:
                S(f'LOAD"PIC{_idx}.SCR",&C000')          # pantalla nativa cruda
            else:
                S(f'LOAD"PIC{_idx}.SCR",&8B00:CALL &8A00')  # comprimida + depack
            S('GOTO {SHPDONE}')
            LBL(_sk)
        S('LOAD"BLANK.SCR",&8B00:CALL &8A00')
        LBL('SHPDONE')
        S('RETURN')

    LBL('ENGCOGE')
    S('IF FNca(OE) THEN A$="Ya lo llevas.":GOSUB {PW}:RETURN')
    S('IF OF%(OE)=1 THEN A$="No puedes coger eso.":GOSUB {PW}:RETURN')
    S('OL%(OE)=240:A$="Coges "+NM$(OE)+".":GOSUB {PW}:RETURN')
    LBL('ENGDEJA')
    S('IF FNca(OE)=0 THEN A$="No lo llevas.":GOSUB {PW}:RETURN')
    S('OL%(OE)=P:A$="Dejas "+NM$(OE)+".":GOSUB {PW}:RETURN')

    # ── parser ──
    LBL('PARSE')
    S('VB=0:N1=0:N2=0:W$="":LI$=LI$+" "')
    S(f'FOR PX=1 TO LEN(LI$):CC$=MID$(LI$,PX,1)')
    S('IF CC$<>" " THEN W$=W$+CC$ ELSE GOSUB {PWORD}')
    S('NEXT:RETURN')
    LBL('PWORD')
    S('IF LEN(W$)=0 THEN RETURN')
    S('W$=UPPER$(W$):IF LEN(W$)>5 THEN W$=LEFT$(W$,5)')
    S('GOSUB {VERBID}')
    S('IF RV>0 AND VB=0 THEN VB=RV:W$="":RETURN')
    S('GOSUB {NOUNID}')
    S('IF RN>0 AND N1=0 THEN N1=RN:W$="":RETURN')
    S('IF RN>0 AND N2=0 THEN N2=RN')
    S('W$="":RETURN')

    def chain(label, aliases, outvar):
        LBL(label)
        S(f'{outvar}=0')
        porid = sx._alias_por_id(aliases)
        for i, palabras in sorted(porid.items()):
            palabras = sorted(set(w for w in palabras if w))
            for k in range(0, len(palabras), 4):
                grupo = palabras[k:k+4]
                cond = ' OR '.join(f'W$="{w}"' for w in grupo)
                S(f'IF {cond} THEN {outvar}={i}:RETURN')
        S('RETURN')
    chain('VERBID', c.verbalias, 'RV')
    chain('NOUNID', c.nounalias, 'RN')

    # ── on_enter / timers / condacts ──
    LBL('ONENTER')
    for lid in c.locids:
        sc = g['locations'][lid].get('on_enter')
        if not sc:
            continue
        sk = nl()
        asm.iffalse(f'(P={c.locidx[lid]})', sk)
        script2cpc(c, sc, False, asm)
        LBL(sk)
    S('RETURN')

    LBL('TICK')
    for tid in c.timids:
        t = c.timidx[tid]
        sk = nl()
        asm.iffalse(f'(TA%({t})=1)', sk)
        S(f'TC%({t})=TC%({t})-1')
        sk2 = nl()
        asm.iffalse(f'(TC%({t})<=0)', sk2)
        script2cpc(c, g['timers'][tid].get('on_expire'), False, asm)
        el = nl(); dn = nl()
        asm.iffalse(f'(TL%({t})=1)', el)
        S(f'TC%({t})=TD%({t})'); asm.goto(dn)
        LBL(el); S(f'TA%({t})=0'); LBL(dn)
        LBL(sk2); LBL(sk)
    S('RETURN')

    for name, clave in (('ONSTART', 'on_start'), ('BEFORET', 'before_turn'),
                        ('AFTERT', 'after_turn')):
        LBL(name)
        script2cpc(c, (g.get('condacts') or {}).get(clave), False, asm)
        S('RETURN')

    LBL('RESP')
    S('HD=0')
    script2cpc(c, (g.get('condacts') or {}).get('responses'), True, asm)
    S('RETURN')

    # ── builtins ──
    LBL('BUILTINS')
    # movimiento (verbos 1..6)
    mv = nl()
    asm.iffalse('(VB>=1 AND VB<=6)', mv)
    S('DD=EX%(P,VB-1)')
    nomove = nl()
    asm.iffalse('(DD<>0)', nomove)
    S('P=DD:GOSUB {DARKCHK}:GOSUB {DESCL}:GOSUB {ONENTER}:RETURN')
    LBL(nomove)
    S('A$="No puedes ir en esa direccion.":GOSUB {PW}:RETURN')
    LBL(mv)

    def verb_branch(vid, body):
        if not vid:
            return
        sk = nl()
        asm.iffalse(f'(VB={vid})', sk)
        body()
        LBL(sk)

    def vb(name):
        return c.verbid.get(name, 0)

    # INVENTARIO
    def _inven():
        S('O=0')
        S(f'FOR I=1 TO {nobj}:IF OL%(I)=240 THEN IF O=0 THEN A$="Llevas:":GOSUB {{PW}}:O=1')
        S(f'IF OL%(I)=240 THEN A$="  "+NM$(I):GOSUB {{PW}}')
        S('NEXT')
        S(f'FOR I=1 TO {nobj}:IF OL%(I)=241 THEN O=1:A$="Llevas puesto: "+NM$(I):GOSUB {{PW}}')
        S('NEXT')
        S('IF O=0 THEN A$="No llevas nada.":GOSUB {PW}')
        S('RETURN')
    verb_branch(vb('INVEN'), _inven)
    verb_branch(vb('PUNT'), lambda: S('GOSUB {SHOWPTS}:RETURN'))
    verb_branch(vb('SALIR'),
                lambda: S('A$="Abandonas la aventura.":GOSUB {PW}:GOSUB {GAMEOVER}:RETURN'))

    # EXAMINAR
    def _exami():
        S('IF DK=1 THEN A$="Esta demasiado oscuro para ver nada.":GOSUB {PW}:RETURN')
        S('IF N1=0 THEN GOSUB {DESCL}:RETURN')
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 THEN A$="No ves eso aqui.":GOSUB {PW}:RETURN')
        S('OE=OB:GOSUB {EXDESC}:RETURN')
    verb_branch(vb('EXAMI'), _exami)

    # COGER
    def _coger():
        tk = nl()
        asm.iffalse(f'(N1={TODO})', tk)
        S('IF DK=1 THEN A$="Esta demasiado oscuro para ver que hay.":GOSUB {PW}:RETURN')
        S('O=0')
        S(f'FOR I=1 TO {nobj}:IF OL%(I)=P AND OF%(I)=0 THEN O=1:OE=I:GOSUB {{ENGCOGE}}')
        S('NEXT')
        S('IF O=0 THEN A$="No ves nada que puedas coger aqui.":GOSUB {PW}')
        S('RETURN')
        LBL(tk)
        S('IF N1=0 THEN A$="Que quieres coger?":GOSUB {PW}:RETURN')
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 THEN A$="No ves eso aqui.":GOSUB {PW}:RETURN')
        S('OE=OB:GOSUB {ENGCOGE}:RETURN')
    verb_branch(vb('COGER'), _coger)

    # DEJAR
    def _dejar():
        tk = nl()
        asm.iffalse(f'(N1={TODO})', tk)
        S('O=0')
        S(f'FOR I=1 TO {nobj}:IF OL%(I)=240 THEN O=1:OE=I:GOSUB {{ENGDEJA}}')
        S('NEXT')
        S('IF O=0 THEN A$="No llevas nada que dejar.":GOSUB {PW}')
        S('RETURN')
        LBL(tk)
        S('IF N1=0 THEN A$="Que quieres dejar?":GOSUB {PW}:RETURN')
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 OR FNca(OB)=0 THEN A$="No llevas eso.":GOSUB {PW}:RETURN')
        S('OE=OB:GOSUB {ENGDEJA}:RETURN')
    verb_branch(vb('DEJAR'), _dejar)

    # PONER / QUITA
    def _poner():
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 OR OL%(OB)<>240 THEN A$="No llevas eso.":GOSUB {PW}:RETURN')
        S('IF OW%(OB)=0 THEN A$="No puedes ponerte eso.":GOSUB {PW}:RETURN')
        S('OL%(OB)=241:A$="Te pones "+NM$(OB)+".":GOSUB {PW}:RETURN')
    verb_branch(vb('PONER'), _poner)

    def _quita():
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 OR OL%(OB)<>241 THEN A$="No llevas puesto eso.":GOSUB {PW}:RETURN')
        S('OL%(OB)=240:A$="Te quitas "+NM$(OB)+".":GOSUB {PW}:RETURN')
    verb_branch(vb('QUITA'), _quita)

    # ABRIR / CERRA
    def _abrir():
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 THEN A$="No ves eso aqui.":GOSUB {PW}:RETURN')
        S('IF OA%(OB)=0 THEN A$="No puedes abrir eso.":GOSUB {PW}:RETURN')
        S('IF OO%(OB)=1 THEN A$="Ya esta abierto.":GOSUB {PW}:RETURN')
        lk = nl()
        asm.iffalse('(OK%(OB)=1)', lk)
        S('IF OY%(OB)>0 AND FNca(OY%(OB)) THEN OK%(OB)=0:OO%(OB)=1:A$="Lo abres con "+NM$(OY%(OB))+".":GOSUB {PW}:RETURN')
        S('A$="Esta cerrado con llave.":GOSUB {PW}:RETURN')
        LBL(lk)
        S('OO%(OB)=1:A$="Abierto.":GOSUB {PW}:RETURN')
    verb_branch(vb('ABRIR'), _abrir)

    def _cerra():
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 THEN A$="No ves eso aqui.":GOSUB {PW}:RETURN')
        S('IF OA%(OB)=0 OR OO%(OB)=0 THEN A$="Ya esta cerrado.":GOSUB {PW}:RETURN')
        S('OO%(OB)=0:A$="Cerrado.":GOSUB {PW}:RETURN')
    verb_branch(vb('CERRA'), _cerra)

    # METER / SACAR
    def _meter():
        S('NB=N1:GOSUB {PORNOUN}:MA=OB')
        S('NB=N2:GOSUB {PORNOUN}:MB=OB')
        S('IF MA=0 OR MB=0 OR FNca(MA)=0 THEN A$="No puedes hacer eso.":GOSUB {PW}:RETURN')
        S('IF OO%(MB)=0 THEN A$="Esta cerrado.":GOSUB {PW}:RETURN')
        S('OL%(MA)=100+MB:A$="Metes "+NM$(MA)+".":GOSUB {PW}:RETURN')
    verb_branch(vb('METER'), _meter)

    def _sacar():
        S('NB=N1:GOSUB {PORNOUN}')
        S('IF OB=0 OR FNpr(OB)=0 OR OL%(OB)<100 OR OL%(OB)>=240 THEN A$="No esta en ningun contenedor.":GOSUB {PW}:RETURN')
        S('OL%(OB)=240:A$="Sacas "+NM$(OB)+".":GOSUB {PW}:RETURN')
    verb_branch(vb('SACAR'), _sacar)

    S('A$="No puedes hacer eso.":GOSUB {PW}:RETURN')

    # ── INITMAP / INITOBJ + DATA ──
    LBL('INITMAP')
    S('RESTORE {MAPDATA}')
    S(f'FOR I=1 TO {nloc}:FOR J=0 TO 5:READ EX%(I,J):NEXT:NEXT')
    for lid in c.locids:
        if g['locations'][lid].get('dark'):
            S(f'LD%({c.locidx[lid]})=1')
    S('RETURN')

    LBL('INITOBJ')
    for oid in c.objids:
        o = g['objects'][oid]
        i = c.objidx[oid]
        parts = [f'OL%({i})={c.locval(o.get("location"))}']
        n5 = translit_cpc((o.get('noun') or '')[:5]).upper()
        if n5 and n5 in c.nounid:
            parts.append(f'OBN%({i})={c.nounid[n5]}')
        if 'fixed' in (o.get('attributes') or []):
            parts.append(f'OF%({i})=1')
        if o.get('wearable'):
            parts.append(f'OW%({i})=1')
        if o.get('light_source'):
            parts.append(f'OG%({i})=1')
        if o.get('lit'):
            parts.append(f'OT%({i})=1')
        if o.get('openable'):
            parts.append(f'OA%({i})=1')
        if o.get('open'):
            parts.append(f'OO%({i})=1')
        if o.get('locked'):
            parts.append(f'OK%({i})=1')
        k = o.get('key')
        if k and k in c.objidx:
            parts.append(f'OY%({i})={c.objidx[k]}')
        if o.get('initial_message'):
            parts.append(f'HM%({i})=1')
        S(':'.join(parts))
        S(f'NM$({i})=' + sx.q(translit_cpc(o.get('name', oid))))
    S(f'FOR I=1 TO {nobj}:OI%(I)=OL%(I):NEXT')
    for tid in c.timids:
        t = g['timers'][tid]; i = c.timidx[tid]
        S(f'TD%({i})={int(t.get("turns", 10))}')
        if t.get('loop'):
            S(f'TL%({i})=1')
        if t.get('active'):
            S(f'TA%({i})=1:TC%({i})=TD%({i})')
    S('RETURN')

    LBL('MAPDATA')
    for lid in c.locids:
        exs = g['locations'][lid].get('exits') or {}
        fila = ','.join(str(c.locidx.get(exs.get(d) or '', 0)) for d in sx.DIRS)
        S('DATA ' + fila)

    if imgs:
        LBL('DEPDATA')
        _bs = list(DEPACK_Z80)
        for _k in range(0, len(_bs), 16):
            S('DATA ' + ','.join(str(b) for b in _bs[_k:_k + 16]))
    if menu_inks:
        LBL('MENUPAL')
        S('DATA ' + ','.join(str(int(x)) for x in menu_inks))

    if comprime_texto:
        _aplica_compresion_texto(asm)
    return render(asm, start=10, step=2)


def _aplica_compresion_texto(asm):
    """Comprime los literales A$="..." con un diccionario BPE: sustituye
    subcadenas frecuentes por bytes-token (128-255), inyecta en PW la expansion
    en runtime (DG$) y el diccionario en DATA. Reduce mucho el texto del .bas.
    Verificado: la expansion runtime reproduce el texto original byte a byte."""
    import txtpack
    pat = re.compile(r'^A\$="([^"]*)"$')
    idxs, lits = [], []
    for i, op in enumerate(asm.ops):
        if op[0] == 'S':
            m = pat.match(op[1])
            if m:
                idxs.append(i); lits.append(m.group(1))
    if not lits:
        return
    dic = txtpack.build_dict(''.join(lits), 128)
    if not dic:
        return
    N = len(dic)
    exps = txtpack.expansions(dic)
    for i, lit in zip(idxs, lits):
        tk = txtpack.tokenize(lit, dic).decode('latin-1')
        asm.ops[i] = ('S', 'A$="' + tk + '"')
    # PW: 'T$=A$' -> expansion de tokens (run-batched, sin coste si no hay tokens)
    for i, op in enumerate(asm.ops):
        if op[0] == 'S' and op[1] == 'T$=A$':
            asm.ops[i:i + 1] = [
                ('S', 'T$="":PJ=1:PN=LEN(A$)'),
                ('LBL', 'PWXL'),
                ('S', 'IF PJ>PN THEN GOTO {PWXD}'),
                ('S', 'PK=ASC(MID$(A$,PJ,1))'),
                ('S', 'IF PK>=128 THEN T$=T$+DG$(PK-128):PJ=PJ+1:GOTO {PWXL}'),
                ('S', 'PS=PJ'),
                ('LBL', 'PWXR'),
                ('S', 'PJ=PJ+1:IF PJ<=PN THEN IF ASC(MID$(A$,PJ,1))<128 THEN GOTO {PWXR}'),
                ('S', 'T$=T$+MID$(A$,PS,PJ-PS):GOTO {PWXL}'),
                ('LBL', 'PWXD'),
            ]
            break
    # carga del diccionario (DG$) en la cabecera, antes de START
    for i, op in enumerate(asm.ops):
        if op[0] == 'LBL' and op[1] == 'START':
            asm.ops[i:i] = [
                ('S', 'DIM DG$(%d)' % (N - 1)),
                ('S', 'RESTORE {DICTDATA}'),
                ('S', 'FOR I=0 TO %d:READ DG$(I):NEXT' % (N - 1)),
            ]
            break
    asm.ops.append(('LBL', 'DICTDATA'))
    grp = []
    for e in exps:
        grp.append('"' + e + '"')
        if len(','.join(grp)) > 200:
            asm.ops.append(('S', 'DATA ' + ','.join(grp))); grp = []
    if grp:
        asm.ops.append(('S', 'DATA ' + ','.join(grp)))


def export_bas(game, out_path, modo=1, progreso=None):
    """API principal: genera el .bas Locomotive para CPC."""
    c = cpc_prepare(sx.recolecta(game))
    lines = genera_cpc(c, modo=modo)
    with open(out_path, 'w', encoding='ascii', errors='replace', newline='\r\n') as f:
        f.write('\n'.join(lines) + '\n')
    return c.avisos


# ─── Validador estructural (sin emulador) ───────────────────────────────────
def validar(lines):
    """Chequeos baratos del .bas: numeracion, saltos resueltos, balances."""
    probs = []
    nums = []
    for ln in lines:
        head, _, body = ln.partition(' ')
        if not head.isdigit():
            probs.append(f'linea sin numero: {ln!r}'); continue
        nums.append(int(head))
    for a, b in zip(nums, nums[1:]):
        if b <= a:
            probs.append(f'numeracion no creciente: {a} -> {b}'); break
    numset = set(nums)
    for ln in lines:
        for m in re.finditer(r'(?:GOTO|GOSUB|THEN)\s+(\d+)', ln):
            t = int(m.group(1))
            if t == 0 or t not in numset:
                probs.append(f'salto a linea inexistente ({t}) en: {ln[:60]}')
        if '{' in ln or '@' in ln:
            probs.append(f'token sin resolver en: {ln[:60]}')
    txt = '\n'.join(lines)
    fors = len(re.findall(r'\bFOR\b', txt)); nexts = len(re.findall(r'\bNEXT\b', txt))
    whiles = len(re.findall(r'\bWHILE\b', txt)); wends = len(re.findall(r'\bWEND\b', txt))
    if fors != nexts:
        probs.append(f'FOR/NEXT descompensados: {fors}/{nexts}')
    if whiles != wends:
        probs.append(f'WHILE/WEND descompensados: {whiles}/{wends}')
    for ln in lines:
        if len(ln) > 255:
            probs.append(f'linea >255 chars ({len(ln)}): {ln[:50]}...')
    return probs


# ─── Test / generacion ──────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys, yaml
    path = sys.argv[1] if len(sys.argv) > 1 else 'tifon_demo.yaml'
    modo = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    with open(path, 'r', encoding='utf-8') as f:
        game = yaml.safe_load(f)
    out = path.rsplit('.', 1)[0] + f'_cpc{modo}.bas'
    avisos = export_bas(game, out, modo=modo)
    with open(out, encoding='ascii') as f:
        lines = f.read().splitlines()
    probs = validar(lines)
    print(f'[cpc_export] {out}: {len(lines)} lineas BASIC (modo {modo})')
    print(f'  avisos transpilacion: {len(avisos)}')
    for a in avisos[:10]:
        print('   !', a)
    print(f'  problemas estructura: {len(probs)}')
    for p in probs[:20]:
        print('   x', p)
    print('  --- primeras 28 lineas ---')
    print('\n'.join(lines[:28]))
