import {openSync,readSync,closeSync} from 'node:fs';
import {createHash} from 'node:crypto';

/** Sequential file pinning keeps one bounded scratch buffer, including for large GLBs. */
export function createFileHasher(chunkBytes=1024*1024) {
 if(!Number.isInteger(chunkBytes)||chunkBytes<1024||chunkBytes>8*1024*1024)throw new RangeError('Bounded hash chunk required');
 const buffer=Buffer.allocUnsafe(chunkBytes);
 return file=>{
  const digest=createHash('sha256'),fd=openSync(file,'r');
  try {
   for(;;){const count=readSync(fd,buffer,0,buffer.length,null);if(!count)break;digest.update(buffer.subarray(0,count));}
   return digest.digest('hex');
  }finally{closeSync(fd);}
 };
}
