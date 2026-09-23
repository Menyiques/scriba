# -*- coding: utf-8 -*-
"""Traductor: bloque de condacts de Scriba (texto) -> bytecode del motor nativo."""
import re, paws_lang as pl, game_engine as ge
COP=ge.COP

class Ctx:
    def __init__(self, msgbase=0):
        self.msgbase=msgbase; self.messages=[]; self.msgmap={}
        self.vars={}; self.locs={}; self.objs={}
        self.verbs={}; self.nouns={}; self.timers={}
        self.strict=False; self.warnings=[]; self.fxlist=[]
    def msg(self,t):
        if t in self.msgmap: return self.msgmap[t]
        i=self.msgbase+len(self.messages); self.messages.append(t); self.msgmap[t]=i; return i
    def var(self,n):
        k=n.upper().replace('_','')
        if k in self.vars: return self.vars[k]
        self.vars[k]=len(self.vars); return self.vars[k]
    def loc(self,n):
        if n in self.locs: return self.locs[n]
        if self.strict: raise KeyError('loc '+n)
        self.locs[n]=len(self.locs); return self.locs[n]
    def obj(self,n):
        for k in (n, n.upper(), n.lower()):
            if k in self.objs: return self.objs[k]
        if self.strict: raise KeyError('obj '+n)
        self.objs[n.upper()]=len(self.objs); return self.objs[n.upper()]

CMP={'=':'EQ','==':'EQ','<>':'NE','!=':'NE','<':'LT','>':'GT'}
def expr_rpn(a,ctx):
    t=a[0]
    if t=='num': return [('CONST',a[1])]
    if t=='var': return [('VAR',ctx.var(a[1]))]
    if t=='bin':
        op={'+':'ADD','-':'SUB'}[a[1]]
        return expr_rpn(a[2],ctx)+expr_rpn(a[3],ctx)+[(op,)]
    raise ValueError('expr no soportada: %r'%(a,))

PREDMAP={'AT':'AT','NOTAT':'NOTAT','ZERO':'ZERO','NOTZERO':'NOTZERO','DARK':'DARK',
 'CARRIED':'CARRIED','NOTCARR':'NOTCARR','PRESENT':'PRESENT','ABSENT':'ABSENT',
 'ISAT':'ISAT','CHANCE':'CHANCE','WORN':'WORN','NOTWORN':'NOTWORN',
 'VERB':'VERB','NOUN1':'NOUN1','NOUN2':'NOUN2','TIMER':'TIMER','HASOBJOPEN':'HASOBJOPEN'}

def _destval(ctx,dst):
    # destino para ISAT: localizacion o sentinel (INVEN/PUESTO/NADA)
    u=str(dst).upper()
    if u in ('INVEN','@INVEN'): return ge.CARRIED
    if u in ('PUESTO','WORN','@ONME'): return ge.WORN
    if u in ('NADA','NOWHERE','@NOWHERE'): return ge.NOWHERE
    return ctx.loc(dst)

def _isat_rpn(ctx,o,dst):
    # ISAT admite tres clases de destino: sentinel, localizacion (@id) y
    # contenedor (#id).  El tercero no cabe en un byte de OBJLOC, porque un
    # objeto dentro de un contenedor guarda OBJLOC=CONTAINED y el contenedor
    # en OBJIN; por eso lleva su propio opcode (ISIN).
    s=str(dst); u=s.upper()
    if u in ('INVEN','@INVEN'):        return [('ISAT',o,ge.CARRIED)]
    if u in ('PUESTO','WORN','@ONME'): return [('ISAT',o,ge.WORN)]
    if u in ('NADA','NOWHERE','@NOWHERE'): return [('ISAT',o,ge.NOWHERE)]
    if s in ctx.locs:                  return [('ISAT',o,ctx.locs[s])]
    if s.startswith('#'):              return [('ISIN',o,ctx.obj(s))]
    return [('ISAT',o,ctx.loc(s))]

def cond_rpn(a,ctx):
    t=a[0]
    if t=='pred':
        nm=a[1]; args=a[2]
        if nm not in PREDMAP: raise ValueError('pred no soportado: '+nm)
        op=PREDMAP[nm]
        if nm in ('AT','NOTAT'): return [(op,ctx.loc(args[0]))]
        if nm in ('ZERO','NOTZERO'): return [(op,ctx.var(args[0]))]
        if nm=='DARK': return [('DARK',)]
        if nm=='ISAT': return _isat_rpn(ctx,ctx.obj(args[0]),args[1])
        if nm=='CHANCE': return [('CHANCE',int(args[0])&0xFF)]
        if nm=='TIMER': return [('TIMER',ctx.timers.get(str(args[0]).upper(),0),int(args[1])&0xFF)]
        if nm in ('WORN','NOTWORN'): return [(op,ctx.obj(args[0]))]
        if nm=='VERB':
            w=str(args[0]); v=255 if w=='*' else ctx.verbs.get(w.upper(),0)
            return [('VERB',v)]
        if nm in ('NOUN1','NOUN2'):
            w=str(args[0])
            v=255 if w=='*' else (254 if w=='_' else ctx.nouns.get(w.upper(),0))
            return [(nm,v)]
        return [(op,ctx.obj(args[0]))]              # CARRIED/PRESENT/ABSENT/NOTCARR
    if t=='cmp':
        op=a[1]; l=expr_rpn(a[2],ctx); r=expr_rpn(a[3],ctx)
        if op in ('<=',): return l+r+[('GT',),('NOT',)]
        if op in ('>=',): return l+r+[('LT',),('NOT',)]
        return l+r+[(CMP[op],)]
    if t=='or':
        subs=a[1]; out=cond_rpn(subs[0],ctx)
        for s in subs[1:]: out+=cond_rpn(s,ctx)+[('OR',)]
        return out
    if t=='and':
        subs=a[1]; out=cond_rpn(subs[0],ctx)
        for s in subs[1:]: out+=cond_rpn(s,ctx)+[('AND',)]
        return out
    if t=='not': return cond_rpn(a[1],ctx)+[('NOT',)]
    raise ValueError('cond no soportada: %r'%(a,))

def _string(ln):
    m=re.search(r'"([^"]*)"',ln)
    return m.group(1) if m else ''

def gather_if(lines,i):
    """devuelve (then_lines, else_lines|None, next_i) tras un IF (lines[i:])."""
    then,els=[],None; cur=then; depth=0
    while i<len(lines):
        ln=lines[i].strip(); up=ln.upper()
        if up.startswith('IF'): depth+=1; cur.append(lines[i]); i+=1; continue
        if up.startswith('ENDIF'):
            if depth==0: return then,els,i+1
            depth-=1; cur.append(lines[i]); i+=1; continue
        if up.startswith('ELSE') and depth==0:
            els=[]; cur=els; i+=1; continue
        cur.append(lines[i]); i+=1
    return then,els,i

def _print_rpn(texto, ctx):
    """PRINT "...{_VARIABLE}..." -> mensaje, variable, mensaje, variable...

    Los exports BASIC parten el texto por las llaves y concatenan STR$(v). Aqui
    se hace lo mismo con condacts: el primer trozo va como MESSAGE (que es el
    que mete el salto de linea de delante), los siguientes como MES, y cada
    variable como PRVAR. Un nombre que el juego no declara se deja tal cual,
    con sus llaves, que es lo que hacia el motor antes de existir PRVAR.
    """
    partes = re.split(r'\{([A-Z_][A-Z0-9_]*)\}', texto)
    if len(partes) == 1:
        mi = ctx.msg(texto)
        return bytes([COP['MESSAGE'], mi & 0xFF, (mi >> 8) & 0xFF])
    out = bytearray()
    primero = True                      # el salto de linea aun no ha salido
    pendiente = ''
    for i, p in enumerate(partes):
        if i % 2 == 0:
            pendiente += p
            continue
        if p.upper().replace('_', '') not in ctx.vars:
            pendiente += '{%s}' % p     # variable desconocida: literal
            continue
        if pendiente:
            mi = ctx.msg(pendiente)
            out += bytes([COP['MESSAGE'] if primero else COP['MES'],
                          mi & 0xFF, (mi >> 8) & 0xFF])
            pendiente = ''
        elif primero:
            out += bytes([COP['NEWLINE']])
        primero = False
        out += bytes([ge.COP_EXTRA['PRVAR'], ctx.var(p)])
    if pendiente or primero:
        mi = ctx.msg(pendiente)
        out += bytes([COP['MESSAGE'] if primero else COP['MES'],
                      mi & 0xFF, (mi >> 8) & 0xFF])
    return bytes(out)


def compile_stmt(ln, up, ctx):
    if up.startswith('PRINT'):
        return _print_rpn(translit(_string(ln)), ctx)
    if up.startswith('LET'):
        m=re.match(r'LET\s+(\w+)\s*=\s*(.+)',ln,re.I)
        v=ctx.var(m.group(1)); eb=ge.enc_expr(expr_rpn(pl.parse_expr(m.group(2)),ctx))
        return bytes([26,v])+eb
    if up.startswith('GOTO'):  return bytes([COP['GOTO'],ctx.loc(ln.split()[1])])
    if up.startswith('CREATE') or up.startswith('DROP') or (up.startswith('PUT') and not up.startswith('PUTIN')):
        # CREATE/PUT/DROP #obj [destino]. Sin destino, el objeto va a la
        # localizacion actual (CREATE/DROP del motor). Con destino -una
        # localizacion o INVEN/PUESTO/NADA- es un PLACE: hasta v2.8 el
        # destino se ignoraba y "CREATE #credencial INVEN" dejaba la
        # credencial en el suelo de la trastienda.
        a=ln.split()
        if len(a)>=3:
            return bytes([COP['PLACE'],ctx.obj(a[1]),_destval(ctx,a[2])&0xFF])
        return bytes([COP['CREATE' if up.startswith('CREATE') else 'DROP'],ctx.obj(a[1])])
    if up.startswith('DESTROY'):return bytes([COP['DESTROY'],ctx.obj(ln.split()[1])])
    if up.startswith('GET'):   return bytes([COP['GET'],ctx.obj(ln.split()[1])])
    if up.startswith('ADDSCORE'):
        try: n=int(ln.split()[1])
        except: n=1
        # suma n a PUNTOS y muestra "[+n puntos]" (c_addscore en el motor).
        return bytes([ge.COP_EXTRA['ADDSCORE'], ctx.var('PUNTOS'), n&0xFF])
    # MATCH y END NO son lo mismo. MATCH dice "esta entrada ha acertado, no
    # sigas mirando" (DONE). END acaba la partida, y hasta v2.53 se compilaba
    # tambien a DONE: el texto del final salia y el juego seguia pidiendo
    # ordenes, o sea que en maquina real no habia forma de terminar.
    if up.startswith('MATCH'): return bytes([COP['DONE']])
    if up == 'END' or up.startswith('END '):     # END exacto: ni ENDIF ni ENDON
        return bytes([ge.COP_EXTRA['ENDGAME'], ctx.var('PUNTOS')])
    # --- comandos de pantalla/tiempo: equivalentes CPC en el motor nativo ---
    # Color Spectrum (0-7) -> color firmware CPC mas parecido (versiones vivas).
    _ZX2CPC = (0, 2, 6, 8, 18, 20, 24, 26)
    def _ints(s):
        out=[]
        for p in s.replace(',', ' ').split():
            try: out.append(int(p))
            except: pass
        return out
    def _col(v):
        return _ZX2CPC[v & 7] if isinstance(v, int) else 0
    CX = ge.COP_EXTRA
    if up.startswith('BORDER'):
        n=_ints(ln[6:]); return bytes([CX['BORDER'], _col(n[0]) if n else 0])
    if up.startswith('PAPER'):
        n=_ints(ln[5:]); return bytes([CX['PAPER'], _col(n[0]) if n else 0])
    if up.startswith('INK'):
        n=_ints(ln[3:]); return bytes([CX['INK'], _col(n[0]) if n else 26])
    # Tres condacts que el motor lleva soportando desde siempre -- sus opcodes
    # estan en COP -- y que nadie habia cableado al lenguaje del autor: se
    # compilaban a NADA y la sentencia desaparecia del binario con un aviso que
    # no siempre se ve.
    if up == 'DESC' or up.startswith('DESC '):
        return bytes([COP['DESC']])
    if up == 'NEWLINE' or up.startswith('NEWLINE '):
        return bytes([COP['NEWLINE']])
    if up == 'QUIT' or up.startswith('QUIT '):
        return bytes([CX['QUIT']])
    if up.startswith('SCR ') or up == 'SCR':
        import capabilities
        args = ln[3:].split()
        sala, n = capabilities.partes_scr(args[0] if args else '',
                                          ' '.join(args[1:]) if len(args) > 1 else '')
        lista = [x.lower() for x in getattr(ctx, 'scrlist', [])]
        if not n or n.lower() not in lista:
            ctx.warnings.append('SCR: pantalla no encontrada %r' % ln[3:].strip())
            return b''
        idx = lista.index(n.lower()) & 0xFF
        if sala is None:
            return bytes([CX['SCR'], idx])
        if sala not in ctx.locs:
            ctx.warnings.append('SCR: localizacion desconocida %r' % sala)
            return b''
        return bytes([CX['SCRLOC'], ctx.locs[sala] & 0xFF, idx])
    if up.startswith('SAMPLE'):
        import fx_engine
        idx = fx_engine.fx_index(getattr(ctx, 'smplist', []), ln[6:].strip())
        if not idx:
            ctx.warnings.append('SAMPLE: muestra no encontrada %r' % ln[6:].strip())
        return bytes([CX['SAMPLE'], idx & 0xFF])
    if up.startswith('BRIGHT'):
        n=_ints(ln[6:]); return bytes([CX['BRIGHT'], 1 if (n and n[0]) else 0])
    if up.startswith('FLASH'):
        n=_ints(ln[5:]); return bytes([CX['FLASH'], 1 if (n and n[0]) else 0])
    if up.startswith('INVERSE'):
        n=_ints(ln[7:]); return bytes([CX['INVERSE'], 1 if (n and n[0]) else 0])
    if up.startswith('PAUSE'):
        n=_ints(ln[5:]); return bytes([CX['PAUSE'], (n[0] & 0xFF) if n else 0])
    if up.startswith('CLS'):
        return bytes([CX['CLS']])
    if up.startswith('TIMER_START'):
        return bytes([CX['TSTART'], ctx.timers.get(ln.split()[1].upper(),0)])
    if up.startswith('TIMER_STOP'):
        return bytes([CX['TSTOP'], ctx.timers.get(ln.split()[1].upper(),0)])
    if up.startswith('TIMER_RESET'):
        return bytes([CX['TRESET'], ctx.timers.get(ln.split()[1].upper(),0)])
    if up.startswith('SCORE'):
        return bytes([CX['SCORE'], ctx.var('PUNTOS')])
    if up.startswith('WEAR'):
        return bytes([CX['WEAR'], ctx.obj(ln.split()[1])])
    if up.startswith('REMOVE'):
        return bytes([CX['REMOVE'], ctx.obj(ln.split()[1])])
    if up.startswith('UNLIT'):
        return bytes([CX['UNLIT'], ctx.obj(ln.split()[1])])
    if up.startswith('LIT'):
        return bytes([CX['LIT'], ctx.obj(ln.split()[1])])
    if up.startswith('OPEN'):
        return bytes([CX['OPEN'], ctx.obj(ln.split()[1])])
    if up.startswith('CLOSE'):
        return bytes([CX['CLOSE'], ctx.obj(ln.split()[1])])
    if up.startswith('UNLOCK'):
        return bytes([CX['UNLOCK'], ctx.obj(ln.split()[1])])
    if up.startswith('LOCK'):
        return bytes([CX['LOCK'], ctx.obj(ln.split()[1])])
    if up.startswith('PUTIN'):
        a=ln.split()
        return bytes([CX['PUTIN'], ctx.obj(a[1]), ctx.obj(a[2])])
    if up.startswith('TAKEOUT'):
        return bytes([CX['TAKEOUT'], ctx.obj(ln.split()[1])])
    if up.startswith('PLAY'):
        import fx_engine
        idx=fx_engine.fx_index(getattr(ctx,'fxlist',[]), ln[4:].strip())
        if not idx:
            ctx.warnings.append('PLAY: efecto no encontrado %r'%ln[4:].strip())
        return bytes([CX['PLAY'], idx & 0xFF])
    raise ValueError('sentencia no soportada: '+ln.split()[0])

def compile_lines(lines,ctx):
    out=bytearray(); i=0
    while i<len(lines):
        ln=lines[i].strip()
        if not ln or ln.upper()=='REM' or ln.upper().startswith('REM '): i+=1; continue
        up=ln.upper()
        if up.startswith('IF'):
            i+=1
            cond=ln[2:].strip()
            if cond.upper().endswith('THEN'): cond=cond[:-4].strip()
            tl,el,i=gather_if(lines,i)
            tb=compile_lines(tl,ctx)
            try:
                ce=ge.enc_expr(cond_rpn(pl.parse_condition(cond),ctx))
            except Exception as ex:
                ctx.warnings.append('IF %r: %s'%(cond[:40],ex)); continue
            if el is not None:
                eb=compile_lines(el,ctx); body=tb+bytes([28,len(eb)])
                out+=bytes([27,len(body)])+ce+body+eb
            else:
                out+=bytes([27,len(tb)])+ce+tb
            continue
        if up.startswith('ELSE') or up.startswith('ENDIF'): i+=1; continue
        i+=1
        try: out+=compile_stmt(ln,up,ctx)
        except Exception as ex: ctx.warnings.append('%r: %s'%(ln[:34],ex))
    return bytes(out)


def _on_groups(rest):
    groups=[]; i=0; n=len(rest)
    while i<n:
        while i<n and rest[i]==' ': i+=1
        if i>=n: break
        if rest[i]=='(':
            j=rest.find(')',i)
            inner=rest[i+1:j]
            groups.append([w for w in inner.split() if w.upper()!='OR'])
            i=j+1
        else:
            j=i
            while j<n and rest[j]!=' ': j+=1
            groups.append([rest[i:j]]); i=j
    return groups

def compile_responses(text, ctx, vocab_id):
    lines=text.split('\n'); entries=[]; i=0
    while i<len(lines):
        ln=lines[i].strip(); i+=1
        if not ln.upper().startswith('ON '): continue
        groups=_on_groups(ln[3:].strip())
        verbs=groups[0] if groups else ['_']
        nouns=groups[1] if len(groups)>1 else ['*']
        # La tercera ranura es el SEGUNDO sustantivo y hasta ahora se tiraba,
        # asi que 'ON COGER PASE _' casaba con "coger pase embarque" igual que
        # el export de 128K no lo hacia. Comodines del manual: '_' es hueco
        # vacio (no puede haber palabra) y '*' cualquiera o ninguna.
        nouns2=groups[2] if len(groups)>2 else ['*']
        body=[]
        while i<len(lines) and not lines[i].strip().upper().startswith('ENDON'):
            body.append(lines[i]); i+=1
        i+=1
        bc=compile_lines(body,ctx)
        def _ranura(w):
            if w=='_': return 254        # hueco vacio
            if w=='*': return 255        # cualquier palabra o ninguna
            return vocab_id(w)
        for v in verbs:
            for n in nouns:
                for n2 in nouns2:
                    vid=0 if v in ('_','*') else vocab_id(v)
                    entries.append((vid,_ranura(n),_ranura(n2),bc))
    return entries

import spectrum_export as _sx
def translit(t):
    # Texto de DISPLAY para el motor CPC. Conserva los acentos soportados (espa\u00f1ol
    # o portugu\u00e9s seg\u00fan el idioma) usando translit_disp (c\u00f3digos 144-159) y los
    # desplaza a 224-239, fuera del rango de tokens de compresi\u00f3n (128-223).
    if t is None: return ''
    return desplaza_acentos(_sx.translit_disp(t))

def desplaza_acentos(s):
    """Segunda mitad de translit(): sube los acentos de 144-159 a 224-239, fuera
    del rango de tokens de compresion. Para texto que YA paso por translit_disp
    (p. ej. lo que devuelve spectrum_export.parrafos): pasarlo otra vez por
    translit_disp convierte cada acento en '?'."""
    return ''.join(chr(ord(ch)+80) if 144<=ord(ch)<160 else ch for ch in s)

def compile_game(c, sysm, width=40, filas=0, ficha=None, imagen_intro=False, obj_desc=True):
    g=c.game
    # idioma para los acentos (es/pt). Fija el set de acentos de translit_disp.
    lang=str((getattr(c,'meta',{}) or {}).get('language','') or '').lower()
    _sx._PT_LANG = lang.startswith('pt')
    messages=[translit(m) for m in sysm]; NSYS=len(messages)
    # localizaciones por id (1-based -> 0-based)
    loc_by_id=sorted(c.locidx.items(), key=lambda kv: kv[1])
    locations=[]
    for name,_id in loc_by_id:
        L=g['locations'][name]
        di=len(messages); messages.append(translit(L.get('description','')))
        # Nombre de la localizacion, en mayusculas como en los exports BASIC.
        _nm=str(L.get('name') or name)
        li=len(messages); messages.append(translit(_nm.upper()))
        exits=[]
        for d,dest in (L.get('exits') or {}).items():
            if dest and dest in c.locidx:
                vd=c.verbid.get(d.upper())
                if vd: exits.append((vd, c.locidx[dest]-1))
        locations.append({'desc':di,'name':li,'exits':exits,
                          'dark':1 if L.get('dark') else 0})
    # objetos por id
    obj_by_id=sorted(c.objidx.items(), key=lambda kv: kv[1])
    objects=[]
    for name,_id in obj_by_id:
        O=g['objects'][name]
        ni=len(messages); messages.append(translit(O.get('name','')))
        # Mensaje inicial del objeto: lo que se imprime al mirar la sala en vez de
        # "Aqui hay <nombre>". En los objetos fijos (escenario, PNJ) es ademas lo
        # unico que los hace visibles.
        _im=(O.get('initial_message') or '').strip()
        ii=0
        if _im:
            ii=len(messages); messages.append(translit(_im))
        # Descripcion (lo que imprime EXAMINAR). Hasta v2.10 no se compilaba y
        # EXAMINAR solo daba el nombre. obj_desc=False la deja fuera: el 48K
        # y el CPC lo hacen cuando no cabe en el mapa plano.
        _de=(O.get('description') or '').strip() if obj_desc else ''
        di=0
        if _de:
            di=len(messages); messages.append(translit(_de))
        noun=c.nounid.get(O.get('noun','') or '',0)
        lname=O.get('location')
        attrs=[str(a).lower() for a in (O.get('attributes') or [])]
        # Estos flags solo tienen sentido segun el tipo de objeto (el editor escribe
        # TODOS los campos por defecto, p.ej. open=True en cualquier objeto).
        is_cont=bool(O.get('container') or O.get('openable'))
        is_light=bool(O.get('light_source') or O.get('light'))
        incont=0
        if O.get('worn'):
            loc=ge.WORN
        elif lname in c.locidx:
            loc=c.locidx[lname]-1
        elif lname in c.objidx:                # empieza dentro de un contenedor
            loc=ge.CONTAINED; incont=c.objidx[lname]   # OBJIN = (contenedor 0-based)+1
        else:
            loc=254
        fixed=1 if ('fixed' in attrs or O.get('fixed')) else 0   # no cogible
        light=1 if is_light else 0
        lit=1 if (is_light and O.get('lit')) else 0
        op=1 if (is_cont and O.get('open')) else 0
        lk=1 if (is_cont and O.get('locked')) else 0
        wt=int(O.get('weight',0) or 0)&0xFF
        objects.append({'name':ni,'init':ii,'desc':di,'noun':noun,'loc':loc,'fixed':fixed,
                        'light':light,'lit':lit,'open':op,'locked':lk,'incont':incont,
                        'weight':wt})
    # contexto con indices de recolecta
    if len(c.vars)>ge.NRAM:
        raise ValueError('el motor nativo admite %d variables como mucho '
                         '(FLAGS), y el juego declara %d'%(ge.NRAM,len(c.vars)))
    ctx=Ctx(msgbase=len(messages)); ctx.strict=True
    ctx.vars={k.upper().replace('_',''):i for i,k in enumerate(c.vars.keys())}
    ctx.locs={name:(c.locidx[name]-1) for name in c.locidx}
    ctx.objs={name.upper():(c.objidx[name]-1) for name in c.objidx}
    ctx.verbs={w.upper():vid for w,vid in c.verbalias.items()}
    ctx.nouns={w.upper():nid for w,nid in c.nounalias.items()}
    ctx.timers={str(tid).upper():i for i,tid in enumerate(getattr(c,'timids',[]))}
    ctx.fxlist=(g.get('fx') or [])      # para resolver PLAY "nombre" -> índice
    ctx.smplist=(g.get('samples') or [])   # idem para SAMPLE "nombre"
    import capabilities
    ctx.scrlist=capabilities.used_scr(g)   # SCR nombre -> indice, por orden de uso
    # vocabulario
    vocab=[]
    for w,vid in c.verbalias.items(): vocab.append((w, vid, 2 if vid<=6 else 0))
    for w,nid in c.nounalias.items(): vocab.append((w, nid, 1))
    # condacts
    cd=g.get('condacts',{})
    def vocab_id(word):
        u=word.upper()
        if u in c.verbalias: return c.verbalias[u]
        if u in c.nounalias: return c.nounalias[u]
        return 0
    responses=compile_responses(cd.get('responses','') or '', ctx, vocab_id)
    before=compile_lines((cd.get('before_turn','') or '').split('\n'), ctx)
    after=compile_lines((cd.get('after_turn','') or '').split('\n'), ctx)
    # on_enter de cada localizacion. El motor nativo no tiene tabla de procs por
    # sala -- eso obligaria a tocar el formato de la base de datos, que comparten
    # las cuatro maquinas -- asi que se sintetizan aqui, al final de after_turn,
    # con el predicado ENTERED delante: "si he cambiado de sala en este turno y
    # estoy en @x, corre el on_enter de @x".
    #
    # Hasta la v2.53 on_enter NO se compilaba: lo miraban el interprete de PC y
    # el camino BASIC, y en las cuatro maquinas nativas no se ejecutaba nunca.
    # Un juego que lo usara se comportaba distinto en PC sin decir nada.
    #
    # Diferencia que queda con el interprete: alli el on_enter corre DURANTE el
    # movimiento y aqui al cerrar el turno, o sea despues del resto de after_turn.
    for _nom, _lid in loc_by_id:
        _oe = (g['locations'][_nom] or {}).get('on_enter')
        if isinstance(_oe, (list, tuple)):
            _oe = chr(10).join(str(x) for x in _oe)
        if not (_oe or '').strip():
            continue
        _cuerpo = compile_lines(str(_oe).split(chr(10)), ctx)
        if not _cuerpo:
            continue
        _cond = ge.enc_expr([('ENTERED',), ('AT', _lid - 1), ('AND',)])
        # mismo formato que emite compile_lines para un IF: [27, len(cuerpo)]
        # + condicion + cuerpo
        after += bytes([ge.COP_EXTRA['IF'], len(_cuerpo)]) + _cond + _cuerpo
    onstart=compile_lines((cd.get('on_start','') or '').split('\n'), ctx)
    # Inicializa las variables a su valor inicial al arrancar. El motor pone todos
    # los flags a 0, pero el juego espera valores como HORA_H=3 o LLEVAR_MAX=100.
    # Se prepone un LET (flag,valor) por cada variable con valor inicial != 0, igual
    # que hace la version de Spectrum.
    init_lets=bytearray()
    for i,val in enumerate(c.vars.values()):
        v=int(val) if isinstance(val,(int,float)) else 0
        if v:
            init_lets+=bytes([ge.COP['LET'], i & 0xFF, v & 0xFF])
    onstart=bytes(init_lets)+bytes(onstart)
    # Mensaje inicial (metadata.start_message). El motor nativo nunca lo mostraba:
    # solo lo hacian el interprete y los exports BASIC. Va DESPUES de on_start y
    # antes de describir la sala, que es el orden del export de Spectrum, y
    # termina con PAUSE 0 (espera tecla) para que dé tiempo a leerlo.
    _ini=_sx.parrafos((getattr(c,'meta',{}) or {}).get('start_message',''))
    if _ini:
        # Paginado del mensaje inicial. 'filas' = 0 significa que la plataforma ya
        # para sola cada pantalla (es el caso del Next nativo, que cuenta lineas y
        # espera tecla al desplazar): entonces aqui NO se corta nada, se sueltan
        # los parrafos seguidos y el texto sube como en el export de 128K. Si se
        # cortara, se juntarian dos pausas distintas y ademas el CLS borraria lo
        # que se acababa de leer. Con filas > 0 (el CPC, que no tiene esa cuenta)
        # se corta cada tantas lineas para que no se escape el principio.
        _anc = max(20, int(width or 40))
        _filas = int(filas or 0)
        _usadas = 0
        _b = bytearray()
        if imagen_intro:
            # La imagen de la sala se pone AQUI, no en start: asi el on_start del
            # autor (que suele fijar borde, tinta y papel, y limpiar) ya ha
            # corrido, y no se ve el borde cambiar despues de pintar la imagen.
            _b += bytes([ge.COP_EXTRA['SHOWPIC']])
        for _p in _ini:
            if _filas:
                _n = 1 if not _p else (len(_p) + _anc - 1) // _anc
                if _usadas and _usadas + _n > _filas:
                    _b += bytes([ge.COP_EXTRA['PAUSE'], 0])
                    _b += bytes([ge.COP_EXTRA['CLS']])
                    _usadas = 0
                _usadas += _n
            _mi = ctx.msg(desplaza_acentos(_p))   # parrafos() ya translitero
            _b += bytes([ge.COP['MESSAGE'], _mi & 0xFF, (_mi >> 8) & 0xFF])
        _b += bytes([ge.COP_EXTRA['PAUSE'], 0])
        onstart = bytes(onstart) + bytes(_b)

    # Comando VERSION. VERSI ya esta en el vocabulario de serie, pero el motor
    # nativo no lo atendia y respondia "No entiendo". En vez de tocar la cabecera
    # de la base de datos y el dispatch (que llevan los verbos de sistema en
    # posiciones fijas), se sintetiza una respuesta 'ON version' que imprime la
    # ficha y hace MATCH. El que llama decide si hay ficha y que pone.
    if ficha:
        _vv=c.verbid.get('VERSI') or 0
        if _vv:
            _b=bytearray()
            for _l in ficha:
                _mi=ctx.msg(translit(_l))
                _b+=bytes([ge.COP['MESSAGE'],_mi&0xFF,(_mi>>8)&0xFF])
            _b+=bytes([ge.COP['DONE']])
            responses.append((_vv,0,bytes(_b)))
    # temporizadores: duracion, loop, activo inicial y on_expire compilado
    timers=[]
    for tid in getattr(c,'timids',[]):
        T=g['timers'][tid]
        oe=T.get('on_expire')
        if isinstance(oe,(list,tuple)): oe='\n'.join(str(x) for x in oe)
        exp=compile_lines((oe or '').split('\n'), ctx) if oe else b''
        timers.append({'dur':int(T.get('turns',10))&0xFF,
                       'loop':1 if T.get('loop') else 0,
                       'active':1 if T.get('active') else 0,
                       'expire':bytes(exp)})
    messages=messages+ctx.messages
    # verbos de sistema
    def vid_of(*names):
        for n in names:
            if n in c.verbid: return c.verbid[n]
        return 0
    sysverbs={'look':vid_of('MIRAR','M'),'quit':vid_of('FIN','SALIR'),
              'get':vid_of('COGER'),'drop':vid_of('DEJAR'),
              'inven':vid_of('INVEN','I'),'exam':vid_of('EXAMI','EXAM')}
    # nombre que significa "todo" (para COGER/DEJAR TODO)
    vall=0
    for w in ('TODO','TODOS','TODAS','TODA','ALL'):
        if w in c.nounalias: vall=c.nounalias[w]; break
    start_name=loc_by_id[0][0]
    info=dict(nmsg=len(messages),nloc=len(locations),nobj=len(objects),
              nvocab=len(vocab),nresp=len(responses),
              before=len(before),after=len(after),onstart=len(onstart),
              warnings=ctx.warnings)
    return dict(messages=messages,locations=locations,vocab=vocab,objects=objects,
                responses=responses,startloc=0,sysverbs=sysverbs,width=width,
                proc_before=before,proc_after=after,proc_onstart=onstart,vall=vall,
                font_acc=_font_block(),timers=timers,
                llevarmax=ctx.vars.get('LLEVARMAX',255),
                pantallas=list(ctx.scrlist)), info

def _font_block():
    # 16 glifos de acento (224-239) extraidos del font 8x8 (cpc_font), con trazo de
    # 2px que ya casa con el font de la ROM del CPC. El texto normal lo dibuja la
    # ROM; estos solo cubren las tildes.
    import cpc_font
    acc = _sx._ACC_CODE_PT if _sx._PT_LANG else _sx._ACC_CODE
    by_code = {code: ch for ch, code in acc.items()}
    block = bytearray()
    for code in range(144, 160):                 # acentos 144-159 -> 224-239
        ch = by_code.get(code)
        g = cpc_font.ACC.get(ch) if ch else None
        block += bytes(g) if g else bytes(8)
    return bytes(block)                          # 16*8 = 128 bytes
