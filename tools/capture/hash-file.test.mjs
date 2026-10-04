import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,unlinkSync,rmdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createFileHasher} from './hash-file.mjs';

test('bounded file pins match SHA256 across empty, chunk-boundary and multi-chunk files; repeated reads detect edits',()=>{
 const folder=mkdtempSync(join(tmpdir(),'xexoria-hash-')),file=join(folder,'fixture.bin'),hash=createFileHasher(1024);
 try{
  for(const bytes of [0,1023,1024,1025,1024*3+17]){
   const fixture=Buffer.alloc(bytes);for(let i=0;i<bytes;i++)fixture[i]=(i*29+7)%256;
   writeFileSync(file,fixture);assert.equal(hash(file),createHash('sha256').update(fixture).digest('hex'));
  }
  const before=hash(file);writeFileSync(file,'changed');assert.notEqual(hash(file),before);
  assert.throws(()=>hash(join(folder,'missing.bin')));assert.equal(hash(file),createHash('sha256').update('changed').digest('hex'));
 }finally{unlinkSync(file);rmdirSync(folder);}
});
