/** Art review identity only. This cannot unlock a class or execute draft damage. */
export const HERO_REVIEW_ROSTER=Object.freeze([
 {id:'01',name:'Swordsman',state:'FITTED_RIG_CANDIDATE'},
 {id:'02',name:'Mage',state:'RIGGED_REVIEW_CANDIDATE'},
 {id:'03',name:'Archer',state:'TURNAROUND_APPROVED'},
 {id:'04',name:'Acolyte',state:'P2_PBR_SOURCE_RIG_REPAIR'},
 {id:'05',name:'Thief',state:'INPUT_QA_REQUIRED'},
 {id:'06',name:'Merchant',state:'P2_PBR_SOURCE_RIG_PENDING'},
].map(Object.freeze));
export function heroReviewIdentity(search,dev){
 if(!dev)return null;
 const id=new URLSearchParams(search).get('heroReview');
 if(id==='01')return {id,scale:1,idle:'base.idle',run:'base.run',attacks:['blade_1h.attack_1','blade_1h.attack_2'],isAttack:name=>name.startsWith('blade_1h.attack_')};
 return id==='02'?{id,scale:1,idle:'base.idle',run:'base.run',attacks:['caster.attack_1','caster.attack_2'],isAttack:name=>name.startsWith('caster.attack_')}:null;
}
export const MAGE_REVIEW_SKILLS=Object.freeze([
 {id:'h02_hoarfrost_gale',clip:'mage.skill_gale',name:'Hoarfrost Gale'},
 {id:'h02_rimeshard_nova',clip:'mage.skill_nova',name:'Rimeshard Nova'},
 {id:'h02_starless_hollow',clip:'mage.skill_rift',name:'Starless Hollow'},
 {id:'h02_star_lance',clip:'mage.skill_bolt',name:'Star Lance'},
 {id:'h02_moonveil_ward',clip:'mage.skill_ward',name:'Moonveil Ward'},
 {id:'h02_celestial_orrery',clip:'mage.skill_starfall',name:'Celestial Orrery'},
].map(Object.freeze));
