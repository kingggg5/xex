import test from 'node:test';import assert from 'node:assert/strict';import {build} from 'esbuild';import {fileURLToPath} from 'node:url';
const bundled=await build({entryPoints:[fileURLToPath(new URL('../src/audio.ts',import.meta.url))],bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const {CombatAudio}=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
function setup(rejectFirst=false){
	const instances=[];let htmlAudio=0;
	class Context{
		state='suspended';sampleRate=8000;currentTime=0;destination={};resumes=0;closes=0;
		constructor(){instances.push(this);}
		voices=[];
		createGain(){return {gain:{setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){},disconnect(){}};}
		createOscillator(){const voice={frequency:{setValueAtTime(){},exponentialRampToValueAtTime(){}},type:'sine',onended:null,connect(){},disconnect(){},start(){},stop(){}};this.voices.push(voice);return voice;}
		createBuffer(_channels,length){const data=new Float32Array(length);return {getChannelData:()=>data};}
		resume(){this.resumes++;if(rejectFirst&&this.resumes===1)return Promise.reject(new Error('activation required'));this.state='running';return Promise.resolve();}
		close(){this.closes++;this.state='closed';return Promise.resolve();}
	}
	const target=new EventTarget();target.AudioContext=Context;target.Audio=class{constructor(){htmlAudio++;}};
	const previous=globalThis.window;globalThis.window=target;
	const audio=new CombatAudio();
	return {target,audio,instances,html:()=>htmlAudio,cleanup(){audio.dispose();if(previous===undefined)delete globalThis.window;else globalThis.window=previous;}};
}
test('iOS activation uses release/click/keyboard; down/start never unlock or construct HTML audio',async()=>{
	const f=setup();try{
		for(const type of ['pointerdown','touchstart'])f.target.dispatchEvent(new Event(type));assert.equal(f.instances.length,0);
		f.target.dispatchEvent(new Event('touchend'));await Promise.resolve();assert.equal(f.instances[0].state,'running');assert.equal(f.html(),0);
		f.instances[0].state='interrupted';f.target.dispatchEvent(new Event('pointerup'));await Promise.resolve();assert.equal(f.instances[0].resumes,2);
	}finally{f.cleanup();}
});
test('rejected resume remains retryable and disposal removes activation handlers',async()=>{
	const f=setup(true);try{
		f.target.dispatchEvent(new Event('click'));await new Promise(resolve=>setImmediate(resolve));assert.equal(f.instances[0].state,'suspended');
		f.target.dispatchEvent(new Event('keydown'));await new Promise(resolve=>setImmediate(resolve));assert.equal(f.instances[0].state,'running');assert.equal(f.instances[0].resumes,2);
		f.audio.dispose();f.target.dispatchEvent(new Event('click'));assert.equal(f.instances.length,1);assert.equal(f.instances[0].closes,1);
	}finally{f.cleanup();}
});
test('Mage cues require prior activation, honor master mute, bound voices and release ended nodes',async()=>{
 const f=setup();try{
  f.audio.playMageCue('charge');assert.equal(f.instances.length,0);
  f.target.dispatchEvent(new Event('click'));await new Promise(resolve=>setImmediate(resolve));const ctx=f.instances[0];
  for(let i=0;i<20;i++)f.audio.playMageCue('release');assert.equal(ctx.voices.length,8);
  for(const voice of [...ctx.voices])voice.onended();f.audio.setMuted(true);f.audio.playMageCue('impact');assert.equal(ctx.voices.length,8);
  f.audio.setMuted(false);f.audio.playMageCue('level');assert.equal(ctx.voices.length,11);
  ctx.state='interrupted';f.audio.playMageCue('charge');assert.equal(ctx.voices.length,11);
 }finally{f.cleanup();}
});
