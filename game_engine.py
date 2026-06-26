# -*- coding: utf-8 -*-
"""Motor nativo CPC - Fase 3b: localizaciones, parser, movimiento, mirar, objetos."""
import txtpack

ORG=0x4000; DB=0x8000; TXT=0xBB5A; KMWAIT=0xBB06
# mensajes de sistema (indices fijos)
SCANTGO=0; SEXITS=1; SNOUND=2; SSEE=3; STAKE=4; SDROP=5
SNOTHERE=6; SNOTCARR=7; SINVEN=8; SEMPTY=9; SNOTAKE=10; SDARK=11; SSCORE=12
SHEAVY=13
NSYS=14
CARRIED=255
NOWHERE=254
WORN=253                         # objeto puesto (sentinel en OBJLOC); CARRIED incluye WORN
CONTAINED=252                    # objeto dentro de un contenedor (ver OBJIN)
COP={'AT':0,'NOTAT':1,'PRESENT':2,'ABSENT':3,'CARRIED':4,'NOTCARR':5,'ZERO':6,'NOTZERO':7,
 'EQ':8,'GOTO':9,'MESSAGE':10,'MES':11,'GET':12,'DROP':13,'DESTROY':14,'CREATE':15,'PLACE':16,
 'SET':17,'CLEAR':18,'LET':19,'PLUS':20,'MINUS':21,'DONE':22,'DESC':23,'INVEN':24,'NEWLINE':25}
EOP={'END':0,'CONST':1,'VAR':2,'ADD':3,'SUB':4,'EQ':5,'NE':6,'LT':7,'GT':8,
 'AND':9,'OR':10,'NOT':11,'AT':12,'NOTAT':13,'ZERO':14,'NOTZERO':15,'DARK':16,
 'CARRIED':17,'PRESENT':18,'ABSENT':19,'NOTCARR':20,
 'ISAT':21,'CHANCE':22,'WORN':23,'NOTWORN':24,'VERB':25,'NOUN1':26,
 'TIMER':27,'HASOBJOPEN':28,'NOUN2':29}
# condacts extra: LETX (var,expr) e IF (expr -> salta cuerpo si falso)
COP_EXTRA={'LETX':26,'IF':27,'JMP':28,
 'INK':29,'PAPER':30,'BORDER':31,'PAUSE':32,'CLS':33,
 'WEAR':34,'REMOVE':35,'LIT':36,'UNLIT':37,'SCORE':38,
 'TSTART':39,'TSTOP':40,'TRESET':41,
 'OPEN':42,'CLOSE':43,'LOCK':44,'UNLOCK':45,'PUTIN':46,'TAKEOUT':47,
 'PLAY':48}
def enc_expr(toks):
    # toks: lista RPN como [('CONST',5),('VAR',0),('ADD',),...]  -> bytes (sin END)
    out=bytearray()
    for t in toks:
        out.append(EOP[t[0]])
        for a in t[1:]: out.append(a&0xFF)
    out.append(EOP['END'])
    return bytes(out)
def enc_condacts(clist):
    out=bytearray()
    for c in clist:
        out.append(COP[c[0]])
        for a in c[1:]: out.append(a & 0xFF)
    return bytes(out)

def build_game_db(messages, locations, vocab, objects, responses, startloc, sysverbs, width=40, load=DB, proc_before=b'', proc_after=b'', proc_onstart=b'', title_pal=b'', has_music=False, has_title=False, hdrbuf=0, imgbuf=0, loc_slot=b'', vall=0, font_acc=b'', timers=(), llevarmax=0, fx=b''):
    # Tokens 128..223 (96 max); los codigos 224..239 quedan para los acentos.
    dic=txtpack.build_dict(''.join(messages),96)
    exps=txtpack.expansions(dic); ntok=len(exps)
    toks=[txtpack.tokenize(m,dic) for m in messages]; nmsg=len(messages)
    # Dedup de vocabulario: cada entrada se graba como 4 letras + id + tipo y el
    # parser solo compara esas 4 primeras letras, asi que los alias que colapsan a
    # la misma (4 letras, id, tipo) son entradas identicas y redundantes. Quitarlas
    # no cambia el comportamiento y baja el contador (p.ej. PT: 336 -> 249).
    _seen=set(); _dv=[]
    for _w,_vid,_typ in vocab:
        _k=(_w.upper()[:4], _vid, _typ)
        if _k in _seen: continue
        _seen.add(_k); _dv.append((_w,_vid,_typ))
    vocab=_dv
    nloc=len(locations); nvocab=len(vocab); nobj=len(objects)
    if nvocab>65535:
        raise ValueError('Vocabulario CPC: %d palabras tras quitar duplicados '
                         '(maximo 65535).' % nvocab)
    if nloc>255:
        raise ValueError('CPC: %d localizaciones (maximo 255).' % nloc)
    if nobj>255:
        raise ValueError('CPC: %d objetos (maximo 255).' % nobj)
    HDR=80
    p=load+HDR
    dictidx=p; p+=ntok*2
    ddat=p; dptr=[]; dd=bytearray()
    for s in exps: dptr.append(ddat+len(dd)); dd+=s.encode('latin-1')+b'\x00'
    p=ddat+len(dd)
    msgidx=p; p+=nmsg*2
    mdat=p; mptr=[]; md=bytearray()
    for t in toks: mptr.append(mdat+len(md)); md+=bytes(t)+b'\x00'
    p=mdat+len(md)
    locidx=p; p+=nloc*2
    ldat=p; lptr=[]; lb=bytearray()
    for L in locations:
        lptr.append(ldat+len(lb)); lb.append(L['desc']&0xFF); lb.append((L['desc']>>8)&0xFF)
        ex=L['exits']; lb.append(len(ex))
        for vid,dest in ex: lb.append(vid&0xFF); lb.append(dest&0xFF)
    p=ldat+len(lb)
    vocaddr=p; p+=nvocab*6
    objname=p; p+=nobj*2
    objnoun=p; p+=nobj
    objloc=p; p+=nobj
    objfix=p; p+=nobj            # flag "fixed" (no cogible) por objeto
    locdark=p; p+=nloc           # 1 si la localizacion es oscura
    objlight=p; p+=nobj          # 1 si el objeto es fuente de luz
    objlit=p; p+=nobj            # 1 si la fuente de luz esta encendida (inicial)
    resptab=p
    rbytes=bytearray()
    for (vb,nn,cl) in responses:
        cb=bytes(cl) if isinstance(cl,(bytes,bytearray)) else enc_condacts(cl)
        rbytes.append(vb&0xFF); rbytes.append(nn&0xFF); rbytes.append(len(cb)&0xFF); rbytes+=cb
    rbytes.append(255)
    p+=len(rbytes)
    def mkblk(b): return (bytes([len(b)&0xFF,(len(b)>>8)&0xFF])+bytes(b)) if b else b''
    bb=mkblk(proc_before); ab=mkblk(proc_after); ob=mkblk(proc_onstart)
    before_addr = p if proc_before else 0; p+=len(bb)
    after_addr  = p if proc_after else 0;  p+=len(ab)
    onstart_addr= p if proc_onstart else 0; p+=len(ob)
    palbytes=(bytes(title_pal)+bytes(16))[:16] if title_pal else b''
    pal_addr = p if palbytes else 0; p+=len(palbytes)
    locslot_addr = p if loc_slot else 0; p+=len(loc_slot)
    # Tabla vid -> nombre a mostrar (la palabra mas larga de ese vid). Sirve para
    # imprimir las salidas con el nombre completo (NORTE, OESTE...) en vez de la
    # palabra de 4 letras del parser. Indexada por vid (0..maxvid), 0 = sin nombre.
    # Nombres de salida igual que en la version de Spectrum (spectrum_export):
    # letra unica para los puntos cardinales y "Subir"/"Bajar" para arriba/abajo.
    # Los vids de direccion son fijos 1..6 = N, S, E, O, arriba, abajo.
    vid_name = {1: 'N', 2: 'S', 3: 'E', 4: 'O', 5: 'Subir', 6: 'Bajar'}
    maxvid = max(vid_name) if vid_name else 0
    nvname = maxvid + 1
    vnameidx_addr = p; p += nvname*2
    vname_dat_addr = p
    vname_ptr = []; vnd = bytearray()
    for v in range(nvname):
        if v in vid_name:
            vname_ptr.append(vname_dat_addr + len(vnd))
            vnd += vid_name[v].encode('latin-1') + b'\x00'
        else:
            vname_ptr.append(0)
    p = vname_dat_addr + len(vnd)
    font_acc_addr = p if font_acc else 0; p += len(font_acc)
    # ── temporizadores ──
    nt = len(timers)
    if nt > 16:
        raise ValueError('CPC: %d temporizadores (maximo 16).' % nt)
    tdur_addr = p; p += nt
    tloop_addr = p; p += nt
    tactsrc_addr = p; p += nt
    texp_blocks = [mkblk(bytes(t.get('expire', b''))) for t in timers]
    texp_ptr = []
    for blk in texp_blocks:
        if blk:
            texp_ptr.append(p); p += len(blk)
        else:
            texp_ptr.append(0)
    texptab_addr = p if nt else 0; p += nt*2
    # ── contenedores (estado inicial; se copia a RAM en init) ──
    objopen_a = p; p += nobj
    objlock_a = p; p += nobj
    objin_a   = p; p += nobj
    objweight_a = p; p += nobj
    # ── efectos de sonido FX (blob AY: [nfx][offsets][bloques]); 0 si no hay ──
    fx_addr = p if fx else 0; p += len(fx)
    out=bytearray()
    def w16(v): out.append(v&0xFF); out.append((v>>8)&0xFF)
    w16(dictidx); w16(msgidx); w16(locidx); w16(vocaddr)          # 8
    out.append(width); out.append(ntok); w16(nmsg)               # 12
    out.append(nloc); out.append(nvocab & 0xFF); out.append(startloc)   # 15 (nvocab byte bajo)
    out.append(sysverbs['look']); out.append(sysverbs['quit'])   # 17
    out.append(nobj)                                             # 18
    w16(objname); w16(objnoun); w16(objloc)                      # 24
    out.append(sysverbs['get']); out.append(sysverbs['drop'])    # 26
    out.append(sysverbs['inven']); out.append(sysverbs['exam'])  # 28
    w16(resptab)                                                 # 30
    w16(before_addr); w16(after_addr); w16(onstart_addr)         # 36
    w16(pal_addr)                                                # 38
    out.append(1 if has_music else 0)                            # 39
    out.append(1 if has_title else 0)                            # 40
    w16(hdrbuf); w16(imgbuf)                                      # 44
    w16(locslot_addr)                                            # 46
    w16(vnameidx_addr)                                          # 48
    out.append(vall & 0xFF)                                     # 49 (nombre "TODO")
    w16(font_acc_addr)                                          # 51 (bitmaps acentos)
    w16(objfix)                                                 # 53 (flags "fixed")
    w16(locdark)                                                # 55 (oscuridad loc)
    w16(objlight)                                               # 57 (fuente de luz)
    w16(objlit)                                                 # 59 (encendida, inicial)
    out.append(nt)                                              # 60 (nº timers)
    w16(tdur_addr); w16(tloop_addr); w16(tactsrc_addr)          # 66
    w16(texptab_addr)                                           # 68 (tabla on_expire)
    w16(objopen_a); w16(objlock_a); w16(objin_a)               # 74 (contenedores)
    w16(objweight_a)                                            # 76 (peso por objeto)
    out.append(llevarmax & 0xFF)                                # 77 (flag LLEVAR_MAX)
    w16(fx_addr)                                                # 79 (blob FX por AY)
    out.append((nvocab>>8)&0xFF)                                # 80 (nvocab byte alto)
    assert len(out)==HDR, len(out)
    for x in dptr: w16(x)
    out+=dd
    for x in mptr: w16(x)
    out+=md
    for x in lptr: w16(x)
    out+=lb
    for word,vid,typ in vocab:
        w=(word.upper()[:4]+'    ')[:4]
        for ch in w: out.append(ord(ch)&0xFF)
        out.append(vid&0xFF); out.append(typ&0xFF)
    for o in objects: out.append(o['name']&0xFF); out.append((o['name']>>8)&0xFF)
    for o in objects: out.append(o['noun']&0xFF)
    for o in objects: out.append(o['loc']&0xFF)
    for o in objects: out.append(o.get('fixed',0)&0xFF)
    for L in locations: out.append(1 if L.get('dark') else 0)
    for o in objects: out.append(1 if o.get('light') else 0)
    for o in objects: out.append(1 if o.get('lit') else 0)
    out+=rbytes
    out+=bb; out+=ab; out+=ob; out+=palbytes; out+=bytes(loc_slot)
    for x in vname_ptr: w16(x)
    out+=vnd
    out+=bytes(font_acc)
    for t in timers: out.append(t.get('dur',0)&0xFF)
    for t in timers: out.append(t.get('loop',0)&0xFF)
    for t in timers: out.append(t.get('active',0)&0xFF)
    for blk in texp_blocks: out+=blk
    for x in texp_ptr: w16(x)
    for o in objects: out.append(1 if o.get('open') else 0)
    for o in objects: out.append(1 if o.get('locked') else 0)
    for o in objects: out.append(o.get('incont',0)&0xFF)
    for o in objects: out.append(o.get('weight',0)&0xFF)
    out+=bytes(fx)
    return bytes(out), dict(load=load,ntok=ntok,nmsg=nmsg,nloc=nloc,nvocab=nvocab,nobj=nobj,ntimers=nt,size=len(out))

ENGINE_ASM = r'''
        org   ORIGIN

start:  call  init
        call  show_title
        call  setup_acc        ; define los acentos español/portugués (CPC matrix)
        ; Sin precarga: cada sala se carga de disco la 1a vez y se cachea en banco
        ; (show_loc_image); al volver es instantanea. Asi no hay espera al arrancar.
        ld    hl,(onstartp)
        call  run_proc
        call  describe
        call  mainloop
        ret

init:   ld    hl,(DBB+0)
        ld    (dictidx),hl
        ld    hl,(DBB+2)
        ld    (msgidx),hl
        ld    hl,(DBB+4)
        ld    (locidx),hl
        ld    hl,(DBB+6)
        ld    (vocabp),hl
        ld    a,(DBB+8)
        ld    (width),a
        ld    a,(DBB+13)
        ld    (nvocab),a          ; nvocab byte bajo
        ld    a,(DBB+79)
        ld    (nvocab+1),a        ; nvocab byte alto (vocabulario 16-bit)
        ld    a,(DBB+12)
        ld    (nloc),a
        ld    a,(DBB+14)
        ld    (curloc),a
        ld    a,(DBB+15)
        ld    (vlook),a
        ld    a,(DBB+16)
        ld    (vquit),a
        ld    a,(DBB+17)
        ld    (nobj),a
        ld    hl,(DBB+18)
        ld    (objnamep),hl
        ld    hl,(DBB+20)
        ld    (objnounp),hl
        ld    hl,(DBB+22)
        ld    (objlocsrc),hl
        ld    hl,(DBB+51)
        ld    (objfixp),hl
        ld    hl,(DBB+55)
        ld    (locdarkp),hl
        ld    hl,(DBB+57)
        ld    (objlightp),hl
        ld    a,(DBB+59)
        ld    (ntimers),a
        ld    hl,(DBB+60)
        ld    (tdurp),hl
        ld    hl,(DBB+62)
        ld    (tloopp),hl
        ld    hl,(DBB+64)
        ld    (tactsrcp),hl
        ld    hl,(DBB+66)
        ld    (texptabp),hl
        ld    hl,(DBB+68)
        ld    (objopensrc),hl
        ld    hl,(DBB+70)
        ld    (objlocksrc),hl
        ld    hl,(DBB+72)
        ld    (objinsrc),hl
        ld    hl,(DBB+74)
        ld    (objweightp),hl
        ld    a,(DBB+76)
        ld    (llevarmax),a
        ld    hl,(DBB+77)
        ld    (fxp),hl
        ld    a,(DBB+24)
        ld    (vget),a
        ld    a,(DBB+25)
        ld    (vdrop),a
        ld    a,(DBB+26)
        ld    (vinven),a
        ld    a,(DBB+27)
        ld    (vexam),a
        ld    hl,(DBB+28)
        ld    (respp),hl
        ld    hl,(DBB+30)
        ld    (beforep),hl
        ld    hl,(DBB+32)
        ld    (afterp),hl
        ld    hl,(DBB+34)
        ld    (onstartp),hl
        ld    hl,(DBB+36)
        ld    (titlepal),hl
        ld    a,(DBB+38)
        ld    (hasmusic),a
        ld    a,(DBB+39)
        ld    (hastitle),a
        ld    hl,(DBB+40)
        ld    (hdrbufp),hl
        ld    hl,(DBB+42)
        ld    (imgbufp),hl
        ld    hl,(DBB+44)
        ld    (locslotp),hl
        ld    hl,(DBB+46)
        ld    (vnamep),hl
        ld    a,(DBB+48)
        ld    (vall),a        ; nombre que significa "TODO"
        ld    hl,(DBB+49)
        ld    (faccp),hl      ; bitmaps de acentos (o 0 si no hay)
        call  detect128       ; pone has128=1 si hay RAM extra (CPC 6128)
        ld    hl,FLAGS
        ld    b,64
icf_l:  ld    (hl),0
        inc   hl
        djnz  icf_l
        ld    a,(nobj)
        or    a
        jr    z,init_d
        ld    b,a
        ld    hl,(objlocsrc)
        ld    de,OBJLOC
ic_l:   ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  ic_l
        ld    a,(nobj)        ; copia OBJLIT (estado de encendido) a RAM
        ld    b,a
        ld    hl,(DBB+59)
        ld    de,OBJLIT
icl2_l: ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  icl2_l
        ld    a,(nobj)       ; copia estado de contenedores a RAM
        ld    b,a
        ld    hl,(objopensrc)
        ld    de,OBJOPEN
ico_l:  ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  ico_l
        ld    a,(nobj)
        ld    b,a
        ld    hl,(objlocksrc)
        ld    de,OBJLOCK
ick_l:  ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  ick_l
        ld    a,(nobj)
        ld    b,a
        ld    hl,(objinsrc)
        ld    de,OBJIN
icn_l:  ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  icn_l
        ld    a,(ntimers)    ; TCUR = duracion ; TACT = activo inicial
        or    a
        jr    z,init_d
        ld    b,a
        ld    hl,(tdurp)
        ld    de,TCUR
ict_l:  ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  ict_l
        ld    a,(ntimers)
        ld    b,a
        ld    hl,(tactsrcp)
        ld    de,TACT
ica_l:  ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        djnz  ica_l
init_d: xor   a
        ld    (quitf),a
        ld    (col),a
        ret

mainloop:
        call  newline
        ld    a,62
        call  char_raw
        ld    a,32
        call  char_raw
        call  read_line
        call  parse
        ld    hl,(beforep)
        call  run_proc
        call  dispatch
        ld    hl,(afterp)
        call  run_proc
        call  tick_timers
        ld    a,(quitf)
        or    a
        jr    z,mainloop
        ret

dispatch:
        call  run_response
        or    a
        ret   nz
        ld    a,(verbid)
        ld    b,a
        or    a
        jp    z,d_nound       ; sin verbo reconocido -> "No entiendo"
        ld    a,(vquit)
        cp    b
        jr    nz,d_nq
        ld    a,1
        ld    (quitf),a
        ret
d_nq:   ld    a,(vlook)
        cp    b
        jr    nz,d_ngt
        call  describe
        ret
d_ngt:  ld    a,(vget)
        cp    b
        jr    nz,d_ndr
        call  do_get
        ret
d_ndr:  ld    a,(vdrop)
        cp    b
        jr    nz,d_niv
        call  do_drop
        ret
d_niv:  ld    a,(vinven)
        cp    b
        jr    nz,d_nex
        call  do_inven
        ret
d_nex:  ld    a,(vexam)
        cp    b
        jr    nz,d_mov
        call  do_exam
        ret
d_mov:  ld    a,b
        or    a
        jr    z,d_nound
        ld    a,(vtype)
        cp    2
        jr    nz,d_nound
        call  try_move
        or    a
        jr    z,d_cantgo
        call  describe
        ret
d_cantgo:
        call  newline
        ld    de,SCANTGO
        call  print_msg
        ret
d_nound:
        call  newline
        ld    de,SNOUND
        call  print_msg
        ret

describe:
        call  show_loc_image
        call  newline
        call  is_dark
        or    a
        jp    nz,d_dark
        ld    a,(curloc)
        call  loc_record
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        push  hl
        call  print_msg
        call  newline
        ld    de,SEXITS
        call  print_msg
        pop   hl
        ld    a,(hl)
        inc   hl
        ld    b,a
        or    a
        jr    z,d_noex
d_ex:   ld    a,(hl)
        inc   hl
        push  hl
        push  bc
        call  print_word_id
        pop   bc
        pop   hl
        inc   hl
        djnz  d_ex
d_noex: jp    list_here
d_dark: ld    de,SDARK
        call  print_msg
        ret

; ---- show_loc_image: pinta la imagen de la localizacion + ventana de texto ----
; Camino rapido: con 128K y slot de cache asignado, la imagen se sirve desde un
; banco extra (sin disco). Si no, se carga de disco (PIC<n>.SCR) como siempre.
show_loc_image:
        ld    a,(has128)
        or    a
        jr    z,sli_disc       ; sin RAM extra -> disco
        ld    hl,(locslotp)
        ld    a,h
        or    l
        jr    z,sli_disc       ; sin tabla -> disco
        ld    a,(curloc)
        ld    e,a
        ld    d,0
        add   hl,de
        ld    a,(hl)           ; slot de cache de esta localizacion
        cp    255
        jr    z,sli_disc       ; no cacheable -> disco
        ld    (curslot),a
        call  is_pop
        jr    nc,sli_fill      ; aun no poblado -> cargar de disco y guardar
        call  bank2buf         ; cacheada: banco -> imgbuf (sin disco)
        jr    sli_haveimg
sli_fill:
        call  sli_loadfile     ; 1a vez: disco -> imgbuf
        jr    nc,sli_noimg
        call  buf2bank         ; ...y la copia al banco extra
        call  set_pop
        jr    sli_haveimg
sli_disc:
        call  sli_loadfile
        jr    nc,sli_noimg
sli_haveimg:
        call  depack
        ld    h,0             ; TXT WIN ENABLE: H=izq L=arriba D=der E=abajo
        ld    l,8             ; ventana de texto en filas 8..24 (imagen en 0..7)
        ld    d,79
        ld    e,24
        call  TXTWIN
        jr    sli_cls
sli_noimg:
        ld    h,0
        ld    l,0
        ld    d,79
        ld    e,24
        call  TXTWIN
sli_cls:
        ld    a,12
        call  TXTO
        xor   a
        ld    (col),a
        ret

; sli_loadfile: PIC<curloc>.SCR -> imgbuf via CAS IN. CF=1 ok, CF=0 no existe.
; sli_load_a: igual pero la localizacion va en A (para precarga de contiguas).
sli_loadfile:
        ld    a,(curloc)
sli_load_a:
        ld    b,0
slf_d:  cp    10
        jr    c,slf_dd
        sub   10
        inc   b
        jr    slf_d
slf_dd: push  af
        ld    a,b
        add   a,48
        ld    (fpic+3),a
        pop   af
        add   a,48
        ld    (fpic+4),a
        ld    b,9
        ld    hl,fpic
        ld    de,(hdrbufp)
        call  CASOPEN
        ret   nc
        ld    hl,(imgbufp)
        call  CASDIR
        call  CASCLOSE
        scf
        ret
fpic:   defb "PIC00.SCR"

; ---- cache de imagenes en bancos extra (CPC 6128) ----
; bank2buf: copia 5120 bytes del slot (banco,offset) a imgbuf.
bank2buf:
        ld    a,(curslot)
        call  slotinfo        ; A=config banco, HL=offset(ventana &4000-&7FFF)
        di
        ld    b,&7F
        ld    c,a
        defb  &ED,&49         ; out (c),c  -> pagina el banco extra
        ld    de,(imgbufp)
        ld    bc,5120
        ldir
        ld    bc,&7FC0
        defb  &ED,&49         ; out (c),c  -> RAM normal
        ei
        ret
; buf2bank: copia 5120 bytes de imgbuf al slot (banco,offset).
buf2bank:
        ld    a,(curslot)
        call  slotinfo
        di
        ex    de,hl           ; DE = destino (ventana)
        ld    b,&7F
        ld    c,a
        defb  &ED,&49         ; out (c),c
        ld    hl,(imgbufp)
        ld    bc,5120
        ldir
        ld    bc,&7FC0
        defb  &ED,&49
        ei
        ret
; slotinfo: A=slot -> A=config banco, HL=offset. slottab = 3 bytes/entrada.
slotinfo:
        ld    l,a
        ld    h,0
        ld    e,a
        ld    d,h
        add   hl,hl
        add   hl,de           ; HL = slot*3
        ld    de,slottab
        add   hl,de
        ld    a,(hl)          ; config del banco (&C4..&C7)
        inc   hl
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ex    de,hl           ; HL = offset en la ventana
        ret
slottab:
        defb  &C4
        defw  &4000
        defb  &C4
        defw  &5400
        defb  &C4
        defw  &6800
        defb  &C5
        defw  &4000
        defb  &C5
        defw  &5400
        defb  &C5
        defw  &6800
        defb  &C6
        defw  &4000
        defb  &C6
        defw  &5400
        defb  &C6
        defw  &6800
        defb  &C7
        defw  &4000
        defb  &C7
        defw  &5400
        defb  &C7
        defw  &6800
; is_pop: CF=1 si el slot (curslot) ya esta poblado.
is_pop:
        ld    a,(curslot)
        call  popmask         ; HL->byte del bitmap, A=mascara
        and   (hl)
        scf
        ret   nz
        or    a
        ret
; set_pop: marca el slot (curslot) como poblado.
set_pop:
        ld    a,(curslot)
        call  popmask
        or    (hl)
        ld    (hl),a
        ret
; popmask: A=slot -> HL=&populated+slot/8, A=1<<(slot%8).
popmask:
        ld    b,a
        srl   a
        srl   a
        srl   a
        ld    l,a
        ld    h,0
        ld    de,populated
        add   hl,de
        ld    a,b
        and   7
        ld    b,a
        ld    a,1
        inc   b
pm_l:   dec   b
        jr    z,pm_done
        add   a,a
        jr    pm_l
pm_done:
        ret
; detect128: has128=1 si hay RAM extra de 128K (escribe/lee bancos 4 y 5 en
; &4000 con salva/restaura de la base para no corromper la DB en maquinas de 64K).
detect128:
        di
        ld    a,(&4000)
        push  af
        ld    bc,&7FC4
        defb  &ED,&49
        ld    a,&AA
        ld    (&4000),a
        ld    bc,&7FC5
        defb  &ED,&49
        ld    a,&55
        ld    (&4000),a
        ld    bc,&7FC4
        defb  &ED,&49
        ld    a,(&4000)
        ld    e,a
        ld    bc,&7FC0
        defb  &ED,&49
        pop   af
        ld    (&4000),a
        ei
        ld    a,e
        cp    &AA            ; banco4 conserva &AA -> bancos distintos -> 128K
        ld    a,0
        jr    nz,d128_no
        inc   a
d128_no:
        ld    (has128),a
        ret

; preload_cache: con 128K, carga de disco todas las imagenes con slot asignado y
; las deja en sus bancos, para que esas salas salgan al instante desde la 1a vez.
; Muestra "Preparando..." y un punto por imagen. Preserva curloc.
preload_cache:
        ld    a,(has128)
        or    a
        ret   z               ; sin RAM extra: nada que precargar
        ld    a,(curloc)
        ld    (plc_save),a     ; salva la localizacion inicial
        ld    a,2
        call  SCRMODE          ; modo 2, limpia pantalla
        ld    hl,plc_txt
plc_pr: ld    a,(hl)
        or    a
        jr    z,plc_st
        inc   hl
        call  TXTO
        jr    plc_pr
plc_st: xor   a
        ld    (plc_i),a
plc_loop:
        ld    a,(plc_i)
        ld    hl,nloc
        cp    (hl)
        jr    nc,plc_end       ; recorridas todas las localizaciones
        ld    hl,(locslotp)
        ld    e,a
        ld    d,0
        add   hl,de
        ld    a,(hl)           ; slot de esta localizacion
        cp    255
        jr    z,plc_next       ; no cacheable
        ld    (curslot),a
        call  is_pop
        jr    c,plc_next       ; ya poblado
        ld    a,(plc_i)
        ld    (curloc),a
        call  sli_loadfile     ; disco -> imgbuf
        jr    nc,plc_next      ; sin fichero
        call  buf2bank         ; imgbuf -> banco
        call  set_pop
        ld    a,46             ; '.' de progreso
        call  TXTO
plc_next:
        ld    a,(plc_i)
        inc   a
        ld    (plc_i),a
        jr    plc_loop
plc_end:
        ld    a,(plc_save)
        ld    (curloc),a       ; restaura la localizacion inicial
        ret
plc_txt: defb "Preparando...",0

; ---- precarga predictiva de las salas contiguas (mientras se lee/teclea) ----
; prefetch_init: prepara la lista de salidas de la localizacion actual.
prefetch_init:
        ld    a,(has128)
        or    a
        jr    z,pfi_none      ; sin RAM extra -> nada que cachear
        ld    a,(curloc)
        call  loc_record      ; HL -> registro de la localizacion
        inc   hl
        inc   hl              ; saltar el mensaje de descripcion (2 bytes)
        ld    a,(hl)          ; nº de salidas
        ld    (pf_n),a
        inc   hl
        ld    (pf_exits),hl   ; HL -> pares (verbo,destino)
        xor   a
        ld    (pf_i),a
        ret
pfi_none:
        xor   a
        ld    (pf_n),a
        ret
; prefetch_one: carga en banco UNA imagen contigua pendiente (o nada). Preserva
; HL y BC para no romper el editor de linea.
prefetch_one:
        push  hl
        push  bc
pfo_l:  ld    a,(pf_i)
        ld    hl,pf_n
        cp    (hl)
        jr    nc,pfo_e        ; recorridas todas las salidas
        ld    l,a
        ld    h,0
        add   hl,hl           ; pf_i*2 (cada salida = verbo+destino)
        ld    de,(pf_exits)
        add   hl,de
        inc   hl              ; -> byte de destino
        ld    a,(hl)
        ld    (picloc),a      ; destino a precargar
        ld    a,(pf_i)
        inc   a
        ld    (pf_i),a
        ld    a,(picloc)      ; slot = loc_slot[destino]
        ld    hl,(locslotp)
        ld    e,a
        ld    d,0
        add   hl,de
        ld    a,(hl)
        cp    255
        jr    z,pfo_l         ; no cacheable -> siguiente salida
        ld    (curslot),a
        call  is_pop
        jr    c,pfo_l         ; ya cacheada -> siguiente salida
        ld    a,(picloc)
        call  sli_load_a      ; PIC<destino> -> imgbuf
        jr    nc,pfo_e        ; sin fichero
        call  buf2bank        ; -> banco
        call  set_pop
pfo_e:  pop   bc
        pop   hl
        ret

; ---- setup_acc: define los 16 acentos (codigos 224-239) como caracteres de
; usuario del CPC. faccp -> 128 bytes de bitmaps (16 x 8). MTABLE = tabla en RAM.
; setup_acc: redefine SOLO los acentos (224-239); el texto normal usa el font de
; la ROM del CPC (mas grueso). Los glifos de acento vienen ya engrosados a 2px
; desde el build (nativecc) para casar con el grosor de la ROM.
setup_acc:
        ld    hl,(faccp)
        ld    a,h
        or    l
        ret   z                ; sin font -> nada
        ld    de,224           ; primer caracter redefinible
        ld    hl,MTABLE        ; tabla de matrices (RAM central, &8000)
        call  TXTMTABLE        ; TXT SET M TABLE (DE=primer char, HL=tabla)
        ld    hl,(faccp)       ; 16 glifos de acento (8 bytes c/u)
        ld    (accptr),hl
        ld    a,224
        ld    (acccode),a
        ld    b,16
sac_loop:
        push  bc
        ld    a,(acccode)
        ld    hl,(accptr)
        call  TXTMATRIX        ; TXT SET MATRIX (A=char, HL=matriz 8 bytes)
        ld    hl,(accptr)
        ld    de,8
        add   hl,de
        ld    (accptr),hl
        ld    a,(acccode)
        inc   a
        ld    (acccode),a
        pop   bc
        djnz  sac_loop
        ret

depack: ld    hl,(imgbufp)
        ld    de,&C000
dpk_l:  ld    a,(hl)
        inc   hl
        bit   7,a
        jr    z,dpk_lit
        neg
        inc   a
        ld    b,a
        ld    a,(hl)
        inc   hl
dpk_run: ld   (de),a
        inc   de
        dec   b
        jr    nz,dpk_run
        ld    a,d
        or    e
        jr    nz,dpk_l
        ret
dpk_lit: inc  a
        ld    b,a
dpk_ll: ld    a,(hl)
        inc   hl
        ld    (de),a
        inc   de
        dec   b
        jr    nz,dpk_ll
        ld    a,d
        or    e
        jr    nz,dpk_l
        ret

; ---- list_here: lista objetos en curloc ("Aqui ves: ...") ----
list_here:
        ld    a,(nobj)
        or    a
        ret   z
        ld    b,a
        ld    hl,OBJLOC
        ld    a,(curloc)
        ld    c,a
        ld    d,0
lh_c:   ld    a,(hl)
        cp    c
        jr    nz,lh_cn
        inc   d
lh_cn:  inc   hl
        djnz  lh_c
        ld    a,d
        or    a
        ret   z
        call  newline
        ld    de,SSEE
        call  print_msg
        ld    a,(nobj)
        ld    b,a
        xor   a
        ld    (oidx),a
lh_l:   ld    a,(oidx)
        call  objloc_get
        ld    c,a
        ld    a,(curloc)
        cp    c
        jr    nz,lh_sk
        push  bc
        ld    a,(oidx)
        call  print_objname
        ld    a,32
        call  char_raw
        pop   bc
lh_sk:  ld    a,(oidx)
        inc   a
        ld    (oidx),a
        djnz  lh_l
        ret

; ---- do_get ----
do_get: ld    a,(nounid)
        or    a
        jp    z,dg_no
        ld    hl,vall
        cp    (hl)
        jp    z,dg_all        ; COGER TODO
        ld    (tnoun),a
        ld    a,(nobj)
        or    a
        jr    z,dg_no
        ld    b,a
        xor   a
        ld    (oidx),a
dg_l:   ld    a,(oidx)
        call  objnoun_get
        ld    hl,tnoun
        cp    (hl)
        jr    nz,dg_nx
        ld    a,(oidx)
        call  objloc_get
        ld    hl,curloc
        cp    (hl)
        jr    nz,dg_nx
        ld    a,(oidx)
        call  objfix_get
        or    a
        jr    nz,dg_fixed     ; objeto fijo (PNJ/escenario): no se puede coger
        ld    a,(oidx)
        call  too_heavy
        or    a
        jr    nz,dg_heavy     ; excede LLEVAR_MAX
        ld    a,(oidx)
        call  objloc_carr
        call  newline
        ld    de,STAKE
        call  print_msg
        ld    a,(oidx)
        call  print_objname
        ret
dg_fixed:
        call  newline
        ld    de,SNOTAKE
        call  print_msg
        ret
dg_heavy:
        call  newline
        ld    de,SHEAVY
        call  print_msg
        ret
dg_nx:  ld    a,(oidx)
        inc   a
        ld    (oidx),a
        djnz  dg_l
dg_no:  call  newline
        ld    de,SNOTHERE
        call  print_msg
        ret
; ---- COGER TODO: coge todos los objetos presentes en la localizacion ----
dg_all: xor   a
        ld    (oidx),a
        ld    (ctmp),a        ; ctmp = nº de objetos cogidos
dga_l:  ld    a,(oidx)
        ld    hl,nobj
        cp    (hl)
        jr    nc,dga_e        ; recorridos todos
        ld    a,(oidx)
        call  objloc_get
        ld    hl,curloc
        cp    (hl)
        jr    nz,dga_nx       ; no esta aqui
        ld    a,(oidx)
        call  objfix_get
        or    a
        jr    nz,dga_nx       ; fijo (PNJ/escenario): no se coge con "coger todo"
        ld    a,(oidx)
        call  too_heavy
        or    a
        jr    nz,dga_nx       ; demasiado peso: se deja
        ld    a,(oidx)
        call  objloc_carr     ; cogerlo
        call  newline
        ld    de,STAKE
        call  print_msg
        ld    a,(oidx)
        call  print_objname
        ld    a,(ctmp)
        inc   a
        ld    (ctmp),a
dga_nx: ld    a,(oidx)
        inc   a
        ld    (oidx),a
        jr    dga_l
dga_e:  ld    a,(ctmp)
        or    a
        ret   nz             ; cogio algo
        jp    dg_no          ; nada que coger -> "No ves eso aqui."

; ---- do_drop ----
do_drop:
        ld    a,(nounid)
        or    a
        jp    z,dd_no
        ld    hl,vall
        cp    (hl)
        jp    z,dd_all        ; DEJAR TODO
        ld    (tnoun),a
        ld    a,(nobj)
        or    a
        jr    z,dd_no
        ld    b,a
        xor   a
        ld    (oidx),a
dd_l:   ld    a,(oidx)
        call  objnoun_get
        ld    hl,tnoun
        cp    (hl)
        jr    nz,dd_nx
        ld    a,(oidx)
        call  objloc_get
        cp    CARRIED
        jr    nz,dd_nx
        ld    a,(oidx)
        call  objloc_cur
        call  newline
        ld    de,SDROP
        call  print_msg
        ld    a,(oidx)
        call  print_objname
        ret
dd_nx:  ld    a,(oidx)
        inc   a
        ld    (oidx),a
        djnz  dd_l
dd_no:  call  newline
        ld    de,SNOTCARR
        call  print_msg
        ret
; ---- DEJAR TODO: deja todos los objetos que se llevan ----
dd_all: xor   a
        ld    (oidx),a
        ld    (ctmp),a
dda_l:  ld    a,(oidx)
        ld    hl,nobj
        cp    (hl)
        jr    nc,dda_e
        ld    a,(oidx)
        call  objloc_get
        cp    CARRIED
        jr    nz,dda_nx      ; no se lleva
        ld    a,(oidx)
        call  objloc_cur     ; dejarlo aqui
        call  newline
        ld    de,SDROP
        call  print_msg
        ld    a,(oidx)
        call  print_objname
        ld    a,(ctmp)
        inc   a
        ld    (ctmp),a
dda_nx: ld    a,(oidx)
        inc   a
        ld    (oidx),a
        jr    dda_l
dda_e:  ld    a,(ctmp)
        or    a
        ret   nz
        jp    dd_no          ; nada que dejar -> "No llevas eso."

; ---- do_inven ----
do_inven:
        ld    a,(nobj)
        or    a
        jr    z,di_e
        ld    b,a
        ld    hl,OBJLOC
        ld    d,0
di_c:   ld    a,(hl)
        call  held_z
        jr    nz,di_cn
        inc   d
di_cn:  inc   hl
        djnz  di_c
        ld    a,d
        or    a
        jr    z,di_e
        call  newline
        ld    de,SINVEN
        call  print_msg
        ld    a,(nobj)
        ld    b,a
        xor   a
        ld    (oidx),a
di_l:   ld    a,(oidx)
        call  objloc_get
        call  held_z
        jr    nz,di_nx
        push  bc
        ld    a,(oidx)
        call  print_objname
        ld    a,32
        call  char_raw
        pop   bc
di_nx:  ld    a,(oidx)
        inc   a
        ld    (oidx),a
        djnz  di_l
        ret
di_e:   call  newline
        ld    de,SEMPTY
        call  print_msg
        ret

; ---- do_exam: imprime el nombre del objeto presente/llevado ----
do_exam:
        ld    a,(nounid)
        or    a
        jp    z,describe      ; "mirar"/"examinar" sin objeto -> describe la sala
        ld    (tnoun),a
        ld    a,(nobj)
        or    a
        jr    z,dx_no
        ld    b,a
        xor   a
        ld    (oidx),a
dx_l:   ld    a,(oidx)
        call  objnoun_get
        ld    hl,tnoun
        cp    (hl)
        jr    nz,dx_nx
        ld    a,(oidx)
        call  objloc_get
        cp    CARRIED
        jr    z,dx_f
        ld    hl,curloc
        cp    (hl)
        jr    nz,dx_nx
dx_f:   call  newline
        ld    a,(oidx)
        call  print_objname
        ret
dx_nx:  ld    a,(oidx)
        inc   a
        ld    (oidx),a
        djnz  dx_l
dx_no:  call  newline
        ld    de,SNOTHERE
        call  print_msg
        ret

; ---- helpers objetos ----
objloc_get:
        ld    e,a
        ld    d,0
        ld    hl,OBJLOC
        add   hl,de
        ld    a,(hl)
        ret
objnoun_get:
        ld    e,a
        ld    d,0
        ld    hl,(objnounp)
        add   hl,de
        ld    a,(hl)
        ret
; objfix_get: A=indice de objeto -> A = flag "fixed" (1 = no cogible)
objfix_get:
        ld    e,a
        ld    d,0
        ld    hl,(objfixp)
        add   hl,de
        ld    a,(hl)
        ret
; held_z: Z=1 si A (valor de OBJLOC) es CARRIED o WORN (llevado o puesto)
held_z: cp    CARRIED
        ret   z
        cp    WORN
        ret
; objlit_addr: A=obj -> HL = &OBJLIT[obj]
objlit_addr:
        ld    e,a
        ld    d,0
        ld    hl,OBJLIT
        add   hl,de
        ret
; objlight_get: A=obj -> A = flag "fuente de luz"
objlight_get:
        ld    e,a
        ld    d,0
        ld    hl,(objlightp)
        add   hl,de
        ld    a,(hl)
        ret
; --- contenedores ---
objopen_addr:
        ld    e,a
        ld    d,0
        ld    hl,OBJOPEN
        add   hl,de
        ret
objlock_addr:
        ld    e,a
        ld    d,0
        ld    hl,OBJLOCK
        add   hl,de
        ret
objin_addr:
        ld    e,a
        ld    d,0
        ld    hl,OBJIN
        add   hl,de
        ret
objin_get:
        call  objin_addr
        ld    a,(hl)
        ret
objweight_get:
        ld    e,a
        ld    d,0
        ld    hl,(objweightp)
        add   hl,de
        ld    a,(hl)
        ret
; carried_weight: A = suma de pesos de los objetos llevados/puestos
carried_weight:
        ld    a,(nobj)
        or    a
        jr    z,cw_z
        ld    b,a
        ld    c,0
        xor   a
        ld    (widx),a
cw_l:   ld    a,(widx)
        call  objloc_get
        call  held_z
        jr    nz,cw_nx
        ld    a,(widx)
        call  objweight_get
        add   a,c
        ld    c,a
cw_nx:  ld    a,(widx)
        inc   a
        ld    (widx),a
        djnz  cw_l
        ld    a,c
        ret
cw_z:   xor   a
        ret
; too_heavy: A=obj -> A=1 si coger ese objeto excederia LLEVAR_MAX (0 = sin limite)
too_heavy:
        ld    (wtmp),a       ; obj (temporal)
        ld    a,(llevarmax)
        cp    255
        jr    z,th_no        ; sin variable LLEVAR_MAX -> sin limite
        ld    a,(wtmp)
        call  objweight_get
        ld    (wtmp),a       ; peso del objeto
        call  carried_weight
        ld    hl,wtmp
        add   a,(hl)
        ld    (wtmp),a       ; peso total resultante
        ld    a,(llevarmax)
        call  flag_addr
        ld    a,(hl)         ; valor de LLEVAR_MAX
        or    a
        jr    z,th_no        ; 0 -> sin limite
        ld    c,a
        ld    a,(wtmp)
        cp    c
        jr    z,th_no
        jr    c,th_no
        ld    a,1
        ret
th_no:  xor   a
        ret
; obj_present: A=obj -> A=1 si presente (llevado/puesto, en la sala, o en un
; contenedor abierto que a su vez este presente). A=0 si no.
obj_present:
        ld    (ctmp),a
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jr    z,op_yes
        cp    WORN
        jr    z,op_yes
        ld    hl,curloc
        cp    (hl)
        jr    z,op_yes
        cp    CONTAINED
        jr    nz,op_no
        ld    a,(ctmp)
        call  objin_get
        or    a
        jr    z,op_no
        dec   a
        ld    (ctmp),a
        call  objopen_addr
        ld    a,(hl)
        or    a
        jr    z,op_no
        ld    a,(ctmp)
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jr    z,op_yes
        cp    WORN
        jr    z,op_yes
        ld    hl,curloc
        cp    (hl)
        jr    z,op_yes
op_no:  xor   a
        ret
op_yes: ld    a,1
        ret
; is_dark: A=1 si la sala actual es oscura y no hay fuente de luz encendida y
; presente; A=0 en caso contrario.
is_dark:
        ld    a,(curloc)
        ld    e,a
        ld    d,0
        ld    hl,(locdarkp)
        add   hl,de
        ld    a,(hl)
        or    a
        ret   z                ; sala no oscura -> no oscuro
        ld    a,(nobj)
        or    a
        jr    z,isd_yes        ; sin objetos -> oscuro
        ld    b,a
        xor   a
        ld    (oidx),a
isd_l:  ld    a,(oidx)
        call  objlight_get
        or    a
        jr    z,isd_nx         ; no es fuente de luz
        ld    a,(oidx)
        call  objlit_addr
        ld    a,(hl)
        or    a
        jr    z,isd_nx         ; apagada
        ld    a,(oidx)
        call  objloc_get
        call  held_z
        jr    z,isd_no         ; llevada/puesta -> hay luz
        ld    a,(oidx)
        call  objloc_get
        ld    hl,curloc
        cp    (hl)
        jr    z,isd_no         ; en la sala -> hay luz
isd_nx: ld    a,(oidx)
        inc   a
        ld    (oidx),a
        djnz  isd_l
isd_yes:
        ld    a,1
        ret
isd_no: xor   a
        ret
; --- temporizadores ---
tcur_addr:
        ld    e,a
        ld    d,0
        ld    hl,TCUR
        add   hl,de
        ret
tact_addr:
        ld    e,a
        ld    d,0
        ld    hl,TACT
        add   hl,de
        ret
tdur_get:
        ld    e,a
        ld    d,0
        ld    hl,(tdurp)
        add   hl,de
        ld    a,(hl)
        ret
tloop_get:
        ld    e,a
        ld    d,0
        ld    hl,(tloopp)
        add   hl,de
        ld    a,(hl)
        ret
texp_run:                  ; A=i -> ejecuta on_expire[i] (run_proc gestiona 0)
        add   a,a
        ld    e,a
        ld    d,0
        ld    hl,(texptabp)
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a
        jp    run_proc
tick_timers:
        ld    a,(ntimers)
        or    a
        ret   z
        ld    b,a
        xor   a
        ld    (tidx),a
tt_l:   ld    a,(tidx)
        call  tact_addr
        ld    a,(hl)
        or    a
        jr    z,tt_nx
        ld    a,(tidx)
        call  tcur_addr
        ld    a,(hl)
        dec   a
        ld    (hl),a
        or    a
        jr    z,tt_exp
        jp    m,tt_exp
        jr    tt_nx
tt_exp: push  bc
        ld    a,(tidx)
        call  texp_run
        ld    a,(tidx)
        call  tloop_get
        or    a
        jr    z,tt_off
        ld    a,(tidx)
        call  tdur_get
        ld    c,a
        ld    a,(tidx)
        call  tcur_addr
        ld    (hl),c
        jr    tt_re
tt_off: ld    a,(tidx)
        call  tact_addr
        ld    (hl),0
tt_re:  pop   bc
tt_nx:  ld    a,(tidx)
        inc   a
        ld    (tidx),a
        djnz  tt_l
        ret
; print_dec: imprime A (0..255) en decimal sin ceros a la izquierda
print_dec:
        push  af
        xor   a
        ld    (pdlead),a
        pop   af
        ld    b,100
        call  pd_dig
        ld    b,10
        call  pd_dig
        add   a,48           ; '0'
        jp    char_raw
pd_dig: ld    c,47           ; '0'-1
pd_l:   inc   c
        sub   b
        jr    nc,pd_l
        add   a,b
        push  af
        ld    a,c
        cp    48             ; '0'
        jr    nz,pd_show
        ld    a,(pdlead)
        or    a
        jr    z,pd_noshow
pd_show:
        ld    a,1
        ld    (pdlead),a
        push  bc
        ld    a,c
        call  char_raw
        pop   bc
pd_noshow:
        pop   af
        ret
objloc_carr:
        ld    e,a
        ld    d,0
        ld    hl,OBJLOC
        add   hl,de
        ld    (hl),CARRIED
        ret
objloc_cur:
        ld    e,a
        ld    d,0
        ld    hl,OBJLOC
        add   hl,de
        ld    a,(curloc)
        ld    (hl),a
        ret
print_objname:
        add   a,a
        ld    e,a
        ld    d,0
        ld    hl,(objnamep)
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        jp    print_msg

try_move:
        ld    a,(curloc)
        call  loc_record
        inc   hl
        inc   hl
        ld    a,(hl)
        inc   hl
        ld    b,a
        or    a
        jr    z,tm_no
        ld    a,(verbid)
        ld    c,a
tm_s:   ld    a,(hl)
        inc   hl
        cp    c
        jr    z,tm_f
        inc   hl
        djnz  tm_s
tm_no:  xor   a
        ret
tm_f:   ld    a,(hl)
        ld    (curloc),a
        ld    a,1
        ret

loc_record:
        ld    l,a
        ld    h,0
        add   hl,hl
        ld    de,(locidx)
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a
        ret

; print_word_id: imprime el nombre completo de un vid (para las salidas) usando
; la tabla vnamep (vid -> puntero a cadena). Si no hay nombre, imprime solo espacio.
print_word_id:
        ld    l,a
        ld    h,0
        add   hl,hl           ; vid*2
        ld    de,(vnamep)
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a             ; HL = puntero al nombre (o 0)
        ld    a,h
        or    l
        jr    z,pw_pd         ; sin nombre -> solo espacio
pw_p:   ld    a,(hl)
        or    a
        jr    z,pw_pd
        call  char_raw
        inc   hl
        jr    pw_p
pw_pd:  ld    a,32
        call  char_raw
        ret

read_line:
        call  prefetch_init   ; prepara la precarga de salas contiguas
        ld    hl,INBUF
        ld    b,0
rl_l:   call  KMREAD          ; lee tecla SIN bloquear (CF=1 si hay)
        jr    nc,rl_idle      ; sin tecla -> precargar una contigua y reintentar
        cp    13
        jr    z,rl_d
        cp    127             ; DEL -> borra el ultimo caracter
        jr    z,rl_bs
        cp    32
        jr    c,rl_l          ; otros codigos de control -> ignorar
        ld    (hl),a
        inc   hl
        inc   b
        push  hl
        push  bc
        call  char_raw
        pop   bc
        pop   hl
        ld    a,b
        cp    38
        jr    c,rl_l
        jr    rl_d            ; buffer lleno
rl_bs:  ld    a,b
        or    a
        jr    z,rl_l          ; nada que borrar
        dec   hl
        dec   b
        push  hl
        push  bc
        ld    a,8             ; cursor a la izquierda
        call  TXTO
        ld    a,32            ; espacio (borra el glifo)
        call  TXTO
        ld    a,8             ; cursor a la izquierda otra vez
        call  TXTO
        pop   bc
        pop   hl
        jr    rl_l
rl_d:   ld    (hl),0
        ret
rl_idle:
        call  prefetch_one   ; sin tecla: precarga una sala contigua
        push  hl
        push  bc
        call  rnd8           ; entropia para CHANCE segun el tiempo de tecleo
        pop   bc
        pop   hl
        jp    rl_l

parse:  xor   a
        ld    (verbid),a
        ld    (nounid),a
        ld    (nounid2),a
        ld    hl,INBUF
pa_w:   ld    a,(hl)
        or    a
        ret   z
        cp    32
        jr    nz,pa_h
        inc   hl
        jr    pa_w
pa_h:   call  norm_word
        push  hl
        call  vocab_lookup
        pop   hl
        jr    nc,pa_w
        ld    d,a
        ld    a,e
        cp    1
        jr    z,pa_n
        ld    a,(verbid)
        or    a
        jr    nz,pa_w
        ld    a,d
        ld    (verbid),a
        ld    a,e
        ld    (vtype),a
        jr    pa_w
pa_n:   ld    a,(nounid)
        or    a
        jr    z,pa_n1         ; primer nombre
        ld    a,(nounid2)
        or    a
        jr    nz,pa_w         ; ya hay dos nombres
        ld    a,d
        ld    (nounid2),a
        jr    pa_w
pa_n1:  ld    a,d
        ld    (nounid),a
        jr    pa_w

norm_word:
        ld    de,KEY
        ld    b,4
nw1:    ld    a,(hl)
        cp    32
        jr    z,nw_p
        or    a
        jr    z,nw_p
        call  upcase
        ld    (de),a
        inc   de
        inc   hl
        djnz  nw1
        jr    nw_s
nw_p:   ld    a,32
nw_pp:  ld    (de),a
        inc   de
        djnz  nw_pp
        ret
nw_s:   ld    a,(hl)
        or    a
        ret   z
        cp    32
        ret   z
        inc   hl
        jr    nw_s

upcase: cp    97
        ret   c
        cp    123
        ret   nc
        sub   32
        ret

vocab_lookup:
        ld    a,(nvocab)
        ld    c,a
        ld    a,(nvocab+1)
        ld    b,a             ; BC = nº de palabras (16-bit)
        or    c
        ret   z              ; vocabulario vacío -> sin coincidencia
        ld    hl,(vocabp)
vl_s:   push  hl
        push  bc
        ld    de,KEY
        ld    b,4
vl_c:   ld    a,(de)
        cp    (hl)
        jr    nz,vl_nm
        inc   hl
        inc   de
        djnz  vl_c
        ld    a,(hl)
        inc   hl
        ld    e,(hl)
        pop   bc
        pop   hl
        scf
        ret
vl_nm:  pop   bc
        pop   hl
        ld    de,6
        add   hl,de
        dec   bc
        ld    a,b
        or    c
        jr    nz,vl_s
        or    a
        ret

print_msg:
        call  expand_msg
        call  wrap_print
        ret

expand_msg:
        ld    h,d
        ld    l,e
        add   hl,hl
        ld    de,(msgidx)
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a
        ld    de,BUF
em_l:   ld    a,(hl)
        inc   hl
        or    a
        jr    z,em_d
        cp    224
        jr    nc,em_lit       ; >=224 -> caracter acentuado (literal)
        bit   7,a
        jr    z,em_lit
        push  hl
        sub   128
        ld    l,a
        ld    h,0
        add   hl,hl
        ld    bc,(dictidx)
        add   hl,bc
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a
em_t:   ld    a,(hl)
        inc   hl
        or    a
        jr    z,em_te
        ld    (de),a
        inc   de
        jr    em_t
em_te:  pop   hl
        jr    em_l
em_lit: ld    (de),a
        inc   de
        jr    em_l
em_d:   ld    hl,BUF
        ld    a,e
        sub   l
        ld    c,a
        ld    a,d
        sbc   h
        ld    b,a
        ld    hl,BUF
        ret

wrap_print:
wp_m:   ld    a,b
        or    c
        ret   z
        ld    a,(hl)
        cp    32
        jp    z,wp_sp
        push  hl
        push  bc
        ld    d,0
wp_me:  ld    a,b
        or    c
        jr    z,wp_md
        ld    a,(hl)
        cp    32
        jr    z,wp_md
        inc   d
        inc   hl
        dec   bc
        jr    wp_me
wp_md:  pop   bc
        pop   hl
        ld    a,(col)
        add   a,d
        ld    e,a
        ld    a,(width)
        cp    e
        jr    nc,wp_nn
        call  newline
wp_nn:  ld    a,d
        or    a
        jp    z,wp_m
        ld    a,(hl)
        call  char_raw
        inc   hl
        dec   bc
        dec   d
        jr    wp_nn
wp_sp:  ld    a,(col)
        ld    e,a
        ld    a,(width)
        cp    e
        jr    z,wp_spn
        jr    c,wp_spn
        ld    a,32
        call  char_raw
        inc   hl
        dec   bc
        jp    wp_m
wp_spn: call  newline
        inc   hl
        dec   bc
        jp    wp_m

char_raw:
        push  hl
        push  de
        push  bc
        call  TXTO
        ld    a,(col)
        inc   a
        ld    (col),a
        pop   bc
        pop   de
        pop   hl
        ret

newline:
        push  hl
        push  de
        push  bc
        ld    a,13
        call  TXTO
        ld    a,10
        call  TXTO
        xor   a
        ld    (col),a
        pop   bc
        pop   de
        pop   hl
        ret

; ================= condacts =================
run_response:
        ld    hl,(respp)
rr_e:   ld    a,(hl)
        cp    255
        jr    z,rr_no
        ld    b,a
        inc   hl
        ld    c,(hl)
        inc   hl
        ld    a,(hl)
        inc   hl
        ld    e,a
        ld    d,0
        push  hl
        push  de
        add   hl,de
        ld    (rnext),hl
        pop   de
        pop   hl
        ld    a,(verbid)
        cp    b
        jr    nz,rr_nx
        ld    a,c
        or    a
        jr    z,rr_run
        ld    a,(nounid)
        cp    c
        jr    nz,rr_nx
rr_run: call  run_condacts
        or    a
        jr    z,rr_nx
        ld    a,1
        ret
rr_nx:  ld    hl,(rnext)
        jr    rr_e
rr_no:  xor   a
        ret

run_proc:
        ld    a,h
        or    l
        ret   z
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        call  run_condacts
        ret

run_condacts:
        ld    (cptr),hl
        add   hl,de
        ld    (rcend),hl
rc_loop:
        ld    hl,(cptr)
        ld    de,(rcend)
        ld    a,h
        cp    d
        jr    c,rc_go
        jr    nz,rc_end
        ld    a,l
        cp    e
        jr    nc,rc_end
rc_go:  call  getop
        cp    49
        jr    nc,rc_loop
        add   a,a
        ld    e,a
        ld    d,0
        ld    hl,CTAB
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a
        jp    (hl)
rc_handled:
        ld    a,1
        ret
rc_end:
rc_fail:
        xor   a
        ret

getop:  ld    hl,(cptr)
        ld    a,(hl)
        inc   hl
        ld    (cptr),hl
        ret
getop16:
        ld    hl,(cptr)
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        ld    (cptr),hl
        ret

flag_addr:
        ld    e,a
        ld    d,0
        ld    hl,FLAGS
        add   hl,de
        ret
obj_addr:
        ld    e,a
        ld    d,0
        ld    hl,OBJLOC
        add   hl,de
        ret

c_at:   call  getop
        ld    hl,curloc
        cp    (hl)
        jp    z,rc_loop
        jp    rc_fail
c_notat:
        call  getop
        ld    hl,curloc
        cp    (hl)
        jp    nz,rc_loop
        jp    rc_fail
c_present:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jp    z,rc_loop
        ld    hl,curloc
        cp    (hl)
        jp    z,rc_loop
        jp    rc_fail
c_absent:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jp    z,rc_fail
        ld    hl,curloc
        cp    (hl)
        jp    z,rc_fail
        jp    rc_loop
c_carried:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jp    z,rc_loop
        jp    rc_fail
c_notcarr:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jp    nz,rc_loop
        jp    rc_fail
c_zero: call  getop
        call  flag_addr
        ld    a,(hl)
        or    a
        jp    z,rc_loop
        jp    rc_fail
c_notzero:
        call  getop
        call  flag_addr
        ld    a,(hl)
        or    a
        jp    nz,rc_loop
        jp    rc_fail
c_eq:   call  getop
        ld    (ctmp),a
        call  getop
        ld    c,a
        ld    a,(ctmp)
        call  flag_addr
        ld    a,(hl)
        cp    c
        jp    z,rc_loop
        jp    rc_fail
c_goto: call  getop
        ld    (curloc),a
        jp    rc_loop
c_message:
        call  getop16
        push  de
        call  newline
        pop   de
        call  print_msg
        jp    rc_loop
c_mes:  call  getop16
        call  print_msg
        jp    rc_loop
c_get:  call  getop
        call  objloc_carr
        jp    rc_loop
c_drop: call  getop
        call  objloc_cur
        jp    rc_loop
c_destroy:
        call  getop
        call  obj_addr
        ld    (hl),NOWHERE
        jp    rc_loop
c_create:
        call  getop
        call  objloc_cur
        jp    rc_loop
c_wear: call  getop
        call  obj_addr
        ld    (hl),WORN
        jp    rc_loop
c_remove:
        call  getop
        call  obj_addr
        ld    (hl),CARRIED
        jp    rc_loop
c_lit:  call  getop
        call  objlit_addr
        ld    (hl),1
        jp    rc_loop
c_unlit:
        call  getop
        call  objlit_addr
        ld    (hl),0
        jp    rc_loop
c_score:
        call  getop          ; indice del flag PUNTOS
        call  flag_addr
        ld    a,(hl)
        push  af
        ld    de,SSCORE
        call  print_msg
        pop   af
        call  print_dec
        call  newline
        jp    rc_loop
c_tstart:
        call  getop
        ld    (ctmp),a
        call  tact_addr
        ld    (hl),1
        ld    a,(ctmp)
        call  tdur_get
        ld    c,a
        ld    a,(ctmp)
        call  tcur_addr
        ld    (hl),c
        jp    rc_loop
c_tstop:
        call  getop
        call  tact_addr
        ld    (hl),0
        jp    rc_loop
c_treset:
        call  getop
        ld    (ctmp),a
        call  tdur_get
        ld    c,a
        ld    a,(ctmp)
        call  tcur_addr
        ld    (hl),c
        jp    rc_loop
c_open: call  getop
        ld    (ctmp),a
        call  objopen_addr
        ld    (hl),1
        ld    a,(ctmp)
        call  objlock_addr
        ld    (hl),0
        jp    rc_loop
c_close:
        call  getop
        call  objopen_addr
        ld    (hl),0
        jp    rc_loop
c_lock: call  getop
        call  objlock_addr
        ld    (hl),1
        jp    rc_loop
c_unlock:
        call  getop
        call  objlock_addr
        ld    (hl),0
        jp    rc_loop
c_putin:
        call  getop          ; obj
        ld    (ctmp),a
        call  getop          ; contenedor
        inc   a              ; OBJIN = contenedor+1
        ld    c,a
        ld    a,(ctmp)
        call  objin_addr
        ld    (hl),c
        ld    a,(ctmp)
        call  obj_addr
        ld    (hl),CONTAINED
        jp    rc_loop
c_takeout:
        call  getop
        ld    (ctmp),a
        call  objin_addr
        ld    (hl),0
        ld    a,(ctmp)
        call  obj_addr
        ld    (hl),CARRIED
        jp    rc_loop
c_place:
        call  getop
        ld    (ctmp),a
        call  getop
        ld    c,a
        ld    a,(ctmp)
        call  obj_addr
        ld    (hl),c
        jp    rc_loop
c_set:  call  getop
        call  flag_addr
        ld    (hl),255
        jp    rc_loop
c_clear:
        call  getop
        call  flag_addr
        ld    (hl),0
        jp    rc_loop
c_let:  call  getop
        ld    (ctmp),a
        call  getop
        ld    c,a
        ld    a,(ctmp)
        call  flag_addr
        ld    (hl),c
        jp    rc_loop
c_plus: call  getop
        ld    (ctmp),a
        call  getop
        ld    c,a
        ld    a,(ctmp)
        call  flag_addr
        ld    a,(hl)
        add   a,c
        ld    (hl),a
        jp    rc_loop
c_minus:
        call  getop
        ld    (ctmp),a
        call  getop
        ld    c,a
        ld    a,(ctmp)
        call  flag_addr
        ld    a,(hl)
        sub   c
        ld    (hl),a
        jp    rc_loop
c_done: jp    rc_handled
c_desc: call  describe
        jp    rc_loop
c_inven:
        call  do_inven
        jp    rc_loop
c_newline:
        call  newline
        jp    rc_loop

eval_expr:
        xor   a
        ld    (esp),a
ev_l:   call  getop
        cp    30
        jr    nc,ev_l
        add   a,a
        ld    e,a
        ld    d,0
        ld    hl,ETAB
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a
        jp    (hl)
e_push: push  hl
        push  de
        ld    hl,esp
        ld    e,(hl)
        inc   (hl)
        ld    d,0
        ld    hl,ESTACK
        add   hl,de
        ld    (hl),a
        pop   de
        pop   hl
        ret
e_pop:  push  hl
        push  de
        ld    hl,esp
        dec   (hl)
        ld    e,(hl)
        ld    d,0
        ld    hl,ESTACK
        add   hl,de
        ld    a,(hl)
        pop   de
        pop   hl
        ret
ex_end: call  e_pop
        ret
ex_const:
        call  getop
        call  e_push
        jp    ev_l
ex_var: call  getop
        call  flag_addr
        ld    a,(hl)
        call  e_push
        jp    ev_l
ex_add: call  e_pop
        ld    c,a
        call  e_pop
        add   a,c
        call  e_push
        jp    ev_l
ex_sub: call  e_pop
        ld    c,a
        call  e_pop
        sub   c
        call  e_push
        jp    ev_l
ex_eq:  call  e_pop
        ld    c,a
        call  e_pop
        cp    c
        jp    z,ex_t
        jp    ex_f
ex_ne:  call  e_pop
        ld    c,a
        call  e_pop
        cp    c
        jp    nz,ex_t
        jp    ex_f
ex_lt:  call  e_pop
        ld    c,a
        call  e_pop
        cp    c
        jp    c,ex_t
        jp    ex_f
ex_gt:  call  e_pop
        ld    c,a
        call  e_pop
        cp    c
        jp    z,ex_f
        jp    nc,ex_t
        jp    ex_f
ex_and: call  e_pop
        ld    c,a
        call  e_pop
        or    a
        jp    z,ex_f
        ld    a,c
        or    a
        jp    z,ex_f
        jp    ex_t
ex_or:  call  e_pop
        ld    c,a
        call  e_pop
        or    a
        jp    nz,ex_t
        ld    a,c
        or    a
        jp    nz,ex_t
        jp    ex_f
ex_not: call  e_pop
        or    a
        jp    z,ex_t
        jp    ex_f
ex_at:  call  getop
        ld    hl,curloc
        cp    (hl)
        jp    z,ex_t
        jp    ex_f
ex_notat:
        call  getop
        ld    hl,curloc
        cp    (hl)
        jp    nz,ex_t
        jp    ex_f
ex_zero:
        call  getop
        call  flag_addr
        ld    a,(hl)
        or    a
        jp    z,ex_t
        jp    ex_f
ex_nzero:
        call  getop
        call  flag_addr
        ld    a,(hl)
        or    a
        jp    nz,ex_t
        jp    ex_f
ex_dark:
        call  is_dark
        or    a
        jp    nz,ex_t
        jp    ex_f
ex_carr:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jp    z,ex_t
        cp    WORN
        jp    z,ex_t
        jp    ex_f
ex_pres:
        call  getop
        call  obj_present
        or    a
        jp    nz,ex_t
        jp    ex_f
ex_abs: call  getop
        call  obj_present
        or    a
        jp    z,ex_t
        jp    ex_f
ex_hasopen:
        call  getop
        call  objopen_addr
        ld    a,(hl)
        or    a
        jp    nz,ex_t
        jp    ex_f
ex_ncar:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    CARRIED
        jp    z,ex_f
        cp    WORN
        jp    z,ex_f
        jp    ex_t
ex_worn:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    WORN
        jp    z,ex_t
        jp    ex_f
ex_nworn:
        call  getop
        call  obj_addr
        ld    a,(hl)
        cp    WORN
        jp    z,ex_f
        jp    ex_t
ex_isat:
        call  getop          ; obj
        call  obj_addr
        ld    a,(hl)
        ld    c,a            ; c = OBJLOC[obj]
        call  getop          ; dest
        cp    c
        jp    z,ex_t
        jp    ex_f
ex_chance:
        call  getop          ; n (0..100)
        ld    c,a
        call  rnd8           ; a = 0..255
exc_m:  cp    100
        jr    c,exc_ok
        sub   100
        jr    exc_m
exc_ok: cp    c             ; rnd < n -> exito
        jp    c,ex_t
        jp    ex_f
ex_verb:
        call  getop          ; v (255 = comodin *)
        cp    255
        jp    z,ex_t
        ld    hl,verbid
        cp    (hl)
        jp    z,ex_t
        jp    ex_f
ex_noun1:
        call  getop          ; n (255=*, 254=_, else id)
        cp    255
        jr    z,exn_any
        cp    254
        jr    z,exn_no
        ld    hl,nounid
        cp    (hl)
        jp    z,ex_t
        jp    ex_f
exn_any:
        ld    a,(nounid)
        or    a
        jp    nz,ex_t
        jp    ex_f
exn_no: ld    a,(nounid)
        or    a
        jp    z,ex_t
        jp    ex_f
ex_noun2:
        call  getop          ; n (255=*, 254=_, else id)
        cp    255
        jr    z,e2_any
        cp    254
        jr    z,e2_no
        ld    hl,nounid2
        cp    (hl)
        jp    z,ex_t
        jp    ex_f
e2_any: ld    a,(nounid2)
        or    a
        jp    nz,ex_t
        jp    ex_f
e2_no:  ld    a,(nounid2)
        or    a
        jp    z,ex_t
        jp    ex_f
ex_timer:
        call  getop          ; timer
        call  tcur_addr
        ld    a,(hl)
        ld    c,a
        call  getop          ; valor
        cp    c
        jp    z,ex_t
        jp    ex_f
; rnd8: A = pseudoaleatorio 0..255 (LCG: seed = seed*5 + 1)
rnd8:   push  de
        ld    hl,(rndseed)
        ld    d,h
        ld    e,l
        add   hl,hl
        add   hl,hl
        add   hl,de
        inc   hl
        ld    (rndseed),hl
        ld    a,h
        pop   de
        ret
ex_t:   ld    a,1
        call  e_push
        jp    ev_l
ex_f:   xor   a
        call  e_push
        jp    ev_l
ETAB:   defw ex_end,ex_const,ex_var,ex_add,ex_sub,ex_eq,ex_ne,ex_lt,ex_gt,ex_and
        defw ex_or,ex_not,ex_at,ex_notat,ex_zero,ex_nzero,ex_dark,ex_carr,ex_pres,ex_abs,ex_ncar
        defw ex_isat,ex_chance,ex_worn,ex_nworn,ex_verb,ex_noun1,ex_timer,ex_hasopen
        defw ex_noun2
c_letx: call  getop
        ld    (ctmp),a
        call  eval_expr
        ld    c,a
        ld    a,(ctmp)
        call  flag_addr
        ld    (hl),c
        jp    rc_loop
c_if:   call  getop
        ld    (ctmp),a
        call  eval_expr
        or    a
        jp    nz,rc_loop
        ld    a,(ctmp)
        ld    e,a
        ld    d,0
        ld    hl,(cptr)
        add   hl,de
        ld    (cptr),hl
        jp    rc_loop
c_jmp:  call  getop
        ld    e,a
        ld    d,0
        ld    hl,(cptr)
        add   hl,de
        ld    (cptr),hl
        jp    rc_loop
; --- comandos de pantalla/tiempo equivalentes CPC (color ZX->CPC ya mapeado) ---
c_ink:  call  getop           ; INK n: color del TEXTO (pluma 1)
        ld    b,a
        ld    c,a             ; B=C=color (solido, sin parpadeo)
        ld    a,1
        call  SCRINK          ; SCR SET INK: A=pluma, B/C=color firmware
        jp    rc_loop
c_paper:
        call  getop           ; PAPER n: color del FONDO (pluma 0)
        ld    b,a
        ld    c,a
        ld    a,0
        call  SCRINK
        jp    rc_loop
c_border:
        call  getop           ; BORDER n: color del borde
        ld    b,a
        ld    c,a             ; B=C=color (mismo -> borde solido, sin parpadeo)
        call  SCRBORDER       ; SCR SET BORDER: B=color1, C=color2
        jp    rc_loop
c_pause:
        call  getop           ; PAUSE n: espera n frames (50 Hz); 0 = espera tecla
        or    a
        jr    z,cpa_key
        ld    b,a
cpa_l:  push  bc
        call  MCWAIT          ; espera el barrido de un frame
        pop   bc
        djnz  cpa_l
        jp    rc_loop
cpa_key:
        call  KMW
        jp    rc_loop
c_cls:  ld    a,12            ; CLS: borra la ventana de texto actual
        call  TXTO
        xor   a
        ld    (col),a
        jp    rc_loop
; PLAY n: reproduce el efecto FX n (1-based) por el AY. Bloqueante: para cada
; frame escribe R0/R1 (tono), R6 (ruido), R7 (mezclador) y R8 (volumen) del canal
; A con MC SOUND REGISTER (&BD34, preserva la linea de teclado) y espera un frame
; con MCWAIT (~50 Hz). Al acabar silencia el canal A. Datos: blob en (fxp), con
; formato [nfx][off0..][bloques]; cada offset relativo al inicio del blob.
c_play: call  getop           ; A = numero de efecto (1-based)
        ld    b,a             ; B = n (preservar)
        or    a
        jp    z,rc_loop       ; n=0 -> nada
        ld    hl,(fxp)
        ld    a,h
        or    l
        jp    z,rc_loop       ; sin datos FX
        ld    a,(hl)          ; nfx
        cp    b
        jp    c,rc_loop       ; nfx < n -> fuera de rango
        ld    a,b
        dec   a
        add   a,a            ; (n-1)*2
        ld    e,a
        ld    d,0
        inc   hl             ; fxp+1 (inicio tabla de offsets)
        add   hl,de          ; -> &offset[n-1]
        ld    e,(hl)
        inc   hl
        ld    d,(hl)         ; DE = offset (relativo a fxp)
        ld    a,d
        or    e
        jp    z,rc_loop      ; offset 0 -> efecto no incluido
        ld    hl,(fxp)
        add   hl,de          ; HL -> bloque del efecto
        ld    a,(hl)         ; nframes
        inc   hl
        or    a
        jp    z,rc_loop
        ld    b,a            ; B = contador de frames
cpl_f:  push  bc
        xor   a             ; reg 0 (tono lo)
        ld    c,(hl)
        push  hl
        call  SNDREG
        pop   hl
        inc   hl
        ld    a,1           ; reg 1 (tono hi)
        ld    c,(hl)
        push  hl
        call  SNDREG
        pop   hl
        inc   hl
        ld    a,6           ; reg 6 (ruido)
        ld    c,(hl)
        push  hl
        call  SNDREG
        pop   hl
        inc   hl
        ld    a,7           ; reg 7 (mezclador)
        ld    c,(hl)
        push  hl
        call  SNDREG
        pop   hl
        inc   hl
        ld    a,8           ; reg 8 (volumen canal A)
        ld    c,(hl)
        push  hl
        call  SNDREG
        pop   hl
        inc   hl
        push  hl
        call  MCWAIT        ; esperar 1 frame (~1/50 s)
        pop   hl
        pop   bc
        djnz  cpl_f
        ld    a,8           ; silenciar canal A (volumen 0)
        ld    c,0
        call  SNDREG
        jp    rc_loop
CTAB:   defw c_at,c_notat,c_present,c_absent,c_carried,c_notcarr,c_zero,c_notzero,c_eq
        defw c_goto,c_message,c_mes,c_get,c_drop,c_destroy,c_create,c_place,c_set
        defw c_clear,c_let,c_plus,c_minus,c_done,c_desc,c_inven,c_newline
        defw c_letx,c_if,c_jmp
        defw c_ink,c_paper,c_border,c_pause,c_cls
        defw c_wear,c_remove,c_lit,c_unlit
        defw c_score,c_tstart,c_tstop,c_treset
        defw c_open,c_close,c_lock,c_unlock,c_putin,c_takeout
        defw c_play

show_title:
        ld    a,(hastitle)
        or    a
        ret   z
        call  set_title_pal
        ld    a,(hasmusic)
        or    a
        jr    z,st_nomus
        ; El reproductor se engancha a la interrupcion de frame (50 Hz) con
        ; KL_ADD_FRAME_FLY. Toda la E/S del AY ocurre dentro de la interrupcion
        ; (con interrupciones inhibidas), sin chocar con el escaneo de teclado del
        ; firmware. El primer plano solo espera la tecla (KMW, bloqueante).
        ;
        ; El firmware EXIGE que la rutina de evento y el bloque esten en los 32 KB
        ; centrales (&4000-&BFFF), siempre RAM aunque la ROM este paginada. El motor
        ; vive en &1200 (16 KB bajos), asi que copiamos la rutina al buffer hdrbuf
        ; (en zona central y libre durante la portada) e instalamos desde alli.
        call  MUSINIT
        di
        ld    de,(hdrbufp)    ; DE = destino rutina (central, libre en portada)
        ld    (mrt),de
        ld    hl,mplay
        ld    bc,mpend-mplay
        ldir                  ; copia la rutina; DE queda justo detras = bloque
        ld    (mblk),de       ; bloque de evento, tambien en zona central
        ld    hl,(mblk)
        ld    b,&C1           ; clase: near(b0)+express(b6)+async(b7): interrupcion
        ld    c,0
        ld    de,(mrt)
        call  KLINIT
        ld    hl,(mblk)
        call  KLADDF
        ei
        call  KMW             ; espera tecla; la musica suena por interrupcion
        di
        ld    hl,(mblk)
        call  KLDELF
        ei
        call  MUSSTOP
        jr    st_done
st_nomus:
        call  KMW
st_done:
        ld    a,2
        call  SCRMODE
        ld    a,0
        ld    b,1
        ld    c,1
        call  SCRINK
        ld    a,1
        ld    b,24
        ld    c,24
        call  SCRINK
        ld    a,12
        call  TXTO
        ret
set_title_pal:
        ld    hl,(titlepal)
        ld    a,h
        or    l
        ret   z
        ld    d,0
stp_l:  ld    a,(hl)
        ld    b,a
        ld    c,a
        ld    a,d
        push  hl
        push  de
        call  SCRINK
        pop   de
        pop   hl
        inc   hl
        inc   d
        ld    a,d
        cp    16
        jr    c,stp_l
        ret
; Envoltorio del reproductor llamado desde la interrupcion de frame.
; Preserva TODOS los registros (principal + alternativo + IX/IY) porque la
; interrupcion puede caer en cualquier punto del primer plano.
mplay:  push  af
        push  bc
        push  de
        push  hl
        push  ix
        push  iy
        exx
        ex    af,af'
        push  af
        push  bc
        push  de
        push  hl
        call  MUSPLAY
        pop   hl
        pop   de
        pop   bc
        pop   af
        ex    af,af'
        exx
        pop   iy
        pop   ix
        pop   hl
        pop   de
        pop   bc
        pop   af
        ret
mpend:                        ; fin de mplay (para copiar mpend-mplay bytes)
ftitle: defb "TITLE.SCR"

dictidx:  defw 0
msgidx:   defw 0
locidx:   defw 0
vocabp:   defw 0
objnamep: defw 0
objnounp: defw 0
objlocsrc: defw 0
objfixp: defw 0
locdarkp: defw 0
objlightp: defw 0
tdurp: defw 0
tloopp: defw 0
tactsrcp: defw 0
texptabp: defw 0
ntimers: defb 0
tidx: defb 0
pdlead: defb 0
objopensrc: defw 0
objlocksrc: defw 0
objinsrc: defw 0
objweightp: defw 0
fxp: defw 0
llevarmax: defb 0
widx: defb 0
wtmp: defb 0
width:    defb 40
nvocab:   defw 0
curloc:   defb 0
nobj:     defb 0
vlook:    defb 0
vquit:    defb 0
vget:     defb 0
vdrop:    defb 0
vinven:   defb 0
vexam:    defb 0
verbid:   defb 0
nounid:   defb 0
nounid2:  defb 0
vtype:    defb 0
tnoun:    defb 0
oidx:     defb 0
quitf:    defb 0
rndseed:  defw 1
col:      defb 0
respp:    defw 0
cptr:     defw 0
rcend:    defw 0
rnext:    defw 0
beforep:  defw 0
afterp:   defw 0
onstartp: defw 0
titlepal: defw 0
hasmusic: defb 0
hastitle: defb 0
mrt:      defw 0
mblk:     defw 0
hdrbufp:  defw 0
imgbufp:  defw 0
locslotp: defw 0
vnamep:   defw 0
has128:   defb 0
curslot:  defb 0
populated: defw 0
nloc:     defb 0
plc_i:    defb 0
plc_save: defb 0
vall:     defb 0
pf_i:     defb 0
pf_n:     defb 0
pf_exits: defw 0
picloc:   defb 0
faccp:    defw 0
accptr:   defw 0
acccode:  defb 0
accbuf:   defs 8
ctmp:     defb 0
FLAGS:    defs 64
esp:      defb 0
darkf:    defb 0
ESTACK:   defs 16
KEY:      defs 4
INBUF:    defs 41
OBJLOC:   defs 64
OBJLIT:   defs 64
OBJOPEN:  defs 64
OBJLOCK:  defs 64
OBJIN:    defs 64
TCUR:     defs 16
TACT:     defs 16
BUF:      defs 1024
'''

def assemble_engine(org=ORG, db_base=DB):
    import z80asm
    L=[]
    L.append('ORIGIN equ &%04X'%org)
    L.append('TXTO equ &%04X'%TXT)
    L.append('KMW equ &%04X'%KMWAIT)
    L.append('DBB equ &%04X'%db_base)
    L.append('CASOPEN equ &BC77')
    L.append('CASDIR equ &BC83')
    L.append('CASCLOSE equ &BC7A')
    L.append('SCRMODE equ &BC0E')
    L.append('SCRINK equ &BC32')
    L.append('SCRBORDER equ &BC38')   # SCR SET BORDER (color firmware 0-26)
    L.append('TXTPEN equ &BB90')      # TXT SET PEN (pluma de texto)
    L.append('TXTPAPER equ &BB96')    # TXT SET PAPER (pluma de fondo)
    L.append('TXTMATRIX equ &BBA8')   # TXT SET MATRIX (A=char, HL=matriz)
    L.append('TXTGETMATRIX equ &BBA5') # TXT GET MATRIX (A=char -> HL=matriz ROM)
    L.append('TXTMTABLE equ &BBAB')   # TXT SET M TABLE (DE=1er char, HL=tabla)
    L.append('MTABLE equ &8000')      # tabla de matrices de usuario (RAM central)
    L.append('ROMCOPY equ &8200')     # rutina de lectura de ROM reubicada (RAM alta)
    L.append('MCWAIT equ &BD19')
    L.append('SNDQUEUE equ &BCAA')   # SOUND QUEUE (firmware): reproduce FX vía AY
    L.append('SNDREG equ &BD34')     # MC SOUND REGISTER: A=reg, C=val (FX por AY)
    L.append('KMREAD equ &BB09')
    L.append('KLINIT equ &BCEF')      # KL INIT EVENT
    L.append('KLADDF equ &BCD7')      # KL NEW FRAME FLY (inicializa + añade el evento)
    L.append('KLDELF equ &BCDD')      # KL DEL FRAME FLY (lo quita de la lista)
    L.append('MUSINIT equ &8B00')     # reproductor: init
    L.append('MUSPLAY equ &8B03')     # reproductor: tocar 1 frame
    L.append('MUSSTOP equ &8B06')     # reproductor: parar
    L.append('CASOPEN equ &BC77')
    L.append('CASDIR equ &BC83')
    L.append('CASCLOSE equ &BC7A')
    L.append('TXTWIN equ &BB66')
    L.append('SCANTGO equ %d'%SCANTGO)
    L.append('SEXITS equ %d'%SEXITS)
    L.append('SNOUND equ %d'%SNOUND)
    L.append('SSEE equ %d'%SSEE)
    L.append('STAKE equ %d'%STAKE)
    L.append('SDROP equ %d'%SDROP)
    L.append('SNOTHERE equ %d'%SNOTHERE)
    L.append('SNOTCARR equ %d'%SNOTCARR)
    L.append('SINVEN equ %d'%SINVEN)
    L.append('SEMPTY equ %d'%SEMPTY)
    L.append('SNOTAKE equ %d'%SNOTAKE)
    L.append('SDARK equ %d'%SDARK)
    L.append('SSCORE equ %d'%SSCORE)
    L.append('SHEAVY equ %d'%SHEAVY)
    L.append('CARRIED equ %d'%CARRIED)
    L.append('NOWHERE equ %d'%NOWHERE)
    L.append('WORN equ %d'%WORN)
    L.append('CONTAINED equ %d'%CONTAINED)
    prefix=chr(10).join(L)+chr(10)
    return z80asm.assemble(prefix+ENGINE_ASM, org=org)
