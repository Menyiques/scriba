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
    if u in ('INVEN',): return ge.CARRIED
    if u in ('PUESTO','WORN'): return ge.WORN
    if u in ('NADA','NOWHERE'): return ge.NOWHERE
    return ctx.loc(dst)

def cond_rpn(a,ctx):
    t=a[0]
    if t=='pred':
        nm=a[1]; args=a[2]
        if nm not in PREDMAP: raise ValueError('pred no soportado: '+nm)
        op=PREDMAP[nm]
        if nm in ('AT','NOTAT'): return [(op,ctx.loc(args[0]))]
        if nm in ('ZERO','NOTZERO'): return [(op,ctx.var(args[0]))]
        if nm=='DARK': return [('DARK',)]
        if nm=='ISAT': return [('ISAT',ctx.obj(args[0]),_destval(ctx,args[1]))]
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

def compile_stmt(ln, up, ctx):
    if up.startswith('PRINT'):
        mi=ctx.msg(translit(_string(ln))); return bytes([COP['MESSAGE'],mi&0xFF,(mi>>8)&0xFF])
    if up.startswith('LET'):
        m=re.match(r'LET\s+(\w+)\s*=\s*(.+)',ln,re.I)
        v=ctx.var(m.group(1)); eb=ge.enc_expr(expr_rpn(pl.parse_expr(m.group(2)),ctx))
        return bytes([26,v])+eb
    if up.startswith('GOTO'):  return bytes([COP['GOTO'],ctx.loc(ln.split()[1])])
    if up.startswith('CREATE'):return bytes([COP['CREATE'],ctx.obj(ln.split()[1])])
    if up.startswith('DESTROY'):return bytes([COP['DESTROY'],ctx.obj(ln.split()[1])])
    if up.startswith('GET'):   return bytes([COP['GET'],ctx.obj(ln.split()[1])])
    if up.startswith('DROP') or (up.startswith('PUT') and not up.startswith('PUTIN')):
        return bytes([COP['DROP'],ctx.obj(ln.split()[1])])
    if up.startswith('ADDSCORE'):
        try: n=int(ln.split()[1])
        except: n=1
        # suma n a PUNTOS y muestra "[+n puntos]" (c_addscore en el motor).
        return bytes([ge.COP_EXTRA['ADDSCORE'], ctx.var('PUNTOS'), n&0xFF])
    if up.startswith('MATCH') or up.startswith('END'): return bytes([COP['DONE']])
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
        if not ln or ln.upper().startswith('REM'): i+=1; continue
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
        nouns=groups[1] if len(groups)>1 else ['_']
        body=[]
        while i<len(lines) and not lines[i].strip().upper().startswith('ENDON'):
            body.append(lines[i]); i+=1
        i+=1
        bc=compile_lines(body,ctx)
        for v in verbs:
            for n in nouns:
                vid=0 if v=='_' else vocab_id(v)
                nid=0 if n=='_' else vocab_id(n)
                entries.append((vid,nid,bc))
    return entries

import spectrum_export as _sx
def translit(t):
    # Texto de DISPLAY para el motor CPC. Conserva los acentos soportados (espa\u00f1ol
    # o portugu\u00e9s seg\u00fan el idioma) usando translit_disp (c\u00f3digos 144-159) y los
    # desplaza a 224-239, fuera del rango de tokens de compresi\u00f3n (128-223).
    if t is None: return ''
    s=_sx.translit_disp(t)
    return ''.join(chr(ord(ch)+80) if 144<=ord(ch)<160 else ch for ch in s)

def compile_game(c, sysm, width=40):
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
        exits=[]
        for d,dest in (L.get('exits') or {}).items():
            if dest and dest in c.locidx:
                vd=c.verbid.get(d.upper())
                if vd: exits.append((vd, c.locidx[dest]-1))
        locations.append({'desc':di,'exits':exits,
                          'dark':1 if L.get('dark') else 0})
    # objetos por id
    obj_by_id=sorted(c.objidx.items(), key=lambda kv: kv[1])
    objects=[]
    for name,_id in obj_by_id:
        O=g['objects'][name]
        ni=len(messages); messages.append(translit(O.get('name','')))
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
        objects.append({'name':ni,'noun':noun,'loc':loc,'fixed':fixed,
                        'light':light,'lit':lit,'open':op,'locked':lk,'incont':incont,
                        'weight':wt})
    # contexto con indices de recolecta
    ctx=Ctx(msgbase=len(messages)); ctx.strict=True
    ctx.vars={k.upper().replace('_',''):i for i,k in enumerate(c.vars.keys())}
    ctx.locs={name:(c.locidx[name]-1) for name in c.locidx}
    ctx.objs={name.upper():(c.objidx[name]-1) for name in c.objidx}
    ctx.verbs={w.upper():vid for w,vid in c.verbalias.items()}
    ctx.nouns={w.upper():nid for w,nid in c.nounalias.items()}
    ctx.timers={str(tid).upper():i for i,tid in enumerate(getattr(c,'timids',[]))}
    ctx.fxlist=(g.get('fx') or [])      # para resolver PLAY "nombre" -> índice
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
                llevarmax=ctx.vars.get('LLEVARMAX',255)), info

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
