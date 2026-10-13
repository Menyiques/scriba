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
    # EX: la abreviatura de siempre de EXAMINAR (y X en ingles). Es una palabra
    # entera, no un prefijo: el motor compara cuatro/cinco letras rellenando con
    # espacios, asi que EX no se confunde con EXPLO(SIVO) ni con nada que
    # empiece igual.
    'EXAMI': {'es': ['examinar', 'examina', 'ex', 'mirar', 'mira', 'ver', 'observar'],
              'en': ['examine', 'ex', 'x', 'inspect', 'look'],
              'pt': ['examinar', 'examina', 'ex', 'olhar', 'ver', 'observar']},
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
    # SALIDAS: dice por donde se puede ir, sin describir otra vez la sala. En
    # estos juegos SALIR/EXIT es casi siempre eso ("¿por donde salgo?"), asi que
    # van aqui y no en ACABAR: antes eran el verbo de abandonar, y en las
    # maquinas, que comparan cuatro letras, SALIDAS (SALI) acababa la partida.
    'SALID': {'es': ['salidas', 'salida', 'salir', 'exits', 'exit'],
              'en': ['exits', 'exit'],
              'pt': ['saidas', 'saida', 'sair', 'exits', 'exit']},
    # ACABAR: abandonar la partida. Hasta la 3.0 su canonico era SALIR (y un
    # verbo SALIR en el vocabulario de un juego se sigue tomando por este).
    'ACABA': {'es': ['acabar', 'abandonar', 'fin', 'quit'],
              'en': ['quit', 'abandon'],
              'pt': ['acabar', 'abandonar', 'fim', 'quit']},
    'ABRIR': {'es': ['abrir', 'abre'],
              'en': ['open'],
              'pt': ['abrir', 'abre']},
    'VERSI': {'es': ['version'],
              'en': ['version', 'about'],
              'pt': ['versao']},
    'CERRA': {'es': ['cerrar', 'cierra'],
              'en': ['close', 'shut'],
              'pt': ['fechar', 'fecha']},
    # GRABAR / RECUPERAR: una sola partida grabada en memoria (el RAMSAVE y el
    # RAMLOAD de PAWS y DAAD). Ninguno gasta turno, y lo grabado sobrevive a
    # 'jugar otra vez'. Si una palabra choca con otra del juego (en Tifon,
    # GUARDAR con GUARDIA y CARGAR con la CARGA de explosivo), manda la del
    # juego y quedan las demas. GRABA es tambien el verbo de los juegos
    # importados de DAAD, cuyas respuestas, si las tienen, van antes.
    'GRABA': {'es': ['grabar', 'graba', 'guardar', 'salvar', 'save'],
              'en': ['save'],
              'pt': ['gravar', 'grava', 'guardar', 'salvar', 'save']},
    'RECUP': {'es': ['recuperar', 'recupera', 'cargar', 'restaurar', 'load'],
              'en': ['load', 'restore'],
              'pt': ['recuperar', 'recupera', 'carregar', 'restaurar', 'load']},
    # DECIR: hablar a un personaje. Con una orden entre comillas (DECIR A JUAN
    # "COGE LA LLAVE") o con una coma (JUAN, COGE LA LLAVE), la orden queda
    # aparte y PARSE la analiza en la respuesta del autor. El verbo no hace nada
    # por su cuenta: sin respuesta, sale el mensaje de siempre.
    'DECIR': {'es': ['decir', 'di', 'dile'],
              'en': ['say', 'tell'],
              'pt': ['dizer', 'diz', 'diga']},
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

# Catalan y frances, aparte para no alargar cada entrada de arriba. Sin ellos,
# un juego en esos idiomas tiraba del espanol (y en frances el SUR de serie, la
# direccion, se comia la preposicion 'sur'). Elegidas para no chocar entre si:
# en frances ni PORTER (porte, la puerta), ni PLACER (place, la plaza), ni
# TIRER (tambien es disparar); en catalan TREURE va a QUITARSE, que en los
# juegos suele cubrir tambien sacar.
_CA_FR_VERBS = {
    'EXAMI': (['examinar', 'examina', 'ex', 'mirar', 'mira', 'observar', 'veure'],
              ['examiner', 'examine', 'ex', 'x', 'regarder', 'observer', 'inspecter']),
    'COGER': (['agafar', 'agafa', 'prendre', 'recollir', 'pillar'],
              ['prendre', 'prends', 'ramasser', 'saisir', 'attraper']),
    'DEJAR': (['deixar', 'deixa', 'amollar', 'dipositar'],
              ['poser', 'pose', 'lacher', 'deposer', 'laisser']),
    # METTRE, como PONER en espanol, es ponerse: "mettre l'uniforme". Con
    # complemento ("mettre X dans Y") el interprete lo trata como METER.
    'PONER': (['posar', 'vestir', 'equipar'],
              ['mettre', 'enfiler', 'revetir', 'habiller', 'endosser']),
    'QUITA': (['treure', 'despullar', 'llevar'],
              ['enlever', 'oter']),
    'METER': (['ficar', 'fica', 'introduir', 'inserir'],
              ['inserer', 'introduire', 'glisser']),
    'SACAR': (['extreure', 'extraure'],
              ['extraire', 'retirer']),
    'INVEN': (['inventari', 'inv', 'i'],
              ['inventaire', 'inv', 'i']),
    'PUNT':  (['punts', 'puntuacio', 'score'],
              ['score', 'points']),
    'SALID': (['sortides', 'sortida', 'sortir', 'exits', 'exit'],
              ['sorties', 'sortie', 'issues', 'exits', 'exit']),
    'ACABA': (['acabar', 'abandonar', 'fi', 'quit'],
              ['quitter', 'abandonner', 'fin', 'quit']),
    'ABRIR': (['obrir', 'obre'],
              ['ouvrir', 'ouvre']),
    'VERSI': (['versio'],
              ['version']),
    'CERRA': (['tancar', 'tanca'],
              ['fermer', 'ferme']),
    'GRABA': (['desar', 'gravar', 'guardar', 'save'],
              ['sauver', 'sauvegarder', 'enregistrer', 'save']),
    'RECUP': (['recuperar', 'carregar', 'restaurar', 'load'],
              ['restaurer', 'charger', 'recuperer', 'load']),
    'DECIR': (['dir', 'digues'],
              ['dire', 'dis']),
}
_CA_FR_DIRS = {
    'N': (['nord', 'n'], ['nord', 'n']),
    'S': (['sud', 's'], ['sud', 's']),
    'E': (['est', 'e'], ['est', 'e']),
    'O': (['oest', 'o'], ['ouest', 'o', 'w']),
    'U': (['amunt', 'pujar', 'puja', 'u'], ['monter', 'haut', 'u']),
    'D': (['avall', 'baixar', 'baixa', 'd'], ['descendre', 'bas', 'd']),
}
_CA_FR_PREPS = {
    'EN':    (['dins', 'dintre', 'en'], ['dans', 'en', 'dedans']),
    'CON':   (['amb'], ['avec']),
    'A':     (['a', 'al', 'cap'], ['a', 'au', 'vers']),
    'DE':    (['de', 'del', 'des'], ['de', 'du', 'des']),
    'SOBRE': (['sobre', 'damunt'], ['sur', 'dessus']),
    'BAJO':  (['sota'], ['sous', 'dessous']),
    'PARA':  (['per'], ['pour']),
    'ENTRE': (['entre'], ['entre']),
    'SIN':   (['sense'], ['sans']),
}
for _tabla, _extra in ((VERBS, _CA_FR_VERBS), (DIRS, _CA_FR_DIRS), (PREPS, _CA_FR_PREPS)):
    for _canon, (_ca, _fr) in _extra.items():
        _tabla[_canon]['ca'] = _ca
        _tabla[_canon]['fr'] = _fr

# Las palabras de TODO ("COGER TODO", "DEJAR TODO") por idioma. TODO y ALL
# valen siempre, como hasta ahora.
TODO = {'es': ['todo'], 'en': ['all'], 'pt': ['tudo'],
        'ca': ['tot', 'tots'], 'fr': ['tout', 'tous']}


def todo(lang='es'):
    """Las palabras que significan TODO en el idioma del juego (+ todo, all)."""
    out = []
    for w in TODO.get(norm_lang(lang), []) + ['todo', 'all']:
        if w not in out:
            out.append(w)
    return out

# Las claves de los verbos de direccion de los juegos son identificadores en
# espanol (NORTE, ARRIB...) o en ingles: son direccion en cualquier idioma, no
# solo cuando coinciden con una palabra de direccion del idioma del juego.
CLAVES_DIRECCION = {
    'NORTE': 'N', 'NORTH': 'N', 'SUR': 'S', 'SOUTH': 'S',
    'ESTE': 'E', 'EAST': 'E', 'OESTE': 'O', 'WEST': 'O',
    'ARRIBA': 'U', 'ARRIB': 'U', 'UP': 'U', 'SUBIR': 'U',
    'ABAJO': 'D', 'DOWN': 'D', 'BAJAR': 'D',
}

# Etiquetas legibles para el editor.
LABELS = {
    'EXAMI': 'Examinar', 'COGER': 'Coger', 'DEJAR': 'Dejar', 'PONER': 'Ponerse',
    'QUITA': 'Quitarse', 'METER': 'Meter', 'SACAR': 'Sacar', 'INVEN': 'Inventario',
    'PUNT': 'Puntuación', 'SALID': 'Salidas', 'ACABA': 'Acabar', 'ABRIR': 'Abrir',
    'CERRA': 'Cerrar', 'GRABA': 'Grabar partida', 'RECUP': 'Recuperar partida',
    'DECIR': 'Decir (órdenes)',
    'N': 'Norte', 'S': 'Sur', 'E': 'Este', 'O': 'Oeste', 'U': 'Arriba', 'D': 'Abajo',
    'EN': 'en / in', 'CON': 'con / with', 'A': 'a / to', 'DE': 'de / from',
    'SOBRE': 'sobre / on', 'BAJO': 'bajo / under', 'PARA': 'para / for',
    'ENTRE': 'entre / between', 'SIN': 'sin / without',
}


def norm_lang(lang):
    s = str(lang or 'es').strip().lower()
    if s.startswith(('pt', 'por')):
        return 'pt'
    if s.startswith('en'):
        return 'en'
    if s.startswith('ca'):            # ca, cat, catala
        return 'ca'
    if s.startswith('fr'):            # fr, fra, francais
        return 'fr'
    return 'es'


def _corta5(lst):
    """Recorta cada palabra a 5 letras (lo que el motor usa internamente) y quita
    los duplicados que resulten (ignorando mayus/minus). Ej.: 'agarrar'->'agarr',
    'observar'->'obser', y 'examinar'/'examina' -> un solo 'exami'."""
    out, vistos = [], set()
    for w in lst:
        w5 = str(w)[:5]
        k = w5.lower()
        if k in vistos:
            continue
        vistos.add(k)
        out.append(w5)
    return out


# Canonicos que han cambiado de nombre: los overrides de metadata['vocab_base']
# y los verbos del vocabulario de un juego con el nombre viejo valen por el nuevo.
RENOMBRADOS = {'SALIR': 'ACABA'}


def _group(table, lang, overrides):
    lang = norm_lang(lang)
    ov = {RENOMBRADOS.get(k, k): v for k, v in (overrides or {}).items()}
    out = {}
    for canon, bylang in table.items():
        if canon in ov and ov[canon]:
            syns = list(ov[canon])
        else:
            syns = list(bylang.get(lang) or bylang.get('es') or [])
        out[canon] = _corta5(syns)
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
