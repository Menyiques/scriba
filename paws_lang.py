#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paws_lang.py — Parser ÚNICO del mini-lenguaje de condacts de Scriba.

Tokeniza y construye un AST para expresiones aritméticas y condiciones, una
sola vez.  Tres consumidores comparten esta gramática:

  · interpreter.py   evalúa el AST en Python (jugar en PC).
  · spectrum_export.py emite ZX BASIC a partir del AST (exportar al Spectrum).
  · compiler.py      parsea para detectar errores de sintaxis (validar).

Así desaparecen las dos fragilidades antiguas:
  1. El parser de expresiones ya no trocea strings: tokeniza y respeta
     paréntesis, precedencia (* / MOD sobre + -) y el menos unario.
  2. Hay una única definición de la sintaxis; los tres caminos (PC, Spectrum,
     validación) no pueden divergir porque parsean con este mismo módulo.

GRAMÁTICA
  condición := or
  or        := and (' OR '  and)*
  and       := not (' AND ' not)*
  not       := 'NOT' not | 'NOT(' or ')' | primaria
  primaria  := predicado            (si empieza por palabra clave)
             | expr CMP expr        (comparación)
             | predicado            (resto: delegado/desconocido)
  expr      := term (('+'|'-') term)*
  term      := factor (('*'|'/'|'MOD') factor)*
  factor    := ('-'|'+') factor | '(' expr ')' | NÚMERO | VARIABLE

AST
  Condición:  ('or',[c…]) ('and',[c…]) ('not',c) ('true',)
              ('cmp', op, exprIzq, exprDer)
              ('pred', NOMBRE, [arg…])      # args crudos: los interpreta el backend
  Expresión:  ('num', int) ('var', nombre) ('neg', e) ('bin', op, izq, der)
"""

import re

# Predicados (condiciones-palabra-clave). Sus argumentos NO son expresiones:
# son ids de localización/objeto/timer, números o comodines (* _), y los
# resuelve cada backend (check_condition en PC, _pred2zx en el export).
PREDICATES = {
    # entorno
    'AT', 'NOTAT', 'DARK', 'CHANCE', 'TIMER',
    # comando del turno
    'VERB', 'NOUN1', 'NOUN2',
    # estado de objeto
    'CARRIED', 'NOTCARR', 'PRESENT', 'ABSENT', 'WORN', 'NOTWORN',
    'ISAT', 'HASOBJOPEN',
    # estado de variable
    'ZERO', 'NOTZERO', 'EQ', 'GT', 'LT',
}

# Operadores de comparación, los multi-carácter primero (para casar bien
# >=, <=, ==, !=, <> antes que >, <, =).
CMP_OPS = ('>=', '<=', '==', '!=', '<>', '=', '>', '<')


class ParseError(Exception):
    """Error de sintaxis en una expresión o condición PAWS."""


# ─── Tokenizador de expresiones aritméticas ─────────────────────────────────

def _tokenize_expr(s):
    toks = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            toks.append(('num', int(s[i:j])))
            i = j
            continue
        if ch == '#':
            # Propiedad de objeto: #objeto.propiedad (p.ej. #puerta.locked) o
            # id de objeto suelto (p.ej. como destino en #obj.isat = #cofre).
            j = i + 1
            while j < n and (s[j] == '_' or s[j] == '.' or s[j].isalnum()):
                j += 1
            toks.append(('id', s[i:j]))
            i = j
            continue
        if ch == '@':
            # Id de localización: @playa (destino de #objeto.isat = @loc)
            j = i + 1
            while j < n and (s[j] == '_' or s[j].isalnum()):
                j += 1
            toks.append(('id', s[i:j]))
            i = j
            continue
        if ch == '_' or ch.isalpha():
            j = i
            while j < n and (s[j] == '_' or s[j].isalnum()):
                j += 1
            word = s[i:j]
            if word.upper() == 'MOD':
                toks.append(('op', 'MOD'))
            else:
                toks.append(('id', word))
            i = j
            continue
        if ch in '()+-*/':
            toks.append(('op', ch))
            i += 1
            continue
        raise ParseError(f"carácter inesperado {ch!r} en expresión {s!r}")
    return toks


class _ExprParser:
    def __init__(self, toks, src):
        self.toks = toks
        self.src = src
        self.i = 0

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _next(self):
        t = self._peek()
        self.i += 1
        return t

    def parse(self):
        if not self.toks:
            raise ParseError(f"expresión vacía: {self.src!r}")
        node = self._expr()
        if self.i != len(self.toks):
            raise ParseError(f"sobra '{self.src}' tras analizar la expresión")
        return node

    def _expr(self):
        node = self._term()
        while self._peek() in (('op', '+'), ('op', '-')):
            op = self._next()[1]
            node = ('bin', op, node, self._term())
        return node

    def _term(self):
        node = self._factor()
        while self._peek() in (('op', '*'), ('op', '/'), ('op', 'MOD')):
            op = self._next()[1]
            node = ('bin', op, node, self._factor())
        return node

    def _factor(self):
        t = self._peek()
        if t == ('op', '-'):
            self._next()
            return ('neg', self._factor())
        if t == ('op', '+'):
            self._next()
            return self._factor()
        if t == ('op', '('):
            self._next()
            node = self._expr()
            if self._peek() != ('op', ')'):
                raise ParseError(f"falta ')' en {self.src!r}")
            self._next()
            return node
        ty, val = self._next()
        if ty == 'num':
            return ('num', val)
        if ty == 'id':
            return ('var', val)
        raise ParseError(f"token inesperado {val!r} en {self.src!r}")


def parse_expr(s):
    """Analiza una expresión aritmética y devuelve su AST."""
    return _ExprParser(_tokenize_expr(s), s).parse()


# ─── Parser de condiciones ──────────────────────────────────────────────────

def _split_top(s, op):
    """Trocea s por el operador lógico op (' OR ' / ' AND ') a profundidad 0
    de paréntesis. Devuelve la lista de partes (sin recortar internamente)."""
    parts, depth, start = [], 0, 0
    up, ou, L, i = s.upper(), op.upper(), len(op), 0
    while i < len(s):
        ch = s[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0 and up[i:i + L] == ou:
            parts.append(s[start:i].strip())
            start = i + L
            i = start
            continue
        i += 1
    parts.append(s[start:].strip())
    return parts


def _find_cmp(s):
    """Localiza la primera comparación a profundidad 0. Devuelve (op, idx) o
    (None, -1). El operador más largo gana (>= antes que >)."""
    depth, i = 0, 0
    while i < len(s):
        ch = s[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif depth == 0:
            for op in CMP_OPS:
                if s[i:i + len(op)] == op:
                    return op, i
        i += 1
    return None, -1


def _check_parens(s):
    """Verifica que los paréntesis estén equilibrados (sirve para detectar
    errores que no llegan a formar una comparación, p. ej. '(A+1 >')."""
    depth = 0
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                raise ParseError(f"')' sin '(' en {s!r}")
    if depth != 0:
        raise ParseError(f"paréntesis sin cerrar en {s!r}")


def parse_condition(s):
    """Analiza una condición PAWS y devuelve su AST."""
    s = s.strip()
    if not s:
        return ('true',)
    _check_parens(s)

    parts = _split_top(s, ' OR ')
    if len(parts) > 1:
        return ('or', [parse_condition(p) for p in parts])
    parts = _split_top(s, ' AND ')
    if len(parts) > 1:
        return ('and', [parse_condition(p) for p in parts])

    up = s.upper()
    if up.startswith('NOT(') and s.endswith(')'):
        return ('not', parse_condition(s[4:-1]))
    toks = s.split()
    if toks and toks[0].upper() == 'NOT':
        return ('not', parse_condition(' '.join(toks[1:])))

    op, idx = _find_cmp(s)
    first = toks[0].upper() if toks else ''
    if op is not None and not (op == '=' and first in PREDICATES):
        left = s[:idx].strip()
        right = s[idx + len(op):].strip()
        return ('cmp', op, parse_expr(left), parse_expr(right))

    # Predicado (palabra clave reconocida).
    if first in PREDICATES:
        return ('pred', first, toks[1:])

    # Si no es un predicado, se intenta como EXPRESIÓN suelta: la condición es
    # cierta si su valor es distinto de 0 (p.ej. 'IF _arena_cavada' equivale a
    # 'IF _arena_cavada <> 0'; también vale '#obj.open', '_a + _b', etc.).
    try:
        return ('cmp', '!=', parse_expr(s), ('num', 0))
    except ParseError:
        # No parsea como expresión: se deja como predicado desconocido (el
        # backend decide; en PC devuelve True, el export avisa).
        return ('pred', first, toks[1:])


# ─── Backend 1: evaluación en Python (intérprete PC) ────────────────────────

def eval_expr(node, getvar):
    """Evalúa una expresión. getvar(nombre)->int (0 si no existe)."""
    t = node[0]
    if t == 'num':
        return node[1]
    if t == 'var':
        return getvar(node[1])
    if t == 'neg':
        return -eval_expr(node[1], getvar)
    if t == 'bin':
        a = eval_expr(node[2], getvar)
        b = eval_expr(node[3], getvar)
        op = node[1]
        if op == '+':
            return a + b
        if op == '-':
            return a - b
        if op == '*':
            return a * b
        if op == '/':
            return a // b if b else 0           # división entera, 0 si /0
        if op == 'MOD':
            return a % b if b else 0
    raise ParseError(f"nodo de expresión desconocido: {node!r}")


_CMP = {
    '=': lambda a, b: a == b, '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b, '<>': lambda a, b: a != b,
    '>': lambda a, b: a > b, '>=': lambda a, b: a >= b,
    '<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
}


def eval_condition(node, getvar, predicate):
    """Evalúa una condición.
       getvar(nombre)->int ; predicate(NOMBRE, [args])->bool."""
    t = node[0]
    if t == 'true':
        return True
    if t == 'or':
        return any(eval_condition(c, getvar, predicate) for c in node[1])
    if t == 'and':
        return all(eval_condition(c, getvar, predicate) for c in node[1])
    if t == 'not':
        return not eval_condition(node[1], getvar, predicate)
    if t == 'cmp':
        a = eval_expr(node[2], getvar)
        b = eval_expr(node[3], getvar)
        return _CMP[node[1]](a, b)
    if t == 'pred':
        return predicate(node[1], node[2])
    raise ParseError(f"nodo de condición desconocido: {node!r}")


# ─── Backend 2: emisión de ZX BASIC (export al Spectrum) ────────────────────
#
# El backend es cualquier objeto con tres métodos:
#   var(nombre)        -> str   nombre de variable ZX (y la registra)
#   num(entero)        -> str   literal numérico
#   predicate(NOMBRE, [args]) -> str   condición-palabra-clave como BASIC
# y opcionalmente cmp_op(op) si se quisiera reasignar; aquí usamos el mapeo fijo.

_ZX_PREC = {'+': 1, '-': 1, '*': 2, '/': 2, 'MOD': 2}
_ZX_CMP = {'>=': '>=', '<=': '<=', '!=': '<>', '<>': '<>',
           '==': '=', '=': '=', '>': '>', '<': '<'}


def emit_expr(node, backend, parent_prec=0):
    """Emite una expresión como ZX BASIC con paréntesis MÍNIMOS por
    precedencia (reproduce la salida antigua en los casos sin paréntesis)."""
    t = node[0]
    if t == 'num':
        return backend.num(node[1])
    if t == 'var':
        return backend.var(node[1])
    if t == 'neg':
        return '-' + emit_expr(node[1], backend, 3)
    if t == 'bin':
        op = node[1]
        p = _ZX_PREC[op]
        left = emit_expr(node[2], backend, p)
        right = emit_expr(node[3], backend, p + 1)   # izquierda-asociativo
        s = f'{left} {op} {right}'
        if p < parent_prec:
            s = '(' + s + ')'
        return s
    raise ParseError(f"nodo de expresión desconocido: {node!r}")


def emit_condition(node, backend):
    """Emite una condición como ZX BASIC (devuelve una expresión booleana)."""
    t = node[0]
    if t == 'true':
        return '1'
    if t == 'or':
        return '(' + ' OR '.join(emit_condition(c, backend) for c in node[1]) + ')'
    if t == 'and':
        return '(' + ' AND '.join(emit_condition(c, backend) for c in node[1]) + ')'
    if t == 'not':
        return 'NOT ' + emit_condition(node[1], backend)
    if t == 'cmp':
        zop = _ZX_CMP[node[1]]
        return ('(' + emit_expr(node[2], backend) + ' ' + zop + ' '
                + emit_expr(node[3], backend) + ')')
    if t == 'pred':
        return backend.predicate(node[1], node[2])
    raise ParseError(f"nodo de condición desconocido: {node!r}")


# ─── Cabecera de bloque ON (con alternativas OR por hueco) ──────────────────
#
# Sintaxis:  ON <verbo> <nombre1> <nombre2>
# Cada hueco puede ser:
#   · una palabra           p.ej.  USAR
#   · '*'                   cualquiera
#   · '_'                   ninguno (None)
#   · '(A OR B OR C)'       alternativas (también vale 'A|B|C')
# Ejemplo:  ON (USAR OR METER OR PONER) (PILAS OR LINTE) (LINTE OR PILAS)

def parse_on(rest):
    """Divide la parte de un ON (texto tras 'ON') en 3 huecos.
    Cada hueco devuelto es:  '*'  |  '_'  |  lista de alternativas (MAYÚS)."""
    slots = []
    i, n = 0, len(rest)
    while i < n and len(slots) < 3:
        while i < n and rest[i].isspace():
            i += 1
        if i >= n:
            break
        if rest[i] == '(':                     # grupo (A OR B ...)
            depth, j = 1, i + 1
            while j < n and depth:
                if rest[j] == '(':
                    depth += 1
                elif rest[j] == ')':
                    depth -= 1
                j += 1
            inner = rest[i + 1:j - 1]
            alts = [a.strip().upper()
                    for a in re.split(r'(?i)\s+OR\s+|\|', inner) if a.strip()]
            slots.append(alts or ['*'])
            i = j
        else:                                  # token suelto / * / _
            j = i
            while j < n and not rest[j].isspace():
                j += 1
            tok = rest[i:j].upper()
            slots.append(tok if tok in ('*', '_') else [tok])
            i = j
    while len(slots) < 3:
        slots.append('*')
    return slots


def on_slot_matches(slot, value):
    """¿El valor actual (verbo/nombre del turno, o None) casa con el hueco?"""
    if slot == '*':
        return True
    if slot == '_':
        return value is None
    if value is None:
        return False
    return value in slot          # slot es lista de alternativas


# ─── Subrutinas: SUB nombre ... ENDSUB ──────────────────────────────────────
#
# Un bloque con nombre que se llama con CALL nombre desde cualquier script
# (respuestas, before/after_turn, on_start, on_enter, temporizadores y otras
# subrutinas). Se escriben al nivel de arriba de cualquier seccion de condacts,
# fuera de los ON; lo normal es dejarlas al final de las respuestas. RETURN
# sale de la subrutina antes de su final; MATCH y END, como siempre, cortan
# todo lo que se este ejecutando.
#
# Los nombres no distinguen mayusculas. Todas las maquinas admiten como mucho
# CALL_MAX llamadas una dentro de otra: la que se pasa no se hace (el probador
# de PC lo dice), asi que una subrutina que se llame a si misma sin parar no
# cuelga la partida.

CALL_MAX = 8
SUB_MAX = 256
# DOALL dentro de DOALL (tambien a traves de CALL): el que se pasa no se hace
DOALL_MAX = 4

_RE_SUB = re.compile(r'(?i)^SUB\s+([A-Za-z_][A-Za-z0-9_]*)\s*$')


def _codigo(linea):
    """La linea sin espacios ni el numero de linea opcional del principio."""
    code = (linea or '').strip()
    parts = code.split(None, 1)
    if parts and parts[0].isdigit():
        code = parts[1].strip() if len(parts) > 1 else ''
    return code


def es_sub(linea):
    """Nombre (en MAYUS) si la linea abre una subrutina, si no None."""
    m = _RE_SUB.match(_codigo(linea))
    return m.group(1).upper() if m else None


def es_endsub(linea):
    return _codigo(linea).upper() == 'ENDSUB'


def separa_subs(texto):
    """Parte un script en (lineas_sin_subrutinas, {NOMBRE: [lineas]}).
    Acepta str o lista de str. Un SUB sin ENDSUB llega hasta el final."""
    if isinstance(texto, (list, tuple)):
        lineas = [str(x) for x in texto]
    else:
        lineas = str(texto or '').split('\n')
    resto, subs = [], {}
    i = 0
    while i < len(lineas):
        nom = es_sub(lineas[i])
        if nom is None:
            resto.append(lineas[i])
            i += 1
            continue
        i += 1
        cuerpo = []
        while i < len(lineas) and not es_endsub(lineas[i]):
            cuerpo.append(lineas[i])
            i += 1
        i += 1                                  # el ENDSUB
        subs.setdefault(nom, cuerpo)            # repetida: vale la primera
    return resto, subs


def subs_del_juego(game):
    """{NOMBRE: [lineas]} de todas las secciones de condacts, en orden."""
    subs = {}
    for _sec, script in ((game or {}).get('condacts') or {}).items():
        if isinstance(script, (list, tuple)) and script and not isinstance(script[0], str):
            continue                            # formato JSON antiguo
        for nom, cuerpo in separa_subs(script or '')[1].items():
            subs.setdefault(nom, cuerpo)
    return subs


def _codigo_lineas(script):
    """Las lineas de un script (str o lista de str); nada si es JSON antiguo."""
    if isinstance(script, (list, tuple)):
        if script and not isinstance(script[0], str):
            return []
        return [str(x) for x in script]
    return str(script or '').split('\n')


# ─── Órdenes a personajes: JUAN, COGE LA LLAVE / DECIR A JUAN "COGE..." ─────
#
# La frase del jugador se parte por el primer signo de comillas o, si no hay,
# por la primera coma. Lo de delante es la frase del turno; lo de detrás, la
# orden, que el autor analiza con PARSE (VERB, NOUN1 y NOUN2 pasan a ser los
# de la orden). Con coma, solo es una orden si delante hay un nombre y ningún
# verbo, y el verbo del turno es entonces DECIR; si no, la coma es un espacio.
# El motor nativo hace lo mismo en su parser (pa_go); allí solo hay " y ,.

COMILLAS = '"\u201c\u201d\u00ab\u00bb'


def separa_orden(texto):
    """(delante, orden, con_coma). orden es None si la frase no lleva."""
    t = texto or ''
    for i, ch in enumerate(t):
        if ch in COMILLAS:
            resto = t[i + 1:]
            j = next((k for k, c in enumerate(resto) if c in COMILLAS), len(resto))
            return t[:i], resto[:j], False
        if ch == ',':
            return t[:i], t[i + 1:], True
    return t, None, False
