# Scriba 3.0 — Novedades desde la 2.3

Scriba 3.0 es un cambio grande: todas las máquinas de 8 bits salen ahora de un
mismo motor escrito en ensamblador Z80, compilado dentro del propio Scriba. Ya
no hace falta instalar nada más (adiós a Boriel ZX BASIC y a `zxbasic/`), y la
misma aventura se exporta a siete máquinas distintas y a Windows.

El manual (`Scriba manual v3.0.pdf`) lo explica todo con detalle; aquí va el
resumen de lo nuevo.

---

## Máquinas

| Máquina | Fichero | Lo que lleva |
|---|---|---|
| ZX Spectrum 48K | `.tap` | texto y portada |
| ZX Spectrum 128K | `.tap` | imágenes, portada con música, efectos y muestras de sonido |
| ZX Spectrum Next | `.nex` | imágenes a todo color, portada con música, efectos y muestras |
| Amstrad CPC 6128 | `.dsk` | Modo 1 (40 columnas, 4 colores) o Modo 2 (80 columnas); portada con música y efectos |
| MSX2 | `.rom` | cartucho que arranca solo; imágenes en color, portada con música y efectos |
| Amstrad PCW 8256 / 8512 | `.dsk` | disco que arranca solo; 90 columnas e imágenes en blanco y negro |
| Windows | `.exe` | un único ejecutable con el juego dentro, a todo color |

- **Amstrad PCW** (nuevo): un disco que arranca solo, sin CP/M ni LocoScript.
  Para el 8512, dos discos: el A arranca y el B (720K) lleva el resto.
- **MSX2** (nuevo): un cartucho MegaROM que arranca solo en cualquier MSX2 o en
  un emulador (openMSX, WebMSX, blueMSX).
- **Amstrad CPC**: elige Modo 1 o Modo 2; el texto que no cabe va a la memoria
  extra del 6128; la portada se ve mientras carga el resto, y los discos cargan
  en la mitad de tiempo que antes.
- **ZX Spectrum 48K y 128K, y Next**: con el motor nativo, más rápido y con
  mucho más sitio para el juego.
- **Windows**: «Exportar para Windows» da un solo `.exe` con el juego dentro,
  comprimido y cifrado (quien abra la carpeta no ve el texto ni las soluciones).
  Ya no hace falta `ScribaPlayer.exe`: el reproductor es el propio `Scriba.exe`.
- **Exportar todos los idiomas y máquinas** (menú Archivo): todo de una vez, en
  segundo plano, con un informe final.

## Imágenes, sonido y presentación

- **Una imagen por sala en cada máquina**, sacada de un máster en color
  (`img/Original`) o de arte preparado a mano para cada una (`img/Spectrum`,
  `img/Next`, `img/AmstradCPC`, `img/MSX`, `img/PCW`). En `img/Spectrum` vale
  `.scr`, `.jpg`, `.png` o `.bmp`. El nombre vale con arroba y sin ella.
- **Portada** (`screen.*`) e **imagen de presentación** (`intro.*`), que sale
  con el mensaje inicial.
- **Condact `SCR`**: pinta una pantalla suelta (una tira o la pantalla entera),
  y `SCR @sala nombre` cambia la imagen de una sala (la base intacta y luego en
  llamas).
- **Sonido**: música del título (`.psg` o `.mid`), efectos (`PLAY "nombre"`) y
  muestras digitalizadas (`SAMPLE`, en 128K y Next). Un clic ligero al teclear,
  en todas las máquinas.
- Una sala a oscuras no enseña su imagen hasta que haya luz.

## Para el jugador

- **GRABAR** y **RECUPERAR** la partida (en todas menos en el 48K). Lo grabado
  sobrevive a «jugar otra vez».
- **SALIDAS** dice por dónde se puede ir.
- **ACABAR** abandona la partida (antes era SALIR, que ahora enseña las
  salidas; los juegos antiguos siguen funcionando).
- **EX** abrevia EXAMINAR; **VERSION** dice qué versión del juego es y con qué
  Scriba se compiló.
- EXAMINAR describe los objetos en todas las máquinas, INVENTARIO pone un objeto
  por línea, COGER TODO y DEJAR TODO avisan si no hay nada, y ENTER sin escribir
  nada es un turno con su propio mensaje.
- Al terminar, el juego ofrece otra partida.
- El analizador de las máquinas distingue las 5 primeras letras de cada palabra
  (antes 4): ya no se confunden palabras como PRISONER y PRISE.

## Para el autor

- **Idiomas**: cada juego se escribe en un idioma, y su autor decide a cuántos
  lo traduce (Archivo → «Exportar literales para traducir», que ahora lleva
  también los objetos y los textos de los temporizadores). Scriba trae de serie
  los verbos, las preposiciones y los mensajes del sistema en español, inglés,
  portugués y, como novedad, catalán y francés; para cualquier otro idioma se
  parte del español y se cambian en «Verbos/preposiciones…» y «Mensajes del
  sistema…».
- **Importar juegos de DAAD** (`.ddb`, versiones 1 y 2 de 8 bits): vocabulario,
  salas, objetos, mensajes y lógica.
- **Metadatos**: el nombre de los ficheros exportados (`DAS-BOOT_128kb_es.tap`…)
  y el color del borde, que ahora vale en todas las máquinas.
- **Validar juego** (F7) avisa de los predicados desconocidos y de lo que cada
  máquina no soporta; al exportar, una ventana dice cuánto ocupa cada parte y
  qué no ha cabido.
- **Editor**: la tabla de objetos se ordena por cualquier columna, Ctrl+F busca
  en la pestaña Referencia y el mensaje inicial de cada objeto se edita en su
  ficha.
- **Lenguaje**: `PRINT "Te quedan {_PILAS} turnos"`, `ISAT` con contenedores,
  `CREATE`/`PUT` con destino y la lectura de `#objeto.propiedad` funcionan en
  todas las máquinas (con `LET`, en las máquinas se pueden cambiar `lit`, `open`
  y `locked`).
- Los identificadores llevan prefijo: `@sala`, `#objeto`, `_variable`. La
  pestaña Problemas tiene «Migrar prefijos» para los juegos antiguos.

## Correcciones destacadas

- En las máquinas, los juegos terminan de verdad (END) y ofrecen otra partida.
- Los objetos que empiezan en el inventario o puestos, y las propiedades de
  objeto (`#linterna.lit`, `#caja.open`…), funcionan en todas las máquinas.
- Los juegos traducidos: las salidas, QUIT, las direcciones, TODO y los
  apóstrofos (`l'uniforme`) funcionan en su idioma.
- Se respeta la sala inicial (`start_location`) en todas las máquinas.
- En el CPC ya no se pierden letras al teclear ni se escapa el texto largo por
  arriba sin dar tiempo a leerlo.

<!-- AUTO:INICIO desde="3.0 — 2026-10-12" -->
<!-- AUTO:FIN -->

## Ejemplos incluidos

- **El Faro** (`Games/el_faro`): una aventura breve de tres salas, solo texto,
  para empezar.
- **DAS BOOT — Demo** (`Games/operacion_tifon_negro_demo`): las primeras salas de
  DAS BOOT, con imágenes, portada y música.

Ábrelos con Scriba (Archivo → Abrir), pruébalos con «▶ Probar juego» y
expórtalos a la máquina que quieras.
