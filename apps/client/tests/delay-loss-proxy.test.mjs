import test from 'node:test';
import assert from 'node:assert/strict';
import {FramePipe} from '../../../tools/delay-loss-proxy.mjs';
test('impairment proxy delivers a burst in FIFO order despite fractional deadlines',async()=>{
	const delivered=[];let resolveDone;
	const done=new Promise(resolve=>resolveDone=resolve);
	const pipe=new FramePipe(()=>.5,25,5,0,bytes=>{delivered.push(bytes.readUInt32LE());if(delivered.length===600)resolveDone();},'test',()=>assert.fail('bounded burst must not overflow'));
	for(let id=0;id<600;id++){const b=Buffer.alloc(4);b.writeUInt32LE(id);assert.equal(pipe.enqueue(b,20+id%7),true);}
	let timeout;try {await Promise.race([done,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('proxy did not finish its bounded queue')),2000);})]);}finally{clearTimeout(timeout);}
	assert.deepEqual(delivered,Array.from({length:600},(_,i)=>i));assert.equal(pipe.queuedBytes,0);assert.equal(pipe.queuedFrames,0);
});
test('impairment proxy refuses a byte overflow before allocating queued work',()=>{
	let closed=0;const pipe=new FramePipe(()=>.5,25,5,0,()=>assert.fail('overflow cannot be forwarded'),'test',()=>closed++);
	assert.equal(pipe.enqueue(Buffer.alloc(1024*1024+1),25),false);assert.equal(closed,1);assert.equal(pipe.queuedBytes,0);assert.equal(pipe.queuedFrames,0);assert.equal(pipe.queue.length,0);
});
