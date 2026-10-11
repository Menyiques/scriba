# -*- coding: utf-8 -*-
"""
daad_ddb.py - Lector de bases de datos DAAD (.ddb) de las maquinas de 8 bits.

Lee la cabecera, el vocabulario, los textos (comprimidos con tokens), los
objetos, las localizaciones, las conexiones y los procesos con sus condacts.
No interpreta nada: deja los datos en Python para que ddb2scriba los traduzca.

Formato (DAAD 1 y 2, little-endian):
  0  version (1 o 2)       1  maquina<<4 | idioma     2  caracter nulo ('_')
  3  n objetos  4 n localizaciones  5 n mensajes  6 n mensajes de sistema
  7  n procesos
  8.. punteros de 16 bits: tokens, procesos, objetos, localizaciones,
      mensajes, mensajes de sistema, conexiones, vocabulario, "inicialmente
      en", palabras de los objetos, peso y atributos, fin.
Los punteros son direcciones absolutas: hace falta la direccion de carga
(base). Si no se da, se deduce: el vocabulario empieza justo tras la cabecera.
"""
import struct

MAQUINAS = {0: 'PC', 1: 'Spectrum', 2: 'C64', 3: 'CPC', 4: 'MSX', 5: 'Atari ST',
            6: 'Amiga', 7: 'PCW'}
IDIOMAS = {0: 'en', 1: 'es'}
TIPOS = {0: 'verbo', 1: 'adverbio', 2: 'nombre', 3: 'adjetivo',
         4: 'preposicion', 5: 'conjuncion', 6: 'pronombre'}

# Caracteres 16..31 del juego de caracteres DAAD (espanol)
ESPECIALES = {16: 'ª', 17: '¡', 18: '¿', 19: '«', 20: '»', 21: 'á', 22: 'é',
              23: 'í', 24: 'ó', 25: 'ú', 26: 'ñ', 27: 'Ñ', 28: 'ç', 29: 'Ç',
              30: 'ü', 31: 'Ü'}

# (nombre, numero de parametros) de los 128 condacts de DAAD
CONDACTS = [
    ('AT', 1), ('NOTAT', 1), ('ATGT', 1), ('ATLT', 1), ('PRESENT', 1),
    ('ABSENT', 1), ('WORN', 1), ('NOTWORN', 1), ('CARRIED', 1), ('NOTCARR', 1),
    ('CHANCE', 1), ('ZERO', 1), ('NOTZERO', 1), ('EQ', 2), ('GT', 2), ('LT', 2),
    ('ADJECT1', 1), ('ADVERB', 1), ('SFX', 2), ('DESC', 1), ('QUIT', 0),
    ('END', 0), ('DONE', 0), ('OK', 0), ('ANYKEY', 0), ('SAVE', 1), ('LOAD', 1),
    ('DPRINT', 1), ('DISPLAY', 1), ('CLS', 0), ('DROPALL', 0), ('AUTOG', 0),
    ('AUTOD', 0), ('AUTOW', 0), ('AUTOR', 0), ('PAUSE', 1), ('SYNONYM', 2),
    ('GOTO', 1), ('MESSAGE', 1), ('REMOVE', 1), ('GET', 1), ('DROP', 1),
    ('WEAR', 1), ('DESTROY', 1), ('CREATE', 1), ('SWAP', 2), ('PLACE', 2),
    ('SET', 1), ('CLEAR', 1), ('PLUS', 2), ('MINUS', 2), ('LET', 2),
    ('NEWLINE', 0), ('PRINT', 1), ('SYSMESS', 1), ('ISAT', 2), ('SETCO', 1),
    ('SPACE', 0), ('HASAT', 1), ('HASNAT', 1), ('LISTOBJ', 0), ('EXTERN', 2),
    ('RAMSAVE', 0), ('RAMLOAD', 1), ('BEEP', 2), ('PAPER', 1), ('INK', 1),
    ('BORDER', 1), ('PREP', 1), ('NOUN2', 1), ('ADJECT2', 1), ('ADD', 2),
    ('SUB', 2), ('PARSE', 1), ('LISTAT', 1), ('PROCESS', 1), ('SAME', 2),
    ('MES', 1), ('WINDOW', 1), ('NOTEQ', 2), ('NOTSAME', 2), ('MODE', 1),
    ('WINAT', 2), ('TIME', 2), ('PICTURE', 1), ('DOALL', 1), ('MOUSE', 1),
    ('GFX', 2), ('ISNOTAT', 2), ('WEIGH', 2), ('PUTIN', 2), ('TAKEOUT', 2),
    ('NEWTEXT', 0), ('ABILITY', 2), ('WEIGHT', 1), ('RANDOM', 1), ('INPUT', 2),
    ('SAVEAT', 0), ('BACKAT', 0), ('PRINTAT', 2), ('WHATO', 0), ('CALL', 1),
    ('PUTO', 1), ('NOTDONE', 0), ('AUTOP', 1), ('AUTOT', 1), ('MOVE', 1),
    ('WINSIZE', 2), ('REDO', 0), ('CENTRE', 0), ('EXIT', 1), ('INKEY', 0),
    ('BIGGER', 2), ('SMALLER', 2), ('ISDONE', 0), ('ISNDONE', 0), ('SKIP', 1),
    ('RESTART', 0), ('TAB', 1), ('COPYOF', 2), ('dumb', 0), ('COPYOO', 2),
    ('dumb', 0), ('COPYFO', 2), ('dumb', 0), ('COPYFF', 2), ('COPYBF', 2),
    ('RESET', 0),
]
CONDICIONES = {'AT', 'NOTAT', 'ATGT', 'ATLT', 'PRESENT', 'ABSENT', 'WORN',
               'NOTWORN', 'CARRIED', 'NOTCARR', 'CHANCE', 'ZERO', 'NOTZERO',
               'EQ', 'GT', 'LT', 'ADJECT1', 'ADVERB', 'ISAT', 'ISNOTAT', 'HASAT',
               'HASNAT', 'PREP', 'NOUN2', 'ADJECT2', 'SAME', 'NOTEQ', 'NOTSAME',
               'ISDONE', 'ISNDONE', 'BIGGER', 'SMALLER', 'INKEY', 'QUIT'}


class ErrorDDB(Exception):
    pass


class DDB:
    def __init__(self, datos, base=None):
        self.d = bytes(datos)
        d = self.d
        if len(d) < 0x22 or d[0] not in (1, 2):
            raise ErrorDDB('no parece un .ddb de DAAD (version %r)' % (d[:1],))
        self.version = d[0]
        self.maquina = MAQUINAS.get(d[1] >> 4, '?%d' % (d[1] >> 4))
        self.idioma = IDIOMAS.get(d[1] & 15, '?')
        self.nulo = d[2]
        (self.nobj, self.nloc, self.nmsg, self.nsys, self.npro) = d[3:8]
        p = struct.unpack('<12H', d[8:32])
        if base is None:
            base = p[7] - 0x20          # vocabulario tras la cabecera
            if not (0 <= p[7] - base < len(d)):
                raise ErrorDDB('no puedo deducir la direccion de carga')
        self.base = base
        (self.p_tok, self.p_pro, self.p_obj, self.p_loc, self.p_msg, self.p_sys,
         self.p_con, self.p_voc, self.p_ini, self.p_opal, self.p_attr,
         self.p_fin) = p
        for q in p[:11]:
            if not (0 <= q - base < len(d)):
                raise ErrorDDB('puntero fuera del fichero: &%04X (base &%04X)'
                               % (q, base))
        self._tokens()
        self.vocabulario = self._vocab()
        self.objetos_txt = self._tabla(self.p_obj, self.nobj)
        self.localizaciones = self._tabla(self.p_loc, self.nloc)
        self.mensajes = self._tabla(self.p_msg, self.nmsg)
        self.sistema = self._tabla(self.p_sys, self.nsys)
        self.conexiones = self._conexiones()
        self.ini = [self.b(self.p_ini + i) for i in range(self.nobj)]
        self.obj_pal = [(self.b(self.p_opal + 2 * i), self.b(self.p_opal + 2 * i + 1))
                        for i in range(self.nobj)]
        self.obj_attr = [self.b(self.p_attr + i) for i in range(self.nobj)]
        self.procesos = [self._proceso(i) for i in range(self.npro)]

    # -- acceso por direccion --
    def b(self, a):
        return self.d[a - self.base]

    def w(self, a):
        o = a - self.base
        return self.d[o] | self.d[o + 1] << 8

    # -- textos --
    def _tokens(self):
        o = self.p_tok - self.base + 1        # el primer byte es una marca
        self.tokens, cur = [], bytearray()
        while o < len(self.d) and self.d[o] != 0 and len(self.tokens) < 256:
            c = self.d[o]
            o += 1
            ch = c & 0x7f
            cur += ESPECIALES.get(ch, chr(ch)).encode('latin-1', 'replace')
            if c & 0x80:
                self.tokens.append(cur.decode('latin-1'))
                cur = bytearray()

    def texto(self, a):
        o, s = a - self.base, []
        while o < len(self.d):
            c = self.d[o] ^ 0xff
            o += 1
            if c == 0x0a:
                break
            if c >= 128:
                k = c - 128
                s.append(self.tokens[k] if k < len(self.tokens) else '')
            elif c == 0x0d or c == 0x0c:
                s.append('\n')
            elif c in ESPECIALES:
                s.append(ESPECIALES[c])
            elif c == 0x7f:
                pass
            elif c >= 32:
                s.append(chr(c))
        return ''.join(s).replace('_', ' ')

    def _tabla(self, p, n):
        return [self.texto(self.w(p + 2 * i)) for i in range(n)]

    # -- vocabulario: (palabra, numero, tipo) --
    def _vocab(self):
        out, o = [], self.p_voc - self.base
        while o + 7 <= len(self.d) and self.d[o] != 0:
            pal = ''.join(ESPECIALES.get(c ^ 0xff, chr(c ^ 0xff))
                          for c in self.d[o:o + 5]).rstrip()
            out.append((pal, self.d[o + 5], self.d[o + 6]))
            o += 7
        return out

    def _conexiones(self):
        out = []
        for i in range(self.nloc):
            a, lst = self.w(self.p_con + 2 * i), []
            while self.b(a) != 0xff:
                lst.append((self.b(a), self.b(a + 1)))
                a += 2
            out.append(lst)
        return out

    # -- procesos: [(verbo, nombre, [(condact, indirecto, [params])])] --
    def _proceso(self, n):
        a, entradas = self.w(self.p_pro + 2 * n), []
        while self.b(a) != 0:
            v, nn, pc = self.b(a), self.b(a + 1), self.w(a + 2)
            a += 4
            entradas.append((v, nn, self._condacts(pc)))
        return entradas

    def _condacts(self, a):
        out = []
        for _ in range(512):
            c = self.b(a)
            a += 1
            if c == 0xff:
                return out
            ind, op = bool(c & 0x80), c & 0x7f
            nombre, np = CONDACTS[op]
            params = [self.b(a + i) for i in range(np)]
            a += np
            out.append((nombre, ind, params))
        raise ErrorDDB('una entrada de proceso no termina')

    # -- utilidades --
    def palabras(self, tipo, numero):
        return [p for p, n, t in self.vocabulario if t == tipo and n == numero]

    def resumen(self):
        uso = {}
        for pr in self.procesos:
            for _v, _n, cs in pr:
                for c, _i, _p in cs:
                    uso[c] = uso.get(c, 0) + 1
        return {
            'version': self.version, 'maquina': self.maquina,
            'idioma': self.idioma, 'base': self.base,
            'objetos': self.nobj, 'localizaciones': self.nloc,
            'mensajes': self.nmsg, 'sistema': self.nsys,
            'procesos': self.npro, 'vocabulario': len(self.vocabulario),
            'tokens': len(self.tokens),
            'entradas': sum(len(p) for p in self.procesos), 'condacts': uso,
        }


def lee(ruta, base=None):
    with open(ruta, 'rb') as f:
        return DDB(f.read(), base)
