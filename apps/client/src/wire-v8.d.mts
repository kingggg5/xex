import type {ServerMessage} from './protocol';
export const V8_BASELINE_LIMIT: 32;
export const V8_VISIBLE_LIMIT: 64;
export class ResyncRequired extends Error {readonly reason:string;constructor(reason:string);}
export interface SnapshotDecoder {
	decode(data:ArrayBuffer,zoneLimit?:number):ServerMessage;
	reset():void;
	snapshotAck():{epoch:number;tick:bigint}|null;
	retainedBaselines():number;
}
export function createSnapshotDecoder():SnapshotDecoder;
export function encodeSnapshotAck(epoch:number,tick:bigint,resync?:boolean):ArrayBuffer;
