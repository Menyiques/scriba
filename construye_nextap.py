#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
construye_nextap.py - Pipeline COMPLETO de "juego -> .tap para Next":
  1) convierte img/Next/<id>.(png|jpg) -> data/<id>.nxi + .nxp (Layer 2),
  2) genera el .bas (modo tap: texto comprimido en bancos + Layer 2) + blob,
  3) compila con zxbc (org 24576),
  4) empaqueta el .tap (texto en bancos bajos $7FFD + imagenes en altos $DFFD).

Ejecutar con un Python que tenga Pillow + PyYAML (el mismo del editor):
  python construye_nextap.py juego.yaml [columnas] [carpeta_NextBuild]
"""
import sys
import os
import glob
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yaml
import png2next
import next_export


def main():
    if len(sys.argv) < 2:
        print('uso: python construye_nextap.py juego.yaml [columnas] [carpeta_NextBuild]')
        return
    yaml_path = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    nb = sys.argv[3] if len(sys.argv) > 3 else r'C:\Users\User\ZX\NextBuild'

    base = os.path.splitext(os.path.basename(yaml_path))[0]
    outdir = os.path.dirname(os.path.abspath(yaml_path)) or '.'
    bas_name = base + '_next.bas'
    bin_name = base + '_next.bin'
    texto_name = base + '_next_texto.bin'
    tap_name = base + '_next.tap'
    bas_path = os.path.join(outdir, bas_name)

    game = yaml.safe_load(open(yaml_path, encoding='utf-8'))
    game.pop('_editor', None)
    locids = set(game.get('locations', {}).keys())

    # ── 1) convertir imagenes de img/Next ──
    print('=== 1) Convirtiendo imagenes (img/Next -> data/*.nxi+.nxp) ===')
    imgdir = os.path.join(outdir, 'img', 'Next')
    datadir = os.path.join(outdir, 'data')
    os.makedirs(datadir, exist_ok=True)
    nconv = 0
    if os.path.isdir(imgdir):
        for f in sorted(glob.glob(os.path.join(imgdir, '*'))):
            b = os.path.splitext(os.path.basename(f))[0]
            if not f.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue
            es_scr = b.lower() in ('screen', 'menu')
            if not (b in locids or es_scr):
                continue
            try:
                _, _, info = png2next.convert(
                    f, os.path.join(datadir, b + '.nxi'),
                    os.path.join(datadir, b + '.nxp'), menu=es_scr)
                print('  ', info[0])
                nconv += 1
            except Exception as e:
                print('   ERROR %s: %s' % (b, e))
    else:
        print('   (no hay carpeta img/Next; sin imagenes)')
    print('   %d imagen(es) convertida(s).' % nconv)

    # ── 2) generar .bas + blob + manifiesto (modo tap) ──
    print('=== 2) Generando .bas (modo tap) ===')
    print(next_export.export_bas(game, bas_path, columnas=cols, modo='tap'))

    # ── org adaptativo: el cargador BASIC (CLEAR org-1) tiene que caber bajo
    #    RAMTOP. Cuantos mas bancos (texto + imagenes) mas largo el cargador, asi
    #    que subimos el org para darle holgura (si no: "M RAMTOP no good"). ──
    texto_path = os.path.join(outdir, texto_name)
    n_text = (os.path.getsize(texto_path) + 16383) // 16384 if os.path.isfile(texto_path) else 0
    n_img = 0
    man = bas_path + '.banks'
    if os.path.isfile(man):
        n_img = sum(1 for ln in open(man, encoding='ascii') if ln.strip())
    n_banks = n_text + n_img
    org = 23755 + (120 + 60 * n_banks) + 900      # PROG + cargador + holgura
    org = max(24576, ((org + 255) // 256) * 256)   # alinea a 256
    org_s = str(org)

    # ── 3) compilar con zxbc ──
    print('=== 3) Compilando (zxbc, org %d ; %d banco[s]) ===' % (org, n_banks))
    py = os.path.join(nb, 'zxbasic', 'python', 'python.exe')
    zxbc = os.path.join(nb, 'zxbasic', 'zxbc.py')
    cmd = [py, zxbc, '--arch', 'zxnext', '-O2', '--org', org_s,
           '--heap-size', '4096', '--array-base=0', '--string-base=0',
           '-o', bin_name, bas_name]
    r = subprocess.run(cmd, cwd=outdir, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    bin_path = os.path.join(outdir, bin_name)
    if not os.path.isfile(bin_path):
        print('*** FALLO: no se genero %s. Revisa los errores de zxbc arriba.'
              % bin_name)
        return
    print('   %s: %d bytes' % (bin_name, os.path.getsize(bin_path)))

    # ── 4) empaquetar el .tap ──
    print('=== 4) Empaquetando .tap ===')
    man = bas_path + '.banks'
    imgargs = []
    if os.path.isfile(man):
        with open(man, encoding='ascii') as fh:
            for line in fh:
                bank, _, fn = line.strip().partition('\t')
                if bank and fn:
                    imgargs += ['--img', '%s:%s' % (bank, os.path.join('data', fn))]
    cmd2 = [py, os.path.join(HERE, 'empaqueta_nextap.py'),
            bin_name, texto_name, tap_name, '--org', org_s] + imgargs
    r2 = subprocess.run(cmd2, cwd=outdir, capture_output=True, text=True)
    if r2.stdout.strip():
        print(r2.stdout.strip())
    if r2.stderr.strip():
        print(r2.stderr.strip())
    tap_path = os.path.join(outdir, tap_name)
    if os.path.isfile(tap_path):
        print('\n*** LISTO: %s (%d bytes) ***' % (tap_name, os.path.getsize(tap_path)))
        print('Copialo a la SD del Next y cargalo (Browser -> %s).' % tap_name)
    else:
        print('*** FALLO al empaquetar el .tap (ver arriba).')


if __name__ == '__main__':
    main()
