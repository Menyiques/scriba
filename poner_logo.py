#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poner_logo.py — Superpone el logo de Scriba en la portada de Scriba_Manual.pdf.

Uso (en la carpeta del proyecto, donde estan el PDF y el logo):
    pip install pypdf reportlab
    python poner_logo.py

Busca el logo (scriba_logo.png/.PNG, scriba-logo.png/.PNG o logo.png) y el
manual (Scriba_Manual.pdf) en el directorio actual y genera
Scriba_Manual_con_logo.pdf con el logo centrado en la parte superior.
"""
import io
import os
import sys

LOGO_CANDIDATOS = ['scriba_logo.png', 'scriba_logo.PNG',
                   'scriba-logo.png', 'scriba-logo.PNG', 'logo.png']
PDF_ENTRADA = 'Scriba_Manual.pdf'
PDF_SALIDA  = 'Scriba_Manual_con_logo.pdf'


def buscar_logo():
    for nombre in LOGO_CANDIDATOS:
        if os.path.isfile(nombre) and os.path.getsize(nombre) > 0:
            return nombre
    return None


def main():
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
    except ImportError:
        print("Faltan dependencias. Instala con:  pip install pypdf reportlab")
        sys.exit(1)

    logo = buscar_logo()
    if not logo:
        print("No encuentro el logo. Guarda 'scriba_logo.png' en esta carpeta.")
        sys.exit(1)
    if not os.path.isfile(PDF_ENTRADA):
        print(f"No encuentro '{PDF_ENTRADA}' en esta carpeta.")
        sys.exit(1)

    W, H = A4
    iw, ih = ImageReader(logo).getSize()
    anchura = 30 * mm                      # ancho del logo en la portada
    altura  = anchura * ih / iw
    x = (W - anchura) / 2
    y = H - 14 * mm - altura               # margen superior de 14 mm

    # Capa con el logo
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawImage(logo, x, y, anchura, altura, mask='auto',
                preserveAspectRatio=True)
    c.save()
    buf.seek(0)
    capa = PdfReader(buf).pages[0]

    # Fusionar la capa sobre la primera pagina del manual
    lector = PdfReader(PDF_ENTRADA)
    escritor = PdfWriter()
    for i, pagina in enumerate(lector.pages):
        if i == 0:
            pagina.merge_page(capa)
        escritor.add_page(pagina)

    with open(PDF_SALIDA, 'wb') as f:
        escritor.write(f)
    print(f"Listo: {PDF_SALIDA}  (logo: {logo})")


if __name__ == '__main__':
    main()
