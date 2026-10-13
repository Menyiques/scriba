# -*- coding: utf-8 -*-
"""Pone al dia NOVEDADES_distribucion.md (las novedades que van en el zip de
Scriba, para el usuario) a partir de NOVEDADES.md (el registro completo).
Lo llama build_exe.bat antes de compilar.

El texto de NOVEDADES_distribucion.md esta escrito a mano y no se toca, salvo:
  - el numero de version del titulo ('# Scriba X.Y — ...'), que sale de
    scriba_info.SCRIBA_VERSION;
  - la seccion entre las marcas AUTO, que se regenera entera: los titulos de
    las entradas de NOVEDADES.md mas nuevas que la seccion que dice la marca
    (desde="..."), o sea, lo que el texto escrito a mano aun no cuenta.

Las entradas internas (pruebas, scripts, modulos del motor) no salen: no le
dicen nada a quien descarga Scriba.

Al reescribir a mano las novedades para una version nueva, hay que mover el
desde="..." de la marca a la cabecera de NOVEDADES.md que ya cubre el texto.

    python novedades_distribucion.py
"""
import io
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
REGISTRO = os.path.join(AQUI, 'NOVEDADES.md')
DISTRIB = os.path.join(AQUI, 'NOVEDADES_distribucion.md')

MARCA = re.compile(r'<!-- AUTO:INICIO desde="([^"]+)" -->.*?<!-- AUTO:FIN -->', re.S)
# lo que delata una entrada interna: pruebas, scripts y piezas del motor
INTERNO = re.compile(r'\.pru\b|\.py\b|\.bat\b|probar_|bateria_|verify_|nativecc|game_engine|'
                     r'z80asm|arn[eé]s|PyInstaller|build_exe', re.I)


def entradas_nuevas(registro, desde):
    """{'Novedades': [titulos], 'Correcciones': [titulos]} de las secciones de
    NOVEDADES.md que van por encima de la que empieza por 'desde'."""
    out = {'Novedades': [], 'Correcciones': []}
    hallada = False
    for sec in re.split(r'(?m)^## ', registro)[1:]:
        cab = sec.split('\n', 1)[0].strip()
        if cab.startswith(desde):
            hallada = True
            break
        # cada entrada es su linea '- ' mas las que siguen sangradas: el titulo
        # en negrita puede partirse en dos lineas
        grupo, entradas = None, []
        for linea in sec.split('\n')[1:]:
            if linea.startswith('### '):
                grupo = linea[4:].strip() if linea[4:].strip() in out else None
            elif linea.startswith('- '):
                entradas.append((grupo, linea))
            elif linea.startswith('  ') and entradas and entradas[-1][0] == grupo:
                entradas[-1] = (grupo, entradas[-1][1] + ' ' + linea.strip())
        for grupo, texto in entradas:
            m = re.match(r'- \*\*(.+?)\*\*', texto, re.S)
            if grupo and m and not INTERNO.search(m.group(1)):
                titulo = ' '.join(m.group(1).split())
                if titulo not in out[grupo]:
                    out[grupo].append(titulo)
    if not hallada:
        raise SystemExit('novedades_distribucion: no encuentro en NOVEDADES.md la seccion '
                         '"%s" (la marca AUTO de NOVEDADES_distribucion.md)' % desde)
    return out


def seccion_auto(desde, nuevas):
    lineas = ['<!-- AUTO:INICIO desde="%s" -->' % desde]
    if nuevas['Novedades'] or nuevas['Correcciones']:
        lineas += ['## Últimos cambios', '',
                   'Lo que ha entrado después de lo que se cuenta arriba (lista sacada del',
                   'registro de cambios al compilar Scriba).', '']
        for grupo in ('Novedades', 'Correcciones'):
            if nuevas[grupo]:
                lineas += ['### ' + grupo, '']
                lineas += ['- ' + t for t in nuevas[grupo]]
                lineas.append('')
    lineas.append('<!-- AUTO:FIN -->')
    return '\n'.join(lineas)


def main():
    sys.path.insert(0, AQUI)
    import scriba_info
    registro = io.open(REGISTRO, encoding='utf-8').read()
    texto = io.open(DISTRIB, encoding='utf-8').read()
    m = MARCA.search(texto)
    if not m:
        raise SystemExit('novedades_distribucion: falta la marca AUTO en NOVEDADES_distribucion.md')
    desde = m.group(1)
    nuevas = entradas_nuevas(registro, desde)
    nuevo = texto[:m.start()] + seccion_auto(desde, nuevas) + texto[m.end():]
    nuevo = re.sub(r'(?m)^# Scriba [0-9.]+ ', '# Scriba %s ' % scriba_info.SCRIBA_VERSION, nuevo, count=1)
    if nuevo != texto:
        tmp = DISTRIB + '.tmp'
        with io.open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(nuevo)
        os.replace(tmp, DISTRIB)
    n = len(nuevas['Novedades']) + len(nuevas['Correcciones'])
    print('NOVEDADES_distribucion.md: Scriba %s, %d cambio(s) posteriores a "%s"%s'
          % (scriba_info.SCRIBA_VERSION, n, desde, '' if nuevo != texto else ' (sin cambios)'))


if __name__ == '__main__':
    main()
