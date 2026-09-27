# SCRIBA

Sistema de autoría de aventuras conversacionales. El juego se escribe en YAML y
de ahí salen cinco destinos: probador de PC, ZX Spectrum 48K/128K, ZX Spectrum
Next, Amstrad CPC, MSX2 y .exe de Windows.

---

## Reglas permanentes

**1. Los comandos, siempre en PowerShell.**
Nada de `^` para partir líneas (eso es CMD). `&` delante de una ruta de
ejecutable entrecomillada. Para volcar a fichero, `2>&1 | Out-File -Encoding utf8`
y nunca `>`, que escribe UTF-16 y deja el log ilegible.

**2. Cada cambio en un YAML sube `metadata.version`.**
El editor sella `revision` y `modified` al guardar, pero una edición hecha
fuera del editor se salta ese sello: hay que poner `version`, `revision` y
`modified` a mano.

---

## Lo que hay que saber antes de tocar nada

**`paws_lang.py` es el único analizador del lenguaje de condacts.** Produce un
AST que consumen todos los destinos. Un predicado nuevo hay que darlo de alta
en `PREDICATES` y **además** implementarlo en cada backend. Si falta en uno, ese
destino lo evalúa mal y no avisa.

Backends:

| Fichero | Destino |
|---|---|
| `interpreter.py` | probador de PC y `.exe` de Windows |
| `player.py` + `scriba_pack.py` | reproductor de ventana y el juego cifrado pegado al `.exe` |
| `nativecc.py` + `game_engine.py` | motor Z80 nativo (bytecode), común a las cuatro máquinas |
| `spectrum48_nativo.py`, `spectrum128_nativo.py` | ZX Spectrum 48K y 128K, a `.tap` |
| `next_nativo.py` | ZX Spectrum Next, a `.nex` |
| `cpc_nativo.py` | Amstrad CPC, a `.dsk` |
| `msx2_nativo.py` | MSX2, a cartucho `.rom` (MegaROM ASCII16) |
| `pcw_nativo.py` | Amstrad PCW 8256/8512, a disco autoarrancable `.dsk` |
| `spectrum_export.py` | ya NO es un backend: queda como biblioteca (`recolecta`, acentos, PSG, dzx0, imágenes) de la que tiran todos los demás |

**`compiler.py::check_predicates()`** detecta predicados no soportados por
destino. Pásalo antes de dar nada por bueno.

---

## Motor nativo Z80

`game_engine.ENGINE_ASM` (~2800 líneas de Z80) es independiente de máquina:
parser, VM de condacts, evaluador de expresiones, tablas, temporizadores y
word-wrap. Toda su dependencia de la máquina está en ~20 símbolos externos que
cada plataforma resuelve a su manera:

- CPC: al firmware (`&BBxx`/`&BCxx`), en el prefijo de `assemble_engine()`,
  salvo `TXTO` y `KMW`, que son rutinas de `CPC_PLAT_ASM`: paginan el texto
  (esperan tecla antes de que una línea sin leer se vaya por arriba, como
  `nxmas` en Next/MSX2) y llaman al firmware como `TXTFW`/`KMWFW`.
  El CPC no precarga las salas contiguas: mientras AMSDOS lee, el teclado no
  se atiende (se pierden letras), así que solo se lee de disco cuando el
  jugador ya espera (al entrar en la sala). Las pruebas de tiempos de disco,
  en MAME (`cpc6128`), que imita la rotación: Caprice32 no, lee al instante.
- Next: a rutinas propias en `next_nativo.PLAT_ASM`, sin tocar `game_engine.py`.

El backend del Next **no usa la ROM para nada** (fuente, teclado e impresión son
propios), así que los slots MMU 0 y 1 quedan libres para mapear RAM sobre
`&0000-&3FFF` si algún día hace falta. Hoy no hace falta: cabe de sobra.

**El mapa de 128K y Next (v2.7).** Dos mitades con una regla: por debajo de
`&C000` vive todo lo que el motor necesita siempre —código, índices, vocabulario,
objetos, respuestas y la pila, en `&BFF0`—; `&C000-&FFFF` es una **ventana de
paginación pura** por la que se leen, cada uno de su banco, el texto (por
mensaje, vía `TXTPAGE`), la música del título, los FX, las imágenes y las
muestras. Nada permanente vive en la ventana, así que se pagina cuando hace
falta y no se devuelve nada a su sitio. La base de datos lleva, por mensaje, el
banco (`msgbnk`) y la dirección en la ventana; `expand_msg` pagina antes de
seguir el puntero. En 48K `TXTPAGE` es un `RET` y el texto sigue plano; el
CPC tiene su propio mapa (abajo).
El mapa plano son 24.432 bytes (`&6000-&BF70`): menos que los 40K del 48K, pero
sin el texto, que es dos tercios de la base de datos. Y los bancos del 128K son
**seis** (1, 3, 4, 6, 7 y 0, en ese orden de carga): el 0 dejó de ser la RAM
alta del juego y es uno más. Como valor de `&7FFD` los ids son 17, 19, 20, 22,
23 y 16 — nunca 0, que en `msgbnk`/`fxbnk`/`psgbnk` significa «plano».

**El mapa del CPC (v3.0).** La ventana de los bancos del 6128 es
`&4000-&7FFF`, en medio de la RAM, así que no puede ser «pura» como la del
128K: lo que corre mientras hay un banco puesto tiene que estar por debajo de
`&4000` (el motor entero, con `TBUF`, acaba hacia `&3200`-`&3400`; el export lo
comprueba) o por encima de `&8000` (la pila del firmware). Base: motor en
`&1200` o más arriba: BASIC necesita 4K libres bajo `HIMEM` para el buffer de
`LOAD` (si no, «Memory full»), y el cargador crece con las 16 tintas de la
portada y, con texto en bancos, con la prueba del 6128; `export_native` sube
el motor lo justo (`cpc_nativo.BASIC_BUFFER`, que `probar_cpc` también
comprueba al interpretar el cargador). Detrás del motor, la DB; luego `hdrbuf` (2K de CAS IN, y la rutina de la música
del título: el firmware la quiere en los 32K centrales, por eso nunca por
debajo de `&4000`) y `MTABLE` (256 bytes), todo antes de `imgbuf` (`&8B00`).
Si el juego no cabe, los primeros mensajes se quedan planos (banco 0 en
`msgbnk`) y el resto va a los bancos `&C4-&C7`; el `TXTPAGE` del CPC copia el
mensaje a `TBUF` y devuelve `&C0` antes de expandir, y `expand_msg` lee el
puntero **antes** de paginar (el índice está en la RAM base, bajo la
ventana). Todo lo propio del CPC se aplica sobre el texto de `ENGINE_ASM` en
`game_engine._engine_cpc()`: el 48K, el 128K y el Next salen byte a byte
igual. Imágenes: `[tinta 2][tinta 3][ZX0 de 64 líneas de 80 bytes seguidas]`,
cargadas pegadas a `IMGTOP` (`&A67C`) y descomprimidas en el sitio al
principio de `imgbuf`; `pinta_pic` las copia a la pantalla línea a línea.
La portada va lo primero del disco, cargada oculta (las 16 tintas del color
del fondo) y con su paleta puesta justo después, para que se vea mientras
carga lo demás (en 48K y 128K, igual: `LOAD ""
SCREEN$` al principio de la cinta; el 48K espera una tecla antes de `start`). La
caché de imágenes son ranuras a medida en lo que deja el texto en los bancos.

`z80asm.py` ensambla (incluye Z80N) y `z80.py` simula (incluye Z80N, puertos y
NextRegs). Eso permite verificar el motor entero sin emulador.

`font42.py` lo genera `genera_font42.py`. **No editarlo a mano.**

---

## Verificación

```powershell
Set-Location 'C:\CLAUDE\PAWS\SCRIBA_NEXT'
python verify_cpc.py                      # motor nativo en CPC
python verify_next.py                     # motor nativo en Next, incluido el .nex
python verify_next.py 'Games\apolo11\apolo11_pt.yaml'
```

`verify_next.py` es el arnés bueno: no pone stubs de texto, así que ejercita el
impresor de verdad contra la pantalla simulada y **decodifica los píxeles de
vuelta a texto**. Además empaqueta el `.nex`, lo relee del disco y juega un par
de órdenes. `verify_cpc.py` sí anula el firmware con stubs, o sea que el camino
de texto del CPC no se prueba ahí: eso lo hace `probar_cpc.py` (abajo).

Los dos arneses suponen que los objetos 0, 5 y 6 tienen ciertas propiedades. En
juegos donde no es así (NIVEL7, "1") fallan dos comprobaciones **en los dos**.
Eso es del arnés, no del motor: antes de perseguir un fallo del Next, comprueba
si el CPC falla igual.

### Baterías del juego, no del motor

Los arneses de arriba prueban el **motor**. Para probar **una aventura** —¿se
puede acabar?, ¿la linterna luce sin pilas?— hay dos corredores que comparten
formato de fichero (`.pru`):

```powershell
python probar_juego.py 'Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml' `
                       'Games\Operacion Tifon Negro\tifon.pru'
python probar_cpc.py   'Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml' `
                       'Games\Operacion Tifon Negro\tifon.pru'      # --modo 2, --464, --png carpeta
python bateria_next.py 'Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml' `
                       'Games\Operacion Tifon Negro\tifon.pru' --jnext 'C:\...\jnext.exe'
```

- `probar_juego.py` juega dentro del simulador Z80 de Python y lee la pantalla
  de los píxeles. No hace falta instalar nada. `probar_48.py`, `probar_128.py`
  y `probar_pc.py` hacen lo mismo en su máquina.
- `probar_cpc.py` juega el `.dsk` tal cual: interpreta el cargador BASIC,
  imita el firmware en Python (texto con ventanas, teclado, CAS IN, tintas) y
  pagina la RAM de 128K por `&7Fxx`. Al describir cada sala compara las 64
  líneas de arriba con la imagen convertida. `--464` quita la RAM extra.
- `bateria_next.py` ejecuta el `.nex` en **jnext** (`--headless`), un emulador
  de Next de verdad: prueba además el cargador NEX, la ROM, la MMU, Layer 2 y el
  Z80N. Se baja de <https://github.com/jorgegv/jnext/releases>; la ruta va en
  `--jnext`, en la variable de entorno `JNEXT` o en el `PATH`.

**La traza llega con los saltos de línea del sistema.** El puerto mágico sale
por la salida de error de jnext, y en Windows el runtime de C convierte cada
`\n` en `\r\n`, así que una marca llega como `\r\n#RESET\r\n`. `descodifica()`
tira los retornos de carro y las expresiones los toleran igualmente. Si se
vuelve a tocar el troceo de la traza, **probarlo con CRLF**, no solo en Linux:
esto costó una tarde.

**La primera vez en una máquina, jnext no tiene la imagen de tarjeta SD** — de
ahí saca las ROMs, igual que una máquina real — y pregunta si se la baja. Se
resuelve con `--bajar-sd` (1 GB), con `--sdcard FICHERO` si ya se tiene una, o
ejecutando jnext a mano una vez. Ojo a **dónde** la deja: jnext lee `$HOME`, y
si no está puesta —lo normal en Windows— usa `.jnext` **de la carpeta desde la
que se le lance**, no la del usuario. `$JNEXT_CONFIG_DIR` manda sobre las dos. `bateria_next.py` lanza el emulador con la
entrada estándar cerrada a propósito, para que esa pregunta se responda sola
que no y salga con su mensaje en vez de quedarse colgada esperando una tecla
que nadie ve que haga falta; y corta si pasan `--paciencia` segundos (120 por
defecto) sin noticias del puerto.

Cómo lo hace `bateria_next.py`: `next_nativo._modo_prueba()` compila un `.nex`
**de pruebas** que lleva el guion dentro y se teclea solo (parchea `KMREAD`),
copia cada carácter impreso a un puerto de E/S (parchea `TXTO`) que jnext vuelca
con `--magic-port`, no gasta guion en las esperas de tecla (parchea `KMW`), pone
la CPU a 28 MHz y se salta las esperas de barrido decorativas. Dos bytes de
control en el guion: `1` vuelca el estado del motor (variables, `OBJLOC`,
`OBJIN`, sala) y `2` reinicia la partida, así que **toda la batería cabe en una
sola ejecución del emulador**. El `.nex` que se distribuye no lleva nada de esto.

Formato `.pru`:

| línea | qué hace |
|---|---|
| `=== nombre` | abre una prueba y **reinicia** la partida |
| `MIRAR` | una orden, tal cual la teclearía el jugador |
| `? texto` / `!? texto` | la respuesta debe / no debe contener ese texto |
| `$ PUNTOS = 110` | una variable (`=`, `<>`, `>`, `<`, `>=`, `<=`) |
| `@ @playa` | dónde está el jugador |
| `% #linterna = INVEN` | dónde está un objeto: `@sala`, `INVEN`, `PUESTO`, `NADA` o `#contenedor` |
| `* 40 I` | repite una orden 40 veces (dejar pasar turnos) |
| `<< fichero : 21` | mete las 21 primeras órdenes de un walkthrough |

Los dos aceptan `-v` (cuenta cada orden según pasa: dónde acaba el jugador, la
puntuación y el principio de la respuesta, y cada comprobación con su `ok` o su
`FALLA`) y `-vv` (además la respuesta entera). `bateria_next.py` lee la salida
del emulador **según sale**, no al terminar, así que con `-v` se ve la partida
avanzar en vivo.

El emulador se corta en cuanto el guion llega al final, así que `--frames` solo
tiene que ser generoso, no exacto: las 690 órdenes de *Tifón Negro* tardan unos
30 s. El texto se compara **sin acentos**, que en pantalla son códigos propios
de la fuente.

El guion va en su propio banco, paginado sobre la ROM en `&2000`: caben 8 KB de
teclas. Si no cabe, la batería lo dice; `* 40 I` en vez de repetir una orden
larga cuarenta veces suele bastar.

Las comprobaciones miran la respuesta a la **última orden**, no la pantalla
entera. Los nombres de variable se escriben sin guiones bajos (`_PILAS_CARGA`
se comprueba como `$ PILASCARGA`), que es como los indexa el motor.

---

## Imágenes por plataforma

| carpeta | para | formato |
|---|---|---|
| `img/Original/<id>.png\|jpg` | máster, y fallback de todo | lo que sea; se autocontrasta |
| `img/Spectrum/<id>.scr` | 48/128K | 6912 o 2304 bytes |
| `img/Spectrum/<id>.jpg\|png\|bmp` | 48/128K | **4:1** (256×64); se convierte **sin** autocontraste |
| `temp/Next/data/<id>.nxi` | Next | Layer 2, lo genera el editor; manda la grafía **con** arroba |

El nombre vale **con arroba y sin ella** (`@playa.jpg` = `playa.jpg`): los
másteres se guardan con la del id y el arte de `img/Spectrum`, históricamente,
sin ella. Lo que está en `img/Spectrum` es la versión definitiva, así que si no
cumple el 4:1 **se corta la exportación** con un error que dice cuánto mide;
los másteres de `img/Original`, en cambio, se escalan sin protestar. Margen del
2% en la proporción. La pantalla de carga (`screen.*`) va a pantalla completa,
4:3, y no se le exige proporción.

---

## MSX2 (`msx2_nativo.py`)

El quinto destino del motor nativo: un cartucho **MegaROM ASCII16** (`.rom`)
que arranca solo en cualquier MSX2 (y en openMSX, WebMSX, blueMSX o un
cartucho flash). Misma base de datos y mismo `ENGINE_ASM`; la capa de
plataforma es `next_nativo.PLAT_ASM` con las rutinas de máquina cambiadas por
`_cambia_rutina()` (de etiqueta a etiqueta: si `PLAT_ASM` cambia de forma,
falla a voces en vez de ensamblar otra cosa).

- **Mapa.** Página 0 = BIOS (interrupción, `CHSNS`/`CHGET`, `KILBUF`). Página
  1 (`&4000-&7FFF`) = el cartucho, que tras arrancar es la **ventana de
  paginación pura**, como `&C000` en 128K/Next (registro ASCII16 en `&6000`;
  los ids de `msgbnk` son números de banco, nunca 0). Páginas 2-3 = RAM: el
  motor y la DB plana en `&8000`, la pila `PILA_MIN` bytes por encima, y todo
  por debajo de `HIMEM`. El motor lleva sus variables entre el código, así que
  **no puede correr desde ROM**: el cargador del banco 0 pone en la página 2 la
  RAM del slot de la página 3, copia a RAM un trocito que copia la imagen
  desde sus bancos, y salta. Si `HIMEM` no llega (disquetera inicializada
  antes), lo dice por la BIOS; en un MSX1, también.
- **Pantalla.** SCREEN 5 programado a mano en el VDP (sin `CHGMOD`, que va a la
  SUB-ROM). 42×24 con la fuente de 6 px: cada glifo son 3 bytes por línea,
  alineados. Scroll y borrado por comandos del VDP (`YMMM`/`HMMV`). Paleta: 0-7
  = colores del Spectrum (fijos, los de `INK`/`PAPER`/`BORDER`); 8-15 = los de
  cada imagen. Las imágenes de sala se cuantizan a esos 8 + negro y blanco (los
  demás fijos, al difuminar, salen como motas). La portada usa los 16.
- **Imágenes.** `img/MSX/<id>` manda (sin autocontraste); si no,
  `img/Original/<id>` (con autocontraste, como las demás). Sala = 256×64 en
  crudo (8 KB, dos por banco). Portada = 256×192 centrada en las 212 líneas.
  `SCR`: 4:1 es tira de 8 filas; lo demás, pantalla entera (16K + 8K).
- **Sonido.** PSG por `&A0/&A1`. `SNDREG` fuerza en el registro 7 el bit 7 a 1
  y el 6 a 0: son la dirección de los puertos de E/S del PSG (joysticks).
- **No hay:** `BRIGHT`/`FLASH` (sin efecto) ni muestras (`SMPPLAY` es `RET`).
- **Firma `ASCII16X` en el byte 16 del fichero.** WebMSX no adivina el mapper
  de una ROM que no conoce: coge ASCII8, que va antes en su lista, la imagen
  RAM se copia mal y la máquina se reinicia al BASIC. Con la firma escoge
  ASCII16-X, que con bancos de 8 bits es ASCII16. openMSX sigue detectándola
  bien, y en hardware real la firma son 8 bytes de datos que nadie ejecuta.

### Batería en openMSX

```powershell
python bateria_msx2.py 'Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml' `
                       'Games\Operacion Tifon Negro\tifon.pru' --openmsx 'C:\...\openmsx.exe'
```

Mismo `.pru` y mismo juez que `bateria_next.py`. El cartucho de pruebas lleva
el guion en sus últimos bancos (leído por la ventana de `&4000`), la traza sale
por el *debugdevice* de openMSX (`&2E/&2F`) y un `OUT (&2D)` al acabar cierra el
emulador (watchpoint en el script Tcl). Máquina por defecto `C-BIOS_MSX2_EU`
(libre, viene con openMSX). Las pruebas `=== [48 next] ...` se saltan si no
llevan `msx`/`msx2`. `--png fichero` vuelca la VRAM al final.

Dos diferencias con `bateria_next.py`, las dos a propósito:
- `(ENTER)` es ENTER sin nada, como en `probar_juego.py` (en la del Next se
  teclea la palabra «enter»).
- Tras un **FIN DEL JUEGO** la partida se queda parada hasta la prueba
  siguiente, y las órdenes que queden se juzgan contra la última respuesta. En
  la del Next, `KMW` no gasta guion, la partida se reinicia sola y la foto de
  la última orden sale ya con `PUNTOS = 0`.

### Trampa: `z80asm` no distingue mayúsculas en las etiquetas

`nxcol` (la columna del cursor) y `NXCOL` (la tabla de colores) son **la misma
etiqueta** y gana la última: en `PLAT_ASM` el cursor escribe su columna encima
del primer byte de la tabla, o sea que `INK 0`/`PAPER 0`/`BORDER 0` salen del
color de la columna en que estuviera el cursor. En MSX2 la tabla se llama
`NXCOLT`; **en Spectrum y Next sigue así**. Lo mismo mordió a `msxpal`/`MSXPAL`.

---

## Amstrad PCW (`pcw_nativo.py`)

El sexto destino: un **disco autoarrancable** de PCW 8256/8512 (`.dsk`, CF2 de
180K, una cara). Se mete en la unidad A y se enciende la máquina: sin CP/M ni
LocoScript. Mismo motor, misma DB; la capa es `PLAT_ASM` con las rutinas de
máquina cambiadas por `_cambia_rutina()` (la de `msx2_nativo`).

- **Arranque.** El PCW carga el sector 1 de la pista 0 en `&F000`, exige que
  sus 512 bytes **sumen `&FF`** (el byte 15 lo cuadra; en el 9512 sería 1) y
  salta a `&F010` con los bloques 0-3 en `&0000-&FFFF`. Nuestro sector se copia
  a `&0200` (bloque 0), lee el resto pista a pista por el uPD765 (sondeo,
  `READ DATA` hasta `EOT`, `INI` a mano con `defb &ED,&A2`: z80asm no la
  conoce) a los bloques 4 en adelante, por la ventana de `&4000`, y copia el
  motor —que va el último en el disco, pegado al último bloque de datos— a
  `&8000`. Si una pista sale mal la repite (5 veces) y si no, pantalla en
  inverso y quieto.
- **Mapa.** Bloque 0 en `&0000` = pantalla S0 (filas 0-21) + roller-RAM en
  `&3E00`. Bloque 1 = S1 (filas 22-31) + buffer de descompresión. `&4000` =
  **ventana de paginación pura** (texto, FX, imágenes y, al pintar una fila de
  S1, la propia S1). Bloques 2-3 = motor y DB en `&8000`; pila en `&FFF0`,
  justo bajo el teclado, que el PCW mapea en `&3FF0` del bloque 3. Ids de
  `TXTPAGE` = `&80 + bloque`.
- **Sin interrupciones.** Todo con DI: en `&0038` y `&0066` hay pantalla.
  `MCWAIT` cuenta ticks del reloj de 300 Hz en el puerto `&F4` (cuenta aunque
  nadie atienda la interrupción); `char_lento` también pasa por ahí (el
  `EI/HALT` de `PLAT_ASM` colgaría la máquina).
- **Pantalla.** 720×256 mono; 90×32 con la fuente de 6 px centrada en celdas
  de 8×8 (una celda son 8 bytes seguidos: el glifo se pinta con 8 `LD (DE),A`).
  El scroll rota `ROWADR` y el roller-RAM, no mueve pantalla. INK/PAPER solo
  deciden el vídeo inverso (papel más claro que la tinta). Imágenes de sala =
  11 filas (720×88, 4:1 en píxeles del PCW, que son el doble de altos), Bayer
  8×8 y ZX0 con `offset_limit=1024` (≈4 KB por tira; Floyd-Steinberg daba 7).
  Caché en `temp/PCW`. `img/PCW/<id>` manda; si no, `img/Original`.
- **Disco lleno.** 180K para todo: si no cabe, se cae primero la portada y
  luego las últimas imágenes, con aviso. *Tifón Negro* entra con sus 23 salas y
  sus 3 SCR, pero sin portada.
- **Teclado.** Mapa de `&FFF2-&FFFA` contra la última lectura; vale la primera
  tecla nueva. La tecla de `;` (la Ñ del teclado español) escribe `n`.
- **Sonido:** no hay AY. `PLAY` y `SAMPLE` guardan su tiempo y no suenan.
- **PCW 8512: dos discos** (`--8512`, «Exportar Amstrad PCW 8512…»). El PCW
  solo arranca de la unidad A, que en el 8512 sigue siendo de 180K; la de 720K
  es la B (CF2DD: 80 pistas, dos caras). Así que el disco A lleva solo el
  sector de arranque, y el B (`<nombre>_B.dsk`) todo lo demás, desde su primer
  sector: cabe la portada y no se recorta nada. El cargador es el mismo con
  constantes: `UNIT` 1, `CARAS` 2, sin sector de arranque delante (`S0INI` 1)
  y con `RECALIBRATE` de la B dos veces (el 765 da 77 pasos como mucho) tras
  medio segundo de motor. Una "unidad" del cargador es una cara de pista; la
  cara 1 se lee sin buscar. Con los 512K del 8512, bloques 4-31.
  `probar_pcw.py --8512` juega esa versión.

### Pruebas

`probar_pcw.py juego.yaml bateria.pru` juega en el simulador Z80 con la
memoria del PCW imitada (bloques por `&F0-&F3`, teclado en `&FFF0`, `&F4`) y
lee la pantalla de su memoria por `ROWADR`. No prueba el sector de arranque:
eso, en JOYCE (`xjoyce -a juego.dsk`), que arranca el disco igual que la
máquina (pero **no comprueba la suma**; la del cargador la asegura un `assert`).

---

## Trampas que ya han mordido

- **`run_condacts` recibe la longitud del cuerpo en DE.** `run_response` la
  deja ahí y cualquier `ld de,...` por el medio la destruye: el cuerpo de la
  respuesta se ejecuta con un final absurdo y la regla parece no casar. Costó
  una tarde y no da ningún error, solo «No entiendo eso».

- **Comodines de sustantivo (manual):** `_` = hueco vacío, o sea que NO puede
  haber palabra; `*` = cualquier palabra o ninguna. En la tabla de respuestas
  se codifican 254 y 255, y 0 es la ranura que la regla no declara.

- **`startswith('REM')` se come `REMOVE`.** Fue un bug real en cinco sitios. Al
  detectar comentarios, `upper == 'REM' or upper.startswith('REM ')`.

- **`Scriba.exe` va congelado con PyInstaller.** Editar el `.py` no cambia el
  `.exe`. Hay que reconstruirlo con `build_exe.bat`, que lee la versión de
  `scriba_info.py`.

- **`scriba_info.py` es la única fuente de la versión.** No repartirla.

- **Las ubicaciones internas llevan `@`**: `@INVEN`, `@ONME`, `@NOWHERE`.
  `spectrum_export.locval()` y `nativecc._destval()` tienen que aceptar las dos
  formas, con y sin `@`. Si no, `CREATE #obj INVEN` compila a "en ninguna parte"
  y el juego se vuelve imposible de terminar sin que salte ningún error.

- **Borrar en la carpeta conectada está desactivado por defecto.** Si aparece un
  `.git/index.lock` huérfano, hay que pedir permiso de borrado antes.

- **Los offsets de la cabecera de la base de datos son el final de cada campo,
  no el principio.** En `build_game_db` el comentario `# 55` de `w16(locdark)`
  quiere decir «después de esto `len(out)` vale 55», o sea que `locdark` empieza
  en 53. El motor leía `locdark`, `objlight` y `objlit` dos bytes más arriba y
  **la oscuridad no funcionó nunca**, ni en Next ni en CPC. Al añadir un campo,
  comprobar los `ld hl,(DBB+n)` de `init` contra la tabla, no contra los
  comentarios.

- **El motor nativo no admite mas de 64 objetos ni 64 variables.** `FLAGS`,
  `OBJLOC`, `OBJLIT`, `OBJOPEN`, `OBJLOCK` y `OBJIN` son `defs 64` fijos y
  pasarse no daba error: escribia sobre la matriz siguiente. Desde 2.47
  `build_game_db` y `nativecc` cortan con un mensaje claro
  (`game_engine.NRAM`). Las **localizaciones** si llegan a 255: no tienen
  matriz en RAM. Subir el tope cuesta ~1,1 KB de RAM por las seis matrices.

- **`ISAT` tiene tres clases de destino, no dos**: sentinel (`INVEN`/`PUESTO`/
  `NADA`), localización (`@sala`) y **contenedor** (`#objeto`). El tercero no
  cabe en el byte de `OBJLOC` — un objeto contenido guarda `CONTAINED` ahí y el
  contenedor en `OBJIN` — y por eso lleva opcode propio (`ISIN`). Si vuelve a
  caer en `ctx.loc()`, el juego se queda sin poder sacar nada de una caja.

- **`z80asm` no distingue mayúsculas en las etiquetas.** `nxcol` (la columna
  del cursor) y `NXCOL` (la tabla de colores) eran la misma: ganaba la última
  y el cursor escribía su columna encima del color 0, así que `INK 0`,
  `PAPER 0` y `BORDER 0` salían de otro color en 48K, 128K y Next. La tabla
  se llama ahora `NXCOLT`, y desde entonces `z80asm` **corta con un error**
  si una etiqueta o un `equ` se define dos veces.

- **Los glifos `_` y `q` de `print42_es.bas` / `print42_pt.bas` están mal**: el
  subrayado apunta al índice de la `á`, y la cola de la `q` invade un píxel del
  carácter siguiente. `genera_font42.py` los corrige al generar la tabla del
  motor nativo, así que hoy no afecta a ningún binario; los `.bas` siguen ahí
  porque son la fuente de esa tabla.

---

## Trampas

- **Tras tocar un módulo del motor, reconstruir `Scriba.exe` ANTES de probar una
  exportación desde el editor.** El `.exe` es una foto congelada: lleva dentro su
  propia copia de `game_engine`, `nativecc`, `next_nativo`, `spectrum*_nativo`…
  Si exportas desde el `.exe` viejo obtienes un binario sin el arreglo, y desde
  la línea de comandos el mismo juego sale bien — dos resultados distintos para
  el mismo código fuente. Nos costó dos vueltas con los FX del Next en la v2.53.
  Para comparar binarios, mirar la fecha de `dist/Scriba.exe` antes que nada.

- **El reproductor de Windows es el propio `Scriba.exe`** (desde la 3.0; antes
  era un `ScribaPlayer.exe` aparte que no estaba en el repositorio y, si
  faltaba, «Exportar para Windows» fallaba). «Exportar para Windows» copia el
  `Scriba.exe` que está corriendo y le pega el juego detrás; al arrancar,
  `editor.py` mira el pie del ejecutable (`_juego_pegado`) y, si lleva juego,
  abre `player.main` en vez del editor. Por eso `build_exe.bat` lleva
  `--hidden-import player`, `PIL.ImageTk` y **`PIL._tkinter_finder`**: sin este
  último, `ImageTk.PhotoImage` falla dentro del .exe («No module named
  PIL._tkinter_finder», lo pide la extensión en C) y el juego sale sin
  imágenes. Desde el código fuente, exportar usa `dist/Scriba.exe`.

- **El bloque que se pega al final del `.exe` no puede contener el patrón de
  8 bytes de PyInstaller** (`MEI\x0c\x0b\x0a\x0b\x0e`). Su arranque busca su
  archivo escaneando el fichero de atrás hacia delante y se queda con la
  primera aparición; si la nuestra apareciera por casualidad, el `.exe` dejaría
  de arrancar **en la máquina del jugador**, no en la nuestra.
  `scriba_pack.empaqueta()` lo comprueba en cada empaquetado y cambia la sal si
  hiciera falta. No quitar esa comprobación.

- **En 128K y Next, nada del arnés puede vivir en `&C000-&FFFF`.** Es la
  ventana de paginación: la primera llamada a `TXTPAGE` se lleva lo que hubiera
  ahí. `verify_next.ejecutar` ponía su pila y su retorno postizo en `&FFEE`, y
  al sacar el texto a bancos `describe` "no terminaba nunca": el `RET` final
  volvía a un banco de texto. Ahora `PILA_ARNES` lo baja a `&BFEE` en
  `verify_128` y en `verificar_nex`. Cualquier arnés nuevo para esas dos
  máquinas tiene que hacer lo mismo.

- **Los símbolos de plataforma que en una máquina son una rutina de verdad y en
  otra un `RET` se rompen en silencio.** `MCWAIT` estuvo así desde que existe el
  motor nativo en Spectrum: en CPC era la espera de barrido del firmware y en la
  capa de Spectrum/Next un `RET` del montón de stubs. `PAUSE` no esperaba y
  **ningún FX sonó nunca** en 48K, 128K ni Next. Mismo patrón que `END`
  compilándose a `DONE`. Al añadir un símbolo de plataforma, comprobar que las
  CUATRO implementaciones hacen algo, y dejar una prueba que lo verifique.

---

## Estado

Rama de trabajo: `fix/predicados-objeto-v2.44`. Scriba 2.8.

**Boriel se ha ido** (v2.54). Las cuatro máquinas salen del motor nativo Z80 y
no hay otro camino: se borraron `next_export.py`, `cpc_export.py`,
`empaqueta_cpc.py`, `empaqueta_nextap.py`, `construye_nextap.py`,
`empaqueta48.py` y `build_nextap.bat`, y con ellos el submenú «Exportaciones
heredadas», el diálogo de configuración del TAP y todo lo que invocaba `zxbc`.
Queda un resto: el transpilador a BASIC sigue DENTRO de `spectrum_export.py`,
sin que lo llame nadie, esperando a que se separe lo que sí se usa. El informe
de `EmbeddedMmuSwitchAssembleError` para upstream sigue en
`reporte_boriel_splitmodules/`, ya solo como documento.

El motor nativo del Next tiene imágenes (Layer 2, un banco por sala), pantalla
de título, música del AY, efectos FX y muestras digitalizadas. Desde la 2.7, en
128K y Next el texto, la música y los FX van en bancos (ver «El mapa de 128K y
Next»). Desde la 3.0, en el CPC el texto que no cabe va a los bancos del
6128 y las imágenes van en ZX0 y en Modo 1 (ver «El mapa del CPC»).

Lo que queda: los glifos `_` y `q` siguen mal en los `.tap` de 128K y Next
(`genera_font42.py` solo corrige la tabla del motor nativo), el DMA y el Copper
están sin usar, y los dos arneses suponen que los objetos 0, 5 y 6 tienen
ciertas propiedades, cosa que en NIVEL7 y "1" no se cumple.
