/** CPU oracle for the immutable D5 atlas and native water graph. No scene writes. */
export const WATER_DEPTH_D5_REVISION='d5-depth-oracle/1';
export const clampD5=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
export const smoothD5=(a,b,x)=>{const t=clampD5((x-a)/(b-a));return t*t*(3-2*t);};
export function sampleWaterAtlasD5(bytes,width,height,uv){
	if(bytes.length!==width*height*4||uv.length!==2||uv.some(x=>!Number.isFinite(x)))throw new TypeError('Finite RGBA atlas sample required');
	const x=clampD5(uv[0]*width-.5,0,width-1),y=clampD5(uv[1]*height-.5,0,height-1),ix=Math.floor(x),iy=Math.floor(y),fx=x-ix,fy=y-iy;
	const pixel=(px,py,c)=>bytes[(py*width+px)*4+c]/255;
	return [0,1,2,3].map(c=>(1-fy)*((1-fx)*pixel(ix,iy,c)+fx*pixel(Math.min(width-1,ix+1),iy,c))+fy*((1-fx)*pixel(ix,Math.min(height-1,iy+1),c)+fx*pixel(Math.min(width-1,ix+1),Math.min(height-1,iy+1),c)));
}
const mix=(a,b,t)=>a.map((v,i)=>v*(1-t)+b[i]*t);
const hex=h=>[1,3,5].map(i=>Math.pow(parseInt(h.slice(i,i+2),16)/255,2.2));
export function waterDepthGraphD5({red,viewY=.38,day=1,art=true,revision=3,blueprint=true,repairCove=false}){
	if([red,viewY,day].some(x=>!Number.isFinite(x))||red<0||red>1)throw new TypeError('Finite normalized graph inputs required');
	const optical=red*1.2*(1+.35*(1/clampD5(viewY,.25,1)-1));
	let body=mix(hex(blueprint?'#7cbbb1':'#6f9387'),hex(blueprint?'#38a9b8':'#386268'),smoothD5(.05,.75,optical));
	if(!art&&blueprint&&repairCove)body=mix(body,hex('#1b637b'),smoothD5(.38,1.15,optical));
	if(art){const r02=revision===2||revision===3,shallow=r02?mix(hex('#77bdb1'),hex('#719887'),day):hex('#77bdb1'),middle=r02?mix(hex('#38a9b8'),hex('#347c82'),day):hex('#38a9b8');body=mix(mix(shallow,middle,smoothD5(.03,.42,optical)),hex('#1b637b'),smoothD5(.38,1.15,optical));}
	return {optical,body,opacity:.16+.78*(1-Math.exp(-2.6*optical)),middleWeight:smoothD5(.03,.42,optical),deepWeight:smoothD5(.38,1.15,optical)};
}
