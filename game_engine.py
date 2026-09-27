# -*- coding: utf-8 -*-
"""Motor nativo CPC - Fase 3b: localizaciones, parser, movimiento, mirar, objetos."""
import txtpack

ORG=0x4000; DB=0x8000; TXT=0xBB5A; KMWAIT=0xBB06
# mensajes de sistema (indices fijos)
SCANTGO=0; SEXITS=1; SNOUND=2; SSEE=3; STAKE=4; SDROP=5
SNOTHERE=6; SNOTCARR=7; SINVEN=8; SEMPTY=9; SNOTAKE=10; SDARK=11; SSCORE=12
SHEAVY=13
SSCOREP=14                       # prefijo de "+N puntos" (ADDSCORE)
SSCORES=15                       # sufijo de "+N puntos"
SFIN=16                          # cierre de partida (END), prefijo de la puntuacion
SOTRA=17                         # "pulsa una tecla para jugar otra vez"
SNADAC=18                        # COGER TODO sin nada que coger
SNADAD=19                        # DEJAR TODO sin nada que dejar
SOSCHAY=20                       # COGER TODO a oscuras
SVACIO=21                        # ENTER sin nada (linea_vacia, configurable por juego)
NSYS=22
NRAM=64                          # tamano de las matrices de estado en RAM
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
 'TIMER':27,'HASOBJOPEN':28,'NOUN2':29,'ISIN':30,'ENTERED':31}
# condacts extra: LETX (var,expr) e IF (expr -> salta cuerpo si falso)
COP_EXTRA={'SHOWPIC':50,'PRVAR':51,'ENDGAME':52,
 'BRIGHT':53,'FLASH':54,'INVERSE':55,'SAMPLE':56,'QUIT':57,'SCR':58,'SCRLOC':59,
 'LETX':26,'IF':27,'JMP':28,
 'INK':29,'PAPER':30,'BORDER':31,'PAUSE':32,'CLS':33,
 'WEAR':34,'REMOVE':35,'LIT':36,'UNLIT':37,'SCORE':38,
 'TSTART':39,'TSTOP':40,'TRESET':41,
 'OPEN':42,'CLOSE':43,'LOCK':44,'UNLOCK':45,'PUTIN':46,'TAKEOUT':47,
 'PLAY':48,'ADDSCORE':49}
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

def empaqueta_en_bancos(trozos, tam=16384, bancos=None):
    """Coloca trozos seguidos en bancos de `tam` bytes sin que ninguno cruce
    de un banco al siguiente. Devuelve (bancos, [(indice_de_banco, desplazamiento)]).
    `bancos` es una lista de bytearray que se puede traer ya empezada: asi la
    musica se pone detras del texto en el hueco que este deje."""
    bancos = bancos if bancos is not None else []
    donde = []
    for t in trozos:
        if len(t) > tam:
            raise ValueError('un trozo de %d bytes no cabe en un banco de %d'
                             % (len(t), tam))
        if not bancos or len(bancos[-1]) + len(t) > tam:
            bancos.append(bytearray())
        donde.append((len(bancos) - 1, len(bancos[-1])))
        bancos[-1] += t
    return bancos, donde


def build_game_db(messages, locations, vocab, objects, responses, startloc, sysverbs, width=40, load=DB, proc_before=b'', proc_after=b'', proc_onstart=b'', title_pal=b'', has_music=False, has_title=False, hdrbuf=0, imgbuf=0, loc_slot=b'', vall=0, font_acc=b'', timers=(), llevarmax=0, fx=b'', exit_names=None, texto=None):
    """La base de datos del juego, como la lee el motor.

    `texto`: None (48K, y el CPC cuando le cabe todo) deja los mensajes dentro,
    en el mapa plano. En el 128K y el Next se pasa dict(ventana=&C000,
    tam=16384, ids=[...]) y los mensajes -y el blob de FX- se van a BANCOS: la
    DB guarda por mensaje su direccion dentro de la ventana y el banco que hay
    que paginar (la tabla msgbnk, con los `ids` tal como los espera TXTPAGE en
    esa maquina). Lo que hay que meter en cada banco vuelve en
    info['bancos_texto'], sin rellenar. El diccionario BPE y el indice se
    quedan en la DB plana: son pequeños y el motor los necesita al mismo
    tiempo que el mensaje.
    El CPC 6128 pasa ademas `plano` (los numeros de mensaje que se quedan en
    la DB plana, con banco 0: los que caben en la RAM base; el resto va a los
    bancos) y `fx_plano` (los FX, en la DB: se tocan fuera de TXTPAGE).
    """
    # Las matrices de estado del motor (FLAGS, OBJLOC, OBJLIT, OBJOPEN, OBJLOCK,
    # OBJIN) son 'defs 64' fijos, asi que pasarse no da error: escribe encima de
    # la siguiente. Mejor parar aqui que depurar luego por que se mueve solo un
    # objeto al encender una linterna.
    if len(objects)>NRAM:
        raise ValueError('el motor nativo admite %d objetos como mucho, y el '
                         'juego trae %d' % (NRAM, len(objects)))
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
    HDR=89
    p=load+HDR
    dictidx=p; p+=ntok*2
    ddat=p; dptr=[]; dd=bytearray()
    for s in exps: dptr.append(ddat+len(dd)); dd+=s.encode('latin-1')+b'\x00'
    p=ddat+len(dd)
    msgidx=p; p+=nmsg*2
    bancos_texto=[]; mbnk=[]; fx_en_banco=None
    if texto is None:
        mdat=p; mptr=[]; md=bytearray()
        for t in toks: mptr.append(mdat+len(md)); md+=bytes(t)+b'\x00'
        p=mdat+len(md)
        msgbnk=0
    else:
        # a bancos: cada mensaje entero en uno, y detras de ellos los FX
        ventana=texto['ventana']; ids=list(texto['ids'])
        plano=set(texto.get('plano') or ())
        fx_banco=bool(fx) and not texto.get('fx_plano')
        banc=[i for i in range(nmsg) if i not in plano]
        trozos=[bytes(toks[i])+b'\x00' for i in banc]+([bytes(fx)] if fx_banco else [])
        bancos_texto,donde=empaqueta_en_bancos(trozos, texto.get('tam',16384))
        if len(bancos_texto)>len(ids):
            raise ValueError('el texto ocupa %d bancos y la maquina solo da %d'
                             % (len(bancos_texto), len(ids)))
        mptr=[0]*nmsg; mbnk=[0]*nmsg
        for k,i in enumerate(banc):
            mptr[i]=ventana+donde[k][1]; mbnk[i]=ids[donde[k][0]]
        if fx_banco: fx_en_banco=(ids[donde[len(banc)][0]], ventana+donde[len(banc)][1])
        # los que se quedan en la DB (banco 0), detras del indice
        mdat=p; md=bytearray()
        for i in range(nmsg):
            if i in plano:
                mptr[i]=mdat+len(md); md+=bytes(toks[i])+b'\x00'
        p=mdat+len(md)
        msgbnk=p; p+=nmsg
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
    # Cuerpos compartidos: dos entradas con el mismo cuerpo (las alternativas
    # de un ON, o dos reglas identicas) lo guardan una vez. La segunda lleva
    # longitud 0 y un puntero al byte de longitud de la primera (el motor lo
    # resuelve en run_response). Un cuerpo vacio seria confundible con un
    # alias, asi que se sustituye por un opcode nulo (63: >= 60, el motor
    # lo salta) que no marca la orden como atendida, igual que antes.
    _cuerpos={}
    for _r in responses:
        # (verbo, sustantivo1, cuerpo) o (verbo, sustantivo1, sustantivo2,
        # cuerpo). 0 = ranura no declarada (vale cualquier cosa), 254 = '_'
        # (hueco vacio: no puede haber palabra), 255 = '*' (cualquiera o
        # ninguna), y si no, el id del sustantivo.
        if len(_r)==4: vb,nn,n2,cl=_r
        else:          (vb,nn,cl),n2=_r,0
        cb=bytes(cl) if isinstance(cl,(bytes,bytearray)) else enc_condacts(cl)
        if not cb: cb=bytes([63])
        if len(cb)>255:
            raise ValueError('una respuesta compila a %d bytes y el motor nativo admite 255 como mucho: parte el bloque ON en dos'%len(cb))
        rbytes.append(vb&0xFF); rbytes.append(nn&0xFF); rbytes.append(n2&0xFF)
        if cb in _cuerpos:
            _dir=_cuerpos[cb]
            rbytes.append(0); rbytes.append(_dir&0xFF); rbytes.append((_dir>>8)&0xFF)
        else:
            _cuerpos[cb]=resptab+len(rbytes)
            rbytes.append(len(cb)&0xFF); rbytes+=cb
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
    vid_name = exit_names if exit_names else {1: 'N', 2: 'S', 3: 'E', 4: 'O', 5: 'Subir', 6: 'Bajar'}
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
    # mensaje inicial por objeto (indice de mensaje, 0 = no tiene)
    objinit_a = p; p += nobj*2
    # nombre de cada localizacion (indice de mensaje, 0 = sin nombre)
    locname_a = p; p += nloc*2
    # descripcion por objeto (indice de mensaje, 0 = no tiene); sin tabla
    # si ningun objeto la trae (el export la omite cuando no cabe)
    objdesc_a = 0
    if any(o.get('desc') for o in objects):
        objdesc_a = p; p += nobj*2
    # ── efectos de sonido FX (blob AY: [nfx][offsets][bloques]); 0 si no hay ──
    if fx_en_banco:
        fxbnk, fx_addr = fx_en_banco          # en su banco, detras del texto
    else:
        fxbnk = 0
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
    w16(objinit_a)                                              # 82 (mensaje inicial)
    w16(locname_a)                                              # 84 (nombre de loc)
    w16(msgbnk)                                                 # 86 (banco por mensaje; 0 = texto plano)
    out.append(fxbnk & 0xFF)                                    # 87 (banco de los FX; 0 = planos)
    w16(objdesc_a)                                              # 89 (descripcion por objeto; 0 = sin tabla)
    assert len(out)==HDR, len(out)
    for x in dptr: w16(x)
    out+=dd
    for x in mptr: w16(x)
    out+=md
    out+=bytes(mbnk)
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
    for o in objects:
        _mi=o.get('init',0)&0xFFFF
        out.append(_mi&0xFF); out.append((_mi>>8)&0xFF)
    for L in locations:
        _ln=L.get('name',0)&0xFFFF
        out.append(_ln&0xFF); out.append((_ln>>8)&0xFF)
    if objdesc_a:
        for o in objects:
            _d=o.get('desc',0)&0xFFFF
            out.append(_d&0xFF); out.append((_d>>8)&0xFF)
    if not fx_en_banco: out+=bytes(fx)
    return bytes(out), dict(load=load,ntok=ntok,nmsg=nmsg,nloc=nloc,nvocab=nvocab,nobj=nobj,ntimers=nt,size=len(out),
                            bancos_texto=bancos_texto,
                            msg_tam=[len(t)+1 for t in toks])

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
gameover:                      ; etiqueta para el arnes de pruebas: aqui, y solo
        ; aqui, se sabe que la partida ha terminado (antes solo se notaba porque
        ; 'start' hacia RET, y ya no lo hace).
        ; Se acabo la partida. Volver aqui con un RET deja al jugador en el
        ; BASIC de la maquina -- en Next, el copyright de Sinclair Research; en
        ; cinta, teniendo que recargar -- que es lo que hacia hasta la v2.53.
        ; Una aventura de los ochenta ofrece otra partida, y eso es 'jp start':
        ; init reinicia variables, objetos y temporizadores desde la base de
        ; datos, que es lo mismo que hace el #RESET del modo prueba.
        call  newline
        ld    de,SOTRA
        call  print_msg
        call  KMW
        ; Pantalla limpia antes de volver: si no, la portada del 128/Next se
        ; levanta sobre el texto de la partida anterior y, en el 48K -- que no
        ; tiene portada que repintar -- la partida nueva empieza debajo del
        ; "FIN DEL JUEGO" de la anterior.
        ld    a,12
        call  TXTO
        xor   a
        ld    (col),a
        jp    start

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
        ld    hl,(DBB+80)
        ld    (objinitp),hl   ; mensajes iniciales de objeto (0 = no tiene)
        ld    hl,(DBB+82)
        ld    (locnamep),hl   ; nombres de localizacion (0 = sin nombre)
        ld    hl,(DBB+84)
        ld    (msgbnk),hl     ; banco por mensaje (0 = el texto es plano)
        ld    hl,(DBB+87)
        ld    (objdescp),hl   ; descripciones de objeto (0 = sin tabla)
        ld    a,(DBB+86)
        ld    (fxbnk),a       ; banco de los FX (0 = planos)
        ld    hl,(DBB+20)
        ld    (objnounp),hl
        ld    hl,(DBB+22)
        ld    (objlocsrc),hl
        ld    hl,(DBB+51)
        ld    (objfixp),hl
        ld    hl,(DBB+53)
        ld    (locdarkp),hl
        ld    hl,(DBB+55)
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
        ld    hl,(DBB+57)
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
        ld    (scrfull),a
        ld    hl,LOCSCR        ; ninguna sala con pantalla reasignada (SCR @sala)
        ld    a,(nloc)
        ld    b,a
        ld    a,255
init_l: ld    (hl),a
        inc   hl
        djnz  init_l
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
        ld    a,(quitf)      ; END dentro de before_turn: se acabo aqui mismo,
        or    a              ; igual que hace el interprete de PC
        jr    nz,ml_fin
        call  dispatch
        ld    a,(quitf)      ; END dentro de una respuesta (o el verbo SALIR):
        or    a              ; ni after_turn ni temporizadores
        jr    nz,ml_fin
        ld    hl,(afterp)
        call  run_proc
        ld    a,(curloc)      ; cerrado el turno, ya no es "recien entrado"
        ld    (prevloc),a
        call  tick_timers
        ld    a,(quitf)
        or    a
        jr    z,mainloop
ml_fin: ret

dispatch:
        call  run_response
        or    a
        ret   nz
        ld    a,(verbid)
        ld    b,a
        or    a
        jp    z,d_vacio       ; sin verbo: linea vacia o "No entiendo"
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
; Sin verbo reconocido. Si la linea estaba vacia (ENTER sin nada, o solo
; espacios) sale SVACIO, que cada juego redacta a su manera ("El tiempo
; pasa."); si tenia palabras que el parser no conoce, el "No entiendo" de
; siempre. El turno corre igual en los dos casos: after_turn y temporizadores.
d_vacio:
        ld    hl,INBUF
dv_l:   ld    a,(hl)
        or    a
        jr    z,dv_si
        cp    32
        jr    nz,d_nound
        inc   hl
        jr    dv_l
dv_si:  call  newline
        ld    de,SVACIO
        call  print_msg
        ret
d_nound:
        call  newline
        ld    de,SNOUND
        call  print_msg
        ret

describe:
        call  scr_rest        ; si habia una pantalla entera puesta, fuera
        call  loc_scr         ; la imagen de la sala (o la que le puso SCR @sala)
        call  newline
        ld    a,(curloc)      ; nombre de la localizacion, antes que nada (y
        call  locname_get     ; tambien a oscuras, como en el resto de motores)
        ld    a,d
        or    e
        jr    z,d_nonom
        call  print_msg
        call  newline
d_nonom:
        call  is_dark
        or    a
        jp    nz,d_dark
        ld    a,(curloc)
        call  loc_record
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        push  hl               ; HL apunta al numero de salidas del registro;
        call  print_msg        ; descripcion
        call  list_here        ; objetos que hay aqui
        call  newline
        call  newline          ; una linea en blanco: las salidas, aparte
        ld    de,SEXITS        ; y las salidas al final, como en el export de
        call  print_msg        ; 128K: descripcion, objetos, salidas
        pop   hl               ; ...se recupera aqui, que print_msg se lo lleva
        ld    a,(hl)
        inc   hl
        ld    b,a
        or    a
        ret   z
d_ex:   ld    a,(hl)
        inc   hl
        push  hl
        push  bc
        call  print_word_id
        pop   bc
        pop   hl
        inc   hl
        djnz  d_ex
        ret
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
        ld    hl,MTABLE        ; tabla de matrices (en los 32K centrales)
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
        xor   a
        ld    (oidx),a
lh_l:   push  bc
        ld    a,(oidx)
        call  objloc_get
        ld    c,a
        ld    a,(curloc)
        cp    c
        jr    nz,lh_sk         ; el objeto no esta aqui
        ld    a,(oidx)
        call  objinit_get      ; DE = mensaje inicial del objeto
        ld    a,d
        or    e
        jr    nz,lh_ini
        ; Sin mensaje inicial: si es fijo (escenario, PNJ) no se lista, porque se
        ; da por hecho que la descripcion de la sala ya lo menciona.
        ld    a,(oidx)
        call  objfix_get
        or    a
        jr    nz,lh_sk
        jr    lh_nom
lh_ini:
        ; Con mensaje inicial: vale siempre si es fijo, y si no lo es solo
        ; mientras siga donde lo dejo el autor. Una vez movido pasa a listarse
        ; por su nombre, como en PAW.
        push  de
        ld    a,(oidx)
        call  objfix_get
        or    a
        jr    nz,lh_pon
        ld    a,(oidx)
        call  objorig_get
        ld    c,a
        ld    a,(curloc)
        cp    c
        jr    nz,lh_mov
lh_pon: pop   de
        call  newline
        call  print_msg
        jr    lh_sk
lh_mov: pop   de
lh_nom: call  newline
        ld    de,SSEE
        call  print_msg
        ld    a,(oidx)
        call  print_objname
lh_sk:  ld    a,(oidx)
        inc   a
        ld    (oidx),a
        pop   bc
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
        jr    z,dg_aqui
        cp    CONTAINED       ; dentro de un contenedor: vale si se alcanza
        jr    nz,dg_nx
        ld    a,(oidx)
        call  obj_present
        or    a
        jr    z,dg_nx
dg_aqui:
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
dg_all: call  is_dark         ; a oscuras no se ve que hay (como en PC)
        or    a
        jr    z,dga_luz
        call  newline
        ld    de,SOSCHAY
        jp    print_msg
dga_luz:
        xor   a
        ld    (oidx),a
        ld    (dgcnt),a       ; dgcnt = nº de objetos cogidos (ctmp lo usa
                              ; obj_present, que se llama en el bucle)
dga_l:  ld    a,(oidx)
        ld    hl,nobj
        cp    (hl)
        jr    nc,dga_e        ; recorridos todos
        ld    a,(oidx)
        call  objloc_get
        ld    hl,curloc
        cp    (hl)
        jr    z,dga_aqui      ; suelto en la sala
        cp    CONTAINED       ; o dentro de un contenedor abierto y presente:
        jr    nz,dga_nx       ; "coger todo" coge todo lo que se pueda coger
        ld    a,(oidx)
        call  obj_present
        or    a
        jr    z,dga_nx
dga_aqui:
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
        ld    a,(dgcnt)
        inc   a
        ld    (dgcnt),a
dga_nx: ld    a,(oidx)
        inc   a
        ld    (oidx),a
        jr    dga_l
dga_e:  ld    a,(dgcnt)
        or    a
        ret   nz             ; cogio algo
        call  newline        ; nada que coger (antes decia "No ves eso aqui")
        ld    de,SNADAC
        jp    print_msg

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
        call  newline        ; nada que dejar (antes decia "No llevas eso")
        ld    de,SNADAD
        jp    print_msg

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
        call  newline         ; un objeto por linea, "  - nombre", como en PC
        ld    a,32
        call  char_raw
        ld    a,32
        call  char_raw
        ld    a,'-'
        call  char_raw
        ld    a,32
        call  char_raw
        ld    a,(oidx)
        call  print_objname
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
        call  objdesc_get     ; DE = descripcion del objeto (0 = no tiene)
        ld    a,d
        or    e
        jr    z,dx_nom
        jp    print_msg
dx_nom: ld    a,(oidx)
        call  print_objname   ; sin descripcion: el nombre, como siempre
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
; objinit_get: A = objeto -> DE = indice del mensaje inicial (0 = no tiene)
objinit_get:
        ld    e,a
        ld    d,0
        ld    hl,(objinitp)
        ld    a,h
        or    l
        jr    z,oig_no        ; el juego no trae tabla de mensajes iniciales
        ex    de,hl           ; HL = indice, DE = tabla
        add   hl,hl           ; indice*2 (entradas de 16 bits)
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ret
oig_no: ld    de,0
        ret
; objdesc_get: A = objeto -> DE = indice del mensaje de descripcion (0 = no
; tiene, o el juego no trae la tabla: el 48K la deja fuera cuando no cabe)
objdesc_get:
        ld    e,a
        ld    d,0
        ld    hl,(objdescp)
        ld    a,h
        or    l
        jr    z,oig_no
        ex    de,hl
        add   hl,hl
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ret
; locname_get: A = localizacion -> DE = indice del mensaje de su nombre (0 = sin)
locname_get:
        ld    e,a
        ld    d,0
        ld    hl,(locnamep)
        ld    a,h
        or    l
        jr    z,lng_no
        ex    de,hl           ; HL = indice, DE = tabla
        add   hl,hl
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ret
lng_no: ld    de,0
        ret
; objorig_get: A = objeto -> A = localizacion donde lo puso el autor
objorig_get:
        ld    e,a
        ld    d,0
        ld    hl,(objlocsrc)
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

; expand_msg: DE = numero de mensaje -> el texto expandido en BUF, HL = BUF,
; BC = longitud. En 128K y Next los mensajes viven en bancos: msgbnk dice, por
; mensaje, cual, y TXTPAGE (capa de plataforma) lo trae a la ventana de &C000
; ANTES de seguir el puntero del indice. El indice y el diccionario BPE estan en
; la DB plana, asi que da igual que banco quede puesto al terminar: nada de lo
; que el motor necesita siempre vive en la ventana. En 48K y CPC msgbnk es 0 y
; el texto es plano, como siempre.
expand_msg:
        ld    h,d
        ld    l,e
        ld    bc,(msgbnk)
        ld    a,b
        or    c
        jr    z,em_pl
        push  hl
        add   hl,bc
        ld    a,(hl)          ; A = banco de este mensaje
        pop   hl
        call  TXTPAGE         ; conserva HL
em_pl:  add   hl,hl
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
        ld    b,a             ; verbo que pide la regla
        inc   hl
        ld    c,(hl)          ; sustantivo 1
        inc   hl
        ld    a,(hl)
        ld    (rnoun2),a      ; sustantivo 2
        inc   hl
        ld    a,(hl)          ; longitud del cuerpo
        inc   hl
        or    a
        jr    nz,rr_len
        ; Longitud 0 = alias: los dos bytes siguientes apuntan al byte de
        ; longitud de otra entrada, cuyo cuerpo se comparte. Asi las reglas
        ; con alternativas (A OR B) y las que repiten cuerpo lo guardan una
        ; sola vez (build_game_db los deduplica).
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        ld    (rnext),hl
        ex    de,hl
        ld    a,(hl)
        inc   hl
        ld    e,a
        ld    d,0
        jr    rr_chk
rr_len: ld    e,a
        ld    d,0
        push  hl
        push  de
        add   hl,de
        ld    (rnext),hl
        pop   de
        pop   hl
rr_chk: ld    a,(verbid)
        cp    b
        jr    nz,rr_nx
        push  de              ; DE = longitud del cuerpo, la quiere run_condacts
        ld    a,(nounid)
        ld    b,a
        ld    a,c
        call  rr_casa
        pop   de
        jr    nz,rr_nx
        push  de
        ld    a,(nounid2)
        ld    b,a
        ld    a,(rnoun2)
        call  rr_casa
        pop   de
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

; rr_casa: A = lo que pide la regla, B = lo que tecleo el jugador. Vuelve con Z
; si casan, y sin tocar DE ni HL, que llevan el cuerpo y su longitud.
; Comodines del manual: '_' (254) es hueco vacio, o sea que NO puede haber
; palabra; '*' (255) es cualquier palabra o ninguna; y 0 es la ranura que la
; regla no declara, que tambien vale para todo.
rr_casa:
        or    a
        ret   z               ; 0  -> la regla no pide nada ahi
        cp    255
        jr    z,rrc_si        ; *  -> cualquier palabra o ninguna
        cp    254
        jr    z,rrc_vacio     ; _  -> tiene que no haber palabra
        cp    b
        ret
rrc_vacio:
        ld    a,b
        or    a
        ret
rrc_si: xor   a
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
        cp    60
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
        call  newline        ; en linea nueva, como MESSAGE: si no, la
                             ; puntuacion sale pegada al eco de la orden
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

; ENDGAME (el condact END del autor): cierra la partida. Imprime el remate con
; la puntuacion y levanta quitf, que es lo que mira mainloop para salir. Hasta
; v2.53 END se compilaba a DONE, que solo significa "esta entrada ha acertado,
; siguiente turno": el texto del final salia y el juego seguia, asi que en
; maquina real ninguna aventura terminaba nunca.
c_endgame:
        call  newline
        call  getop          ; indice del flag PUNTOS
        call  flag_addr
        ld    a,(hl)
        push  af
        ld    de,SFIN
        call  print_msg
        pop   af
        call  print_dec
        call  newline
        ld    a,1
        ld    (quitf),a
        jp    rc_handled     ; END corta el bloque en seco, como en PC: lo que
                             ; venga detras en la respuesta ya no se ejecuta
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
        cp    32
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
; ENTERED: cierto si el jugador ha cambiado de sala en este turno. Es lo que
; permite compilar los on_enter del autor sin tocar el formato de la base de
; datos: nativecc los sintetiza en after_turn con este predicado delante.
; prevloc arranca a 255 para que la sala inicial tambien cuente como entrada.
ex_entered:
        ld    a,(curloc)
        ld    hl,prevloc
        cp    (hl)
        jp    nz,ex_t
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
; ex_isin: obj dentro del contenedor C -> OBJLOC[obj]=CONTAINED y OBJIN[obj]=C+1
ex_isin:
        call  getop          ; obj
        ld    (ctmp),a
        call  obj_addr
        ld    a,(hl)
        cp    CONTAINED
        jr    nz,exin_no
        ld    a,(ctmp)
        call  objin_get      ; a = contenedor+1 (0 = ninguno)
        ld    c,a
        call  getop          ; contenedor
        inc   a
        cp    c
        jp    z,ex_t
        jp    ex_f
exin_no:
        call  getop          ; hay que consumir el operando igual
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
exn_any:                 ; '*' = cualquier palabra o ninguna
        jp    ex_t
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
e2_any: jp    ex_t         ; '*' = cualquier palabra o ninguna
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
        defw ex_noun2,ex_isin,ex_entered
; c_prvar: imprime el valor de una variable en decimal, donde este el cursor.
; Es la mitad que le faltaba a PRINT "...{_VARIABLE}...": nativecc parte el
; texto por las llaves y va alternando trozo de mensaje y variable.
c_prvar:
        call  getop
        call  flag_addr
        ld    a,(hl)
        call  print_dec
        jp    rc_loop
; LETX e IF guardan su operando en un sitio propio (iftmp) y no en ctmp:
; eval_expr pasa por obj_present (PRESENT/ABSENT), que usa ctmp de borrador,
; y un "IF PRESENT #x" falso saltaba tantos bytes como el indice del objeto
; en vez de la longitud del cuerpo (Scriba 2.10).
c_letx: call  getop
        ld    (iftmp),a
        call  eval_expr
        ld    c,a
        ld    a,(iftmp)
        call  flag_addr
        ld    (hl),c
        jp    rc_loop
c_if:   call  getop
        ld    (iftmp),a
        call  eval_expr
        or    a
        jp    nz,rc_loop
        ld    a,(iftmp)
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
; BRIGHT / FLASH / INVERSE: atributos de pantalla del Spectrum. Los tres pasan
; por SCRATTR, que los resuelve cada plataforma: en Spectrum y Next son bits del
; atributo (y el impresor complementa el glifo para INVERSE), y en el CPC, que
; no los tiene, SCRATTR es un RET. Hasta v2.53 estos tres condacts ni existian
; en el motor nativo: nativecc los rechazaba y Apolo 11 los perdia.
;   A = 0 BRIGHT, 1 FLASH, 2 INVERSE     C = valor (0/1)
c_bright:
        call  getop
        ld    c,a
        xor   a
        call  SCRATTR
        jp    rc_loop
c_flash:
        call  getop
        ld    c,a
        ld    a,1
        call  SCRATTR
        jp    rc_loop
c_inverse:
        call  getop
        ld    c,a
        ld    a,2
        call  SCRATTR
        jp    rc_loop

; SAMPLE n: reproduce la muestra digitalizada n (1-based) por el AY. Como
; BRIGHT y compania, va por un simbolo de plataforma: donde no hay AY -- el 48K
; y el CPC -- SMPPLAY es un RET y el condact no hace nada.
c_sample:
        call  getop
        call  SMPPLAY
        jp    rc_loop

; QUIT: acaba la partida SIN el remate que imprime END. Es lo que hace el
; interprete de PC (running = False y ya), y lo que hace el verbo SALIR.
c_quit: ld    a,1
        ld    (quitf),a
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
c_cls:  call  scr_rest        ; una pantalla entera (SCR) se va con el CLS
        ld    a,12            ; CLS: borra la ventana de texto actual
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
        ld    a,(fxbnk)
        or    a
        call  nz,TXTPAGE      ; los FX en su banco (128K, Next); conserva BC
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
; ADDSCORE: suma n al flag PUNTOS y muestra "[+n puntos]" (prefijo+num+sufijo).
; Operandos: índice del flag PUNTOS y n.
c_addscore:
        call  getop          ; índice del flag PUNTOS
        ld    (ctmp),a
        call  getop          ; n
        ld    c,a
        ld    a,(ctmp)
        call  flag_addr      ; HL -> flag
        ld    a,c
        add   a,(hl)
        ld    (hl),a         ; flag += n
        ld    a,c
        push  af
        call  newline        ; en linea nueva, como MESSAGE y SCORE: si no,
                             ; "[+5 puntos]" salia pegado al mensaje anterior
        ld    de,SSCOREP     ; prefijo "[+"
        call  print_msg
        pop   af
        call  print_dec      ; n
        ld    de,SSCORES     ; sufijo " puntos]"
        call  print_msg
        jp    rc_loop        ; sin salto detras: lo pone quien venga despues,
                             ; igual que tras un MESSAGE (asi no queda una
                             ; linea en blanco, que en el PC tampoco la hay)
; SCR n: pinta la pantalla suelta n (0-based; el compilador numera las que usa
; el juego por orden de aparicion). Las hay de 8 filas -el tercio superior,
; como la imagen de una sala, con el texto debajo- y de 24, que tapan todo.
; Quien pinta es SHOWSCR, de la capa de plataforma: cada maquina guarda sus
; pantallas donde guarda las de sala (bancos, disco, o el mapa plano en el 48K)
; y deja puesta la ventana de texto que toque. Entra con A = indice y C = 1 si
; hay que borrar toda la pantalla antes (como al describir una sala) o 0 para
; pintar encima y dejar el texto donde estaba. Devuelve A = 0 (8 filas), 1 (24
; filas) o 255 (esa pantalla no esta en esta maquina: no pinta nada).
; Una pantalla de 24 filas se queda hasta el siguiente CLS o hasta que se
; describe una sala: scr_rest pide entonces a la plataforma que devuelva la
; pantalla a su modo normal (en Next apaga Layer 2, en CPC vuelve a Modo 2).
c_scr:  call  getop
        ld    c,0
        call  SHOWSCR
        cp    255
        jp    z,rc_loop
        ld    (scrfull),a
        jp    rc_loop
; SCR @sala n: a partir de ahora esa sala se describe con la pantalla n en vez
; de con su imagen (LOCSCR, una entrada por sala, 255 = la suya). Si el
; jugador esta en esa sala, se repinta en el acto -- solo la imagen: el texto
; que hubiera debajo se queda.
c_scrloc:
        call  getop           ; sala
        ld    (ctmp),a
        call  getop           ; pantalla
        ld    c,a
        ld    a,(ctmp)
        ld    e,a
        ld    d,0
        ld    hl,LOCSCR
        add   hl,de
        ld    (hl),c
        ld    a,(curloc)
        cp    e
        jp    nz,rc_loop
        call  is_dark
        or    a
        jp    nz,rc_loop      ; a oscuras no se ve: ya saldra al describir
        ld    a,c
        ld    c,0
        call  SHOWSCR
        jp    rc_loop
; loc_scr: lo que llama describe en vez de show_loc_image: si la sala tiene
; pantalla reasignada (y no esta a oscuras), se pinta esa, borrando antes como
; hace la imagen de sala; si no, la imagen de siempre.
loc_scr:
        ld    hl,LOCSCR
        ld    a,(curloc)
        ld    e,a
        ld    d,0
        add   hl,de
        ld    a,(hl)
        cp    255
        jp    z,show_loc_image
        push  af
        call  is_dark
        or    a
        jr    z,ls_ok
        pop   af
        jp    show_loc_image  ; a oscuras: el camino de siempre, sin imagen
ls_ok:  pop   af
        ld    c,1
        call  SHOWSCR
        cp    255
        jp    z,show_loc_image ; esta maquina no la tiene: la de siempre
        ret
scr_rest:
        ld    a,(scrfull)
        or    a
        ret   z
        xor   a
        ld    (scrfull),a
        jp    SCRREST
; c_showpic: pinta la imagen de la localizacion actual sin describirla. Sirve
; para que la portada de la sala este puesta ANTES del mensaje inicial, o sea
; despues de que el on_start del autor haya dejado borde y colores como quiere.
c_showpic:
        call  loc_scr
        jp    rc_loop

CTAB:   defw c_at,c_notat,c_present,c_absent,c_carried,c_notcarr,c_zero,c_notzero,c_eq
        defw c_goto,c_message,c_mes,c_get,c_drop,c_destroy,c_create,c_place,c_set
        defw c_clear,c_let,c_plus,c_minus,c_done,c_desc,c_inven,c_newline
        defw c_letx,c_if,c_jmp
        defw c_ink,c_paper,c_border,c_pause,c_cls
        defw c_wear,c_remove,c_lit,c_unlit
        defw c_score,c_tstart,c_tstop,c_treset
        defw c_open,c_close,c_lock,c_unlock,c_putin,c_takeout
        defw c_play,c_addscore
        defw c_showpic,c_prvar,c_endgame
        defw c_bright,c_flash,c_inverse,c_sample,c_quit,c_scr,c_scrloc

show_title:
        ld    a,(hastitle)
        or    a
        ret   z
        ; La portada la deja puesta el cargador BASIC (MODE 0 + LOAD"TITLE.SCR"),
        ; asi que la primera vez ya esta en pantalla y aqui solo hay que ponerle
        ; la paleta y la musica. Al acabar una partida y empezar otra ya no esta:
        ; el juego ha escrito encima. Entonces hay que volver al Modo 0 y
        ; recargarla del disco -- que es lo que el CPC hace de todas formas con
        ; las imagenes de las salas. Si no hay disco, se sigue sin portada en vez
        ; de dejar al jugador mirando una pantalla en blanco con musica.
        ld    a,(titdone)
        or    a
        jr    z,st_puesta
        xor   a
        call  SCRMODE         ; Modo 0: la portada son 16 colores
        call  st_load
        jr    nc,st_done      ; sin disco: Modo 2, pantalla limpia y a jugar
st_puesta:
        ld    a,1
        ld    (titdone),a
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

; st_load: TITLE.SCR -> pantalla (&C000, 16K en Modo 0). CF=1 ok, CF=0 no esta.
; Mismo camino que sli_loadfile para las imagenes de sala, pero sin pasar por
; imgbuf: la portada no va comprimida, va tal cual a la pantalla.
st_load:
        ld    b,9
        ld    hl,ftitle
        ld    de,(hdrbufp)
        call  CASOPEN
        ret   nc
        ld    hl,&C000
        call  CASDIR
        call  CASCLOSE
        scf
        ret
titdone: defb 0               ; 0 = la portada sigue siendo la que cargo el BASIC

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
msgbnk:   defw 0
fxbnk:    defb 0
locidx:   defw 0
vocabp:   defw 0
objnamep: defw 0
objinitp: defw 0
objdescp: defw 0               ; tabla de descripciones de objeto (0 = sin tabla)
locnamep: defw 0
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
dgcnt:    defb 0
rnoun2:   defb 0
oidx:     defb 0
quitf:    defb 0
scrfull:  defb 0
rndseed:  defw 1
col:      defb 0
respp:    defw 0
iftmp:    defb 0               ; operando de IF/LETX a salvo de obj_present
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
prevloc:  defb 255
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
LOCSCR:   defs LOCSCRN       ; pantalla reasignada por sala (SCR @sala); 255 = la suya
                             ; (LOCSCRN y no NLOC: z80asm no distingue mayusculas y
                             ;  NLOC chocaria con la variable nloc de arriba)
'''

CPC_PLAT_ASM = r'''
; ===========================================================================
;  Añadido SOLO para el Amstrad CPC
; ===========================================================================
; El CPC no tiene atributos de brillo ni parpadeo, ni impresion inversa. El
; condact se compila igual en las cuatro maquinas -- la base de datos es la
; misma -- y aqui simplemente no hace nada. En Spectrum, 128K y Next, SCRATTR
; es una etiqueta de la capa de plataforma (next_nativo.PLAT_ASM).
SCRATTR: ret
SMPPLAY: ret

; ---------------------------------------------------------------------------
; Paginacion. TXT OUTPUT del firmware desplaza la ventana sin esperar a nadie:
; un texto mas largo que la ventana (la presentacion, una descripcion larga)
; se iba por arriba sin dar tiempo a leerlo. TXTO cuenta los saltos de linea
; desde lo ultimo que el jugador ha visto (la orden que ha tecleado, una tecla
; pulsada o un borrado) y, si el salto va a tirar una linea por arriba y ya se
; ha escrito una ventana entera, espera una tecla. Es lo mismo que hacen el
; Spectrum, el Next y el MSX2 (nxmas), y como alli sin aviso: el texto se para.
; ---------------------------------------------------------------------------
TXTO:   cp    10
        jr    z,cto_lf
        cp    12
        jp    nz,TXTFW
        push  af
        xor   a
        ld    (pgcnt),a        ; ventana limpia: la cuenta, a cero
        pop   af
        jp    TXTFW
cto_lf: push  bc
        push  de
        push  hl
        ld    a,(pgcnt)
        inc   a
        jr    z,cto_c          ; se queda en 255
        ld    (pgcnt),a
cto_c:  call  TXTGETCUR        ; L = fila del cursor (1 = la de arriba)
        push  hl
        call  TXTGETWIN        ; L = fila de arriba, E = la de abajo
        ld    a,e
        sub   l
        inc   a                ; A = alto de la ventana
        pop   hl
        cp    l
        jr    nz,cto_no        ; el cursor no esta abajo: el salto no desplaza
        ld    b,a
        ld    a,(pgcnt)
        cp    b
        call  nc,pgwait        ; ya hay una ventana entera sin leer: a esperar
cto_no: pop   hl
        pop   de
        pop   bc
        ld    a,10
        jp    TXTFW
; pgwait: espera una tecla para seguir. Si es una letra (o cualquier cosa que
; se pueda teclear que no sea el espacio), ademas se devuelve al teclado: quien
; ve el texto parado sin prompt suele ponerse a escribir la orden, y asi la
; primera letra no se pierde. ESPACIO, ENTER y demas solo hacen seguir.
pgwait: call  KMWFW
        cp    33
        jr    c,pgw_x
        cp    127
        call  nz,KMRETURN      ; KM CHAR RETURN: la vuelve a leer read_line
pgw_x:  xor   a
        ld    (pgcnt),a
        ret
; KMW: espera una tecla (KM WAIT CHAR). Lo que hubiera en pantalla ya esta leido.
KMW:    call  KMWFW
        push  af
        xor   a
        ld    (pgcnt),a
        pop   af
        ret
pgcnt:  defb  0

; oculta_pal: HL = 16 tintas (o 0). El borde y las 16 tintas, del color de la
; primera: lo que se cargue a la pantalla no se ve dibujarse linea a linea, y
; aparece entero al poner su paleta.
oculta_pal:
        ld    a,h
        or    l
        ld    b,0
        jr    z,op_c
        ld    b,(hl)
op_c:   ld    c,b
        push  bc
        call  SCRBORDER
        pop   bc
        xor   a
op_l:   push  af
        push  bc
        call  SCRINK
        pop   bc
        pop   af
        inc   a
        cp    16
        jr    c,op_l
        ret

; st_mus: MUSIC.BIN otra vez a su sitio (&8B00). Hace falta al empezar otra
; partida: la musica esta en imgbuf, y las imagenes de las salas la han pisado.
; CF=1 ok, CF=0 no esta en el disco.
st_mus: ld    b,9
        ld    hl,fmusic
        ld    de,(hdrbufp)
        call  CASOPEN
        ret   nc
        ld    hl,MUSINIT
        call  CASDIR
        call  CASCLOSE
        scf
        ret
fmusic: defb  "MUSIC.BIN"
; TXTPAGE: A = banco del mensaje (0 = esta en la DB plana) y HL = donde esta
; dentro de la ventana &4000-&7FFF. El banco tapa esa parte de la RAM base
; -- donde viven la DB y el buffer de cabecera --, asi que el mensaje no se
; expande desde ahi: se copia (tokens, hasta el 0) a TBUF, bajo &4000, se
; devuelve la RAM normal y HL queda apuntando a la copia. Con las
; interrupciones cortadas y sin salir de la RAM baja: codigo, TBUF y pila.
; Un juego que cabe entero en la RAM base no pasa nunca por aqui (msgbnk = 0).
TXTPAGE:
        or    a
        ret   z
        di
        push  bc
        push  de
        ld    b,&7F
        ld    c,a
        defb  &ED,&49         ; out (c),c  -> el banco del texto en &4000
        ld    de,TBUF
tp_l:   ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   de
        or    a
        jr    nz,tp_l
        ld    bc,&7FC0
        defb  &ED,&49         ; out (c),c  -> RAM normal
        ei
        pop   de
        pop   bc
        ld    hl,TBUF
        ret

; ---------------------------------------------------------------------------
; Pantallas sueltas (SCR n) en el CPC: del disco, como las de sala.
; SCRT lleva un byte por pantalla, las filas (0 = no esta en este disco, 8 o
; 24), y SCRINKS 16 tintas por pantalla (solo cuentan en las de 24). El fichero
; es SCRnn.SCR: las de 8 filas van como las PICnn (sus 2 tintas y el ZX0, al
; final de imgbuf y de ahi a pantalla, por pinta_pic); las de 24 son una
; pantalla de Modo 0 de 16K que va derecha a &C000, como TITLE.SCR, con su
; paleta. Entra con A = indice y C = 1
; si hay que borrar el texto antes.
; ---------------------------------------------------------------------------
SHOWSCR:
        cp    NSCR
        jp    nc,ss_no
        ld    (ss_borra),bc    ; C, en el byte bajo
        ld    e,a
        ld    d,0
        ld    hl,SCRT
        add   hl,de
        ld    a,(hl)
        or    a
        jp    z,ss_no
        ld    (ss_filas),a
        ld    a,e
        ld    (ss_idx),a
        ld    b,0
ss_dec: cp    10
        jr    c,ss_dd
        sub   10
        inc   b
        jr    ss_dec
ss_dd:  push  af
        ld    a,b
        add   a,48
        ld    (fscr+3),a
        pop   af
        add   a,48
        ld    (fscr+4),a       ; SCRnn.SCR
        ld    a,(ss_borra)
        or    a
        jr    z,ss_pinta
        ld    h,0
        ld    l,0
        ld    d,COLS1
        ld    e,24
        call  TXTWIN
        ld    a,12
        call  TXTO             ; como al describir una sala: el texto, fuera
ss_pinta:
        ld    a,(ss_filas)
        cp    24
        jr    z,ss_ent
        ld    a,1
        call  ss_carga         ; disco -> final de imgbuf
        jp    nc,ss_no
        call  pinta_pic        ; -> tercio superior
        ; la ventana de texto pasa a empezar debajo de la imagen, sin mover el
        ; cursor si ya estaba ahi (TXT GET WINDOW: L = fila de arriba)
        call  &BB69
        ld    a,l
        cp    8
        jr    z,ss_8
        ld    h,0
        ld    l,8
        ld    d,COLS1
        ld    e,24
        call  TXTWIN
        xor   a
        ld    (col),a
ss_8:   xor   a
        ret                    ; A = 0: 8 filas
ss_ent: ld    a,(ss_idx)
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl            ; x16
        ld    de,SCRINKS
        add   hl,de            ; HL = sus 16 tintas
        push  hl
        call  oculta_pal       ; que no se vea cargar, ni con otra paleta
        xor   a
        call  SCRMODE          ; Modo 0: 16 colores, como la portada
        xor   a
        call  ss_carga         ; la pantalla entera, derecha a la RAM de video
        pop   hl
        jr    nc,ss_ent0
        ld    de,(titlepal)
        push  de               ; la paleta de la portada, a salvo: la usa el
        ld    (titlepal),hl    ; reinicio de partida
        call  set_title_pal    ; sus 16 tintas, por la rutina de la portada
        pop   hl
        ld    (titlepal),hl
        ld    a,1
        ret                    ; A = 1: 24 filas; SCRREST vuelve a Modo 2
ss_ent0:
        call  SCRREST          ; sin fichero: Modo 2 y a seguir
        ld    a,255
        ret
ss_no:  ld    a,255
        ret
; ss_carga: SCRnn.SCR por CAS IN. Con A = 0 va derecha a la pantalla (&C000,
; las de 24 filas); si no, al final de imgbuf, como las imagenes de sala.
; CF=1 ok, CF=0 no existe.
ss_carga:
        push  af
        ld    b,9
        ld    hl,fscr
        ld    de,(hdrbufp)
        call  CASOPEN
        pop   de               ; D = la A de entrada (los flags, los de CASOPEN)
        ret   nc
        ld    hl,&C000
        ld    a,d
        or    a
        call  nz,pic_dest      ; BC = longitud -> HL, picsrc, piclen
        call  CASDIR
        call  CASCLOSE
        scf
        ret
; SCRREST: fuera la pantalla entera: Modo 2, tintas del texto y borrado (es lo
; mismo que hace la portada al terminar).
SCRREST:
        jp    st_done
fscr:   defb "SCR00.SCR"
ss_borra: defw 0
ss_filas: defb 0
ss_idx:   defb 0

; ---------------------------------------------------------------------------
; Imagenes (salas y SCR de 8 filas). Fichero = [tinta 2][tinta 3][ZX0 de las
; 64 lineas de 80 bytes, seguidas]. Se carga pegado al final de imgbuf
; (IMGTOP) y se descomprime al principio: la salida va siempre por detras de
; lo que queda por leer (el export lo comprueba al comprimir).
; ---------------------------------------------------------------------------
; pic_dest: tras CAS IN OPEN (BC = longitud del fichero), HL = donde cargarlo.
pic_dest:
        ld    (piclen),bc
        ld    hl,IMGTOP
        or    a
        sbc   hl,bc
        ld    (picsrc),hl
        ret
; pinta_pic: la imagen de picsrc al tercio de arriba de la pantalla. Se
; descomprime entera en imgbuf y se copia linea a linea: en la pantalla del
; CPC cada linea de pixel de una fila de caracteres esta &800 mas alla.
pinta_pic:
        ld    hl,(picsrc)
        ld    de,pictin
        ldi
        ldi                    ; sus dos tintas, a salvo
        ld    de,(imgbufp)
        call  dzx0st
        call  PICNEGRO         ; Modo 1: tintas 2 y 3 a negro mientras se copia
        ld    hl,(imgbufp)
        ld    de,&C000
        ld    b,8              ; 8 filas de caracteres...
pp_f:   push  bc
        push  de
        ld    b,8              ; ...de 8 lineas de pixel
pp_l:   push  bc
        push  de
        ld    bc,80
        ldir
        pop   de
        ld    a,d
        add   a,8
        ld    d,a              ; la linea de pixel siguiente
        pop   bc
        djnz  pp_l
        pop   de
        ex    de,hl
        ld    bc,80
        add   hl,bc            ; la fila de caracteres siguiente
        ex    de,hl
        pop   bc
        djnz  pp_f
        jp    PICTINTA
'''

# Modo 1: las tintas 0 y 1 son las del texto (papel y pluma) y las 2 y 3 las
# pone cada imagen. Mientras se copia una imagen nueva, las 2 y 3 van a negro:
# asi no se ve un instante con los colores de la anterior.
CPC_TINTAS_M1 = r'''
PICNEGRO:
        ld    a,2
        ld    bc,0
        call  SCRINK
        ld    a,3
        ld    bc,0
        call  SCRINK
        jp    MCWAIT
PICTINTA:
        ld    a,(pictin)
        ld    b,a
        ld    c,a
        ld    a,2
        call  SCRINK
        ld    a,(pictin+1)
        ld    b,a
        ld    c,a
        ld    a,3
        jp    SCRINK
'''
# Modo 2: dos colores, los del texto; la imagen no trae tintas.
CPC_TINTAS_M2 = r'''
PICNEGRO:
PICTINTA:
        ret
'''

# dzx0_standard (Einar Saukas & Urusergi): el mismo que spectrum48_nativo.DZX0_ASM.
# HL = flujo comprimido, DE = destino.
CPC_DZX0 = r'''
dzx0st: ld    bc,&FFFF
        push  bc
        inc   bc
        ld    a,&80
dzx0li: call  dzx0el
        ldir
        add   a,a
        jr    c,dzx0no
        call  dzx0el
dzx0cp: ex    (sp),hl
        push  hl
        add   hl,de
        ldir
        pop   hl
        ex    (sp),hl
        add   a,a
        jr    nc,dzx0li
dzx0no: pop   bc
        ld    c,&FE
        call  dzx0lo
        inc   c
        ret   z
        ld    b,c
        ld    c,(hl)
        inc   hl
        rr    b
        rr    c
        push  bc
        ld    bc,1
        call  nc,dzx0bt
        inc   bc
        jr    dzx0cp
dzx0el: inc   c
dzx0lo: add   a,a
        jr    nz,dzx0sk
        ld    a,(hl)
        inc   hl
        rla
dzx0sk: ret   c
dzx0bt: add   a,a
        rl    c
        rl    b
        jr    dzx0lo
'''


# ---------------------------------------------------------------------------
#  El motor del CPC: ENGINE_ASM con lo que solo tiene el CPC puesto al dia.
#  Se hace aqui, sobre el texto, para que el 48K, el 128K y el Next (que
#  parten del mismo ENGINE_ASM) sigan saliendo byte a byte igual.
# ---------------------------------------------------------------------------
def _entre(src, desde, hasta):
    i = src.index(desde)
    j = src.index(hasta, i)
    return i, j


def _engine_cpc(slots):
    src = ENGINE_ASM

    def cambia(viejo, nuevo):
        nonlocal src
        if src.count(viejo) != 1:
            raise RuntimeError('_engine_cpc: no encuentro %r' % viejo[:60])
        src = src.replace(viejo, nuevo)

    # Sin precarga de las salas contiguas. Leia de disco en los ratos sin
    # teclear, con CAS IN, que bloquea: mientras gira el disco (arrancar el
    # motor, el directorio, la imagen: un par de segundos en un 6128 de verdad)
    # el firmware no lee el teclado, asi que lo que el jugador empezaba a
    # escribir no salia en pantalla y ademas se perdian letras ("inventario"
    # llegaba como "ivnario"). Ahora cada imagen se lee al entrar en su sala,
    # que es cuando el jugador ya esta esperando, y se guarda en los bancos del
    # 6128: al volver, sale al instante.
    cambia("""        call  prefetch_init   ; prepara la precarga de salas contiguas
""", "")
    cambia("""        call  prefetch_one   ; sin tecla: precarga una sala contigua
""", "")
    cambia("""pf_i:     defb 0
pf_n:     defb 0
pf_exits: defw 0
picloc:   defb 0
""", "")

    # expand_msg: el puntero, ANTES de paginar -- el indice esta en la RAM
    # base, en la misma ventana que tapa el banco del texto.
    i, j = _entre(src, '\nexpand_msg:\n', '        ld    de,BUF\n')
    src = src[:i] + '''
expand_msg:
        ld    h,d
        ld    l,e
        add   hl,hl
        ld    bc,(msgidx)
        add   hl,bc
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a             ; HL = el mensaje (en la ventana, si va en banco)
        ld    bc,(msgbnk)
        ld    a,b
        or    c
        jr    z,em_pl
        ex    de,hl           ; HL = numero de mensaje, DE = puntero
        add   hl,bc
        ld    a,(hl)          ; A = banco de este mensaje (0 = plano)
        ex    de,hl
        call  TXTPAGE         ; lo copia a TBUF y deja HL ahi
em_pl:  ld    de,BUF
''' + src[j + len('        ld    de,BUF\n'):]

    # show_loc_image: la imagen por pinta_pic y la ventana a las columnas del modo
    i, j = _entre(src, '\nshow_loc_image:\n', '\n; sli_loadfile:')
    blk = src[i:j]
    if blk.count('call  depack') != 1 or blk.count('ld    d,79') != 2:
        raise RuntimeError('_engine_cpc: show_loc_image ha cambiado')
    blk = blk.replace('call  depack', 'call  pinta_pic').replace('ld    d,79', 'ld    d,COLS1')
    # A oscuras no se ve la sala, ni su imagen: como en Spectrum, Next, MSX2 y
    # PCW. La ventana pasa a pantalla completa y se borra (sli_noimg), asi que
    # tampoco se queda la imagen de la sala anterior.
    cab = '\nshow_loc_image:\n'
    if not blk.startswith(cab):
        raise RuntimeError('_engine_cpc: show_loc_image ha cambiado')
    blk = (cab + '        call  is_dark\n'
                 '        or    a\n'
                 '        jp    nz,sli_noimg     ; a oscuras no se ve nada\n'
           + blk[len(cab):])
    src = src[:i] + blk + src[j:]

    cambia('''        ld    hl,(imgbufp)
        call  CASDIR
''', '''        call  pic_dest        ; BC = longitud -> HL = sitio al final de imgbuf
        call  CASDIR
''')

    # bank2buf / buf2bank: ranuras a medida, con la longitud delante
    i, j = _entre(src, '; ---- cache de imagenes en bancos extra', '; slotinfo:')
    src = src[:i] + '''; ---- cache de imagenes en bancos extra (CPC 6128) ----
; Cada ranura guarda [longitud][fichero PIC tal cual]; el export las coloca a
; medida en lo que dejan libre los bancos del texto, sin cruzar el final de la
; ventana. Las copias van con las interrupciones cortadas: mientras el banco
; esta en &4000-&7FFF, la RAM base de ahi no se ve.
; bank2buf: ranura (curslot) -> final de imgbuf; deja picsrc y piclen.
bank2buf:
        ld    a,(curslot)
        call  slotinfo        ; A=config banco, HL=direccion en la ventana
        di
        ld    b,&7F
        ld    c,a
        defb  &ED,&49         ; out (c),c  -> pagina el banco extra
        ld    e,(hl)
        inc   hl
        ld    d,(hl)          ; DE = longitud
        inc   hl
        ld    (piclen),de
        push  hl
        ld    hl,IMGTOP
        or    a
        sbc   hl,de
        ld    (picsrc),hl
        ex    de,hl           ; DE = destino, HL = longitud
        ld    b,h
        ld    c,l
        pop   hl
        ldir
        ld    bc,&7FC0
        defb  &ED,&49         ; out (c),c  -> RAM normal
        ei
        ret
; buf2bank: la imagen recien cargada (picsrc, piclen) -> su ranura (curslot).
buf2bank:
        ld    a,(curslot)
        call  slotinfo
        ex    de,hl           ; DE = destino (ventana)
        ld    hl,(picsrc)
        dec   hl
        dec   hl              ; la longitud, delante: 2 bytes libres de imgbuf
        ld    bc,(piclen)
        ld    (hl),c
        inc   hl
        ld    (hl),b
        dec   hl
        inc   bc
        inc   bc
        di
        push  bc
        ld    b,&7F
        ld    c,a
        defb  &ED,&49         ; out (c),c
        pop   bc
        ldir
        ld    bc,&7FC0
        defb  &ED,&49
        ei
        ret
''' + src[j:]

    # la tabla de ranuras, la que salga del reparto de los bancos
    i, j = _entre(src, '\nslottab:\n', '\n; is_pop:')
    tab = ''.join('        defb  &%02X\n        defw  &%04X\n' % (c, d) for c, d in slots)
    src = src[:i] + '\nslottab:\n' + tab.rstrip('\n') + src[j:]
    cambia('populated: defw 0', 'populated: defs 8')

    # detect128 sin romper nada: el cargador BASIC ya ha dejado el texto ahi
    i, j = _entre(src, '; detect128:', '; preload_cache:')
    src = src[:i] + '''; detect128: has128=1 si hay RAM extra (CPC 6128, o 464 ampliado). Escribe
; en &4000 de los bancos 4 y 5 y lo deja todo como estaba, porque el cargador
; BASIC ya ha puesto ahi el texto del juego. Sin RAM extra y con el texto en
; bancos no hay juego: lo dice y se queda ahi (el cargador BASIC ya lo avisa
; antes; esto es por si alguien carga GAME.BIN a mano).
detect128:
        di
        ld    a,(&4000)
        ld    (d128b),a       ; el byte de la RAM base
        ld    bc,&7FC4
        defb  &ED,&49
        ld    a,(&4000)
        ld    (d128b+1),a     ; el del banco 4 (en un 464, el mismo)
        ld    bc,&7FC5
        defb  &ED,&49
        ld    a,(&4000)
        ld    (d128b+2),a     ; el del banco 5
        ld    a,&55
        ld    (&4000),a
        ld    bc,&7FC4
        defb  &ED,&49
        ld    a,&AA
        ld    (&4000),a
        ld    bc,&7FC5
        defb  &ED,&49
        ld    a,(&4000)
        ld    e,a             ; &55 si el banco 5 no es el 4
        ld    a,(d128b+2)
        ld    (&4000),a
        ld    bc,&7FC4
        defb  &ED,&49
        ld    a,(d128b+1)
        ld    (&4000),a
        ld    bc,&7FC0
        defb  &ED,&49
        ld    a,(d128b)
        ld    (&4000),a
        ei
        ld    a,e
        cp    &55
        ld    a,1
        jr    z,d128_si
        ld    hl,(msgbnk)
        ld    a,h
        or    l
        jr    z,d128_si       ; A = 0: sin cache de imagenes, texto plano
        ld    hl,AVISO128
d128_av: ld   a,(hl)
        inc   hl
        or    a
d128_x: jr    z,d128_x
        call  TXTO
        jr    d128_av
d128_si:
        ld    (has128),a
        ret

''' + src[j:]
    # la precarga de todas las imagenes al arrancar ya no se usaba, y la de
    # las salas contiguas tampoco (ver arriba)
    i, j = _entre(src, '; preload_cache:', '; ---- setup_acc')
    src = src[:i] + src[j:]
    # el RLE de antes
    i, j = _entre(src, '\ndepack: ', '\n; ---- list_here')
    src = src[:i] + src[j:]

    # fin de la portada: el modo del juego, sus tintas y el borde del papel
    cambia('''st_done:
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
''', '''st_done:
        ld    a,MODO
        call  SCRMODE
        ld    a,0
        ld    b,TINTA0
        ld    c,TINTA0
        call  SCRINK
        ld    a,1
        ld    b,TINTA1
        ld    c,TINTA1
        call  SCRINK
        ld    b,TINTA0
        ld    c,TINTA0
        call  SCRBORDER
''')

    # Paginacion (TXTO, en CPC_PLAT_ASM): lo que hay por encima del prompt ya
    # lo ha leido el jugador, asi que la cuenta vuelve a empezar desde ahi.
    cambia('''        call  read_line
        call  parse
''', '''        call  read_line
        xor   a
        ld    (pgcnt),a       ; lo de arriba del prompt ya esta leido
        call  parse
''')

    # Otra partida: la portada se vuelve a cargar del disco, pero oculta (sus
    # tintas, todas del color del fondo) -- si no, se veia dibujarse con la
    # paleta del juego --, y la musica tambien: vive en imgbuf y las imagenes
    # de las salas la han pisado. Sin ella, MUSINIT saltaba a basura y el CPC
    # se reiniciaba.
    cambia('''        xor   a
        call  SCRMODE         ; Modo 0: la portada son 16 colores
        call  st_load
        jr    nc,st_done      ; sin disco: Modo 2, pantalla limpia y a jugar
st_puesta:
''', '''        ld    hl,(titlepal)
        call  oculta_pal      ; que no se vea cargar
        xor   a
        call  SCRMODE         ; Modo 0: la portada son 16 colores
        call  st_load
        jr    nc,st_done      ; sin disco: el modo del juego y a jugar
        ld    a,(hasmusic)
        or    a
        jr    z,st_puesta
        call  st_mus          ; la musica, otra vez a imgbuf
        jr    c,st_puesta
        xor   a
        ld    (hasmusic),a    ; no esta: sin musica, mejor que colgarse
st_puesta:
''')
    return src


# Las 12 ranuras de 5120 bytes de antes: lo que sale si no se pasa reparto.
SLOTS_CPC = [(0xC4 + b, 0x4000 + k * 0x1400) for b in range(4) for k in range(3)]


def assemble_engine(org=ORG, db_base=DB, nloc=256, pantallas=None, modo=2,
                    tintas=None, slots=None, tbufn=256, mtable=0x8000,
                    imgtop=0xA67C, aviso128='Necesita un CPC 6128.'):
    """El motor del CPC. pantallas: [(filas, 16 tintas)] de las pantallas
    sueltas del SCR (filas 0 = no esta en el disco), en el orden de
    spec['pantallas']. modo: 1 (40 columnas, 4 colores) o 2 (80, 2).
    tintas: (papel, pluma) del texto, colores del firmware; por defecto los de
    siempre de cada modo. slots: [(config del banco, direccion)] de las
    ranuras de la cache de imagenes. tbufn: lo que ocupa el mensaje mas largo
    (tokens + 0), que es lo que TXTPAGE copia fuera del banco. mtable: la
    tabla de matrices de los acentos (en los 32K centrales). aviso128: lo que
    se escribe si el texto va en bancos y la maquina no tiene RAM extra."""
    import z80asm
    if tintas is None:
        tintas = (0, 26) if modo == 1 else (1, 24)
    L=[]
    L.append('ORIGIN equ &%04X'%org)
    L.append('MODO equ %d'%modo)
    L.append('COLS1 equ %d'%(39 if modo == 1 else 79))
    L.append('TINTA0 equ %d'%(tintas[0] & 31))
    L.append('TINTA1 equ %d'%(tintas[1] & 31))
    L.append('IMGTOP equ &%04X'%imgtop)
    L.append('TBUFN equ %d'%max(1, tbufn))
    L.append('LOCSCRN equ %d'%max(1, nloc))
    L.append('NSCR equ %d'%len(pantallas or ()))
    # TXTO y KMW son rutinas de CPC_PLAT_ASM (la paginacion del texto): las
    # del firmware quedan como TXTFW y KMWFW.
    L.append('TXTFW equ &%04X'%TXT)
    L.append('KMWFW equ &%04X'%KMWAIT)
    L.append('TXTGETCUR equ &BB78')   # TXT GET CURSOR (L = fila logica, 1 arriba)
    L.append('TXTGETWIN equ &BB69')   # TXT GET WINDOW (L = arriba, E = abajo)
    L.append('KMRETURN equ &BB0C')    # KM CHAR RETURN (A = la tecla, otra vez)
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
    L.append('MTABLE equ &%04X'%mtable)  # tabla de matrices de usuario (RAM central)
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
    L.append('SSCOREP equ %d'%SSCOREP)
    L.append('SSCORES equ %d'%SSCORES)
    L.append('SFIN equ %d'%SFIN)
    L.append('SOTRA equ %d'%SOTRA)
    L.append('SNADAC equ %d'%SNADAC)
    L.append('SNADAD equ %d'%SNADAD)
    L.append('SOSCHAY equ %d'%SOSCHAY)
    L.append('SVACIO equ %d'%SVACIO)
    L.append('CARRIED equ %d'%CARRIED)
    L.append('NOWHERE equ %d'%NOWHERE)
    L.append('WORN equ %d'%WORN)
    L.append('CONTAINED equ %d'%CONTAINED)
    prefix=chr(10).join(L)+chr(10)
    tablas=['SCRT:']
    for filas,_t in (pantallas or ()): tablas.append('        defb %d'%filas)
    tablas.append('SCRINKS:')
    for _f,tintas in (pantallas or ()):
        tablas.append('        defb '+','.join(str(t&0xFF) for t in (list(tintas)+[0]*16)[:16]))
    aviso = ''.join(ch for ch in str(aviso128) if 32 <= ord(ch) < 127 and ch != '"')
    vars_cpc = ('picsrc:   defw 0\n'
                'piclen:   defw 0\n'
                'pictin:   defs 2\n'
                'd128b:    defs 3\n'
                'AVISO128: defb "%s",13,10,0\n'
                'TBUF:     defs TBUFN\n' % aviso)
    fuente = (prefix + _engine_cpc(SLOTS_CPC if slots is None else slots) +
              CPC_PLAT_ASM + (CPC_TINTAS_M1 if modo == 1 else CPC_TINTAS_M2) +
              CPC_DZX0 + vars_cpc + chr(10).join(tablas) + chr(10))
    return z80asm.assemble(fuente, org=org)
