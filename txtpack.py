#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
txtpack.py — Compresion de texto por diccionario (BPE), en Python puro y sin
dependencias. Nacio para los literales A$="..." del .bas del CPC; hoy la usa el
motor nativo Z80 (game_engine.build_game_db) para meter todo el texto del juego
en la base de datos: sustituye las subcadenas frecuentes por bytes-token
128-255 y genera el diccionario que el motor expande al imprimir.

  build_dict(text, ntok)  -> dict  {token_byte: (a, b)}  (merges BPE)
  tokenize(s, dict)       -> bytes (s con las subcadenas sustituidas por tokens)
  expansions(dict)        -> [str]  expansion completa de cada token, en orden
"""

import collections


def build_dict(text, ntok=128, first=128):
    """Byte-Pair Encoding: funde repetidamente el par de simbolos mas frecuente
    en un token nuevo (bytes 128..). Devuelve {token: (a, b)} en orden de creacion."""
    syms = list(text.encode('latin-1', 'replace'))
    dic = {}
    for t in range(ntok):
        if first + t > 255:
            break
        pairs = collections.Counter(zip(syms, syms[1:]))
        if not pairs:
            break
        (a, b), cnt = pairs.most_common(1)[0]
        if cnt < 3:                      # no compensa por debajo de 3 repeticiones
            break
        tok = first + t
        dic[tok] = (a, b)
        ns = []
        i = 0
        while i < len(syms):
            if i + 1 < len(syms) and syms[i] == a and syms[i + 1] == b:
                ns.append(tok); i += 2
            else:
                ns.append(syms[i]); i += 1
        syms = ns
    return dic


def tokenize(s, dic):
    """Aplica los merges del diccionario (en orden) a s -> bytes con tokens."""
    syms = list(s.encode('latin-1', 'replace'))
    for tok in sorted(dic):
        a, b = dic[tok]
        ns = []
        i = 0
        while i < len(syms):
            if i + 1 < len(syms) and syms[i] == a and syms[i + 1] == b:
                ns.append(tok); i += 2
            else:
                ns.append(syms[i]); i += 1
        syms = ns
    return bytes(syms)


def _expand(tok, dic, cache):
    if tok < 128 or tok >= 224:   # <128 literal; 224-239 = acentos (literales)
        return bytes([tok])
    if tok in cache:
        return cache[tok]
    a, b = dic[tok]
    r = _expand(a, dic, cache) + _expand(b, dic, cache)
    cache[tok] = r
    return r


def expansions(dic):
    """Expansion completa (str) de cada token, en orden de token (128, 129, ...).

    El cache es LOCAL a esta llamada a proposito. Cuando era un dict por defecto
    del propio _expand, sobrevivia entre llamadas y se indexaba solo por numero
    de token: al comprimir un segundo texto en el mismo proceso, sus tokens se
    expandian con el diccionario del PRIMERO y el juego salia con frases de otro.
    """
    cache = {}
    return [_expand(t, dic, cache).decode('latin-1') for t in sorted(dic)]
