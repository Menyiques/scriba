#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
z80.py — Simulador Z80 en Python puro, para verificar el motor nativo del CPC
sin emulador externo. No pretende ser ciclo-exacto; sí exacto en resultados y
flags para las instrucciones que usa el motor. Las llamadas al firmware del CPC
(CALL &BBxx) se pueden interceptar con hooks de Python para mockear E/S.

Uso basico:
    cpu = Z80(mem)                 # mem: bytearray de 65536
    cpu.pc = 0x4000
    cpu.hook_call = {0xBB5A: my_txt_output}
    cpu.run(start=0x4000)          # ejecuta hasta RET con la pila al nivel inicial
"""

# tablas de paridad y sign/zero
_PARITY = [0] * 256
for _i in range(256):
    _b = _i
    _p = 0
    while _b:
        _p ^= _b & 1
        _b >>= 1
    _PARITY[_i] = 0 if _p else 1     # 1 = par

FS, FZ, FH, FPV, FN, FC = 0x80, 0x40, 0x10, 0x04, 0x02, 0x01
F5, F3 = 0x20, 0x08                  # bits no documentados


class Z80:
    def __init__(self, mem=None):
        self.mem = mem if mem is not None else bytearray(65536)
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.ix = self.iy = 0
        self.sp = 0xC000
        self.pc = 0
        self.a_ = self.f_ = self.bc_ = self.de_ = self.hl_ = 0
        self.i = self.r = 0
        self.iff1 = self.iff2 = 0
        self.halted = False
        self.hook_call = {}          # {addr: fn(cpu)}  intercepta CALL/llamada a addr
        self.hook_rst = {}
        self.cycles = 0
        self.trace = False

    # ---- pares de 16 bits ----
    def _g(self, hi, lo): return (getattr(self, hi) << 8) | getattr(self, lo)
    def _s(self, hi, lo, v):
        setattr(self, hi, (v >> 8) & 0xFF); setattr(self, lo, v & 0xFF)

    @property
    def bc(self): return (self.b << 8) | self.c
    @bc.setter
    def bc(self, v): self.b = (v >> 8) & 0xFF; self.c = v & 0xFF
    @property
    def de(self): return (self.d << 8) | self.e
    @de.setter
    def de(self, v): self.d = (v >> 8) & 0xFF; self.e = v & 0xFF
    @property
    def hl(self): return (self.h << 8) | self.l
    @hl.setter
    def hl(self, v): self.h = (v >> 8) & 0xFF; self.l = v & 0xFF
    @property
    def af(self): return (self.a << 8) | self.f
    @af.setter
    def af(self, v): self.a = (v >> 8) & 0xFF; self.f = v & 0xFF

    # ---- memoria ----
    def rb(self, a): return self.mem[a & 0xFFFF]
    def wb(self, a, v): self.mem[a & 0xFFFF] = v & 0xFF
    def rw(self, a): return self.rb(a) | (self.rb(a + 1) << 8)
    def ww(self, a, v): self.wb(a, v & 0xFF); self.wb(a + 1, (v >> 8) & 0xFF)

    def _fetch(self):
        op = self.mem[self.pc]; self.pc = (self.pc + 1) & 0xFFFF; return op
    def _fw(self):
        v = self.rw(self.pc); self.pc = (self.pc + 2) & 0xFFFF; return v

    # ---- flags ----
    def _setf(self, bit, on):
        if on: self.f |= bit
        else: self.f &= ~bit & 0xFF

    def _szp(self, v, extra=0):
        v &= 0xFF
        f = extra
        if v & 0x80: f |= FS
        if v == 0: f |= FZ
        if _PARITY[v]: f |= FPV
        f |= v & (F5 | F3)
        self.f = f

    def _add8(self, a, b, carry=0):
        r = a + b + carry
        f = 0
        if (r & 0xFF) & 0x80: f |= FS
        if (r & 0xFF) == 0: f |= FZ
        if ((a & 0xF) + (b & 0xF) + carry) & 0x10: f |= FH
        if (~(a ^ b) & (a ^ r) & 0x80): f |= FPV
        if r & 0x100: f |= FC
        f |= (r & 0xFF) & (F5 | F3)
        self.f = f
        return r & 0xFF

    def _sub8(self, a, b, carry=0):
        r = a - b - carry
        f = FN
        if (r & 0xFF) & 0x80: f |= FS
        if (r & 0xFF) == 0: f |= FZ
        if ((a & 0xF) - (b & 0xF) - carry) & 0x10: f |= FH
        if ((a ^ b) & (a ^ r) & 0x80): f |= FPV
        if r & 0x100: f |= FC
        f |= (r & 0xFF) & (F5 | F3)
        self.f = f
        return r & 0xFF

    def _cp(self, b):
        a = self.a
        r = a - b
        f = FN
        if (r & 0xFF) & 0x80: f |= FS
        if (r & 0xFF) == 0: f |= FZ
        if ((a & 0xF) - (b & 0xF)) & 0x10: f |= FH
        if ((a ^ b) & (a ^ r) & 0x80): f |= FPV
        if r & 0x100: f |= FC
        f |= b & (F5 | F3)            # los bits 3/5 vienen del operando en CP
        self.f = f

    def _inc8(self, v):
        r = (v + 1) & 0xFF
        f = self.f & FC
        if r & 0x80: f |= FS
        if r == 0: f |= FZ
        if (v & 0xF) == 0xF: f |= FH
        if v == 0x7F: f |= FPV
        f |= r & (F5 | F3)
        self.f = f
        return r

    def _dec8(self, v):
        r = (v - 1) & 0xFF
        f = (self.f & FC) | FN
        if r & 0x80: f |= FS
        if r == 0: f |= FZ
        if (v & 0xF) == 0: f |= FH
        if v == 0x80: f |= FPV
        f |= r & (F5 | F3)
        self.f = f
        return r

    def _and(self, b):
        self.a &= b; self._szp(self.a, FH)
    def _or(self, b):
        self.a |= b; self._szp(self.a, 0)
    def _xor(self, b):
        self.a ^= b; self._szp(self.a, 0)

    def _add16(self, a, b):
        r = a + b
        f = self.f & (FS | FZ | FPV)
        if ((a & 0xFFF) + (b & 0xFFF)) & 0x1000: f |= FH
        if r & 0x10000: f |= FC
        f |= (r >> 8) & (F5 | F3)
        self.f = f
        return r & 0xFFFF

    # registro 8 por indice (B,C,D,E,H,L,(HL),A)
    _R8 = ['b', 'c', 'd', 'e', 'h', 'l', None, 'a']
    def _r8get(self, i):
        if i == 6: return self.rb(self.hl)
        return getattr(self, self._R8[i])
    def _r8set(self, i, v):
        if i == 6: self.wb(self.hl, v)
        else: setattr(self, self._R8[i], v & 0xFF)

    def push(self, v):
        self.sp = (self.sp - 2) & 0xFFFF; self.ww(self.sp, v)
    def pop(self):
        v = self.rw(self.sp); self.sp = (self.sp + 2) & 0xFFFF; return v

    def _jr(self, cond):
        e = self._fetch()
        if e >= 128: e -= 256
        if cond: self.pc = (self.pc + e) & 0xFFFF

    def _call_cond(self, cond):
        a = self._fw()
        if cond:
            if a in self.hook_call:
                self.hook_call[a](self); return
            self.push(self.pc); self.pc = a

    def step(self):
        op = self._fetch()
        m = self.mem
        # ---- bloque LD r,r' / HALT (0x40-0x7F) ----
        if 0x40 <= op <= 0x7F:
            if op == 0x76:
                self.halted = True; return
            dst = (op >> 3) & 7; src = op & 7
            self._r8set(dst, self._r8get(src)); return
        # ---- ALU A,r (0x80-0xBF) ----
        if 0x80 <= op <= 0xBF:
            v = self._r8get(op & 7); kind = (op >> 3) & 7
            if kind == 0: self.a = self._add8(self.a, v)
            elif kind == 1: self.a = self._add8(self.a, v, self.f & FC)
            elif kind == 2: self.a = self._sub8(self.a, v)
            elif kind == 3: self.a = self._sub8(self.a, v, self.f & FC)
            elif kind == 4: self._and(v)
            elif kind == 5: self._xor(v)
            elif kind == 6: self._or(v)
            else: self._cp(v)
            return
        # ---- resto por opcode ----
        h = _OPS.get(op)
        if h is None:
            raise RuntimeError('opcode no implementado: %02X en %04X' % (op, (self.pc - 1) & 0xFFFF))
        h(self)

    def run(self, start=None, max_steps=20_000_000):
        if start is not None: self.pc = start
        self.halted = False
        base_sp = self.sp
        n = 0
        while n < max_steps:
            n += 1
            op = self.mem[self.pc]
            if op == 0xC9 and self.sp == base_sp:      # RET al nivel inicial -> fin
                self.pc = (self.pc + 1) & 0xFFFF
                return n
            self.step()
            if self.halted:
                return n
        raise RuntimeError('limite de pasos (%d) — posible bucle infinito' % max_steps)


# ============ tabla de opcodes (unprefixed, salvo bloques 0x40-0xBF) ============
def _ld_bc_nn(c): c.bc = c._fw()
def _ld_de_nn(c): c.de = c._fw()
def _ld_hl_nn(c): c.hl = c._fw()
def _ld_sp_nn(c): c.sp = c._fw()

_OPS = {}
def _op(code):
    def d(fn): _OPS[code] = fn; return fn
    return d

_OPS[0x00] = lambda c: None                                   # NOP
_OPS[0x01] = _ld_bc_nn
_OPS[0x11] = _ld_de_nn
_OPS[0x21] = _ld_hl_nn
_OPS[0x31] = _ld_sp_nn
_OPS[0x02] = lambda c: c.wb(c.bc, c.a)                        # LD (BC),A
_OPS[0x12] = lambda c: c.wb(c.de, c.a)                        # LD (DE),A
_OPS[0x0A] = lambda c: setattr(c, 'a', c.rb(c.bc))            # LD A,(BC)
_OPS[0x1A] = lambda c: setattr(c, 'a', c.rb(c.de))            # LD A,(DE)
_OPS[0x22] = lambda c: c.ww(c._fw(), c.hl)                    # LD (nn),HL
_OPS[0x2A] = lambda c: setattr(c, 'hl', c.rw(c._fw()))        # LD HL,(nn)
_OPS[0x32] = lambda c: c.wb(c._fw(), c.a)                     # LD (nn),A
_OPS[0x3A] = lambda c: setattr(c, 'a', c.rb(c._fw()))         # LD A,(nn)

def _inc16(hi, lo):
    def f(c): setattr(c, hi+lo, (getattr(c, hi+lo) + 1) & 0xFFFF)
    return f
_OPS[0x03] = lambda c: setattr(c, 'bc', (c.bc + 1) & 0xFFFF)
_OPS[0x13] = lambda c: setattr(c, 'de', (c.de + 1) & 0xFFFF)
_OPS[0x23] = lambda c: setattr(c, 'hl', (c.hl + 1) & 0xFFFF)
_OPS[0x33] = lambda c: setattr(c, 'sp', (c.sp + 1) & 0xFFFF)
_OPS[0x0B] = lambda c: setattr(c, 'bc', (c.bc - 1) & 0xFFFF)
_OPS[0x1B] = lambda c: setattr(c, 'de', (c.de - 1) & 0xFFFF)
_OPS[0x2B] = lambda c: setattr(c, 'hl', (c.hl - 1) & 0xFFFF)
_OPS[0x3B] = lambda c: setattr(c, 'sp', (c.sp - 1) & 0xFFFF)

# INC/DEC r  (0x04,0x0C,...,0x3D) y LD r,n (0x06..0x3E)
for _i, _r in enumerate(['b', 'c', 'd', 'e', 'h', 'l', None, 'a']):
    def _mkinc(idx):
        return lambda c: c._r8set(idx, c._inc8(c._r8get(idx)))
    def _mkdec(idx):
        return lambda c: c._r8set(idx, c._dec8(c._r8get(idx)))
    def _mkldn(idx):
        return lambda c: c._r8set(idx, c._fetch())
    _OPS[0x04 + _i * 8] = _mkinc(_i)
    _OPS[0x05 + _i * 8] = _mkdec(_i)
    _OPS[0x06 + _i * 8] = _mkldn(_i)

_OPS[0x09] = lambda c: setattr(c, 'hl', c._add16(c.hl, c.bc))
_OPS[0x19] = lambda c: setattr(c, 'hl', c._add16(c.hl, c.de))
_OPS[0x29] = lambda c: setattr(c, 'hl', c._add16(c.hl, c.hl))
_OPS[0x39] = lambda c: setattr(c, 'hl', c._add16(c.hl, c.sp))

def _rlca(c):
    a = c.a; cy = (a >> 7) & 1; c.a = ((a << 1) | cy) & 0xFF
    c.f = (c.f & (FS | FZ | FPV)) | (FC if cy else 0) | (c.a & (F5 | F3))
def _rrca(c):
    a = c.a; cy = a & 1; c.a = ((a >> 1) | (cy << 7)) & 0xFF
    c.f = (c.f & (FS | FZ | FPV)) | (FC if cy else 0) | (c.a & (F5 | F3))
def _rla(c):
    a = c.a; cy = (a >> 7) & 1; c.a = ((a << 1) | (1 if c.f & FC else 0)) & 0xFF
    c.f = (c.f & (FS | FZ | FPV)) | (FC if cy else 0) | (c.a & (F5 | F3))
def _rra(c):
    a = c.a; cy = a & 1; c.a = ((a >> 1) | (0x80 if c.f & FC else 0)) & 0xFF
    c.f = (c.f & (FS | FZ | FPV)) | (FC if cy else 0) | (c.a & (F5 | F3))
_OPS[0x07] = _rlca; _OPS[0x0F] = _rrca; _OPS[0x17] = _rla; _OPS[0x1F] = _rra

def _cpl(c):
    c.a ^= 0xFF; c.f |= FH | FN; c.f = (c.f & ~(F5 | F3)) | (c.a & (F5 | F3))
def _scf(c):
    c.f = (c.f & (FS | FZ | FPV)) | FC | (c.a & (F5 | F3))
def _ccf(c):
    cy = c.f & FC
    c.f = (c.f & (FS | FZ | FPV)) | (FH if cy else 0) | (0 if cy else FC) | (c.a & (F5 | F3))
_OPS[0x2F] = _cpl; _OPS[0x37] = _scf; _OPS[0x3F] = _ccf

def _daa(c):
    a = c.a; corr = 0; cy = c.f & FC
    if (c.f & FH) or (a & 0x0F) > 9: corr |= 0x06
    if cy or a > 0x99: corr |= 0x60; cy = FC
    a = (a - corr) if (c.f & FN) else (a + corr)
    a &= 0xFF
    c._szp(a, (c.f & FN) | cy | ((c.a ^ a) & FH))
    c.a = a
_OPS[0x27] = _daa

# JR
_OPS[0x18] = lambda c: c._jr(True)
_OPS[0x20] = lambda c: c._jr(not (c.f & FZ))
_OPS[0x28] = lambda c: c._jr(bool(c.f & FZ))
_OPS[0x30] = lambda c: c._jr(not (c.f & FC))
_OPS[0x38] = lambda c: c._jr(bool(c.f & FC))
def _djnz(c):
    c.b = (c.b - 1) & 0xFF; c._jr(c.b != 0)
_OPS[0x10] = _djnz

# JP
_OPS[0xC3] = lambda c: setattr(c, 'pc', c._fw())
def _jp_cond(mask, want):
    def f(c):
        a = c._fw()
        if bool(c.f & mask) == want: c.pc = a
    return f
_OPS[0xC2] = _jp_cond(FZ, False); _OPS[0xCA] = _jp_cond(FZ, True)
_OPS[0xD2] = _jp_cond(FC, False); _OPS[0xDA] = _jp_cond(FC, True)
_OPS[0xE2] = _jp_cond(FPV, False); _OPS[0xEA] = _jp_cond(FPV, True)
_OPS[0xF2] = _jp_cond(FS, False); _OPS[0xFA] = _jp_cond(FS, True)
_OPS[0xE9] = lambda c: setattr(c, 'pc', c.hl)                # JP (HL)

# CALL / RET
_OPS[0xCD] = lambda c: c._call_cond(True)
_OPS[0xC4] = lambda c: c._call_cond(not (c.f & FZ))
_OPS[0xCC] = lambda c: c._call_cond(bool(c.f & FZ))
_OPS[0xD4] = lambda c: c._call_cond(not (c.f & FC))
_OPS[0xDC] = lambda c: c._call_cond(bool(c.f & FC))
_OPS[0xE4] = lambda c: c._call_cond(not (c.f & FPV))
_OPS[0xEC] = lambda c: c._call_cond(bool(c.f & FPV))
_OPS[0xF4] = lambda c: c._call_cond(not (c.f & FS))
_OPS[0xFC] = lambda c: c._call_cond(bool(c.f & FS))
_OPS[0xC9] = lambda c: setattr(c, 'pc', c.pop())            # RET
def _ret_cond(mask, want):
    def f(c):
        if bool(c.f & mask) == want: c.pc = c.pop()
    return f
_OPS[0xC0] = _ret_cond(FZ, False); _OPS[0xC8] = _ret_cond(FZ, True)
_OPS[0xD0] = _ret_cond(FC, False); _OPS[0xD8] = _ret_cond(FC, True)
_OPS[0xE0] = _ret_cond(FPV, False); _OPS[0xE8] = _ret_cond(FPV, True)
_OPS[0xF0] = _ret_cond(FS, False); _OPS[0xF8] = _ret_cond(FS, True)

# PUSH/POP
_OPS[0xC5] = lambda c: c.push(c.bc); _OPS[0xC1] = lambda c: setattr(c, 'bc', c.pop())
_OPS[0xD5] = lambda c: c.push(c.de); _OPS[0xD1] = lambda c: setattr(c, 'de', c.pop())
_OPS[0xE5] = lambda c: c.push(c.hl); _OPS[0xE1] = lambda c: setattr(c, 'hl', c.pop())
_OPS[0xF5] = lambda c: c.push(c.af); _OPS[0xF1] = lambda c: setattr(c, 'af', c.pop())

# ALU A,n
_OPS[0xC6] = lambda c: setattr(c, 'a', c._add8(c.a, c._fetch()))
_OPS[0xCE] = lambda c: setattr(c, 'a', c._add8(c.a, c._fetch(), c.f & FC))
_OPS[0xD6] = lambda c: setattr(c, 'a', c._sub8(c.a, c._fetch()))
_OPS[0xDE] = lambda c: setattr(c, 'a', c._sub8(c.a, c._fetch(), c.f & FC))
_OPS[0xE6] = lambda c: c._and(c._fetch())
_OPS[0xEE] = lambda c: c._xor(c._fetch())
_OPS[0xF6] = lambda c: c._or(c._fetch())
_OPS[0xFE] = lambda c: c._cp(c._fetch())

_OPS[0xEB] = lambda c: (setattr(c, 'de', c.hl ^ 0), c.__setattr__('hl', c.de)) and None  # placeholder, real abajo
def _ex_de_hl(c): c.de, c.hl = c.hl, c.de
_OPS[0xEB] = _ex_de_hl
def _ex_af(c): c.af, c.af_ = (c.af_ if hasattr(c, 'af_') else 0), c.af
_OPS[0x08] = _ex_af
def _exx(c):
    c.bc, c.bc_ = c.bc_, c.bc; c.de, c.de_ = c.de_, c.de; c.hl, c.hl_ = c.hl_, c.hl
_OPS[0xD9] = _exx
_OPS[0xF9] = lambda c: setattr(c, 'sp', c.hl)               # LD SP,HL
def _ex_sp_hl(c):
    t = c.rw(c.sp); c.ww(c.sp, c.hl); c.hl = t
_OPS[0xE3] = _ex_sp_hl

_OPS[0xF3] = lambda c: setattr(c, 'iff1', 0)               # DI
_OPS[0xFB] = lambda c: setattr(c, 'iff1', 1)               # EI

# RST
def _rst(addr):
    def f(c):
        if addr in c.hook_rst: c.hook_rst[addr](c); return
        c.push(c.pc); c.pc = addr
    return f
for _a in (0x00, 0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38):
    _OPS[0xC7 + _a] = _rst(_a)

# ---- prefijo CB ----
def _cb(c):
    op = c._fetch(); reg = op & 7; kind = (op >> 3) & 7; top = op >> 6
    v = c._r8get(reg)
    if top == 0:               # rotaciones/shifts
        cy = c.f & FC
        if kind == 0:   nc = (v >> 7) & 1; v = ((v << 1) | nc) & 0xFF          # RLC
        elif kind == 1: nc = v & 1; v = ((v >> 1) | (nc << 7)) & 0xFF          # RRC
        elif kind == 2: nc = (v >> 7) & 1; v = ((v << 1) | (1 if cy else 0)) & 0xFF  # RL
        elif kind == 3: nc = v & 1; v = ((v >> 1) | (0x80 if cy else 0)) & 0xFF      # RR
        elif kind == 4: nc = (v >> 7) & 1; v = (v << 1) & 0xFF                 # SLA
        elif kind == 5: nc = v & 1; v = ((v >> 1) | (v & 0x80)) & 0xFF         # SRA
        elif kind == 6: nc = (v >> 7) & 1; v = ((v << 1) | 1) & 0xFF           # SLL
        else:           nc = v & 1; v = (v >> 1) & 0xFF                        # SRL
        c._r8set(reg, v); c._szp(v, FC if nc else 0)
    elif top == 1:             # BIT b,r
        b = (op >> 3) & 7
        z = (v >> b) & 1
        f = (c.f & FC) | FH
        if not z: f |= FZ | FPV
        if b == 7 and z: f |= FS
        f |= v & (F5 | F3)
        c.f = f
    elif top == 2:             # RES b,r
        c._r8set(reg, v & ~(1 << ((op >> 3) & 7)) & 0xFF)
    else:                      # SET b,r
        c._r8set(reg, v | (1 << ((op >> 3) & 7)))
_OPS[0xCB] = _cb

# ---- prefijo ED ----
def _ed(c):
    op = c._fetch()
    if op == 0x44 or op == 0x4C or op == 0x54:           # NEG
        c.a = c._sub8(0, c.a)
    elif op == 0xB0:                                      # LDIR
        while True:
            c.wb(c.de, c.rb(c.hl))
            c.hl = (c.hl + 1) & 0xFFFF; c.de = (c.de + 1) & 0xFFFF
            c.bc = (c.bc - 1) & 0xFFFF
            if c.bc == 0: break
        c.f &= ~(FH | FN | FPV) & 0xFF
    elif op == 0xA0:                                      # LDI
        c.wb(c.de, c.rb(c.hl)); c.hl = (c.hl + 1) & 0xFFFF
        c.de = (c.de + 1) & 0xFFFF; c.bc = (c.bc - 1) & 0xFFFF
        c._setf(FPV, c.bc != 0); c._setf(FH, False); c._setf(FN, False)
    elif op == 0xB8:                                      # LDDR
        while True:
            c.wb(c.de, c.rb(c.hl))
            c.hl = (c.hl - 1) & 0xFFFF; c.de = (c.de - 1) & 0xFFFF
            c.bc = (c.bc - 1) & 0xFFFF
            if c.bc == 0: break
        c.f &= ~(FH | FN | FPV) & 0xFF
    elif op == 0xA8:                                      # LDD
        c.wb(c.de, c.rb(c.hl)); c.hl = (c.hl - 1) & 0xFFFF
        c.de = (c.de - 1) & 0xFFFF; c.bc = (c.bc - 1) & 0xFFFF
        c._setf(FPV, c.bc != 0); c._setf(FH, False); c._setf(FN, False)
    elif op in (0x43, 0x53, 0x63, 0x73):                 # LD (nn),rr
        rr = {0x43: 'bc', 0x53: 'de', 0x63: 'hl', 0x73: 'sp'}[op]
        c.ww(c._fw(), getattr(c, rr))
    elif op in (0x4B, 0x5B, 0x6B, 0x7B):                 # LD rr,(nn)
        rr = {0x4B: 'bc', 0x5B: 'de', 0x6B: 'hl', 0x7B: 'sp'}[op]
        setattr(c, rr, c.rw(c._fw()))
    elif op in (0x42, 0x52, 0x62, 0x72):                 # SBC HL,rr
        rr = {0x42: c.bc, 0x52: c.de, 0x62: c.hl, 0x72: c.sp}[op]
        cy = 1 if c.f & FC else 0; a = c.hl; r = a - rr - cy
        f = FN
        if (r & 0xFFFF) & 0x8000: f |= FS
        if (r & 0xFFFF) == 0: f |= FZ
        if ((a & 0xFFF) - (rr & 0xFFF) - cy) & 0x1000: f |= FH
        if ((a ^ rr) & (a ^ r) & 0x8000): f |= FPV
        if r & 0x10000: f |= FC
        c.hl = r & 0xFFFF; c.f = f
    elif op in (0x4A, 0x5A, 0x6A, 0x7A):                 # ADC HL,rr
        rr = {0x4A: c.bc, 0x5A: c.de, 0x6A: c.hl, 0x7A: c.sp}[op]
        cy = 1 if c.f & FC else 0; a = c.hl; r = a + rr + cy
        f = 0
        if (r & 0xFFFF) & 0x8000: f |= FS
        if (r & 0xFFFF) == 0: f |= FZ
        if ((a & 0xFFF) + (rr & 0xFFF) + cy) & 0x1000: f |= FH
        if (~(a ^ rr) & (a ^ r) & 0x8000): f |= FPV
        if r & 0x10000: f |= FC
        c.hl = r & 0xFFFF; c.f = f
    elif op == 0x47: c.i = c.a                            # LD I,A
    elif op == 0x4F: c.r = c.a                            # LD R,A
    elif op == 0x5F: c.a = c.r; c._szp(c.a, (c.f & FC) | (FPV if c.iff2 else 0))
    elif op == 0x57: c.a = c.i; c._szp(c.a, (c.f & FC) | (FPV if c.iff2 else 0))
    elif op in (0x46, 0x56, 0x5E, 0x4E, 0x66, 0x6E, 0x76, 0x7E):  # IM x
        pass
    elif op == 0x4D or op == 0x45:                        # RETI/RETN
        c.pc = c.pop()
    else:
        raise RuntimeError('ED %02X no implementado en %04X' % (op, (c.pc - 2) & 0xFFFF))
_OPS[0xED] = _ed

# ---- prefijos DD/FD (IX/IY) — subconjunto habitual ----
def _idx(regname):
    def _pref(c):
        op = c._fetch()
        ir = regname
        def base(): return getattr(c, ir)
        if op == 0x21: setattr(c, ir, c._fw())                       # LD IX,nn
        elif op == 0x22: c.ww(c._fw(), base())                       # LD (nn),IX
        elif op == 0x2A: setattr(c, ir, c.rw(c._fw()))               # LD IX,(nn)
        elif op == 0x23: setattr(c, ir, (base() + 1) & 0xFFFF)
        elif op == 0x2B: setattr(c, ir, (base() - 1) & 0xFFFF)
        elif op == 0xE5: c.push(base())                              # PUSH IX
        elif op == 0xE1: setattr(c, ir, c.pop())                     # POP IX
        elif op == 0xE9: c.pc = base()                               # JP (IX)
        elif op == 0x36:                                             # LD (IX+d),n
            d = c._fetch();
            if d >= 128: d -= 256
            n = c._fetch(); c.wb((base() + d) & 0xFFFF, n)
        elif op in (0x7E, 0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E):       # LD r,(IX+d)
            d = c._fetch()
            if d >= 128: d -= 256
            dst = (op >> 3) & 7; c._r8set(dst, c.rb((base() + d) & 0xFFFF))
        elif op in (0x77, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75):       # LD (IX+d),r
            d = c._fetch()
            if d >= 128: d -= 256
            src = op & 7; c.wb((base() + d) & 0xFFFF, c._r8get(src))
        elif op == 0x34:                                             # INC (IX+d)
            d = c._fetch()
            if d >= 128: d -= 256
            a = (base() + d) & 0xFFFF; c.wb(a, c._inc8(c.rb(a)))
        elif op == 0x35:                                             # DEC (IX+d)
            d = c._fetch()
            if d >= 128: d -= 256
            a = (base() + d) & 0xFFFF; c.wb(a, c._dec8(c.rb(a)))
        elif 0x80 <= op <= 0xBF:                                     # ALU A,(IX+d)
            d = c._fetch()
            if d >= 128: d -= 256
            v = c.rb((base() + d) & 0xFFFF); kind = (op >> 3) & 7
            if kind == 0: c.a = c._add8(c.a, v)
            elif kind == 1: c.a = c._add8(c.a, v, c.f & FC)
            elif kind == 2: c.a = c._sub8(c.a, v)
            elif kind == 3: c.a = c._sub8(c.a, v, c.f & FC)
            elif kind == 4: c._and(v)
            elif kind == 5: c._xor(v)
            elif kind == 6: c._or(v)
            else: c._cp(v)
        elif op == 0x09: setattr(c, ir, c._add16(base(), c.bc))
        elif op == 0x19: setattr(c, ir, c._add16(base(), c.de))
        elif op == 0x29: setattr(c, ir, c._add16(base(), base()))
        elif op == 0x39: setattr(c, ir, c._add16(base(), c.sp))
        else:
            raise RuntimeError('%s %02X no implementado' % (ir.upper(), op))
    return _pref
_OPS[0xDD] = _idx('ix')
_OPS[0xFD] = _idx('iy')


if __name__ == '__main__':
    # autotest minimo
    cpu = Z80()
    prog = [0x3E, 0x05, 0x06, 0x03, 0x80, 0x10, 0xFD, 0x76]  # LD A,5: LD B,3: (loop) ADD A,B? no
    cpu.mem[0:len(prog)] = bytes(prog)
    cpu.run(0)
    print('A =', cpu.a)
