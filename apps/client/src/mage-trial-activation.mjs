/** Retry one exact activation identity. No profile, item or resource is granted locally. */
export class MageTrialActivation {
 constructor(now,createId){this.now=now;this.createId=createId;this.connect(0);}
 connect(epoch){this.epoch=epoch;this.intent=null;this.attempts=0;this.nextAt=0;this.done=false;this.unknown=false;}
 confirm(profile){if(profile?.epoch===this.epoch&&(profile.profile==='mage_trial'||profile.capability_enabled===false))this.done=true;}
 settle(opId){if(this.intent?.op_id===opId)this.done=true;}
 poll(ready){
  const now=this.now();if(!ready||!this.epoch||this.done||this.unknown||!Number.isFinite(now)||now<this.nextAt)return null;
  if(this.attempts===4){this.unknown=true;return{kind:'reconnect'};}
  if(!this.intent)this.intent=Object.freeze({t:'mage_trial',enabled:true,op_id:this.createId()});
  this.attempts++;this.nextAt=now+1000;return{kind:'retry',intent:this.intent};
 }
}
