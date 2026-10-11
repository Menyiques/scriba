"""Flyer de publicidad de Scriba (A4), en cinco idiomas.

    python "flyer source/flyer.py" [es en pt ca fr] [--png]

Escribe flyer source/flyer_<idioma>.html y, con Chrome sin ventana, el PDF en
Games/Operacion Tifon Negro/dist/Scriba_<idioma>.pdf (con --png, ademas una
imagen de la pagina en flyer source/flyer_<idioma>.png, para revisarla).

La maqueta reproduce el flyer de septiembre de 2026 (img/original_es_2026-09.jpg,
que solo existia como imagen): las medidas estan en mm sacadas de esa imagen y
las fotos (capturas, logos, QR) son recortes de ella. Los textos de cada idioma
estan en TEXTOS; las lineas que tienen que caber en una (titular, cabecera,
pie) se encogen solas si en un idioma no caben.
"""
import html
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DIST = os.path.join(RAIZ, 'Games', 'Operacion Tifon Negro', 'dist')
GITHUB = 'github.com/Menyiques/scriba'
NB = ' '                       # espacio duro (tipografia francesa)

TEXTOS = {
    'es': {
        'cab': ('PUBLICIDAD', 'Sistema multiplataforma de aventuras conversacionales',
                'VERSIÓN 3.0 · OCTUBRE 2026'),
        'titular': ('BASIC por fuera.', 'ASM por dentro.'),
        'sello': ('¡Nuevo!', '3.0'),
        'entradilla': 'Escribe tu aventura conversacional una vez y llévala al Spectrum, '
                      'al Amstrad, al MSX2 y al PC. Con editor visual, depurador y '
                      'multiidioma de serie.',
        'capturas': (('ZX Spectrum 128K.', 'Apolo 11, en español.'),
                     ('ZX Spectrum Next.', 'Imágenes por Layer 2.'),
                     ('Amstrad CPC 6128.', 'Modo 1, a 4 colores.')),
        'c1': ('ASM nativo', 'Tu aventura corre sobre un motor nativo en código máquina Z80. '
               'Desde la 3.0, todas las máquinas salen del mismo motor, compilado en '
               'Python puro.',
               ('Música AY, efectos FX y sonido WAV digitalizado',
                'En el Next, Layer 2 y sin tocar la ROM',
                'Presupuesto de memoria en cada exportación')),
        'c2': ('Condacts en BASIC', 'Si has escrito BASIC, ya sabes escribir condacts: ON, '
               'IF, THEN, ELSE, LET y PRINT, con variables y temporizadores.'),
        'codigo': ('El Faro', 'CAVAR', 'ARENA', '@playa', '_ARENA_CAVADA', '#llave',
                   'Asoma una llave.'),
        'c3': ('Siete plataformas', 'Una misma base de datos, compilada para cada máquina y '
               'en cinco idiomas: español, catalán, inglés, francés y portugués.', 'disco'),
        'nov': ('Novedades', 'de esta versión'),
        'novedades': (('MSX2.', 'Cartucho MegaROM, SCREEN 5 a 42 columnas y música por el PSG.'),
                      ('Amstrad PCW.', 'Disco autoarrancable para 8256 y 8512, a 90×32.'),
                      ('Motor nativo Z80', 'en todas las máquinas. Adiós a Boriel.'),
                      ('CPC en Modo 1.', '40 columnas e imágenes de 4 colores en ZX0.'),
                      ('128K y Next.', 'Texto, música y FX en bancos de memoria.'),
                      ('Windows.', 'Un único .exe con el juego dentro, cifrado.'),
                      ('Importa DAAD.', 'Abre juegos .ddb de DAAD 1 y 2 (8 bits) y los '
                       'convierte a YAML, con su lógica.')),
        'editor': ('El editor.', 'Mapa arrastrable de Apolo 11, con pestañas de objetos, '
                   'vocabulario, condacts y sonido. Pruebas en el PC al instante, con '
                   'depurador paso a paso.'),
        'pie': ('Pruébalo hoy.', 'Únete al canal.',
                'Código en {gh}, con El Faro y la demo de Operación Tifón Negro.',
                'Un programa de Sergio Morales'),
    },
    'en': {
        'cab': ('ADVERTISEMENT', 'A multi-platform text adventure system',
                'VERSION 3.0 · OCTOBER 2026'),
        'titular': ('BASIC outside.', 'ASM inside.'),
        'sello': ('New!', '3.0'),
        'entradilla': 'Write your text adventure once and take it to the Spectrum, the '
                      'Amstrad, the MSX2 and the PC. Visual editor, debugger and '
                      'multi-language support included.',
        'capturas': (('ZX Spectrum 128K.', 'Apollo 11, in Spanish.'),
                     ('ZX Spectrum Next.', 'Layer 2 graphics.'),
                     ('Amstrad CPC 6128.', 'Mode 1, in 4 colours.')),
        'c1': ('Native ASM', 'Your adventure runs on a native Z80 machine-code engine. '
               'Since 3.0, every machine is built from the same engine, compiled in '
               'pure Python.',
               ('AY music, FX and digitised WAV sound',
                'On the Next, Layer 2 and the ROM left untouched',
                'A memory budget with every export')),
        'c2': ('Condacts in BASIC', 'If you have written BASIC, you can already write '
               'condacts: ON, IF, THEN, ELSE, LET and PRINT, with variables and timers.'),
        'codigo': ('El Faro', 'DIG', 'SAND', '@beach', '_SAND_DUG', '#key',
                   'A key peeks out.'),
        'c3': ('Seven platforms', 'One database, compiled for each machine and in five '
               'languages: Spanish, Catalan, English, French and Portuguese.', 'disk'),
        'nov': ("What's new", 'in this version'),
        'novedades': (('MSX2.', 'MegaROM cartridge, SCREEN 5 at 42 columns and music '
                       'through the PSG.'),
                      ('Amstrad PCW.', 'Self-booting disk for the 8256 and 8512, at 90×32.'),
                      ('Native Z80 engine', 'on every machine. Goodbye, Boriel.'),
                      ('CPC in Mode 1.', '40 columns and 4-colour images in ZX0.'),
                      ('128K and Next.', 'Text, music and FX in memory banks.'),
                      ('Windows.', 'A single encrypted .exe with the game inside.'),
                      ('DAAD import.', 'Opens DAAD 1 and 2 .ddb games (8-bit) and converts '
                       'them to YAML, logic included.')),
        'editor': ('The editor.', 'Draggable map of Apollo 11, with tabs for objects, '
                   'vocabulary, condacts and sound. Instant testing on the PC, with a '
                   'step-by-step debugger.'),
        'pie': ('Try it today.', 'Join the channel.',
                'Source code at {gh}, with El Faro and the DAS BOOT demo.',
                'A program by Sergio Morales'),
    },
    'pt': {
        'cab': ('PUBLICIDADE', 'Sistema multiplataforma de aventuras de texto',
                'VERSÃO 3.0 · OUTUBRO 2026'),
        'titular': ('BASIC por fora.', 'ASM por dentro.'),
        'sello': ('Novo!', '3.0'),
        'entradilla': 'Escreve a tua aventura de texto uma vez e leva-a ao Spectrum, ao '
                      'Amstrad, ao MSX2 e ao PC. Com editor visual, depurador e '
                      'multilíngue de série.',
        'capturas': (('ZX Spectrum 128K.', 'Apolo 11, em espanhol.'),
                     ('ZX Spectrum Next.', 'Imagens em Layer 2.'),
                     ('Amstrad CPC 6128.', 'Modo 1, a 4 cores.')),
        'c1': ('ASM nativo', 'A tua aventura corre sobre um motor nativo em código máquina '
               'Z80. Desde a 3.0, todas as máquinas saem do mesmo motor, compilado em '
               'Python puro.',
               ('Música AY, efeitos FX e som WAV digitalizado',
                'No Next, Layer 2 e sem tocar na ROM',
                'Orçamento de memória em cada exportação')),
        'c2': ('Condacts em BASIC', 'Se já escreveste BASIC, já sabes escrever condacts: '
               'ON, IF, THEN, ELSE, LET e PRINT, com variáveis e temporizadores.'),
        'codigo': ('El Faro', 'CAVAR', 'AREIA', '@praia', '_AREIA_CAVADA', '#chave',
                   'Aparece uma chave.'),
        'c3': ('Sete plataformas', 'Uma mesma base de dados, compilada para cada máquina e '
               'em cinco línguas: espanhol, catalão, inglês, francês e português.', 'disco'),
        'nov': ('Novidades', 'desta versão'),
        'novedades': (('MSX2.', 'Cartucho MegaROM, SCREEN 5 a 42 colunas e música pelo PSG.'),
                      ('Amstrad PCW.', 'Disco de arranque automático para 8256 e 8512, '
                       'a 90×32.'),
                      ('Motor nativo Z80', 'em todas as máquinas. Adeus, Boriel.'),
                      ('CPC em Modo 1.', '40 colunas e imagens de 4 cores em ZX0.'),
                      ('128K e Next.', 'Texto, música e FX em bancos de memória.'),
                      ('Windows.', 'Um único .exe com o jogo lá dentro, cifrado.'),
                      ('Importa DAAD.', 'Abre jogos .ddb do DAAD 1 e 2 (8 bits) e '
                       'converte-os para YAML, com a lógica.')),
        'editor': ('O editor.', 'Mapa arrastável de Apolo 11, com separadores de objetos, '
                   'vocabulário, condacts e som. Testes no PC na hora, com depurador '
                   'passo a passo.'),
        'pie': ('Experimenta hoje.', 'Junta-te ao canal.',
                'Código em {gh}, com El Faro e a demo de DAS BOOT.',
                'Um programa de Sergio Morales'),
    },
    'ca': {
        'cab': ('PUBLICITAT', "Sistema multiplataforma d'aventures conversacionals",
                'VERSIÓ 3.0 · OCTUBRE 2026'),
        'titular': ('BASIC per fora.', 'ASM per dins.'),
        'sello': ('Nou!', '3.0'),
        'entradilla': "Escriu la teva aventura conversacional una sola vegada i porta-la a "
                      "l'Spectrum, a l'Amstrad, a l'MSX2 i al PC. Amb editor visual, "
                      "depurador i multiidioma de sèrie.",
        'capturas': (('ZX Spectrum 128K.', 'Apol·lo 11, en castellà.'),
                     ('ZX Spectrum Next.', 'Imatges amb Layer 2.'),
                     ('Amstrad CPC 6128.', 'Mode 1, a 4 colors.')),
        'c1': ('ASM natiu', 'La teva aventura corre sobre un motor natiu en codi màquina '
               'Z80. Des de la 3.0, totes les màquines surten del mateix motor, compilat '
               'en Python pur.',
               ('Música AY, efectes FX i so WAV digitalitzat',
                'Al Next, Layer 2 i sense tocar la ROM',
                'Pressupost de memòria a cada exportació')),
        'c2': ('Condacts en BASIC', 'Si has escrit BASIC, ja saps escriure condacts: ON, '
               'IF, THEN, ELSE, LET i PRINT, amb variables i temporitzadors.'),
        'codigo': ('El Faro', 'CAVAR', 'SORRA', '@platja', '_SORRA_CAVADA', '#clau',
                   'Treu el cap una clau.'),
        'c3': ('Set plataformes', 'Una mateixa base de dades, compilada per a cada màquina '
               'i en cinc idiomes: castellà, català, anglès, francès i portuguès.', 'disc'),
        'nov': ('Novetats', "d'aquesta versió"),
        'novedades': (('MSX2.', 'Cartutx MegaROM, SCREEN 5 a 42 columnes i música pel PSG.'),
                      ('Amstrad PCW.', "Disc d'arrencada automàtica per a 8256 i 8512, "
                       'a 90×32.'),
                      ('Motor natiu Z80', 'a totes les màquines. Adéu, Boriel.'),
                      ('CPC en Mode 1.', '40 columnes i imatges de 4 colors en ZX0.'),
                      ('128K i Next.', 'Text, música i FX en bancs de memòria.'),
                      ('Windows.', 'Un únic .exe amb el joc a dins, xifrat.'),
                      ('Importa DAAD.', 'Obre jocs .ddb de DAAD 1 i 2 (8 bits) i els '
                       'converteix a YAML, amb la lògica.')),
        'editor': ("L'editor.", "Mapa arrossegable d'Apol·lo 11, amb pestanyes d'objectes, "
                   'vocabulari, condacts i so. Proves al PC a l’instant, amb depurador '
                   'pas a pas.'),
        'pie': ("Prova'l avui.", "Uneix-te al canal.",
                'Codi a {gh}, amb El Faro i la demo de DAS BOOT.',
                'Un programa de Sergio Morales'),
    },
    'fr': {
        'cab': ('PUBLICITÉ', "Système multiplateforme d'aventures textuelles",
                'VERSION 3.0 · OCTOBRE 2026'),
        'titular': ('BASIC en façade.', 'ASM sous le capot.'),
        'sello': ('Nouveau' + NB + '!', '3.0'),
        'entradilla': 'Écrivez votre aventure textuelle une seule fois et emmenez-la sur '
                      'Spectrum, Amstrad, MSX2 et PC. Éditeur visuel, débogueur et '
                      'multilingue inclus.',
        'capturas': (('ZX Spectrum 128K.', 'Apollo 11, en espagnol.'),
                     ('ZX Spectrum Next.', 'Images en Layer 2.'),
                     ('Amstrad CPC 6128.', 'Mode 1, en 4 couleurs.')),
        'c1': ('ASM natif', 'Votre aventure tourne sur un moteur natif en code machine '
               'Z80. Depuis la 3.0, toutes les machines sortent du même moteur, compilé '
               'en Python pur.',
               ('Musique AY, effets FX et son WAV numérisé',
                'Sur le Next, Layer 2 sans toucher à la ROM',
                'Budget mémoire à chaque export')),
        'c2': ('Condacts en BASIC', 'Si vous avez écrit du BASIC, vous savez déjà écrire '
               'des condacts' + NB + ': ON, IF, THEN, ELSE, LET et PRINT, avec variables et '
               'minuteries.'),
        'codigo': ('El Faro', 'CREUSER', 'SABLE', '@plage', '_SABLE_CREUSE', '#cle',
                   'Une clé dépasse.'),
        'c3': ('Sept plateformes', 'Une même base de données, compilée pour chaque machine '
               'et en cinq langues' + NB + ': espagnol, catalan, anglais, français et '
               'portugais.', 'disquette'),
        'nov': ('Nouveautés', 'de cette version'),
        'novedades': (('MSX2.', 'Cartouche MegaROM, SCREEN 5 en 42 colonnes et musique '
                       'par le PSG.'),
                      ('Amstrad PCW.', 'Disquette auto-amorçable pour 8256 et 8512, '
                       'en 90×32.'),
                      ('Moteur natif Z80', 'sur toutes les machines. Adieu, Boriel.'),
                      ('CPC en mode 1.', '40 colonnes et images 4 couleurs en ZX0.'),
                      ('128K et Next.', 'Texte, musique et FX en banques mémoire.'),
                      ('Windows.', 'Un seul .exe chiffré, le jeu à l’intérieur.'),
                      ('Import DAAD.', 'Ouvre les jeux .ddb de DAAD 1 et 2 (8 bits) et '
                       'les convertit en YAML, logique comprise.')),
        'editor': ("L'éditeur.", "Carte déplaçable d'Apollo 11, avec onglets pour objets, "
                   'vocabulaire, condacts et son. Tests immédiats sur PC, avec débogueur '
                   'pas à pas.'),
        'pie': ('Essayez-le.', 'Rejoignez la chaîne.',
                'Code source sur {gh}, avec El Faro et la démo de DAS BOOT.',
                'Un programme de Sergio Morales'),
    },
}

PLATAFORMAS = (('ZX Spectrum 48K', '.TAP'), ('ZX Spectrum 128K', '.TAP'),
               ('ZX Spectrum Next', '.NEX'), ('Amstrad CPC 6128', '.DSK'),
               ('MSX2', 'MegaROM'), ('Amstrad PCW', None), ('Windows', '.EXE'))

CSS = r'''
@page { size: 210mm 297mm; margin: 0; }
html, body { margin: 0; padding: 0; background: #f2f2f2; }
body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.pag { position: relative; width: 210mm; height: 297mm; overflow: hidden;
       background: #f2f2f2; color: #1e1e1e;
       font-family: 'Source Serif 4', Georgia, serif; }
.a { position: absolute; }
img { display: block; }
.fit { white-space: nowrap; }
.barra { left: 12.71mm; width: 184.75mm; top: 10.84mm; height: 1.36mm; background: #221e1b; }
.cab { left: 12.71mm; width: 184.75mm; top: 12.2mm; height: 6.52mm;
       border-bottom: 0.34mm solid #1e1e1e; display: flex; align-items: center;
       justify-content: space-between; font-size: 7.35pt; }
.cab .i { font-weight: 700; letter-spacing: 0.13em; }
.cab .c { font-style: italic; font-size: 8.6pt; }
.cab .d { letter-spacing: 0.11em; }
.titular { left: 12.0mm; width: 138mm; top: 19.59mm; font-size: 45.1pt; line-height: 18.26mm;
           font-weight: 700; letter-spacing: -0.012em; color: #0a0a0a;
           text-shadow: -0.3mm -0.22mm 0 #d9c300, 0.32mm 0.25mm 0 #d4006c; }
.sello { left: 151.55mm; top: 27.19mm; width: 20.25mm; height: 20.25mm; border-radius: 50%;
         background: #d4006c; color: #fff; display: flex; flex-direction: column;
         align-items: center; justify-content: center; }
.sello .n { font-style: italic; font-size: 9.3pt; line-height: 1; white-space: nowrap;
           transform: rotate(9deg); margin: 0.6mm 0 0.7mm 1.6mm; }
.sello .v { font-style: italic; font-weight: 600; font-size: 22pt; line-height: 1;
           transform: rotate(5deg); margin: 0 1.6mm 0 0; }
.logo { left: 173.32mm; top: 38.63mm; width: 23.89mm; }
/* --k: escala que el script baja (hasta 0,8) si un bloque no cabe en su alto */
.entradilla { left: 12.71mm; width: 146mm; top: 62.03mm; font-style: italic; color: #2a2a2a;
              font-size: calc(11.9pt * var(--k, 1)); line-height: calc(5.55mm * var(--k, 1)); }
.cap { top: 118.45mm; width: 58mm; font-size: 8.1pt; line-height: 4mm; }
.cap b { font-weight: 700; }
.cap i { color: #333; }
.col { top: 126.52mm; width: 56.75mm; font-size: calc(9.44pt * var(--k, 1));
       line-height: calc(4.75mm * var(--k, 1)); }
.col h2 { margin: 0 0 1.38mm 0; font-size: 15.3pt; line-height: 7mm; color: #006484;
          font-weight: 600; white-space: nowrap; }
.col p { margin: 0; }
.col ul { margin: 2.29mm 0 0 0; padding: 0; list-style: none;
          font-size: calc(8.9pt * var(--k, 1)); line-height: calc(4.08mm * var(--k, 1)); }
.col li { position: relative; padding-left: 4.36mm; margin-bottom: calc(1.45mm * var(--k, 1)); }
.col li::before { content: ''; position: absolute; left: 0; top: 0.9mm; width: 2.2mm;
                  height: 2.2mm; background: #a80854; }
pre { margin: 2.43mm 0 0 0; font-family: 'Source Code Pro', Consolas, monospace;
      font-size: calc(7.04pt * var(--k, 1)); line-height: calc(4.02mm * var(--k, 1));
      color: #2b2b2b; }
pre .k { color: #006484; font-weight: 700; }
pre .r { color: #5d5d5d; font-style: italic; }
pre .s { color: #98144c; }
table { margin-top: 2.15mm; border-collapse: collapse; width: 100%; }
td { padding: 0; height: calc(5.08mm * var(--k, 1)); vertical-align: baseline;
     font-size: calc(8.9pt * var(--k, 1)); }
td.f { font-style: italic; color: #333; width: 15.5mm; }
.nov3 { left: 12.62mm; top: 193.05mm; font-size: 37pt; line-height: 1; font-weight: 700;
        color: #0a0a0a; text-shadow: -0.45mm -0.25mm 0 #d9c300, 0.45mm 0.25mm 0 #d4006c; }
.novt { left: 33.68mm; top: 194.86mm; font-size: 15.1pt; line-height: 5.75mm; }
.novt b { font-weight: 700; display: block; }
.novt i { display: block; }
.lista { left: 12.71mm; width: 88mm; top: 209.96mm; margin: 0; padding: 0; list-style: none;
         font-size: calc(8.5pt * var(--k, 1)); line-height: calc(4.2mm * var(--k, 1));
         counter-reset: n; }
.lista li { position: relative; padding-left: 4.61mm; margin-bottom: calc(0.95mm * var(--k, 1));
            counter-increment: n; }
.lista li::before { content: counter(n); position: absolute; left: 0; top: 0;
                    color: #a80854; font-weight: 700; }
.lista b { font-weight: 700; }
.editor { left: 106.57mm; top: 195.01mm; width: 91.23mm; }
.edpie { left: 106.57mm; width: 91.2mm; top: 242.42mm;
         font-size: calc(8.14pt * var(--k, 1)); line-height: calc(4.02mm * var(--k, 1)); }
.edpie i { color: #333; }
.regla { left: 12.71mm; width: 184.75mm; top: 259.13mm; height: 0.34mm; background: #1e1e1e; }
.pt { left: 12.62mm; width: 112mm; top: 261.93mm; font-size: 17pt; line-height: 7.4mm; }
.pt b { font-weight: 700; }
.url { left: 12.63mm; top: 269.75mm; font-size: 13.1pt; line-height: 7mm; color: #006480; }
.cod { left: 12.62mm; width: 108.6mm; top: 278.08mm; font-size: 8.4pt; line-height: 3.5mm;
       color: #333; }
.cod a { color: #006480; text-decoration: none; }
.prog { left: 130.37mm; width: 39.05mm; top: 267.44mm; text-align: center; font-style: italic;
        font-size: 7.73pt; color: #333; white-space: nowrap; }
.meny { left: 130.37mm; top: 273.11mm; width: 39.05mm; }
.qr { left: 176.28mm; top: 263.71mm; width: 21.52mm; }
'''

FIT = r'''
var MM = 96 / 25.4;
document.fonts.ready.then(function () {
  // lo que va en una linea y no cabe a lo ancho: se encoge
  document.querySelectorAll('.fit').forEach(function (e) {
    var t = 0, s = parseFloat(getComputedStyle(e).fontSize);
    while (e.scrollWidth > e.clientWidth + 0.5 && t++ < 60) {
      s *= 0.985; e.style.fontSize = s + 'px';
    }
  });
  // los bloques con data-max (mm desde arriba) que se pasan: se encoge su --k
  document.querySelectorAll('[data-max]').forEach(function (e) {
    var k = 1, max = parseFloat(e.getAttribute('data-max')) * MM;
    while (e.getBoundingClientRect().bottom > max && k > 0.8) {
      k -= 0.01; e.style.setProperty('--k', k.toFixed(2));
    }
  });
  document.body.setAttribute('data-listo', '1');
});
'''


def e(s):
    return html.escape(s, quote=False)


def pagina(lang):
    T = TEXTOS[lang]
    cap = ''.join(
        '<div class="a cap" style="left:%smm;width:%smm"><b>%s</b> <i>%s</i></div>'
        % (x, w, e(a), e(b)) for (a, b), (x, w) in
        zip(T['capturas'], ((12.71, 58), (76.12, 58), (139.52, 58))))
    rem, verbo, nombre, sala, var, obj, txt = T['codigo']
    codigo = ('<span class="r">REM %s</span>\n'
              '<span class="k">ON</span> %s %s\n'
              '  <span class="k">IF AT</span> %s <span class="k">THEN</span>\n'
              '    <span class="k">LET</span> %s = 1\n'
              '    <span class="k">CREATE</span> %s %s\n'
              '    <span class="k">PRINT</span> <span class="s">"%s"</span>\n'
              '  <span class="k">ENDIF</span>\n'
              '<span class="k">ENDON</span>') % tuple(e(x) for x in (
                  rem, verbo, nombre, sala, var, obj, sala, txt))
    filas = ''.join('<tr><td>%s</td><td class="f">%s</td></tr>'
                    % (e(m), e(f if f else T['c3'][2])) for m, f in PLATAFORMAS)
    lista = ''.join('<li><b>%s</b> %s</li>' % (e(a), e(b)) for a, b in T['novedades'])
    gh = '<a>%s</a>' % GITHUB
    cod = e(T['pie'][2]).replace('{gh}', gh)
    return '''<!doctype html>
<html lang="%(lang)s"><head><meta charset="utf-8">
<title>Scriba publicidad flyer (%(lang)s)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;0,700;0,800;1,400;1,700&family=Source+Code+Pro:wght@400;700&display=block" rel="stylesheet">
<style>%(css)s</style></head>
<body><div class="pag">
<div class="a barra"></div>
<div class="a cab"><span class="i">%(c0)s</span><span class="c fit" style="max-width:110mm">%(c1)s</span><span class="d">%(c2)s</span></div>
<div class="a titular"><div class="fit">%(t0)s</div><div class="fit">%(t1)s</div></div>
<div class="a sello"><div class="n">%(s0)s</div><div class="v">%(s1)s</div></div>
<img class="a logo" src="img/scriba_logo.png" alt="SCRIBA">
<div class="a entradilla" data-max="76.9">%(entr)s</div>
<img class="a" src="img/apolo_128k.png" style="left:12.2mm;top:77.93mm;width:58.96mm" alt="">
<img class="a" src="img/apolo_next.png" style="left:75.9mm;top:78.02mm;width:58.11mm" alt="">
<img class="a" src="img/apolo_cpc.png" style="left:139.01mm;top:77.93mm;width:58.88mm" alt="">
%(cap)s
<div class="a col" style="left:12.71mm" data-max="190.6"><h2 class="fit">%(h1)s</h2><p>%(p1)s</p><ul>%(ul1)s</ul></div>
<div class="a col" style="left:76.71mm" data-max="190.6"><h2 class="fit">%(h2)s</h2><p>%(p2)s</p><pre>%(code)s</pre></div>
<div class="a col" style="left:140.71mm" data-max="190.6"><h2 class="fit">%(h3)s</h2><p>%(p3)s</p><table>%(filas)s</table></div>
<div class="a nov3">3.0</div>
<div class="a novt"><b>%(n0)s</b><i>%(n1)s</i></div>
<ol class="a lista" data-max="257.9">%(lista)s</ol>
<img class="a editor" src="img/editor.png" alt="">
<div class="a edpie" data-max="257.9"><b>%(e0)s</b> <i>%(e1)s</i></div>
<div class="a regla"></div>
<div class="a pt fit"><b>%(p0)s</b> <i>%(pi)s</i></div>
<div class="a url">t.me/ScribaAdventures</div>
<div class="a cod">%(cod)s</div>
<div class="a prog">%(prog)s</div>
<img class="a meny" src="img/menyiques.png" alt="Menyiques soft">
<img class="a qr" src="img/qr.png" alt="QR">
</div><script>%(fit)s</script></body></html>
''' % dict(lang=lang, css=CSS, fit=FIT,
           c0=e(T['cab'][0]), c1=e(T['cab'][1]), c2=e(T['cab'][2]),
           t0=e(T['titular'][0]), t1=e(T['titular'][1]),
           s0=e(T['sello'][0]), s1=e(T['sello'][1]), entr=e(T['entradilla']), cap=cap,
           h1=e(T['c1'][0]), p1=e(T['c1'][1]),
           ul1=''.join('<li>%s</li>' % e(x) for x in T['c1'][2]),
           h2=e(T['c2'][0]), p2=e(T['c2'][1]), code=codigo,
           h3=e(T['c3'][0]), p3=e(T['c3'][1]), filas=filas,
           n0=e(T['nov'][0]), n1=e(T['nov'][1]), lista=lista,
           e0=e(T['editor'][0]), e1=e(T['editor'][1]),
           p0=e(T['pie'][0]), pi=e(T['pie'][1]), cod=cod, prog=e(T['pie'][3]))


def chrome():
    for p in (os.path.join(os.environ.get('ProgramFiles', ''), r'Google\Chrome\Application\chrome.exe'),
              os.path.join(os.environ.get('ProgramFiles(x86)', ''), r'Google\Chrome\Application\chrome.exe'),
              os.path.join(os.environ.get('ProgramFiles(x86)', ''), r'Microsoft\Edge\Application\msedge.exe')):
        if os.path.isfile(p):
            return p
    raise SystemExit('no encuentro Chrome ni Edge')


def renderiza(lang, png=False):
    h = os.path.join(AQUI, 'flyer_%s.html' % lang)
    with open(h, 'w', encoding='utf-8') as f:
        f.write(pagina(lang))
    url = 'file:///' + h.replace('\\', '/')
    base = [chrome(), '--headless=new', '--disable-gpu', '--hide-scrollbars',
            '--run-all-compositor-stages-before-draw', '--virtual-time-budget=20000']
    pdf = os.path.join(DIST, 'Scriba_%s.pdf' % lang)
    subprocess.run(base + ['--no-pdf-header-footer', '--print-to-pdf=' + pdf, url],
                   check=True, capture_output=True)
    out = [pdf]
    if png:
        p = os.path.join(AQUI, 'flyer_%s.png' % lang)
        subprocess.run(base + ['--window-size=794,1123', '--force-device-scale-factor=3',
                               '--screenshot=' + p, url], check=True, capture_output=True)
        out.append(p)
    return out


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for lang in (args or list(TEXTOS)):
        print(lang, renderiza(lang, png='--png' in sys.argv))
