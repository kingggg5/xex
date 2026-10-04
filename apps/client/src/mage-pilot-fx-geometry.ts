/** Original authored geometric spell shapes. No reference pixels or provider assets. */
export interface MageShape { positions: number[]; indices: number[]; colors: number[] }
const faceColours = [[.24,.61,.87],[.43,.79,.95],[.64,.88,.98],[.25,.43,.77]] as const;

export function magePointedShape(lance: boolean): MageShape {
 const length=lance?1.8:.45,width=lance?.16:.07;
 const p=[[0,0,length*.62],[-width,0,0],[0,width*.65,0],[width,0,0],[0,-width*.65,0],[0,0,-length*.38]];
 const faces=[[0,1,2],[0,2,3],[0,3,4],[0,4,1],[5,2,1],[5,3,2],[5,4,3],[5,1,4]];
 const shape:MageShape={positions:[],indices:[],colors:[]};
 for(const [i,face] of faces.entries())for(const v of face){shape.indices.push(shape.indices.length);shape.positions.push(...p[v]);shape.colors.push(...faceColours[i%4],v===0?.92:v===5?.10:.38);}
 // Four cyan physical ribs trace the faceted taper, in the SAME draw/material.
 // The tiny outward offset prevents coplanar shimmer; the tail rib fades away.
 for(const [nx,ny] of [[1,0],[0,1],[-1,0],[0,-1]]){
  const r=width*(ny?.65:1),w=lance?.009:.0035;
  const centres=[[nx*.0025,ny*.0025,length*.62],[nx*(r+.0025),ny*(r+.0025),0],[nx*.0025,ny*.0025,-length*.38]];
  for(let segment=0;segment<2;segment++){
   const start=shape.positions.length/3;
   for(const [j,sign] of [[segment,-1],[segment,1],[segment+1,1],[segment+1,-1]]){
    const c=centres[j];shape.positions.push(c[0]-ny*w*sign,c[1]+nx*w*sign,c[2]);shape.colors.push(.67,.94,1,j===2?.18:.97);
   }
   shape.indices.push(start,start+1,start+2,start,start+2,start+3);
  }
 }
 return shape;
}

/** Thin heptagon, inner seven-point construction and broken peripheral marks.
 * Every line is a narrow quad; the center stays genuinely empty geometry. */
export function mageOpenSigilShape(): MageShape {
 const shape:MageShape={positions:[],indices:[],colors:[]};
 const point=(i:number,r:number)=>[Math.sin(i*Math.PI*2/7)*r,Math.cos(i*Math.PI*2/7)*r] as const;
 const line=(a:readonly number[],b:readonly number[],width:number,colour:readonly number[])=>{
  const dx=b[0]-a[0],dy=b[1]-a[1],d=Math.hypot(dx,dy),nx=-dy/d*width/2,ny=dx/d*width/2,start=shape.positions.length/3;
  shape.positions.push(a[0]+nx,a[1]+ny,0,a[0]-nx,a[1]-ny,0,b[0]-nx,b[1]-ny,0,b[0]+nx,b[1]+ny,0);
  shape.indices.push(start,start+1,start+2,start,start+2,start+3);
  for(let i=0;i<4;i++)shape.colors.push(...colour,1);
 };
 for(let i=0;i<7;i++){
  line(point(i,.60),point(i+1,.60),.020,[.51,.87,.96]);
  line(point(i,.46),point(i+2,.46),.014,[.53,.47,.88]);
  const p=point(i,.65),q=point(i,.70);line(p,q,.022,[.79,.76,.54]);
 }
 return shape;
}

export function mageDynamicShape(quads:number): MageShape {
 const shape:MageShape={positions:new Array(quads*12).fill(0),indices:[],colors:[]};
 for(let i=0;i<quads;i++){
  const n=i*4;shape.indices.push(n,n+1,n+2,n,n+2,n+3);
  for(let v=0;v<4;v++)shape.colors.push(.39,.75,.92,v<2?.18:.82);
 }
 return shape;
}

/** Tetrahedral ice fragments: four facets per shard, one stable batch draw. */
export function mageShardShape(count:number):MageShape {
 const shape:MageShape={positions:new Array(count*12).fill(0),indices:[],colors:[]};
 for(let i=0;i<count;i++){
  const n=i*4;shape.indices.push(n,n+1,n+2,n,n+2,n+3,n,n+3,n+1,n+1,n+3,n+2);
  for(let v=0;v<4;v++)shape.colors.push(v===0?.73:.35,v===0?.96:.75,v===0?1:.93,v===0?.95:.53);
 }
 return shape;
}
