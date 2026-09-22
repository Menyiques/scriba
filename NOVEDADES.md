# Novedades de Scriba

Registro de cambios por versión. En cada *release*, añade una nueva sección **arriba**
(justo debajo de «Sin publicar»), con la fecha y los cambios agrupados en **Novedades**
y **Correcciones**. Al publicar, mueve lo acumulado de «Sin publicar» a la nueva versión.

> Formato basado en *Keep a Changelog*. Versionado: `MAYOR.MENOR` (`2.3`).

---

## [Sin publicar]

### Novedades
- (añade aquí lo que vaya entrando para la próxima versión)

### Correcciones
- (…)

---

## 2.6 — 2026-09-22 — El juego, dentro del ejecutable

### Novedades
- **«Exportar para Windows» da un solo `.exe`, y el juego ya no viaja en texto
  plano.** Hasta ahora dejaba el `game.yaml` al lado del ejecutable: cualquiera
  que abriera la carpeta con el Bloc de notas tenia delante las soluciones de
  los acertijos y el final. Ahora el juego entero —texto e imagenes— va en un
  bloque serializado, comprimido y cifrado (`scriba_pack.py`) que se PEGA AL
  FINAL de una copia del reproductor. El jugador recibe un fichero y en su
  carpeta no hay nada que leer.
  - El reproductor se lee a si mismo al arrancar y lo descifra **en memoria**:
    no se escribe en disco en ningun momento.
  - Cada exportacion lleva su propia sal, asi que dos copias del mismo juego no
    se parecen entre si.
  - Se sigue leyendo el formato antiguo (game.yaml + player_cfg.json +
    img/Original al lado del .exe) para que los paquetes ya repartidos no dejen
    de funcionar.
  - `build_game_exe.py` (un `.exe` por juego, compilado con PyInstaller) tenia
    el mismo agujero por otra puerta: un `.exe` *onefile* se descomprime al
    arrancar en una carpeta temporal, donde el `.yaml` volvia a estar en claro.
    Ahora lo que mete —y lo que aparece en ese temporal— es el bloque cifrado.
  - Hasta donde protege: el reproductor tiene que leer el juego para jugarlo,
    asi que la clave va dentro del binario. Es un candado contra la
    curiosidad, no una caja fuerte.
- La pestaña «Muestras» del editor pasa a llamarse **«Sonido WAV»**, que es lo
  que se importa ahí y lo que la gente busca.
- **`verify_pack.py`**, 12 comprobaciones: el juego vuelve identico, las
  imagenes byte a byte, ninguna de las 638 frases largas de Tifon Negro se lee
  en el bloque, y el reproductor lo encuentra solo dentro del `.exe`.

### Notas
- **Por que se puede pegar algo al final de un `.exe` de PyInstaller**: su
  arranque no espera la cabecera en el ultimo byte, la busca escaneando de
  atras hacia delante en trozos de 8 KB (`pyi_utils_find_magic_pattern`),
  precisamente para sobrevivir a las firmas digitales. Como se queda con la
  primera aparicion que encuentra yendo hacia atras, lo unico que hay que
  garantizar es que el bloque no contenga por casualidad ese patron de 8 bytes:
  `empaqueta()` lo comprueba y, si pasara, cambia la sal y vuelve a cifrar.

---

## 2.54 — 2026-09-22 — Se acabo la partida, y vuelta a empezar

### Novedades
- **Fuera Boriel.** Las cuatro maquinas salen del motor nativo Z80 desde la
  v2.53, y desde esta ya no hay otro camino: se han quitado del menu del editor
  las «Exportaciones heredadas (ZX BASIC / Boriel)» y el dialogo de
  configuracion del TAP, y con ellos todo lo que invocaba `zxbc` —unas 830
  lineas del editor, incluidos los exportadores a BASIC de CPC y Next que ya no
  estaban ni en el menu—. Se han borrado siete ficheros: `next_export.py`,
  `cpc_export.py`, `empaqueta_cpc.py`, `empaqueta_nextap.py`,
  `construye_nextap.py`, `empaqueta48.py` y `build_nextap.bat`.
  - `build_exe.bat` ya no arrastra esos cuatro modulos ni empaqueta los
    `print42/64_*.bas` dentro del `.exe` (siguen en el repositorio: son la
    fuente de la que `genera_font42.py` saca la tabla del motor nativo).
  - Queda un resto a proposito: el transpilador a ZX BASIC sigue DENTRO de
    `spectrum_export.py`, ya sin que lo llame nadie. Ese fichero es ademas la
    biblioteca de la que tiran los cinco exportadores nativos y los
    verificadores (`recolecta`, los acentos, el reproductor PSG, dzx0, las
    imagenes), asi que separarlo es un paso aparte, con su propia tanda de
    pruebas.
- **Al terminar, otra partida.** Hasta ahora el motor salia de `mainloop` con un
  `RET` y devolvia el control al BASIC de la maquina: en el Next, el copyright
  de Sinclair Research; en cinta, a recargar. Ahora se ofrece otra partida
  («Pulsa una tecla para jugar otra vez.», mensaje de sistema `SOTRA`, traducible
  como los demas) y al pulsar se vuelve a la **pantalla de presentacion con su
  musica** y de ahi al juego reinicializado, que es lo que hacia cualquier
  aventura de los ochenta.
  - **128K y Next**: se repinta la portada de su banco y el reproductor PSG
    rebobina, asi que la musica suena entera otra vez.
  - **CPC**: la portada la dejaba puesta el cargador BASIC y el juego escribe
    encima, asi que ahora se vuelve al Modo 0 y se **recarga `TITLE.SCR` del
    disco** —lo mismo que ya hace con las imagenes de sala—. Sin disco en la
    unidad no hay portada, pero la partida nueva arranca igual.
  - **48K**: no hay portada que repintar (la suya es la pantalla de carga de la
    cinta), pero la partida nueva empieza con la pantalla limpia.
- **El presupuesto de memoria, en la ventana de cada exportacion.** Las cuentas
  de `presupuesto.py` ya no salen solo cuando algo NO cabe: cada exportacion
  (48K, 128K, Next y CPC) termina enseñando en que se va la memoria y cuanto
  queda libre, en una tabla monoespaciada —motor, musica del titulo, base de
  datos, imagenes en bancos— con su tope delante. Antes eso solo existia como
  excepcion, o sea que el autor se enteraba de lo justo que iba el juego el dia
  que se pasaba.
  - La ventana de resultado es nueva (`_ventana_resultado`): sustituye al
    *messagebox*, donde las columnas no cuadraban por ser fuente proporcional,
    y de paso **enseña los avisos del exportador**, que hasta ahora se quedaban
    en el diccionario de info sin que los viera nadie: los efectos FX que no
    caben en el CPC y quedan mudos, la musica recortada del 128K, las salas que
    se leeran del disco cada vez.
  - El Next tambien pasa por `presupuesto.comprueba` para el mapa plano, que era
    el unico backend que se quejaba a mano.
- **`verify_reinicio.py`.** Arnes nuevo, 20 comprobaciones, que juega el final de
  la partida en los tres binarios (48K, 128K y Next) y comprueba que se sale de
  `mainloop`, que se pasa por la portada y arranca la musica, que `quitf` vuelve
  a cero y el jugador a la sala inicial, y que no queda en pantalla el texto de
  la partida anterior.

### Correcciones
- **La pantalla se limpia antes de reiniciar.** Sin esto, la portada del 128/Next
  se levantaba sobre el texto de la partida anterior y en el 48K la partida nueva
  empezaba debajo del «FIN DEL JUEGO» de la anterior.
- **El arnes `.pru` sabia que la partida habia acabado porque el motor hacia
  `RET`** (una direccion postiza en la pila). Como ya no lo hace, se vigila la
  etiqueta `gameover` del motor, justo detras del `call mainloop`: se llega a
  ella con la pantalla del final todavia puesta, que es lo que la prueba quiere
  leer.
- **`probar_pc.py` tardaba 30 segundos por cada final de partida.** Esperaba el
  turno con un `get(timeout=30)` a secas y, cuando la partida terminaba, no habia
  nadie que soltara la ficha. Ahora mira ademas si el hilo del juego sigue vivo:
  la bateria de Tifon Negro ha pasado de mas de dos minutos a 3 segundos.

---

## 2.53 — 2026-09-21 — El motor nativo en 48K, y los juegos vuelven a terminar

### Novedades
- **ZX Spectrum 48K con el motor nativo Z80, sin Boriel.** `spectrum48_nativo.py`
  ensambla motor, capa de plataforma y base de datos en el mapa plano
  `&6000-&FF00` y empaqueta un `.tap`. La capa de plataforma del Next ya era un
  48K —imprime sobre la pantalla ULA, lee el teclado por la matriz del puerto
  `&FE` y no toca la ROM—, asi que no se ha reescrito: se le sustituyen las
  siete instrucciones Z80N que usaba (`PIXELAD`, `PIXELDN`, `ADD HL,nn`,
  `ADD HL,A`) por Z80 normal. Operacion Tifon Negro ocupa 31.530 de los 40.704
  bytes del mapa; entran los nueve juegos del repositorio.
- **`probar_pc.py`: la bateria `.pru` sobre el interprete de Python.** Los otros
  corredores van todos contra el motor nativo; este va contra `interpreter.py`,
  que es el que mueve «Probar juego» del editor y el `.exe` de PC, y que no
  tenia ni una prueba automatica. Mismo `.pru`, mismas ordenes y mismo juez que
  `probar_48.py`, de modo que una divergencia entre los dos motores sale sola.
- **ZX Spectrum 128K con el motor nativo Z80.** `spectrum128_nativo.py`: el
  48K nativo mas los bancos. El juego entero sigue en el mapa plano
  &6000-&FF00 y los cinco bancos conmutables quedan ENTEROS para las
  imagenes, porque el texto viaja comprimido dentro de la base de datos y ya
  no compite con ellas. En el export de BASIC el texto se lleva 26.176 de los
  81.920 bytes de banco y deja 10.863 libres; aqui quedan **37.039**, que a
  1.951 bytes de media por pantalla sube el techo de unas 28 imagenes a unas
  42. Las imagenes son los mismos flujos ZX0 que ya produce
  `spectrum_export.imagenes_128k`, con su misma verificacion, y el
  descompresor es el `dzx0_standard` de Saukas/Urusergi que ya usaba el
  export. Tifon Negro: 31.887 bytes de RAM principal, 44.881 de imagenes en
  tres bancos, `.tap` de 77.224 frente a los 108.044 del build de BASIC.
- **`verify_48.py` y `verify_128.py`**: arneses de validacion del 48K y del
  128K, hermanos de `verify_next.py` y `verify_cpc.py`. El del 128K compara la
  imagen descomprimida byte a byte con la que saca el simulador de dzx0, y
  comprueba que el motor devuelve el banco 0 a su sitio (si no, se llevaria
  por delante la mitad alta de su propia base de datos).
- **`probar_128.py`**: la bateria `.pru` sobre el binario de 128K, con la
  paginacion del puerto &7FFD emulada.
- **`bateria_next --maquina 48|128`**: la bateria sobre EMULADOR llega a las
  otras dos maquinas. Hasta ahora 48K y 128K solo se probaban en el simulador
  de Python; ahora el mismo binario que va en el `.tap` se envuelve en un
  `.nex` y lo arranca jnext, con su Z80 ciclo a ciclo, su ULA y -- en 128K --
  su paginacion por &7FFD y el descompresor de imagenes. El `.tap` sigue
  siendo lo que se distribuye: lo que NO cubre esta bateria es el cargador
  BASIC de la cinta.
- **El guion de la bateria ya no cabe en una pagina.** Se lee por una ventana
  de 8 KB sobre la ROM y el motor salta a la pagina siguiente al agotarla, asi
  que una bateria larga deja de ser un problema del que escribe las pruebas.
  Hacia falta: `tifon.pru` pasa de 8 KB al partir en cuatro la prueba del
  patio, y con el limite de una pagina el `.nex` de pruebas ya no compilaba.
- **Presupuesto de memoria en las cuatro maquinas** (`presupuesto.py`). Cada
  backend tenia sus topes y avisaba a su manera, o no avisaba: el 48K y el CPC
  no miraban nada y sacaban un binario corrupto, y el Next no contaba sus
  bancos. Ahora el aviso es el mismo en todas y dice las DOS cosas que hacen
  falta: que ocupa cada partida y por cuanto te pasas.
- **En CPC los FX entran hasta donde haya hueco.** Es la maquina mas apretada
  -- su RAM util acaba en &8B00, donde empieza el buffer de imagen -- y con los
  doce efectos nuevos Tifon Negro se pasaba por 517 bytes: el `.dsk` habria
  salido con la base de datos solapando el buffer. Ahora entran los que quepan
  EN EL ORDEN de la pestana FX, y los que se quedan fuera no rompen la
  numeracion (su ranura va a cero y `PLAY` sale mudo). De paso, las imagenes
  que no entran en las 12 ranuras de cache del CPC dejan de caerse en silencio.
- **Sonido digitalizado por el AY, en 128K y Next.** El AY no tiene DAC,
  pero su registro de volumen es de 4 bits: apagando el mezclador y
  escribiendo la amplitud a ritmo constante hace de DAC, que es lo que llevan
  haciendo los digidrums desde los ochenta. `wav2ay.py` convierte un WAV
  pasandolo por la curva LOGARITMICA real del chip -- volcar los cuatro bits
  altos del PCM amontona todo arriba y la parte baja no se oye -- y empaqueta
  dos muestras por byte. `sample_ay.py` es el reproductor, 64 bytes, con los
  retardos calculados en T-estados: los dos tramos del bucle cuestan 32 y 68 T,
  asi que hay que igualarlos o la onda sale con cojera audible. El condact es
  `SAMPLE "nombre"`, existe en las cuatro maquinas y no hace nada donde no hay
  AY (48K y CPC). En 128K las muestras van detras de las imagenes, en los
  mismos bancos; en Next, en bancos propios, con una ventana de 16K sobre la
  ROM -- se puede tapar entera porque el reproductor corre con las
  interrupciones quitadas y lo unico que hace falta de ella es el gestor de
  &0038. Pestana «Muestras» en el editor, con importacion de WAV y una
  audicion que suena con los MISMOS 16 niveles que la maquina.
- **Musica del AY en el 128K nativo.** El reproductor de PSG del Next se
  reaprovecha tal cual: el 128K lleva el mismo chip y los mismos puertos
  (&FFFD para elegir registro, &BFFD para el dato). Suena sobre la portada
  hasta que se pulsa tecla, y el hueco que se le da es el que queda libre en
  el mapa plano, medido despues de todo lo demas, con tope en PSG_MAX.
- **Las cuatro maquinas pasan a exportarse por el motor nativo.** El menu
  Archivo ofrece 48K, 128K, Next y CPC sin apellidos: las cuatro se compilan
  aqui, en Python puro. El camino por ZX BASIC se conserva en un submenu,
  «Exportaciones heredadas (ZX BASIC / Boriel)», hasta que los cuatro targets
  nativos esten rodados en maquina con todos los juegos. Nada se ha borrado.
- **`BRIGHT`, `FLASH` e `INVERSE` en el motor nativo.** Eran el unico agujero
  real frente al export de BASIC, y no era teorico: Apolo 11 usa `BRIGHT` en
  sus tres idiomas y lo perdia en las cuatro maquinas nativas. Los tres pasan
  por un simbolo de plataforma nuevo, `SCRATTR`. En Spectrum, 128K y Next,
  `BRIGHT` y `FLASH` son bits del atributo; `INVERSE` no lo es -- en el
  Spectrum invierte los PIXELES del caracter, no sus colores -- asi que se
  guarda un flag y `nxplot` complementa los seis pixeles del glifo, dejando a
  cero los dos que son del vecino. En el CPC, que no tiene nada de esto,
  `SCRATTR` es un RET.

### Correcciones
- **`capabilities.py` mentia sobre el Next.** `CAPS['next'] = CAPS['spectrum']`
  decia que Next iba en BASIC y lo soportaba todo, cuando lleva el motor
  nativo desde la v2.0: daba via libre a un `BEEP` que en el `.nex` no suena.
  Ahora el contrato del motor nativo se define UNA vez (`CAPS_NATIVO`) y lo
  comparten CPC, Next, 48K y 128K, con la excepcion del 48K, que no lleva AY
  y por tanto no tiene `PLAY`.
- **`PAUSE` no esperaba y los efectos de sonido eran mudos en Spectrum, 128K
  y Next.** `MCWAIT` -- en el CPC la espera de barrido del firmware -- estaba en
  el grupo de stubs de la capa de plataforma que solo hacen `RET`. El motor lo
  llama en dos sitios: `c_pause`, entre frame y frame de `PAUSE`, y `c_play`,
  entre frame y frame de un efecto. Con un `RET`, `PAUSE n` era instantaneo y
  un FX entero se reproducia en microsegundos, o sea que no sonaba. En el CPC
  siempre funcionaron, y por eso no habia saltado: era el unico backend donde
  `MCWAIT` era la rutina de verdad. Ahora es `EI`+`HALT`, que con IM1 da el
  barrido exacto. `verify_48` comprueba que `PAUSE 3` pasa tres veces por ahi.
- **`END` se comia un `ENDIF` o un `ENDON` sueltos.** El reconocedor era
  `startswith('END')`, asi que una de esas dos palabras fuera de su bloque se
  habria compilado como fin de partida. Ahora es `END` exacto.

### Correcciones
- **Ningun juego terminaba en maquina real.** `nativecc` compilaba el condact
  `END` a `DONE`, que en semantica PAW solo significa «esta entrada ha acertado,
  siguiente turno». El texto del final se imprimia y el juego devolvia el
  prompt: en Tifon Negro te capturaban las SS y seguias jugando, y ningun final
  —ganador o perdedor— era alcanzable en CPC, Next ni 48K. `END` pasa a
  compilarse a un condact propio, `ENDGAME`, que imprime el cierre con la
  puntuacion (mensaje de sistema `SFIN`, del catalogo de `mensajes.py`) y
  levanta `quitf`. `mainloop` ademas mira `quitf` donde lo mira el interprete de
  PC —tras `before_turn` y tras el despacho—, y no solo al final del turno.
  Lo encontro `probar_pc.py` en su primera pasada.
- **Las salidas se escribian distinto en PC que en las maquinas.** El motor
  nativo saca los nombres del catalogo compartido (`dir_n`..`dir_d`, de
  `mensajes.py`) y el interprete de Python los llevaba cableados en
  `DIR_NAMES_L`: el Spectrum decia «Salidas: N S» y el PC «Salidas: Norte,
  Sur». Peor aun, una traduccion hecha en el editor cambiaba las maquinas y no
  el PC. `interpreter._dir_name()` pasa a leer el mismo catalogo, con la tabla
  por idioma de ultimo recurso, y la linea se separa por espacios como en el
  motor nativo. Lo encontro `probar_pc.py`.
- **El arnes del Z80 no sabia que una partida puede acabarse.** Que el motor
  dejara de pedir ordenes se vivia como un cuelgue, a 40 millones de pasos de
  simulador por orden. Ahora se deja una direccion de retorno reconocible en la
  pila y `teclea` corta ahi.

---

## 2.52 — 2026-09-21 — Las imagenes del Next, por el nombre bueno

### Correcciones
- **El Next cogia imagenes viejas cuando el id de la localizacion no llevaba
  arroba.** Los `.nxi`/`.nxp` se buscaban con el id tal cual, y en `temp/Next/
  data` conviven las dos epocas: las que escribe el editor hoy, con arroba, y
  un resto de antes de la convencion de prefijos, sin ella. Un juego con ids
  sin arroba -la version portuguesa de Tifon Negro- se llevaba las de junio,
  con su borde blanco. Ahora se prueban las dos grafias y manda la de la
  arroba, que es la que el editor mantiene al dia.

---

## 2.51 — 2026-09-21 — Los comodines del manual, y COGER TODO como debe

### Novedades
- **Una linea en blanco antes de las salidas** en la descripcion de sala.

### Correcciones
- **`COGER TODO` ya coge todo lo que se pueda coger**, este suelto en la sala o
  dentro de un contenedor abierto y presente. `COGER <objeto>` tambien. El
  motor nativo solo miraba lo que hubiera suelto; el export de 128K si sacaba
  de los contenedores, asi que los dos backends daban resultados distintos ante
  la misma orden.
- **Los comodines de sustantivo funcionan como dice el manual.** `_` es hueco
  vacio (no puede haber palabra) y `*` es cualquier palabra o ninguna. En el
  motor nativo `_` se compilaba a 0 y 0 significaba "cualquier cosa", justo lo
  contrario; y **el segundo sustantivo de la cabecera `ON` se tiraba entero**,
  de modo que `ON COGER PASE _` casaba con "coger pase embarque". Ahora la
  tabla de respuestas lleva las dos ranuras y las compara con esas reglas.
  `*` en un predicado `NOUN1`/`NOUN2` tambien pasa a ser cierto sin palabra.

---

## Sin publicar — correccion de Tifon Negro (YAML 1.5)

### Correcciones
- **Tifon Negro se volvia inacabable si vaciabas la caja fuerte con `COGER
  TODO`.** El flag del pase y el de los codigos solo se ponian en las
  respuestas de `COGER PASE` y `COGER CODIGOS` exactas; con cualquier otra
  forma de cogerlos se los llevaba el `GET` generico y los flags se quedaban a
  cero: con el pase en la mano el Bootsmann no te dejaba subir al submarino, y
  con los codigos encima el amanecer te mataba igual. Ahora `after_turn` mira
  **lo que llevas**, no como lo cogiste, y ahi se ponen el flag y el punto.
  Mas visible en 128K, porque alli `COGER TODO` **si** vacia los contenedores
  abiertos (el motor nativo no), asi que era el camino natural.
- Tres pruebas nuevas en `tifon.pru`: los objetos de la caja cuentan se cojan
  como se cojan, con el pase se sube a la torre y sin el no.

---

## 2.5 — 2026-09-20 — Arte de Spectrum en JPG, PNG o BMP

### Novedades
- **`img/Spectrum` ya no obliga a trabajar en `.scr`.** Ademas del `.scr` de
  siempre, la carpeta admite `.jpg`, `.png` y `.bmp` **en 4:1** —la tira de
  256x64 del tercio superior—, que se incrustan como si fueran un `.scr`: se
  pasan a tinta y papel con el mismo dithering Bayer de 2 colores por bloque de
  8x8. Igual para la pantalla de carga (`screen.*`, esa a pantalla completa).
  - Lo que se deja en `img/Spectrum` es arte **ya preparado para la maquina**,
    asi que se convierte **sin tocar niveles**. El autocontraste se queda donde
    tiene sentido: en el fallback de los masteres fotograficos de `img/Original`.
  - Y si no viene en 4:1 **se rechaza con un error que dice cuanto mide y cuanto
    deberia medir**, en vez de achatarlo en silencio. Hay un 2% de margen, que
    recortar a mano nunca sale exacto.
  - El orden de preferencia queda: `Spectrum/<id>.scr`, luego
    `Spectrum/<id>.jpg|png|bmp`, y por ultimo el master de `Original/<id>.*`.
- **El nombre vale con arroba y sin ella**: `@playa.jpg` y `playa.jpg` valen los
  dos. Los masteres de `img/Original` se guardan con la arroba del id y el arte
  de `img/Spectrum`, historicamente, sin ella; buscar solo una de las dos formas
  dejaba fuera media carpeta sin decir nada.
- El editor previsualiza estas imagenes **exactamente como van a salir**, con el
  mismo tratamiento que el export, y si una no cumple el 4:1 lo dice en el hueco
  de la imagen en vez de dibujar algo que luego no sera.

---

## 2.48 — 2026-09-20 — El guion de la bateria, fuera del mapa plano

### Novedades
- **El guion del modo prueba viaja en su propio banco**, paginado sobre la ROM
  en `&2000-&3FFF` (la ranura de abajo no vale: `nxsubepal` la usa un instante
  para leer las paletas). Antes iba en el mapa plano y una bateria de 690
  ordenes —6,5 KB de teclas— no cabia junto al juego; ahora el tope son 8 KB de
  guion y el binario no se entera. Es, literalmente, el truco de mapear RAM
  sobre la ROM que el Next permite.
- **`* 40 ORDEN` en el `.pru`**: repite una orden N veces. Dejar pasar turnos es
  lo que mas se repite en una bateria y el guion viaja dentro del `.nex`, asi
  que conviene que ocupe poco (`* 103 I` son 206 bytes; 103 `PUNTUACION`, 1133).
- **Las comprobaciones de texto ya no miran los acentos.** En pantalla los
  acentos son codigos propios de la fuente del juego y obligar a escribirlos en
  el `.pru` solo servia para que una prueba fallara por una tilde.
- Cuando el guion no cabe, la bateria lo dice con todas las letras en vez de
  soltar el error del exportador, que habla de direcciones y no de pruebas.

### Correcciones
- **La puntuacion salia pegada al eco de la orden** en el motor nativo
  (`puntuacionPuntuacion: 25`): el condact `SCORE` imprimia sin saltar de linea
  antes, al reves que `MESSAGE` y que el export de 128K.

---

## 2.47 — 2026-09-20 — Baterias de prueba sobre el .nex real

### Novedades
- **`bateria_next.py`: bateria de pruebas del juego sobre un emulador de Next
  de verdad.** Ejecuta el `.nex` en [jnext](https://github.com/jorgegv/jnext)
  en modo *headless* y comprueba lo que el juego contesta. No lee pixeles ni
  cuenta barridos: el `.nex` se compila en **modo prueba**, que le mete dentro
  el guion de la partida — se teclea solo — y hace que copie cada caracter que
  imprime a un puerto de E/S; jnext vuelca ese puerto a su salida de error
  (`--magic-port`), asi que una partida entera sale como texto plano. El guion
  lleva ademas dos bytes de control: uno pide una foto del estado del motor
  (variables, donde esta cada objeto, dentro de que contenedor, sala actual) y
  otro vuelve a empezar la partida, con lo que toda la bateria cabe en una sola
  ejecucion del emulador. **El `.nex` que se distribuye no lleva nada de esto**:
  son parches que solo se aplican cuando `compila()` recibe un guion.
  En modo prueba la CPU se pone a 28 MHz y se quitan las esperas de barrido
  decorativas: 288 ordenes de *Tifon Negro* tardan minuto y medio.
- **`probar_juego.py`: la misma bateria sin emulador**, dentro del simulador Z80
  de Python, leyendo la pantalla de los pixeles. Mas comoda para el dia a dia
  (no hay que instalar nada); la de jnext prueba ademas el cargador NEX, la ROM,
  la MMU, Layer 2 y el Z80N.
- **Formato `.pru`** compartido por las dos: `===` abre una prueba (y reinicia
  la partida), una linea suelta es una orden, `?` / `!?` comprueban el texto de
  la respuesta, `$` una variable, `@` la localizacion, `%` donde esta un objeto
  (incluido «dentro de tal contenedor») y `<<` mete las ordenes de un
  walkthrough, entero o solo las N primeras.
- **`Games/Operacion Tifon Negro/tifon.pru`**: 14 pruebas del juego, entre ellas
  que se puede acabar con 110/110 siguiendo la ruta optima.
- **Modo verboso en las dos** (`-v`, `-vv`): cuenta cada orden segun pasa
  — donde acaba el jugador, la puntuacion y el principio de la respuesta — y
  cada comprobacion con su `ok` o su `FALLA` en su sitio, en vez de una lista
  al final. `bateria_next.py` lee la salida del emulador **segun sale**, asi
  que la partida se ve avanzar en vivo.
- **La bateria ya no se puede quedar colgada.** El emulador se lanza con la
  entrada estandar cerrada, que es lo que hacia falta para que la pregunta de
  «¿me bajo la imagen de tarjeta SD?» — que sale por su salida estandar, no por
  la de error — se responda sola que no en vez de esperar una tecla que nadie
  ve que haga falta. Ademas se corta a los `--paciencia` segundos sin noticias
  (120 por defecto) y se cuenta lo que dijo el emulador, con la pista de la
  tarjeta si es lo que falla. Opciones nuevas: `--bajar-sd`, `--paciencia`.
- **Arreglado en Windows**: el puerto magico sale por la salida de error de
  jnext y alli el runtime de C convierte cada `\n` en `\r\n`, asi que las marcas
  del volcado llegaban como `\r\n#RESET\r\n` y no casaba ninguna: la bateria se
  tiraba la partida entera sin enterarse de nada y daba las 12 pruebas por no
  alcanzadas. Ahora se tiran los retornos de carro al descodificar. De paso, el
  aviso de la tarjeta SD mira donde la busca jnext de verdad (`$JNEXT_CONFIG_DIR`,
  `$HOME/.jnext` y, si HOME no esta puesta, `.jnext` de la carpeta desde la que
  se lance), no la carpeta del usuario a secas.
- **Y va seis veces mas rapida**: el emulador se corta en cuanto el guion llega
  al final, en lugar de seguir barriendo hasta el tope. Las 288 ordenes de
  *Tifon Negro* pasan de 91 s a 14 s.

### Correcciones
Las tres las encontro la bateria nueva.

- **`ISAT #objeto #contenedor` no estaba soportado en el motor nativo**, y
  *Tifon Negro* **no se podia acabar** por eso: coger los codigos Enigma o el
  pase del muelle de dentro de la caja fuerte se rechazaba siempre. Un objeto
  dentro de un contenedor guarda `OBJLOC = CONTAINED` y el contenedor aparte, en
  `OBJIN`, asi que no cabe en el byte de destino que compara `ISAT`; ahora
  `nativecc` emite un opcode propio (`ISIN`) cuando el destino es un `#objeto`.
- **Ni la oscuridad ni las fuentes de luz han funcionado nunca en el motor
  nativo** (ni en Next ni en CPC). El motor leia las tablas `locdark`,
  `objlight` y `objlit` dos bytes por encima de donde las deja el constructor de
  la base de datos, de modo que ninguna sala era oscura y ningun objeto
  alumbraba: en *Tifon Negro* el tunel de escape se veia sin linterna.
- **El motor nativo se pasaba de largo con mas de 64 objetos o 64 variables.**
  Las matrices de estado en RAM (`FLAGS`, `OBJLOC`, `OBJLIT`, `OBJOPEN`,
  `OBJLOCK`, `OBJIN`) son de 64 y no habia ninguna comprobacion: el objeto 65
  escribia sobre la matriz siguiente sin dar error. Ahora se corta al compilar
  con un mensaje claro. (Las **localizaciones** si llegan a 255: no llevan
  matriz en RAM.)

- **La puntuacion salia pegada al eco de la orden** en el motor nativo
  (`puntuacionPuntuacion: 25`): el condact `SCORE` imprimia sin saltar de linea
  antes, al reves que `MESSAGE` y que el export de 128K.

- **`PRINT "...{_VARIABLE}..."` imprimia las llaves tal cual** en el motor
  nativo, en vez del valor: salia `[0{_HORA_H}:{_HORA_M}]` y `(Carga restante:
  {_PILAS_CARGA} turnos.)`. Ahora `nativecc` parte el texto por las llaves y va
  alternando mensaje y variable, con un condact nuevo (`PRVAR`) que imprime el
  valor en decimal — lo mismo que hacen los exports BASIC con `STR$()`.

---

## 2.46 — 2026-09-20 — Motor nativo para ZX Spectrum Next

### Novedades
- **Motor nativo de ZX Spectrum Next.** Nuevo destino del editor, «Exportar ZX
  Spectrum Next (.nex, motor nativo)», que sustituye al export BASIC a `.tap`.
  Compila motor y base de datos en Python puro (sin zxbc, sin Boriel y sin
  NextBuild) reutilizando el motor Z80 que ya servia al CPC: de sus ~2800 lineas
  de ensamblador, solo una veintena de simbolos dependian de la maquina. Sale en
  `dist/{juego}_next_{idioma}.nex`.
  - Texto de 42 columnas con la misma tipografia que los builds BASIC, con los
    acentos de español y portugues.
  - Imagenes de localizacion por Layer 2: cada una en su banco de 16K, asi que
    cambiar de sala es apuntar el NextReg $12 a otro banco, sin mover un pixel.
    Se descubren de arriba abajo subiendo la linea de corte del clip.
  - Pantalla de titulo a pantalla completa, con musica del AY (reproductor de
    stream PSG). La musica se ajusta al hueco que quede en el binario.
  - Efectos de sonido FX por AY (el condact `PLAY`).
  - El texto se escribe a ritmo — una descripcion de sala tarda unos 2 s — y se
    para a esperar tecla cada vez que se llena la ventana.
  - Teclado leido por la matriz del puerto &FE, con borrado en CAPS+0.
  - Motor y plataforma ocupan ~8 KB; un juego con 23 imagenes, portada y musica
    se queda en ~35 KB de binario plano mas sus bancos.
  - No usa la ROM para nada (fuente, teclado e impresion son propios): solo la
    aparta un instante, con el MMU, para leer las paletas de su banco.
- **Comando VERSION en el motor nativo**, que quedaba pendiente en 2.45. Ahora
  responden los cuatro motores.
- **`metadata.start_message` en el motor nativo**: la presentacion del juego, que
  hasta ahora solo salia en el interprete y en los exports BASIC. Vale tambien
  para el CPC nativo.
- **`initial_message` de los objetos en el motor nativo**: cada objeto sale con
  su frase propia en vez de listarse por el nombre, y un objeto fijo sin frase
  no se lista, que para eso lo cuenta la descripcion de la sala. Como en el
  interprete, la frase deja de usarse en cuanto el objeto se mueve. Vale tambien
  para el CPC nativo.
- **Nombre de la localizacion en el motor nativo**: solo imprimia la
  descripcion. Vale tambien para el CPC nativo.
- `z80asm.py` y `z80.py` entienden ahora IN/OUT por puertos, los NextRegs y el
  juego de instrucciones **Z80N** (PIXELAD, PIXELDN, LDWS, LDIRX, ADD HL,A...).
  El simulador emula ademas la paginacion de la ranura 0 del MMU.
- `verify_next.py`: arnes que ensambla el motor, lo corre en el simulador,
  **decodifica la pantalla de vuelta a texto** comparando con la fuente, empaqueta
  el `.nex`, lo relee del disco y juega ordenes. A diferencia de `verify_cpc.py`,
  no pone stubs de texto ni de teclado: ese camino se ejercita de verdad.
- `genera_font42.py` genera `font42.py`, la fuente de 6 pixeles del motor nativo,
  a partir de la fuente de la ROM y de las tablas de `print42_*.bas`.

### Correcciones
- **`txtpack`: la segunda compresion de texto de un proceso salia con las frases
  de la primera.** `_expand` llevaba un `dict` mutable como valor por defecto,
  que sobrevivia entre llamadas y se indexaba solo por numero de token. Se veia
  como texto casi correcto con trozos de otro juego metidos. Afecta a **todos**
  los destinos y a cualquier sesion que exporte dos veces sin reiniciar.
- Las salidas se imprimen al final de la descripcion (nombre, descripcion,
  objetos, salidas), como en el export de 128K, y no entre la descripcion y los
  objetos.
- Cada objeto de la sala sale en su propia linea, en vez de amontonados.
- Glifos `_` y `q` corregidos en la fuente de 42 columnas del motor nativo: en
  `print42_*.bas` el subrayado apunta al indice de la `a` acentuada, y el remate
  de la cola de la `q` se sale de la celda e invade el caracter siguiente.
- Los menus de 48K y 128K decian «(.bas)», que es el intermedio: lo que producen
  es un `.tap` en `dist/`.

### Pendiente
- Los glifos `_` y `q` siguen mal en `print42_es.bas` y `print42_pt.bas`, o sea
  en los `.tap` de 128K y de Next.
- El camino `.nex` con Boriel sigue parado por `EmbeddedMmuSwitchAssembleError`
  (`next_export.moduliza_texto`, escrito pero sin usar). El motor nativo resuelve
  lo mismo sin Boriel.
- El DMA y el Copper del Next estan sin usar: el borrado y el desplazamiento de
  pantalla siguen con `LDIR`, que es justo donde el DMA rentaria.

---

## 2.45 — 2026-09-19 — Ficha de identificacion de los compilados

### Novedades
- Comando **VERSION** en todos los juegos y en los cuatro motores. Muestra
  titulo, version y revision del juego con su fecha, autor, idioma, version de
  Scriba, fecha de compilacion y sistema. El texto se resuelve al exportar,
  porque en la maquina destino no hay YAML que consultar.
- El editor sella `metadata.revision` (contador que sube en cada guardado) y
  `metadata.modified` (fecha) al guardar. `metadata.version` sigue siendo del
  autor, para marcar hitos.
- Nuevo modulo `scriba_info.py`: fuente unica de la version de Scriba y de la
  ficha, compartida por editor, interprete y los tres exportadores.
  `build_exe.bat` lee de ahi el numero para nombrar el ejecutable.

### Correcciones
- `build_exe.bat` empaqueta `Scriba_Manual.pdf` en vez del PDF con la version en
  el nombre, que obligaba a renombrarlo en cada release para que el manual
  siguiera abriendose desde el programa.

### Pendiente
- El motor nativo de CPC (`nativecc.py` / `game_engine.py`) no responde todavia
  al comando VERSION; el export a BASIC Locomotive si.

---

## 2.44 — 2026-09-19 — Restauración de los predicados de objeto

### Novedades
- El validador rechaza las condiciones que usan un predicado desconocido, con el
  nombre y la línea. Aparece también en el panel de problemas del editor.
- Al validar, se informa de lo que cada plataforma no soporta del juego.
- `paws_lang.PREDICATES` vuelve a estar completo (21 nombres), de modo que
  `capabilities.py` y `compiler.py` reconocen los predicados de estado.

### Correcciones
- Restaurados los trece predicados de estado (`CARRIED`, `NOTCARR`, `PRESENT`,
  `ABSENT`, `WORN`, `NOTWORN`, `ISAT`, `HASOBJOPEN`, `ZERO`, `NOTZERO`, `EQ`,
  `GT`, `LT`) en el intérprete de PC y en el exportador de Spectrum —del que
  bebe el Next—. Se perdieron en 2.43 al unificar la gramática en `paws_lang`;
  mientras faltaron, toda condición que los usara valía «verdadero» siempre.
  El backend de CPC no se vio afectado y sirvió de referencia.
- `REMOVE` no llegaba a ejecutarse: la detección de comentarios comparaba por
  prefijo con `REM`. Corregido en `interpreter.py`, `nativecc.py` y en tres
  puntos de `editor.py` (depurador, puntos de ruptura y renombrado).
- `CREATE` y `PUT` con destino `INVEN`, `PUESTO` o `NADA` dejaban el objeto en
  «ninguna parte» al exportar a Spectrum, Next y CPC, porque `locval()` solo
  admitía las formas con arroba. Ahora acepta las dos escrituras, igual que
  `_destval()` en `nativecc.py`.
- Un predicado que el motor no reconozca ya no se da por cierto: se avisa una
  vez por consola y se evalúa como falso.

---

## 2.3 — Vocabulario de serie editable y por idioma

### Novedades
- **Verbos y preposiciones de serie editables** desde el editor (botón «Verbos/preposiciones…»),
  con valores **por idioma** (ES/EN/PT) según `metadata.language` y guardados en
  `metadata['vocab_base']`. Válido para PC, Spectrum, Next y CPC (fuente única `vocab_base.py`,
  antes duplicada e inconsistente).
- **CPC:** el aviso **«[+n puntos]»** del condact `ADDSCORE` ahora se muestra (antes solo sumaba
  en silencio) y es **traducible** (`puntos_mas` en Mensajes del sistema).
- Manual **reconstruido como documento fluido** (docx/odt/pdf), con logo, portada 2.3,
  índice, tablas y bloques de código; documentada la cláusula `ON` con **dos nombres**
  (verbo + nombre1 + nombre2) para acciones con dos objetos («poner pilas en linterna»).

### Correcciones
- Generador ZX BASIC: `exDesc` (EXAMINAR) ya no emite un `IF 0 THEN` con bloque vacío
  cuando ningún objeto tiene descripción (Boriel no admite THEN vacío).
- Recordatorio de sintaxis: el `IF` debe terminar en `THEN` (tanto en el intérprete
  interno como al exportar).

---

## 2.2 — FX en Next, localización completa y nombres de distribución

### Novedades
- **Efectos FX por AY también en ZX Spectrum Next.** En Next el heap se ajusta a 2 KB solo
  cuando el juego usa FX (libera RAM para el reproductor); 4 KB si no.
- **`PLAY "nombre"`:** el condact referencia los efectos por **nombre** en vez de por número
  (`PLAY "explosion"`; se sigue admitiendo `PLAY n`). Borrar o reordenar efectos ya no
  descoloca las llamadas.
- **Localización de mensajes del sistema (ES/EN/PT):**
  - Catálogo de mensajes traducibles ampliado (incluye «Salidas:», nombres de salida y
    «Llevas demasiado peso.»); editable con «Mensajes del sistema…».
  - Las traducciones (`metadata['mensajes']`) valen para **Spectrum, Next y CPC**.
  - El **intérprete de PC** se traduce automáticamente por idioma (tablas ES/EN/PT) y respeta
    los textos personalizados del autor.
- **Nombres de distribución unificados:** `{juego}_{plataforma}_{idioma}.{ext}`
  (`48kb`/`128kb`/`next`/`cpc`/`windows`), todos juntos en una única carpeta `dist/`
  (sin subcarpetas por plataforma).
- **CPC:** vocabulario ampliado de **255 a 16 bits** (hasta 65535 palabras tras quitar duplicados).

---

## 2.1 — Efectos de sonido FX (AY)

### Novedades
- **Pestaña FX** en el editor: crear efectos sintetizados (bloques de tono/ruido) o
  **importar AYFX** del AY Sound FX Editor de Shiru (`.afx` individual o bancos `.afb`),
  con diálogo de previsualización (oír con las flechas/clic, marcar con la barra espaciadora).
- **Condact `PLAY`** para disparar efectos por el chip **AY** en PC y **Spectrum 128K**.
- En la exportación retro solo se embeben los efectos realmente referenciados por algún `PLAY`.

---

## 2.0 — Motor nativo CPC y exportación a Windows

### Novedades
- **Amstrad CPC:** motor **nativo Z80** (modelo PAW/DAAD), salida en `.dsk` arrancable, con
  **paridad** de lógica con las demás plataformas: objetos vestibles, luz/oscuridad,
  temporizadores, contenedores (candado y llave), límite de peso y parser de dos nombres (NOUN2).
- **Exportación a Windows (.exe):** paquete portable con el reproductor `ScribaPlayer.exe`
  y el juego; el jugador descomprime y ejecuta, sin instalar nada.
- **Peso** (`LLEVAR_MAX` + peso por objeto) en Spectrum/Next y CPC.
- Resumen de compilación **48K** con memoria libre; avisos de compatibilidad por plataforma
  (lo que un destino no soporta).
- Correcciones varias del editor (histórico de walkthrough, Guardar/Cargar/Snapshot, reinicio
  del probador, búsqueda en el código) y de exportación (vocabulario PT, «coger todo»).

---

<!--
Plantilla para una nueva versión (copia y rellena):

## X.Y — Título breve

### Novedades
- …

### Correcciones
- …
-->
