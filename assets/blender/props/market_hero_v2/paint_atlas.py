"""Original seeded shared trim atlas, 360px/m authoring scale, no photographic inputs."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image

def paint(out,revision):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);n=2048
    y,x=np.mgrid[0:n,0:n];u=x/(n-1);v=1-y/(n-1)
    rgb=np.zeros((n,n,3),np.float32);rgb[:]=[.32,.24,.17]
    height=np.zeros((n,n),np.float32);rough=np.full((n,n),.82,np.float32);ao=np.ones((n,n),np.float32);metal=np.zeros((n,n),np.float32)
    wood=(u<.5)&(v>.5);a=u*2;b=(v-.5)*2
    edge=np.minimum.reduce([a,1-a,b,1-b]);grainphase=b*150+np.sin(a*8)*.6+np.sin(a*21)*.12
    grain=np.sin(grainphase)*.025+np.sin(grainphase*2.35)*.008
    knots=np.exp(-(((a-.58)/.15)**2+((b-.38)/.028)**2))
    broad=.92+.045*np.sin(a*6)*np.cos(b*5)+grain-.09*knots
    worn=np.exp(-np.maximum(0,edge)*55)*.12
    col=np.array([.43,.29,.185])[None,None,:]*broad[...,None]+worn[...,None]*np.array([.65,.51,.31])
    rgb[wood]=col[wood];height[wood]=(.06*grain-.025*knots)[wood];ao[wood]=np.clip(.98-.12*np.exp(-edge*30),.78,1)[wood]
    cloth=(u<.5)&(v<=.5);cx=u*2048/360;cy=v*2048/360
    stripe=(np.floor(cx/.3)%2)==0
    base=np.where(stripe[...,None],np.array([.17,.31,.525]),np.array([.90,.835,.70]))
    fold=1-.055*np.cos(cx*2*np.pi/.3)**12
    hem=np.exp(-((cy-.09)/.012)**2)+np.exp(-((cy-1.82)/.012)**2)
    stitch=np.maximum(0,np.sin(cx*2*np.pi/.021))**6*hem
    weave=.0035*np.sin(cx*2*np.pi/.007)*np.sin(cy*2*np.pi/.008)
    rgb[cloth]=(base*fold[...,None]*(1-.04*hem[...,None])+stitch[...,None]*.025)[cloth]
    height[cloth]=(weave+.004*hem+.001*stitch)[cloth];rough[cloth]=.92
    colors={'apple':(.60,.20,.125),'bread':(.76,.53,.27),'clay':(.58,.30,.20),'basket':(.60,.45,.24),'iron':(.24,.26,.28)}
    tiles={'apple':(.53,.03),'bread':(.76,.03),'clay':(.53,.26),'basket':(.76,.26),'iron':(.53,.53)}
    for name,(u0,v0) in tiles.items():
        mask=(u>=u0)&(u<u0+.2)&(v>=v0)&(v<v0+.2);a=(u-u0)/.2;b=(v-v0)/.2
        variation=.84+.13*b+.025*np.sin(a*7+b*9)
        h=np.zeros_like(u)
        if name=='bread':
            slash=np.maximum(0,np.cos(a*28+b*4))**14*np.exp(-((b-.55)/.25)**2);variation-=slash*.16;h-=slash*.035
        if name=='basket':
            weave=.035*np.sin(a*95)*np.cos(b*95);variation+=weave;h+=weave*.08
        if name=='clay':variation+=.04*np.sin(b*33);h+=.005*np.sin(b*33);rough[mask]=.70
        if name=='iron':
            stud=np.exp(-(((a-.18)/.035)**2+((b-.20)/.035)**2))+np.exp(-(((a-.18)/.035)**2+((b-.8)/.035)**2))
            variation+=stud*.20;h+=stud*.02;metal[mask]=.55;rough[mask]=.65
        rgb[mask]=(np.array(colors[name])[None,None,:]*variation[...,None])[mask];height[mask]=h[mask]
    gy,gx=np.gradient(height);normal=np.stack([-gx*35,gy*35,np.ones_like(gx)],-1);normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    orm=np.stack([ao,rough,metal],-1)
    maps={'albedo':rgb,'normal':normal*.5+.5,'orm':orm,'height':np.repeat((height*.6+.5)[...,None],3,axis=-1)}
    for name,data in maps.items():
        image=Image.fromarray(np.round(np.clip(data,0,1)*255).astype(np.uint8),'RGB')
        if name!='albedo':image=image.resize((1024,1024),Image.Resampling.LANCZOS)
        image.save(out/f'market_hero_{name}.png')
    manifest={'schema':'xexoria.market-trim/2','revision':revision,'seed':2026100326,'atlasFamily':'market_hero_v2','albedoSize':2048,'dataSize':1024,'texelDensity':360,'woodUV':[0,.5,.5,1],'clothUV':[0,0,.5,.5],'goodsTiles':tiles,'normal':'OpenGL +Y','provenance':'Original procedural pixels; no third-party input; bake augmentation follows'}
    (out/'atlas.json').write_text(json.dumps(manifest,indent=2));print('MARKET ATLAS',out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--revision',type=int,default=1);a=p.parse_args();paint(a.out,a.revision)
