"""Original seeded craft atlas; broad painted grain and edge/cavity hierarchy."""
from pathlib import Path
import argparse
import numpy as np

CELLS = {'wood':0,'stone':1,'turf':2,'thatch':3,'rope':4,'sapphire':5,'terracotta':6,'slate':7,
         'iron':8,'coal':9,'apple':10,'carrot':11,'bread':12,'clay':13,'fish':14,'cream':15}
COLORS = ['8a5a35','d0b98f','6f7f2e','bba258','baa778','2b4f86','b8603f','3e5a7a',
          '3a3a40','2a1a12','a94637','ba6b38','c49751','985a43','789ca2','e8d9bc']

def uv_rect(name):
    i=CELLS[name];return ((i%4+.035)/4,1-(i//4+.965)/4,.93/4,.93/4)

def paint(out,revision=1):
    from PIL import Image
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    sz=512;y,x=np.mgrid[0:sz,0:sz].astype(float)/(sz-1)
    rgb=np.zeros((2048,2048,3));height=np.zeros((2048,2048));rough=np.zeros_like(height);ao=np.ones_like(height);metal=np.zeros_like(height)
    for name,i in CELLS.items():
        col=np.array([int(COLORS[i][k:k+2],16)/255 for k in (0,2,4)])
        edge=np.minimum.reduce([x,1-x,y,1-y]);rim=np.exp(-((edge-.022)/.018)**2)
        broad=np.sin(x*10+y*5+i)*.025+np.sin(x*5-y*8+i)*.020
        grain=.022*np.sin(y*96+np.sin(x*9)*1.8)+.008*np.sin(y*210+x*8)
        value=.82+.17*(1-y)+broad+.10*rim-.13*np.exp(-edge*60)
        h=.12*rim
        if name in ('wood','rope','thatch'):
            value+=grain*(1 if name=='wood' else .75)
            h+=grain*.7
        if name=='wood':
            # Four iron studs per plank, painted rather than added draw/triangle cost.
            for a in (.09,.91):
                for b in (.23,.77):
                    d=np.hypot((x-a)*1.8,y-b);stud=np.clip((.027-d)*120,0,1)
                    value=value*(1-stud)+.37*stud;h+=stud*.035
            knot=np.exp(-(((x-.57)/.095)**2+((y-.40)/.023)**2))* .18
            value-=knot
        if name=='stone':
            seam=np.exp(-((y-.5)/.012)**2)*.13+np.exp(-((x-.52)/.015)**2)*(y>.5)*.12
            value-=seam;h-=seam*.2
        if name=='turf':
            value+=.035*np.sin(x*29+np.sin(y*18))+.020*np.sin(y*41+x*4)
            h+=.035*np.sin(x*24+y*11)
            if revision>=3:
                patch=.055*np.sin(x*12+y*9)*np.cos(x*9-y*5)
                strokes=.04*np.maximum(0,np.cos((x+y*.2)*70))*np.exp(-(((y*4)%1-.3)**2)/.06)
                value+=patch+strokes;h+=strokes*.4
        if name in ('sapphire','terracotta','slate'):
            stripe=(np.floor(x*(10 if name=='terracotta' else 8))%2)==0
            c2=np.array([.91,.85,.74]);base=np.where(stripe[...,None],col,c2)
            value=.91+.07*np.cos(y*5)-.075*np.cos(x*8*np.pi)**12
            if revision>=2:value+=.06*rim
            col=base
            h=.035*np.cos(x*8*np.pi)
        if name=='coal':
            ember=np.maximum(0,np.sin(x*15+y*21)-.85)*2
            base=np.broadcast_to(col,(sz,sz,3)).copy();base+=ember[...,None]*np.array([.45,.16,.03]);col=base
        if name=='fish':value+=.045*np.sin(y*22+x*10)
        yy,xx=(i//4)*sz,(i%4)*sz;sl=np.s_[yy:yy+sz,xx:xx+sz]
        rgb[sl]=np.clip(col*value[...,None],.025,.95);height[sl]=h
        rough[sl]=(.64 if name in ('iron','fish','clay') else .88)+broad*.8
        ao[sl]=np.clip(1-.12*np.exp(-edge*45),.7,1)
        if name=='iron':metal[sl]=.7
    # OpenGL +Y normal: PNG rows run downwards, so green uses +dheight/drow.
    gy,gx=np.gradient(height);n=np.stack([-gx*2,gy*2,np.ones_like(gx)],-1);n/=np.linalg.norm(n,axis=-1,keepdims=True)
    orm=np.stack([ao,rough,metal],-1)
    for name,a,size in [('albedo',rgb,2048),('normal',n*.5+.5,512),('orm',orm,256)]:
        Image.fromarray(np.round(np.clip(a,0,1)*255).astype('uint8'),'RGB').resize((size,size),Image.Resampling.LANCZOS).save(out/f'sm_craft_{name}.png')
    print('CRAFT atlas 2048 / normal512 / ORM256 original procedural, revision',revision)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--revision',type=int,default=1)
    a=ap.parse_args();paint(a.out,a.revision)
