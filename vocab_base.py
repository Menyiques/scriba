# -*- coding: utf-8 -*-
"""
vocab_base.py — Vocabulario de SERIE (verbos, direcciones y preposiciones) que el
motor inyecta en todos los juegos, en una ÚNICA fuente de verdad y por idioma
(es/en/pt). Antes estaba duplicado y fijo en castellano en interpreter.py y en
spectrum_export.recolecta; ahora ambos (y el CPC, que reutiliza recolecta) leen
de aquí.

El AUTOR puede editar los sinónimos por juego: metadata['vocab_base'] con la forma
    {'verbs': {CANON: [sinónimos...]}, 'dirs': {N/S/...: [...]}, 'preps': {CANON: [...]}}
Si un canónico aparece en el override, SUSTITUYE sus sinónimos para ese idioma; si
no, se usan los del idioma. Los CANÓNICOS son identificadores internos estables
(no cambian con el idioma); el motor despacha sobre ellos.
"""

# CANÓNICO -> {idioma: [sinónimos]}. El primer sinónimo suele ser la forma "bonita".
VERBS = {
    'EXAMI': {'es': ['examinar', 'examina', 'mirar', 'mira', 'ver', 'observar'],
              'en': ['examine', 'x', 'inspect', 'look'],
              'pt': ['examinar', 'examina', 'olhar', 'ver', 'observar']},
    'COGER': {'es': ['coger', 'coge', 'tomar', 'toma', 'agarrar', 'recoger'],
              'en': ['take', 'get', 'grab', 'pick'],
              'pt': ['apanhar', 'apanha', 'pegar', 'agarrar', 'tomar']},
    'DEJAR': {'es': ['dejar', 'deja', 'soltar', 'suelta', 'depositar'],
              'en': ['drop', 'leave'],
              'pt': ['largar', 'larga', 'deixar', 'soltar', 'pousar']},
    'PONER': {'es': ['ponerse', 'poner', 'vestir', 'equipar'],
              'en': ['wear', 'don'],
              'pt': ['vestir', 'veste', 'equipar']},
    'QUITA': {'es': ['quitarse', 'quitar', 'desvestir'],
              'en': ['remove', 'doff'],
              'pt': ['tirar', 'tira', 'despir', 'remover']},
    'METER': {'es': ['meter', 'mete', 'introducir', 'insertar'],
              'en': ['put', 'insert', 'place'],
              'pt': ['meter', 'mete', 'introduzir', 'inserir']},
    'SACAR': {'es': ['sacar', 'saca', 'extraer'],
              'en': ['extract', 'withdraw'],
              'pt': ['retirar', 'retira', 'extrair']},
    'INVEN': {'es': ['inventario', 'inv', 'i', 'llevo'],
              'en': ['inventory', 'inv', 'i'],
              'pt': ['inventario', 'inv', 'i']},
    'PUNT':  {'es': ['puntos', 'puntuacion', 'score'],
              'en': ['score', 'points'],
              'pt': ['pontos', 'pontuacao', 'score']},
    'SALIR': {'es': ['salir', 'abandonar', 'quit'],
              'en': ['quit', 'exit', 'abandon'],
              'pt': ['sair', 'abandonar', 'quit']},
    'ABRIR': {'es': ['abrir', 'abre'],
              'en': ['open'],
              'pt': ['abrir', 'abre']},
    'CERRA': {'es': ['cerrar', 'cierra'],
              'en': ['close', 'shut'],
              'pt': ['fechar', 'fecha']},
}

# Direcciones: CANÓNICO corto (N/S/E/O/U/D) -> {idioma: [palabras]}.
DIRS = {
    'N': {'es': ['norte', 'n'], 'en': ['north', 'n'], 'pt': ['norte', 'n']},
    'S': {'es': ['sur', 's'], 'en': ['south', 's'], 'pt': ['sul', 's']},
    'E': {'es': ['este', 'e'], 'en': ['east', 'e'], 'pt': ['este', 'leste', 'e']},
    'O': {'es': ['oeste', 'o'], 'en': ['west', 'w', 'o'], 'pt': ['oeste', 'o']},
    'U': {'es': ['arriba', 'subir', 'sube', 'u'], 'en': ['up', 'u'],
          'pt': ['cima', 'subir', 'sobe', 'u']},
    'D': {'es': ['abajo', 'bajar', 'baja', 'd'], 'en': ['down', 'd'],
          'pt': ['baixo', 'descer', 'desce', 'd']},
}

# Preposiciones: CANÓNICO -> {idioma: [palabras]}.
PREPS = {
    'EN':    {'es': ['en', 'dentro', 'interior'], 'en': ['in', 'into', 'inside'],
              'pt': ['em', 'dentro', 'no', 'na']},
    'CON':   {'es': ['con'], 'en': ['with', 'using'], 'pt': ['com']},
    'A':     {'es': ['a', 'al', 'hacia'], 'en': ['to', 'at'], 'pt': ['ao', 'aa']},
    'DE':    {'es': ['de', 'del', 'desde'], 'en': ['from', 'of'],
              'pt': ['de', 'do', 'da', 'desde']},
    'SOBRE': {'es': ['sobre', 'encima'], 'en': ['on', 'onto', 'over'],
              'pt': ['sobre', 'encima']},
    'BAJO':  {'es': ['bajo', 'debajo'], 'en': ['under', 'beneath', 'below'],
              'pt': ['sob', 'debaixo']},
    'PARA':  {'es': ['para'], 'en': ['for'], 'pt': ['para']},
    'ENTRE': {'es': ['entre'], 'en': ['between', 'among'], 'pt': ['entre']},
    'SIN':   {'es': ['sin'], 'en': ['without'], 'pt': ['sem']},
}

# Etiquetas legibles para el editor.
LABELS = {
    'EXAMI': 'Examinar', 'COGER': 'Coger', 'DEJAR': 'Dejar', 'PONER': 'Ponerse',
    'QUITA': 'Quitarse', 'METER': 'Meter', 'SACAR': 'Sacar', 'INVEN': 'Inventario',
    'PUNT': 'Puntuación', 'SALIR': 'Salir', 'ABRIR': 'Abrir', 'CERRA': 'Cerrar',
    'N': 'Norte', 'S': 'Sur', 'E': 'Este', 'O': 'Oeste', 'U': 'Arriba', 'D': 'Abajo',
    'EN': 'en / in', 'CON': 'con / with', 'A': 'a / to', 'DE': 'de / from',
    'SOBRE': 'sobre / on', 'BAJO': 'bajo / under', 'PARA': 'para / for',
    'ENTRE': 'entre / between', 'SIN': 'sin / without',
}


def norm_lang(lang):
    s = str(lang or 'es').strip().lower()
    return 'pt' if s.startswith(('pt', 'por')) else 'en' if s.startswith('en') else 'es'


def _group(table, lang, overrides):
    lang = norm_lang(lang)
    ov = overrides or {}
    out = {}
    for canon, bylang in table.items():
        if canon in ov and ov[canon]:
            syns = list(ov[canon])
        else:
            syns = list(bylang.get(lang) or bylang.get('es') or [])
        out[canon] = syns
    return out


def verbs(lang='es', overrides=None):
    """{CANON: [sinónimos]} de los verbos de serie para el idioma + overrides."""
    return _group(VERBS, lang, (overrides or {}).get('verbs'))


def dirs(lang='es', overrides=None):
    return _group(DIRS, lang, (overrides or {}).get('dirs'))


def preps(lang='es', overrides=None):
    return _group(PREPS, lang, (overrides or {}).get('preps'))


def all_for(game):
    """Atajo: lee metadata['language'] y metadata['vocab_base'] del juego y
    devuelve (verbs, dirs, preps) ya resueltos."""
    meta = (game or {}).get('metadata') or {}
    lang = meta.get('language')
    ov = meta.get('vocab_base') or {}
    return verbs(lang, ov), dirs(lang, ov), preps(lang, ov)
