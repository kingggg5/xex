//! Per-piece gear identity. Aggregate stack counts are a compatibility projection.
use serde::{Deserialize,Serialize};
use sha2::{Digest,Sha256};
use std::collections::BTreeMap;
pub const MAX_INSTANCES:usize=14; // Twelve bag pieces plus two equipped pieces.

#[derive(Debug,Clone,PartialEq,Eq,Serialize,Deserialize)]
pub struct ItemInstance {
    pub instance_id:String,
    pub def:String,
    pub location:String,
    pub refine:u8,
}

fn legacy_id(namespace:&str,def:&str,ordinal:usize)->String {
    let mut hash=Sha256::new();hash.update(b"xexoria-legacy-gear-v1\0");hash.update(namespace.as_bytes());hash.update([0]);hash.update(def.as_bytes());hash.update((ordinal as u64).to_le_bytes());
    let digest=hash.finalize();let mut bytes=[0u8;16];bytes.copy_from_slice(&digest[..16]);bytes[6]=(bytes[6]&15)|0x80;bytes[8]=(bytes[8]&63)|0x80;
    uuid::Uuid::from_bytes(bytes).to_string()
}

pub fn reconcile(namespace:&str,version:&mut u8,instances:&mut BTreeMap<String,ItemInstance>,bag:&BTreeMap<String,u8>,equipment:&BTreeMap<String,String>,refine:&BTreeMap<String,u8>,slots:&BTreeMap<String,String>)->Result<(),&'static str> {
    let expected=slots.keys().map(|def|usize::from(bag.get(def).copied().unwrap_or(0))+equipment.values().filter(|d|*d==def).count()).sum::<usize>();
    if expected>MAX_INSTANCES {return Err("instance_limit");}
    if *version>1 || expected>0 && namespace.is_empty() || equipment.iter().any(|(slot,def)|slots.get(def)!=Some(slot)) {return Err("invalid_inventory_state");}
    let mut next=instances.clone();
    for (id,i) in &next {
        if id!=&i.instance_id || uuid::Uuid::parse_str(id).is_err() || !slots.contains_key(&i.def) || i.refine>10 || !matches!(i.location.as_str(),"bag"|"weapon"|"armor") {return Err("invalid_inventory_state");}
    }
    for (def,slot) in slots {
        let total=usize::from(bag.get(def).copied().unwrap_or(0))+equipment.values().filter(|d|*d==def).count();
        let mut ids=next.iter().filter(|(_,i)|&i.def==def).map(|(id,_)|id.clone()).collect::<Vec<_>>();
        if ids.len()>total {return Err("invalid_inventory_state");}
        for ordinal in ids.len()..total {
            let id=if *version==0 {legacy_id(namespace,def,ordinal)} else {uuid::Uuid::new_v4().to_string()};
            if next.contains_key(&id) {return Err("invalid_inventory_state");}
            next.insert(id.clone(),ItemInstance {instance_id:id.clone(),def:def.clone(),location:"bag".into(),refine:0});ids.push(id);
        }
        let equipped=equipment.get(slot)==Some(def);
        let existing=ids.iter().find(|id|next[*id].location==*slot).cloned();
        if *version==0 && equipped && existing.is_none() {
            let id=ids.first().ok_or("invalid_inventory_state")?;
            let i=next.get_mut(id).unwrap();i.location=slot.clone();i.refine=refine.get(slot).copied().unwrap_or(0).min(10);
        }
        let equipped_count=ids.iter().filter(|id|next[*id].location==*slot).count();
        if equipped_count!=usize::from(equipped) || ids.iter().filter(|id|next[*id].location=="bag").count()!=usize::from(bag.get(def).copied().unwrap_or(0)) {return Err("invalid_inventory_state");}
        if equipped && ids.iter().find(|id|next[*id].location==*slot).is_some_and(|id|next[id].refine!=refine.get(slot).copied().unwrap_or(0)) {return Err("invalid_inventory_state");}
    }
    *instances=next;*version=1;Ok(())
}

pub fn move_piece(instances:&mut BTreeMap<String,ItemInstance>,bag:&mut BTreeMap<String,u8>,equipment:&mut BTreeMap<String,String>,refine:&mut BTreeMap<String,u8>,slots:&BTreeMap<String,String>,id:&str,to:&str)->Result<(),&'static str> {
    if !matches!(to,"bag"|"weapon"|"armor") {return Err("invalid_destination");}
    let item=instances.get(id).cloned().ok_or("not_owned")?;
    if to!="bag" && slots.get(&item.def).map(String::as_str)!=Some(to) {return Err("wrong_slot");}
    let mut next=instances.clone();
    if to!="bag" {for i in next.values_mut().filter(|i|i.location==to) {i.location="bag".into();}}
    next.get_mut(id).unwrap().location=to.into();
    let mut new_bag=bag.clone();let mut new_equipment=BTreeMap::new();let mut new_refine=BTreeMap::new();
    for def in slots.keys() {new_bag.remove(def);}
    for i in next.values() {
        if i.location=="bag" {*new_bag.entry(i.def.clone()).or_insert(0)+=1;} else {
            if new_equipment.insert(i.location.clone(),i.def.clone()).is_some() {return Err("invalid_inventory_state");}
            new_refine.insert(i.location.clone(),i.refine);
        }
    }
    if new_bag.values().filter(|n|**n>0).count()>12 {return Err("inventory_full");}
    *instances=next;*bag=new_bag;*equipment=new_equipment;*refine=new_refine;Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn migration_is_stable_and_mints_one_id_per_piece() {
        let slots=BTreeMap::from([("blade".into(),"weapon".into())]);let bag=BTreeMap::from([("blade".into(),2)]);let equip=BTreeMap::new();let mut a=BTreeMap::new();let mut b=BTreeMap::new();let mut av=0;let mut bv=0;
        reconcile("full-owner",&mut av,&mut a,&bag,&equip,&BTreeMap::new(),&slots).unwrap();reconcile("full-owner",&mut bv,&mut b,&bag,&equip,&BTreeMap::new(),&slots).unwrap();assert_eq!(a,b);assert_eq!(a.len(),2);
        reconcile("full-owner",&mut av,&mut a,&bag,&equip,&BTreeMap::new(),&slots).unwrap();assert_eq!(a,b);
    }
    #[test]
    fn move_swap_preserves_piece_refinement_and_is_atomic() {
        let slots=BTreeMap::from([("a".into(),"weapon".into()),("b".into(),"weapon".into())]);let mut bag=BTreeMap::from([("a".into(),1), ("b".into(),1)]);let mut equip=BTreeMap::new();let mut refine=BTreeMap::new();let mut instances=BTreeMap::new();let mut version=0;
        reconcile("owner",&mut version,&mut instances,&bag,&equip,&refine,&slots).unwrap();let a=instances.values().find(|i|i.def=="a").unwrap().instance_id.clone();let b=instances.values().find(|i|i.def=="b").unwrap().instance_id.clone();instances.get_mut(&a).unwrap().refine=4;
        move_piece(&mut instances,&mut bag,&mut equip,&mut refine,&slots,&a,"weapon").unwrap();move_piece(&mut instances,&mut bag,&mut equip,&mut refine,&slots,&b,"weapon").unwrap();assert_eq!(instances[&a].refine,4);assert_eq!(instances[&a].location,"bag");assert_eq!(refine["weapon"],0);
        let before=instances.clone();assert_eq!(move_piece(&mut instances,&mut bag,&mut equip,&mut refine,&slots,&a,"armor"),Err("wrong_slot"));assert_eq!(before,instances);
    }
    #[test]
    fn oversized_legacy_inventory_is_preserved_without_partial_migration() {
        let slots=BTreeMap::from([("blade".into(),"weapon".into())]);let bag=BTreeMap::from([("blade".into(),15)]);let mut instances=BTreeMap::new();let mut version=0;
        assert_eq!(reconcile("owner",&mut version,&mut instances,&bag,&BTreeMap::new(),&BTreeMap::new(),&slots),Err("instance_limit"));
        assert_eq!(bag["blade"],15);assert_eq!(version,0);assert!(instances.is_empty());
    }
}
