export function createMonsterViewRegistry<Snapshot extends {id:number;kind:number},View>(adapter:{create:(snapshot:Snapshot)=>View;update:(view:View,snapshot:Snapshot)=>void;dispose:(view:View,id:number)=>void},maximum?:number):{
	synchronize:(monsters:Snapshot[])=>void;dispose:()=>void;get:(id:number)=>View|undefined;size:()=>number;
};
