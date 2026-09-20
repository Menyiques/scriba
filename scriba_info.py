# -*- coding: utf-8 -*-
"""
scriba_info.py — Version de Scriba y ficha de identificacion de un compilado.

Fuente UNICA: la leen el editor, el interprete y los tres exportadores, de modo
que el comando VERSION dice lo mismo en PC, Spectrum, Next y CPC. build_exe.bat
saca de aqui SCRIBA_VERSION para nombrar el ejecutable, asi que la linea
'SCRIBA_VERSION = ...' debe empezar en la columna 0 y llevar comillas simples.
"""

import datetime

SCRIBA_VERSION = '2.52'

PLATAFORMA = {
    'pc':      'PC (interprete)',
    '48k':     'ZX Spectrum 48K',
    '128k':    'ZX Spectrum 128K',
    'tap':     'ZX Spectrum Next',
    'next':    'ZX Spectrum Next',
    'cpc':     'Amstrad CPC',
    'windows': 'PC (Windows)',
}


def hoy():
    return datetime.date.today().strftime('%d/%m/%Y')


def ahora():
    return datetime.datetime.now().strftime('%d/%m/%Y %H:%M')


def sello_yaml(meta):
    """'1.0 r7 - 19/09/2026' a partir de version / revision / modified."""
    txt = 'Version ' + str(meta.get('version') or '1.0')
    rev = meta.get('revision')
    if rev:
        txt += ' r' + str(rev)
    mod = meta.get('modified')
    if mod:
        txt += ' - ' + str(mod)
    return txt


def ficha(game, plataforma='pc', compilado=None):
    """Lineas del comando VERSION. 'game' es el YAML cargado; 'compilado' es la
    marca de compilacion (None en el interprete, que juega el YAML en vivo)."""
    m = (game or {}).get('metadata') or {}
    lineas = [
        str(m.get('title') or 'Sin titulo'),
        sello_yaml(m),
        str(m.get('author') or 'Autor desconocido'),
        'Idioma: ' + str(m.get('language') or 'es'),
        '',
        'Motor: Scriba ' + SCRIBA_VERSION,
    ]
    if compilado:
        lineas.append('Compilado: ' + compilado)
    lineas.append('Sistema: ' + PLATAFORMA.get(str(plataforma).lower(),
                                               str(plataforma)))
    return lineas
