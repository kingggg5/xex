import { parseCommunity,COMMUNITY_COPY,currentDevice } from "./community";
import type { CommunityAction } from "./community";
import type { ActionKind } from "./protocol";
import type { CharacterStateMessage, DialogueMessage, PartyStateMessage, QuestStateMessage } from "./cold_v4.gen";
import { initChat, onSystemLine, setChatGroupAvailable, appendLocalChat, releaseChat } from "./chat";
import type { ChatChannel } from "./chat";
import type { CosmeticSlot, EconomyWalletState } from "./economy-ui";
import { parseFriendEntries, parseFriendsBody, parseGroupBody, parseGroupInfo, sanitizeDisplayName } from "./social-parse.mjs";
import type { FriendEntry, GroupInfo } from "./social-ui";
import { isChannelId, isRoomRow } from "./rooms-ui";
import type { ChannelState } from "./rooms-ui";
import { parseTowerState, sanitizeTowerState } from "./tower-ui";
import type { TowerState } from "./tower-ui";
import type { WorldRouteDefinition } from "./world-layout";
import { applyPrefs, loadPrefs } from "./settings";
import { mountGameUi } from "./ui/bridge.svelte";
import type { UiDomBridge } from "./ui/bridge.svelte";
import { loadShopCatalog } from "./ui/store-data";
import type { InventorySnapshot, ShopCatalog } from "./ui/types";
import { createHudSnapshot } from "./ui/hud-types";
import type { HudSnapshot } from "./ui/hud-types";
import { createPanelSnapshot, characterPanelData, partyPanelData, dialoguePanelData, presencePanelData, groupPanelData, roomPanelData, mapPanelData, journalPanelData, settingsPanelData, changeSettingsPreferences, changeGraphicsPreference, changeEnvironmentPreference, resetPanelSettings } from "./ui/panel-data";
import type { PanelSnapshot } from "./ui/panel-types";
import type {MageTrialState} from './mage-pilot-client.mjs';
import {characterSnapshotDecision} from './character-snapshot-policy.mjs';
import { actionByCode } from "./combat-actions.mjs";
import { emptyCombatView, nextCombatView, emptyDeathView, nextDeathView, confirmAliveView, canReturnToTown, startTownRequest, applyTownResult, createResourceStates, updateResource, nextTransactions, RESOURCE_KEYS, normalizeReadability,parseItemInstances } from "./ui/combat-model";
import type { CombatPresentation, DeathStateDTO, ReturnToTownResult, PanelResourceState, ResourceKey, UiTransaction, CombatReadability,InventoryInstanceEntry,ItemMoveIntent } from "./ui/combat-model";
import { loadCombatReadability, saveCombatReadability } from "./ui/combat-readability";
export type { CombatPresentation, CombatActorPresentation, DeathStateDTO, ReturnToTownResult, ResourceKey, PanelResourceState, UiTransaction, CombatReadability,ItemMoveIntent } from "./ui/combat-model";
export interface MovementInput {
    x: number;
    z: number;
}
export interface UiHooks {
    onMoveItemInstance?(opId:string,instanceId:string,expectedRevision:number,to:"bag"|"weapon"|"armor"):boolean;
    itemEquipmentSlot?(def:string):"weapon"|"armor"|null;
    onReturnToTown?(opId: string, deathRevision: number): boolean;
    onRefreshResource?(key: ResourceKey): boolean;
    onCombatReadabilityChanged?(value: CombatReadability): void;
    onCommunity?(action:CommunityAction): boolean;
    onAction(action: ActionKind): void;
    onPotion(opId: string | null): boolean;
    onContext(action: ContextAction): void;
    onChoose(npc: string, token: string, choice: string): void;
    onClaim(quest: string): void;
    onParty(action: {
        kind: "create" | "join" | "leave";
        code?: string;
    }): void;
    // D-14 economy hooks; main.ts supplies them later. Optional so existing
    // constructions keep compiling — GameHud defaults them to a toast.
    onBuy?(itemOrCosmeticId: string): void;
    onOpenBox?(boxId: string): void;
    onEquip?(slot: CosmeticSlot, id: string): void;
    // E07: equip a weapon/armor bag item; `equippable` reports whether the
    // bundle marks the item as gear (main.ts reads the content bundle).
    onEquipItem?(item: string): void;
    equippable?(item: string): boolean;
    onUseItem?(item: string): void;
    isConsumable?(item: string): boolean;
    isBox?(item: string): boolean;
    onAllocateStat?(stat: "str" | "agi" | "vit" | "int" | "dex" | "luk"): void;
    onRefineItem?(slot: "weapon" | "armor",instanceId?:string,expectedRevision?:number): void;
    // Tower + channel hooks; main.ts supplies them later (same pattern as the
    // economy hooks above — optional, defaulted to a "coming online soon" toast).
    onTowerEnter?(): void;
    onTowerLeave?(): void;
    onChannelPicked?(channel: number | null): void;
    // Social hooks (live chat, friends, groups); same optional pattern. main.ts
    // supplies them later — they encode the cold messages chat/friend_add/
    // friend_remove/group_create/group_join/group_leave.
    onChatSend?(channel: ChatChannel, text: string): void;
    onFriendAdd?(handle: string): void;
    onFriendRemove?(handle: string): void;
    onGroupCreate?(): void;
    onGroupJoin?(code: string): void;
    onGroupLeave?(): void;
    itemName(item: string): string;
    questName(quest: string): string;
    translate(key: string): string;
    language: "en" | "th";
}
export interface ContextAction {
    kind: "talk" | "activate" | "pickup";
    id: string;
    label: string;
}
/** Compatibility controller: validated server data and input intent, with no window rendering. */
export class GameHud {
    private readonly keys = new Set<string>();
    private touchX = 0;
    private touchZ = 0;
    private online = false;
    private connectionInterrupted = false;
    private disposed = false;
    private combatView = emptyCombatView();
    private deathView = emptyDeathView();
    private resourceStates = createResourceStates();
    private transactions: UiTransaction[] = [];
    private itemInstances:InventoryInstanceEntry[]=[];
    private instanceDataKnown=false;
    private mageHudKey='';
    private pendingItemMoves=new Map<string,ItemMoveIntent>();
    private transactionTimers=new Map<string,number>();
    private combatReadability = normalizeReadability(null);
    private returnTownTimer = 0;
    private chatExpanded = false;
    private recovering = false;
    private worldLoading = false;
    private activeModal: string | null = null;
    private characterRevision = 0;
    private characterAuthorityId:string|null=null;
    private questRevision = 0;
    private partyRevision = 0;
    private characterState: CharacterStateMessage | null = null;
    private partyState: PartyStateMessage | null = null;
    private walletState: EconomyWalletState = { gold: 0, coin: 0, ownedCosmetics: [], skin: null, pet: null, bagCounts: {} };
    private towerState: TowerState = { inTower: false, floor: 0, bestFloor: 0 };
    private channelState: ChannelState = { rooms: null, current: null };
    private friendsList: FriendEntry[] = [];
    private groupState: GroupInfo | null = null;
    private playerDisplayName: string | null = null;
    private contextAction: ContextAction | null = null;
    private pendingPotionOpId = "";
    private potions = 3;
    private xp = 0;
    private slimeKills = 0;
    private clover = 0;
    private mapPoints: Record<string, {
        x: number;
        z: number;
    }> = {};
    private mapRoutes: WorldRouteDefinition[] = [];
    private mapExtent = 28;
    private mapX = 0;
    private mapZ = 0;
    private lastPositionUpdate = 0;
    private toastSequence = 0;
    private shopCatalog: ShopCatalog = { entries: [], boxes: [] };
    private shopStatus: "loading" | "ready" | "unavailable" = "loading";
    private shopRequested = false;
    private shopGeneration = 0;
    private readonly uiEvents = new AbortController();
    private readonly hudView: HudSnapshot;
    private readonly panelsView: PanelSnapshot;
    private domUi!: UiDomBridge;
    constructor(private readonly hooks: UiHooks) {
        this.hudView = createHudSnapshot(hooks.language);
        this.panelsView = createPanelSnapshot(hooks.language);
        const hudRoot = document.getElementById("hud");
        const modalRoot = document.getElementById("modal-backdrop");
        const chatRoot = document.querySelector<HTMLElement>(".chat");
        if (!hudRoot || !modalRoot || !chatRoot)
            throw new Error("Game UI mount hosts are missing");
        const unavailable = () => this.showToast(hooks.language === "th" ? "ระบบนี้ยังไม่พร้อมให้บริการ" : "This feature is not available yet");
        this.domUi = mountGameUi(hudRoot, modalRoot, chatRoot, hooks.language, {
            moveItemInstance: (id,revision,to)=>this.moveItemInstance(id,revision,to),
            returnToTown: () => this.requestReturnToTown(),
            refreshResource: key => this.refreshPanelResource(key),
            readabilityChanged: value => this.setCombatReadability(value),
            community: action => { if(!this.online)return; if(hooks.onCommunity?.(action)) this.domUi.update({communityPending:true}); else this.showToast(hooks.language==="th"?"ส่งรายการไม่สำเร็จ ตรวจการเชื่อมต่อหรือลดไอเท็มที่เสนอ":"Could not send. Check your connection or offer fewer items."); },
            closeModal: () => this.closeModal(),
            inventoryAction: (item, action) => {
                if (!this.online)
                    return;
                if (action === "equip")
                    hooks.onEquipItem?.(item);
                else if (action === "open")
                    hooks.onOpenBox?.(item);
                else if (item === "trail_potion")
                    this.usePotion();
                else
                    hooks.onUseItem?.(item);
            },
            buy: id => { if (this.online)
                hooks.onBuy?.(id); },
            openBox: id => { if (this.online)
                hooks.onOpenBox?.(id); },
            equip: (slot, id) => { if (this.online)
                hooks.onEquip?.(slot, id); },
            chatExpanded: expanded => { this.chatExpanded = expanded; if (this.domUi) {
                if (expanded)
                    this.neutralizeMovement();
                this.syncInput();
            } },
            hud: {
                action: action => { if (!this.inputBlocked())
                    hooks.onAction(action); },
                potion: () => { if (!this.inputBlocked())
                    this.usePotion(); },
                context: () => { if (!this.inputBlocked() && this.contextAction)
                    hooks.onContext(this.contextAction); },
                openModal: name => this.openModal(name),
                questsCollapsed: collapsed => this.patchHud({ quests: { ...this.hudView.quests, collapsed } }),
                movement: (x, z) => { this.touchX = this.inputBlocked() ? 0 : x; this.touchZ = this.inputBlocked() ? 0 : z; },
                fullscreen: () => { void this.toggleFullscreen(); },
            },
            panels: {
                openPanel: name => this.openModal(name), closeModal: () => this.closeModal(),
                allocateStat: stat => {
                    if(!this.online||this.deathView.down||this.recovering||this.worldLoading||!this.characterState?.stat_points||this.transactions.some(tx=>(tx.resource==="inventory"||tx.resource==="character")&&(tx.phase==="submitting"||tx.phase==="outcome-unknown")))return;
                    hooks.onAllocateStat?.(stat);
                },
                moveItemInstance: (id,rev,to) => this.moveItemInstance(id,rev,to),
                selectInventoryInstance: id => {
                    if(!this.itemInstances.some(row=>row.instanceId===id))return;
                    this.patchPanels({selectedInventoryInstanceId:id});
                },
                refineItem: (slot,instanceId,expectedRevision) => {
                    if(!this.online||this.deathView.down||this.transactions.some(tx=>(tx.resource==="inventory"||tx.resource==="character")&&(tx.phase==="submitting"||tx.phase==="outcome-unknown")))return;
                    if(expectedRevision!==undefined&&expectedRevision!==this.characterRevision)return;
                    const instance=instanceId?this.itemInstances.find(row=>row.instanceId===instanceId&&row.location===slot):this.itemInstances.find(row=>row.location===slot);
                    if(this.instanceDataKnown&&!instance)return;
                    hooks.onRefineItem?.(slot,instance?.instanceId,instance?this.characterRevision:undefined);
                },
                party: action => { if (this.online)
                    hooks.onParty(action); },
                choose: (npc, token, choice) => { if (this.online)
                    hooks.onChoose(npc, token, choice); this.closeModal(); },
                claim: quest => { if (this.online)
                    hooks.onClaim(quest); this.closeModal(); },
                friendAdd: handle => { if (this.online)
                    hooks.onFriendAdd?.(handle); },
                friendRemove: handle => { if (this.online)
                    hooks.onFriendRemove?.(handle); },
                groupCreate: () => { if (this.online)
                    hooks.onGroupCreate?.(); },
                groupJoin: code => { if (this.online)
                    hooks.onGroupJoin?.(code); },
                groupLeave: () => { if (this.online)
                    hooks.onGroupLeave?.(); },
                towerEnter: () => { if (this.online)
                    (hooks.onTowerEnter ?? unavailable)(); },
                towerLeave: () => { if (this.online)
                    (hooks.onTowerLeave ?? unavailable)(); },
                channelPicked: channel => { if (this.online)
                    hooks.onChannelPicked?.(channel); },
                settingsChanged: prefs => changeSettingsPreferences(prefs),
                resetSettings: () => resetPanelSettings(),
                graphicsChanged: choice => changeGraphicsPreference(choice),
                environmentChanged: change => changeEnvironmentPreference(change),
            },
        });
        this.domUi.updateHud(this.hudView);
        this.domUi.updatePanels(this.panelsView);
        this.combatReadability = loadCombatReadability(uiStorage(),loadPrefs().shake);
        this.deathView = { ...this.deathView, canSubmit: !!hooks.onReturnToTown };
        this.domUi.update({ readability:this.combatReadability, readabilitySupported:!!hooks.onCombatReadabilityChanged, resourceRefreshSupported:!!hooks.onRefreshResource, death:this.deathView, resources:this.resourceStates });
        this.syncInventoryView();
        this.syncShopView();
        applyPrefs(loadPrefs());
        initChat(this, (channel, text) => {
            if (hooks.onChatSend)
                hooks.onChatSend(channel, text);
            else if (!this.online)
                this.addChat(text, channel === "group" ? "party" : "world");
            else
                unavailable();
        });
        const signal = this.uiEvents.signal;
        window.addEventListener("keydown", event => this.onKeyDown(event), { signal });
        window.addEventListener("keyup", event => this.keys.delete(normalizeKey(event)), { signal });
        window.addEventListener("blur", () => this.neutralizeMovement(), { signal });
        window.addEventListener("aetherfield:renderer-lost", () => { this.recovering = true; this.neutralizeMovement(); this.syncInput(); }, { signal });
        window.addEventListener("aetherfield:renderer-restored", () => { this.recovering = false; this.syncInput(); }, { signal });
        window.addEventListener("aetherfield:environment-state", event => {
            const value = (event as CustomEvent<{
                clockText?: unknown;
            }>).detail?.clockText;
            if (typeof value === "string" && value.length <= 32)
                this.patchHud({ timeLabel: value });
        }, { signal });
        document.addEventListener("visibilitychange", () => { if (document.hidden)
            this.neutralizeMovement(); this.syncInput(); }, { signal });
        document.addEventListener("fullscreenchange", () => this.patchHud({ fullscreenActive: !!document.fullscreenElement }), { signal });
        window.addEventListener("pagehide", event => { if (!event.persisted)
            this.dispose(); }, { signal });
        this.patchHud({ fullscreenAvailable: document.fullscreenEnabled, fullscreenActive: !!document.fullscreenElement });
    }
    private patchHud(patch: Partial<HudSnapshot>): void { Object.assign(this.hudView, patch); this.domUi?.updateHud(patch); }
    setMageTrialHud(requested:boolean,state:Readonly<MageTrialState>|null,sp:number|null):void {
        if(!requested&&!this.mageHudKey)return;
        const key=JSON.stringify([requested,this.online,state,sp]);if(key===this.mageHudKey)return;this.mageHudKey=key;
        const defaults=createHudSnapshot(this.hooks.language).abilities,th=this.hooks.language==='th';
        const allowed=this.online&&state?.capability_enabled&&state.profile==='mage_trial'&&state.focus_equipped;
        const abilities=this.hudView.abilities.map(row=>{
            if(row.action!=='attack'&&row.action!=='arc_slash')return row;
            if(!requested){const original=defaults.find(a=>a.action===row.action)!;const {description,spCost,rangeM,...plain}=row;return{...plain,label:original.label,art:original.art,disabled:false};}
            const id=row.action==='attack'?'h02_basic':'h02_star_lance',skill=state?.skills.find(s=>s.skill_id===id);
            return{...row,label:row.action==='attack'?(th?'ศรดารา':'Starmote Bolt'):(th?'หอกดารา':'Star Lance'),art:(row.action==='attack'?'mage-basic-art':'mage-lance-art') as typeof row.art,
                ...(skill?{spCost:skill.sp_cost,rangeM:skill.range_m}:{}),description:th?'ชุดทดลองเวท · ผลยืนยันจากเซิร์ฟเวอร์':'Mage trial · server-confirmed outcomes',disabled:!allowed||!skill?.available||sp===null||sp<skill.sp_cost};
        });
        const confirmed=this.online&&state?.capability_enabled&&state.profile==='mage_trial';
        const modeNote=!requested?null:confirmed?(state.focus_equipped?(th?'ชุดทดลองเวท':'Mage trial'):(th?'ชุดทดลองเวท · สวมโฟกัสอาคม':'Mage trial · equip Arcane Focus')):this.online&&state?.capability_enabled===false?(th?'เซิร์ฟเวอร์นี้ยังไม่เปิดชุดทดลองเวท':'Mage trial unavailable on this server'):(th?'ชุดทดลองเวท · รอเซิร์ฟเวอร์':'Mage trial · waiting for server');
        this.patchHud({abilities,modeNote});
    }
    private patchPanels(patch: Partial<PanelSnapshot>): void { Object.assign(this.panelsView, patch); this.domUi?.updatePanels(patch); }
    private inputBlocked(): boolean { return this.disposed || this.deathView.down || this.connectionInterrupted || this.chatExpanded || this.activeModal !== null || this.recovering || this.worldLoading || document.hidden; }
    isGameplayBlocked(): boolean { return this.inputBlocked(); }
    releaseMovement(): void { this.neutralizeMovement(); this.syncInput(); }
    setCombatPresentation(value: CombatPresentation): boolean {
        if (this.disposed) return false;
        const next = nextCombatView(this.combatView, value);
        if (!next) return false;
        this.combatView = next; this.domUi.update({combat:next}); return true;
    }
    setDeathState(value: DeathStateDTO): boolean {
        if (this.disposed) return false;
        const next = nextDeathView(this.deathView, value); if (!next) return false;
        const entering = next.down && !this.deathView.down;
        const replaced = next.revision !== this.deathView.revision || !next.down;
        this.deathView = { ...next, online:this.online, canSubmit:!!this.hooks.onReturnToTown };
        if (replaced) window.clearTimeout(this.returnTownTimer);
        if (entering) this.closeModal();
        if (next.down) this.neutralizeMovement();
        this.domUi.update({death:this.deathView}); this.syncInput(); return true;
    }
    getPendingReturnToTown(): {opId:string;deathRevision:number} | null {
        const request=this.deathView.request; return request ? {opId:request.opId,deathRevision:request.deathRevision}:null;
    }
    confirmAliveSnapshot(): void {
        if(this.disposed||(!this.deathView.down&&!this.deathView.request))return; const wasDown=this.deathView.down;
        window.clearTimeout(this.returnTownTimer); this.deathView=confirmAliveView(this.deathView);
        this.domUi.update({death:this.deathView}); if(wasDown)this.neutralizeMovement(); this.syncInput();
    }
    /** True only for a changed valid public character UUID; runtime fences old socket replies first. */
    beginCharacterAuthority(characterId:string):boolean {
        if(this.disposed||! /^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$/.test(characterId))return false;
        const normalized=characterId.toLowerCase();if(normalized===this.characterAuthorityId)return false;
        this.characterAuthorityId=normalized;
        window.clearTimeout(this.returnTownTimer);for(const timer of this.transactionTimers.values())window.clearTimeout(timer);
        this.transactionTimers.clear();this.pendingItemMoves.clear();this.transactions=[];
        this.characterRevision=this.questRevision=this.partyRevision=0;this.characterState=null;this.partyState=null;this.playerDisplayName=null;
        this.itemInstances=[];this.instanceDataKnown=false;this.friendsList=[];this.groupState=null;
        this.pendingPotionOpId="";this.potions=0;
        this.patchHud({player:{...this.hudView.player,name:this.hooks.language==="th"?"กำลังโหลดตัวละคร…":"Loading traveler…",baseLevel:null,jobLevel:null,hp:0,hpMaximum:0,sp:null,spMaximum:null,expText:"—",jobExpText:"—",expRatio:0,jobExpRatio:0},party:{members:[],inviteText:null,preview:false},quests:{...this.hudView.quests,items:[],loadingText:this.hooks.language==="th"?"กำลังโหลดภารกิจ…":"Loading quests…"},potion:{...this.hudView.potion,pending:false,readyAtMs:0,cooldownDurationMs:0,count:0,unavailable:true}});
        this.deathView={...emptyDeathView(),online:this.online,canSubmit:!!this.hooks.onReturnToTown};
        const shop=this.resourceStates.shop;this.resourceStates={...createResourceStates(),shop};
        this.domUi.update({death:this.deathView,transactions:[],resources:this.resourceStates,community:null,communityPending:false});
        this.patchPanels({character:null,party:null,group:null,friends:[],journal:null,selectedInventoryInstanceId:''});
        this.syncInventoryView();this.releaseMovement();return true;
    }
    setReturnToTownResult(value: ReturnToTownResult): boolean {
        if(this.disposed)return false; const next=applyTownResult(this.deathView,value); if(next===this.deathView)return false;
        window.clearTimeout(this.returnTownTimer); this.deathView=next; this.domUi.update({death:next}); return true;
    }
    private requestReturnToTown(): void {
        if(this.disposed||!canReturnToTown(this.deathView)||!this.hooks.onReturnToTown)return;
        let id:string; try { id=this.deathView.request?.phase==="outcome-unknown" ? this.deathView.request.opId : createOperationId(); }
        catch { this.showToast(this.hooks.language==="th"?"สร้างคำขอไม่ได้ กรุณาลองใหม่":"Could not create the request. Try again."); return; }
        const next=startTownRequest(this.deathView,id); if(!next?.request)return;
        this.deathView=next; this.domUi.update({death:next});
        const request=next.request;
        try { if(!this.hooks.onReturnToTown(request.opId,request.deathRevision)) { this.setReturnToTownResult({opId:request.opId,deathRevision:request.deathRevision,state:"rejected",reason:"not_sent"}); return; } }
        catch { this.setReturnToTownResult({opId:request.opId,deathRevision:request.deathRevision,state:"outcome-unknown",reason:"transport_unknown"}); return; }
        window.clearTimeout(this.returnTownTimer);
        this.returnTownTimer=window.setTimeout(()=>this.setReturnToTownResult({opId:request.opId,deathRevision:request.deathRevision,state:"outcome-unknown",reason:"reply_timeout"}),12_000);
    }
    setPanelResource(key: ResourceKey, value: Pick<PanelResourceState,"status"> & Partial<PanelResourceState>): boolean {
        if(this.disposed||!RESOURCE_KEYS.includes(key))return false; const next=updateResource(this.resourceStates[key],value); if(!next)return false;
        this.resourceStates={...this.resourceStates,[key]:next}; this.domUi.update({resources:this.resourceStates}); return true;
    }
    setTransactionState(value: UiTransaction): boolean {
        if(this.disposed)return false; const next=nextTransactions(this.transactions,value); if(!next||next===this.transactions)return false;
        this.transactions=next; this.domUi.update({transactions:next});
        const row=next.find(row=>row.requestId===value.requestId);
        if(row?.phase==="submitting"&&!this.transactionTimers.has(row.requestId)) {
            const id=row.requestId,resource=row.resource;
            this.transactionTimers.set(id,window.setTimeout(()=>this.setTransactionState({resource,requestId:id,phase:"outcome-unknown",reason:this.hooks.language==="th"?"ยังไม่ได้รับผลยืนยัน ตรวจสถานะเซิร์ฟเวอร์":"No confirmed result. Check server state."}),12_000));
        } else if(row?.phase!=="submitting") {window.clearTimeout(this.transactionTimers.get(value.requestId));this.transactionTimers.delete(value.requestId);}
        if(row?.phase==="committed"||row?.phase==="rejected")this.pendingItemMoves.delete(value.requestId);
        return true;
    }
    getPendingItemMoves():ItemMoveIntent[] {return [...this.pendingItemMoves.values()].map(row=>({...row}));}
    private moveItemInstance(instanceId:string,expectedRevision:number,to:"bag"|"weapon"|"armor"):void {
        const row=this.itemInstances.find(row=>row.instanceId===instanceId);
        if(this.disposed||!this.online||this.deathView.down||this.recovering||this.worldLoading||!this.hooks.onMoveItemInstance||!row||expectedRevision!==this.characterRevision||this.transactions.some(tx=>(tx.resource==="inventory"||tx.resource==="character")&&(tx.phase==="submitting"||tx.phase==="outcome-unknown"))||!["loaded-data","loaded-empty"].includes(this.resourceStates.inventory.status))return;
        if(to===row.location||(row.location==="bag"?to!==row.equipSlot:to!=="bag"))return;
        let opId:string;try{opId=createOperationId();}catch{return;}
        if(this.pendingItemMoves.size>=16)return;
        const intent={opId,instanceId,expectedRevision,to};this.pendingItemMoves.set(opId,intent);
        if(!this.setTransactionState({resource:"inventory",requestId:opId,phase:"submitting",reason:null})){this.pendingItemMoves.delete(opId);return;}
        try{if(!this.hooks.onMoveItemInstance(opId,instanceId,expectedRevision,to))this.setTransactionState({resource:"inventory",requestId:opId,phase:"rejected",reason:this.hooks.language==="th"?"ไม่ได้ส่งรายการ กรุณาตรวจการเชื่อมต่อ":"Request was not sent. Check the connection."});}
        catch{this.setTransactionState({resource:"inventory",requestId:opId,phase:"outcome-unknown",reason:this.hooks.language==="th"?"ยังไม่ทราบผล ตรวจสถานะก่อนส่งซ้ำ":"Outcome unknown. Check server state before retrying."});}
    }
    getCombatReadability(): CombatReadability { return {...this.combatReadability}; }
    setCombatReadability(value: CombatReadability): void {
        if(this.disposed)return; this.combatReadability=normalizeReadability(value); this.domUi.update({readability:this.combatReadability});
        changeSettingsPreferences({...loadPrefs(),shake:this.combatReadability.screenShake??true});
        this.hooks.onCombatReadabilityChanged?.({...this.combatReadability});
        if(!saveCombatReadability(uiStorage(),this.combatReadability))this.showToast(this.hooks.language==="th"?"ใช้ค่าชั่วคราวได้ แต่บันทึกบนอุปกรณ์ไม่ได้":"Applied for this session; device storage is unavailable.");
    }
    private receivedResource(key: ResourceKey, hasEntries=true, requestId?:string): void {
        if(requestId!==undefined){this.setPanelResource(key,{status:hasEntries?"loaded-data":"loaded-empty",requestId});return;}
        // A validated current-socket push supersedes pending HTTP responses.
        this.resourceStates={...this.resourceStates,[key]:{status:hasEntries?"loaded-data":"loaded-empty",hasData:true,message:null,requestId:null}};
        this.domUi.update({resources:this.resourceStates});
    }
    private matchesResourceRequest(key:ResourceKey,requestId?:string):boolean {return requestId===undefined||requestId===this.resourceStates[key].requestId;}
    private refreshPanelResource(key: ResourceKey): void {
        if(key==="shop") {this.shopRequested=false;this.requestShopCatalog();return;}
        this.setPanelResource(key,{status:"loading"});
        let sent=false;try {sent=(key==="community"&&this.online ? this.hooks.onCommunity?.({kind:"sync",device:currentDevice()}) : this.hooks.onRefreshResource?.(key))===true;}catch{/* A failed setup is an error, not loaded-empty. */}
        if(!sent)this.setPanelResource(key,{status:"error",requestId:this.resourceStates[key].requestId,message:this.hooks.language==="th"?"ไม่ได้ส่งคำขอ กรุณาตรวจการเชื่อมต่อ":"Request was not sent. Check the connection."});
    }
    setWorldLoading(loading: boolean): void {
        if (loading === this.worldLoading) return;
        this.worldLoading = loading;
        if (loading) this.neutralizeMovement();
        this.patchHud({ loadingMessage: loading ? (this.hooks.language === "th" ? "กำลังเตรียมเมือง…" : "Preparing the town…") : null });
        this.syncInput();
    }
    private syncInput(): void { this.patchHud({ inputBlocked: this.inputBlocked() }); }
    private neutralizeMovement(): void { this.keys.clear(); this.touchX = 0; this.touchZ = 0; this.patchHud({ inputResetVersion: this.hudView.inputResetVersion + 1 }); }
    getMovement(): MovementInput {
        if (this.inputBlocked())
            return { x: 0, z: 0 };
        let x = Number(this.keys.has("KeyD") || this.keys.has("ArrowRight")) - Number(this.keys.has("KeyA") || this.keys.has("ArrowLeft")) + this.touchX;
        let z = Number(this.keys.has("KeyW") || this.keys.has("ArrowUp")) - Number(this.keys.has("KeyS") || this.keys.has("ArrowDown")) + this.touchZ;
        const length = Math.hypot(x, z);
        if (length > 1) {
            x /= length;
            z /= length;
        }
        return { x, z };
    }
    setRenderer(label: string): void { this.patchHud({ rendererLabel: label }); }
    setFps(fps: number): void { this.patchHud({ fps: Number.isFinite(fps) && fps > 0 ? Math.round(fps) : null }); }
    setNet(rttMs: number | null): void { this.patchHud({ pingMs: rttMs !== null && Number.isFinite(rttMs) && rttMs >= 0 ? Math.round(rttMs) : null }); }
    setActionCooldown(action: ActionKind, readyAtMs: number, durationMs: number): void {
        this.patchHud({ abilities: this.hudView.abilities.map(item => item.action === action ? { ...item, readyAtMs: Number.isFinite(readyAtMs) ? readyAtMs : 0, cooldownDurationMs: Math.max(0, durationMs) } : item) });
    }
    setConnection(online: boolean, message?: string): void {
        const wasOnline = this.online;
        this.online = online;
        if (online) this.connectionInterrupted=false;
        else if (wasOnline) this.connectionInterrupted=true;
        this.deathView={...this.deathView,online};
        if(!online&&this.deathView.request?.phase==="submitting")this.setReturnToTownResult({opId:this.deathView.request.opId,deathRevision:this.deathView.request.deathRevision,state:"outcome-unknown",reason:"connection_lost"});
        this.domUi.update({death:this.deathView});
        this.patchHud({ online, connectionLabel: online ? "LOCAL ROOM · ONLINE" : this.connectionInterrupted ? "CONNECTION INTERRUPTED" : "OFFLINE PREVIEW", connectionMessage: message ?? (online ? null : this.connectionInterrupted ? "Waiting to reconnect · showing last server data" : "Local preview · start the Rust room for multiplayer"), sessionNote: online ? (this.hooks.language === "th" ? "ความคืบหน้าชั่วคราวจะถูกล้างเมื่อเซิร์ฟเวอร์เริ่มใหม่" : "Session progress resets when the room restarts.") : null });
        if (!online) {
            this.neutralizeMovement();
            this.setNet(null);
        }
        if (online && !wasOnline) {
            this.characterRevision=this.questRevision=this.partyRevision=0;
            this.playerDisplayName=null;
            this.characterState=null; this.partyState=null; this.friendsList=[]; this.groupState=null; this.itemInstances=[];this.instanceDataKnown=false;
            this.resourceStates=createResourceStates();
            if(this.shopStatus==="ready")this.resourceStates.shop={status:this.shopCatalog.entries.length||this.shopCatalog.boxes.length?"loaded-data":"loaded-empty",hasData:true,message:null,requestId:null};
            this.domUi.update({resources:this.resourceStates,community:null});
            this.patchPanels({character:null,party:null,friends:[],group:null,journal:null});
            this.potions = 0;
            this.patchHud({ player: { ...this.hudView.player, name: this.hooks.language === "th" ? "กำลังโหลดตัวละคร…" : "Loading traveler…", levelText: "—", baseLevel: null, jobLevel: null, hp: 0, hpMaximum: 0, sp: null, spMaximum: null, expText: "—", expRatio: 0, jobExpText: "—", jobExpRatio: 0, footerExp: "—" }, party: { members: [], inviteText: null, preview: false }, quests: { ...this.hudView.quests, items: [], loadingText: this.hooks.language === "th" ? "กำลังโหลดข้อมูลภารกิจ…" : "Loading server quest state…" } });
        }
        if (!online && wasOnline) {
            for(const key of RESOURCE_KEYS)if(key!=="shop")this.resourceStates[key]={...this.resourceStates[key],status:"stale",message:null};
            this.transactions=this.transactions.map(row=>row.phase==="submitting"?{...row,phase:"outcome-unknown",reason:"Connection changed; check server state."}:row);
            this.domUi.update({resources:this.resourceStates,transactions:this.transactions,communityPending:false});
            setChatGroupAvailable(false);
        }
        this.patchHud({ minimap: { ...this.hudView.minimap, showPreviewParty: !online&&!this.connectionInterrupted } });
        this.domUi.update({ online });
        this.patchPanels({ online });
        this.syncInput();
        this.syncInventoryView();
        this.syncPotion();
        this.syncShopView();
    }
    setCharacterState(state: CharacterStateMessage): boolean {
        if (!isCharacterState(state))return false;
        const authority=(state as unknown as {character_id?:unknown}).character_id;
        if(authority!==undefined&&(typeof authority!=="string"||! /^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$/.test(authority)))return false;
        const instances=parseItemInstances((state as unknown as {item_instances?:unknown}).item_instances,this.hooks.itemName,this.hooks.itemEquipmentSlot);
        if(!instances){this.setPanelResource("inventory",{status:"error",message:this.hooks.language==="th"?"ข้อมูลอุปกรณ์ไม่ถูกต้อง รอข้อมูลใหม่":"Equipment data is invalid. Refresh server state."});return false;}
        if(typeof authority==="string")this.beginCharacterAuthority(authority);
        const decision=characterSnapshotDecision(this.characterState,state);
        if(decision==='stale'||decision==='conflict'||decision==='invalid')return false;
        if(decision==='duplicate'){
            this.receivedResource("character");this.receivedResource("inventory",state.bag.length>0||instances.length>0||Object.values(state.pouch).some(count=>count>0));
            return true;
        }
        this.itemInstances=instances;
        this.instanceDataKnown=(state as unknown as {item_instances?:unknown}).item_instances!==undefined;
        this.characterRevision = state.rev;
        this.characterState = state;
        this.receivedResource("character");
        this.receivedResource("inventory",state.bag.length>0||instances.length>0||Object.values(state.pouch).some(count=>count>0));
        this.potions = state.bag.find(item => item.item === "trail_potion")?.count ?? 0;
        const baseNext = Math.max(1, state.base_exp_next ?? 0), jobNext = Math.max(1, state.job_exp_next ?? 0), th = this.hooks.language === "th";
        this.patchHud({ player: { name: this.playerDisplayName ?? state.name ?? "Traveler", levelText: `Lv. ${String(state.level).padStart(2, "0")}`, baseLevel: state.level, jobLevel: state.job_level, hp: state.hp, hpMaximum: state.max_hp, sp: state.sp ?? null, spMaximum: state.max_sp ?? null, expText: `${state.exp} / ${baseNext}`, expRatio: Math.min(1, state.exp / baseNext), jobExpText: `${state.job_exp} / ${jobNext}`, jobExpRatio: Math.min(1, state.job_exp / jobNext), footerLevel: th ? `เลเวลพื้นฐาน ${state.level}` : `Base Lv. ${String(state.level).padStart(2, "0")}`, footerJob: th ? `อาชีพ ${state.job_level}` : `Job Lv. ${String(state.job_level).padStart(2, "0")}`, footerExp: `${state.exp} / ${baseNext}` } });
        const character=characterPanelData(state, this.hooks.itemName, !!this.hooks.onRefineItem);
        if(character&&this.instanceDataKnown)character.equipment=character.equipment.map(row=>({...row,canRefine:row.canRefine&&instances.some(instance=>instance.location===row.slot)}));
        this.patchPanels({ character });
        this.syncPotion();
        this.syncInventoryView();
        return true;
    }
    setQuestState(state: QuestStateMessage): boolean {
        if (!isQuestState(state) || state.rev <= this.questRevision)
            return false;
        this.questRevision = state.rev;
        this.receivedResource("journal",state.state!=="not_started");
        const th = this.hooks.language === "th", windmarks = state.objectives.windmark ?? 0, hunt = state.objectives.hunt ?? 0;
        const quest = { id: state.quest, title: state.state === "not_started" ? (th ? "ยังไม่มีภารกิจที่รับไว้" : "No accepted quest") : this.hooks.questName(state.quest), description: state.state === "not_started" ? (th ? "รับภารกิจเพื่อเริ่มการเดินทาง" : "Accept a quest to start a route.") : state.state === "ready_to_claim" ? (th ? "กลับไปหาเซลล่าเพื่อรับรางวัล" : "Return to Sella to claim your reward.") : state.state === "completed" ? (th ? "ภารกิจสำเร็จแล้ว" : "Route complete.") : (th ? `ปลุกเครื่องหมายลม ${windmarks}/3 · กำจัดพุดเดิลคิน ${hunt}/3` : `Awaken windmarks ${windmarks}/3 · Defeat Puddlekin ${hunt}/3`), progress: state.state === "ready_to_claim" ? (th ? "พร้อมรับ" : "Ready") : state.state === "completed" ? (th ? "สำเร็จ" : "Done") : state.state === "not_started" ? "—" : (th ? "กำลังทำ" : "Active"), progressId: null };
        this.patchHud({ quests: { ...this.hudView.quests, loadingText: null, items: [quest] } });
        this.patchPanels({ journal: journalPanelData(state, this.hooks.questName) });
        return true;
    }
    setContextAction(action: ContextAction | null): void { this.contextAction = action; this.patchHud({ contextLabel: action?.label ?? null }); }
    setPartyState(state: PartyStateMessage): boolean {
        if (!isPartyState(state) || (state.members.length > 0 && this.partyState && state.rev <= this.partyRevision))
            return false;
        this.partyRevision = state.members.length > 0 ? state.rev : 0;
        this.partyState = state.members.length > 0 ? state : null;
        this.receivedResource("party",state.members.length>0);
        const th = this.hooks.language === "th";
        this.patchHud({ party: { preview: false, members: state.members.map(member => ({ id: member.id, name: member.name, role: member.id === state.leader ? (th ? "หัวหน้ากลุ่ม" : "Leader") : (th ? "สมาชิก" : "Member"), face: "blue", hpRatio: null, level: null })), inviteText: state.code ? `${th ? "รหัสเชิญ" : "Invite"} ${state.code} · ${state.expires_s}s` : null } });
        this.patchPanels({ party: partyPanelData(this.partyState) });
        return true;
    }
    setWalletState(state: EconomyWalletState): void {
        this.walletState = { gold: finiteAmount(state.gold), coin: finiteAmount(state.coin), ownedCosmetics: Array.isArray(state.ownedCosmetics) ? state.ownedCosmetics.filter(id => typeof id === "string" && id.length > 0).slice(0, 128) : [], skin: typeof state.skin === "string" && state.skin ? state.skin : null, pet: typeof state.pet === "string" && state.pet ? state.pet : null, bagCounts: typeof state.bagCounts === "object" && state.bagCounts !== null ? sanitizeBagCounts(state.bagCounts) : {} };
        this.syncShopView();
        this.receivedResource("wallet");
    }
    setTowerState(state: TowerState,requestId?:string): void {
        if(!this.matchesResourceRequest("tower",requestId))return;
        this.towerState = sanitizeTowerState(state);
        this.patchPanels({ tower: this.towerState });
        this.patchHud({ minimap: { ...this.hudView.minimap, mainMap: !this.towerState.inTower } });
        this.syncMapPanel(); this.receivedResource("tower",true,requestId);
    }
    setTowerPayload(body: unknown,requestId?:string): void { const parsed = parseTowerState(body); if (parsed)
        this.setTowerState(parsed,requestId); }
    setChannelState(state: ChannelState,requestId?:string): void { if(!this.matchesResourceRequest("rooms",requestId))return;this.channelState = { rooms: Array.isArray(state.rooms) ? state.rooms.filter(isRoomRow) : null, current: isChannelId(state.current) ? state.current : null }; this.patchPanels({ rooms: roomPanelData(this.channelState) }); if(this.channelState.rooms!==null)this.receivedResource("rooms",this.channelState.rooms.length>0,requestId); }
    setFriends(entries: FriendEntry[],requestId?:string): void { if(!this.matchesResourceRequest("friends",requestId))return;this.friendsList = parseFriendEntries(entries); this.patchPanels({ friends: presencePanelData(this.friendsList) }); this.receivedResource("friends",this.friendsList.length>0,requestId); }
    setFriendsPayload(body: unknown,requestId?:string): void { const parsed = parseFriendsBody(body); if (parsed)
        this.setFriends(parsed,requestId); }
    setGroup(group: GroupInfo | null,requestId?:string): void { if(!this.matchesResourceRequest("group",requestId))return;const info = group ? parseGroupInfo(group) : null; this.groupState = info !== null && (info.code !== "" || info.members.length > 0) ? info : null; setChatGroupAvailable(this.groupState !== null); this.patchPanels({ group: groupPanelData(this.groupState) }); this.syncMapPanel(); this.receivedResource("group",this.groupState!==null,requestId); }
    setGroupPayload(body: unknown,requestId?:string): void { const parsed = parseGroupBody(body); if (parsed)
        this.setGroup(parsed.group,requestId); }
    playerName(name: string): void { const clean = sanitizeDisplayName(name); if (!clean)
        return; this.playerDisplayName = clean; this.patchHud({ player: { ...this.hudView.player, name: clean } }); }
    setMapData(points: Record<string, {
        x: number;
        z: number;
    }>, extent: number, routes: WorldRouteDefinition[] = []): void {
        this.mapPoints = Object.fromEntries(Object.entries(points).slice(0, 80));
        this.mapExtent = Math.max(1, extent);
        this.mapRoutes = routes.slice(0, 64);
        this.patchHud({ minimap: { ...this.hudView.minimap, extent: this.mapExtent, points: Object.entries(this.mapPoints).map(([id, p]) => ({ id, x: p.x, z: p.z })), routes: this.mapRoutes.map(route => ({ id: route.id, points: route.points.slice(0, 80) })) } });
        this.syncMapPanel();
    }
    setPosition(x: number, z: number): void {
        this.mapX = x;
        this.mapZ = z;
        const now = performance.now();
        if (now - this.lastPositionUpdate < 100)
            return;
        this.lastPositionUpdate = now;
        this.patchHud({ minimap: { ...this.hudView.minimap, playerX: x, playerZ: z } });
        if (this.activeModal === "map")
            this.syncMapPanel();
    }
    private syncMapPanel(): void { this.patchPanels({ map: mapPanelData(this.mapPoints, this.mapExtent, this.mapRoutes, { x: this.mapX, z: this.mapZ }, this.groupState?.members ?? [], this.towerState, this.hooks.language) }); }
    showDialogue(message: DialogueMessage, text: string, quest: string): void { this.patchPanels({ dialogue: dialoguePanelData(message, text, quest, this.hooks.translate, this.hooks.language) }); this.openModal("dialogue"); }
    closeDialogue(): void { this.closeModal(); }
    showGameNotice(key: string, params: Record<string, number> = {}): void {
        const th = this.hooks.language === "th";
        // Tower slice: floor spawns and the floor-100 completion arrive as cold
        // notices; main.ts forwards the key (params arrive once the integrator
        // wires them through).
        if (key === "tower_floor") {
            const floor = Number.isSafeInteger(params.floor) ? params.floor : null;
            const text = floor === null
                ? (th ? "กำลังขึ้นชั้นถัดไปของหอคอย…" : "Climbing to the next tower floor…")
                : (th ? `หอคอย · ชั้น ${floor}` : `Tower · floor ${floor}`);
            onSystemLine(text);
            this.showToast(text);
            return;
        }
        if (key === "tower_complete") {
            const text = th
                ? "หอคอยสำเร็จ — ขึ้นครบ 100 ชั้น! กำลังกลับสู่ฟรอนเทียร์"
                : "Tower complete — all 100 floors cleared! Returning to the frontier.";
            onSystemLine(text);
            this.showToast(text);
            return;
        }
        const messages: Record<string, [
            string,
            string
        ]> = {
            windmark_channel_started: ["Awakening the windmark…", "กำลังปลุกเครื่องหมายลม…"],
            windmark_activated: ["Windmark awakened", "ปลุกเครื่องหมายลมแล้ว"],
            windmark_channel_interrupted: ["The channel was interrupted by movement", "การปลุกถูกขัดจังหวะเพราะเคลื่อนที่"],
            windmark_out_of_range: ["Move within 2 m of the windmark", "เข้าใกล้เครื่องหมายลมในระยะ 2 เมตร"],
            windmark_already_activated: ["This windmark is already awake", "ปลุกเครื่องหมายนี้แล้ว"],
            windmark_wrong_order: ["Follow the marked route in order", "ทำตามเครื่องหมายบนแผนที่ตามลำดับ"],
            interaction_out_of_range: ["Move closer to Sella", "เข้าใกล้เซลล่าอีกหน่อย"],
            choice_stale_choice: ["That conversation expired. Speak to Sella again.", "บทสนทนาหมดเวลา คุยกับเซลล่าอีกครั้ง"],
            party_already_in_party: ["Leave your current party first", "ออกจากกลุ่มปัจจุบันก่อน"],
            party_full: ["This party is full", "กลุ่มนี้เต็มแล้ว"],
            party_expired: ["That invite code expired", "รหัสเชิญหมดอายุแล้ว"],
        };
        const copy = messages[key];
        const text = copy ? copy[th ? 1 : 0] : key.replaceAll("_", " ");
        onSystemLine(text);
        this.showToast(text);
    }
    setPotionResult(opId: string, status: string, reason: string, readyAtMs: number): void {
        if (!this.hudView.potion.pending || this.pendingPotionOpId !== opId)
            return;
        this.pendingPotionOpId = "";
        const deadline = Number.isFinite(readyAtMs) ? Math.max(0, readyAtMs) : 0;
        this.patchHud({ potion: { ...this.hudView.potion, pending: false, ...(status === "accepted" || reason === "cooldown" ? { readyAtMs: deadline, cooldownDurationMs: Math.max(0, deadline - performance.now()) } : {}) } });
        this.syncInventoryView();
        const th = this.hooks.language === "th";
        this.showToast(status === "accepted" ? (th ? "ใช้ยาแล้ว" : "Potion used") : reason === "cooldown" ? (th ? "ยากำลังพักฟื้น" : "Potion is recharging") : reason === "hp_full" ? (th ? "พลังชีวิตเต็มแล้ว" : "Health is already full") : (th ? "ใช้ไอเท็มไม่ได้" : "Item use was rejected"));
    }
    setHp(current: number, maximum: number): void { this.patchHud({ player: { ...this.hudView.player, hp: current, hpMaximum: maximum } }); if(this.panelsView.character)this.patchPanels({character:{...this.panelsView.character,hp:current,maxHp:maximum}}); this.syncPotion(); }
    addXp(amount: number): void { if (this.online)
        return; this.xp = Math.min(100, this.xp + amount); this.patchHud({ player: { ...this.hudView.player, expRatio: this.xp / 100, expText: `${this.xp}%`, footerExp: `${this.xp}%` } }); if (this.xp >= 100) {
        this.xp = 0;
        this.patchHud({ player: { ...this.hudView.player, levelText: "Lv. 02", baseLevel: 2, footerLevel: this.hooks.language === "th" ? "เลเวลพื้นฐาน 2" : "Base Lv. 02" } });
        this.showToast("Base level increased · Lv. 02");
    } }
    recordDefeat(enemyName: string, exp: number): void { if (this.online)
        return; this.slimeKills = Math.min(3, this.slimeKills + 1); this.clover = Math.min(5, this.clover + 1); this.patchHud({ quests: { ...this.hudView.quests, items: this.hudView.quests.items.map(item => item.id === "slimes" ? { ...item, progress: `${this.slimeKills} / 3` } : item.id === "clover" ? { ...item, progress: `${this.clover} / 5` } : item) } }); this.addXp(exp); this.showToast(`${enemyName} defeated · +${exp} EXP`); this.addChat("Obtained Clover Gel × 1", "system"); }
    showToast(message: string): void { const now = performance.now(); this.patchHud({ toasts: [...this.hudView.toasts.filter(item => item.expiresAtMs > now), { id: ++this.toastSequence, message: message.slice(0, 1000), expiresAtMs: now + 3200 }].slice(-8) }); }
    addChat(message: string, kind: "world" | "party" | "system" = "world"): void { appendLocalChat(message, kind === "world" ? "room" : kind === "party" ? "group" : "system", this.playerDisplayName ?? "Eira"); }
    flashHurtScreen(): void { if (loadPrefs().flash && !window.matchMedia("(prefers-reduced-motion: reduce)").matches)
        window.dispatchEvent(new Event("xexoria:hurt")); }
    private usePotion(): void {
        if (this.online) {
            if (this.hudView.potion.pending || performance.now() < this.hudView.potion.readyAtMs || this.hudView.potion.unavailable || this.potions <= 0)
                return;
            const id = createOperationId();
            if (this.hooks.onPotion(id)) {
                this.pendingPotionOpId = id;
                this.patchHud({ potion: { ...this.hudView.potion, pending: true } });
                this.syncInventoryView();
            }
            return;
        }
        if (this.potions <= 0)
            return;
        this.potions--;
        this.hooks.onPotion(null);
        this.syncPotion();
        this.showToast(`Potion used · ${this.potions} remaining`);
    }
    private syncPotion(): void { this.patchHud({ potion: { ...this.hudView.potion, count: this.potions, unavailable: this.online && (!this.characterState || this.hudView.player.hp >= this.hudView.player.hpMaximum) } }); this.syncInventoryView(); }
    setCommunityPayload(value:unknown):void { const state=parseCommunity(value); if(state) {this.domUi.update({community:state,communityPending:false});this.receivedResource("community");} }
    communityResult(reason:string):void { this.domUi.update({communityPending:false}); const copy=COMMUNITY_COPY[reason]; if(reason!=="accepted") this.showToast(copy?.[this.hooks.language==="th"?1:0] ?? (this.hooks.language==="th"?"รายการไม่สำเร็จ: ":"Request rejected: ")+reason); }
    private openModal(name: string): void {
        this.neutralizeMovement();
        this.activeModal = name;
        this.syncInput();
        const th = this.hooks.language === "th";
        const titles: Record<string, [
            string,
            string
        ]> = { bag: ["Field Bag", "กระเป๋า"], menu: ["Adventure Menu", "เมนูผจญภัย"], character: ["Character", "ตัวละคร"], skills: ["Skills", "สกิล"], party: ["Party", "ปาร์ตี้"], collection: ["Field Journal", "บันทึกภารกิจ"], store: ["Store", "ร้านค้า"], settings: ["Settings", "ตั้งค่า"], tower: ["Tower", "หอคอย"], friends: ["Friends", "เพื่อน"], group: ["Group", "กลุ่ม"], map: ["World Map", "แผนที่โลก"], trade: ["Trade & players", "แลกเปลี่ยน / ผู้เล่น"], battlepass:["Battle Pass","แบตเทิลพาส"], topup:["Test Top-up","เติมเงินทดสอบ"] };
        if (["trade","battlepass","topup"].includes(name) && this.online) this.hooks.onCommunity?.({kind:"sync",device:currentDevice()});
        if (name === "settings")
            this.patchPanels({ settings: settingsPanelData(this.hooks.language) });
        if (name === "map")
            this.syncMapPanel();
        this.domUi.openModal(name, titles[name]?.[th ? 1 : 0] ?? "Xexoria");
        if (name === "bag")
            this.syncInventoryView();
        if (name === "store") {
            this.syncShopView();
            this.requestShopCatalog();
        }
    }
    private closeModal(): void { this.activeModal = null; this.domUi?.closeModal(); this.neutralizeMovement(); this.syncInput(); }
    private async toggleFullscreen(): Promise<void> { try {
        if (document.fullscreenElement)
            await document.exitFullscreen();
        else
            await document.getElementById("game")?.requestFullscreen();
    }
    catch {
        this.showToast(this.hooks.language === "th" ? "เบราว์เซอร์นี้ไม่รองรับเต็มจอ" : "Fullscreen is unavailable in this browser");
    } }
    private onKeyDown(event: KeyboardEvent): void {
        if (event.repeat)
            return;
        if (this.activeModal !== null) {
            if (event.key === "Escape")
                this.closeModal();
            return;
        }
        const target = event.target;
        if (this.deathView.down || this.chatExpanded || this.recovering || this.worldLoading)
            return;
        if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || (target instanceof HTMLElement && target.closest('button,[contenteditable="true"],[role="tab"]')))
            return;
        const code = normalizeKey(event);
        this.keys.add(code);
        const action = actionByCode(code);
        if (action) {
            if (code === "Space")
                event.preventDefault();
            this.hooks.onAction(action);
        }
        else if (code === "KeyE") {
            if (this.contextAction)
                this.hooks.onContext(this.contextAction);
        }
        else {
            const menus: Record<string, string> = { KeyB: "bag", KeyM: "map", KeyJ: "friends", KeyP: "group", KeyC: "character", KeyK: "skills" };
            if (menus[code])
                this.openModal(menus[code]);
            else if (code === "Escape")
                this.openModal("menu");
        }
    }
    private syncInventoryView(): void {
        const entries = this.characterState?.bag ?? (this.online ? [] : [{ slot: 0, item: "offline_clover_gel", count: 2 }, { slot: 1, item: "trail_potion", count: this.potions }, { slot: 2, item: "offline_copper_leaf", count: 1 }]);
        const seen = new Set<number>();
        const items: InventorySnapshot["items"] = entries.slice(0, 12).filter(entry => { if (seen.has(entry.slot))
            return false; seen.add(entry.slot); return true; }).map(entry => ({ slot: entry.slot, id: entry.item, label: this.hooks.itemName(entry.item).slice(0, 200), count: finiteAmount(entry.count), action: !this.online ? null : this.hooks.equippable?.(entry.item) ? this.itemInstances.some(row=>row.id===entry.item)?null:"equip" : this.hooks.isConsumable?.(entry.item) ? "use" : this.hooks.isBox?.(entry.item) ? "open" : null, isPotion: entry.item === "trail_potion" }));
        this.domUi?.update({ inventory: { language: this.hooks.language, online: this.online, loading: this.online && this.characterState === null, revision:this.characterState?.rev??null,instances:this.itemInstances,instanceMovesSupported:!!this.hooks.onMoveItemInstance,items, pouch: this.characterState ? Object.entries(this.characterState.pouch).slice(0, 64).map(([id, count]) => ({ id, label: this.hooks.itemName(id).slice(0, 200), count: finiteAmount(count) })) : [], potionPending: this.hudView.potion.pending, potionReadyAtMs: this.hudView.potion.readyAtMs, potionUnavailable: this.hudView.potion.unavailable } });
    }
    private syncShopView(): void { this.domUi?.update({ shop: { language: this.hooks.language, online: this.online, status: this.shopStatus, catalog: this.shopCatalog, wallet: { ...this.walletState, ownedCosmetics: [...new Set(this.walletState.ownedCosmetics)].slice(0, 128), bagCounts: Object.fromEntries(Object.entries(this.walletState.bagCounts).slice(0, 128)) } } }); }
    private requestShopCatalog(): void { if (this.shopRequested)
        return; this.shopRequested = true; const generation=++this.shopGeneration; this.setPanelResource("shop",{status:"loading"}); void loadShopCatalog(this.hooks.language).then(catalog => { if (this.disposed||generation!==this.shopGeneration)
        return; this.shopCatalog = catalog ?? { entries: [], boxes: [] }; this.shopStatus = catalog ? "ready" : "unavailable"; this.syncShopView(); if(catalog)this.receivedResource("shop",catalog.entries.length+catalog.boxes.length>0);else this.setPanelResource("shop",{status:"error",hasData:false,message:this.hooks.language==="th"?"โหลดร้านค้าไม่สำเร็จ":"Store content could not be loaded."}); }); }
    dispose(): void { if (this.disposed)
        return; window.clearTimeout(this.returnTownTimer); for(const timer of this.transactionTimers.values())window.clearTimeout(timer);this.transactionTimers.clear();this.pendingItemMoves.clear();this.neutralizeMovement(); this.disposed = true; this.uiEvents.abort(); this.domUi.unmount(); releaseChat(this); }
}
function normalizeKey(event: KeyboardEvent): string {
    const key = event.key.toLowerCase();
    const letter = key.length === 1 && key >= "a" && key <= "z" ? `Key${key.toUpperCase()}` : null;
    if (letter)
        return letter;
    if (key === " ")
        return "Space";
    const digit = key.length === 1 && key >= "0" && key <= "9" ? `Digit${key}` : null;
    return event.code || digit || event.key;
}
function uiStorage(): Storage | null { try { return window.localStorage; } catch { return null; } }
function finiteAmount(value: number): number {
    return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}
function sanitizeBagCounts(value: Record<string, number>): Record<string, number> {
    const out: Record<string, number> = {};
    for (const [id, count] of Object.entries(value)) {
        if (typeof count === "number" && Number.isFinite(count) && count > 0)
            out[id] = Math.floor(count);
    }
    return out;
}
function isPartyState(value: unknown): value is PartyStateMessage {
    if (typeof value !== "object" || value === null)
        return false;
    const state = value as Partial<PartyStateMessage>;
    return state.t === "party_state"
        && Number.isSafeInteger(state.rev) && (state.rev ?? -1) >= 0
        && Number.isSafeInteger(state.leader) && (state.leader ?? -1) >= 0
        && typeof state.code === "string" && (state.code.length === 0 || /^[A-Z0-9]{6}$/.test(state.code))
        && Number.isSafeInteger(state.expires_s) && (state.expires_s ?? -1) >= 0 && (state.expires_s ?? 0) <= 600
        && Array.isArray(state.members) && state.members.length <= 4
        && state.members.every((member) => Number.isSafeInteger(member.id) && member.id > 0
            && typeof member.name === "string" && member.name.length > 0 && member.name.length <= 48);
}
function createOperationId(): string {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function isCharacterState(value: unknown): value is CharacterStateMessage {
    if (typeof value !== "object" || value === null)
        return false;
    const state = value as Partial<CharacterStateMessage>;
    return state.t === "character_state"
        && Number.isSafeInteger(state.rev) && (state.rev ?? 0) > 0
        && Number.isSafeInteger(state.level) && (state.level ?? 0) > 0
        && Number.isSafeInteger(state.exp) && (state.exp ?? -1) >= 0
        && Number.isSafeInteger(state.max_hp) && (state.max_hp ?? 0) > 0
        && Number.isSafeInteger(state.hp) && (state.hp ?? -1) >= 0 && (state.hp ?? 0) <= (state.max_hp ?? 0)
        && Array.isArray(state.bag) && state.bag.length <= 12
        && state.bag.every((entry) => Number.isSafeInteger(entry.slot) && entry.slot >= 0 && entry.slot < 12
            && Number.isSafeInteger(entry.count) && entry.count > 0
            && typeof entry.item === "string" && /^[a-zA-Z0-9_]{1,64}$/.test(entry.item))
        && typeof state.pouch === "object" && state.pouch !== null
        && Object.values(state.pouch).every((count) => Number.isSafeInteger(count) && count >= 0);
}
function isQuestState(value: unknown): value is QuestStateMessage {
    if (typeof value !== "object" || value === null)
        return false;
    const state = value as Partial<QuestStateMessage>;
    return state.t === "quest_state"
        && Number.isSafeInteger(state.rev) && (state.rev ?? 0) > 0
        && typeof state.quest === "string" && /^[a-zA-Z0-9_]{1,64}$/.test(state.quest)
        && typeof state.state === "string" && ["not_started", "active", "ready_to_claim", "completed"].includes(state.state)
        && typeof state.objectives === "object" && state.objectives !== null
        && Object.values(state.objectives).every((count) => Number.isSafeInteger(count) && count >= 0)
        && typeof state.step_ticks === "object" && state.step_ticks !== null
        && Object.values(state.step_ticks).every((tick) => Number.isSafeInteger(tick) && tick >= 0);
}
