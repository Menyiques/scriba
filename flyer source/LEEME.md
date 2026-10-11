# Flyer de publicidad de Scriba

El flyer (A4) en cinco idiomas: español, inglés, portugués, catalán y francés.
Sale a `Games\Operacion Tifon Negro\dist\Scriba_<idioma>.pdf`.

## Regenerarlo

```powershell
Set-Location 'C:\CLAUDE\PAWS\SCRIBA_NEXT'
python "flyer source\flyer.py"              # los cinco
python "flyer source\flyer.py" es en        # solo esos
python "flyer source\flyer.py" es --png     # y una imagen para revisarlo
```

Hace falta Chrome (o Edge) instalado y conexión a internet, porque las fuentes
(Source Serif 4 y Source Code Pro) se cargan de Google Fonts.

## Qué hay aquí

- `flyer.py`: los textos de cada idioma (`TEXTOS`), la maqueta (`CSS`, en mm) y
  la plantilla HTML. **Para cambiar un texto, se cambia en `TEXTOS`**, en los cinco
  idiomas. Las líneas que tienen que caber en una (titular, cabecera, pie) se
  encogen solas si no caben, y los bloques con `data-max` (entradilla,
  columnas, lista de novedades, pie del editor) bajan un poco la letra si se
  pasan de su alto.
- `img/`: las imágenes (capturas de Apolo 11, editor, logo de SCRIBA, logo de
  Menyiques, QR). Son recortes, a 300 ppp, del flyer original de septiembre de
  2026 (`img/original_es_2026-09.jpg`), que solo existía como imagen.
- `flyer_<idioma>.html`: lo que genera `flyer.py` (se abre en el navegador).
- `mide.py` y `compara.py`: para calibrar contra el original (miden la primera
  palabra de cada bloque y ponen las dos páginas lado a lado o superpuestas).
  Solo hacen falta si se cambia la maqueta.
