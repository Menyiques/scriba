#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
traduccion.py - Exporta / importa los literales de un juego Scriba a/desde un
CSV de traduccion (columnas: clave ; original ; traduccion) para traducir el
juego a otro idioma.

El emparejado es por CLAVE (la ruta del texto dentro del juego), no por el texto
original, asi que es robusto: dos textos iguales en contextos distintos tienen
claves distintas, y si editas un original despues no se rompe el import.

Textos cubiertos:
  - metadata: title, start_message
  - localizaciones: name, description (+ literales de on_enter / on_look)
  - objetos: name, description, initial_message
  - condacts/scripts: cada literal entrecomillado ("...") -> cnd.<nombre>#<i>
  - vocabulario: verbs / nouns / prepositions (las sinonimos que teclea el jugador)

Los saltos de linea se guardan como "\\n" (literal) en el CSV para que cada texto
ocupe una sola fila y sea comodo de editar en cualquier hoja de calculo.
"""
import csv
import re
import copy

_QUOTED = re.compile(r'"([^"]*)"')
_VOC_GRUPOS = ('verbs', 'nouns', 'prepositions')
_VACIO = ('', 'None', 'none', '[]')


# ── escape de saltos de linea (texto en una sola celda) ─────────────────────
def _esc(s):
    return str(s).replace('\\', '\\\\').replace('\r', '').replace('\n', '\\n')


def _unesc(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            if n == 'n':
                out.append('\n'); i += 2; continue
            if n == '\\':
                out.append('\\'); i += 2; continue
        out.append(c); i += 1
    return ''.join(out)


def _script_lineas(v):
    """(lineas, es_lista) de un script (str multilinea o lista de lineas)."""
    if isinstance(v, list):
        return list(v), True
    if isinstance(v, str):
        return v.split('\n'), False
    return [], False


def _literales(lineas):
    """Literales entrecomillados de una lista de lineas, en orden de aparicion."""
    lits = []
    for ln in lineas:
        if isinstance(ln, str):
            lits.extend(_QUOTED.findall(ln))
    return lits


# ── recoleccion: lista de (clave, original) recorriendo el juego ────────────
def recolecta_literales(game):
    out = []
    meta = game.get('metadata') or {}
    for f in ('title', 'start_message'):
        if str(meta.get(f, '')).strip() not in _VACIO:
            out.append(('meta.%s' % f, str(meta[f])))

    # mensajes del sistema del motor ("No entiendo eso.", "Coges X.", ...):
    # valor actual = override del juego si lo hay, si no el por defecto.
    try:
        import mensajes
        defs = mensajes.defaults()
        ov = meta.get('mensajes') or {}
        for mid in mensajes.orden():
            out.append(('msg.%s' % mid, str(ov.get(mid, defs[mid]))))
    except Exception:
        pass

    for lid, loc in (game.get('locations') or {}).items():
        for f in ('name', 'description'):
            if str(loc.get(f, '')).strip() not in _VACIO:
                out.append(('loc.%s.%s' % (lid, f), str(loc[f])))
        for sf in ('on_enter', 'on_look'):
            lineas, _ = _script_lineas(loc.get(sf))
            for j, lit in enumerate(_literales(lineas)):
                out.append(('loc.%s.%s#%d' % (lid, sf, j), lit))

    for oid, obj in (game.get('objects') or {}).items():
        for f in ('name', 'description', 'initial_message'):
            if str(obj.get(f, '')).strip() not in _VACIO:
                out.append(('obj.%s.%s' % (oid, f), str(obj[f])))

    for cname, cval in (game.get('condacts') or {}).items():
        lineas, _ = _script_lineas(cval)
        for j, lit in enumerate(_literales(lineas)):
            out.append(('cnd.%s#%d' % (cname, j), lit))

    voc = game.get('vocabulary') or {}
    for grupo in _VOC_GRUPOS:
        d = voc.get(grupo) or {}
        if isinstance(d, dict):
            for wid, syns in d.items():
                orig = ', '.join(syns) if isinstance(syns, list) else str(syns)
                out.append(('voc.%s.%s' % (grupo, wid), orig))
    return out


# ── aplicar una traduccion en su clave ──────────────────────────────────────
def _reemplaza_nth(script_val, idx, nuevo):
    """Reemplaza el literal entrecomillado nº idx del script por 'nuevo'."""
    lineas, es_lista = _script_lineas(script_val)
    cnt = [0]

    def repl(m):
        cur = cnt[0]
        cnt[0] += 1
        return '"' + nuevo + '"' if cur == idx else m.group(0)

    for i, ln in enumerate(lineas):
        if isinstance(ln, str):
            lineas[i] = _QUOTED.sub(repl, ln)
        if cnt[0] > idx:
            break
    return lineas if es_lista else '\n'.join(lineas)


def _aplica(game, clave, trad):
    base, _, idx = clave.partition('#')
    partes = base.split('.')
    pref = partes[0]
    try:
        if pref == 'meta':
            game.setdefault('metadata', {})[partes[1]] = trad
        elif pref == 'msg':                      # mensaje del sistema del motor
            game.setdefault('metadata', {}).setdefault('mensajes', {})[partes[1]] = trad
        elif pref == 'loc':
            lid, campo = partes[1], partes[2]
            loc = (game.get('locations') or {}).get(lid)
            if loc is None:
                return False
            if idx != '':                       # literal de script on_enter/on_look
                loc[campo] = _reemplaza_nth(loc.get(campo), int(idx), trad)
            else:
                loc[campo] = trad
        elif pref == 'obj':
            oid, campo = partes[1], partes[2]
            obj = (game.get('objects') or {}).get(oid)
            if obj is None:
                return False
            obj[campo] = trad
        elif pref == 'cnd':
            cname = partes[1]
            cnd = game.get('condacts') or {}
            if cname not in cnd:
                return False
            cnd[cname] = _reemplaza_nth(cnd[cname], int(idx), trad)
        elif pref == 'voc':
            grupo, wid = partes[1], partes[2]
            d = (game.get('vocabulary') or {}).get(grupo)
            if not isinstance(d, dict) or wid not in d:
                return False
            syns = [w.strip() for w in trad.split(',') if w.strip()]
            d[wid] = syns if isinstance(d[wid], list) else trad
        else:
            return False
    except (IndexError, KeyError, ValueError):
        return False
    return True


# ── CSV ─────────────────────────────────────────────────────────────────────
def _lee_csv(csv_path):
    """Devuelve lista de (clave, original_esc, traduccion_esc) sin cabecera.
    Detecta el separador (; o ,) por la cabecera, para abrir CSV de Excel en
    cualquier locale."""
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        prim = f.readline()
        delim = ';' if prim.count(';') >= prim.count(',') else ','
        f.seek(0)
        filas = list(csv.reader(f, delimiter=delim))
    out = []
    for row in filas:
        if not row:
            continue
        if row[0].strip().lower() == 'clave':       # cabecera
            continue
        clave = row[0].strip()
        orig = row[1] if len(row) > 1 else ''
        trad = row[2] if len(row) > 2 else ''
        if clave:
            out.append((clave, orig, trad))
    return out


def exporta_csv(game, csv_path, previo=None):
    """Escribe el CSV de traduccion (clave ; original ; traduccion).
    Si 'previo' es la ruta de un CSV anterior, reaprovecha las traducciones cuyo
    original NO haya cambiado (memoria de traduccion). Devuelve (total, vacias)."""
    pares = recolecta_literales(game)
    prev = {}
    if previo:
        try:
            for clave, orig, trad in _lee_csv(previo):
                prev[clave] = (orig, trad)
        except Exception:
            prev = {}
    total = vacias = 0
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')          # ; = separador de Excel (ES)
        w.writerow(['clave', 'original', 'traduccion'])
        for clave, orig in pares:
            oe = _esc(orig)
            trad = ''
            if clave in prev and prev[clave][0] == oe:
                trad = prev[clave][1]
            w.writerow([clave, oe, trad])
            total += 1
            if not trad:
                vacias += 1
    return total, vacias


def importa_csv(game, csv_path, idioma=None):
    """Aplica las traducciones (por clave) a una COPIA del juego. Devuelve
    (juego_traducido, aplicadas, avisos)."""
    trads = {}
    for clave, orig, trad in _lee_csv(csv_path):
        trads[clave] = (_unesc(orig), _unesc(trad))
    g = copy.deepcopy(game)
    avisos = []
    aplicadas = sin_trad = cambiadas = 0
    for clave, orig_actual in recolecta_literales(game):
        if clave not in trads:
            sin_trad += 1
            continue
        orig_csv, trad = trads[clave]
        if orig_csv and orig_csv != orig_actual:
            cambiadas += 1
            avisos.append('original cambiado desde la exportacion: %s' % clave)
        if trad.strip():
            if _aplica(g, clave, trad):
                aplicadas += 1
            else:
                avisos.append('no se pudo aplicar (clave invalida): %s' % clave)
    if idioma:
        g.setdefault('metadata', {})['language'] = idioma
    if sin_trad:
        avisos.insert(0, '%d literal(es) del juego sin fila en el CSV '
                      '(¿CSV antiguo?)' % sin_trad)
    return g, aplicadas, avisos


def main():
    import sys
    import yaml
    if len(sys.argv) < 4 or sys.argv[1] not in ('export', 'import'):
        print('uso:  python traduccion.py export juego.yaml salida.csv [previo.csv]')
        print('      python traduccion.py import juego.yaml traduccion.csv salida.yaml [idioma]')
        return
    modo = sys.argv[1]
    game = yaml.safe_load(open(sys.argv[2], encoding='utf-8'))
    game.pop('_editor', None)
    if modo == 'export':
        previo = sys.argv[4] if len(sys.argv) > 4 else None
        total, vacias = exporta_csv(game, sys.argv[3], previo=previo)
        print('Exportados %d literales (%d sin traducir) a %s'
              % (total, vacias, sys.argv[3]))
    else:
        out = sys.argv[4] if len(sys.argv) > 4 else 'juego_traducido.yaml'
        idioma = sys.argv[5] if len(sys.argv) > 5 else None
        g, ap, avisos = importa_csv(game, sys.argv[3], idioma=idioma)
        with open(out, 'w', encoding='utf-8') as f:
            yaml.safe_dump(g, f, allow_unicode=True, sort_keys=False)
        print('Aplicadas %d traducciones -> %s' % (ap, out))
        for a in avisos[:20]:
            print('  AVISO:', a)


if __name__ == '__main__':
    main()
