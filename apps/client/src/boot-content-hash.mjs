/** Exact FNV-1a-64, using integer halves per byte; BigInt is constructed once at the boundary. */
export function fnv1a64Halves(bytes){
	if(!(bytes instanceof Uint8Array))throw new TypeError('Content hash requires Uint8Array bytes.');
	let hi=0xcbf29ce4,lo=0x84222325;
	for(let i=0;i<bytes.length;i++){
		const low=(lo^bytes[i])>>>0;
		const product=low*0x1b3; // <2^41: exact in IEEE-754's 53-bit integer range.
		hi=(Math.imul(hi,0x1b3)+Math.floor(product/0x100000000)+(low<<8))>>>0;
		lo=product>>>0;
	}
	return (BigInt(hi)<<32n)|BigInt(lo);
}
