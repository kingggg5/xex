/** Bounded, page-local render validity. CPU submission time never proves pixels were drawn. */
export function createRendererHealth(){
 let errors=0,validationErrors=0,blank=null,probe='UNVERIFIED',messages=[],disposed=false;
 const scrub=value=>String(value??'Unknown GPU error').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/(https?:\/\/[^\s?]+)\?[^\s]+/g,'$1?[redacted]').slice(0,600);
 const snapshot=()=>({status:blank===true?'BLANK_RENDER':errors?'INVALID_RENDER':probe==='NONEMPTY_RGBA'?'NONEMPTY_OUTPUT':'UNVERIFIED',valid:errors||blank===true?false:probe==='NONEMPTY_RGBA'?true:null,blankRender:blank,gpuErrors:errors,validationErrors,probe,messages:messages.map(m=>({...m}))});
 function error(kind,message){if(disposed)return false;errors=Math.min(errors+1,1000000);if(kind==='GPUValidationError')validationErrors=Math.min(validationErrors+1,1000000);const entry={kind:scrub(kind).slice(0,64),message:scrub(message)};const retained=messages.length<8&&!messages.some(m=>m.kind===entry.kind&&m.message===entry.message);if(retained)messages.push(entry);return retained;}
 function readback(rgba,{ready=false,scope='unknown'}={}){
  if(disposed)return snapshot();
  // MSAA swap-chain readback is not a valid blank-output test. Only a resolved render target qualifies.
  if(!ready||scope!=='resolved-target'||!(rgba instanceof Uint8Array)||rgba.length<16||rgba.length%4!==0||rgba.length>65536){probe='UNAVAILABLE';return snapshot();}
  let empty=true,changed=false;const r=rgba[0],g=rgba[1],b=rgba[2],a=rgba[3];
  for(let i=0;i<rgba.length;i+=4){if(rgba[i]||rgba[i+1]||rgba[i+2]||rgba[i+3])empty=false;if(rgba[i]!==r||rgba[i+1]!==g||rgba[i+2]!==b||rgba[i+3]!==a)changed=true;}
  blank=empty;probe=empty?'EMPTY_RGBA':changed?'NONEMPTY_RGBA':'SOLID_RGBA';return snapshot();
 }
 return {error,readback,snapshot,dispose(){disposed=true;}};
}
