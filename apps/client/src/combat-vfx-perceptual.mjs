// Independent CIEDE2000 equations (kL=kC=kH=1), verified against Sharma/Wu/Dalal test pairs.
// Source: https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/ . No MATLAB code is vendored.
const rad=Math.PI/180,p25=25**7;
const linear=value=>{const v=value/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;};
const pivot=value=>value>216/24389?Math.cbrt(value):(24389/27*value+16)/116;
export function rgbToLab(r,g,b){r=linear(r);g=linear(g);b=linear(b);const x=pivot((.4124564*r+.3575761*g+.1804375*b)/.95047),y=pivot(.2126729*r+.7151522*g+.0721750*b),z=pivot((.0193339*r+.1191920*g+.9503041*b)/1.08883);return [116*y-16,500*(x-y),200*(y-z)];}
export function deltaE00(a,b){
 const [l1,a1,b1]=a,[l2,a2,b2]=b,c1=Math.hypot(a1,b1),c2=Math.hypot(a2,b2),c=(c1+c2)/2,g=.5*(1-Math.sqrt(c**7/(c**7+p25))),ap1=(1+g)*a1,ap2=(1+g)*a2,cp1=Math.hypot(ap1,b1),cp2=Math.hypot(ap2,b2);
 const hue=(aa,bb)=>{const h=Math.atan2(bb,aa)/rad;return h<0?h+360:h;},h1=cp1===0?0:hue(ap1,b1),h2=cp2===0?0:hue(ap2,b2);
 let dh=h2-h1;if(cp1*cp2===0)dh=0;else if(dh>180)dh-=360;else if(dh< -180)dh+=360;
 const dl=l2-l1,dc=cp2-cp1,dH=2*Math.sqrt(cp1*cp2)*Math.sin(dh*rad/2),lb=(l1+l2)/2,cb=(cp1+cp2)/2;
 let hb;if(cp1*cp2===0)hb=h1+h2;else if(Math.abs(h1-h2)<=180)hb=(h1+h2)/2;else hb=(h1+h2+(h1+h2<360?360:-360))/2;
 const t=1-.17*Math.cos((hb-30)*rad)+.24*Math.cos(2*hb*rad)+.32*Math.cos((3*hb+6)*rad)-.20*Math.cos((4*hb-63)*rad),theta=30*Math.exp(-Math.pow((hb-275)/25,2)),rc=2*Math.sqrt(cb**7/(cb**7+p25)),sl=1+.015*(lb-50)**2/Math.sqrt(20+(lb-50)**2),sc=1+.045*cb,sh=1+.015*cb*t,rt=-Math.sin(2*theta*rad)*rc;
 return Math.sqrt(Math.max(0,(dl/sl)**2+(dc/sc)**2+(dH/sh)**2+rt*(dc/sc)*(dH/sh)));
}
/** Bounded diagnostic only: full paired frames for light spill, ROI only for colourfulness. */
export function measureDraftVfxPixels(rgba,background,width,height,roi){
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0||width*height>4096*2160||rgba.length!==width*height*4||background.length!==rgba.length)throw new RangeError('Invalid paired FX raster');
 if(!roi||![roi.x,roi.y,roi.width,roi.height].every(Number.isInteger)||roi.width<=0||roi.height<=0||roi.x<0||roi.y<0||roi.x+roi.width>width||roi.y+roi.height>height)throw new RangeError('Invalid FX ROI');
 let changed=0,count=0,rg=0,yb=0,rg2=0,yb2=0,white=0;const cache=new Map();
 const lab=(r,g,b)=>{const key=r*65536+g*256+b;let value=cache.get(key);if(!value){value=rgbToLab(r,g,b);if(cache.size<4096)cache.set(key,value);}return value;};
 for(let i=0;i<rgba.length;i+=4){if(rgba[i+3]<16||rgba[i]===background[i]&&rgba[i+1]===background[i+1]&&rgba[i+2]===background[i+2])continue;
  if(deltaE00(lab(rgba[i],rgba[i+1],rgba[i+2]),lab(background[i],background[i+1],background[i+2]))<=5)continue;changed++;
  const x=(i/4)%width,y=Math.floor(i/4/width);if(x<roi.x||x>=roi.x+roi.width||y<roi.y||y>=roi.y+roi.height)continue;
  const r=rgba[i]-rgba[i+1],b=(rgba[i]+rgba[i+1])*.5-rgba[i+2];rg+=r;yb+=b;rg2+=r*r;yb2+=b*b;count++;if(Math.min(rgba[i],rgba[i+1],rgba[i+2])>=250)white++;
 }
 const m=count?Math.sqrt(Math.max(0,rg2/count-(rg/count)**2)+Math.max(0,yb2/count-(yb/count)**2))+.3*Math.hypot(rg/count,yb/count):null;
 return {changedPixels:changed,roiChangedPixels:count,screenCoverage:changed/(width*height),colourfulnessM:m,whiteClipFraction:count?white/count:null,basis:'Full-frame paired sRGB D65 CIEDE2000 deltaE>5 (light spill included); colourfulness only in changed ROI. Moving scene may contaminate; not object-ID isolation'};
}
