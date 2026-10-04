// Existing admitted dais is an 8.5 m solid platform. Activate from the surrounding path.
export const DUNGEON_WARP_HUB=Object.freeze({id:'warp_city_portal_dais',x:40,z:186,radius:10.4,effectDistance:72,platformTopY:.8,cityLocalXZ:[40,10]});
export const DUNGEON_DESTINATIONS=Object.freeze([
	{id:'tower',name:'Tower of Trials',thai:'หอคอยทดสอบ',description:'100 floors · private instance',thaiDescription:'100 ชั้น · ห้องส่วนตัว',kind:'live-tower'},
	{id:'sunken_temple_of_aurel',name:'Sunken Temple of Aurel',thai:'วิหารสุริยันจมน้ำ',description:'Party dungeon · in development',thaiDescription:'ดันเจียนปาร์ตี้ · กำลังพัฒนา',kind:'planned'},
	{id:'rimecrest_snow',name:'Rimecrest Wilds',thai:'ดินแดนหิมะ Rimecrest',description:'Snow region · in development',thaiDescription:'แมพหิมะ · กำลังพัฒนา',kind:'planned'},
]);
export function warpDestinationEnabled(id,{connected=false,busy=false}={}){return id==='tower'&&connected&&!busy;}
export function warpProximity(player,origin=DUNGEON_WARP_HUB){
	if(!player||![player.x,player.z,origin.x,origin.z].every(Number.isFinite))return {near:false,effects:false};
	const distance=Math.hypot(player.x-origin.x,player.z-origin.z);
	return {near:distance<=origin.radius,effects:distance<=origin.effectDistance};
}
