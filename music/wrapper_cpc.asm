; ============================================================================
;  wrapper_cpc.asm  -  Envoltorio para reproducir musica Arkos Tracker (AKY)
;  desde el titulo del juego (CPC) que genera Scriba.
;
;  ORG = &8B00  (IMPORTANTE: Scriba carga la musica ahi durante la portada;
;                no lo cambies salvo que tambien cambies el export de Scriba.)
;  Puntos de entrada (los llama el BASIC generado):
;     &8B00  Init      &8B03  Play (1 frame)      &8B06  Stop
;
;  PASOS:
;   1) En Arkos Tracker: importa tu MIDI, arreglalo a <= 3 voces y exporta la
;      cancion como FUENTE (p.ej. MyMusic.asm). En la ventana de export, deja
;      "encode to address" DESMARCADO (no queremos ORG en la cancion).
;   2) Copia aqui el player AKY del paquete de Arkos: sources/playerAky/PlayerAky.asm
;   3) Ensambla con rasm (https://github.com/EdouardBERGE/rasm):
;         rasm wrapper_cpc.asm -o music
;   4) Copia el music.bin resultante a la carpeta  music/  del proyecto.
;   5) Exporta CPC "80 columnas + imagenes" desde Scriba: la musica sonara en
;      la portada y se parara al pulsar tecla para entrar al juego.
;
;  Limite de tamano: player + cancion deben caber en ~6,5 KB (&8B00..&A5FF),
;  por debajo del area de trabajo de AMSDOS. Para una sintonia de menu sobra.
; ============================================================================

    org #8B00

    jp Init
    jp Play
    jp StopMusic

Init:
    ld hl,Music         ; direccion de los datos de la cancion
    ld a,0              ; subcancion 0 (AKY solo tiene una)
    call Player + 0
    ret

Play:
    di
    ex af,af'
    exx
        push af         ; preservamos lo que el sistema necesita
        push bc
        push ix
        push iy
        call Player + 3 ; reproduce un frame
        pop iy
        pop ix
        pop bc
        pop af
    ex af,af'
    exx
    ei
    ret

StopMusic:
    di
    ex af,af'
    exx
        push af
        push bc
        push ix
        push iy
        call Player + 6 ; detiene la musica y silencia el AY
        pop iy
        pop ix
        pop bc
        pop af
    ex af,af'
    exx
    ei
    ret

Player:
    include "PlayerAky.asm"     ; el player AKY del paquete de Arkos Tracker

Music:
    include "MyMusic.asm"       ; tu cancion exportada como fuente (sin ORG)
