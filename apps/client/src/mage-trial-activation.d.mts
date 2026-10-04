import type {MageTrialState} from './mage-pilot-client.mjs';
export type MageActivationIntent=Readonly<{t:'mage_trial';enabled:true;op_id:string}>;
export class MageTrialActivation {
 constructor(now:()=>number,createId:()=>string);
 connect(epoch:number):void;confirm(profile:Readonly<MageTrialState>):void;settle(opId:string):void;
 poll(ready:boolean):{kind:'retry';intent:MageActivationIntent}|{kind:'reconnect'}|null;
}
