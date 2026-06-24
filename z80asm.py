# -*- coding: utf-8 -*-
"""Ensamblador Z80 de dos pasadas (copia de test del sandbox)."""
import re
R8 = {'b':0,'c':1,'d':2,'e':3,'h':4,'l':5,'(hl)':6,'a':7}
RP_SP = {'bc':0,'de':1,'hl':2,'sp':3}
RP_AF = {'bc':0,'de':1,'hl':2,'af':3}
CC = {'nz':0,'z':1,'nc':2,'c':3,'po':4,'pe':5,'p':6,'m':7}
ALU = {'add':0,'adc':1,'sub':2,'sbc':3,'and':4,'xor':5,'or':6,'cp':7}
CBROT = {'rlc':0,'rrc':1,'rl':2,'rr':3,'sla':4,'sra':5,'sll':6,'srl':7}

class AsmError(Exception): pass

def _ev(s, sym, cur):
    s = s.strip()
    m = re.fullmatch(r"'(.)'", s)
    if m: return ord(m.group(1))
    e = s
    e = re.sub(r'&([0-9A-Fa-f]+)', lambda m: str(int(m.group(1),16)), e)
    e = re.sub(r'0x([0-9A-Fa-f]+)', lambda m: str(int(m.group(1),16)), e)
    e = re.sub(r'%([01]+)', lambda m: str(int(m.group(1),2)), e)
    e = re.sub(r'\$', str(cur), e)
    def repl(m):
        w = m.group(0)
        if re.fullmatch(r'\d+', w): return w
        if w.lower() in sym: return str(sym[w.lower()])
        return 'UNRESOLVED'
    e = re.sub(r'[A-Za-z_][A-Za-z0-9_]*', repl, e)
    if 'UNRESOLVED' in e: return 0
    try: return int(eval(e, {'__builtins__':{}}, {})) & 0xFFFF
    except Exception as ex: raise AsmError('no eval "%s"->"%s": %s'%(s,e,ex))

def _split_ops(rest):
    if not rest.strip(): return []
    ops=[]; depth=0; cur=''
    for ch in rest:
        if ch=='(' : depth+=1
        elif ch==')': depth-=1
        if ch==',' and depth==0: ops.append(cur.strip()); cur=''
        else: cur+=ch
    ops.append(cur.strip()); return ops

def _is_mem(o): return o.startswith('(') and o.endswith(')')

def _idx_disp(o):
    inner=o[1:-1].strip().lower()
    m=re.fullmatch(r'(ix|iy)\s*([+-]\s*.+)?', inner)
    if not m: return None
    pref=0xDD if m.group(1)=='ix' else 0xFD
    disp=m.group(2)
    return pref, (disp.replace(' ','') if disp else '+0')

def _enc(mnem, ops, cur, sym, final=False):
    m=mnem.lower(); o=[x.lower() for x in ops]
    def n8(x): return _ev(x,sym,cur)&0xFF
    def n16(x): return _ev(x,sym,cur)&0xFFFF
    def lo(v): return v&0xFF
    def hi(v): return (v>>8)&0xFF
    simple={'nop':[0],'halt':[0x76],'ret':[0xC9],'reti':[0xED,0x4D],'retn':[0xED,0x45],
        'di':[0xF3],'ei':[0xFB],'exx':[0xD9],'rlca':[7],'rrca':[0x0F],'rla':[0x17],
        'rra':[0x1F],'daa':[0x27],'cpl':[0x2F],'scf':[0x37],'ccf':[0x3F],'neg':[0xED,0x44],
        'ldir':[0xED,0xB0],'lddr':[0xED,0xB8],'ldi':[0xED,0xA0],'ldd':[0xED,0xA8],
        'cpir':[0xED,0xB1],'cpi':[0xED,0xA1]}
    if m in simple and not o: return simple[m]
    if m=='ex':
        if o==['de','hl']: return [0xEB]
        if o==['af',"af'"] or o==['af','af']: return [0x08]
        if o==['(sp)','hl']: return [0xE3]
    if m=='im': return [0xED,{'0':0x46,'1':0x56,'2':0x5E}[o[0]]]
    if m=='ld':
        d,s=o[0],o[1]
        if d in R8 and s in R8 and not (d=='(hl)' and s=='(hl)'): return [0x40|(R8[d]<<3)|R8[s]]
        if d in R8 and not _is_mem(s) and s not in RP_SP and s not in ('ix','iy'): return [0x06|(R8[d]<<3), n8(s)]
        if d in RP_SP and not _is_mem(s):
            v=n16(s); return [0x01|(RP_SP[d]<<4),lo(v),hi(v)]
        if d in ('ix','iy') and not _is_mem(s):
            v=n16(s); return [0xDD if d=='ix' else 0xFD,0x21,lo(v),hi(v)]
        if d=='a' and _is_mem(s) and s[1:-1] not in ('bc','de','hl'):
            idd=_idx_disp(s)
            if idd: pref,disp=idd; return [pref,0x7E,_ev(disp,sym,cur)&0xFF]
            v=n16(s[1:-1]); return [0x3A,lo(v),hi(v)]
        if _is_mem(d) and s=='a' and d[1:-1] not in ('bc','de','hl'):
            idd=_idx_disp(d)
            if idd: pref,disp=idd; return [pref,0x77,_ev(disp,sym,cur)&0xFF]
            v=n16(d[1:-1]); return [0x32,lo(v),hi(v)]
        if d=='a' and s in ('(bc)','(de)'): return [0x0A if s=='(bc)' else 0x1A]
        if d in ('(bc)','(de)') and s=='a': return [0x02 if d=='(bc)' else 0x12]
        if _is_mem(d) and s in RP_SP:
            v=n16(d[1:-1])
            if s=='hl': return [0x22,lo(v),hi(v)]
            return [0xED,0x43|(RP_SP[s]<<4),lo(v),hi(v)]
        if d in RP_SP and _is_mem(s):
            v=n16(s[1:-1])
            if d=='hl': return [0x2A,lo(v),hi(v)]
            return [0xED,0x4B|(RP_SP[d]<<4),lo(v),hi(v)]
        if _is_mem(d) and _idx_disp(d):
            pref,disp=_idx_disp(d); dv=_ev(disp,sym,cur)&0xFF
            if s in R8 and s!='(hl)': return [pref,0x70|R8[s],dv]
            return [pref,0x36,dv,n8(s)]
        if d in R8 and d!='(hl)' and _is_mem(s) and _idx_disp(s):
            pref,disp=_idx_disp(s); dv=_ev(disp,sym,cur)&0xFF
            return [pref,0x46|(R8[d]<<3),dv]
        if d=='sp' and s=='hl': return [0xF9]
        if d=='i' and s=='a': return [0xED,0x47]
        if d=='r' and s=='a': return [0xED,0x4F]
        if d=='a' and s=='i': return [0xED,0x57]
        if d=='a' and s=='r': return [0xED,0x5F]
        raise AsmError('LD no soportado: %s'%ops)
    if m in ALU:
        k=ALU[m]
        if m=='add' and o[0]=='hl' and o[1] in RP_SP: return [0x09|(RP_SP[o[1]]<<4)]
        if m=='adc' and o[0]=='hl' and o[1] in RP_SP: return [0xED,0x4A|(RP_SP[o[1]]<<4)]
        if m=='sbc' and o[0]=='hl' and o[1] in RP_SP: return [0xED,0x42|(RP_SP[o[1]]<<4)]
        operand=o[1] if len(o)==2 else o[0]
        if operand in R8: return [0x80|(k<<3)|R8[operand]]
        if _is_mem(operand) and _idx_disp(operand):
            pref,disp=_idx_disp(operand); return [pref,0x80|(k<<3)|6,_ev(disp,sym,cur)&0xFF]
        return [0xC6|(k<<3), n8(operand)]
    if m in ('inc','dec'):
        d=o[0]
        if d in R8: return [(0x04 if m=='inc' else 0x05)|(R8[d]<<3)]
        if d in RP_SP: return [(0x03 if m=='inc' else 0x0B)|(RP_SP[d]<<4)]
        if d in ('ix','iy'): return [0xDD if d=='ix' else 0xFD, 0x23 if m=='inc' else 0x2B]
        if _is_mem(d) and _idx_disp(d):
            pref,disp=_idx_disp(d); return [pref,0x34 if m=='inc' else 0x35,_ev(disp,sym,cur)&0xFF]
        raise AsmError('%s: %s'%(m,ops))
    if m=='jp':
        if len(o)==1:
            if o[0] in ('(hl)','hl'): return [0xE9]
            v=n16(o[0]); return [0xC3,lo(v),hi(v)]
        cc=CC[o[0]]; v=n16(o[1]); return [0xC2|(cc<<3),lo(v),hi(v)]
    def _rel(t):
        d=t-(cur+2)
        if final and (d<-128 or d>127):
            raise AsmError('salto relativo fuera de rango (%+d) a &%04X desde &%04X; usa jp' % (d,t,cur))
        return d&0xFF
    if m=='jr':
        if len(o)==1:
            t=n16(o[0]); return [0x18,_rel(t)]
        cc={'nz':0x20,'z':0x28,'nc':0x30,'c':0x38}[o[0]]; t=n16(o[1]); return [cc,_rel(t)]
    if m=='djnz':
        t=n16(o[0]); return [0x10,_rel(t)]
    if m=='call':
        if len(o)==1: v=n16(o[0]); return [0xCD,lo(v),hi(v)]
        cc=CC[o[0]]; v=n16(o[1]); return [0xC4|(cc<<3),lo(v),hi(v)]
    if m=='ret' and o: return [0xC0|(CC[o[0]]<<3)]
    if m=='rst': return [0xC7|(n8(o[0])&0x38)]
    if m in ('push','pop'):
        base=0xC5 if m=='push' else 0xC1
        if o[0] in RP_AF: return [base|(RP_AF[o[0]]<<4)]
        if o[0]=='ix': return [0xDD,base]
        if o[0]=='iy': return [0xFD,base]
    if m in CBROT:
        if o[0] in R8: return [0xCB,(CBROT[m]<<3)|R8[o[0]]]
    if m in ('bit','set','res'):
        b=n8(o[0])&7
        top={'bit':0x40,'res':0x80,'set':0xC0}[m]
        if o[1] in R8: return [0xCB,top|(b<<3)|R8[o[1]]]
    raise AsmError('instruccion no soportada: %s %s'%(mnem,ops))

def _split_data_items(arg):
    items=[]; cur=''; q=None
    for ch in arg:
        if q: cur+=ch;  q=None if ch==q else q
        elif ch in '"\'': q=ch; cur+=ch
        elif ch==',': items.append(cur); cur=''
        else: cur+=ch
    if cur.strip(): items.append(cur)
    return items

def _count_data(arg, size):
    n=0
    for it in _split_data_items(arg):
        it=it.strip()
        if it.startswith('"') and it.endswith('"'): n+=(len(it)-2)*size
        else: n+=size
    return n

def _emit_data(mnem, arg, sym, cur):
    out=[]
    if mnem in ('ds','defs'):
        parts=[p.strip() for p in arg.split(',')]
        n=_ev(parts[0],sym,cur); fill=_ev(parts[1],sym,cur) if len(parts)>1 else 0
        return [fill&0xFF]*n
    size=1 if mnem in ('db','defb') else 2
    for it in _split_data_items(arg):
        it=it.strip()
        if it.startswith('"') and it.endswith('"'):
            for ch in it[1:-1]: out.append(ord(ch)&0xFF)
        else:
            v=_ev(it,sym,cur+len(out))
            if size==1: out.append(v&0xFF)
            else: out.append(v&0xFF); out.append((v>>8)&0xFF)
    return out

def assemble(source, org=0):
    sym={}; cur=org; parsed=[]
    DATADIR=('db','defb','dw','defw','ds','defs')
    for raw in source.split('\n'):
        line=raw.split(';',1)[0].rstrip()
        if not line.strip(): continue
        mlabel=re.match(r'^([A-Za-z_][A-Za-z0-9_]*):', line)
        rest=line
        if mlabel:
            sym[mlabel.group(1).lower()]=cur; rest=line[mlabel.end():]
        rest=rest.strip()
        if not rest: continue
        toks=rest.split(None,2)
        if len(toks)>=2 and toks[1].lower()=='equ':
            sym[toks[0].lower()]=_ev(toks[2],sym,cur); continue
        if len(toks)>=2 and toks[1].lower() in DATADIR and toks[0].lower() not in DATADIR \
                and re.match(r'^[A-Za-z_]',toks[0]):
            sym[toks[0].lower()]=cur
            mnem=toks[1].lower(); arg=toks[2] if len(toks)>2 else ''
        else:
            parts=rest.split(None,1); mnem=parts[0].lower(); arg=parts[1] if len(parts)>1 else ''
        if mnem=='org': cur=_ev(arg,sym,cur); parsed.append(('org',cur)); continue
        if mnem=='equ': continue
        if mnem in ('db','defb'): parsed.append(('data',cur,mnem,arg)); cur+=_count_data(arg,1); continue
        if mnem in ('dw','defw'): parsed.append(('data',cur,mnem,arg)); cur+=_count_data(arg,2); continue
        if mnem in ('ds','defs'): parsed.append(('data',cur,mnem,arg)); cur+=_ev(arg.split(',')[0],sym,cur); continue
        parsed.append(('inst',cur,mnem,arg)); cur+=len(_enc(mnem,_split_ops(arg),cur,sym))
    out={}
    for item in parsed:
        if item[0]=='org': continue
        if item[0]=='data':
            _,at,mnem,arg=item
            for i,bb in enumerate(_emit_data(mnem,arg,sym,at)): out[at+i]=bb
        else:
            _,at,mnem,arg=item
            for i,bb in enumerate(_enc(mnem,_split_ops(arg),at,sym,final=True)): out[at+i]=bb
    if not out: return b'', sym
    lo_a=min(out); hi_a=max(out); buf=bytearray(hi_a-lo_a+1)
    for a,v in out.items(): buf[a-lo_a]=v
    return bytes(buf), sym
