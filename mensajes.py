#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mensajes.py - Catalogo de los MENSAJES DEL SISTEMA del motor (los que estan
"hardcodeados" en spectrum_export: "No entiendo eso.", "Coges X.", etc.) para
poder editarlos/traducirlos desde el editor.

Funciona por SUSTITUCION post-generacion: el motor sigue generando sus literales
por defecto; si el juego tiene un override en metadata['mensajes'][id], se
reemplaza el literal por el personalizado en la fuente ZX BASIC ya generada
(antes de comprimir). Asi no hay que tocar las decenas de llamadas del motor.

Los textos por defecto van SIN acentos (como en el motor); el override puede
llevar acentos (se pasan por translit_disp al aplicarlos).

Cada entrada: (id, plantilla, placeholders, descripcion)
  placeholders: dict {ph: expr_BASIC} para las partes dinamicas (concatenadas).
  El placeholder especial {max} se sustituye por la puntuacion maxima del juego.
"""
import re

_PH = re.compile(r'(\{[a-z]+\})')

CATALOGO = [
    # ── parser / acciones generales ──
    ('no_entiendo',     "No entiendo eso.",                         {}, "Orden no reconocida por el parser"),
    ('no_hacer',        "No puedes hacer eso.",                     {}, "Accion no permitida"),
    ('no_direccion',    "No puedes ir en esa direccion.",           {}, "Salida inexistente"),
    ('pulsa_tecla',     "Pulsa una tecla...",                       {}, "Espera de tecla (mas/paginado)"),
    # ── mirar / oscuridad ──
    ('no_especial',     "No ves nada especial.",                    {}, "Examinar sin descripcion"),
    ('oscuro_total',    "Esta completamente oscuro. No puedes ver nada.", {}, "Localizacion a oscuras (al describir)"),
    ('oscuro_ver',      "Esta demasiado oscuro para ver nada.",     {}, "Mirar a oscuras"),
    ('oscuro_hay',      "Esta demasiado oscuro para ver que hay.",  {}, "Listar objetos a oscuras"),
    ('no_ves_eso',      "No ves eso aqui.",                         {}, "El objeto no esta presente/visible"),
    # ── coger / dejar ──
    ('ya_llevas',       "Ya lo llevas.",                            {}, "Coger algo que ya llevas"),
    ('no_coger',        "No puedes coger eso.",                     {}, "Objeto no cogible"),
    ('peso_max',        "Llevas demasiado peso.",                   {}, "Coger algo que supera el limite de peso"),
    ('coges',           "Coges {o}.",          {'o': 'onomW$(i)'},     "Coger con exito (X = objeto)"),
    ('no_lo_llevas',    "No lo llevas.",                            {}, "Dejar algo que no llevas"),
    ('dejas',           "Dejas {o}.",          {'o': 'onomW$(i)'},     "Dejar con exito"),
    ('nada_coger',      "No ves nada que puedas coger aqui.",       {}, "Coger sin nombre y nada cogible"),
    ('que_coger',       "Que quieres coger?",                       {}, "Coger sin objeto"),
    ('nada_dejar',      "No llevas nada que dejar.",                {}, "Dejar sin nada en el inventario"),
    ('que_dejar',       "Que quieres dejar?",                       {}, "Dejar sin objeto"),
    ('no_llevas_eso',   "No llevas eso.",                           {}, "Accion sobre objeto no llevado"),
    # ── inventario ──
    ('llevas_cab',      "Llevas:",                                  {}, "Cabecera del inventario"),
    ('puesto',          "Llevas puesto: {o}", {'o': 'onomW$(i)'},     "Linea de prenda puesta (inventario)"),
    ('no_llevas_nada',  "No llevas nada.",                          {}, "Inventario vacio"),
    ('aqui_hay',        "Aqui hay {o}.",       {'o': 'onomW$(i)'},     "Objeto presente en la localizacion"),
    # ── vestir ──
    ('no_ponerte',      "No puedes ponerte eso.",                   {}, "Objeto no vestible"),
    ('te_pones',        "Te pones {o}.",       {'o': 'onomW$(o)'},     "Ponerse con exito"),
    ('no_puesto',       "No llevas puesto eso.",                    {}, "Quitarse algo no puesto"),
    ('te_quitas',       "Te quitas {o}.",      {'o': 'onomW$(o)'},     "Quitarse con exito"),
    # ── abrir / cerrar / contenedores ──
    ('no_abrir',        "No puedes abrir eso.",                     {}, "Objeto no abrible"),
    ('ya_abierto',      "Ya esta abierto.",                         {}, "Abrir algo ya abierto"),
    ('abres_con',       "Lo abres con {o}.",   {'o': 'onomW$(okey(o))'}, "Abrir con llave"),
    ('cerrado_llave',   "Esta cerrado con llave.",                  {}, "Abrir algo cerrado con llave"),
    ('abierto',         "Abierto.",                                 {}, "Abrir con exito (sin llave)"),
    ('ya_cerrado',      "Ya esta cerrado.",                         {}, "Cerrar algo ya cerrado"),
    ('cerrado',         "Cerrado.",                                 {}, "Cerrar con exito"),
    ('esta_cerrado',    "Esta cerrado.",                            {}, "Acceder a contenedor cerrado"),
    ('no_contenedor',   "No esta en ningun contenedor.",            {}, "Sacar algo que no esta dentro"),
    ('metes',           "Metes {o}.",          {'o': 'onomW$(o)'},     "Meter en contenedor"),
    ('sacas',           "Sacas {o}.",          {'o': 'onomW$(o)'},     "Sacar de contenedor"),
    # ── puntuacion / fin ──
    ('abandona',        "Abandonas la aventura.",                   {}, "Comando FIN/QUIT"),
    ('puntuacion',      "Puntuacion: {p}/{max}",        {'p': 'STR$(VvPUNTOS)'}, "Mostrar puntuacion"),
    ('fin_juego',       "== FIN DEL JUEGO - Puntuacion: {p}/{max} ==", {'p': 'STR$(VvPUNTOS)'}, "Mensaje de fin de juego"),
    # ── salidas (la linea "Salidas: N S E ...") ──
    ('salidas',         "Salidas:",                                 {}, "Etiqueta de la lista de salidas (ingles: Exits:)"),
    ('dir_n',           " N",                                       {}, "Salida Norte (conserva el espacio inicial)"),
    ('dir_s',           " S",                                       {}, "Salida Sur"),
    ('dir_e',           " E",                                       {}, "Salida Este"),
    ('dir_o',           " O",                                       {}, "Salida Oeste (ingles: ' W' con su espacio)"),
    ('dir_u',           " Subir",                                   {}, "Salida Arriba (ingles: ' Up')"),
    ('dir_d',           " Bajar",                                   {}, "Salida Abajo (ingles: ' Down')"),
    # ── pantalla de carga (solo Next; va en el cargador BASIC, fuente de la ROM) ──
    ('cargando',        "CARGANDO...",                              {}, "Pantalla de carga (solo Next; mayusculas sin tildes)"),
]

_DEF = {mid: txt for mid, txt, _ph, _d in CATALOGO}
_DESC = {mid: d for mid, _t, _ph, d in CATALOGO}
_PHS = {mid: ph for mid, _t, ph, _d in CATALOGO}
_ORDEN = [mid for mid, _t, _ph, _d in CATALOGO]


def defaults():
    return dict(_DEF)


def descripciones():
    return dict(_DESC)


def orden():
    return list(_ORDEN)


def _expr(plantilla, placeholders, max_score, prep):
    """Construye la expresion BASIC para 'plantilla'. prep() se aplica al texto
    (identidad para los defaults ASCII, translit_disp para los personalizados)."""
    txt = plantilla.replace('{max}', str(max_score))
    out = []
    for p in _PH.split(txt):
        m = re.fullmatch(r'\{([a-z]+)\}', p)
        if m and m.group(1) in placeholders:
            out.append(placeholders[m.group(1)])
        elif p:
            out.append('"' + prep(p) + '"')
    return ' + '.join(out) if out else '""'


def aplica(src, overrides, max_score, translit):
    """Reemplaza en 'src' (ZX BASIC ya generado, ANTES de comprimir) los mensajes
    del sistema cuyo override en 'overrides' difiera del defecto. 'translit' es
    translit_disp (acentos -> bytes 144-159). Devuelve (src, n_aplicados)."""
    overrides = overrides or {}
    n = 0
    for mid, defecto, ph, _d in CATALOGO:
        custom = overrides.get(mid)
        if not custom or str(custom) == defecto:
            continue
        viejo_expr = _expr(defecto, ph, max_score, lambda s: s)
        nuevo_expr = _expr(str(custom), ph, max_score, translit)
        # El motor imprime con pw(...) (con salto) o pri(...) (sin salto: "Salidas:"
        # y los nombres de salida). Se prueban ambas formas; solo una existe.
        for pfx in ('pw(', 'pri('):
            viejo = pfx + viejo_expr + ')'
            if viejo in src:
                src = src.replace(viejo, pfx + nuevo_expr + ')')
                n += 1
    return src, n
