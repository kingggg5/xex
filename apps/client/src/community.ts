export type DeviceKind = "desktop" | "mobile" | "unknown";
export interface TradeOffer { gold: number; items: Record<string,number>;instance_ids?:string[] }
export type CommunityAction =
    | {kind:"sync";device:DeviceKind}
    | {kind:"invite";handle:string}
    | {kind:"accept"|"confirm";trade:string;revision:number}
    | {kind:"offer";trade:string;revision:number;offer:TradeOffer}
    | {kind:"cancel";trade:string}
    | {kind:"pass_claim";season:string;tier:number;premium:boolean;op_id:string}
    | {kind:"pass_premium";season:string;op_id:string}
    | {kind:"test_topup";pack:string;op_id:string}
    | {kind:"megaphone";text:string};
export interface CommunityState {
    rewards:Array<[number,number,number]>;packs:Array<[string,number]>;
    season:string;xp:number;tiers:number;xp_per_tier:number;premium:boolean;free_claims:number;premium_claims:number;
    test_credits:number;test_enabled:boolean;premium_test_cost:number;order_count:number;gold:number;durable:boolean;
    orders:Array<{id:string;pack:string;credits:number}>;
    items:Array<{id:string;count:number}>;
    players:Array<{handle:string;name:string;device:DeviceKind;nearby:boolean}>;
    trade:null|{id:string;revision:number;accepted:boolean;incoming:boolean;peer:string;peer_device:DeviceKind;mine:TradeOffer;theirs:TradeOffer;confirmed:boolean;peer_confirmed:boolean;pending:boolean};
}
export function deviceKind(value: unknown): DeviceKind {return value === "desktop" || value === "mobile" ? value : "unknown";}
export function detectDevice(mobileHint:unknown,agent:unknown,touches=0):DeviceKind {
    if(typeof mobileHint==="boolean")return mobileHint?"mobile":"desktop";
    if(typeof agent!=="string"||!agent)return "unknown";
    const ua=agent.slice(0,512);
    if(/Android|iPhone|iPod|iPad|Mobile/i.test(ua)||(/Macintosh/i.test(ua)&&touches>1))return "mobile";
    return /Windows|Macintosh|Linux|CrOS|X11/i.test(ua)?"desktop":"unknown";
}
export function currentDevice():DeviceKind {
    if(typeof navigator==="undefined")return "unknown";
    const hints=navigator as Navigator&{userAgentData?:{mobile?:boolean}};
    // Display hint only. Never send/store UA, hardware identifiers or high-entropy hints.
    return detectDevice(hints.userAgentData?.mobile,navigator.userAgent,navigator.maxTouchPoints);
}
const record=(v:unknown):v is Record<string,unknown>=>typeof v==="object"&&v!==null&&!Array.isArray(v);
const amount=(v:unknown,max=2_147_483_647):v is number=>Number.isSafeInteger(v)&&Number(v)>=0&&Number(v)<=max;
const text=(v:unknown,max=64):v is string=>typeof v==="string"&&v.length<=max;
function offer(value:unknown):value is TradeOffer {return record(value)&&amount(value.gold,1_000_000)&&record(value.items)&&Object.keys(value.items).length<=6&&Object.entries(value.items).every(([id,n])=>/^[A-Za-z0-9_]{1,64}$/.test(id)&&amount(n,99)&&Number(n)>0);}
/** Fail closed at the socket boundary; engine objects never enter UI state. */
export function parseCommunity(value:unknown):CommunityState|null {
    if(!record(value)||!text(value.season)||value.tiers!==20||value.xp_per_tier!==100||!amount(value.xp,2000))return null;
    if(!Array.isArray(value.rewards)||value.rewards.length!==20||!value.rewards.every((r,i)=>Array.isArray(r)&&r.length===3&&r[0]===i+1&&amount(r[1],10000)&&amount(r[2],10000)))return null;
    if(!Array.isArray(value.packs)||value.packs.length>8||!value.packs.every(p=>Array.isArray(p)&&p.length===2&&typeof p[0]==="string"&&/^[a-z0-9_]{1,32}$/.test(p[0])&&amount(p[1],10000)))return null;
    for(const key of ["free_claims","premium_claims"])if(!amount(value[key],(1<<20)-1))return null;
    for(const key of ["test_credits","premium_test_cost","order_count","gold"])if(!amount(value[key]))return null;
    for(const key of ["premium","test_enabled","durable"])if(typeof value[key]!=="boolean")return null;
    if(!Array.isArray(value.orders)||value.orders.length>5||!value.orders.every(o=>record(o)&&text(o.id,36)&&text(o.pack)&&amount(o.credits,600)))return null;
    if(!Array.isArray(value.items)||value.items.length>12||!value.items.every(i=>record(i)&&text(i.id)&&amount(i.count,99)))return null;
    if(!Array.isArray(value.players)||value.players.length>12||!value.players.every(p=>record(p)&&text(p.handle,24)&&text(p.name,64)&&["desktop","mobile","unknown"].includes(String(p.device))&&typeof p.nearby==="boolean"))return null;
    if(value.trade!==null){const t=value.trade;if(!record(t)||!text(t.id,36)||!amount(t.revision)||!text(t.peer)||!offer(t.mine)||!offer(t.theirs)||!["desktop","mobile","unknown"].includes(String(t.peer_device)))return null;for(const key of ["accepted","incoming","confirmed","peer_confirmed","pending"])if(typeof t[key]!=="boolean")return null;}
    const pick=(input:Record<string,unknown>,keys:string[])=>Object.fromEntries(keys.map(key=>[key,input[key]]));
    const fields=pick(value,["season","xp","tiers","xp_per_tier","premium","free_claims","premium_claims","test_credits","test_enabled","premium_test_cost","order_count","gold","durable","rewards","packs"]);
    fields.orders=value.orders.map(o=>pick(o,["id","pack","credits"]));
    fields.items=value.items.map(i=>pick(i,["id","count"]));
    fields.players=value.players.map(p=>pick(p,["handle","name","device","nearby"]));
    const t=value.trade;
    fields.trade=t===null?null:{...pick(t as Record<string,unknown>,["id","revision","accepted","incoming","peer","peer_device","confirmed","peer_confirmed","pending"]),mine:{gold:(t as Record<string,TradeOffer>).mine.gold,items:{...(t as Record<string,TradeOffer>).mine.items}},theirs:{gold:(t as Record<string,TradeOffer>).theirs.gold,items:{...(t as Record<string,TradeOffer>).theirs.items}}};
    return structuredClone(fields) as unknown as CommunityState;
}
export const COMMUNITY_COPY:Record<string,[string,string]>={
    accepted:["Updated","อัปเดตแล้ว"],trade_invited:["A player invited you to trade. Open Trade to review.","มีผู้เล่นขอเทรด เปิดหน้าแลกเปลี่ยนเพื่อตรวจสอบ"],trade_complete:["Trade completed","แลกเปลี่ยนสำเร็จ"],trade_cancelled:["Trade cancelled","ยกเลิกการเทรดแล้ว"],offer_changed:["Offer changed. Review it before confirming again.","ข้อเสนอเปลี่ยนแล้ว ตรวจสอบก่อนยืนยันใหม่"],out_of_range:["Stand within 12 metres of your trading partner.","ยืนห่างจากคู่เทรดไม่เกิน 12 เมตร"],trade_busy:["One of you is already trading.","มีฝ่ายหนึ่งกำลังเทรดอยู่"],not_enough_gold:["Not enough gold","ทองไม่เพียงพอ"],not_enough_items:["Some offered items are no longer available.","ไอเท็มที่เสนอมีไม่ครบแล้ว"],inventory_full:["No inventory space or stack is full.","กระเป๋าหรือจำนวนซ้อนเต็ม"],item_not_tradeable:["Equipped items cannot be traded.","ของที่สวมใส่อยู่แลกเปลี่ยนไม่ได้"],already_claimed:["Reward already claimed","รับรางวัลนี้แล้ว"],tier_locked:["Earn more season XP first.","สะสม EXP ซีซันเพิ่มก่อน"],premium_required:["Premium track required","ต้องเปิดสิทธิ์ Premium ก่อน"],not_enough_test_credits:["Add preview credits from Test Top-up.","เพิ่มเครดิตทดลองจากหน้าเติมเงินทดสอบ"],test_disabled:["Test commerce is disabled on this server.","เซิร์ฟเวอร์นี้ยังไม่เปิดระบบเติมเงินทดสอบ"],megaphone_cooldown:["Megaphone: wait 30 seconds between announcements.","โทรโข่งส่งได้ทุก 30 วินาที"],storage_pending:["Waiting for storage. Please try again.","กำลังรอระบบบันทึกข้อมูล ลองใหม่อีกครั้ง"],trade_committing:["Finalising the exchange. Items are temporarily locked.","กำลังบันทึกการแลกเปลี่ยน ไอเท็มถูกล็อกชั่วคราว"],trade_storage_conflict:["Trade stopped because character ownership changed.","หยุดเทรดเพราะข้อมูลหรือผู้ครอบครองตัวละครเปลี่ยน"],operation_conflict:["This order ID belongs to a different request.","รหัสคำสั่งนี้ใช้กับรายการอื่นแล้ว"],test_order_limit:["Preview order limit reached (64).","ครบเพดานรายการทดสอบ 64 รายการแล้ว"],test_wallet_full:["Preview credit cap reached (10,000).","ครบเพดานเครดิตทดลอง 10,000 แล้ว"],player_unavailable:["Player is no longer available.","ผู้เล่นไม่พร้อมใช้งานแล้ว"],trade_expired:["This trade has ended.","การเทรดนี้สิ้นสุดแล้ว"]
};
