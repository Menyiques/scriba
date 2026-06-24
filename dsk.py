# -*- coding: utf-8 -*-
"""Empaquetador de disco AMSDOS .dsk (formato DATA) en Python puro."""
def amsdos_header(name, ext, length, load, exec_addr=None):
    if exec_addr is None: exec_addr=load
    h=bytearray(128)
    h[0]=0
    h[1:9]=(name.upper()+' '*8)[:8].encode('ascii')
    h[9:12]=(ext.upper()+' '*3)[:3].encode('ascii')
    h[18]=2                                   # tipo: binario
    h[21]=load&0xFF; h[22]=(load>>8)&0xFF
    h[24]=length&0xFF; h[25]=(length>>8)&0xFF
    h[26]=exec_addr&0xFF; h[27]=(exec_addr>>8)&0xFF
    h[64]=length&0xFF; h[65]=(length>>8)&0xFF; h[66]=(length>>16)&0xFF
    cs=sum(h[0:67])&0xFFFF
    h[67]=cs&0xFF; h[68]=(cs>>8)&0xFF
    return bytes(h)

def bin_file(name, ext, data, load):
    return amsdos_header(name,ext,len(data),load)+bytes(data)

def make_dsk(files):
    SECTORS=9; SECSIZE=512; TRACKS=40
    SECIDS=[0xC1+i for i in range(SECTORS)]
    nblocks=TRACKS*SECTORS*SECSIZE//1024     # 180
    blocks=[bytearray(1024) for _ in range(nblocks)]
    directory=bytearray(2048)
    next_block=2; entry_i=0
    for (name,ext,data) in files:
        nb=(len(data)+1023)//1024
        blks=[]
        for k in range(nb):
            chunk=data[k*1024:(k+1)*1024]
            b=bytearray(1024); b[:len(chunk)]=chunk
            blocks[next_block]=b; blks.append(next_block); next_block+=1
        recs_total=(len(data)+127)//128
        bi=0; extent=0
        while bi<len(blks) or extent==0:
            e=bytearray(32)
            e[1:9]=(name.upper()+' '*8)[:8].encode()
            e[9:12]=(ext.upper()+' '*3)[:3].encode()
            e[12]=extent
            eblks=blks[bi:bi+16]
            recs=max(0,min(128, recs_total-extent*128))
            e[15]=recs&0xFF
            for j,bn in enumerate(eblks): e[16+j]=bn
            directory[entry_i*32:entry_i*32+32]=e
            entry_i+=1; extent+=1; bi+=16
            if bi>=len(blks): break
    blocks[0]=bytearray(directory[0:1024]); blocks[1]=bytearray(directory[1024:2048])
    flat=bytearray()
    for b in blocks: flat+=b
    img=bytearray()
    dib=bytearray(256)
    dib[0:34]=b'MV - CPCEMU Disk-File\r\nDisk-Info\r\n'
    dib[34:42]=b'Scriba\0\0'
    dib[48]=TRACKS; dib[49]=1
    ts=256+SECTORS*SECSIZE
    dib[50]=ts&0xFF; dib[51]=(ts>>8)&0xFF
    img+=dib
    for t in range(TRACKS):
        tib=bytearray(256)
        tib[0:12]=b'Track-Info\r\n'
        tib[16]=t; tib[17]=0; tib[20]=2; tib[21]=SECTORS; tib[22]=0x4E; tib[23]=0xE5
        for s in range(SECTORS):
            o=24+s*8
            tib[o]=t; tib[o+2]=SECIDS[s]; tib[o+3]=2
        img+=tib
        base=t*SECTORS*SECSIZE
        img+=flat[base:base+SECTORS*SECSIZE]
    return bytes(img)

def read_dir(dsk):
    # leer las entradas de directorio (validacion)
    flat_off=256+256   # DIB + track0 info -> sector data
    dirbytes=dsk[flat_off:flat_off+2048]
    entries=[]
    for i in range(64):
        e=dirbytes[i*32:i*32+32]
        if e[0]==0xE5 or e[1]==0x20 and e[0]==0: 
            if e[1]==0x20: continue
        if e[0]==0 and e[1]!=0x20 and 32<=e[1]<127:
            nm=bytes(b&0x7F for b in e[1:9]).decode('ascii','replace').strip()
            ex=bytes(b&0x7F for b in e[9:12]).decode('ascii','replace').strip()
            entries.append((nm,ex,e[12],e[15],[b for b in e[16:32] if b]))
    return entries
